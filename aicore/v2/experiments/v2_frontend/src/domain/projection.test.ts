import { describe, expect, it } from 'vitest'
import type { AgentConsoleEvent } from './events'
import {
  applyTaskEvent,
  canCancelTask,
  formatTaskDuration,
  getActiveTaskList,
  getArchivedTaskList,
  getTaskDurationMs,
  getTaskList,
  initialTaskProjectionState,
} from './projection'

const baseTime = '2026-06-16T10:00:00.000Z'

function event(overrides: Partial<AgentConsoleEvent>): AgentConsoleEvent {
  return {
    id: 'event-1',
    type: 'task.created',
    timestamp: baseTime,
    taskId: 'task-1',
    toolName: 'tool',
    arguments: { value: true },
    title: 'tool',
    ...overrides,
  } as AgentConsoleEvent
}

describe('task projection reducer', () => {
  it('projects a task from created to running to success', () => {
    let state = initialTaskProjectionState()
    state = applyTaskEvent(state, event({
      type: 'task.created',
      originMessageId: 'agent-origin',
    }))
    state = applyTaskEvent(state, event({ id: 'event-2', type: 'task.start' }))
    state = applyTaskEvent(state, event({ id: 'event-3', type: 'task.progress', progress: 55, message: 'halfway' }))
    state = applyTaskEvent(state, event({ id: 'event-4', type: 'task.success', result: { ok: true } }))

    const task = state.byId['task-1']
    expect(task.status).toBe('success')
    expect(task.progress).toBe(100)
    expect(task.trace).toEqual(['halfway'])
    expect(task.result).toEqual({ ok: true })
    expect(task.originMessageId).toBe('agent-origin')
  })

  it('records task start time and derives live and final runtime', () => {
    let state = initialTaskProjectionState()
    state = applyTaskEvent(state, event({ type: 'task.created', timestamp: '2026-06-16T10:00:00.000Z' }))
    state = applyTaskEvent(state, event({ id: 'event-2', type: 'task.start', timestamp: '2026-06-16T10:00:02.000Z' }))

    let task = state.byId['task-1']
    expect(task.startedAt).toBe('2026-06-16T10:00:02.000Z')
    expect(getTaskDurationMs(task, Date.parse('2026-06-16T10:00:07.500Z'))).toBe(5500)
    expect(formatTaskDuration(5500)).toBe('5.5s')

    state = applyTaskEvent(state, event({ id: 'event-3', type: 'task.success', timestamp: '2026-06-16T10:00:12.250Z', result: {} }))
    task = state.byId['task-1']

    expect(getTaskDurationMs(task, Date.parse('2026-06-16T10:01:00.000Z'))).toBe(10250)
    expect(formatTaskDuration(getTaskDurationMs(task))).toBe('10.3s')
  })

  it('moves a running task through cancelling to cancelled', () => {
    let state = initialTaskProjectionState()
    state = applyTaskEvent(state, event({ type: 'task.created' }))
    state = applyTaskEvent(state, event({ id: 'event-2', type: 'task.start' }))
    state = applyTaskEvent(state, event({ id: 'event-3', type: 'task.cancel.requested', reason: '用户点击取消' }))
    state = applyTaskEvent(state, event({ id: 'event-4', type: 'task.cancelled', reason: '用户取消' }))

    const task = state.byId['task-1']
    expect(task.status).toBe('cancelled')
    expect(task.progress).toBe(0)
    expect(task.cancelReason).toBe('用户取消')
    expect(canCancelTask(task)).toBe(false)
  })

  it('moves a pending task through cancelling to cancelled', () => {
    let state = initialTaskProjectionState()
    state = applyTaskEvent(state, event({ type: 'task.created' }))
    state = applyTaskEvent(state, event({ id: 'event-2', type: 'task.cancel.requested', reason: '用户点击取消' }))

    expect(state.byId['task-1']).toMatchObject({
      status: 'cancelling',
      cancelReason: '用户点击取消',
    })

    state = applyTaskEvent(state, event({ id: 'event-3', type: 'task.cancelled', reason: '用户取消' }))
    expect(state.byId['task-1'].status).toBe('cancelled')
  })

  it('only allows cancelling pending or running tasks', () => {
    let state = initialTaskProjectionState()
    state = applyTaskEvent(state, event({ type: 'task.created' }))
    expect(canCancelTask(state.byId['task-1'])).toBe(true)

    state = applyTaskEvent(state, event({ id: 'event-2', type: 'task.start' }))
    expect(canCancelTask(state.byId['task-1'])).toBe(true)

    state = applyTaskEvent(state, event({ id: 'event-3', type: 'task.cancel.requested', reason: '用户点击取消' }))
    expect(canCancelTask(state.byId['task-1'])).toBe(false)
  })

  it('keeps task order by first creation', () => {
    let state = initialTaskProjectionState()
    state = applyTaskEvent(state, event({ taskId: 'task-1', toolName: 'tool', title: 'tool' }))
    state = applyTaskEvent(state, event({ id: 'event-2', taskId: 'car-1', toolName: 'car_control', title: '车控' }))

    expect(getTaskList(state).map((task) => task.taskId)).toEqual(['task-1', 'car-1'])
  })

  it('separates active tasks from archived tasks by status', () => {
    let state = initialTaskProjectionState()
    state = applyTaskEvent(state, event({ taskId: 'pending-task', title: '等待任务' }))
    state = applyTaskEvent(state, event({ taskId: 'running-task', title: '运行任务' }))
    state = applyTaskEvent(state, event({ id: 'start-running', taskId: 'running-task', type: 'task.start' }))
    state = applyTaskEvent(state, event({ taskId: 'cancelling-task', title: '取消中任务' }))
    state = applyTaskEvent(state, event({ id: 'start-cancelling', taskId: 'cancelling-task', type: 'task.start' }))
    state = applyTaskEvent(state, event({ id: 'request-cancel', taskId: 'cancelling-task', type: 'task.cancel.requested', reason: '用户取消' }))
    state = applyTaskEvent(state, event({ taskId: 'success-task', title: '成功任务' }))
    state = applyTaskEvent(state, event({ id: 'success', taskId: 'success-task', type: 'task.success', timestamp: '2026-06-16T10:00:03.000Z', result: {} }))
    state = applyTaskEvent(state, event({ taskId: 'failed-task', title: '失败任务' }))
    state = applyTaskEvent(state, event({ id: 'failed', taskId: 'failed-task', type: 'task.failure', timestamp: '2026-06-16T10:00:05.000Z', error: '失败' }))
    state = applyTaskEvent(state, event({ taskId: 'cancelled-task', title: '取消任务' }))
    state = applyTaskEvent(state, event({ id: 'start-cancelled', taskId: 'cancelled-task', type: 'task.start' }))
    state = applyTaskEvent(state, event({ id: 'cancelled', taskId: 'cancelled-task', type: 'task.cancelled', timestamp: '2026-06-16T10:00:04.000Z', reason: '用户取消' }))

    expect(getActiveTaskList(state).map((task) => task.taskId)).toEqual([
      'pending-task',
      'running-task',
      'cancelling-task',
    ])
    expect(getArchivedTaskList(state).map((task) => task.taskId)).toEqual([
      'failed-task',
      'cancelled-task',
      'success-task',
    ])
  })

  it('ignores non-task and unknown task events', () => {
    let state = initialTaskProjectionState()
    state = applyTaskEvent(state, {
      id: 'agent-event-1',
      type: 'agent.text.done',
      timestamp: baseTime,
      messageId: 'agent-1',
    })
    state = applyTaskEvent(state, event({ type: 'task.start', taskId: 'unknown-task' }))

    expect(state).toEqual(initialTaskProjectionState())
  })

  it('preserves createdAt and trace when a task is recreated', () => {
    let state = initialTaskProjectionState()
    state = applyTaskEvent(state, event({ timestamp: baseTime }))
    state = applyTaskEvent(state, event({ id: 'event-2', type: 'task.start' }))
    state = applyTaskEvent(state, event({ id: 'event-3', type: 'task.progress', progress: 30, message: 'progress' }))
    state = applyTaskEvent(state, event({ id: 'event-4', type: 'task.created', timestamp: '2026-06-16T10:00:05.000Z' }))

    expect(state.byId['task-1'].createdAt).toBe(baseTime)
    expect(state.byId['task-1'].trace).toEqual(['progress'])
    expect(state.order).toEqual(['task-1'])
  })

  it('ignores repeated cancel requests while already cancelling', () => {
    let state = applyTaskEvent(initialTaskProjectionState(), event({ type: 'task.created' }))
    state = applyTaskEvent(state, event({ id: 'event-2', type: 'task.cancel.requested', reason: '用户点击取消' }))
    const next = applyTaskEvent(state, event({ id: 'event-3', type: 'task.cancel.requested', reason: '重复点击' }))

    expect(next).toBe(state)
    expect(next.byId['task-1'].cancelReason).toBe('用户点击取消')
  })
})
