import type { AgentConsoleEvent, TaskStatus } from './events'
import { isTaskEvent } from './events'

export interface TaskProjection {
  taskId: string
  toolName: string
  title: string
  arguments: Record<string, unknown>
  originMessageId?: string
  conversationTurnId?: string
  status: TaskStatus
  progress?: number
  trace: string[]
  result?: unknown
  error?: string
  cancelReason?: string
  createdAt: string
  startedAt?: string
  updatedAt: string
  completedAt?: string
}

export interface TaskProjectionState {
  byId: Record<string, TaskProjection>
  order: string[]
}

export function initialTaskProjectionState(): TaskProjectionState {
  return { byId: {}, order: [] }
}

export function canCancelTask(task?: TaskProjection): boolean {
  return task?.status === 'pending' || task?.status === 'running'
}

export function isActiveTaskStatus(status: TaskStatus): boolean {
  return status === 'pending' || status === 'running' || status === 'cancelling'
}

export function getTaskList(state: TaskProjectionState): TaskProjection[] {
  return state.order
    .map((taskId) => state.byId[taskId])
    .filter((task): task is TaskProjection => Boolean(task))
}

export function getActiveTaskList(state: TaskProjectionState): TaskProjection[] {
  return getTaskList(state).filter((task) => isActiveTaskStatus(task.status))
}

export function getArchivedTaskList(state: TaskProjectionState): TaskProjection[] {
  return getTaskList(state)
    .filter((task) =>
      task.status === 'success' ||
      task.status === 'failed' ||
      task.status === 'cancelled',
    )
    .sort((left, right) => {
      const leftTime = left.completedAt ?? left.updatedAt
      const rightTime = right.completedAt ?? right.updatedAt
      return rightTime.localeCompare(leftTime)
    })
}

export function getTaskDurationMs(
  task: TaskProjection,
  nowMs = Date.now(),
): number {
  const start = Date.parse(task.startedAt ?? task.createdAt)
  const end = task.completedAt === undefined ? nowMs : Date.parse(task.completedAt)

  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    return 0
  }

  return Math.max(0, end - start)
}

export function formatTaskDuration(durationMs: number): string {
  const seconds = Math.max(0, durationMs) / 1000
  return `${seconds.toFixed(1)}s`
}

export function applyTaskEvent(
  state: TaskProjectionState,
  event: AgentConsoleEvent,
): TaskProjectionState {
  if (!isTaskEvent(event)) {
    return state
  }

  if (event.type === 'task.created') {
    const current = state.byId[event.taskId]
    const task: TaskProjection = {
      taskId: event.taskId,
      toolName: event.toolName,
      title: event.title,
      arguments: event.arguments,
      originMessageId: event.originMessageId ?? current?.originMessageId,
      conversationTurnId:
        event.conversationTurnId ?? current?.conversationTurnId,
      status: 'pending',
      progress: 0,
      trace: current?.trace ?? [],
      createdAt: current?.createdAt ?? event.timestamp,
      startedAt: current?.startedAt,
      updatedAt: event.timestamp,
    }

    return {
      byId: {
        ...state.byId,
        [event.taskId]: task,
      },
      order: state.order.includes(event.taskId)
        ? state.order
        : [...state.order, event.taskId],
    }
  }

  const current = state.byId[event.taskId]
  if (!current) {
    return state
  }

  switch (event.type) {
    case 'task.start':
      return updateTask(state, {
        ...current,
        status: 'running',
        startedAt: current.startedAt ?? event.timestamp,
        updatedAt: event.timestamp,
      })

    case 'task.progress':
      return updateTask(state, {
        ...current,
        status: current.status === 'pending' ? 'running' : current.status,
        progress: event.progress ?? current.progress,
        trace: [...current.trace, event.message],
        startedAt: current.startedAt ?? event.timestamp,
        updatedAt: event.timestamp,
      })

    case 'task.success':
      return updateTask(state, {
        ...current,
        status: 'success',
        progress: 100,
        result: event.result,
        updatedAt: event.timestamp,
        completedAt: event.timestamp,
      })

    case 'task.failure':
      return updateTask(state, {
        ...current,
        status: 'failed',
        error: event.error,
        updatedAt: event.timestamp,
        completedAt: event.timestamp,
      })

    case 'task.cancel.requested':
      if (current.status !== 'pending' && current.status !== 'running') {
        return state
      }
      return updateTask(state, {
        ...current,
        status: 'cancelling',
        cancelReason: event.reason,
        updatedAt: event.timestamp,
      })

    case 'task.cancelled':
      return updateTask(state, {
        ...current,
        status: 'cancelled',
        progress: 0,
        cancelReason: event.reason,
        updatedAt: event.timestamp,
        completedAt: event.timestamp,
      })
  }

  return state
}

function updateTask(
  state: TaskProjectionState,
  task: TaskProjection,
): TaskProjectionState {
  return {
    byId: {
      ...state.byId,
      [task.taskId]: task,
    },
    order: state.order,
  }
}
