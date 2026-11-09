import styles from './index.module.less'
import {
  Button,
  Collapse,
  InputNumber,
  List,
  message,
  Modal,
  notification,
  Segmented,
  Select,
  Spin,
  Switch,
  Tag,
  Tooltip,
} from 'antd'
import {
  AudioOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import taskApi from '@/apis/task-data'
import {
  fetchAdapterConfig,
  fetchPausedRuns,
  fetchTaskRunStatus,
  frontendVadFromConfig,
  loadStoredAdapterConfig,
  saveAdapterConfig,
  type PausedRunItem,
  type VoiceAdapterConfig,
} from './adapter-config'
import ExDrawer from '@/components/Form/drawer'
import { useOptions } from '@/hooks/options'
import { BrowserVoiceAudio, type TtsPlayHandler } from './audio-helper'
import { WsHeartbeat } from './WsHeartbeat'
import AdapterConfigForm from './adapter-config-form'
import LocalRecorderStatusForm from './local-recorder-status'
import {
  loadLocalRecorderConfig,
  localRecorderShouldRun,
  localRecorderStart,
  localRecorderStop,
  localRecorderWriteCaseResult,
  type LocalRecorderConfig,
  type LocalRecorderStopItem,
} from './local-recorder-client'
import { BASE_URL } from '@/request/https'
import CaseTimeline from './case-timeline'
import type { CaseWaitHint } from './case-detail-view'
import CaseListPanel from './case-list-panel'
import VoiceCaseSourceBar from './voice-case-source-bar'
import VoiceCaseForm, { normalizeVoiceCaseForm, toVoiceCaseFormData } from './case-form'
import { useResizableSplit } from './use-resizable-split'
import { loadDatasetCases, loadVoiceCaseOptions, type VoiceCaseOption } from './case-catalog'
import { validateVoiceCase } from './case-state'
import { INITIAL_RUN_VIEW_STATE, voiceRunReducer, type CaseStatus, type WsPayload } from './run-state'
import SystemTrace from './system-trace'
import {
  fetchVoiceAgentOptions,
  isVoiceTarget,
  VOICE_ONLY_FALLBACK,
  VOICE_TEST_TARGET_AGENT_V1,
  VOICE_TEST_TARGET_VOICE,
  type VoiceTestAgentOption,
} from './agent-catalog'

import { getVoiceTestWsUrl } from './ws-url'
import AsrDemo from './asr-demo'
import useApiModeStore from '@/stores/apiMode'

type CaseLoadStatus = 'loading' | 'ready' | 'error'

const phaseTag: Record<string, string> = {
  speaking: '播音',
  listening: '收音',
  idle: '空闲',
}

const connectionTag: Record<string, { color: string; label: string }> = {
  disconnected: { color: 'default', label: '未连接' },
  connecting: { color: 'processing', label: '连接中' },
  connected: { color: 'blue', label: '已连接' },
  ready: { color: 'success', label: '已就绪' },
  error: { color: 'error', label: '异常' },
}

type RunMode = 'single' | 'batch'
type BatchPace = 'auto' | 'manual'

type BatchProgress = {
  completed: number
  total: number
  currentCase?: string
}

type CatalogLoadStatus = 'idle' | 'loading' | 'ready' | 'error'

type BatchNavItem = {
  index: number
  caseId: string
  status?: CaseStatus
  repeatIndex?: number
  repeatN?: number
}

const RUN_MODE_REMARK: Record<RunMode, string> = {
  single: '单用例：标准示例或从数据集选一条，可编辑后调试；可设轮次，结果不入库。',
  batch: '批量测试：按数据集执行，每条可跑 N 轮（epoch），结果会写入数据库。',
}

const App: React.FC = () => {
  const isLegacy = useApiModeStore((s) => s.mode) === 'legacy'
  const [messageApi, contextHolder] = message.useMessage()
  const [notifyApi, notifyHolder] = notification.useNotification()
  const [caseForm, setCaseForm] = useState<ComplexReasoningCase | null>(null)
  const [caseLoadStatus, setCaseLoadStatus] = useState<CaseLoadStatus>('loading')
  const [caseOptions, setCaseOptions] = useState<VoiceCaseOption[]>([])
  const [selectedCaseKey, setSelectedCaseKey] = useState('')
  const [runMode, setRunMode] = useState<RunMode>('single')
  const [agentOptions, setAgentOptions] = useState<VoiceTestAgentOption[]>(VOICE_ONLY_FALLBACK)
  const [selectedAgentType, setSelectedAgentType] = useState(VOICE_TEST_TARGET_VOICE)
  const [batchPace, setBatchPace] = useState<BatchPace>('auto')
  const [batchPaused, setBatchPaused] = useState(false)
  // 流式 ASR 体验弹窗开关
  const [asrOpen, setAsrOpen] = useState(false)
  // 暂停任务列表弹窗：用户点"恢复任务"按钮时实时查 /paused_runs 填充
  const [pausedRunsList, setPausedRunsList] = useState<Array<{
    task_run_id: string
    progress?: { completed?: number; total?: number }
    metadata?: Record<string, unknown>
    updated_time?: string
  }>>([])
  // 列表弹窗加载中标志
  const [pausedRunsLoading, setPausedRunsLoading] = useState(false)
  const [datasetId, setDatasetId] = useState<string>()
  const [singleDatasetId, setSingleDatasetId] = useState<string>()
  const [singleCaseCatalog, setSingleCaseCatalog] = useState<ComplexReasoningCase[]>([])
  const [singleCatalogLoadStatus, setSingleCatalogLoadStatus] = useState<CatalogLoadStatus>('idle')
  const [singleSelectedCaseId, setSingleSelectedCaseId] = useState('')
  const [running, setRunning] = useState(false)
  const [waitingForNext, setWaitingForNext] = useState(false)
  const [selectedCaseIndex, setSelectedCaseIndex] = useState<number | null>(null)
  const [batchCaseCatalog, setBatchCaseCatalog] = useState<ComplexReasoningCase[]>([])
  const [catalogLoadStatus, setCatalogLoadStatus] = useState<CatalogLoadStatus>('idle')
  const [batchCollapseKeys, setBatchCollapseKeys] = useState<string[]>(['config'])
  const [enableJudge, setEnableJudge] = useState(true)
  const [repeatN, setRepeatN] = useState(1)
  const [configOpen, setConfigOpen] = useState(false)
  const [adapterConfig, setAdapterConfig] = useState<VoiceAdapterConfig>(loadStoredAdapterConfig)
  const [localRecorderConfig, setLocalRecorderConfig] = useState<LocalRecorderConfig>(loadLocalRecorderConfig)
  const [phase, setPhase] = useState('idle')
  const [batchProgress, setBatchProgress] = useState<BatchProgress | null>(null)
  const [lastTaskRunId, setLastTaskRunIdState] = useState<string>(() => {
    return localStorage.getItem('vt_last_task_run_id') || undefined
  })
  const setLastTaskRunId = useCallback((id: string | undefined) => {
    setLastTaskRunIdState(id)
    if (id) {
      localStorage.setItem('vt_last_task_run_id', id)
    } else {
      localStorage.removeItem('vt_last_task_run_id')
    }
  }, [])
  const [runView, dispatchRun] = useReducer(voiceRunReducer, INITIAL_RUN_VIEW_STATE)
  const [scrollToCaseIndex, setScrollToCaseIndex] = useState<number | null>(null)
  const [caseWaitHint, setCaseWaitHint] = useState<CaseWaitHint | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  /** WS 心跳实例：半开连接兜底，断网时 onclose/onerror 不触发，靠 ping/pong 超时判定 */
  const heartbeatRef = useRef<WsHeartbeat | null>(null)
  const audioRef = useRef<BrowserVoiceAudio | null>(null)
  const caseFormRef = useRef<ComplexReasoningCase | null>(null)
  const recordingCaseIdRef = useRef('')
  const pendingRecordCaseIdRef = useRef('')
  const pendingRecordRunIndexRef = useRef(0)
  /** key=case_id#r{NN} 或 case_id，value=/start 返回的 dir；/case_result 时取出来传给后端 */
  const recordingDirRef = useRef<Map<string, string>>(new Map())
  /** 本遍已尝试过开录（含失败），避免多段冷启动重复 start / 重复报错 */
  const recordStartAttemptedKeyRef = useRef('')
  const singleCaseIdForRunRef = useRef('')
  const repeatNForRunRef = useRef(1)
  /** 单用例本次运行是否已写过 case_result，避免 error 事件重复写 */
  const singleCaseResultWrittenRef = useRef(false)
  const taskRunIdRef = useRef('')
  const localRecorderConfigRef = useRef(localRecorderConfig)
  /** WS 回调里读：是否语音通道（与 isVoiceChannel 同步） */
  const isVoiceChannelRef = useRef(isVoiceTarget(selectedAgentType))
  const prevRunModeRef = useRef(runMode)
  /** 恢复模式标志：onopen 时发 resume_confirm action=continue 而不是 start_batch */
  const resumeOnOpenRef = useRef(false)
  /** 恢复时使用的 task_run_id（由 resumeFromStoredRef 写入，onopen 读取） */
  const resumeTaskRunIdRef = useRef<string>('')
  const [datasetOptions] = useOptions(taskApi.complexReasoningDataset.list, undefined, (dataset) => ({
    label: dataset.item_count == null ? dataset.name : `${dataset.name}（${dataset.item_count} 条）`,
    value: dataset.id,
    data: dataset,
  }))
  const batchDatasetOptions = datasetOptions
  const isVoiceChannel = isVoiceTarget(selectedAgentType)

  useEffect(() => {
    localRecorderConfigRef.current = localRecorderConfig
  }, [localRecorderConfig])

  useEffect(() => {
    isVoiceChannelRef.current = isVoiceChannel
  }, [isVoiceChannel])

  useEffect(() => {
    taskRunIdRef.current = lastTaskRunId || ''
  }, [lastTaskRunId])

  useEffect(() => {
    if (!caseWaitHint || caseWaitHint.remainingSec <= 0) {
      return
    }
    const timer = window.setTimeout(() => {
      setCaseWaitHint((prev) => {
        if (!prev || prev.remainingSec <= 1) {
          return null
        }
        return { ...prev, remainingSec: prev.remainingSec - 1 }
      })
    }, 1000)
    return () => window.clearTimeout(timer)
  }, [caseWaitHint])

  const notifyRecordingSaved = useCallback((item: LocalRecorderStopItem) => {
    if (!item.ok) {
      dispatchRun({
        type: 'push_system',
        level: 'error',
        text: item.message || `本地记录无效：${item.dir}`,
      })
      return
    }
    dispatchRun({
      type: 'push_system',
      level: 'info',
      text: `本地记录已保存：${item.dir}`,
    })
  }, [])

  const tryStartCaseRecording = useCallback(async () => {
    // 非 voice / 未开启：一律不录
    const cfg = localRecorderConfigRef.current
    const caseId = pendingRecordCaseIdRef.current
    const runIndex = pendingRecordRunIndexRef.current
    const attemptKey = runIndex > 0 ? `${caseId}#r${runIndex}` : caseId
    if (
      !localRecorderShouldRun(cfg, isVoiceChannelRef.current) ||
      !caseId.trim() ||
      recordingCaseIdRef.current === attemptKey ||
      recordStartAttemptedKeyRef.current === attemptKey
    ) {
      return
    }
    pendingRecordCaseIdRef.current = ''
    recordStartAttemptedKeyRef.current = attemptKey
    const result = await localRecorderStart(cfg, caseId, runIndex)
    if (!result) {
      dispatchRun({
        type: 'push_system',
        level: 'error',
        text: '本地记录没启动成功，请在「语音测试配置 → 本地记录」里点「检查」',
      })
      return
    }
    recordingCaseIdRef.current = attemptKey
    if (result.dir) {
      recordingDirRef.current.set(attemptKey, result.dir)
    }
    dispatchRun({
      type: 'push_system',
      level: 'info',
      text: `本地记录已开始：${result.dir}`,
    })
  }, [])

  const endCaseRecording = useCallback(
    async (caseId: string) => {
      pendingRecordCaseIdRef.current = ''
      const cfg = localRecorderConfigRef.current
      if (!localRecorderShouldRun(cfg, isVoiceChannelRef.current)) {
        recordingCaseIdRef.current = ''
        return
      }
      const recordingKey = recordingCaseIdRef.current
      if (!recordingKey) {
        return
      }
      const targetCase = caseId.trim()
      if (targetCase && recordingKey !== targetCase && !recordingKey.startsWith(`${targetCase}#r`)) {
        return
      }
      const stopCaseId = targetCase || recordingKey.split('#r')[0]
      const stopped = await localRecorderStop(cfg, stopCaseId)
      recordingCaseIdRef.current = ''
      const item = stopped[0]
      if (item) {
        notifyRecordingSaved(item)
      }
    },
    [notifyRecordingSaved]
  )

  const endAllCaseRecordings = useCallback(async () => {
    pendingRecordCaseIdRef.current = ''
    const cfg = localRecorderConfigRef.current
    if (!localRecorderShouldRun(cfg, isVoiceChannelRef.current)) {
      recordingCaseIdRef.current = ''
      return
    }
    const stopped = await localRecorderStop(cfg, '')
    recordingCaseIdRef.current = ''
    for (const item of stopped) {
      notifyRecordingSaved(item)
    }
  }, [notifyRecordingSaved])

  // 收到 batch_case_result / judge_result / judge_skipped / error 时把 outcome 转发给 local_recorder
  const writeCaseResult = useCallback(async (data: WsPayload) => {
    const cfg = localRecorderConfigRef.current
    if (!localRecorderShouldRun(cfg, isVoiceChannelRef.current)) {
      return
    }
    // batch_case_result 自带 case_id；单用例事件（judge_result/judge_skipped/error）从 ref 取
    const caseId = (data.case_id || singleCaseIdForRunRef.current || '').trim()
    if (!caseId) {
      return
    }
    // 单用例模式：一次运行只写一次结果，避免 error 事件重复写
    const isSingleMode = !data.case_id
    if (isSingleMode && singleCaseResultWrittenRef.current) {
      return
    }
    // run_index 与 /start 保持一致：repeat_n>1 才传，否则 0
    const runIndex = (data.repeat_n || 1) > 1 ? data.repeat_index || 0 : 0
    // attemptKey 与 /start 时存的一致，用来取 dir 传给后端
    const attemptKey = runIndex > 0 ? `${caseId}#r${runIndex}` : caseId
    const dir = recordingDirRef.current.get(attemptKey) || recordingDirRef.current.get(caseId) || ''
    if (!dir) {
      // 没录上（/start 失败/未调用），直接跳过写结果
      return
    }
    const taskRunItemId = data.task_run_item_id?.trim() || ''
    const callbackUrl = taskRunItemId
      ? `${window.location.origin}${BASE_URL}/task_run_item/${taskRunItemId}/metadata`
      : ''
    const result = await localRecorderWriteCaseResult(cfg, {
      case_id: caseId,
      dir,
      run_index: runIndex,
      execution_success: !!data.execution_success,
      execution_error: data.execution_error ?? null,
      judge_status: data.judge_status || 'not_run',
      is_passed: data.is_passed ?? null,
      reason: data.reason ?? null,
      repeat_index: data.repeat_index ?? null,
      repeat_n: data.repeat_n ?? null,
      task_run_item_id: taskRunItemId,
      callback_url: callbackUrl,
    })
    if (isSingleMode && result && result.ok) {
      singleCaseResultWrittenRef.current = true
    }
    if (result && result.ok) {
      dispatchRun({
        type: 'push_system',
        level: 'info',
        text: `本地记录结果已写入：${result.result_tag} → ${result.dir}`,
      })
    } else if (result && !result.ok) {
      dispatchRun({
        type: 'push_system',
        level: 'error',
        text: result.message || `本地记录结果写入失败：${caseId}`,
      })
    }
  }, [])

  const onTtsPlay = useCallback<TtsPlayHandler>(
    async (text, voice, hooks) => {
      try {
        if (!audioRef.current) {
          audioRef.current = new BrowserVoiceAudio()
        }
        await audioRef.current.playTtsText(text, voice, hooks)
      } catch {
        messageApi.error('TTS 播放失败')
      }
    },
    [messageApi]
  )

  const activeCaseIndex = useMemo(() => {
    if (runView.activeCaseIndex !== null) {
      return runView.activeCaseIndex
    }
    const runningCase = runView.cases.find((item) => item.status === 'running')
    if (runningCase) {
      return runningCase.index
    }
    const waitingCase = runView.cases.find((item) => item.status === 'waiting')
    return waitingCase?.index ?? null
  }, [runView.activeCaseIndex, runView.cases])

  const batchNavItems = useMemo((): BatchNavItem[] => {
    const showBatchRunNav = runMode === 'batch' && runView.cases.length > 0
    if (showBatchRunNav) {
      return runView.cases.map((item) => ({
        index: item.index,
        caseId: item.caseId,
        status: item.status,
        repeatIndex: item.repeatIndex,
        repeatN: item.repeatN,
      }))
    }
    return batchCaseCatalog.map((item, itemIndex) => ({
      index: itemIndex + 1,
      caseId: item.case_id || '',
      status: undefined,
    }))
  }, [runMode, runView.cases, batchCaseCatalog])

  const selectedNavItem = useMemo(
    () => batchNavItems.find((item) => item.index === selectedCaseIndex) ?? null,
    [batchNavItems, selectedCaseIndex]
  )

  const selectedCaseDefinition = useMemo(() => {
    if (!selectedNavItem?.caseId) {
      return null
    }
    return batchCaseCatalog.find((item) => item.case_id === selectedNavItem.caseId) ?? null
  }, [batchCaseCatalog, selectedNavItem])

  const singleCaseIdOptions = useMemo(
    () =>
      singleCaseCatalog.map((item) => ({
        label: item.case_id || '',
        value: item.case_id || '',
        title: item.case_description,
      })),
    [singleCaseCatalog]
  )

  const applyCaseTemplate = useCallback((option: VoiceCaseOption) => {
    const nextCase = { ...option.case }
    caseFormRef.current = nextCase
    setSelectedCaseKey(option.key)
    setCaseForm(nextCase)
    setSingleSelectedCaseId('')
  }, [])

  const applyCaseFromCatalog = useCallback((caseDoc: ComplexReasoningCase) => {
    const nextCase = { ...caseDoc }
    caseFormRef.current = nextCase
    setSelectedCaseKey('')
    setCaseForm(nextCase)
    setSingleSelectedCaseId(caseDoc.case_id || '')
  }, [])

  const handleCaseTemplateChange = useCallback(
    (caseKey: string) => {
      if (!caseKey) {
        setSelectedCaseKey('')
        return
      }
      const option = caseOptions.find((item) => item.key === caseKey)
      if (!option) {
        return
      }
      setSingleDatasetId(undefined)
      setSingleSelectedCaseId('')
      applyCaseTemplate(option)
    },
    [applyCaseTemplate, caseOptions]
  )

  useEffect(() => {
    fetchVoiceAgentOptions()
      .then((options) => {
        if (options?.length) {
          setAgentOptions(options)
        }
      })
      .catch(() => {
        setAgentOptions(VOICE_ONLY_FALLBACK)
      })
  }, [])

  useEffect(() => {
    let cancelled = false
    setCaseLoadStatus('loading')
    loadVoiceCaseOptions()
      .then(({ options, missing }) => {
        if (cancelled) {
          return
        }
        setCaseOptions(options)
        if (missing.length > 0) {
          messageApi.warning(`有 ${missing.length} 个展示用例未加载（数据集或 case_id 未找到）`)
        }
        const defaultOption = options[0]
        if (defaultOption) {
          applyCaseTemplate(defaultOption)
          setCaseLoadStatus('ready')
          return
        }
        caseFormRef.current = null
        setCaseForm(null)
        setSelectedCaseKey('')
        setCaseLoadStatus('error')
        messageApi.warning('代表性用例均未加载成功，请检查数据集与 case_id 配置')
      })
      .catch(() => {
        if (!cancelled) {
          setCaseOptions([])
          caseFormRef.current = null
          setCaseForm(null)
          setSelectedCaseKey('')
          setCaseLoadStatus('error')
          messageApi.error('加载用例列表失败')
        }
      })
    return () => {
      cancelled = true
    }
  }, [applyCaseTemplate, messageApi])

  useEffect(() => {
    if (runMode !== 'batch' || !datasetId) {
      setBatchCaseCatalog([])
      setCatalogLoadStatus('idle')
      return
    }

    let cancelled = false
    setCatalogLoadStatus('loading')
    loadDatasetCases(datasetId)
      .then((cases) => {
        if (cancelled) {
          return
        }
        setBatchCaseCatalog(cases)
        setCatalogLoadStatus('ready')
      })
      .catch(() => {
        if (!cancelled) {
          setBatchCaseCatalog([])
          setCatalogLoadStatus('error')
          messageApi.error('加载数据集用例失败')
        }
      })

    return () => {
      cancelled = true
    }
  }, [datasetId, messageApi, runMode])

  useEffect(() => {
    if (runMode !== 'single' || !singleDatasetId) {
      setSingleCaseCatalog([])
      setSingleCatalogLoadStatus('idle')
      return
    }

    let cancelled = false
    setSingleCatalogLoadStatus('loading')
    loadDatasetCases(singleDatasetId)
      .then((cases) => {
        if (cancelled) {
          return
        }
        setSingleCaseCatalog(cases)
        setSingleCatalogLoadStatus('ready')
      })
      .catch(() => {
        if (!cancelled) {
          setSingleCaseCatalog([])
          setSingleCatalogLoadStatus('error')
          messageApi.error('加载数据集用例失败')
        }
      })

    return () => {
      cancelled = true
    }
  }, [messageApi, runMode, singleDatasetId])

  useEffect(() => {
    if (runMode !== 'single') {
      return
    }
    setSingleSelectedCaseId('')
  }, [runMode, singleDatasetId])

  const resetIdleSessionView = useCallback(() => {
    dispatchRun({ type: 'reset' })
    setBatchProgress(null)
    setScrollToCaseIndex(null)
  }, [])

  // 仅切换数据集时清空预览态；批量跑完 running→false 不能触发 reset，否则会清掉结果。
  useEffect(() => {
    if (runMode !== 'batch') {
      return
    }
    setSelectedCaseIndex(null)
    if (running) {
      return
    }
    resetIdleSessionView()
  }, [datasetId, runMode, resetIdleSessionView])

  useEffect(() => {
    if (prevRunModeRef.current === runMode) {
      return
    }
    prevRunModeRef.current = runMode
    if (!running) {
      resetIdleSessionView()
    }
  }, [runMode, running, resetIdleSessionView])

  useEffect(() => {
    if (running) {
      setBatchCollapseKeys([])
      return
    }
    if (batchNavItems.length > 0) {
      setBatchCollapseKeys(['config', 'nav'])
    }
  }, [running, batchNavItems.length])

  const batchConfigSummary = useMemo(() => {
    const datasetName =
      batchDatasetOptions.find((item) => item.value === datasetId)?.label?.toString() ?? '未选择数据集'
    const paceLabel = batchPace === 'manual' ? '手动' : '自动'
    const repeatLabel = repeatN > 1 ? ` · 每条×${repeatN}轮` : ''
    return `${datasetName} · ${paceLabel}${repeatLabel}`
  }, [batchDatasetOptions, batchPace, datasetId, repeatN])

  const batchNavSummary = useMemo(() => {
    if (batchProgress) {
      return `进度 ${batchProgress.completed}/${batchProgress.total}`
    }
    if (selectedNavItem) {
      return `#${selectedNavItem.index} ${selectedNavItem.caseId}`
    }
    return `共 ${batchNavItems.length} 条`
  }, [batchNavItems.length, batchProgress, selectedNavItem])

  const handleCaseFormChange = useCallback((next: ComplexReasoningCase) => {
    caseFormRef.current = next
  }, [])

  const releaseSession = useCallback((reason: 'user_stop' | 'page_unload' = 'user_stop') => {
    void endAllCaseRecordings()
    // 主动关 WS 前停心跳，避免关 ws 后心跳仍在计时误触发 onTimeout
    heartbeatRef.current?.stop()
    heartbeatRef.current = null
    const ws = wsRef.current
    if (ws) {
      ws.onmessage = null
      ws.onerror = null
      ws.onclose = null
      if (ws.readyState === WebSocket.OPEN) {
        // page_unload（刷新/关页/切路由）：发 pause，让后端标 PAUSED 可续跑
        // user_stop（用户点结束按钮）：发 stop，后端标 FAILED 不可恢复
        const msgType = reason === 'page_unload' && running ? 'pause' : 'stop'
        ws.send(JSON.stringify({ type: msgType }))
      }
      ws.close()
      wsRef.current = null
    }
    audioRef.current?.stop()
    audioRef.current = null
  }, [endAllCaseRecordings, running])

  const cleanup = useCallback(() => {
    releaseSession()
    setRunning(false)
    setWaitingForNext(false)
    setSelectedCaseIndex(null)
    setPhase('idle')
    setBatchPaused(false)
    // 重置恢复模式标志：避免上次续跑未走完（error/done 未触发）时，下次点"开始"误走 resume 分支
    resumeOnOpenRef.current = false
    resumeTaskRunIdRef.current = ''
    dispatchRun({ type: 'set_connection', connection: 'disconnected' })
  }, [releaseSession])

  useEffect(() => {
    fetchAdapterConfig()
      .then((cfg) => {
        if (cfg) {
          setAdapterConfig((prev) => ({ ...cfg, ...prev }))
        }
      })
      .catch(() => {
        // 使用 localStorage / FALLBACK_ADAPTER_CONFIG
      })
  }, [])

  // 用 ref 持有 releaseSession，避免 running 变化导致 releaseSession 重建时
  // 触发 useEffect cleanup 误清 audioRef（导致 TTS PCM 到达时 audioRef=null 无声）
  const releaseSessionRef = useRef(releaseSession)
  releaseSessionRef.current = releaseSession
  useEffect(() => {
    const onPageHide = () => releaseSessionRef.current('page_unload')
    window.addEventListener('pagehide', onPageHide)
    return () => {
      window.removeEventListener('pagehide', onPageHide)
      releaseSessionRef.current('page_unload')
    }
  }, [])

  // 恢复函数 ref：避免 useEffect 依赖 handleStart 导致闭包陷阱
  const resumeFromStoredRef = useRef<(taskRunId?: string) => void>(() => {})

  // 页面加载时只检查 localStorage 的 id：PAUSED 弹轻提醒，非 PAUSED 静默清理
  useEffect(() => {
    let cancelled = false
    void (async () => {
      const storedId = localStorage.getItem('vt_last_task_run_id')
      if (!storedId) return
      const info = await fetchTaskRunStatus(storedId)
      if (cancelled) return
      if (!info || !info.resumable) {
        // 不可恢复（状态非 PAUSED 或 metadata 缺 dataset_id）：静默清理 localStorage
        setLastTaskRunId(undefined)
        return
      }
      // 可恢复：弹轻提醒 notification
      const name = (info.metadata?.dataset_name as string) || '未命名任务'
      const completed = info.progress?.completed ?? 0
      const total = info.progress?.total ?? 0
      const pct = total > 0 ? Math.round((completed / total) * 100) : 0
      notifyApi.info({
        key: 'vt_resume_prompt',
        message: '检测到未完成任务',
        description: `任务名：${name}，进度：${completed} / ${total} (${pct}%)`,
        btn: (
          <Button
            type="primary"
            size="small"
            icon={<PlayCircleOutlined />}
            onClick={() => {
              notifyApi.destroy('vt_resume_prompt')
              resumeFromStoredRef.current(info.task_run_id)
            }}
          >
            恢复
          </Button>
        ),
        duration: 0,
        placement: 'topRight',
      })
    })()
    return () => { cancelled = true }
  }, [notifyApi, setLastTaskRunId])

  const handleStop = useCallback(() => {
    // 结束后的统一清理
    const doCleanup = () => {
      releaseSession()
      setRunning(false)
      setWaitingForNext(false)
      setSelectedCaseIndex(null)
      setPhase('idle')
      // 手动结束：清理 localStorage，避免刷新后误弹恢复通知（task_run 已被后端标 FAILED）
      setLastTaskRunId(undefined)
      notifyApi.destroy('vt_resume_prompt')
      dispatchRun({ type: 'push_system', level: 'info', text: '已手动结束' })
      dispatchRun({ type: 'set_connection', connection: 'disconnected' })
    }
    // 单用例：无续跑概念，直接结束；批跑：task_run 永久 FAILED，二次确认防手滑
    // 注：effectiveRunMode 在下方定义（TDZ），这里用 isVoiceChannel/runMode 同等计算
    const isSingle = isVoiceChannel ? runMode === 'single' : true
    if (isSingle) {
      doCleanup()
      return
    }
    Modal.confirm({
      title: '确认结束任务？',
      content: '结束后当前任务将不可恢复，已跑完的数据会保留但无法继续。',
      okText: '确认结束',
      cancelText: '再想想',
      okType: 'danger',
      onOk: doCleanup,
    })
  }, [isVoiceChannel, runMode, releaseSession, setLastTaskRunId, notifyApi])

  const sendBatchStep = useCallback((type: 'next_case' | 'skip_case') => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type }))
      setWaitingForNext(false)
    }
  }, [])

  const sendBatchPause = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'pause' }))
    }
  }, [])

  const sendBatchResume = useCallback(() => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return
    // 暂停状态下 WS 仍连接，直接发 resume_confirm action=continue 续跑当前 task_run
    const id = lastTaskRunId || localStorage.getItem('vt_last_task_run_id')
    if (!id) {
      messageApi.warning('没有可恢复的任务')
      return
    }
    wsRef.current.send(JSON.stringify({ type: 'resume_confirm', task_run_id: id, action: 'continue' }))
    setBatchPaused(false)
  }, [lastTaskRunId, messageApi])

  // 暂停列表弹窗：用户选了一个任务后走 HTTP 校验 + WS resume_confirm
  const selectPausedRun = useCallback((taskRunId: string) => {
    setPausedRunsList([])
    void resumeFromStoredRef.current(taskRunId)
  }, [])

  // 工具栏"恢复任务"按钮：实时查 /paused_runs 弹列表 Modal
  const handleShowPausedRuns = useCallback(async () => {
    if (running) {
      messageApi.warning('当前有任务正在运行，请先停止')
      return
    }
    setPausedRunsLoading(true)
    try {
      const runs = await fetchPausedRuns()
      if (runs.length === 0) {
        messageApi.info('没有可恢复的暂停任务')
        return
      }
      setPausedRunsList(runs)
    } catch {
      messageApi.error('查询暂停任务失败')
    } finally {
      setPausedRunsLoading(false)
    }
  }, [running, messageApi])

  const handleWsPayload = useCallback(
    (data: WsPayload) => {
      dispatchRun({ type: 'ws', data })

      if (data.type === 'phase') {
        setPhase(data.phase || 'idle')
      }
      if (data.type === 'batch_started' && data.case_ids?.length) {
        setBatchProgress({ completed: 0, total: data.total || 0 })
        setSelectedCaseIndex(1)
      }
      if (data.type === 'batch_case_waiting') {
        setWaitingForNext(true)
        if (data.index) {
          setScrollToCaseIndex(data.index)
        }
      }
      if (data.type === 'batch_paused') {
        setBatchPaused(true)
      }
      if (data.type === 'batch_resumed') {
        setBatchPaused(false)
        // 恢复进度（避免被后续 batch_started 重置为 0）
        const resumedCompleted = (data as { completed?: number }).completed
        const resumedTotal = (data as { total?: number }).total
        if (resumedTotal > 0) {
          setBatchProgress({
            completed: resumedCompleted ?? 0,
            total: resumedTotal,
          })
        }
      }
      if (data.type === 'batch_case_started') {
        setWaitingForNext(false)
        if (data.index) {
          setScrollToCaseIndex(data.index)
        }
        setBatchProgress({
          completed: Math.max(0, (data.index || 1) - 1),
          total: data.total || 0,
          currentCase: data.case_id,
        })
        if (data.case_id && isVoiceChannelRef.current) {
          recordStartAttemptedKeyRef.current = ''
          pendingRecordCaseIdRef.current = data.case_id
          pendingRecordRunIndexRef.current = (data.repeat_n || 1) > 1 ? data.repeat_index || 0 : 0
        }
      }
      if (data.type === 'dialogue_history') {
        // 对话结束即停录，不含 judge 阶段
        void endCaseRecording('')
      }
      if (data.type === 'batch_case_result') {
        setBatchProgress({
          completed: data.index || 0,
          total: data.total || 0,
          currentCase: data.case_id,
        })
        // 兜底：失败且无 dialogue_history 时可能仍在录
        if (recordingCaseIdRef.current) {
          void endCaseRecording(data.case_id || '')
        }
        // 把 outcome 转发给 local_recorder，写入 case_result.json + marker
        void writeCaseResult(data)
      }
      if (data.type === 'countdown_wait') {
        const seconds = Number(data.seconds) || 0
        const label = (data.label || '等待中').trim() || '等待中'
        if (seconds > 0) {
          setCaseWaitHint({ label, remainingSec: seconds })
        } else {
          setCaseWaitHint(null)
        }
      }
      if (
        data.type === 'user_query' ||
        data.type === 'batch_case_started' ||
        data.type === 'done' ||
        data.type === 'error'
      ) {
        setCaseWaitHint(null)
      }
      if (data.type === 'user_query' && pendingRecordCaseIdRef.current) {
        void tryStartCaseRecording()
      }
      if (data.type === 'batch_done') {
        void endAllCaseRecordings()
      }
    },
    [endAllCaseRecordings, endCaseRecording, tryStartCaseRecording, writeCaseResult]
  )

  const effectiveRunMode = isVoiceChannel ? runMode : 'single'
  const showBatchCaseWorkspace =
    effectiveRunMode === 'batch' && !!datasetId && (catalogLoadStatus === 'loading' || batchNavItems.length > 0)
  const showManualStepBar = effectiveRunMode === 'batch' && batchPace === 'manual' && running && waitingForNext

  const startDisabled = running || (effectiveRunMode === 'single' && caseLoadStatus !== 'ready')

  const handleStart = async () => {
    if (running) {
      return
    }

    // 恢复模式：跳过 case/dataset 校验，onopen 发 resume_confirm action=continue
    const isResume = resumeOnOpenRef.current
    // 先读出 resumeId，cleanup 会清掉 ref，需要在 cleanup 后重新写回，避免 onopen 读到空值
    const resumeId = resumeTaskRunIdRef.current

    let singleCaseToRun: ComplexReasoningCase | null = null
    if (!isResume) {
      if (effectiveRunMode === 'single') {
        if (caseLoadStatus !== 'ready' || !caseFormRef.current) {
          messageApi.warning('用例尚未加载完成，请稍候或检查配置')
          return
        }
        const currentCase = caseFormRef.current
        const formError = validateVoiceCase(currentCase)
        if (formError) {
          messageApi.warning(formError)
          return
        }
        singleCaseToRun = currentCase
      } else if (!datasetId) {
        messageApi.warning('请选择要批量测试的数据集')
        return
      }

      if (isVoiceChannel && (adapterConfig.vad_timeout_ms < 500 || adapterConfig.vad_timeout_ms > 50000)) {
        messageApi.warning('VAD 静音判停须在 500～50000 毫秒之间')
        return
      }
    }

    saveAdapterConfig(adapterConfig)

    cleanup()
    dispatchRun({ type: 'reset' })
    dispatchRun({
      type: 'configure',
      goodbyeMarkers: adapterConfig.goodbye_markers,
      goodbyeReply: adapterConfig.goodbye_reply,
    })
    setBatchProgress(null)
    taskRunIdRef.current = ''
    if (isResume) {
      // cleanup 会清 ref，但 onopen 还要读，resume 模式下立即写回
      resumeOnOpenRef.current = true
      resumeTaskRunIdRef.current = resumeId
    } else {
      setLastTaskRunId(undefined)
    }
    setScrollToCaseIndex(null)
    setSelectedCaseIndex(null)
    setCaseWaitHint(null)
    recordingCaseIdRef.current = ''
    pendingRecordCaseIdRef.current = ''
    pendingRecordRunIndexRef.current = 0
    recordingDirRef.current.clear()
    recordStartAttemptedKeyRef.current = ''
    singleCaseIdForRunRef.current = ''
    singleCaseResultWrittenRef.current = false
    repeatNForRunRef.current = Math.max(1, Math.min(50, repeatN || 1))
    isVoiceChannelRef.current = isVoiceChannel
    setRunning(true)
    dispatchRun({ type: 'set_connection', connection: 'connecting' })
    dispatchRun({ type: 'push_system', level: 'info', text: '连接 WebSocket…' })

    if (effectiveRunMode === 'single' && singleCaseToRun) {
      const payloadCase = normalizeVoiceCaseForm(toVoiceCaseFormData(singleCaseToRun))
      singleCaseIdForRunRef.current = payloadCase.case_id || ''
      // repeat_n>1 时由服务端 batch_started 展开时间线，避免先建单条再被覆盖
      if (repeatNForRunRef.current <= 1) {
        dispatchRun({
          type: 'init_single_case',
          caseId: payloadCase.case_id || '',
        })
      }
    }

    if (isVoiceChannel) {
      // 前端 VAD 开关：true=Silero VAD 段式发送；false=流式 200ms 帧发送（后端缓存节流）
      const vadEnabled = adapterConfig.frontend_vad_enabled
      const audio = new BrowserVoiceAudio({
        vad: vadEnabled,
        vadConfig: frontendVadFromConfig(adapterConfig),
      })
      audioRef.current = audio
      try {
        await audio.init()
        dispatchRun({ type: 'push_system', level: 'info', text: '麦克风已就绪' })
      } catch {
        messageApi.error('无法访问麦克风')
        dispatchRun({ type: 'push_system', level: 'error', text: '无法访问麦克风' })
        dispatchRun({ type: 'set_connection', connection: 'error' })
        cleanup()
        return
      }
      audio.startCapture((chunk) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(chunk)
        }
      })
    } else {
      dispatchRun({ type: 'push_system', level: 'info', text: '文本模式：无需麦克风' })
    }

    const ws = new WebSocket(getVoiceTestWsUrl(isLegacy))
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    // WS 心跳：半开连接兜底（断网时 onclose/onerror 不触发）
    // 10s ping + 5s pong 超时 + 连续 2 次未响应 → 判定断开，总检测时长 ~30s
    const heartbeat = new WsHeartbeat(ws, {
      intervalMs: 10_000,
      timeoutMs: 5_000,
      maxMissed: 2,
      onTimeout: () => {
        console.warn('[VT] ws heartbeat timeout, treat as disconnected')
        messageApi.warning('与服务器连接已断开（心跳超时），可刷新页面恢复任务')
        dispatchRun({ type: 'push_system', level: 'error', text: '连接已断开（心跳超时 30s 未响应）' })
        dispatchRun({ type: 'set_connection', connection: 'error' })
        cleanup()
      },
    })
    heartbeatRef.current = heartbeat

    ws.onopen = () => {
      dispatchRun({ type: 'set_connection', connection: 'connected' })
      // 启动心跳：连上后开始周期性 ping（业务消息也会重置计时，活跃时几乎不发 ping）
      heartbeat.start()
      // 恢复模式：onopen 直接发 resume_confirm action=continue（HTTP 已校验状态）
      // resumeId 在 handleStart 顶部预读（cleanup 之前），避免 ref 被 cleanup 清掉后读到空值
      if (isResume) {
        if (resumeId) {
          dispatchRun({ type: 'push_system', level: 'info', text: 'WebSocket 已连接，发送续跑确认…' })
          ws.send(JSON.stringify({ type: 'resume_confirm', task_run_id: resumeId, action: 'continue' }))
          setBatchPaused(false)
        } else {
          // 兜底：无 task_run_id 时直接结束
          messageApi.error('恢复失败：缺少 task_run_id')
          cleanup()
        }
        return
      }
      dispatchRun({
        type: 'push_system',
        level: 'info',
        text: effectiveRunMode === 'single' ? 'WebSocket 已连接，提交 TestCase' : 'WebSocket 已连接，提交数据集',
      })
      const payload =
        effectiveRunMode === 'single' && singleCaseToRun
          ? {
              type: 'start',
              agent_type: selectedAgentType,
              case: normalizeVoiceCaseForm(toVoiceCaseFormData(singleCaseToRun)),
              enable_judge: enableJudge,
              repeat_n: repeatNForRunRef.current,
              adapter_config: adapterConfig,
            }
          : {
              type: 'start_batch',
              agent_type: selectedAgentType,
              dataset_id: datasetId,
              enable_judge: enableJudge,
              repeat_n: repeatNForRunRef.current,
              adapter_config: adapterConfig,
              batch_pace: batchPace,
            }
      ws.send(JSON.stringify(payload))
    }

    ws.onmessage = (event) => {
      if (wsRef.current !== ws) {
        return
      }
      // 心跳先处理：pong 重置计数；业务消息也视为活跃，避免活跃时仍发 ping
      heartbeat.onMessage(event.data)
      if (typeof event.data === 'string') {
        const data = JSON.parse(event.data) as WsPayload
        // pong 是心跳响应，不进入业务流程
        if (data.type === 'pong') return

        if (data.type === 'user_query') {
          console.debug('[VT] ws recv user_query mode=', (data as any).mode, 'text=', (data as any).text)
          audioRef.current?.softStopPlayback()
        }
        if (data.type === 'await_playback_drain') {
          console.debug('[VT] ws recv await_playback_drain')
          void audioRef.current?.waitForPlaybackDrain().then(() => {
            console.debug('[VT] ws send playback_drained')
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({ type: 'playback_drained' }))
            }
          })
        }
        if (data.type === 'phase') {
          console.debug('[VT] ws recv phase=', data.phase)
          setPhase(data.phase || 'idle')
          audioRef.current?.setListening(data.phase === 'listening')
        }
        if (data.type === 'judge_result' && effectiveRunMode === 'single') {
          if (data.is_passed) {
            messageApi.success('评估通过')
          } else {
            messageApi.warning('评估未通过')
          }
          void writeCaseResult({
            type: 'judge_result',
            case_id: singleCaseIdForRunRef.current,
            execution_success: true,
            judge_status: 'completed',
            is_passed: data.is_passed,
            reason: data.reason,
          })
        }
        if (data.type === 'judge_skipped' && effectiveRunMode === 'single') {
          messageApi.info('对话完成，已跳过自动评测')
          void writeCaseResult({
            type: 'judge_skipped',
            case_id: singleCaseIdForRunRef.current,
            execution_success: true,
            judge_status: 'skipped',
          })
        }
        if (data.type === 'task_run_created' && data.task_run_id) {
          // 批跑一开始就有 task_run：立刻显示按钮，勿提前弹窗误导
          taskRunIdRef.current = data.task_run_id
          setLastTaskRunId(data.task_run_id)
        }
        if (data.type === 'ready' && effectiveRunMode === 'single' && repeatNForRunRef.current <= 1) {
          const caseId = singleCaseIdForRunRef.current
          if (
            caseId &&
            isVoiceChannelRef.current &&
            !recordingCaseIdRef.current &&
            recordStartAttemptedKeyRef.current !== caseId
          ) {
            pendingRecordCaseIdRef.current = caseId
          }
        }
        if (data.type === 'batch_done') {
          setWaitingForNext(false)
          setBatchProgress({ completed: data.total || 0, total: data.total || 0 })
          const taskRunId = taskRunIdRef.current
          // 单用例多遍：不弹窗（与单测结束一样，看时间线即可）
          if (!(effectiveRunMode === 'single' && !taskRunId)) {
            notifyApi.success({
              message: '批量测试完成',
              description: taskRunId
                ? '结果已写入数据库。可点击下方「查看结果」，或右上角同名按钮查看详情。'
                : '批量测试已结束。',
              btn: taskRunId ? (
                <Button
                  type="primary"
                  size="small"
                  icon={<FileSearchOutlined />}
                  onClick={() => {
                    window.open(`/task/task-run/${taskRunId}`, '_blank')
                    notifyApi.destroy()
                  }}
                >
                  查看结果
                </Button>
              ) : undefined,
              duration: 12,
              placement: 'topRight',
            })
          }
        }
        if (data.type === 'error') {
          messageApi.error(data.message || '服务错误')
          // 恢复模式查询失败：重置标志，避免下次点"开始"仍走恢复分支
          const wasResume = resumeOnOpenRef.current
          resumeOnOpenRef.current = false
          // 恢复流程中收到 error（HTTP 校验已过但 WS resume_confirm 失败）：清理 localStorage 避免下次刷新仍弹窗
          if (wasResume && lastTaskRunId) {
            setLastTaskRunId(undefined)
            notifyApi.destroy('vt_resume_prompt')
            setBatchPaused(false)
            setPausedRunsList([])
          }
          // 单用例模式：执行失败/Judge 异常时也写一次结果（若尚未写过）
          if (effectiveRunMode === 'single' && !singleCaseResultWrittenRef.current) {
            void writeCaseResult({
              type: 'error',
              message: data.message,
            })
          }
        }
        if (data.type === 'done') {
          setRunning(false)
          setWaitingForNext(false)
          audioRef.current?.setListening(false)
          setPhase('idle')
          setBatchPaused(false)
          setPausedRunsList([])
          // 任务正常结束，清理 localStorage 中的 task_run_id
          localStorage.removeItem('vt_last_task_run_id')
          // 重置恢复模式标志
          resumeOnOpenRef.current = false
        }

        // 从 log 消息里提取 sid（连接级），持久化到 localStorage，便于断网后查全链路日志
        if (data.type === 'log' && data.message) {
          const ms = data.message.match(/\[sid=([a-z0-9]+)\]/i)
          if (ms) {
            localStorage.setItem('vt_sid', ms[1])
          }
        }

        handleWsPayload(data)

        if (data.type === 'done') {
          releaseSession()
          dispatchRun({ type: 'set_connection', connection: 'disconnected' })
        }
        return
      }

      audioRef.current?.playTtsChunk(event.data as ArrayBuffer)
      console.debug('[VT] ws recv audio bytes=', (event.data as ArrayBuffer).byteLength)
    }

    ws.onerror = () => {
      heartbeat.stop()
      messageApi.error('WebSocket 连接失败')
      dispatchRun({ type: 'push_system', level: 'error', text: 'WebSocket 连接失败' })
      dispatchRun({ type: 'set_connection', connection: 'error' })
      cleanup()
    }

    ws.onclose = (ev) => {
      if (wsRef.current !== ws) return
      heartbeat.stop()
      // 能进到这里都是被动断开（releaseSession 主动关 WS 前已清 onclose 回调）
      // code=1000：后端任务正常完成/被后端主动 close → 静默
      // code!=1000：后端断网/Nginx 504/进程崩溃 → 提示用户可刷新恢复
      if (ev.code !== 1000) {
        messageApi.warning('连接已断开，可刷新页面恢复任务')
        dispatchRun({ type: 'push_system', level: 'error', text: '连接已断开，可刷新页面恢复任务' })
      }
      cleanup()
    }
  }

  // 恢复函数：HTTP 校验 task_run 状态后建 WS，onopen 直接发 resume_confirm action=continue
  resumeFromStoredRef.current = async (taskRunId?: string) => {
    if (running) {
      messageApi.warning('当前有任务正在运行，请先停止')
      return
    }
    const id = taskRunId || localStorage.getItem('vt_last_task_run_id')
    if (!id) {
      messageApi.warning('没有可恢复的任务')
      return
    }
    // HTTP 校验可恢复性：status=PAUSED 且 metadata 含 dataset_id 才放行
    const info = await fetchTaskRunStatus(id)
    if (!info || !info.resumable) {
      messageApi.warning('任务已结束或元数据缺失，无法恢复')
      setLastTaskRunId(undefined)
      notifyApi.destroy('vt_resume_prompt')
      return
    }
    // 校验通过：同步 localStorage、切 batch 模式、设置 resumePending，建 WS
    setLastTaskRunId(id)
    setRunMode('batch')
    resumeOnOpenRef.current = true
    resumeTaskRunIdRef.current = id
    void handleStart()
  }

  const handleCaseNavClick = useCallback((index: number) => {
    setSelectedCaseIndex(index)
    setScrollToCaseIndex(index)
  }, [])

  const handleSingleCaseIdChange = useCallback(
    (caseId: string) => {
      if (!caseId) {
        setSingleSelectedCaseId('')
        return
      }
      const caseDef = singleCaseCatalog.find((item) => item.case_id === caseId)
      if (caseDef) {
        applyCaseFromCatalog(caseDef)
      }
    },
    [applyCaseFromCatalog, singleCaseCatalog]
  )

  const handleSingleDatasetChange = useCallback((value?: string) => {
    setSingleDatasetId(value)
    setSingleSelectedCaseId('')
    if (value) {
      setSelectedCaseKey('')
    }
  }, [])

  const noopCaseChange = useCallback((_next: ComplexReasoningCase) => {}, [])

  const connMeta = connectionTag[runView.connection] || connectionTag.disconnected
  const {
    containerRef,
    configPanelStyle,
    collapsed,
    dragging,
    toggleCollapsed,
    onDividerPointerDown,
    onDividerPointerUp,
    onDividerDoubleClick,
  } = useResizableSplit()

  return (
    <>
      {contextHolder}
      {notifyHolder}
      <div className={styles.page}>
        <div className={styles.pageHeader}>
          {/* 第一行：配置区 + 状态指示区 */}
          <div className={styles.pageHeaderRow}>
            <div className={styles.pageHeaderLeft}>
              <div className={styles.headerScope}>
                <span className={styles.judgeToggleLabel}>被测 Agent</span>
                <Select
                  size="small"
                  className={styles.headerAgentSelect}
                  value={selectedAgentType}
                  disabled={running}
                  options={agentOptions.map((item) => ({
                    value: item.value,
                    label: item.label,
                    title: item.description,
                  }))}
                  onChange={(value) => {
                    const nextAgentType = value ?? VOICE_TEST_TARGET_VOICE
                    setSelectedAgentType(nextAgentType)
                    if (!isVoiceTarget(nextAgentType)) {
                      setRunMode('single')
                      setConfigOpen(false)
                    }
                  }}
                />
              </div>
              <div className={styles.headerDivider} aria-hidden />
              <div className={styles.headerMode}>
                <span className={styles.headerModeLabel}>运行方式</span>
                <Segmented<RunMode>
                  value={runMode}
                  disabled={running}
                  options={[
                    {
                      label: <Tooltip title={RUN_MODE_REMARK.single}>单个用例</Tooltip>,
                      value: 'single',
                    },
                    {
                      label: <Tooltip title={isVoiceChannel ? RUN_MODE_REMARK.batch : '不支持批量'}>批量数据集</Tooltip>,
                      value: 'batch',
                      disabled: !isVoiceChannel,
                    },
                  ]}
                  onChange={setRunMode}
                />
                {isVoiceChannel ? (
                  <Button size="small" icon={<SettingOutlined />} disabled={running} onClick={() => setConfigOpen(true)}>
                    配置
                  </Button>
                ) : null}
              </div>
            </div>
            <div className={styles.pageHeaderRight}>
              <div className={styles.headerStatus}>
                <Tag color={connMeta.color}>{connMeta.label}</Tag>
                {isVoiceChannel && (
                  <Tag color={phase === 'listening' ? 'green' : phase === 'speaking' ? 'blue' : 'default'}>
                    {phaseTag[phase] || phase}
                  </Tag>
                )}
                {batchProgress && (
                  <Tag>
                    批量 {batchProgress.completed}/{batchProgress.total}
                  </Tag>
                )}
                {batchPaused && <Tag color="orange">已暂停</Tag>}
                {runMode === 'batch' && batchPace === 'manual' && waitingForNext && <Tag color="gold">待播放</Tag>}
              </div>
            </div>
          </div>
          {/* 第二行：参数区 + 操作按钮区 */}
          <div className={styles.pageHeaderRow}>
            <div className={styles.pageHeaderLeft}>
              <div className={styles.headerJudge}>
                <span className={styles.judgeToggleLabel}>评测</span>
                <Switch
                  checked={enableJudge}
                  disabled={running}
                  checkedChildren="开"
                  unCheckedChildren="关"
                  onChange={setEnableJudge}
                />
              </div>
              <div className={styles.headerDivider} aria-hidden />
              <Tooltip title="每个用例跑几轮 epoch（单测/批跑共用）。单测不入库；批跑每轮各写一条结果。">
                <div className={styles.headerJudge}>
                  <span className={styles.judgeToggleLabel}>轮次</span>
                  <InputNumber
                    min={1}
                    max={50}
                    size="small"
                    value={repeatN}
                    disabled={running}
                    onChange={(value) => setRepeatN(Math.max(1, Math.min(50, Number(value) || 1)))}
                    style={{ width: 64 }}
                  />
                </div>
              </Tooltip>
            </div>
            <div className={styles.pageHeaderRight}>
              <div className={styles.globalActions}>
                <Button icon={<AudioOutlined />} onClick={() => setAsrOpen(true)}>
                  ASR 测试
                </Button>
                {lastTaskRunId && (
                  <Button
                    type="primary"
                    icon={<FileSearchOutlined />}
                    onClick={() => window.open(`/task/task-run/${lastTaskRunId}`, '_blank')}
                  >
                    查看结果
                  </Button>
                )}
                {effectiveRunMode === 'batch' && (
                  <Button
                    icon={<HistoryOutlined />}
                    disabled={running}
                    loading={pausedRunsLoading}
                    onClick={handleShowPausedRuns}
                  >
                    恢复任务
                  </Button>
                )}
                <Button
                  type={lastTaskRunId ? 'default' : 'primary'}
                  icon={<PlayCircleOutlined />}
                  loading={running && !waitingForNext}
                  disabled={startDisabled}
                  onClick={handleStart}
                >
                  开始
                </Button>
                {effectiveRunMode === 'batch' && running && !batchPaused && (
                  <Button icon={<PauseCircleOutlined />} onClick={sendBatchPause}>
                    暂停
                  </Button>
                )}
                {effectiveRunMode === 'batch' && running && batchPaused && (
                  <Button type="primary" icon={<PlayCircleOutlined />} onClick={sendBatchResume}>
                    继续
                  </Button>
                )}
                <Button icon={<StopOutlined />} disabled={!running} onClick={handleStop}>
                  结束
                </Button>
              </div>
            </div>
          </div>
        </div>

        <Modal
          open={pausedRunsList.length > 0}
          title="选择要恢复的任务"
          onCancel={() => setPausedRunsList([])}
          footer={null}
        >
          <Spin spinning={pausedRunsLoading}>
            <List
              dataSource={pausedRunsList}
            renderItem={(item) => (
              <List.Item
                actions={[
                  <Button
                    key="resume"
                    type="primary"
                    size="small"
                    onClick={() => selectPausedRun(item.task_run_id)}
                  >
                    恢复
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={(item.metadata?.dataset_name as string) || '未命名任务'}
                  description={
                    <>
                      <div>
                        进度: {item.progress?.completed ?? 0} / {item.progress?.total ?? 0}
                        {item.progress?.total ? ` (${Math.round(((item.progress?.completed ?? 0) / item.progress.total) * 100)}%)` : ''}
                      </div>
                      {item.updated_time && <div>更新时间: {item.updated_time}</div>}
                    </>
                  }
                />
              </List.Item>
            )}
          />
          </Spin>
        </Modal>

        <AsrDemo open={asrOpen} onClose={() => setAsrOpen(false)} />

        <div
          ref={containerRef}
          className={`${styles.content} ${dragging ? styles.contentDragging : ''} ${collapsed ? styles.contentCollapsed : ''}`}
        >
          {collapsed && (
            <div className={styles.configCollapsedRail}>
              <Button
                type="text"
                size="small"
                icon={<MenuUnfoldOutlined />}
                aria-label="展开配置面板"
                title="展开配置"
                onClick={toggleCollapsed}
              />
            </div>
          )}

          <div
            className={`${styles.panel} ${styles.configPanel} ${collapsed ? styles.configPanelCollapsed : ''}`}
            style={configPanelStyle}
            aria-hidden={collapsed}
          >
            <div className={styles.configSurface}>
              <div className={styles.configSurfaceHeader}>
                <Button
                  type="text"
                  size="small"
                  icon={<MenuFoldOutlined />}
                  aria-label="收起配置面板"
                  title="收起配置"
                  onClick={toggleCollapsed}
                />
                <span className={styles.configSurfaceTitle}>
                  {effectiveRunMode === 'single' ? '用例配置' : '批量测试'}
                </span>
              </div>
              <div
                className={`${styles.configSurfaceBody} ${effectiveRunMode === 'batch' && showBatchCaseWorkspace ? styles.configSurfaceBodyBatch : ''}`}
              >
                {effectiveRunMode === 'single' ? (
                  caseLoadStatus === 'loading' ? (
                    <div className={styles.caseLoadPlaceholder}>
                      <Spin />
                      <span>加载代表性用例…</span>
                    </div>
                  ) : caseLoadStatus === 'error' || !caseForm ? (
                    <div className={styles.caseLoadError}>
                      用例加载失败，请检查 case-showcase-config 中的数据集名称与 case_id 是否与数据库一致。
                    </div>
                  ) : (
                    <div className={styles.singleForm}>
                      <VoiceCaseSourceBar
                        caseOptions={caseOptions}
                        selectedCaseKey={selectedCaseKey}
                        datasetId={singleDatasetId}
                        datasetOptions={batchDatasetOptions}
                        selectedCaseId={singleSelectedCaseId}
                        caseIdOptions={singleCaseIdOptions}
                        catalogLoadStatus={singleCatalogLoadStatus}
                        disabled={running}
                        onPresetChange={handleCaseTemplateChange}
                        onDatasetChange={handleSingleDatasetChange}
                        onCaseIdChange={handleSingleCaseIdChange}
                      />
                      <VoiceCaseForm
                        value={caseForm}
                        caseOptions={caseOptions}
                        selectedCaseKey={selectedCaseKey}
                        hidePreset
                        disabled={running}
                        onChange={handleCaseFormChange}
                        onCaseTemplateChange={handleCaseTemplateChange}
                      />
                    </div>
                  )
                ) : (
                  <div
                    className={`${styles.batchForm} ${showBatchCaseWorkspace && selectedCaseIndex != null ? styles.batchFormWithCases : ''}`}
                  >
                    <Collapse
                      className={styles.batchPanelCollapse}
                      activeKey={batchCollapseKeys}
                      onChange={(keys) => setBatchCollapseKeys(typeof keys === 'string' ? [keys] : keys)}
                      items={[
                        {
                          key: 'config',
                          label: (
                            <span className={styles.batchCollapseLabel}>
                              <span className={styles.batchCollapseTitle}>运行配置</span>
                              {!batchCollapseKeys.includes('config') && (
                                <span className={styles.batchCollapseSummary}>{batchConfigSummary}</span>
                              )}
                            </span>
                          ),
                          children: (
                            <div className={styles.batchFormConfig}>
                              <div className={styles.batchConfigRow}>
                                <div className={styles.batchConfigItem}>
                                  <span className={styles.batchConfigLabel}>数据集</span>
                                  <Select
                                    className={styles.batchDatasetSelect}
                                    showSearch
                                    allowClear
                                    value={datasetId}
                                    options={batchDatasetOptions}
                                    disabled={running}
                                    placeholder="请选择数据集"
                                    optionFilterProp="label"
                                    onChange={(value) => setDatasetId(value)}
                                  />
                                </div>
                                <Tooltip
                                  title={
                                    batchPace === 'auto'
                                      ? '开启后自动播放数据集中所有用例'
                                      : '关闭后每条需手动点「播放本条」，也可跳过当前'
                                  }
                                >
                                  <div className={styles.batchConfigItem}>
                                    <span className={styles.batchConfigLabel}>自动</span>
                                    <Switch
                                      checked={batchPace === 'auto'}
                                      disabled={running}
                                      checkedChildren="开"
                                      unCheckedChildren="关"
                                      onChange={(checked) => setBatchPace(checked ? 'auto' : 'manual')}
                                    />
                                  </div>
                                </Tooltip>
                              </div>
                            </div>
                          ),
                        },
                        ...(showBatchCaseWorkspace
                          ? [
                              {
                                key: 'nav',
                                label: (
                                  <span className={styles.batchCollapseLabel}>
                                    <span className={styles.batchCollapseTitle}>用例列表</span>
                                    {!batchCollapseKeys.includes('nav') && (
                                      <span className={styles.batchCollapseSummary}>{batchNavSummary}</span>
                                    )}
                                  </span>
                                ),
                                children: (
                                  <>
                                    <CaseListPanel
                                      items={batchNavItems}
                                      selectedIndex={selectedCaseIndex}
                                      activeCaseIndex={activeCaseIndex}
                                      loadStatus={catalogLoadStatus}
                                      disabled={running}
                                      onSelect={handleCaseNavClick}
                                    />
                                    {catalogLoadStatus === 'ready' &&
                                      batchNavItems.length > 0 &&
                                      selectedCaseIndex == null && (
                                        <div className={styles.caseListSelectHint}>点击用例查看详情</div>
                                      )}
                                  </>
                                ),
                              },
                            ]
                          : []),
                      ]}
                    />
                    {showBatchCaseWorkspace && selectedCaseIndex != null && selectedCaseDefinition && (
                      <div className={styles.caseDetailSection}>
                        <div className={styles.caseDetailSectionHeader}>
                          <span className={styles.label}>用例详情</span>
                          {running && selectedCaseIndex !== activeCaseIndex && activeCaseIndex != null && (
                            <span className={styles.caseDetailHint}>
                              执行 #{activeCaseIndex} · 查看 #{selectedCaseIndex ?? '—'}
                            </span>
                          )}
                        </div>
                        <div className={styles.caseDetailSectionBody}>
                          <VoiceCaseForm
                            value={selectedCaseDefinition}
                            caseOptions={[]}
                            selectedCaseKey=""
                            hidePreset
                            disabled
                            preview
                            onChange={noopCaseChange}
                            onCaseTemplateChange={() => {}}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>

          {!collapsed && (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="调整左右面板宽度"
              className={styles.splitDivider}
              onPointerDown={onDividerPointerDown}
              onPointerUp={onDividerPointerUp}
              onPointerCancel={onDividerPointerUp}
              onDoubleClick={onDividerDoubleClick}
            />
          )}

          <div className={`${styles.panel} ${styles.runPanel}`}>
            <div className={styles.mainView}>
              <CaseTimeline
                cases={runView.cases}
                activeCaseIndex={activeCaseIndex}
                showManualStep={showManualStepBar}
                onManualPlay={() => sendBatchStep('next_case')}
                onManualSkip={() => sendBatchStep('skip_case')}
                onTtsPlay={selectedAgentType === VOICE_TEST_TARGET_AGENT_V1 ? onTtsPlay : undefined}
                onCaseClick={handleCaseNavClick}
                scrollToIndex={scrollToCaseIndex}
                onStart={handleStart}
                startDisabled={startDisabled}
                waitHint={caseWaitHint}
              />
              <SystemTrace items={runView.systemTrace} />
            </div>
          </div>
        </div>
      </div>

      <ExDrawer title="语音测试配置" open={configOpen} setOpen={setConfigOpen} maskClosable>
        <AdapterConfigForm value={adapterConfig} disabled={running} onChange={setAdapterConfig} />
        <LocalRecorderStatusForm
          value={localRecorderConfig}
          disabled={running}
          active={configOpen}
          onChange={setLocalRecorderConfig}
        />
      </ExDrawer>
    </>
  )
}

export default App
