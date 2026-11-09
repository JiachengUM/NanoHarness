import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type RefObject,
  type SetStateAction,
  type UIEvent,
} from 'react'
import type {
  RuntimeTraceEntry,
  RuntimeTraceState,
  RuntimeTraceStatus,
} from '../app/runtimeTraceReducer'
import {
  canCancelTask,
  formatTaskDuration,
  getActiveTaskList,
  getTaskDurationMs,
  type TaskProjection,
  type TaskProjectionState,
} from '../domain/projection'
import { isVoiceInputActive, type VoicePhase } from '../voice/voiceTypes'
import { getFocusWrapIndex } from '../utils/focus'
import {
  RUNTIME_LANE_HEIGHT,
  RUNTIME_LANE_TOPS,
  RUNTIME_TASK_AXIS_HEIGHT,
  buildRuntimeTimeline,
  projectRuntimeConnector,
  type PositionedRuntimeEntry,
  type RuntimeTimelineLayout,
} from './runtimeTimeline'

type ReactRuntimePanelProps = {
  runtimeTrace: RuntimeTraceState
  tasks: TaskProjectionState
  connected: boolean | null
  voicePhase: VoicePhase
  voiceDraft: string
  onCancelTask: (taskId: string) => void
  onSelectTask: (taskId: string) => void
  onCollapse?: () => void
  clockNowMs?: number
}

type RuntimeTaskBlockProps = {
  task: TaskProjection
  left: number
  top: number
  width: number
  nowMs: number
  onCancelTask: (taskId: string) => void
  onHoverTask: (taskId: string | undefined) => void
  onFocusTask: (taskId: string | undefined) => void
  onSelectTask: (taskId: string) => void
}

type RuntimeScrollMetrics = {
  clientWidth: number
  scrollWidth: number
  currentScrollLeft: number
  previousContentEndX: number
  contentEndX: number
  isInitial: boolean
}

type RuntimeScrollTarget = {
  shouldScroll: boolean
  left: number
}

export type RuntimeResizeScrollMetrics = RuntimeLiveEdgeMetrics & {
  scrollWidth: number
  wasAtLiveEdge: boolean
}

export type RuntimeLiveEdgeMetrics = {
  clientWidth: number
  currentScrollLeft: number
  contentEndX: number
}

export type RuntimeTaskLiveEdgeMetrics = {
  clientHeight: number
  scrollHeight: number
  currentScrollTop: number
}

export type RuntimeTaskScrollMetrics = {
  clientHeight: number
  scrollHeight: number
  currentScrollTop: number
  previousViewportHeight: number
  previousContentHeight: number
  isInitial: boolean
}

export type RuntimeTaskScrollTarget = {
  shouldScroll: boolean
  top: number
}

type RuntimeTaskViewport = {
  scrollTop: number
  viewportHeight: number
}

type RuntimeTaskScrollSnapshot = {
  contentHeight: number
  viewportHeight: number
}

type RuntimeHorizontalScrollSnapshot = {
  contentEndX: number
  viewportWidth: number
  atLiveEdge: boolean
}

type RuntimeLiveEdges = {
  horizontal: boolean
  vertical: boolean
}

const RUNTIME_TIMER_INTERVAL_MS = 250
const RUNTIME_SCROLL_PADDING = 24
const RUNTIME_SCROLL_FOLLOW_THRESHOLD = 32
const INITIAL_RUNTIME_LIVE_EDGES: RuntimeLiveEdges = {
  horizontal: true,
  vertical: true,
}

const ENTRY_STATUS_LABELS: Record<RuntimeTraceStatus, string> = {
  submitted: '已提交',
  active: '进行中',
  complete: '已完成',
  interrupted: '已中断',
  failed: '失败',
  cancelling: '取消中',
  cancelled: '已取消',
}

export function getRuntimeEntryStatusLabel(entry: RuntimeTraceEntry): string {
  if (entry.kind === 'agent.delegated') return '已发起'
  if (entry.lane === 'agent' && entry.status === 'active') return '思考中'
  return ENTRY_STATUS_LABELS[entry.status]
}

function formatRuntimeGap(durationMs: number): string {
  const seconds = Math.round(durationMs / 1_000)
  return seconds < 60 ? `+${seconds}s` : `+${Math.round(seconds / 60)}m`
}

const TASK_STATUS_LABELS: Record<TaskProjection['status'], string> = {
  pending: '等待中',
  running: '运行中',
  success: '完成',
  failed: '失败',
  cancelling: '取消中',
  cancelled: '已取消',
}

const CONNECTOR_LABELS = {
  submit: '提交',
  delegate: '发起',
  result: '结果',
} as const

const CONNECTOR_KINDS = ['submit', 'delegate', 'result'] as const
const INITIAL_TASK_VIEWPORT: RuntimeTaskViewport = {
  scrollTop: 0,
  viewportHeight: Number.POSITIVE_INFINITY,
}

export function getRuntimeContentEndX(layout: RuntimeTimelineLayout): number {
  return Math.max(
    layout.playheadX,
    ...layout.entries.map(({ x, width }) => x + width),
    ...layout.tasks.map(({ x, width }) => x + width),
    ...layout.connectors.flatMap(({ from, to }) => [from.x, to.x]),
  )
}

export function getRuntimeScrollTarget({
  clientWidth,
  scrollWidth,
  currentScrollLeft,
  previousContentEndX,
  contentEndX,
  isInitial,
}: RuntimeScrollMetrics): RuntimeScrollTarget {
  const maximumLeft = Math.max(0, scrollWidth - clientWidth)
  const targetLeft = Math.min(
    maximumLeft,
    Math.max(0, contentEndX - clientWidth + RUNTIME_SCROLL_PADDING),
  )
  const viewportEndX = currentScrollLeft + clientWidth
  const shouldFollow = viewportEndX >=
    previousContentEndX - RUNTIME_SCROLL_FOLLOW_THRESHOLD

  return isInitial || contentEndX < previousContentEndX || shouldFollow
    ? { shouldScroll: true, left: targetLeft }
    : { shouldScroll: false, left: currentScrollLeft }
}

export function getRuntimeResizeScrollTarget({
  clientWidth,
  scrollWidth,
  currentScrollLeft,
  contentEndX,
  wasAtLiveEdge,
}: RuntimeResizeScrollMetrics): RuntimeScrollTarget {
  if (wasAtLiveEdge) {
    return getRuntimeScrollTarget({
      clientWidth,
      scrollWidth,
      currentScrollLeft,
      previousContentEndX: contentEndX,
      contentEndX,
      isInitial: true,
    })
  }

  const maximumLeft = Math.max(0, scrollWidth - clientWidth)
  const left = Math.min(maximumLeft, Math.max(0, currentScrollLeft))
  return left === currentScrollLeft
    ? { shouldScroll: false, left }
    : { shouldScroll: true, left }
}

export function isRuntimeAtLiveEdge({
  clientWidth,
  currentScrollLeft,
  contentEndX,
}: RuntimeLiveEdgeMetrics): boolean {
  return currentScrollLeft + clientWidth >=
    contentEndX - RUNTIME_SCROLL_FOLLOW_THRESHOLD
}

export function isRuntimeTaskAtLiveEdge({
  clientHeight,
  scrollHeight,
  currentScrollTop,
}: RuntimeTaskLiveEdgeMetrics): boolean {
  return currentScrollTop + clientHeight >=
    scrollHeight - RUNTIME_SCROLL_FOLLOW_THRESHOLD
}

export function getRuntimeTaskScrollTarget({
  clientHeight,
  scrollHeight,
  currentScrollTop,
  previousViewportHeight,
  previousContentHeight,
  isInitial,
}: RuntimeTaskScrollMetrics): RuntimeTaskScrollTarget {
  const maximumTop = Math.max(0, scrollHeight - clientHeight)
  const targetTop = maximumTop
  const viewportEnd = currentScrollTop + previousViewportHeight
  const shouldFollow = viewportEnd >=
    previousContentHeight - RUNTIME_SCROLL_FOLLOW_THRESHOLD

  const clampedTop = Math.min(maximumTop, Math.max(0, currentScrollTop))
  const top = isInitial || shouldFollow ? targetTop : clampedTop

  return top === currentScrollTop
    ? { shouldScroll: false, top }
    : { shouldScroll: true, top }
}

export function shouldRunRuntimeTimer({
  clockNowMs,
  voicePhase,
  runtimeTrace,
  tasks,
}: Pick<
  ReactRuntimePanelProps,
  'clockNowMs' | 'voicePhase' | 'runtimeTrace' | 'tasks'
>): boolean {
  if (clockNowMs !== undefined) return false

  return isVoiceInputActive(voicePhase) ||
    runtimeTrace.entries.some(
      (entry) => entry.lane === 'agent' && entry.status === 'active',
    ) ||
    getActiveTaskList(tasks).length > 0
}

type RuntimeFocusable = {
  focus: () => void
}

type RuntimeReturnFocusTargets = {
  fullscreen: boolean
  timeline: RuntimeFocusable | null
  fullscreenClose: RuntimeFocusable | null
}

export function focusRuntimeAfterReturn({
  fullscreen,
  timeline,
  fullscreenClose,
}: RuntimeReturnFocusTargets): void {
  const target = fullscreen ? fullscreenClose ?? timeline : timeline
  target?.focus()
}

export function RuntimeTaskBlock({
  task,
  left,
  top,
  width,
  nowMs,
  onCancelTask,
  onHoverTask,
  onFocusTask,
  onSelectTask,
}: RuntimeTaskBlockProps) {
  const progress = task.progress === undefined
    ? undefined
    : Math.min(100, Math.max(0, Math.round(task.progress)))
  const progressSummary = progress === undefined
    ? '进度未报告'
    : `进度 ${progress}%`
  const duration = formatTaskDuration(getTaskDurationMs(task, nowMs))
  const cancellable = canCancelTask(task)
  const cancelling = task.status === 'cancelling'
  const showCancelAction = cancellable || cancelling

  return (
    <article
      className="runtime-task-item"
      data-cancel-action={showCancelAction ? 'true' : 'false'}
      data-status={task.status}
      data-tool-name={task.toolName}
      style={{ left, top, width }}
      onMouseEnter={() => onHoverTask(task.taskId)}
      onMouseLeave={() => onHoverTask(undefined)}
      onFocus={() => onFocusTask(task.taskId)}
      onBlur={(event) => {
        if (!(event.relatedTarget instanceof Node) ||
          !event.currentTarget.contains(event.relatedTarget)) {
          onFocusTask(undefined)
        }
      }}
    >
      <button
        className="runtime-task-block"
        data-status={task.status}
        type="button"
        title={task.title}
        aria-label={`查看任务 ${task.title}`}
        onClick={() => onSelectTask(task.taskId)}
      >
        <span className="runtime-task-title" title={task.title}>{task.title}</span>
        <span className="runtime-task-meta">
          <span className="runtime-task-status">{TASK_STATUS_LABELS[task.status]}</span>
          <span>{progressSummary}</span>
          <span>{duration}</span>
        </span>
      </button>
      {showCancelAction && (
        <button
          className="runtime-task-cancel"
          data-state={cancelling ? 'cancelling' : 'ready'}
          type="button"
          aria-label={`${cancelling ? '正在取消' : '取消'} ${task.title}`}
          title={cancelling ? '正在取消任务' : '取消任务'}
          disabled={!cancellable}
          onClick={() => onCancelTask(task.taskId)}
        >
          <span aria-hidden="true">{cancelling ? '…' : '×'}</span>
        </button>
      )}
    </article>
  )
}

export function ReactRuntimePanel({
  runtimeTrace,
  tasks,
  connected,
  voicePhase,
  voiceDraft,
  onCancelTask,
  onSelectTask,
  onCollapse,
  clockNowMs,
}: ReactRuntimePanelProps) {
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [highlightedEntryId, setHighlightedEntryId] = useState<string>()
  const [hoveredTaskId, setHoveredTaskId] = useState<string>()
  const [focusedTaskId, setFocusedTaskId] = useState<string>()
  const [liveNowMs, setLiveNowMs] = useState(() => clockNowMs ?? Date.now())
  const [regularTaskViewport, setRegularTaskViewport] = useState(
    INITIAL_TASK_VIEWPORT,
  )
  const [fullscreenTaskViewport, setFullscreenTaskViewport] = useState(
    INITIAL_TASK_VIEWPORT,
  )
  const [regularLiveEdges, setRegularLiveEdges] = useState<RuntimeLiveEdges>(
    INITIAL_RUNTIME_LIVE_EDGES,
  )
  const [fullscreenLiveEdges, setFullscreenLiveEdges] = useState<RuntimeLiveEdges>(
    INITIAL_RUNTIME_LIVE_EDGES,
  )
  const regularScrollRef = useRef<HTMLDivElement>(null)
  const fullscreenScrollRef = useRef<HTMLDivElement>(null)
  const regularTaskScrollRef = useRef<HTMLDivElement>(null)
  const fullscreenTaskScrollRef = useRef<HTMLDivElement>(null)
  const regularHorizontalScrollSnapshotRef = useRef<
    RuntimeHorizontalScrollSnapshot | undefined
  >(undefined)
  const fullscreenHorizontalScrollSnapshotRef = useRef<
    RuntimeHorizontalScrollSnapshot | undefined
  >(undefined)
  const regularTaskScrollSnapshotRef = useRef<
    RuntimeTaskScrollSnapshot | undefined
  >(undefined)
  const fullscreenTaskScrollSnapshotRef = useRef<
    RuntimeTaskScrollSnapshot | undefined
  >(undefined)
  const fullscreenTriggerRef = useRef<HTMLButtonElement>(null)
  const fullscreenDialogRef = useRef<HTMLDivElement>(null)
  const fullscreenCloseRef = useRef<HTMLButtonElement>(null)
  const voiceActive = isVoiceInputActive(voicePhase)
  const runtimeTimerActive = shouldRunRuntimeTimer({
    clockNowMs,
    voicePhase,
    runtimeTrace,
    tasks,
  })
  const nowMs = clockNowMs ?? liveNowMs
  const highlightedTaskId = hoveredTaskId ?? focusedTaskId
  const activeTaskIds = useMemo(() => new Set(
    getActiveTaskList(tasks).map((task) => task.taskId),
  ), [tasks])
  const activeEntryIds = useMemo(() => new Set(
    runtimeTrace.entries
      .filter((entry) => entry.status === 'active')
      .map((entry) => entry.id),
  ), [runtimeTrace.entries])
  const layout = useMemo(
    () => buildRuntimeTimeline(runtimeTrace, tasks, nowMs),
    [nowMs, runtimeTrace, tasks],
  )
  const contentEndX = getRuntimeContentEndX(layout)
  const currentContentEndRef = useRef(contentEndX)
  currentContentEndRef.current = contentEndX

  const reconcileHorizontalScroller = (
    scrollRef: RefObject<HTMLDivElement | null>,
    snapshotRef: {
      current: RuntimeHorizontalScrollSnapshot | undefined
    },
    setLiveEdges: Dispatch<SetStateAction<RuntimeLiveEdges>>,
  ) => {
    const scroller = scrollRef.current
    if (!scroller) return

    const currentContentEndX = currentContentEndRef.current
    const previousSnapshot = snapshotRef.current
    const viewportChanged = previousSnapshot !== undefined &&
      previousSnapshot.viewportWidth !== scroller.clientWidth
    const target = viewportChanged
      ? getRuntimeResizeScrollTarget({
          clientWidth: scroller.clientWidth,
          scrollWidth: scroller.scrollWidth,
          currentScrollLeft: scroller.scrollLeft,
          contentEndX: currentContentEndX,
          wasAtLiveEdge: previousSnapshot.atLiveEdge,
        })
      : getRuntimeScrollTarget({
          clientWidth: scroller.clientWidth,
          scrollWidth: scroller.scrollWidth,
          currentScrollLeft: scroller.scrollLeft,
          previousContentEndX: previousSnapshot?.contentEndX ??
            currentContentEndX,
          contentEndX: currentContentEndX,
          isInitial: previousSnapshot === undefined,
        })
    if (target.shouldScroll) scroller.scrollLeft = target.left

    const horizontal = isRuntimeAtLiveEdge({
      clientWidth: scroller.clientWidth,
      currentScrollLeft: scroller.scrollLeft,
      contentEndX: currentContentEndX,
    })
    snapshotRef.current = {
      contentEndX: currentContentEndX,
      viewportWidth: scroller.clientWidth,
      atLiveEdge: horizontal,
    }
    setLiveEdges((current) => current.horizontal === horizontal
      ? current
      : { ...current, horizontal })
  }

  useEffect(() => {
    setHighlightedEntryId(undefined)
    setHoveredTaskId(undefined)
    setFocusedTaskId(undefined)
  }, [isFullscreen])

  useEffect(() => {
    if (!runtimeTimerActive) return undefined

    setLiveNowMs(Date.now())
    const intervalId = window.setInterval(() => {
      setLiveNowMs(Date.now())
    }, RUNTIME_TIMER_INTERVAL_MS)

    return () => window.clearInterval(intervalId)
  }, [runtimeTimerActive])

  useEffect(() => {
    reconcileHorizontalScroller(
      regularScrollRef,
      regularHorizontalScrollSnapshotRef,
      setRegularLiveEdges,
    )
    if (isFullscreen) {
      reconcileHorizontalScroller(
        fullscreenScrollRef,
        fullscreenHorizontalScrollSnapshotRef,
        setFullscreenLiveEdges,
      )
    } else {
      fullscreenHorizontalScrollSnapshotRef.current = undefined
      setFullscreenLiveEdges(INITIAL_RUNTIME_LIVE_EDGES)
    }
  }, [contentEndX, isFullscreen])

  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return undefined

    const observers: ResizeObserver[] = []
    const observeScroller = (
      scrollRef: RefObject<HTMLDivElement | null>,
      snapshotRef: {
        current: RuntimeHorizontalScrollSnapshot | undefined
      },
      setLiveEdges: Dispatch<SetStateAction<RuntimeLiveEdges>>,
    ) => {
      const scroller = scrollRef.current
      if (!scroller) return

      const observer = new ResizeObserver(() => {
        reconcileHorizontalScroller(scrollRef, snapshotRef, setLiveEdges)
      })
      observer.observe(scroller)
      observers.push(observer)
    }

    observeScroller(
      regularScrollRef,
      regularHorizontalScrollSnapshotRef,
      setRegularLiveEdges,
    )
    if (isFullscreen) {
      observeScroller(
        fullscreenScrollRef,
        fullscreenHorizontalScrollSnapshotRef,
        setFullscreenLiveEdges,
      )
    }

    return () => observers.forEach((observer) => observer.disconnect())
  }, [isFullscreen])

  useEffect(() => {
    const observers: ResizeObserver[] = []
    const observeTaskScroller = (
      taskScrollRef: RefObject<HTMLDivElement | null>,
      snapshotRef: { current: RuntimeTaskScrollSnapshot | undefined },
      setTaskViewport: Dispatch<SetStateAction<RuntimeTaskViewport>>,
      setLiveEdges: Dispatch<SetStateAction<RuntimeLiveEdges>>,
    ) => {
      const taskScroller = taskScrollRef.current
      if (!taskScroller) return

      const reconcile = () => {
        const previousSnapshot = snapshotRef.current
        const target = getRuntimeTaskScrollTarget({
          clientHeight: taskScroller.clientHeight,
          scrollHeight: taskScroller.scrollHeight,
          currentScrollTop: taskScroller.scrollTop,
          previousViewportHeight: previousSnapshot?.viewportHeight ??
            Number.POSITIVE_INFINITY,
          previousContentHeight: previousSnapshot?.contentHeight ??
            layout.taskContentHeight,
          isInitial: previousSnapshot === undefined,
        })
        if (target.shouldScroll) taskScroller.scrollTop = target.top

        const next = {
          scrollTop: taskScroller.scrollTop,
          viewportHeight: taskScroller.clientHeight,
        }
        setTaskViewport((current) => current.scrollTop === next.scrollTop &&
          current.viewportHeight === next.viewportHeight
          ? current
          : next)
        const vertical = isRuntimeTaskAtLiveEdge({
          clientHeight: taskScroller.clientHeight,
          scrollHeight: taskScroller.scrollHeight,
          currentScrollTop: taskScroller.scrollTop,
        })
        setLiveEdges((current) => current.vertical === vertical
          ? current
          : { ...current, vertical })
        snapshotRef.current = {
          contentHeight: layout.taskContentHeight,
          viewportHeight: taskScroller.clientHeight,
        }
      }
      reconcile()
      if (typeof ResizeObserver === 'undefined') return

      const observer = new ResizeObserver(reconcile)
      observer.observe(taskScroller)
      observers.push(observer)
    }

    observeTaskScroller(
      regularTaskScrollRef,
      regularTaskScrollSnapshotRef,
      setRegularTaskViewport,
      setRegularLiveEdges,
    )
    if (isFullscreen) {
      observeTaskScroller(
        fullscreenTaskScrollRef,
        fullscreenTaskScrollSnapshotRef,
        setFullscreenTaskViewport,
        setFullscreenLiveEdges,
      )
    } else {
      fullscreenTaskScrollSnapshotRef.current = undefined
      setFullscreenTaskViewport(INITIAL_TASK_VIEWPORT)
    }

    return () => observers.forEach((observer) => observer.disconnect())
  }, [isFullscreen, layout.taskContentHeight])

  useEffect(() => {
    if (!isFullscreen) return undefined

    fullscreenCloseRef.current?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setIsFullscreen(false)
        return
      }
      if (event.key !== 'Tab') return

      const focusableElements = Array.from(
        fullscreenDialogRef.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled])',
        ) ?? [],
      )
      const currentIndex = focusableElements.indexOf(
        document.activeElement as HTMLElement,
      )
      const wrapIndex = getFocusWrapIndex({
        currentIndex,
        focusableCount: focusableElements.length,
        backwards: event.shiftKey,
      })
      if (wrapIndex === undefined) return

      event.preventDefault()
      focusableElements[wrapIndex]?.focus()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      fullscreenTriggerRef.current?.focus()
    }
  }, [isFullscreen])

  const renderEntry = ({ entry, x, width }: PositionedRuntimeEntry) => (
    <article
      key={entry.id}
      className={`runtime-entry runtime-entry-${entry.lane}`}
      data-kind={entry.kind}
      data-status={entry.status}
      style={{ left: x, width }}
      title={entry.label}
      onMouseEnter={() => setHighlightedEntryId(entry.id)}
      onMouseLeave={() => setHighlightedEntryId(undefined)}
    >
      <span className="runtime-entry-text">{entry.label}</span>
      <span className="runtime-entry-status">{getRuntimeEntryStatusLabel(entry)}</span>
    </article>
  )

  const renderTimeline = (
    scrollRef: RefObject<HTMLDivElement | null>,
    taskScrollRef: RefObject<HTMLDivElement | null>,
    taskViewport: RuntimeTaskViewport,
    setTaskViewport: (viewport: RuntimeTaskViewport) => void,
    horizontalScrollSnapshotRef: {
      current: RuntimeHorizontalScrollSnapshot | undefined
    },
    liveEdges: RuntimeLiveEdges,
    setLiveEdges: Dispatch<SetStateAction<RuntimeLiveEdges>>,
    fullscreen = false,
  ) => {
    const userEntries = layout.entries.filter(({ entry }) => entry.lane === 'user')
    const agentEntries = layout.entries.filter(({ entry }) => entry.lane === 'agent')
    const asrLeft = Math.max(16, Math.min(layout.playheadX + 8, layout.width - 152))
    const hasRuntimeFacts = runtimeTrace.entries.length > 0 || layout.tasks.length > 0
    const markerPrefix = fullscreen ? 'runtime-fullscreen' : 'runtime-regular'
    const viewingHistory = !liveEdges.horizontal || !liveEdges.vertical
    const projectedConnectors = layout.connectors.flatMap((connector) => {
      const projected = projectRuntimeConnector(connector, {
        taskScrollTop: taskViewport.scrollTop,
        taskViewportHeight: taskViewport.viewportHeight,
      })
      return projected === undefined ? [] : [projected]
    })
    const returnToLive = () => {
      const scroller = scrollRef.current
      if (scroller) {
        const target = getRuntimeScrollTarget({
          clientWidth: scroller.clientWidth,
          scrollWidth: scroller.scrollWidth,
          currentScrollLeft: scroller.scrollLeft,
          previousContentEndX: contentEndX,
          contentEndX,
          isInitial: true,
        })
        if (target.shouldScroll) scroller.scrollLeft = target.left
        horizontalScrollSnapshotRef.current = {
          contentEndX,
          viewportWidth: scroller.clientWidth,
          atLiveEdge: true,
        }
      }

      const taskScroller = taskScrollRef.current
      if (taskScroller) {
        taskScroller.scrollTop = Math.max(
          0,
          taskScroller.scrollHeight - taskScroller.clientHeight,
        )
        setTaskViewport({
          scrollTop: taskScroller.scrollTop,
          viewportHeight: taskScroller.clientHeight,
        })
      }
      focusRuntimeAfterReturn({
        fullscreen,
        timeline: scroller,
        fullscreenClose: fullscreenCloseRef.current,
      })
      setLiveEdges(INITIAL_RUNTIME_LIVE_EDGES)
    }

    return (
      <div className={`runtime-timeline-frame${fullscreen ? ' runtime-timeline-fullscreen' : ''}`}>
        {viewingHistory && (
          <div className="runtime-live-return" role="status">
            <span>正在查看历史</span>
            <button type="button" onClick={returnToLive}>回到实时</button>
          </div>
        )}
        <div className="runtime-lane-labels" aria-hidden="true">
          <span style={{ top: RUNTIME_LANE_TOPS.user }}>用户输入</span>
          <span style={{ top: RUNTIME_LANE_TOPS.agent }}>Agent Runner</span>
          <span style={{ top: RUNTIME_LANE_TOPS.task }}>TaskManager</span>
        </div>
        <div
          className="runtime-timeline-scroll"
          ref={scrollRef}
          tabIndex={-1}
          onScroll={({ currentTarget }: UIEvent<HTMLDivElement>) => {
            const previousSnapshot = horizontalScrollSnapshotRef.current
            if (previousSnapshot !== undefined &&
              previousSnapshot.viewportWidth !== currentTarget.clientWidth) {
              return
            }
            const horizontal = isRuntimeAtLiveEdge({
              clientWidth: currentTarget.clientWidth,
              currentScrollLeft: currentTarget.scrollLeft,
              contentEndX,
            })
            horizontalScrollSnapshotRef.current = {
              contentEndX,
              viewportWidth: currentTarget.clientWidth,
              atLiveEdge: horizontal,
            }
            setLiveEdges((current) => current.horizontal === horizontal
              ? current
              : { ...current, horizontal })
          }}
        >
          <div
            className="runtime-timeline-canvas"
            style={{ width: layout.width }}
          >
            <section
              className="runtime-lane runtime-lane-user"
              data-lane="user"
              role="region"
              aria-label="用户输入"
              style={{
                top: RUNTIME_LANE_TOPS.user,
                height: RUNTIME_LANE_HEIGHT,
              }}
            >
              {layout.userGaps.map((gap) => {
                const formatted = formatRuntimeGap(gap.durationMs)
                return (
                  <span
                    className="runtime-gap-marker"
                    key={gap.id}
                    style={{ left: gap.x }}
                    title={`距离上一次用户输入 ${formatted.slice(1)}`}
                  >
                    {formatted}
                  </span>
                )
              })}
              {userEntries.map(renderEntry)}
              {voiceActive && (
                <article className="runtime-asr-live" style={{ left: asrLeft }}>
                  <strong>ASR 实时输入</strong>
                  <span className="runtime-asr-text">
                    {voiceDraft.trim() || '正在接收语音'}
                  </span>
                  <span className="runtime-asr-activity" aria-hidden="true">
                    {Array.from({ length: 5 }, (_, index) => (
                      <span className="runtime-asr-bar" key={index} />
                    ))}
                  </span>
                </article>
              )}
              {!hasRuntimeFacts && !voiceActive && (
                <span className="runtime-empty">
                  <strong>等待用户输入</strong>
                  <span>输入后将展示请求、Agent 与任务的实时关系</span>
                </span>
              )}
            </section>
            <section
              className="runtime-lane runtime-lane-agent"
              data-lane="agent"
              role="region"
              aria-label="Agent Runner"
              style={{
                top: RUNTIME_LANE_TOPS.agent,
                height: RUNTIME_LANE_HEIGHT,
              }}
            >
              {agentEntries.map(renderEntry)}
            </section>
            <section
              className="runtime-lane runtime-lane-task"
              data-lane="task"
              role="region"
              aria-label="TaskManager"
              style={{
                top: RUNTIME_LANE_TOPS.task,
                bottom: 0,
              }}
            >
              <div
                className="runtime-task-scroll"
                ref={taskScrollRef}
                onScroll={({ currentTarget }: UIEvent<HTMLDivElement>) => {
                  setTaskViewport({
                    scrollTop: currentTarget.scrollTop,
                    viewportHeight: currentTarget.clientHeight,
                  })
                  const vertical = isRuntimeTaskAtLiveEdge({
                    clientHeight: currentTarget.clientHeight,
                    scrollHeight: currentTarget.scrollHeight,
                    currentScrollTop: currentTarget.scrollTop,
                  })
                  setLiveEdges((current) => current.vertical === vertical
                    ? current
                    : { ...current, vertical })
                }}
              >
                <div
                  className="runtime-task-axes"
                  style={{ height: layout.taskContentHeight }}
                >
                  {layout.tasks.map(({
                    task,
                    x,
                    width,
                    axisIndex,
                    axisTop,
                    contentTop,
                  }) => (
                    <div
                      aria-label={`任务 ${String(axisIndex + 1).padStart(2, '0')}：${task.title}，状态：${TASK_STATUS_LABELS[task.status]}`}
                      className="runtime-task-axis"
                      data-task-axis={task.taskId}
                      key={task.taskId}
                      role="group"
                      style={{ top: axisTop, height: RUNTIME_TASK_AXIS_HEIGHT }}
                    >
                      <span className="runtime-task-axis-label">
                        任务 {String(axisIndex + 1).padStart(2, '0')} · {task.title}
                      </span>
                      <RuntimeTaskBlock
                        task={task}
                        left={x}
                        top={contentTop - axisTop}
                        width={width}
                        nowMs={nowMs}
                        onCancelTask={onCancelTask}
                        onHoverTask={setHoveredTaskId}
                        onFocusTask={setFocusedTaskId}
                        onSelectTask={onSelectTask}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </section>
            <svg
              className="runtime-connectors"
              width={layout.width}
              height="100%"
              aria-hidden="true"
            >
              <defs>
                {CONNECTOR_KINDS.map((kind) => (
                  <marker
                    className={`runtime-connector-marker runtime-connector-marker-${kind}`}
                    id={`${markerPrefix}-${kind}-arrow`}
                    key={kind}
                    markerHeight="10"
                    markerUnits="userSpaceOnUse"
                    markerWidth="10"
                    orient="auto"
                    refX="9"
                    refY="5"
                    viewBox="0 0 10 10"
                  >
                    <polygon points="0,0 10,5 0,10" />
                  </marker>
                ))}
              </defs>
              {projectedConnectors.map((connector) => {
                const hasActiveEntry = connector.relatedEntryIds.some(
                  (entryId) => activeEntryIds.has(entryId),
                )
                const emphasized =
                  (connector.taskId !== undefined &&
                    (activeTaskIds.has(connector.taskId) ||
                      connector.taskId === highlightedTaskId)) ||
                  hasActiveEntry ||
                  (highlightedEntryId !== undefined &&
                    connector.relatedEntryIds.includes(highlightedEntryId))
                return (
                  <g
                    className="runtime-connector"
                    data-connector={connector.kind}
                    data-emphasis={emphasized ? 'true' : 'false'}
                    key={connector.id}
                  >
                    <path
                      d={connector.path}
                      markerEnd={`url(#${markerPrefix}-${connector.kind}-arrow)`}
                    />
                    <text x={connector.labelX + 6} y={connector.labelY}>
                      {CONNECTOR_LABELS[connector.kind]}
                    </text>
                  </g>
                )
              })}
            </svg>
            <span
              className="runtime-playhead"
              data-live={runtimeTimerActive ? 'true' : 'false'}
              style={{ left: layout.playheadX }}
              aria-hidden="true"
            />
          </div>
        </div>
      </div>
    )
  }

  return (
    <section className="panel runtime-panel">
      <header className="panel-header compact">
        <div>
          <p className="eyebrow">react runtime</p>
          <div className="runtime-heading-row">
            <h2>Agent 如何运行</h2>
            <span
              className="runtime-time-scale"
              title="横向距离经过非线性压缩，表示相对时间"
            >
              压缩时间
            </span>
          </div>
          {connected === false && (
            <span className="runtime-connection-error" role="status">连接异常</span>
          )}
        </div>
        <div className="dag-panel-actions runtime-panel-actions">
          <button
            ref={fullscreenTriggerRef}
            aria-label="全屏查看运行关系"
            className="dag-fullscreen-toggle"
            type="button"
            onClick={() => setIsFullscreen(true)}
          >
            全屏
          </button>
          {onCollapse && (
            <button
              aria-label="收起运行关系面板"
              className="dag-fullscreen-toggle"
              type="button"
              onClick={onCollapse}
            >
              收起 ›
            </button>
          )}
        </div>
      </header>
      {renderTimeline(
        regularScrollRef,
        regularTaskScrollRef,
        regularTaskViewport,
        setRegularTaskViewport,
        regularHorizontalScrollSnapshotRef,
        regularLiveEdges,
        setRegularLiveEdges,
      )}
      {isFullscreen && (
        <div
          ref={fullscreenDialogRef}
          className="dag-fullscreen-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="运行关系全屏视图"
        >
          <section className="dag-fullscreen-panel runtime-fullscreen-panel">
            <header className="dag-fullscreen-header">
              <div>
                <p className="eyebrow">react runtime</p>
                <div className="runtime-heading-row">
                  <h2>Agent 如何运行</h2>
                  <span
                    className="runtime-time-scale"
                    title="横向距离经过非线性压缩，表示相对时间"
                  >
                    压缩时间
                  </span>
                </div>
              </div>
              <button
                ref={fullscreenCloseRef}
                aria-label="退出运行关系全屏"
                className="dag-fullscreen-close"
                type="button"
                onClick={() => setIsFullscreen(false)}
              >
                退出
              </button>
            </header>
            {renderTimeline(
              fullscreenScrollRef,
              fullscreenTaskScrollRef,
              fullscreenTaskViewport,
              setFullscreenTaskViewport,
              fullscreenHorizontalScrollSnapshotRef,
              fullscreenLiveEdges,
              setFullscreenLiveEdges,
              true,
            )}
          </section>
        </div>
      )}
    </section>
  )
}
