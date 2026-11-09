import { describe, expect, it } from 'vitest'
import {
  applyRuntimeEvent,
  getAgentDelegationEntryId,
  initialRuntimeTraceState,
  type RuntimeTraceEntry,
  type RuntimeTraceState,
} from '../app/runtimeTraceReducer'
import type {
  TaskProjection,
  TaskProjectionState,
} from '../domain/projection'
import {
  RUNTIME_LANE_HEIGHT,
  RUNTIME_LANE_TOPS,
  RUNTIME_TASK_AXIS_GAP,
  RUNTIME_TASK_AXIS_HEIGHT,
  RUNTIME_TASK_BLOCK_OFFSET,
  RUNTIME_TASK_CONTENT_PADDING,
  buildRuntimeTimeline,
  compressTimelineGapPx,
  projectRuntimeConnector,
  type RuntimeConnector,
} from './runtimeTimeline'

const START = '2026-07-13T08:00:00.000Z'
const START_MS = Date.parse(START)

function at(seconds: number): string {
  return new Date(START_MS + seconds * 1000).toISOString()
}

function trace(entries: RuntimeTraceEntry[]): RuntimeTraceState {
  return { entries }
}

function agentEntry(
  id: string,
  status: RuntimeTraceEntry['status'],
  timestamp: string,
  endTimestamp?: string,
): RuntimeTraceEntry {
  return {
    id,
    kind: 'agent.activity',
    lane: 'agent',
    label: id,
    status,
    timestamp,
    ...(endTimestamp === undefined ? {} : { endTimestamp }),
  }
}

function task(
  taskId: string,
  createdAt: string,
  completedAt?: string,
): TaskProjection {
  return {
    taskId,
    toolName: 'test_tool',
    title: taskId,
    arguments: {},
    status: completedAt === undefined ? 'running' : 'success',
    progress: completedAt === undefined ? 50 : 100,
    trace: [],
    createdAt,
    updatedAt: completedAt ?? createdAt,
    ...(completedAt === undefined ? {} : { completedAt }),
  }
}

function taskState(tasks: TaskProjection[]): TaskProjectionState {
  return {
    byId: Object.fromEntries(tasks.map((item) => [item.taskId, item])),
    order: tasks.map((item) => item.taskId),
  }
}

describe('runtime timeline layout', () => {
  it('draws every triggering Task into the same Agent output run', () => {
    const runtimeTrace = trace([
      {
        id: 'task-a-done',
        kind: 'task.succeeded',
        lane: 'task',
        label: '任务完成',
        status: 'complete',
        timestamp: at(2),
        taskId: 'task-a',
      },
      {
        id: 'task-b-done',
        kind: 'task.succeeded',
        lane: 'task',
        label: '任务完成',
        status: 'complete',
        timestamp: at(3),
        taskId: 'task-b',
      },
      {
        id: 'activation-output',
        kind: 'agent.activity',
        lane: 'agent',
        label: '基于任务结果回复',
        status: 'complete',
        timestamp: at(4),
        endTimestamp: at(5),
        messageId: 'native-assistant-turn-2',
        outputRunId: 'activation-1',
        triggeringTaskIds: ['task-a', 'task-b'],
      },
    ])

    const layout = buildRuntimeTimeline(
      runtimeTrace,
      taskState([task('task-a', at(0), at(2)), task('task-b', at(1), at(3))]),
      START_MS + 60_000,
    )
    const results = layout.connectors.filter(({ kind }) => kind === 'result')

    expect(results).toHaveLength(2)
    expect(results.map(({ taskId }) => taskId).sort()).toEqual(['task-a', 'task-b'])
    expect(results.every(({ relatedEntryIds }) =>
      relatedEntryIds.includes('activation-output'))).toBe(true)
  })

  it('compresses longer gaps monotonically with decelerating growth', () => {
    const oneSecond = compressTimelineGapPx(1_000)
    const eightSeconds = compressTimelineGapPx(8_000)
    const thirtySeconds = compressTimelineGapPx(30_000)
    expect(oneSecond).toBeLessThan(eightSeconds)
    expect(eightSeconds).toBeLessThan(thirtySeconds)
    expect(thirtySeconds - eightSeconds).toBeLessThan(eightSeconds - oneSecond)
  })

  it('maps compressed start anchors and keeps entries visibly wide', () => {
    const layout = buildRuntimeTimeline(trace([
      {
        id: 'user-1',
        kind: 'user.submitted',
        lane: 'user',
        label: '提交请求',
        status: 'submitted',
        timestamp: at(0),
      },
      {
        id: 'agent-1',
        kind: 'agent.activity',
        lane: 'agent',
        label: 'Agent 响应',
        status: 'complete',
        timestamp: at(1),
        endTimestamp: at(2),
      },
    ]), taskState([]), START_MS + 60_000)

    const user = layout.entries.find(({ entry }) => entry.id === 'user-1')
    const agent = layout.entries.find(({ entry }) => entry.id === 'agent-1')

    expect(RUNTIME_LANE_HEIGHT).toBe(68)
    expect(RUNTIME_TASK_AXIS_HEIGHT).toBe(48)
    expect(RUNTIME_TASK_AXIS_GAP).toBe(4)
    expect(RUNTIME_TASK_CONTENT_PADDING).toBe(8)
    expect(RUNTIME_TASK_BLOCK_OFFSET).toBe(10)
    expect(RUNTIME_LANE_TOPS).toEqual({ user: 12, agent: 94, task: 176 })
    expect(agent!.x - user!.x).toBe(compressTimelineGapPx(1_000))
    expect(user!.width).toBe(76)
    expect(agent!.width).toBeCloseTo(76 + 14 * Math.log1p(1_000 / 2_000))
    expect(layout.width).toBe(640)
  })

  it('keeps reducer-ordered Agent cards separated by a 4px gap', () => {
    let runtimeTrace = applyRuntimeEvent(initialRuntimeTraceState(), {
      id: 'task-created-1',
      type: 'task.created',
      taskId: 'task-1',
      toolName: 'test_tool',
      title: '测试任务',
      arguments: {},
      originMessageId: 'agent-1',
      timestamp: at(0),
    })
    runtimeTrace = applyRuntimeEvent(runtimeTrace, {
      id: 'agent-result-start-1',
      type: 'agent.text.start',
      messageId: 'agent-1',
      sourceTaskId: 'task-1',
      originMessageId: 'agent-1',
      timestamp: at(1),
    })
    runtimeTrace = applyRuntimeEvent(runtimeTrace, {
      id: 'agent-result-done-1',
      type: 'agent.text.done',
      messageId: 'agent-1',
      sourceTaskId: 'task-1',
      originMessageId: 'agent-1',
      timestamp: at(2),
    })

    const layout = buildRuntimeTimeline(runtimeTrace, taskState([]), START_MS + 60_000)
    const delegation = layout.entries.find(({ entry }) =>
      entry.id === getAgentDelegationEntryId('agent-1'))!
    const activity = layout.entries.find(({ entry }) =>
      entry.id === 'agent-result-start-1')!

    expect(layout.entries.map(({ entry }) => entry.id)).toEqual([
      getAgentDelegationEntryId('agent-1'),
      'agent-result-start-1',
    ])
    expect(activity.x - (delegation.x + delegation.width)).toBe(4)
  })

  it('packs Agent cards when compressed start anchors overlap', () => {
    const layout = buildRuntimeTimeline(trace([
      agentEntry('first-agent', 'complete', at(0), at(0)),
      agentEntry('second-agent', 'complete', at(3.3), at(3.3)),
    ]), taskState([]), START_MS + 60_000)
    const first = layout.entries.find(({ entry }) => entry.id === 'first-agent')!
    const second = layout.entries.find(({ entry }) => entry.id === 'second-agent')!

    expect(first.width).toBe(76)
    expect(second.width).toBe(76)
    expect(second.x).toBe(96)
    expect(second.x - (first.x + first.width)).toBe(4)
  })

  it('keeps fixed and minimum-width blocks inside a long timeline', () => {
    const layout = buildRuntimeTimeline(trace([
      {
        id: 'anchor',
        kind: 'agent.activity',
        lane: 'agent',
        label: '时间起点',
        status: 'complete',
        timestamp: at(0),
      },
      {
        id: 'end-user',
        kind: 'user.submitted',
        lane: 'user',
        label: '末端提交',
        status: 'submitted',
        timestamp: at(30),
      },
      {
        id: 'end-agent',
        kind: 'agent.activity',
        lane: 'agent',
        label: '末端短响应',
        status: 'complete',
        timestamp: at(29.9),
        endTimestamp: at(30),
      },
    ]), taskState([
      task('end-task', at(29.8), at(29.9)),
    ]), START_MS + 60_000)

    const endUser = layout.entries.find(({ entry }) => entry.id === 'end-user')!
    const endAgent = layout.entries.find(({ entry }) => entry.id === 'end-agent')!
    const endTask = layout.tasks.find(({ task: item }) => item.taskId === 'end-task')!

    expect(endUser.width).toBe(76)
    expect(endAgent.width).toBeCloseTo(76 + 14 * Math.log1p(100 / 2_000))
    expect(endTask.width).toBeCloseTo(104 + 18 * Math.log1p(100 / 5_000))
    for (const block of [endUser, endAgent, endTask]) {
      expect(layout.width).toBeGreaterThanOrEqual(block.x + block.width + 16)
    }
  })

  it.each([
    {
      name: 'invalid terminal agent end',
      runtimeTrace: trace([
        agentEntry('invalid-end-agent', 'complete', at(10), 'not-a-time'),
      ]),
      tasks: taskState([]),
      nowMs: START_MS + 100_000,
      expectedBlockWidth: 76,
      expectedPlayheadX: 16,
    },
    {
      name: 'terminal agent end before start',
      runtimeTrace: trace([
        agentEntry('reverse-end-agent', 'complete', at(10), at(0)),
      ]),
      tasks: taskState([]),
      nowMs: START_MS + 100_000,
      expectedBlockWidth: 76,
      expectedPlayheadX: 16,
    },
    {
      name: 'terminal task end before start',
      runtimeTrace: trace([]),
      tasks: taskState([
        task('reverse-end-task', at(10), at(0)),
      ]),
      nowMs: START_MS + 100_000,
      expectedBlockWidth: 104,
      expectedPlayheadX: 16,
    },
    {
      name: 'active agent now before start',
      runtimeTrace: trace([
        agentEntry('reverse-now-agent', 'active', at(10)),
      ]),
      tasks: taskState([]),
      nowMs: START_MS,
      expectedBlockWidth: 76,
      expectedPlayheadX: 16,
    },
    {
      name: 'active task now before start',
      runtimeTrace: trace([]),
      tasks: taskState([
        task('reverse-now-task', at(10)),
      ]),
      nowMs: START_MS,
      expectedBlockWidth: 104,
      expectedPlayheadX: 16,
    },
    {
      name: 'terminal task without completedAt',
      runtimeTrace: trace([]),
      tasks: taskState([{
        ...task('terminal-without-end', at(10)),
        status: 'success' as const,
        progress: 100,
      }]),
      nowMs: START_MS + 100_000,
      expectedBlockWidth: 104,
      expectedPlayheadX: 16,
    },
    {
      name: 'active agent with inconsistent terminal end',
      runtimeTrace: trace([
        agentEntry('active-agent-with-end', 'active', at(10), at(100)),
      ]),
      tasks: taskState([]),
      nowMs: START_MS + 20_000,
      expectedBlockWidth: 76 + 14 * Math.log1p(10_000 / 2_000),
      expectedPlayheadX: 16 + compressTimelineGapPx(10_000),
    },
    {
      name: 'active task with inconsistent terminal end',
      runtimeTrace: trace([]),
      tasks: taskState([{
        ...task('active-task-with-end', at(10), at(100)),
        status: 'running' as const,
        progress: 50,
      }]),
      nowMs: START_MS + 20_000,
      expectedBlockWidth: 104 + 18 * Math.log1p(10_000 / 5_000),
      expectedPlayheadX: 16 + compressTimelineGapPx(10_000),
    },
  ])('normalizes $name to one effective endpoint', ({
    runtimeTrace,
    tasks,
    nowMs,
    expectedBlockWidth,
    expectedPlayheadX,
  }) => {
    const layout = buildRuntimeTimeline(runtimeTrace, tasks, nowMs)
    const blocks = [
      ...layout.entries.map(({ x, width }) => ({ x, width })),
      ...layout.tasks.map(({ x, width }) => ({ x, width })),
    ]

    expect(blocks).toHaveLength(1)
    expect(blocks[0].x).toBe(16)
    expect(blocks[0].width).toBeCloseTo(expectedBlockWidth)
    expect(layout.playheadX).toBeCloseTo(expectedPlayheadX)
  })

  it('assigns every task a stable axis ordered by creation time', () => {
    const tasks = taskState([
      task('later', at(10), at(11)),
      task('B', at(3), at(6)),
      task('A', at(2), at(7)),
    ])
    const original = structuredClone(tasks)

    const layout = buildRuntimeTimeline(trace([]), tasks, START_MS + 60_000)

    expect(layout.tasks.map(({ task: item }) => item.taskId)).toEqual(['A', 'B', 'later'])
    expect(layout.tasks.map(({ axisIndex }) => axisIndex)).toEqual([0, 1, 2])
    expect(layout.tasks.map(({ axisTop }) => axisTop)).toEqual([8, 60, 112])
    expect(layout.tasks.map(({ contentTop }) => contentTop)).toEqual([18, 70, 122])
    expect(layout.tasks[0].width).toBeCloseTo(104 + 18 * Math.log1p(5_000 / 5_000))
    expect(layout.tasks[1].width).toBeGreaterThan(104)
    expect(layout.taskContentHeight).toBe(168)
    expect(tasks).toEqual(original)
  })

  it('preserves projection order when tasks share a creation timestamp', () => {
    const sameCreatedAt = at(2)
    const initial = taskState([
      task('Z-first', sameCreatedAt),
      task('A-second', sameCreatedAt),
    ])
    const updated: TaskProjectionState = {
      byId: {
        ...initial.byId,
        'A-second': {
          ...initial.byId['A-second'],
          progress: 75,
          updatedAt: at(5),
        },
      },
      order: [...initial.order],
    }

    expect(buildRuntimeTimeline(trace([]), initial, START_MS + 60_000)
      .tasks.map(({ task: item }) => item.taskId)).toEqual(['Z-first', 'A-second'])
    expect(buildRuntimeTimeline(trace([]), updated, START_MS + 60_000)
      .tasks.map(({ task: item }) => item.taskId)).toEqual(['Z-first', 'A-second'])
  })

  it('maps submit, delegation, and result connectors to exact card edges', () => {
    const layout = buildRuntimeTimeline(trace([
      {
        id: 'submit-1',
        kind: 'user.submitted',
        lane: 'user',
        label: '提交',
        status: 'submitted',
        timestamp: at(0),
        messageId: 'agent-main',
      },
      {
        id: 'agent-main-start',
        kind: 'agent.activity',
        lane: 'agent',
        label: '主 Agent',
        status: 'complete',
        timestamp: at(1),
        endTimestamp: at(4),
        messageId: 'agent-main',
      },
      {
        id: getAgentDelegationEntryId('agent-main'),
        kind: 'agent.delegated',
        lane: 'agent',
        label: '发起任务',
        status: 'complete',
        timestamp: at(2),
        endTimestamp: at(2),
        messageId: 'agent-main',
      },
      {
        id: 'delegate-A',
        kind: 'task.delegated',
        lane: 'task',
        label: '委派 A',
        status: 'active',
        timestamp: at(2),
        taskId: 'A',
        originMessageId: 'agent-main',
      },
      {
        id: 'success-B',
        kind: 'task.succeeded',
        lane: 'task',
        label: 'B 完成',
        status: 'complete',
        timestamp: at(6),
        taskId: 'B',
      },
      {
        id: 'agent-result-B',
        kind: 'agent.activity',
        lane: 'agent',
        label: '处理 B 结果',
        status: 'complete',
        timestamp: at(7),
        endTimestamp: at(8),
        messageId: 'agent-result-B',
        sourceTaskId: 'B',
      },
      {
        id: 'delegate-unknown',
        kind: 'task.delegated',
        lane: 'task',
        label: '未知任务委派',
        status: 'active',
        timestamp: at(7),
        taskId: 'unknown',
        originMessageId: 'agent-main',
      },
      {
        id: 'failure-unknown',
        kind: 'task.failed',
        lane: 'task',
        label: '未知任务失败',
        status: 'failed',
        timestamp: at(7),
        taskId: 'unknown',
      },
    ]), taskState([
      task('A', at(2), at(7)),
      task('B', at(3), at(6)),
    ]), START_MS + 60_000)

    const submit = layout.entries.find(({ entry }) => entry.id === 'submit-1')!
    const mainAgent = layout.entries.find(({ entry }) =>
      entry.id === 'agent-main-start')!
    const delegation = layout.entries.find(({ entry }) =>
      entry.id === getAgentDelegationEntryId('agent-main'))!
    const resultAgent = layout.entries.find(({ entry }) =>
      entry.id === 'agent-result-B')!
    const taskA = layout.tasks.find(({ task: item }) => item.taskId === 'A')!
    const taskB = layout.tasks.find(({ task: item }) => item.taskId === 'B')!

    expect(layout.connectors.map(({
      id,
      kind,
      taskId,
      relatedEntryIds,
      from,
      to,
    }) => ({
      id,
      kind,
      taskId,
      relatedEntryIds,
      from,
      to,
    }))).toEqual([
      {
        id: 'submit-1',
        kind: 'submit',
        taskId: undefined,
        relatedEntryIds: ['submit-1', 'agent-main-start'],
        from: { lane: 'user', x: submit.x + submit.width / 2, y: 64 },
        to: { lane: 'agent', x: mainAgent.x + mainAgent.width / 2, y: 110 },
      },
      {
        id: 'delegate-A',
        kind: 'delegate',
        taskId: 'A',
        relatedEntryIds: [getAgentDelegationEntryId('agent-main')],
        from: { lane: 'agent', x: delegation.x + delegation.width / 2, y: 146 },
        to: { lane: 'task', x: taskA.x, y: 194 },
      },
      {
        id: 'success-B',
        kind: 'result',
        taskId: 'B',
        relatedEntryIds: ['agent-result-B'],
        from: { lane: 'task', x: taskB.x + taskB.width, y: 246 },
        to: { lane: 'agent', x: resultAgent.x + resultAgent.width / 2, y: 146 },
      },
    ])
    expect(layout.entries.map(({ entry }) => entry.id)).toEqual([
      'submit-1',
      'agent-main-start',
      getAgentDelegationEntryId('agent-main'),
      'agent-result-B',
    ])
  })

  it('targets the delegation card when submit has no outward agent text yet', () => {
    const delegationId = getAgentDelegationEntryId('agent-main')
    const layout = buildRuntimeTimeline(trace([
      {
        id: 'submit-1',
        kind: 'user.submitted',
        lane: 'user',
        label: '提交',
        status: 'submitted',
        timestamp: at(0),
        messageId: 'agent-main',
      },
      {
        id: delegationId,
        kind: 'agent.delegated',
        lane: 'agent',
        label: '发起任务',
        status: 'complete',
        timestamp: at(1),
        endTimestamp: at(1),
        messageId: 'agent-main',
      },
    ]), taskState([]), START_MS + 60_000)
    const delegation = layout.entries.find(({ entry }) => entry.id === delegationId)!
    const submit = layout.connectors.find(({ kind }) => kind === 'submit')!

    expect(submit.to).toEqual({
      lane: 'agent',
      x: delegation.x + delegation.width / 2,
      y: RUNTIME_LANE_TOPS.agent + 16,
    })
  })

  it('waits for the target card before rendering submit and result connectors', () => {
    const submission: RuntimeTraceEntry = {
      id: 'submit-later',
      kind: 'user.submitted',
      lane: 'user',
      label: '稍后处理',
      status: 'submitted',
      timestamp: at(0),
      messageId: 'agent-main',
    }
    const mainAgent: RuntimeTraceEntry = {
      id: 'agent-main-start',
      kind: 'agent.activity',
      lane: 'agent',
      label: 'Agent 简短回复',
      status: 'complete',
      timestamp: at(1),
      endTimestamp: at(1),
      messageId: 'agent-main',
    }

    expect(buildRuntimeTimeline(
      trace([submission]),
      taskState([]),
      START_MS + 60_000,
    ).connectors).toEqual([])
    expect(buildRuntimeTimeline(
      trace([submission, mainAgent]),
      taskState([]),
      START_MS + 60_000,
    ).connectors.map(({ kind }) => kind)).toEqual(['submit'])

    const taskEntries: RuntimeTraceEntry[] = [
      mainAgent,
      {
        id: 'delegate-A',
        kind: 'task.delegated',
        lane: 'task',
        label: '委派 A',
        status: 'active',
        timestamp: at(2),
        taskId: 'A',
        originMessageId: 'agent-main',
      },
      {
        id: 'success-A',
        kind: 'task.succeeded',
        lane: 'task',
        label: 'A 完成',
        status: 'complete',
        timestamp: at(3),
        taskId: 'A',
      },
    ]
    const tasks = taskState([task('A', at(2), at(3))])

    expect(buildRuntimeTimeline(
      trace(taskEntries),
      tasks,
      START_MS + 60_000,
    ).connectors.map(({ kind }) => kind)).toEqual(['delegate'])
    expect(buildRuntimeTimeline(trace([
      ...taskEntries,
      {
        id: 'agent-result-A',
        kind: 'agent.activity',
        lane: 'agent',
        label: '基于任务结果回复',
        status: 'complete',
        timestamp: at(4),
        endTimestamp: at(4),
        sourceTaskId: 'A',
      },
    ]), tasks, START_MS + 60_000).connectors.map(({ kind }) => kind)).toEqual([
      'delegate',
      'result',
    ])
  })

  it('anchors wide-task delegation at the left edge and results at the right edge', () => {
    const delegationId = getAgentDelegationEntryId('agent-main')
    const layout = buildRuntimeTimeline(trace([
      {
        id: delegationId,
        kind: 'agent.delegated',
        lane: 'agent',
        label: '发起任务',
        status: 'complete',
        timestamp: at(2),
        endTimestamp: at(2),
        messageId: 'agent-main',
      },
      {
        id: 'delegate-wide',
        kind: 'task.delegated',
        lane: 'task',
        label: '委派宽任务',
        status: 'active',
        timestamp: at(2),
        taskId: 'wide',
        originMessageId: 'agent-main',
      },
      {
        id: 'success-wide',
        kind: 'task.succeeded',
        lane: 'task',
        label: '宽任务完成',
        status: 'complete',
        timestamp: at(12),
        taskId: 'wide',
      },
      {
        id: 'agent-result-wide',
        kind: 'agent.activity',
        lane: 'agent',
        label: '处理宽任务结果',
        status: 'complete',
        timestamp: at(13),
        endTimestamp: at(14),
        sourceTaskId: 'wide',
      },
    ]), taskState([
      task('wide', at(2), at(12)),
    ]), START_MS + 60_000)
    const positionedTask = layout.tasks.find(({ task: item }) => item.taskId === 'wide')!
    const delegate = layout.connectors.find(({ kind }) => kind === 'delegate')!
    const result = layout.connectors.find(({ kind }) => kind === 'result')!

    expect(positionedTask.width).toBeGreaterThan(104)
    expect(delegate.to.x).toBe(positionedTask.x)
    expect(result.from.x).toBe(positionedTask.x + positionedTask.width)
  })

  it('offsets multiple delegation starts from the same agent by 8px', () => {
    const layout = buildRuntimeTimeline(trace([
      {
        id: 'agent-main-start',
        kind: 'agent.activity',
        lane: 'agent',
        label: '主 Agent',
        status: 'complete',
        timestamp: at(1),
        endTimestamp: at(4),
        messageId: 'agent-main',
      },
      {
        id: 'delegate-A',
        kind: 'task.delegated',
        lane: 'task',
        label: '委派 A',
        status: 'active',
        timestamp: at(2),
        taskId: 'A',
        originMessageId: 'agent-main',
      },
      {
        id: 'delegate-B',
        kind: 'task.delegated',
        lane: 'task',
        label: '委派 B',
        status: 'active',
        timestamp: at(3),
        taskId: 'B',
        originMessageId: 'agent-main',
      },
    ]), taskState([
      task('A', at(2), at(7)),
      task('B', at(3), at(6)),
    ]), START_MS + 60_000)

    const delegateStarts = layout.connectors
      .filter(({ kind }) => kind === 'delegate')
      .map(({ from }) => from.x)

    const source = layout.entries.find(({ entry }) =>
      entry.id === 'agent-main-start')!
    expect(delegateStarts[1] - delegateStarts[0]).toBeCloseTo(8)
    expect((delegateStarts[0] + delegateStarts[1]) / 2)
      .toBeCloseTo(source.x + source.width / 2)
  })

  it('keeps eighteen delegation starts inside their shared source card', () => {
    const delegatedTasks = Array.from({ length: 18 }, (_, index) =>
      task(`task-${index}`, at(index + 1), at(20)),
    )
    const layout = buildRuntimeTimeline(trace([
      {
        id: 'agent-main-start',
        kind: 'agent.activity',
        lane: 'agent',
        label: '主 Agent',
        status: 'complete',
        timestamp: at(0),
        endTimestamp: at(1),
        messageId: 'agent-main',
      },
      ...delegatedTasks.map((item, index): RuntimeTraceEntry => ({
        id: `delegate-${index}`,
        kind: 'task.delegated',
        lane: 'task',
        label: `委派 ${index}`,
        status: 'active',
        timestamp: at(index + 1),
        taskId: item.taskId,
        originMessageId: 'agent-main',
      })),
    ]), taskState(delegatedTasks), START_MS + 60_000)
    const source = layout.entries.find(({ entry }) => entry.id === 'agent-main-start')!
    const delegateStarts = layout.connectors
      .filter(({ kind }) => kind === 'delegate')
      .map(({ from }) => from.x)

    expect(delegateStarts).toHaveLength(18)
    expect(delegateStarts.every((x) => x >= 0)).toBe(true)
    expect(delegateStarts.every((x) => x >= source.x && x <= source.x + source.width))
      .toBe(true)
  })

  it('selects the first main span and first task-result span from duplicate indexes', () => {
    const layout = buildRuntimeTimeline(trace([
      {
        id: 'submit-shared',
        kind: 'user.submitted',
        lane: 'user',
        label: '提交',
        status: 'submitted',
        timestamp: at(0),
        messageId: 'shared-message',
      },
      {
        id: 'source-span-before-main',
        kind: 'agent.activity',
        lane: 'agent',
        label: '其他任务结果',
        status: 'complete',
        timestamp: at(0.5),
        messageId: 'shared-message',
        sourceTaskId: 'other-task',
      },
      {
        id: 'main-span-first',
        kind: 'agent.activity',
        lane: 'agent',
        label: '主 Agent 1',
        status: 'complete',
        timestamp: at(1),
        messageId: 'shared-message',
      },
      {
        id: 'main-span-second',
        kind: 'agent.activity',
        lane: 'agent',
        label: '主 Agent 2',
        status: 'complete',
        timestamp: at(2),
        messageId: 'shared-message',
      },
      {
        id: 'delegate-B',
        kind: 'task.delegated',
        lane: 'task',
        label: '委派 B',
        status: 'active',
        timestamp: at(3),
        taskId: 'B',
        originMessageId: 'shared-message',
      },
      {
        id: 'success-B',
        kind: 'task.succeeded',
        lane: 'task',
        label: 'B 完成',
        status: 'complete',
        timestamp: at(4),
        taskId: 'B',
      },
      {
        id: 'result-span-first',
        kind: 'agent.activity',
        lane: 'agent',
        label: 'B 结果 1',
        status: 'complete',
        timestamp: at(5),
        sourceTaskId: 'B',
      },
      {
        id: 'result-span-second',
        kind: 'agent.activity',
        lane: 'agent',
        label: 'B 结果 2',
        status: 'complete',
        timestamp: at(6),
        sourceTaskId: 'B',
      },
    ]), taskState([
      task('B', at(3), at(4)),
    ]), START_MS + 60_000)

    const submit = layout.connectors.find(({ kind }) => kind === 'submit')!
    const delegate = layout.connectors.find(({ kind }) => kind === 'delegate')!
    const result = layout.connectors.find(({ kind }) => kind === 'result')!
    const firstMain = layout.entries.find(({ entry }) =>
      entry.id === 'main-span-first')!
    const firstResult = layout.entries.find(({ entry }) =>
      entry.id === 'result-span-first')!
    const positionedTask = layout.tasks[0]

    expect(submit.to.x).toBe(firstMain.x + firstMain.width / 2)
    expect(delegate.from.x).toBe(firstMain.x + firstMain.width / 2)
    expect(delegate.to.x).toBe(positionedTask.x)
    expect(result.from.x).toBe(positionedTask.x + positionedTask.width)
    expect(result.to.x).toBe(firstResult.x + firstResult.width / 2)
  })

  it('does not draw connectors when either endpoint card cannot be resolved', () => {
    const layout = buildRuntimeTimeline(trace([
      agentEntry('unrelated-agent', 'complete', at(0), at(1)),
      {
        id: 'submit-without-message',
        kind: 'user.submitted',
        lane: 'user',
        label: '提交',
        status: 'submitted',
        timestamp: at(1),
      },
      {
        id: 'delegate-without-origin',
        kind: 'task.delegated',
        lane: 'task',
        label: '委派 A',
        status: 'active',
        timestamp: at(2),
        taskId: 'A',
      },
      {
        id: 'success-A',
        kind: 'task.succeeded',
        lane: 'task',
        label: 'A 完成',
        status: 'complete',
        timestamp: at(3),
        taskId: 'A',
      },
    ]), taskState([
      task('A', at(2), at(3)),
    ]), START_MS + 60_000)

    expect(layout.connectors).toEqual([])
  })

  it('projects visible task connectors as cubic curves and drops offscreen ones', () => {
    const layout = buildRuntimeTimeline(trace([
      {
        id: 'agent-main-start',
        kind: 'agent.activity',
        lane: 'agent',
        label: '主 Agent',
        status: 'complete',
        timestamp: at(1),
        endTimestamp: at(4),
        messageId: 'agent-main',
      },
      {
        id: 'delegate-A',
        kind: 'task.delegated',
        lane: 'task',
        label: '委派 A',
        status: 'active',
        timestamp: at(2),
        taskId: 'A',
        originMessageId: 'agent-main',
      },
    ]), taskState([
      task('A', at(2), at(7)),
    ]), START_MS + 60_000)
    const connector = layout.connectors[0]

    const projected = projectRuntimeConnector(connector, {
      taskScrollTop: 10,
      taskViewportHeight: 88,
    })

    expect(projected).toMatchObject({
      from: { lane: 'agent', y: 146 },
      to: { lane: 'task', y: 184 },
      labelY: 165,
    })
    expect(projected!.from.x).toBeCloseTo(
      layout.entries[0].x + layout.entries[0].width / 2,
    )
    expect(projected!.to.x).toBe(layout.tasks[0].x)
    expect(projected!.labelX).toBeCloseTo(
      (projected!.from.x + projected!.to.x) / 2,
    )
    expect(projected!.path).toContain(' C ')
    expect(projected!.path).not.toContain(' L ')
    expect(projectRuntimeConnector(connector, {
      taskScrollTop: 100,
      taskViewportHeight: 88,
    })).toBeUndefined()
  })

  it.each([
    { name: 'above top', projectedTaskY: 176 - 0.001, visible: false },
    { name: 'at top', projectedTaskY: 176, visible: true },
    { name: 'at bottom', projectedTaskY: 264, visible: true },
    { name: 'below bottom', projectedTaskY: 264 + 0.001, visible: false },
  ])('applies inclusive task viewport boundaries $name', ({
    projectedTaskY,
    visible,
  }) => {
    const taskY = 300
    const taskScrollTop = taskY - projectedTaskY
    const delegate: RuntimeConnector = {
      id: 'delegate-boundary',
      kind: 'delegate',
      taskId: 'A',
      relatedEntryIds: [],
      from: { lane: 'agent', x: 80, y: 193 },
      to: { lane: 'task', x: 140, y: taskY },
    }
    const result: RuntimeConnector = {
      id: 'result-boundary',
      kind: 'result',
      taskId: 'A',
      relatedEntryIds: [],
      from: { lane: 'task', x: 140, y: taskY },
      to: { lane: 'agent', x: 200, y: 193 },
    }
    const options = { taskScrollTop, taskViewportHeight: 88 }

    expect(projectRuntimeConnector(delegate, options) !== undefined).toBe(visible)
    expect(projectRuntimeConnector(result, options) !== undefined).toBe(visible)
  })

  it('drops entries and tasks whose start timestamps are invalid', () => {
    const layout = buildRuntimeTimeline(trace([
      {
        id: 'invalid-entry',
        kind: 'agent.activity',
        lane: 'agent',
        label: '非法时间',
        status: 'complete',
        timestamp: 'not-a-time',
      },
      {
        id: 'valid-entry',
        kind: 'user.submitted',
        lane: 'user',
        label: '合法时间',
        status: 'submitted',
        timestamp: at(0),
      },
    ]), taskState([
      task('invalid-task', 'not-a-time', at(2)),
      task('valid-task', at(1), at(2)),
    ]), START_MS + 60_000)

    expect(layout.entries.map(({ entry }) => entry.id)).toEqual(['valid-entry'])
    expect(layout.tasks.map(({ task: item }) => item.taskId)).toEqual(['valid-task'])
  })

  it('does not extend a settled historical timeline to wall-clock now', () => {
    const historicalTrace = trace([
      {
        id: 'user-1',
        kind: 'user.submitted',
        lane: 'user',
        label: '提交',
        status: 'submitted',
        timestamp: at(0),
      },
      {
        id: 'agent-1',
        kind: 'agent.activity',
        lane: 'agent',
        label: '完成',
        status: 'complete',
        timestamp: at(1),
        endTimestamp: at(2),
      },
    ])
    const settledTasks = taskState([task('done', at(3), at(4))])

    const near = buildRuntimeTimeline(historicalTrace, settledTasks, START_MS + 10_000)
    const far = buildRuntimeTimeline(historicalTrace, settledTasks, START_MS + 86_400_000)

    expect(far).toEqual(near)
    expect(far.playheadX).toBeCloseTo(
      16 +
      compressTimelineGapPx(1_000) +
      compressTimelineGapPx(2_000) +
      compressTimelineGapPx(1_000),
    )
    expect(far.width).toBe(640)
  })

  it('extends active agent and task spans to now', () => {
    const layout = buildRuntimeTimeline(trace([
      {
        id: 'user-1',
        kind: 'user.submitted',
        lane: 'user',
        label: '提交',
        status: 'submitted',
        timestamp: at(0),
      },
      {
        id: 'agent-active',
        kind: 'agent.activity',
        lane: 'agent',
        label: '处理中',
        status: 'active',
        timestamp: at(1),
      },
    ]), taskState([
      task('task-active', at(2)),
    ]), START_MS + 10_000)

    expect(layout.playheadX).toBeCloseTo(
      16 +
      compressTimelineGapPx(1_000) +
      compressTimelineGapPx(1_000) +
      compressTimelineGapPx(8_000),
    )
    expect(layout.entries.find(({ entry }) => entry.id === 'agent-active')!.width)
      .toBeCloseTo(76 + 14 * Math.log1p(9_000 / 2_000))
    expect(layout.tasks[0].width)
      .toBeCloseTo(104 + 18 * Math.log1p(8_000 / 5_000))
  })

  it('scales task widths logarithmically with progressively smaller growth', () => {
    const widthForDuration = (seconds: number) => buildRuntimeTimeline(
      trace([]),
      taskState([task(`task-${seconds}`, at(0), at(seconds))]),
      START_MS + seconds * 1000,
    ).tasks[0].width

    const width5 = widthForDuration(5)
    const width10 = widthForDuration(10)
    const width20 = widthForDuration(20)
    const width30 = widthForDuration(30)
    const width40 = widthForDuration(40)

    expect(width5).toBeCloseTo(104 + 18 * Math.log1p(5_000 / 5_000))
    expect(width10).toBeGreaterThan(width5)
    expect(width10).toBeLessThan(300)
    expect(width20).toBeGreaterThan(width10)
    expect(width20).toBeLessThan(600)
    expect(width30 - width20).toBeLessThan(width20 - width10)
    expect(width40 - width30).toBeLessThan(width30 - width20)
  })

  it('compresses task widths independently from cumulative start anchors', () => {
    const layout = buildRuntimeTimeline(
      trace([]),
      taskState([
        task('early-long-task', at(0), at(20)),
        task('late-long-task', at(30), at(50)),
      ]),
      START_MS + 50_000,
    )
    const early = layout.tasks.find(({ task: item }) =>
      item.taskId === 'early-long-task')!
    const late = layout.tasks.find(({ task: item }) =>
      item.taskId === 'late-long-task')!

    expect(early.width).toBe(late.width)
    expect(late.x).toBeCloseTo(16 + compressTimelineGapPx(30_000))
    expect(layout.playheadX).toBeCloseTo(
      16 + compressTimelineGapPx(30_000) + compressTimelineGapPx(20_000),
    )
  })
})
