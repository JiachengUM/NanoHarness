import { useEffect, useReducer, useRef } from 'react'
import type { ConsoleState } from '../app/consoleReducer'
import {
  formatTaskDuration,
  getTaskDurationMs,
  type TaskProjection,
} from '../domain/projection'
import { JsonBlock } from './JsonBlock'
import { StatusBadge } from './StatusBadge'
import { formatDetailValue } from '../utils/unknown'
import { getTaskProgressPresentation } from './taskPresentation'

type InspectorDrawerProps = {
  state: ConsoleState
  interactionDisabled?: boolean
  onClose: () => void
}

type InspectorFocusTarget = {
  isConnected: boolean
  tabIndex: number
  matches: (selector: string) => boolean
  closest: (selector: string) => unknown
  focus: (options?: FocusOptions) => void
  blur: () => void
}

type InspectorFocusEnvironment = {
  isVisible: (target: InspectorFocusTarget) => boolean
  getActiveElement: () => unknown
  isInsideDrawer: (target: unknown) => boolean
}

type InspectorBlurTarget = {
  blur: () => void
}

type InspectorFocusInListener = (event: { target: unknown }) => void

const INSPECTOR_RETURN_FOCUS_SELECTOR = [
  'a[href]',
  'button',
  'input',
  'select',
  'textarea',
  '[tabindex]',
  '[contenteditable="true"]',
].join(', ')

export type InspectorLifecycleState = {
  isOpen: boolean
  showRaw: boolean
  retainedTask?: TaskProjection
}

export type InspectorLifecycleAction =
  | {
      type: 'sync'
      isOpen: boolean
      selectedTask?: TaskProjection
    }
  | { type: 'toggleRaw' }
  | { type: 'closeRequested' }
  | { type: 'exitTransitionEnd' }

const INSPECTOR_EXIT_FALLBACK_MS = 260

export function createInspectorLifecycleState(
  isOpen: boolean,
  selectedTask?: TaskProjection,
): InspectorLifecycleState {
  return {
    isOpen,
    showRaw: false,
    retainedTask: selectedTask,
  }
}

export function reduceInspectorLifecycle(
  state: InspectorLifecycleState,
  action: InspectorLifecycleAction,
): InspectorLifecycleState {
  switch (action.type) {
    case 'sync':
      return {
        isOpen: action.isOpen,
        showRaw: state.isOpen === action.isOpen ? state.showRaw : false,
        retainedTask: action.selectedTask ?? state.retainedTask,
      }
    case 'toggleRaw':
      return { ...state, showRaw: !state.showRaw }
    case 'closeRequested':
      return state.showRaw ? { ...state, showRaw: false } : state
    case 'exitTransitionEnd':
      return state.isOpen || state.retainedTask === undefined
        ? state
        : { ...state, retainedTask: undefined }
  }
}

export function shouldFinalizeInspectorExit(
  isOpen: boolean,
  isRootEvent: boolean,
  propertyName: string,
): boolean {
  return !isOpen && isRootEvent && propertyName === 'transform'
}

export function runInspectorClose(
  resetRaw: () => void,
  restoreFocus: () => void,
  onClose: () => void,
): void {
  resetRaw()
  restoreFocus()
  onClose()
}

export function restoreInspectorCloseFocus(
  returnFocusTarget: InspectorFocusTarget | null,
  closeButton: InspectorFocusTarget | null,
  isInsideDrawer: boolean,
  environment: InspectorFocusEnvironment,
): void {
  if (!isInspectorReturnFocusTarget(
    returnFocusTarget,
    isInsideDrawer,
    environment.isVisible,
  )) {
    releaseInspectorDrawerFocus(closeButton, environment)
    return
  }

  try {
    returnFocusTarget.focus({ preventScroll: true })
  } catch {
    releaseInspectorDrawerFocus(closeButton, environment)
    return
  }

  if (environment.getActiveElement() !== returnFocusTarget) {
    releaseInspectorDrawerFocus(closeButton, environment)
  }
}

function releaseInspectorDrawerFocus(
  closeButton: InspectorFocusTarget | null,
  environment: InspectorFocusEnvironment,
): void {
  const activeElement = environment.getActiveElement()
  if (isInspectorBlurTarget(activeElement) && environment.isInsideDrawer(activeElement)) {
    try {
      activeElement.blur()
      return
    } catch {
      // Fall through to the known close control when the active element cannot blur.
    }
  }

  closeButton?.blur()
}

function isInspectorBlurTarget(target: unknown): target is InspectorBlurTarget {
  return Boolean(
    target
    && typeof target === 'object'
    && 'blur' in target
    && typeof target.blur === 'function'
  )
}

function isInspectorReturnFocusTarget(
  returnFocusTarget: InspectorFocusTarget | null,
  isInsideDrawer: boolean,
  isVisible: (target: InspectorFocusTarget) => boolean,
): returnFocusTarget is InspectorFocusTarget {
  return Boolean(
    returnFocusTarget?.isConnected
    && !isInsideDrawer
    && !returnFocusTarget.matches(':disabled')
    && returnFocusTarget.tabIndex >= 0
    && !returnFocusTarget.closest('[hidden], [aria-hidden="true"], [inert]')
    && returnFocusTarget.matches(INSPECTOR_RETURN_FOCUS_SELECTOR)
    && isVisible(returnFocusTarget)
  )
}

export function resolveInspectorExternalFocusTarget<T extends InspectorFocusTarget>(
  currentTarget: T | null,
  candidate: T | null,
  isInsideDrawer: boolean,
  isVisible: (target: InspectorFocusTarget) => boolean,
): T | null {
  return isInspectorReturnFocusTarget(candidate, isInsideDrawer, isVisible)
    ? candidate
    : currentTarget
}

export function subscribeToInspectorFocusIn(
  addListener: (listener: InspectorFocusInListener) => void,
  removeListener: (listener: InspectorFocusInListener) => void,
  captureTarget: (target: unknown) => void,
): () => void {
  const listener: InspectorFocusInListener = (event) => captureTarget(event.target)
  addListener(listener)
  return () => removeListener(listener)
}

function isInspectorFocusTargetVisible(target: InspectorFocusTarget): boolean {
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

function IoPanel({
  label,
  value,
  tone = 'default',
}: {
  label: string
  value: unknown
  tone?: 'default' | 'danger'
}) {
  return (
    <div className={`inspector-io-block${tone === 'danger' ? ' is-danger' : ''}`}>
      <div className="inspector-io-head">{label}</div>
      <pre className="inspector-json">{formatDetailValue(value)}</pre>
    </div>
  )
}

function TaskDetail({ task }: { task: TaskProjection }) {
  const { isActive, progress, isIndeterminate, label: progressLabel } =
    getTaskProgressPresentation(task)
  const durationText = formatTaskDuration(getTaskDurationMs(task, Date.now()))
  const resultValue = task.result === undefined && isActive ? '执行中…' : task.result

  return (
    <section className="inspector-section inspector-detail">
      <div className="inspector-status-row">
        <strong>{task.toolName}</strong>
        <StatusBadge status={task.status} />
      </div>

      <div className="inspector-meta">
        <div className="inspector-meta-item">
          <span>耗时</span>
          <strong>{durationText}</strong>
        </div>
        <div className="inspector-meta-item">
          <span>进度</span>
          <strong>{progressLabel}</strong>
        </div>
      </div>

      <div
        className={`progress-track${isActive ? ' active' : ''}${isIndeterminate ? ' indeterminate' : ''}`}
      >
        <span style={isIndeterminate ? undefined : { width: `${progress}%` }} />
      </div>

      <h3 className="inspector-trace-title">执行轨迹</h3>
      {task.trace.length > 0 ? (
        <ol className="task-trace-timeline inspector-timeline">
          {task.trace.map((line, index) => {
            const isLast = index === task.trace.length - 1
            const stepClass = isLast ? (isActive ? ' current' : ' final') : ''
            return (
              <li
                key={`${task.taskId}-detail-trace-${index}`}
                className={`task-trace-step${stepClass}`}
              >
                <span className="task-trace-dot" aria-hidden="true" />
                <span className="task-trace-text">{line}</span>
              </li>
            )
          })}
        </ol>
      ) : (
        <p className="task-trace">暂无执行轨迹。</p>
      )}

      <div className="inspector-io">
        <IoPanel label="工具入参" value={task.arguments} />
        <IoPanel label="工具结果" value={resultValue} />
        {task.error && <IoPanel label="错误信息" value={task.error} tone="danger" />}
        {task.cancelReason && (
          <IoPanel label="取消原因" value={task.cancelReason} tone="danger" />
        )}
      </div>
    </section>
  )
}

export function InspectorDrawer({
  state,
  interactionDisabled = false,
  onClose,
}: InspectorDrawerProps) {
  const selectedTask = state.selectedTaskId ? state.tasks.byId[state.selectedTaskId] : undefined
  const isOpen = Boolean(selectedTask)
  const [lifecycle, dispatchLifecycle] = useReducer(
    reduceInspectorLifecycle,
    undefined,
    () => createInspectorLifecycleState(isOpen, selectedTask),
  )
  const drawerRef = useRef<HTMLElement | null>(null)
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)
  const returnFocusTargetRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!isOpen) return undefined

    const captureExternalFocusTarget = (target: unknown) => {
      const candidate = target instanceof HTMLElement ? target : null
      const isInsideDrawer = Boolean(candidate && drawerRef.current?.contains(candidate))
      returnFocusTargetRef.current = resolveInspectorExternalFocusTarget(
        returnFocusTargetRef.current,
        candidate,
        isInsideDrawer,
        isInspectorFocusTargetVisible,
      )
    }

    returnFocusTargetRef.current = null
    const activeElement = document.activeElement
    captureExternalFocusTarget(activeElement instanceof HTMLElement ? activeElement : null)

    return subscribeToInspectorFocusIn(
      (listener) => document.addEventListener('focusin', listener),
      (listener) => document.removeEventListener('focusin', listener),
      captureExternalFocusTarget,
    )
  }, [isOpen])

  useEffect(() => {
    dispatchLifecycle({
      type: 'sync',
      isOpen,
      selectedTask,
    })
  }, [isOpen, selectedTask])

  useEffect(() => {
    if (isOpen) return undefined

    const timeoutId = window.setTimeout(() => {
      dispatchLifecycle({ type: 'exitTransitionEnd' })
    }, INSPECTOR_EXIT_FALLBACK_MS)
    return () => window.clearTimeout(timeoutId)
  }, [isOpen])

  const displayedTask = selectedTask ?? lifecycle.retainedTask
  const showRaw = lifecycle.showRaw

  return (
    <aside
      ref={drawerRef}
      className={`inspector-drawer${isOpen ? ' is-open' : ''}`}
      aria-label={displayedTask ? '任务详情' : 'Console State'}
      aria-busy={interactionDisabled || undefined}
      aria-hidden={isOpen ? undefined : true}
      inert={!isOpen || interactionDisabled}
      onTransitionEnd={(event) => {
        if (shouldFinalizeInspectorExit(
          isOpen,
          event.currentTarget === event.target,
          event.propertyName,
        )) {
          dispatchLifecycle({ type: 'exitTransitionEnd' })
        }
      }}
    >
      <header>
        <div>
          <p className="eyebrow">{displayedTask ? 'task detail' : 'raw data'}</p>
          <h2>{displayedTask ? displayedTask.title : 'Console State'}</h2>
        </div>
        <button
          ref={closeButtonRef}
          type="button"
          onClick={() => runInspectorClose(
            () => dispatchLifecycle({ type: 'closeRequested' }),
            () => {
              const returnFocusTarget = returnFocusTargetRef.current
              restoreInspectorCloseFocus(
                returnFocusTarget,
                closeButtonRef.current,
                Boolean(returnFocusTarget && drawerRef.current?.contains(returnFocusTarget)),
                {
                  isVisible: isInspectorFocusTargetVisible,
                  getActiveElement: () => document.activeElement,
                  isInsideDrawer: (target) => (
                    target instanceof Node
                    && Boolean(drawerRef.current?.contains(target))
                  ),
                },
              )
            },
            onClose,
          )}
          aria-label={displayedTask ? '关闭任务详情' : '关闭 Console State'}
        >
          ×
        </button>
      </header>

      {displayedTask && <TaskDetail task={displayedTask} />}

      <section className="inspector-section">
        <button
          type="button"
          className="raw-data-toggle"
          aria-expanded={showRaw}
          onClick={() => dispatchLifecycle({ type: 'toggleRaw' })}
        >
          <span className={`raw-data-caret${showRaw ? ' open' : ''}`} aria-hidden="true">
            ▸
          </span>
          raw_data
        </button>
        {showRaw && (
          <div className="raw-data-body">
            {displayedTask && (
              <>
                <h3>Task</h3>
                <JsonBlock value={displayedTask} />
              </>
            )}
            <h3>Projection</h3>
            <JsonBlock value={state.tasks} />
          </div>
        )}
      </section>
    </aside>
  )
}
