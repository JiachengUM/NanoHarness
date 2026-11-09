import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react'
import {
  createLiveAgentClient,
  type LiveAgentClient,
  type RuntimeProfile,
} from './adapters/v2AgentClient'
import { consoleReducer, initialConsoleState, type Toast } from './app/consoleReducer'
import type { AgentConsoleEvent } from './domain/events'
import type { AgentMode } from './domain/planEvents'
import {
  canCancelTask,
  getActiveTaskList,
  type TaskProjection,
} from './domain/projection'
import { errorMessage } from './utils/unknown'
import { traceBrowserLatency } from './utils/latencyTrace'
import { useSplitLayout } from './app/useSplitLayout'
import { ChatPanel } from './components/ChatPanel'
import { DuplexParticleStage } from './components/DuplexParticleStage'
import { InspectorDrawer } from './components/InspectorDrawer'
import { PlannerPanel } from './components/PlannerPanel'
import { ReactRuntimePanel } from './components/ReactRuntimePanel'
import { useVoiceSession } from './voice/useVoiceSession'
import { isVoiceInputActive } from './voice/voiceTypes'
import './styles.css'

type ServiceStatus = {
  label: '检测中' | '服务可用' | '服务不可用'
  tone: 'checking' | 'available' | 'unavailable'
}

export type DuplexSurface = 'particle' | 'input'

export function getNextDuplexSurface(surface: DuplexSurface): DuplexSurface {
  return surface === 'particle' ? 'input' : 'particle'
}

type ModeResetFocusTarget = {
  isConnected: boolean
  tabIndex: number
  matches: (selector: string) => boolean
  closest: (selector: string) => unknown
  focus: (options?: FocusOptions) => void
}

type ModeResetFocusEnvironment = {
  isVisible: (target: ModeResetFocusTarget) => boolean
  getActiveElement: () => ModeResetFocusTarget | null
  isDocumentFallback: (target: ModeResetFocusTarget) => boolean
}

type ModeResetFocusTargets = {
  preferred: HTMLElement | null
  fallback: HTMLElement | null
}

const MODE_RESET_FOCUS_SELECTOR = [
  'a[href]',
  'button',
  'input',
  'select',
  'textarea',
  '[tabindex]',
  '[contenteditable="true"]',
].join(', ')

export function getServiceStatus(connected: boolean | null): ServiceStatus {
  if (connected === null) return { label: '检测中', tone: 'checking' }
  return connected
    ? { label: '服务可用', tone: 'available' }
    : { label: '服务不可用', tone: 'unavailable' }
}

export function getWorkspaceStatusLabel(
  serviceStatus: ServiceStatus,
  modeResetting: boolean,
): string {
  return modeResetting
    ? `${serviceStatus.label} · 正在重置会话`
    : serviceStatus.label
}

export function restoreModeResetFocus(
  modeResetting: boolean,
  preferred: ModeResetFocusTarget | null,
  fallback: ModeResetFocusTarget | null,
  environment: ModeResetFocusEnvironment,
): boolean {
  if (modeResetting) return false

  const activeElement = environment.getActiveElement()
  if (
    activeElement
    && !environment.isDocumentFallback(activeElement)
    && isModeResetFocusTarget(activeElement, environment.isVisible)
  ) {
    return true
  }

  const candidates = preferred === fallback
    ? [preferred]
    : [preferred, fallback]

  for (const candidate of candidates) {
    if (!isModeResetFocusTarget(candidate, environment.isVisible)) continue

    try {
      candidate.focus({ preventScroll: true })
    } catch {
      continue
    }

    if (environment.getActiveElement() === candidate) break
  }

  return true
}

function isModeResetFocusTarget(
  target: ModeResetFocusTarget | null,
  isVisible: (target: ModeResetFocusTarget) => boolean,
): target is ModeResetFocusTarget {
  return Boolean(
    target?.isConnected
    && target.tabIndex >= 0
    && !target.matches(':disabled, [aria-disabled="true"]')
    && !target.closest(
      ':disabled, [aria-disabled="true"], [hidden], [aria-hidden="true"], [inert]',
    )
    && target.matches(MODE_RESET_FOCUS_SELECTOR)
    && isVisible(target)
  )
}

function isModeResetFocusTargetVisible(target: ModeResetFocusTarget): boolean {
  if (!(target instanceof HTMLElement)) return false

  let element: HTMLElement | null = target
  while (element) {
    const style = window.getComputedStyle(element)
    const opacity = Number.parseFloat(style.opacity)
    if (
      style.display === 'none'
      || style.visibility === 'hidden'
      || style.visibility === 'collapse'
      || style.contentVisibility === 'hidden'
      || (Number.isFinite(opacity) && opacity === 0)
    ) {
      return false
    }
    element = element.parentElement
  }

  return target.getClientRects().length > 0
}

export async function runAckFirstSessionReset(
  client: Pick<LiveAgentClient, 'resetSession'>,
  nextMode: AgentMode,
  onAccepted: (mode: AgentMode) => void,
): Promise<void> {
  const result = await client.resetSession(nextMode)
  onAccepted(result.agentMode)
}

const AGENT_MODE_OPTIONS: ReadonlyArray<{
  mode: AgentMode
  label: string
}> = [
  { mode: 'react', label: 'ReAct' },
]

const RUNTIME_PROFILE_OPTIONS: ReadonlyArray<{
  profile: RuntimeProfile
  label: string
}> = [
  { profile: 'react_duplex_shell', label: 'V2 Agent 语音问答' },
  { profile: 'duplex_native', label: '原生 Duplex' },
]

type TaskCancelTarget = Pick<
  TaskProjection,
  'taskId' | 'toolName' | 'title' | 'arguments'
>

const TASK_CANCEL_HINT_KEYS = [
  'query',
  'command',
  'text',
  'keyword',
  'keywords',
  'address',
  'city',
] as const

function normalizeTaskCancelHint(value: string): string {
  return value.replace(/\s+/g, ' ').trim().toLocaleLowerCase()
}

function taskMatchesCancelHint(
  task: TaskCancelTarget,
  rawHint: string,
): boolean {
  const hint = normalizeTaskCancelHint(rawHint)
  if (hint.length < 2) return false

  const toolName = normalizeTaskCancelHint(task.toolName)
  if (toolName.length >= 2 && toolName.includes(hint)) return true

  return Object.values(task.arguments).some((value) => {
    if (typeof value !== 'string') return false
    const argument = normalizeTaskCancelHint(value)
    return (
      argument.length >= 2
      && (hint.includes(argument) || argument.includes(hint))
    )
  })
}

function getPreferredTaskArgumentHints(task: TaskCancelTarget): string[] {
  const hints = TASK_CANCEL_HINT_KEYS.flatMap((key) => {
    const value = task.arguments[key]
    if (typeof value !== 'string') return []
    const normalized = value.replace(/\s+/g, ' ').trim()
    return normalized.length >= 2 ? [normalized.slice(0, 80)] : []
  })
  return [...new Set(hints)]
}

export function getTaskCancelTargetHint(
  task: TaskCancelTarget,
  activeTasks: TaskCancelTarget[],
): string {
  const taskPool = activeTasks.some((candidate) => candidate.taskId === task.taskId)
    ? activeTasks
    : [...activeTasks, task]
  const argumentHints = getPreferredTaskArgumentHints(task)
  const candidates = [...argumentHints, task.toolName.trim()]

  const uniqueHint = candidates.find((hint) => (
    hint.length >= 2
    && taskPool.filter((candidate) => taskMatchesCancelHint(candidate, hint)).length === 1
  ))
  if (uniqueHint !== undefined) return uniqueHint

  return argumentHints[0] || task.toolName.trim() || task.title.trim() || '当前任务'
}

export function buildTaskCancelQuery(
  task: TaskCancelTarget,
  activeTasks: TaskCancelTarget[],
): string {
  return `取消任务：${getTaskCancelTargetHint(task, activeTasks)}`
}

export function submitTaskCancellationThroughAgent(
  task: TaskCancelTarget,
  activeTasks: TaskCancelTarget[],
  onRequested: (
    event: Extract<AgentConsoleEvent, { type: 'task.cancel.requested' }>,
  ) => void,
  submitAgentQuery: (input: string) => void,
  now: () => string = () => new Date().toISOString(),
): string {
  const input = buildTaskCancelQuery(task, activeTasks)
  const timestamp = now()
  onRequested({
    id: `ui-cancel-request-${task.taskId}-${timestamp}`,
    type: 'task.cancel.requested',
    timestamp,
    taskId: task.taskId,
    reason: '用户点击取消，已交给 Agent 处理',
  })
  submitAgentQuery(input)
  return input
}

export function getTaskCancelUnavailableFeedback(
  task?: TaskProjection,
): Pick<Toast, 'message' | 'level'> {
  if (task?.status === 'success') {
    return {
      message: '任务已经完成，无需取消',
      level: 'info',
    }
  }
  return {
    message: '任务已经结束或不存在',
    level: 'info',
  }
}

export default function App() {
  const [state, dispatch] = useReducer(consoleReducer, undefined, initialConsoleState)
  const [liveInput, setLiveInput] = useState('')
  const {
    consoleShellRef,
    handleResizeKeyDown,
    handleResizePointerDown,
    isResizingLayout,
    resetSplitLayout,
    resizerAria,
    splitLayoutStyle,
  } = useSplitLayout()
  const liveTurnRef = useRef(0)

  const liveClient = useMemo(() => createLiveAgentClient(), [])
  const [connected, setConnected] = useState<boolean | null>(null)
  const serviceStatus = getServiceStatus(connected)
  const [plannerCollapsed, setPlannerCollapsed] = useState(false)
  const [agentMode, setAgentMode] = useState<AgentMode>('react')
  const [runtimeProfile, setRuntimeProfile] =
    useState<RuntimeProfile>('duplex_native')
  const [duplexSurface, setDuplexSurface] =
    useState<DuplexSurface>('particle')
  const isPlannerMode = agentMode === 'plact'
  const rightPanelLabel = isPlannerMode ? '任务拆解' : '运行关系'
  const [modeResetting, setModeResetting] = useState(false)
  const modeResetFocusTargetsRef = useRef<ModeResetFocusTargets | null>(null)

  useEffect(() => {
    const targets = modeResetFocusTargetsRef.current
    if (!targets) return

    const restoredAfterUnlock = restoreModeResetFocus(
      modeResetting,
      targets.preferred,
      targets.fallback,
      {
        isVisible: isModeResetFocusTargetVisible,
        getActiveElement: () => (
          document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null
        ),
        isDocumentFallback: (target) => (
          target === document.body || target === document.documentElement
        ),
      },
    )
    if (restoredAfterUnlock) {
      modeResetFocusTargetsRef.current = null
    }
  }, [modeResetting])

  // Poll backend health every 5s
  useEffect(() => {
    let active = true
    const check = () => {
      void liveClient.checkHealth().then((ok) => { if (active) setConnected(ok) })
    }
    check()
    const id = setInterval(check, 5000)
    return () => { active = false; clearInterval(id) }
  }, [liveClient])

  const showToast = useCallback((message: string, level: Toast['level'] = 'error') => {
    dispatch({
      type: 'toast',
      toast: {
        id: `toast-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        message,
        level,
      },
    })
  }, [])

  useEffect(
    () => () => {
      liveClient.dispose()
    },
    [liveClient],
  )

  const {
    inputLocked: voiceInputLocked,
    latestVoiceTranscript,
    liveInputValue,
    readVoiceAcoustics,
    resetVoiceSession,
    speakingAssistantMessageId,
    startTextTurnVoiceOutput,
    toggleVoice,
    voiceMicrophoneOpen,
    voicePhase,
  } = useVoiceSession({
    acceptedPlaybackMessageId: state.acceptedPlaybackMessageId,
    acceptedPlaybackRevision: state.acceptedPlaybackRevision,
    dispatch,
    liveClient,
    liveInput,
    setLiveInput,
    showToast,
  })

  const submitTextTurn = useCallback((input: string) => {
    liveTurnRef.current += 1
    const turnId = liveTurnRef.current
    const assistantMessageId = `agent-live-${turnId}`
    const timestamp = new Date().toISOString()

    traceBrowserLatency('ui.submit', { message_id: assistantMessageId })

    dispatch({
      type: 'startConversation',
      input,
      userMessageId: `user-live-${turnId}`,
      assistantMessageId,
      timestamp,
    })

    const startAgentRun = () => {
      liveClient.start({
        input,
        messageId: assistantMessageId,
        onEvent: (event) => dispatch({ type: 'event', event }),
        onError: (error) => {
          dispatch({
            type: 'event',
            event: {
              id: `live-error-delta-${turnId}`,
              type: 'agent.text.delta',
              timestamp: new Date().toISOString(),
              messageId: assistantMessageId,
              delta: `Live agent connection failed: ${errorMessage(error)}`,
            },
          })
          dispatch({
            type: 'event',
            event: {
              id: `live-error-done-${turnId}`,
              type: 'agent.text.done',
              timestamp: new Date().toISOString(),
              messageId: assistantMessageId,
            },
          })
        },
      })
    }

    startTextTurnVoiceOutput({ startAgentRun })
  }, [liveClient, startTextTurnVoiceOutput])

  const startLive = () => {
    const input = liveInput.trim()
    if (!input) {
      return
    }

    setLiveInput('')
    submitTextTurn(input)
  }

  const cancelRuntimeTask = useCallback((taskId: string) => {
    const task = state.tasks.byId[taskId]
    if (!canCancelTask(task)) {
      const feedback = getTaskCancelUnavailableFeedback(task)
      showToast(feedback.message, feedback.level)
      return
    }

    if (runtimeProfile === 'duplex_native') {
      void liveClient.cancelTask(taskId).then((result) => {
        if (result.requestedEvent) {
          dispatch({ type: 'event', event: result.requestedEvent })
        } else {
          showToast(result.reason ?? '任务无法取消', 'info')
        }
      }).catch((error: unknown) => {
        showToast(`取消任务失败: ${errorMessage(error)}`)
      })
      return
    }

    submitTaskCancellationThroughAgent(
      task,
      getActiveTaskList(state.tasks),
      (event) => dispatch({ type: 'event', event }),
      submitTextTurn,
    )
  }, [liveClient, runtimeProfile, showToast, state.tasks, submitTextTurn])

  const resetSessionProjection = useCallback((
    nextMode: AgentMode,
    focusFallback: HTMLElement,
  ) => {
    if (modeResetting) return
    const activeElement = document.activeElement
    modeResetFocusTargetsRef.current = {
      preferred: activeElement instanceof HTMLElement ? activeElement : null,
      fallback: focusFallback,
    }
    setModeResetting(true)
    void runAckFirstSessionReset(liveClient, nextMode, (acceptedMode) => {
      resetVoiceSession()
      dispatch({ type: 'reset' })
      setLiveInput('')
      setAgentMode(acceptedMode)
    })
      .catch((error: unknown) => {
        showToast(`重置会话失败: ${errorMessage(error)}`)
      })
      .finally(() => {
        setModeResetting(false)
      })
  }, [liveClient, modeResetting, resetVoiceSession, showToast])

  const resetRuntimeProjection = useCallback((
    nextProfile: RuntimeProfile,
    focusFallback: HTMLElement,
  ) => {
    if (modeResetting) return
    const activeElement = document.activeElement
    modeResetFocusTargetsRef.current = {
      preferred: activeElement instanceof HTMLElement ? activeElement : null,
      fallback: focusFallback,
    }
    setModeResetting(true)
    void liveClient.resetRuntime(nextProfile).then((accepted) => {
      resetVoiceSession()
      dispatch({ type: 'reset' })
      setLiveInput('')
      setAgentMode(accepted.agentMode)
      setRuntimeProfile(accepted.runtimeProfile)
    }).catch((error: unknown) => {
      showToast(`重置会话失败: ${errorMessage(error)}`)
    }).finally(() => {
      setModeResetting(false)
    })
  }, [liveClient, modeResetting, resetVoiceSession, showToast])

  const newConversation = (focusFallback: HTMLElement) => {
    resetRuntimeProjection(runtimeProfile, focusFallback)
  }

  // Auto-dismiss toasts after 3s
  useEffect(() => {
    if (state.toasts.length === 0) return
    const timer = setTimeout(() => {
      dispatch({ type: 'dismissToast', toastId: state.toasts[0].id })
    }, 3000)
    return () => clearTimeout(timer)
  }, [state.toasts])

  return (
    <main
      ref={consoleShellRef}
      className="console-shell"
    >
      {state.toasts.length > 0 && (
        <div className="toast-container">
          {state.toasts.map((t: Toast) => (
            <div key={t.id} className={`toast toast-${t.level}`}>
              <span>{t.message}</span>
              <button type="button" onClick={() => dispatch({ type: 'dismissToast', toastId: t.id })}>×</button>
            </div>
          ))}
        </div>
      )}
      <header className="workspace-toolbar">
        <div className="workspace-identity">
          <p className="eyebrow">AICORE · V2</p>
          <h1>Agent Console</h1>
          <p className="workspace-subtitle">对话、计划与运行证据</p>
        </div>
        <div className="workspace-toolbar-actions">
          <div
            className={`service-status service-status-${serviceStatus.tone}`}
            role="status"
            aria-live="polite"
          >
            <span className="service-status-dot" aria-hidden="true" />
            <span>{getWorkspaceStatusLabel(serviceStatus, modeResetting)}</span>
          </div>
          <div className="agent-mode-switch" role="group" aria-label="Agent 模式">
            {AGENT_MODE_OPTIONS.map(({ mode, label }) => (
              <button
                key={mode}
                type="button"
                aria-pressed={agentMode === mode}
                disabled={modeResetting}
                onClick={(event) => {
                  if (mode !== agentMode) resetSessionProjection(mode, event.currentTarget)
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="agent-mode-switch" role="group" aria-label="对话方式">
            {RUNTIME_PROFILE_OPTIONS.map(({ profile, label }) => (
              <button
                key={profile}
                type="button"
                aria-pressed={runtimeProfile === profile}
                disabled={modeResetting}
                onClick={(event) => {
                  if (profile !== runtimeProfile) {
                    resetRuntimeProjection(profile, event.currentTarget)
                  }
                }}
              >
                {label}
              </button>
            ))}
          </div>
          {runtimeProfile === 'duplex_native' && (
            <button
              aria-label={`切换到${duplexSurface === 'particle' ? '输入' : '粒子'}视图`}
              className="duplex-surface-toggle"
              data-surface={duplexSurface}
              disabled={modeResetting}
              title={`当前：${duplexSurface === 'particle' ? '粒子' : '输入'}`}
              type="button"
              onClick={() => setDuplexSurface((current) => getNextDuplexSurface(current))}
            >
              <span data-active={duplexSurface === 'particle'}>粒子</span>
              <i aria-hidden="true">↔</i>
              <span data-active={duplexSurface === 'input'}>输入</span>
            </button>
          )}
          <button
            className="secondary-button"
            type="button"
            disabled={modeResetting}
            onClick={(event) => newConversation(event.currentTarget)}
          >
            {modeResetting ? '正在切换…' : '新建对话'}
          </button>
        </div>
      </header>
      <div
        className={`console-stage${isResizingLayout ? ' is-resizing' : ''}${plannerCollapsed ? ' planner-collapsed' : ''}`}
        aria-busy={modeResetting || undefined}
        inert={modeResetting}
        style={splitLayoutStyle}
      >
        <section className={`workspace${runtimeProfile === 'duplex_native' ? ' duplex-visual-workspace' : ''}`}>
          {runtimeProfile === 'duplex_native' && duplexSurface === 'particle' ? (
            <DuplexParticleStage
              connected={connected}
              disabled={connected === false || modeResetting}
              microphoneOpen={voiceMicrophoneOpen}
              onToggleVoice={toggleVoice}
              readVoiceAcoustics={readVoiceAcoustics}
              transcript={latestVoiceTranscript}
              voicePhase={voicePhase}
            />
          ) : (
            <ChatPanel
              messages={state.messages}
              liveInput={liveInputValue}
              isPlaying={state.isPlaying}
              connected={connected}
              voicePhase={voicePhase}
              voiceInputLocked={voiceInputLocked}
              voiceMicrophoneOpen={voiceMicrophoneOpen}
              speakingAssistantMessageId={speakingAssistantMessageId}
              modeResetting={modeResetting}
              textInputEnabled={runtimeProfile !== 'duplex_native'}
              onLiveInputChange={setLiveInput}
              onStartLive={startLive}
              onToggleVoice={toggleVoice}
            />
          )}
        </section>
        {!plannerCollapsed && (
          <button
            aria-label="调整左右面板宽度"
            aria-orientation="vertical"
            aria-valuemax={resizerAria.max}
            aria-valuemin={resizerAria.min}
            aria-valuenow={resizerAria.now}
            className="console-resizer"
            role="separator"
            title="拖拽调整左右宽度，双击恢复默认"
            type="button"
            onDoubleClick={resetSplitLayout}
            onKeyDown={handleResizeKeyDown}
            onPointerDown={handleResizePointerDown}
          />
        )}
        {plannerCollapsed ? (
          <button
            className="planner-rail"
            type="button"
            aria-label={`展开${rightPanelLabel}面板`}
            title={`展开${rightPanelLabel}`}
            onClick={() => setPlannerCollapsed(false)}
          >
            <span className="planner-rail-icon" aria-hidden="true">‹</span>
            <span className="planner-rail-label">{rightPanelLabel}</span>
          </button>
        ) : (
          <aside className="right-column">
            {isPlannerMode ? (
              <PlannerPanel
                state={state}
                onCollapse={() => setPlannerCollapsed(true)}
                onSelectPage={(pageId) => dispatch({ type: 'selectPlanPage', pageId })}
              />
            ) : (
              <ReactRuntimePanel
                runtimeTrace={state.runtimeTrace}
                tasks={state.tasks}
                connected={connected}
                voicePhase={voicePhase}
                voiceDraft={isVoiceInputActive(voicePhase) ? liveInputValue : ''}
                onCollapse={() => setPlannerCollapsed(true)}
                onCancelTask={cancelRuntimeTask}
                onSelectTask={(taskId) => dispatch({ type: 'selectTask', taskId })}
              />
            )}
          </aside>
        )}
      </div>
      <InspectorDrawer
        state={state}
        interactionDisabled={modeResetting}
        onClose={() => {
          dispatch({ type: 'selectTask', taskId: undefined })
        }}
      />
    </main>
  )
}
