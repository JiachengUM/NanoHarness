import { describe, expect, it } from 'vitest'
import type { AgentConsoleEvent } from '../domain/events'
import {
  applyRuntimeEvent,
  getAgentDelegationEntryId,
  initialRuntimeTraceState,
  markRuntimeSubmissionFailed,
  recordQueuedRuntimeSubmission,
  recordRuntimeSubmission,
} from './runtimeTraceReducer'

const t0 = '2026-07-13T10:00:00.000Z'
const t1 = '2026-07-13T10:00:01.000Z'
const t2 = '2026-07-13T10:00:02.000Z'
const t3 = '2026-07-13T10:00:03.000Z'
const microBase = '2026-07-13T10:00:00.000000Z'
const microT0 = '2026-07-13T10:00:00.000100Z'
const microT1 = '2026-07-13T10:00:00.000200Z'
const microT2 = '2026-07-13T10:00:00.000300Z'

function applyEvents(events: AgentConsoleEvent[]) {
  return events.reduce(applyRuntimeEvent, initialRuntimeTraceState())
}

describe('runtime trace reducer', () => {
  it('exports stable Agent delegation entry ids', () => {
    expect(getAgentDelegationEntryId).toBeTypeOf('function')
    expect(getAgentDelegationEntryId('agent-1')).toBe('agent-delegated:agent-1')
  })

  it('records a frontend submission without claiming backend acceptance', () => {
    const submission = {
      input: '同时找餐厅和停车场',
      userMessageId: 'user-1',
      assistantMessageId: 'agent-1',
      timestamp: t0,
    }

    let state = recordRuntimeSubmission(initialRuntimeTraceState(), submission)
    state = recordRuntimeSubmission(state, submission)

    expect(state.entries).toEqual([{
      id: 'user:user-1',
      kind: 'user.submitted',
      lane: 'user',
      label: '同时找餐厅和停车场',
      messageId: 'agent-1',
      status: 'submitted',
      timestamp: t0,
    }])
  })

  it('records queued voice submissions without interrupting active foreground activity', () => {
    let state = applyRuntimeEvent(initialRuntimeTraceState(), {
      id: 'agent-a1-start',
      type: 'agent.text.start',
      messageId: 'assistant-a1',
      timestamp: t0,
    })

    state = recordQueuedRuntimeSubmission(state, {
      input: '第二个排队语音任务',
      userMessageId: 'voice-user-2',
      assistantMessageId: 'assistant-a2',
      timestamp: t1,
    })

    expect(state.entries).toMatchObject([
      {
        id: 'agent-a1-start',
        messageId: 'assistant-a1',
        status: 'active',
      },
      {
        id: 'user:voice-user-2',
        messageId: 'assistant-a2',
        status: 'submitted',
      },
    ])
    expect(state.entries[0]).not.toHaveProperty('endTimestamp')
  })

  it('fails only the runtime submission owned by the matching assistant id', () => {
    const submission = {
      input: '会失败的语音任务',
      userMessageId: 'voice-user-failed',
      assistantMessageId: 'assistant-owned',
      timestamp: t0,
    }
    const queued = recordQueuedRuntimeSubmission(initialRuntimeTraceState(), submission)

    const badAssistant = markRuntimeSubmissionFailed(queued, {
      userMessageId: 'voice-user-failed',
      assistantMessageId: 'assistant-conflict',
      timestamp: t1,
    })
    expect(badAssistant).toBe(queued)

    const failed = markRuntimeSubmissionFailed(queued, {
      userMessageId: 'voice-user-failed',
      assistantMessageId: 'assistant-owned',
      timestamp: t2,
    })
    expect(failed.entries).toMatchObject([{
      id: 'user:voice-user-failed',
      messageId: 'assistant-owned',
      status: 'failed',
      endTimestamp: t2,
    }])
    expect(markRuntimeSubmissionFailed(failed, {
      userMessageId: 'voice-user-failed',
      assistantMessageId: 'assistant-owned',
      timestamp: t3,
    })).toBe(failed)
  })

  it('merges agent start, delta, and done into one content-free activity span', () => {
    const state = applyEvents([
      { id: 'start-1', type: 'agent.text.start', messageId: 'agent-1', timestamp: t0 },
      {
        id: 'delta-1',
        type: 'agent.text.delta',
        messageId: 'agent-1',
        delta: '这段正文绝不能存入 trace',
        timestamp: t1,
      },
      { id: 'done-1', type: 'agent.text.done', messageId: 'agent-1', timestamp: t2 },
    ])

    expect(state.entries).toMatchObject([{
      id: 'start-1',
      kind: 'agent.activity',
      lane: 'agent',
      label: 'Agent 简短回复',
      messageId: 'agent-1',
      status: 'complete',
      timestamp: t0,
      endTimestamp: t2,
      terminalEventId: 'done-1',
    }])
    expect(JSON.stringify(state)).not.toContain('这段正文绝不能存入 trace')
  })

  it('creates one Agent delegation card and two task markers for tasks from one origin', () => {
    const firstCreated: AgentConsoleEvent = {
      id: 'task-created-1',
      type: 'task.created',
      taskId: 'task-1',
      toolName: 'poi_search',
      title: '搜索餐厅',
      arguments: { query: '不能保存的首个任务参数' },
      originMessageId: 'agent-1',
      timestamp: t0,
    }
    const secondCreated: AgentConsoleEvent = {
      id: 'task-created-2',
      type: 'task.created',
      taskId: 'task-2',
      toolName: 'parking_search',
      title: '搜索停车场',
      arguments: { query: '不能保存的第二个任务参数' },
      originMessageId: 'agent-1',
      timestamp: t1,
    }

    let state = applyRuntimeEvent(initialRuntimeTraceState(), firstCreated)
    state = applyRuntimeEvent(state, secondCreated)
    const beforeReplay = state
    state = applyRuntimeEvent(state, firstCreated)

    expect(state).toBe(beforeReplay)
    expect(state.entries).toEqual([
      {
        id: 'agent-delegated:agent-1',
        kind: 'agent.delegated',
        lane: 'agent',
        label: '发起任务',
        status: 'complete',
        timestamp: t0,
        endTimestamp: t0,
        messageId: 'agent-1',
      },
      {
        id: 'task-created-1',
        kind: 'task.delegated',
        lane: 'task',
        label: '搜索餐厅',
        status: 'active',
        timestamp: t0,
        taskId: 'task-1',
        originMessageId: 'agent-1',
      },
      {
        id: 'task-created-2',
        kind: 'task.delegated',
        lane: 'task',
        label: '搜索停车场',
        status: 'active',
        timestamp: t1,
        taskId: 'task-2',
        originMessageId: 'agent-1',
      },
    ])
    expect(JSON.stringify(state)).not.toMatch(/不能保存的|首个任务参数|第二个任务参数/)
  })

  it('uses each event id for originless Agent delegations and deduplicates replays', () => {
    const firstCreated: AgentConsoleEvent = {
      id: 'task-created-without-origin',
      type: 'task.created',
      taskId: 'task-without-origin',
      toolName: 'poi_search',
      title: '搜索餐厅',
      arguments: { query: '绝不能进入 trace 的参数' },
      timestamp: t0,
    }
    const secondCreated: AgentConsoleEvent = {
      id: 'second-task-created-without-origin',
      type: 'task.created',
      taskId: 'second-task-without-origin',
      toolName: 'parking_search',
      title: '搜索停车场',
      arguments: { query: '另一个绝不能进入 trace 的参数' },
      timestamp: t1,
    }

    let state = applyRuntimeEvent(initialRuntimeTraceState(), firstCreated)
    state = applyRuntimeEvent(state, secondCreated)
    const afterReplay = applyRuntimeEvent(state, firstCreated)

    expect(afterReplay).toBe(state)
    expect(afterReplay.entries).toEqual([
      {
        id: 'agent-delegated:task-created-without-origin',
        kind: 'agent.delegated',
        lane: 'agent',
        label: '发起任务',
        status: 'complete',
        timestamp: t0,
        endTimestamp: t0,
      },
      {
        id: 'task-created-without-origin',
        kind: 'task.delegated',
        lane: 'task',
        label: '搜索餐厅',
        status: 'active',
        timestamp: t0,
        taskId: 'task-without-origin',
      },
      {
        id: 'agent-delegated:second-task-created-without-origin',
        kind: 'agent.delegated',
        lane: 'agent',
        label: '发起任务',
        status: 'complete',
        timestamp: t1,
        endTimestamp: t1,
      },
      {
        id: 'second-task-created-without-origin',
        kind: 'task.delegated',
        lane: 'task',
        label: '搜索停车场',
        status: 'active',
        timestamp: t1,
        taskId: 'second-task-without-origin',
      },
    ])
    expect(JSON.stringify(afterReplay)).not.toMatch(/绝不能进入 trace 的参数/)
  })

  it('keeps Agent delegation separate from later task-result activity', () => {
    const state = applyEvents([
      {
        id: 'task-created-1',
        type: 'task.created',
        taskId: 'task-1',
        toolName: 'poi_search',
        title: '搜索餐厅',
        arguments: { query: '不能保存的任务参数' },
        originMessageId: 'agent-1',
        timestamp: t0,
      },
      {
        id: 'task-result-start-1',
        type: 'agent.text.start',
        messageId: 'agent-1',
        sourceTaskId: 'task-1',
        originMessageId: 'agent-1',
        timestamp: t1,
      },
      {
        id: 'task-result-done-1',
        type: 'agent.text.done',
        messageId: 'agent-1',
        sourceTaskId: 'task-1',
        originMessageId: 'agent-1',
        timestamp: t2,
      },
    ])

    expect(state.entries).toMatchObject([
      {
        id: 'agent-delegated:agent-1',
        kind: 'agent.delegated',
        lane: 'agent',
        label: '发起任务',
        status: 'complete',
        timestamp: t0,
        endTimestamp: t0,
        messageId: 'agent-1',
      },
      {
        id: 'task-created-1',
        kind: 'task.delegated',
        lane: 'task',
        label: '搜索餐厅',
        status: 'active',
        timestamp: t0,
        taskId: 'task-1',
        originMessageId: 'agent-1',
      },
      {
        id: 'task-result-start-1',
        kind: 'agent.activity',
        lane: 'agent',
        label: '基于任务结果回复',
        status: 'complete',
        timestamp: t1,
        messageId: 'agent-1',
        sourceTaskId: 'task-1',
        originMessageId: 'agent-1',
        endTimestamp: t2,
        terminalEventId: 'task-result-done-1',
      },
    ])
    expect(JSON.stringify(state)).not.toContain('不能保存的任务参数')
  })

  it('records task terminal and cancellation markers without results or errors', () => {
    const state = applyEvents([
      { id: 'success-1', type: 'task.success', taskId: 'task-1', result: { secret: 'result' }, timestamp: t0 },
      { id: 'failure-1', type: 'task.failure', taskId: 'task-2', error: 'secret error', timestamp: t0 },
      { id: 'cancel-request-1', type: 'task.cancel.requested', taskId: 'task-3', reason: 'secret reason', timestamp: t1 },
      { id: 'cancelled-1', type: 'task.cancelled', taskId: 'task-3', reason: 'secret reason', timestamp: t2 },
    ])

    expect(state.entries).toEqual([
      expect.objectContaining({
        id: 'success-1',
        kind: 'task.succeeded',
        lane: 'task',
        label: '任务完成',
        status: 'complete',
        taskId: 'task-1',
      }),
      expect.objectContaining({
        id: 'failure-1',
        kind: 'task.failed',
        lane: 'task',
        label: '任务失败',
        status: 'failed',
        taskId: 'task-2',
      }),
      expect.objectContaining({
        id: 'cancel-request-1',
        kind: 'task.cancel.requested',
        lane: 'task',
        label: '正在取消',
        status: 'cancelling',
        taskId: 'task-3',
      }),
      expect.objectContaining({
        id: 'cancelled-1',
        kind: 'task.cancelled',
        lane: 'task',
        label: '已取消',
        status: 'cancelled',
        taskId: 'task-3',
      }),
    ])
    expect(JSON.stringify(state)).not.toMatch(/secret|result|error|reason/)
  })

  it('interrupts foreground activity while background task activity can finish', () => {
    let state = applyEvents([
      { id: 'start-1', type: 'agent.text.start', messageId: 'agent-1', timestamp: t0 },
      {
        id: 'start-2',
        type: 'agent.text.start',
        messageId: 'task-result-1',
        sourceTaskId: 'task-1',
        timestamp: t1,
      },
    ])

    state = recordRuntimeSubmission(state, {
      input: '新的请求',
      userMessageId: 'user-2',
      assistantMessageId: 'agent-2',
      timestamp: t2,
    })

    expect(state.entries.slice(0, 2)).toMatchObject([
      { messageId: 'agent-1', status: 'interrupted', endTimestamp: t2 },
      { messageId: 'task-result-1', status: 'active' },
    ])
    expect(state.entries[1]).not.toHaveProperty('endTimestamp')
    expect(state.entries.at(-1)).toMatchObject({
      kind: 'user.submitted',
      messageId: 'agent-2',
      label: '新的请求',
    })

    const afterBackgroundDone = applyRuntimeEvent(state, {
      id: 'task-result-done-1',
      type: 'agent.text.done',
      messageId: 'task-result-1',
      sourceTaskId: 'task-1',
      timestamp: t3,
    })
    expect(afterBackgroundDone.entries[1]).toMatchObject({
      messageId: 'task-result-1',
      sourceTaskId: 'task-1',
      status: 'complete',
      endTimestamp: t3,
      terminalEventId: 'task-result-done-1',
    })

    const afterLateEvents = applyRuntimeEvent(
      applyRuntimeEvent(afterBackgroundDone, {
        id: 'late-delta-1',
        type: 'agent.text.delta',
        messageId: 'agent-1',
        delta: '迟到正文',
        timestamp: '2026-07-13T10:00:03.000Z',
      }),
      {
        id: 'late-done-1',
        type: 'agent.text.done',
        messageId: 'agent-1',
        timestamp: '2026-07-13T10:00:04.000Z',
      },
    )
    const afterLateStart = applyRuntimeEvent(afterLateEvents, {
      id: 'late-start-1',
      type: 'agent.text.start',
      messageId: 'agent-1',
      timestamp: t0,
    })

    expect(afterLateStart).toEqual(afterBackgroundDone)
  })

  it('supports delta-only and done-only events when starts are missing', () => {
    let state = applyRuntimeEvent(initialRuntimeTraceState(), {
      id: 'delta-only',
      type: 'agent.text.delta',
      messageId: 'agent-delta',
      delta: '不保存',
      timestamp: t0,
    })
    state = applyRuntimeEvent(state, {
      id: 'done-after-delta',
      type: 'agent.text.done',
      messageId: 'agent-delta',
      timestamp: t1,
    })
    state = applyRuntimeEvent(state, {
      id: 'done-only',
      type: 'agent.text.done',
      messageId: 'agent-done',
      timestamp: t2,
    })

    expect(state.entries).toMatchObject([
      {
        id: 'delta-only',
        status: 'complete',
        timestamp: t0,
        endTimestamp: t1,
        terminalEventId: 'done-after-delta',
      },
      {
        id: 'done-only',
        status: 'complete',
        timestamp: t2,
        endTimestamp: t2,
        terminalEventId: 'done-only',
      },
    ])
  })

  it('creates a new activity when the same message starts again after completion', () => {
    const state = applyEvents([
      { id: 'start-1', type: 'agent.text.start', messageId: 'agent-1', timestamp: t0 },
      { id: 'done-1', type: 'agent.text.done', messageId: 'agent-1', timestamp: t1 },
      { id: 'start-2', type: 'agent.text.start', messageId: 'agent-1', timestamp: t2 },
      { id: 'done-2', type: 'agent.text.done', messageId: 'agent-1', timestamp: t3 },
    ])

    expect(state.entries).toMatchObject([
      {
        id: 'start-1',
        messageId: 'agent-1',
        status: 'complete',
        timestamp: t0,
        endTimestamp: t1,
      },
      {
        id: 'start-2',
        messageId: 'agent-1',
        status: 'complete',
        timestamp: t2,
        endTimestamp: t3,
      },
    ])
  })

  it('backfills an earlier start over a delta-first active span', () => {
    const state = applyEvents([
      {
        id: 'delta-1',
        type: 'agent.text.delta',
        messageId: 'agent-1',
        delta: '不保存',
        timestamp: t1,
      },
      {
        id: 'start-1',
        type: 'agent.text.start',
        messageId: 'agent-1',
        originMessageId: 'origin-1',
        sourceTaskId: 'task-1',
        timestamp: t0,
      },
      { id: 'done-1', type: 'agent.text.done', messageId: 'agent-1', timestamp: t2 },
    ])

    expect(state.entries).toMatchObject([{
      id: 'start-1',
      kind: 'agent.activity',
      lane: 'agent',
      label: '基于任务结果回复',
      status: 'complete',
      timestamp: t0,
      endTimestamp: t2,
      terminalEventId: 'done-1',
      messageId: 'agent-1',
      originMessageId: 'origin-1',
      sourceTaskId: 'task-1',
    }])
  })

  it('backfills an earlier start over a done-first span without reopening it', () => {
    const done = {
      id: 'done-1',
      type: 'agent.text.done' as const,
      messageId: 'agent-1',
      timestamp: t2,
    }
    let state = applyRuntimeEvent(initialRuntimeTraceState(), done)
    state = applyRuntimeEvent(state, {
      id: 'start-1',
      type: 'agent.text.start',
      messageId: 'agent-1',
      originMessageId: 'origin-1',
      sourceTaskId: 'task-1',
      timestamp: t0,
    })
    state = applyRuntimeEvent(state, done)

    expect(state.entries).toMatchObject([{
      id: 'start-1',
      kind: 'agent.activity',
      lane: 'agent',
      label: '基于任务结果回复',
      status: 'complete',
      timestamp: t0,
      endTimestamp: t2,
      terminalEventId: 'done-1',
      messageId: 'agent-1',
      originMessageId: 'origin-1',
      sourceTaskId: 'task-1',
    }])
  })

  it('does not apply a repeated old done event to a newer active span', () => {
    const oldDone = {
      id: 'done-1',
      type: 'agent.text.done' as const,
      messageId: 'agent-1',
      timestamp: t1,
    }
    let state = applyRuntimeEvent(initialRuntimeTraceState(), oldDone)
    state = applyRuntimeEvent(state, {
      id: 'start-1',
      type: 'agent.text.start',
      messageId: 'agent-1',
      timestamp: t0,
    })
    state = applyRuntimeEvent(state, {
      id: 'start-2',
      type: 'agent.text.start',
      messageId: 'agent-1',
      timestamp: t2,
    })

    const afterRepeatedDone = applyRuntimeEvent(state, oldDone)

    expect(afterRepeatedDone).toBe(state)
    expect(afterRepeatedDone.entries.at(-1)).toMatchObject({
      id: 'start-2',
      status: 'active',
      timestamp: t2,
    })
  })

  it('orders delta, earlier start, and done within one millisecond', () => {
    const state = applyEvents([
      {
        id: 'delta-1',
        type: 'agent.text.delta',
        messageId: 'agent-1',
        delta: '不保存',
        timestamp: microT1,
      },
      {
        id: 'start-1',
        type: 'agent.text.start',
        messageId: 'agent-1',
        timestamp: microT0,
      },
      { id: 'done-1', type: 'agent.text.done', messageId: 'agent-1', timestamp: microT2 },
    ])

    expect(state.entries).toMatchObject([{
      id: 'start-1',
      status: 'complete',
      timestamp: microT0,
      endTimestamp: microT2,
      terminalEventId: 'done-1',
    }])
  })

  it('backfills a microsecond-earlier start over a done-first span', () => {
    const state = applyEvents([
      { id: 'done-1', type: 'agent.text.done', messageId: 'agent-1', timestamp: microT2 },
      { id: 'start-1', type: 'agent.text.start', messageId: 'agent-1', timestamp: microT0 },
    ])

    expect(state.entries).toMatchObject([{
      id: 'start-1',
      status: 'complete',
      timestamp: microT0,
      endTimestamp: microT2,
      terminalEventId: 'done-1',
    }])
    expect(state.entries).toHaveLength(1)
  })

  it('deduplicates a terminal event replayed during a newer microsecond span', () => {
    const done = {
      id: 'done-1',
      type: 'agent.text.done' as const,
      messageId: 'agent-1',
      timestamp: microT0,
    }
    const state = applyEvents([
      { id: 'start-1', type: 'agent.text.start', messageId: 'agent-1', timestamp: microBase },
      done,
      { id: 'start-2', type: 'agent.text.start', messageId: 'agent-1', timestamp: microT1 },
    ])

    const afterReplay = applyRuntimeEvent(state, done)

    expect(afterReplay).toBe(state)
    expect(afterReplay.entries).toMatchObject([
      { id: 'start-1', status: 'complete', terminalEventId: 'done-1' },
      { id: 'start-2', status: 'active', timestamp: microT1 },
    ])
  })

  it('ignores a late start inside a completed span instead of overlapping it', () => {
    const state = applyEvents([
      { id: 'start-1', type: 'agent.text.start', messageId: 'agent-1', timestamp: microT0 },
      { id: 'done-1', type: 'agent.text.done', messageId: 'agent-1', timestamp: microT2 },
    ])

    const afterLateStart = applyRuntimeEvent(state, {
      id: 'late-start-1',
      type: 'agent.text.start',
      messageId: 'agent-1',
      timestamp: microT1,
    })

    expect(afterLateStart).toBe(state)
    expect(afterLateStart.entries).toMatchObject([{
      id: 'start-1',
      status: 'complete',
      timestamp: microT0,
      endTimestamp: microT2,
      terminalEventId: 'done-1',
    }])
    expect(afterLateStart.entries).toHaveLength(1)
  })

  it('returns the same state for an active delta with no new relationships', () => {
    const state = applyRuntimeEvent(initialRuntimeTraceState(), {
      id: 'start-1',
      type: 'agent.text.start',
      messageId: 'agent-1',
      timestamp: t0,
    })

    const next = applyRuntimeEvent(state, {
      id: 'delta-1',
      type: 'agent.text.delta',
      messageId: 'agent-1',
      delta: '不保存',
      timestamp: t1,
    })

    expect(next).toBe(state)
  })

  it('groups Agent spans by output run and keeps a multi-task cause set', () => {
    const state = applyEvents([
      {
        id: 'run-1-start',
        type: 'agent.text.start',
        messageId: 'native-assistant-turn-1',
        outputRunId: 'activation-1',
        triggeringTaskIds: ['task-a', 'task-b'],
        timestamp: t0,
      },
      {
        id: 'run-1-done',
        type: 'agent.text.done',
        messageId: 'native-assistant-turn-1',
        outputRunId: 'activation-1',
        triggeringTaskIds: ['task-a', 'task-b'],
        timestamp: t1,
      },
      {
        id: 'run-2-start',
        type: 'agent.text.start',
        messageId: 'native-assistant-turn-1',
        outputRunId: 'activation-2',
        triggeringTaskIds: ['task-c'],
        timestamp: t2,
      },
    ])

    expect(state.entries).toMatchObject([
      {
        id: 'run-1-start',
        outputRunId: 'activation-1',
        triggeringTaskIds: ['task-a', 'task-b'],
        status: 'complete',
      },
      {
        id: 'run-2-start',
        outputRunId: 'activation-2',
        triggeringTaskIds: ['task-c'],
        status: 'active',
      },
    ])
  })

  it('deduplicates event ids and ignores progress and Plan events', () => {
    const success: AgentConsoleEvent = {
      id: 'success-1',
      type: 'task.success',
      taskId: 'task-1',
      result: {},
      timestamp: t0,
    }
    const progress: AgentConsoleEvent = {
      id: 'progress-1',
      type: 'task.progress',
      taskId: 'task-1',
      progress: 50,
      message: 'halfway',
      timestamp: t1,
    }
    const roundStart: AgentConsoleEvent = {
      id: 'round-1',
      type: 'plact.round.start',
      messageId: 'agent-1',
      round: 0,
      timestamp: t2,
    }

    let state = applyRuntimeEvent(initialRuntimeTraceState(), success)
    state = applyRuntimeEvent(state, success)
    const unchanged = applyRuntimeEvent(applyRuntimeEvent(state, progress), roundStart)

    expect(unchanged).toEqual(state)
    expect(state.entries).toHaveLength(1)
  })
})
