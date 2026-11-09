import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { message } from 'antd'
import Api from '@/apis/data-generation'
import { PLATFORM_BASE_URL } from '@/request/platform-https'

type ScenarioPlanResponse = ScenarioPlan & {
  _id?: string
  plan?: Partial<ScenarioPlan>
  taskId?: string
  taskDescription?: string
  targetTags?: string[]
  targetScenarioCount?: number
  interpretationNotes?: string
}

const toStringArray = (value: unknown) => {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === 'string')
  return []
}

export const normalizeScenarioPlan = (rawPlan: ScenarioPlanResponse): ScenarioPlan => {
  const nestedPlan = rawPlan.plan || {}
  return {
    ...rawPlan,
    ...nestedPlan,
    id: rawPlan.id || rawPlan._id || nestedPlan.id,
    task_id: rawPlan.task_id || nestedPlan.task_id || rawPlan.taskId || '',
    task_description: rawPlan.task_description || nestedPlan.task_description || rawPlan.taskDescription || '',
    target_tags: toStringArray(rawPlan.target_tags || nestedPlan.target_tags || rawPlan.targetTags),
    interpretation_notes: rawPlan.interpretation_notes || nestedPlan.interpretation_notes || rawPlan.interpretationNotes || '',
  }
}

type GenerationFormSelections = {
  taskId: string
  tagTreeName: string
  query: string
}

type GenerationContextValue = {
  // 步骤与计划
  currentStep: number
  setCurrentStep: (step: number | ((prev: number) => number)) => void
  plan: ScenarioPlan | undefined
  setPlan: (plan: ScenarioPlan | undefined) => void

  // 场景生成相关
  scenarios: GenerationScenario[]
  setScenarios: React.Dispatch<React.SetStateAction<GenerationScenario[]>>
  progress: ScenarioGenerationProgress | undefined
  setProgress: (p: ScenarioGenerationProgress | undefined) => void
  generatingScenarios: boolean
  selectedScenarioIds: string[]
  setSelectedScenarioIds: React.Dispatch<React.SetStateAction<string[]>>
  scenarioGenerationStopped: boolean
  setScenarioGenerationStopped: (v: boolean) => void

  // 用例生成相关
  caseProgress: CaseGenerationProgress | undefined
  setCaseProgress: (p: CaseGenerationProgress | undefined) => void
  result: GenerateCasesResult | undefined
  setResult: React.Dispatch<React.SetStateAction<GenerateCasesResult | undefined>>

  // 表单选择
  formSelections: GenerationFormSelections
  setFormSelections: React.Dispatch<React.SetStateAction<GenerationFormSelections>>

  // 数据集列表（生成用例后会刷新）
  datasets: ComplexReasoningDataset[]
  setDatasets: React.Dispatch<React.SetStateAction<ComplexReasoningDataset[]>>

  // 操作
  generateScenarios: (planId: string) => Promise<void>
  stopScenarioGeneration: () => Promise<void>
  refreshScenarios: (taskId: string) => Promise<void>
  resetGeneration: () => void

  // 用例生成的 AbortController ref（由页面在发起时设置，刷新时由 Provider 统一取消后端任务）
  caseGenerationAbortRef: React.MutableRefObject<AbortController | null>
}

const GenerationContext = createContext<GenerationContextValue | null>(null)

export const GenerationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [currentStep, setCurrentStep] = useState(0)
  const [plan, setPlan] = useState<ScenarioPlan>()
  const [scenarios, setScenarios] = useState<GenerationScenario[]>([])
  const [progress, setProgress] = useState<ScenarioGenerationProgress>()
  const [caseProgress, setCaseProgress] = useState<CaseGenerationProgress>()
  const [result, setResult] = useState<GenerateCasesResult>()
  const [generatingScenarios, setGeneratingScenarios] = useState(false)
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([])
  const [scenarioGenerationStopped, setScenarioGenerationStopped] = useState(false)
  const [datasets, setDatasets] = useState<ComplexReasoningDataset[]>([])
  const [formSelections, setFormSelections] = useState<GenerationFormSelections>({
    taskId: '',
    tagTreeName: '',
    query: '',
  })

  // SSE 连接控制器，存活于 Provider 中，不受路由切换影响
  const scenarioGenerationAbortRef = useRef<AbortController | null>(null)
  // 用例生成的 AbortController（由页面在发起时设置，刷新时由 Provider 统一取消）
  const caseGenerationAbortRef = useRef<AbortController | null>(null)
  // 防止重复触发的 guard flag
  const generatingRef = useRef(false)

  // 页面刷新/关闭时通知后端停止正在运行的生成任务
  useEffect(() => {
    const handleBeforeUnload = () => {
      // 场景生成：通知后端取消
      if (plan?.id && generatingScenarios) {
        const planId = plan.id
        // 使用 sendBeacon 保证刷新时请求能发出
        const blob = new Blob(
          [JSON.stringify({ scenarioPlanId: planId })],
          { type: 'application/json' }
        )
        navigator.sendBeacon(
          `${PLATFORM_BASE_URL}/scenario-generation-stream/cancel`,
          blob
        )
      }
      // 用例生成：通知后端取消
      if (caseGenerationAbortRef.current && !caseGenerationAbortRef.current.signal.aborted) {
        // 用例取消需要 datasetId，由页面在设置 ref 时附带
        const caseCancelData = (caseGenerationAbortRef.current as any).cancelData
        if (caseCancelData) {
          const blob = new Blob(
            [JSON.stringify(caseCancelData)],
            { type: 'application/json' }
          )
          navigator.sendBeacon(
            `${PLATFORM_BASE_URL}/case-generation-stream/cancel`,
            blob
          )
        }
      }
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
      // Provider 卸载时也取消（通常不会发生，Provider 生命周期 = App）
      handleBeforeUnload()
    }
  }, [plan?.id, generatingScenarios])

  const generateScenarios = useCallback(async (planId: string) => {
    if (generatingRef.current || generatingScenarios) {
      message.info('场景正在生成中，请等待完成')
      return
    }
    if (!planId) {
      message.error('当前场景生成计划缺少 id，无法生成场景。请重新生成计划或检查后端响应是否返回 id。')
      return
    }

    // 立即上锁，避免重复调用
    generatingRef.current = true
    setGeneratingScenarios(true)
    setScenarioGenerationStopped(false)
    setProgress(undefined)
    setScenarios([])
    setSelectedScenarioIds([])
    setCaseProgress(undefined)
    setResult(undefined)

    try {
      const abortController = new AbortController()
      scenarioGenerationAbortRef.current = abortController
      await Api.scenario.generateStream(
        {
          scenarioPlanId: planId,
          saveToDb: true,
        },
        (event) => {
          if (event.type === 'progress') {
            setProgress(event.data)
          }
          if (event.type === 'scenario') {
            setScenarios((prev) => {
              const next = event.data.scenario
              if (prev.some((item) => item.scenario_id === next.scenario_id)) return prev
              setSelectedScenarioIds((ids) => Array.from(new Set([...ids, next.scenario_id])))
              return [...prev, next]
            })
          }
          if ((event as any).type === 'scenario_deleted') {
            const deletedId = (event as any).data.scenarioId
            setScenarios((prev) => prev.filter((s) => s.scenario_id !== deletedId))
            setSelectedScenarioIds((prev) => prev.filter((id) => id !== deletedId))
          }
          if (event.type === 'error') {
            message.error(event.data.message)
          }
          if (event.type === 'complete') {
            message.success(`场景生成完成：${event.data.actualCount}/${event.data.targetCount}`)
          }
        },
        undefined,
        abortController.signal
      )

      // 完成后从数据库拉取最终列表，确保一致性
      const planRef = plan
      if (planRef?.task_id) {
        const finalScenarios = await Api.scenario.listByGenerationTask(planRef.task_id)
        setScenarios(finalScenarios)
        setSelectedScenarioIds(finalScenarios.map((s) => s.scenario_id))
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        setScenarioGenerationStopped(true)
        setProgress(undefined)
        message.info('场景生成已终止')
      } else {
        throw error
      }
    } finally {
      scenarioGenerationAbortRef.current = null
      generatingRef.current = false
      setGeneratingScenarios(false)
    }
  }, [generatingScenarios, plan])

  const stopScenarioGeneration = useCallback(async () => {
    setScenarioGenerationStopped(true)
    if (plan?.id) {
      try {
        await Api.scenario.cancelGeneration({ scenarioPlanId: plan.id })
      } catch {
        // 请求取消失败时，仍然执行前端断流，避免页面卡住
      }
    }
    scenarioGenerationAbortRef.current?.abort()
  }, [plan?.id])

  const refreshScenarios = useCallback(async (taskId: string) => {
    if (!taskId) return
    const finalScenarios = await Api.scenario.listByGenerationTask(taskId)
    setScenarios(finalScenarios)
    setSelectedScenarioIds(finalScenarios.map((scenario) => scenario.scenario_id))
  }, [])

  const resetGeneration = useCallback(() => {
    scenarioGenerationAbortRef.current?.abort()
    scenarioGenerationAbortRef.current = null
    generatingRef.current = false
    setGeneratingScenarios(false)
    setScenarioGenerationStopped(false)
    setPlan(undefined)
    setScenarios([])
    setSelectedScenarioIds([])
    setProgress(undefined)
    setCaseProgress(undefined)
    setResult(undefined)
    setCurrentStep(0)
    setFormSelections({ taskId: '', tagTreeName: '', query: '' })
  }, [])

  const value: GenerationContextValue = {
    currentStep,
    setCurrentStep,
    plan,
    setPlan,
    scenarios,
    setScenarios,
    progress,
    setProgress,
    generatingScenarios,
    selectedScenarioIds,
    setSelectedScenarioIds,
    scenarioGenerationStopped,
    setScenarioGenerationStopped,
    caseProgress,
    setCaseProgress,
    result,
    setResult,
    formSelections,
    setFormSelections,
    datasets,
    setDatasets,
    generateScenarios,
    stopScenarioGeneration,
    refreshScenarios,
    resetGeneration,
    caseGenerationAbortRef,
  }

  return <GenerationContext.Provider value={value}>{children}</GenerationContext.Provider>
}

export const useGeneration = (): GenerationContextValue => {
  const ctx = useContext(GenerationContext)
  if (!ctx) {
    throw new Error('useGeneration 必须在 GenerationProvider 内部使用')
  }
  return ctx
}
