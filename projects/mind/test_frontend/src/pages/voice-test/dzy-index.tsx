import styles from './dzy-index.module.less'
import {
  Button,
  Collapse,
  message,
  notification,
  Select,
  Spin,
  Switch,
  Tooltip,
} from 'antd'
import {
  FileSearchOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons'
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import taskApi from '@/apis/task-data'
import {
  fetchAdapterConfig,
  loadStoredAdapterConfig,
  saveAdapterConfig,
  type VoiceAdapterConfig,
} from './adapter-config'
import ExDrawer from '@/components/Form/drawer'
import { useOptions } from '@/hooks/options'
import { BrowserVoiceAudio, type TtsPlayHandler } from './audio-helper'
import AdapterConfigForm from './adapter-config-form'
import LocalRecorderStatusForm from './local-recorder-status'
import {
  loadLocalRecorderConfig,
  localRecorderShouldRun,
  localRecorderStart,
  localRecorderStop,
  type LocalRecorderConfig,
  type LocalRecorderStopItem,
} from './local-recorder-client'
import DzyCaseTimeline from './dzy-case-timeline'
import type { CaseWaitHint } from './case-detail-view'
import CaseListPanel from './case-list-panel'
import DzyVoiceCaseSourceBar from './dzy-voice-case-source-bar'
import DzyVoiceCaseForm, {
  normalizeVoiceCaseForm,
  toVoiceCaseFormData,
} from './dzy-case-form'
import { useResizableSplit } from './use-resizable-split'
import { loadDatasetCases, loadVoiceCaseOptions, type VoiceCaseOption } from './case-catalog'
import { validateVoiceCase } from './case-state'
import {
  INITIAL_RUN_VIEW_STATE,
  voiceRunReducer,
  type CaseStatus,
  type WsPayload,
} from './run-state'
import SystemTrace from './system-trace'
import {
  fetchVoiceAgentOptions,
  isVoiceTarget,
  VOICE_ONLY_FALLBACK,
  VOICE_TEST_TARGET_AGENT_V1,
  VOICE_TEST_TARGET_VOICE,
  type VoiceTestAgentOption,
} from './agent-catalog'
import DzyTopBar, { type RunMode } from './dzy-top-bar'
import DzyEmptyState from './dzy-empty-state'
import { getVoiceTestWsUrl } from './ws-url'
import useApiModeStore from '@/stores/apiMode'

type CaseLoadStatus = 'loading' | 'ready' | 'error'
type BatchPace = 'auto' | 'manual'
type CatalogLoadStatus = 'idle' | 'loading' | 'ready' | 'error'

type BatchProgress = {
  completed: number
  total: number
  currentCase?: string
}

type BatchNavItem = {
  index: number
  caseId: string
  status?: CaseStatus
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
  const [configOpen, setConfigOpen] = useState(false)
  const [adapterConfig, setAdapterConfig] = useState<VoiceAdapterConfig>(loadStoredAdapterConfig)
  const [localRecorderConfig, setLocalRecorderConfig] = useState<LocalRecorderConfig>(
    loadLocalRecorderConfig,
  )
  const [phase, setPhase] = useState('idle')
  const [batchProgress, setBatchProgress] = useState<BatchProgress | null>(null)
  const [lastTaskRunId, setLastTaskRunId] = useState<string>()
  const [runView, dispatchRun] = useReducer(voiceRunReducer, INITIAL_RUN_VIEW_STATE)
  const [scrollToCaseIndex, setScrollToCaseIndex] = useState<number | null>(null)
  const [caseWaitHint, setCaseWaitHint] = useState<CaseWaitHint | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const audioRef = useRef<BrowserVoiceAudio | null>(null)
  const caseFormRef = useRef<ComplexReasoningCase | null>(null)
  const recordingCaseIdRef = useRef('')
  const pendingRecordCaseIdRef = useRef('')
  const recordStartAttemptedCaseRef = useRef('')
  const singleCaseIdForRunRef = useRef('')
  const pendingCaseAudioUrlRef = useRef('')
  const taskRunIdRef = useRef('')
  const localRecorderConfigRef = useRef(localRecorderConfig)
  const isVoiceChannelRef = useRef(isVoiceTarget(selectedAgentType))
  const prevRunModeRef = useRef(runMode)
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
    const cfg = localRecorderConfigRef.current
    const caseId = pendingRecordCaseIdRef.current
    if (
      !localRecorderShouldRun(cfg, isVoiceChannelRef.current) ||
      !caseId.trim() ||
      recordingCaseIdRef.current === caseId ||
      recordStartAttemptedCaseRef.current === caseId
    ) {
      return
    }
    pendingRecordCaseIdRef.current = ''
    recordStartAttemptedCaseRef.current = caseId
    const result = await localRecorderStart(cfg, caseId)
    if (!result) {
      dispatchRun({
        type: 'push_system',
        level: 'error',
        text: '本地记录没启动成功，请在「高级设置 → 本地记录」里点「检查」',
      })
      return
    }
    recordingCaseIdRef.current = caseId
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
      const target = caseId.trim() || recordingCaseIdRef.current
      if (!target || (recordingCaseIdRef.current && recordingCaseIdRef.current !== target)) {
        return
      }
      const stopped = await localRecorderStop(cfg, target, pendingCaseAudioUrlRef.current)
      recordingCaseIdRef.current = ''
      pendingCaseAudioUrlRef.current = ''
      const item = stopped[0]
      if (item) {
        notifyRecordingSaved(item)
      }
    },
    [notifyRecordingSaved],
  )

  const endAllCaseRecordings = useCallback(async () => {
    pendingRecordCaseIdRef.current = ''
    const cfg = localRecorderConfigRef.current
    if (!localRecorderShouldRun(cfg, isVoiceChannelRef.current)) {
      recordingCaseIdRef.current = ''
      return
    }
    const stopped = await localRecorderStop(cfg, '', pendingCaseAudioUrlRef.current)
    recordingCaseIdRef.current = ''
    pendingCaseAudioUrlRef.current = ''
    for (const item of stopped) {
      notifyRecordingSaved(item)
    }
  }, [notifyRecordingSaved])

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
    [messageApi],
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
    [batchNavItems, selectedCaseIndex],
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
    [singleCaseCatalog],
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
    [applyCaseTemplate, caseOptions],
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
          messageApi.warning(`有 ${missing.length} 个展示用例未加载（测试集或 case_id 未找到）`)
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
        messageApi.warning('代表性用例均未加载成功，请检查测试集与 case_id 配置')
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
          messageApi.error('加载测试集用例失败')
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
          messageApi.error('加载测试集用例失败')
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
      batchDatasetOptions.find((item) => item.value === datasetId)?.label?.toString() ?? '未选择测试集'
    const paceLabel = batchPace === 'manual' ? '手动' : '自动'
    return `${datasetName} · ${paceLabel}`
  }, [batchDatasetOptions, batchPace, datasetId])

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

  const releaseSession = useCallback(() => {
    void endAllCaseRecordings()
    const ws = wsRef.current
    if (ws) {
      ws.onmessage = null
      ws.onerror = null
      ws.onclose = null
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'stop' }))
      }
      ws.close()
      wsRef.current = null
    }
    audioRef.current?.stop()
    audioRef.current = null
  }, [endAllCaseRecordings])

  const cleanup = useCallback(() => {
    releaseSession()
    setRunning(false)
    setWaitingForNext(false)
    setSelectedCaseIndex(null)
    setPhase('idle')
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

  useEffect(() => {
    const onPageHide = () => releaseSession()
    window.addEventListener('pagehide', onPageHide)
    return () => {
      window.removeEventListener('pagehide', onPageHide)
      releaseSession()
    }
  }, [releaseSession])

  const handleStop = useCallback(() => {
    releaseSession()
    setRunning(false)
    setWaitingForNext(false)
    setSelectedCaseIndex(null)
    setPhase('idle')
    dispatchRun({ type: 'push_system', level: 'info', text: '已手动结束' })
    dispatchRun({ type: 'set_connection', connection: 'disconnected' })
  }, [releaseSession])

  const sendBatchStep = useCallback((type: 'next_case' | 'skip_case') => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type }))
      setWaitingForNext(false)
    }
  }, [])

  const handleWsPayload = useCallback((data: WsPayload) => {
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
        recordStartAttemptedCaseRef.current = ''
        pendingRecordCaseIdRef.current = data.case_id
        pendingCaseAudioUrlRef.current = ''
      }
    }
    if (data.type === 'case_audio_result' && data.download_url?.trim()) {
      pendingCaseAudioUrlRef.current = data.download_url.trim()
    }
    if (data.type === 'dialogue_history') {
      void endCaseRecording('')
    }
    if (data.type === 'batch_case_result') {
      setBatchProgress({
        completed: data.index || 0,
        total: data.total || 0,
        currentCase: data.case_id,
      })
      if (recordingCaseIdRef.current) {
        void endCaseRecording(data.case_id || '')
      }
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
  }, [endAllCaseRecordings, endCaseRecording, tryStartCaseRecording])

  const effectiveRunMode = isVoiceChannel ? runMode : 'single'
  const showBatchCaseWorkspace =
    effectiveRunMode === 'batch' &&
    !!datasetId &&
    (catalogLoadStatus === 'loading' || batchNavItems.length > 0)
  const showManualStepBar = effectiveRunMode === 'batch' && batchPace === 'manual' && running && waitingForNext

  const startDisabled = running || (effectiveRunMode === 'single' && caseLoadStatus !== 'ready')

  const handleStart = async () => {
    if (running) {
      return
    }

    let singleCaseToRun: ComplexReasoningCase | null = null
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
      messageApi.warning('请选择要批量测试的测试集')
      return
    }

    if (isVoiceChannel && (adapterConfig.vad_timeout_ms < 500 || adapterConfig.vad_timeout_ms > 50000)) {
      messageApi.warning('VAD 静音判停须在 500～50000 毫秒之间')
      return
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
    setLastTaskRunId(undefined)
    setScrollToCaseIndex(null)
    setSelectedCaseIndex(null)
    setCaseWaitHint(null)
    recordingCaseIdRef.current = ''
    pendingRecordCaseIdRef.current = ''
    pendingCaseAudioUrlRef.current = ''
    recordStartAttemptedCaseRef.current = ''
    singleCaseIdForRunRef.current = ''
    isVoiceChannelRef.current = isVoiceChannel
    setRunning(true)
    dispatchRun({ type: 'set_connection', connection: 'connecting' })
    dispatchRun({ type: 'push_system', level: 'info', text: '连接 WebSocket…' })

    if (effectiveRunMode === 'single' && singleCaseToRun) {
      const payloadCase = normalizeVoiceCaseForm(toVoiceCaseFormData(singleCaseToRun))
      singleCaseIdForRunRef.current = payloadCase.case_id || ''
      dispatchRun({
        type: 'init_single_case',
        caseId: payloadCase.case_id || '',
      })
    }

    if (isVoiceChannel) {
      const audio = new BrowserVoiceAudio()
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

    ws.onopen = () => {
      dispatchRun({ type: 'set_connection', connection: 'connected' })
      dispatchRun({
        type: 'push_system',
        level: 'info',
        text: effectiveRunMode === 'single' ? 'WebSocket 已连接，提交测试用例' : 'WebSocket 已连接，提交测试集',
      })
      const payload =
        effectiveRunMode === 'single' && singleCaseToRun
          ? {
              type: 'start',
              agent_type: selectedAgentType,
              case: normalizeVoiceCaseForm(toVoiceCaseFormData(singleCaseToRun)),
              enable_judge: enableJudge,
              adapter_config: adapterConfig,
            }
          : {
              type: 'start_batch',
              agent_type: selectedAgentType,
              dataset_id: datasetId,
              enable_judge: enableJudge,
              adapter_config: adapterConfig,
              batch_pace: batchPace,
            }
      ws.send(JSON.stringify(payload))
    }

    ws.onmessage = (event) => {
      if (wsRef.current !== ws) {
        return
      }
      if (typeof event.data === 'string') {
        const data = JSON.parse(event.data) as WsPayload

        if (data.type === 'user_query') {
          audioRef.current?.resetPlaybackSchedule()
        }
        if (data.type === 'await_playback_drain') {
          void audioRef.current?.waitForPlaybackDrain().then(() => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({ type: 'playback_drained' }))
            }
          })
        }
        if (data.type === 'phase') {
          setPhase(data.phase || 'idle')
          audioRef.current?.setListening(data.phase === 'listening')
        }
        if (data.type === 'judge_result' && effectiveRunMode === 'single') {
          if (data.is_passed) {
            messageApi.success('评分通过')
          } else {
            messageApi.warning('评分未通过')
          }
        }
        if (data.type === 'judge_skipped' && effectiveRunMode === 'single') {
          messageApi.info('对话完成，已跳过自动评分')
        }
        if (data.type === 'task_run_created' && data.task_run_id) {
          taskRunIdRef.current = data.task_run_id
          setLastTaskRunId(data.task_run_id)
        }
        if (data.type === 'ready' && effectiveRunMode === 'single') {
          const caseId = singleCaseIdForRunRef.current
          if (
            caseId &&
            isVoiceChannelRef.current &&
            !recordingCaseIdRef.current &&
            recordStartAttemptedCaseRef.current !== caseId
          ) {
            pendingRecordCaseIdRef.current = caseId
          }
        }
        if (data.type === 'batch_done') {
          setWaitingForNext(false)
          setBatchProgress({ completed: data.total || 0, total: data.total || 0 })
          const taskRunId = taskRunIdRef.current
          notifyApi.success({
            message: '批量测试完成',
            description: taskRunId
              ? '结果已写入数据库。可点击下方「查看结果」查看详情。'
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
        if (data.type === 'error') {
          messageApi.error(data.message || '服务错误')
        }
        if (data.type === 'done') {
          setRunning(false)
          setWaitingForNext(false)
          audioRef.current?.setListening(false)
          setPhase('idle')
        }

        handleWsPayload(data)

        if (data.type === 'done') {
          releaseSession()
          dispatchRun({ type: 'set_connection', connection: 'disconnected' })
        }
        return
      }

      audioRef.current?.playTtsChunk(event.data as ArrayBuffer)
    }

    ws.onerror = () => {
      messageApi.error('WebSocket 连接失败')
      dispatchRun({ type: 'push_system', level: 'error', text: 'WebSocket 连接失败' })
      dispatchRun({ type: 'set_connection', connection: 'error' })
      cleanup()
    }

    ws.onclose = () => {
      if (wsRef.current === ws) {
        cleanup()
      }
    }
  }

  const handleCaseNavClick = useCallback(
    (index: number) => {
      setSelectedCaseIndex(index)
      setScrollToCaseIndex(index)
    },
    [],
  )

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
    [applyCaseFromCatalog, singleCaseCatalog],
  )

  const handleSingleDatasetChange = useCallback((value?: string) => {
    setSingleDatasetId(value)
    setSingleSelectedCaseId('')
    if (value) {
      setSelectedCaseKey('')
    }
  }, [])

  const noopCaseChange = useCallback((_next: ComplexReasoningCase) => {}, [])

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

  const onSelectAgent = useCallback(
    (value: string) => {
      const nextAgentType = value ?? VOICE_TEST_TARGET_VOICE
      setSelectedAgentType(nextAgentType)
      if (!isVoiceTarget(nextAgentType)) {
        setRunMode('single')
        setConfigOpen(false)
      }
    },
    [],
  )

  return (
    <>
      {contextHolder}
      {notifyHolder}
      <div className={styles.dzyPage}>
        <DzyTopBar
          agentOptions={agentOptions}
          selectedAgentType={selectedAgentType}
          onSelectAgent={onSelectAgent}
          runMode={runMode}
          onSelectRunMode={setRunMode}
          batchDisabled={!isVoiceChannel}
          batchDisabledReason="当前测试对象不支持批量测试"
          connection={runView.connection}
          phase={phase}
          isVoiceChannel={isVoiceChannel}
          onOpenConfig={() => setConfigOpen(true)}
          lastTaskRunId={lastTaskRunId}
          onOpenResult={() => {
            if (lastTaskRunId) {
              window.open(`/task/task-run/${lastTaskRunId}`, '_blank')
            }
          }}
          running={running}
          startDisabled={startDisabled}
          onStart={handleStart}
          onStop={handleStop}
        />

        <div
          ref={containerRef}
          className={`${styles.dzyContent} ${dragging ? styles.dzyContentDragging : ''} ${collapsed ? styles.dzyContentCollapsed : ''}`}
        >
          {collapsed && (
            <div className={styles.dzyConfigCollapsedRail}>
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
            className={`${styles.dzyPanel} ${styles.dzyConfigPanel} ${collapsed ? styles.dzyConfigPanelCollapsed : ''}`}
            style={configPanelStyle}
            aria-hidden={collapsed}
          >
            <div className={styles.dzyConfigSurface}>
              <div className={styles.dzyConfigSurfaceHeader}>
                <Button
                  type="text"
                  size="small"
                  icon={<MenuFoldOutlined />}
                  aria-label="收起配置面板"
                  title="收起配置"
                  onClick={toggleCollapsed}
                />
                <span className={styles.dzyConfigSurfaceTitle}>
                  {effectiveRunMode === 'single' ? '单条测试' : '批量测试'}
                </span>
              </div>
              <div
                className={`${styles.dzyConfigSurfaceBody} ${effectiveRunMode === 'batch' && showBatchCaseWorkspace ? styles.dzyConfigSurfaceBodyBatch : ''}`}
              >
                {effectiveRunMode === 'single' ? (
                  caseLoadStatus === 'loading' ? (
                    <div className={styles.dzyCaseLoadPlaceholder}>
                      <Spin />
                      <span>加载示范用例…</span>
                    </div>
                  ) : caseLoadStatus === 'error' || !caseForm ? (
                    <div className={styles.dzyCaseLoadError}>
                      用例加载失败，请检查 case-showcase-config 中的测试集名称与 case_id 是否与数据库一致。
                    </div>
                  ) : (
                    <div className={styles.dzySingleForm}>
                      <DzyVoiceCaseSourceBar
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
                      <DzyVoiceCaseForm
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
                    className={`${styles.dzyBatchForm} ${showBatchCaseWorkspace && selectedCaseIndex != null ? styles.dzyBatchFormWithCases : ''}`}
                  >
                    <Collapse
                      className={styles.dzyBatchPanelCollapse}
                      activeKey={batchCollapseKeys}
                      onChange={(keys) => setBatchCollapseKeys(typeof keys === 'string' ? [keys] : keys)}
                      items={[
                        {
                          key: 'config',
                          label: (
                            <span className={styles.dzyBatchCollapseLabel}>
                              <span className={styles.dzyBatchCollapseTitle}>运行配置</span>
                              {!batchCollapseKeys.includes('config') && (
                                <span className={styles.dzyBatchCollapseSummary}>{batchConfigSummary}</span>
                              )}
                            </span>
                          ),
                          children: (
                            <div className={styles.dzyBatchFormConfig}>
                              <div className={styles.dzyBatchConfigRow}>
                                <div className={styles.dzyBatchConfigItem}>
                                  <span className={styles.dzyBatchConfigLabel}>测试集</span>
                                  <Select
                                    className={styles.dzyBatchDatasetSelect}
                                    showSearch
                                    allowClear
                                    value={datasetId}
                                    options={batchDatasetOptions}
                                    disabled={running}
                                    placeholder="请选择测试集"
                                    optionFilterProp="label"
                                    onChange={(value) => setDatasetId(value)}
                                  />
                                </div>
                                <Tooltip
                                  title={
                                    batchPace === 'auto'
                                      ? '开启后自动播放测试集中所有用例'
                                      : '关闭后每条需手动点「播放本条」，也可跳过当前'
                                  }
                                >
                                  <div className={styles.dzyBatchConfigItem}>
                                    <span className={styles.dzyBatchConfigLabel}>自动连续</span>
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
                                  <span className={styles.dzyBatchCollapseLabel}>
                                    <span className={styles.dzyBatchCollapseTitle}>用例列表</span>
                                    {!batchCollapseKeys.includes('nav') && (
                                      <span className={styles.dzyBatchCollapseSummary}>{batchNavSummary}</span>
                                    )}
                                  </span>
                                ),
                                children: (
                                  <>
                                    {batchProgress && (
                                      <div className={styles.dzyBatchProgress}>
                                        进度 {batchProgress.completed}/{batchProgress.total}
                                      </div>
                                    )}
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
                                        <div className={styles.dzyCaseListSelectHint}>点击用例查看详情</div>
                                      )}
                                  </>
                                ),
                              },
                            ]
                          : []),
                      ]}
                    />
                    {showBatchCaseWorkspace && selectedCaseIndex != null && selectedCaseDefinition && (
                      <div className={styles.dzyCaseDetailSection}>
                        <div className={styles.dzyCaseDetailSectionHeader}>
                          <span className={styles.dzyLabel}>用例详情</span>
                          {running && selectedCaseIndex !== activeCaseIndex && activeCaseIndex != null && (
                            <span className={styles.dzyCaseDetailHint}>
                              执行 #{activeCaseIndex} · 查看 #{selectedCaseIndex ?? '—'}
                            </span>
                          )}
                        </div>
                        <div className={styles.dzyCaseDetailSectionBody}>
                          <DzyVoiceCaseForm
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
              className={styles.dzySplitDivider}
              onPointerDown={onDividerPointerDown}
              onPointerUp={onDividerPointerUp}
              onPointerCancel={onDividerPointerUp}
              onDoubleClick={onDividerDoubleClick}
            />
          )}

          <div className={`${styles.dzyPanel} ${styles.dzyRunPanel}`}>
            <div className={styles.dzyMainView}>
              {runView.cases.length === 0 ? (
                <DzyEmptyState canStart={!startDisabled} onStart={handleStart} />
              ) : (
                <>
                  <DzyCaseTimeline
                    cases={runView.cases}
                    activeCaseIndex={activeCaseIndex}
                    showManualStep={showManualStepBar}
                    onManualPlay={() => sendBatchStep('next_case')}
                    onManualSkip={() => sendBatchStep('skip_case')}
                    onTtsPlay={
                      selectedAgentType === VOICE_TEST_TARGET_AGENT_V1 ? onTtsPlay : undefined
                    }
                    onCaseClick={handleCaseNavClick}
                    scrollToIndex={scrollToCaseIndex}
                    waitHint={caseWaitHint}
                  />
                  <SystemTrace items={runView.systemTrace} />
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      <ExDrawer
        title="高级设置"
        open={configOpen}
        setOpen={setConfigOpen}
        maskClosable
      >
        <div style={{ marginBottom: 16, padding: 12, background: 'var(--v-muted-bg, #fafafa)', borderRadius: 8, fontSize: 13, color: 'var(--v-text-secondary, rgba(0,0,0,0.65))' }}>
          以下设置通常无需调整，默认值已适用于大多数场景。
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, padding: '8px 0', borderBottom: '1px solid var(--v-border, #f0f0f0)' }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>自动评分</span>
          <Switch
            checked={enableJudge}
            disabled={running}
            checkedChildren="开"
            unCheckedChildren="关"
            onChange={setEnableJudge}
          />
          <span style={{ fontSize: 12, color: 'var(--v-text-muted, rgba(0,0,0,0.45))' }}>
            开启后对话结束自动评分
          </span>
        </div>
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
