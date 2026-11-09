import {
  getAgentDelegationEntryId,
  type RuntimeLane,
  type RuntimeTraceEntry,
  type RuntimeTraceState,
} from '../app/runtimeTraceReducer'
import {
  getTaskList,
  type TaskProjection,
  type TaskProjectionState,
} from '../domain/projection'

export const RUNTIME_LANE_HEIGHT = 68
export const RUNTIME_TASK_AXIS_HEIGHT = 48
export const RUNTIME_TASK_AXIS_GAP = 4
export const RUNTIME_TASK_CONTENT_PADDING = 8
export const RUNTIME_TASK_BLOCK_OFFSET = 10
export const RUNTIME_LANE_TOPS: Record<RuntimeLane, number> = {
  user: 12,
  agent: 94,
  task: 176,
}

const SHORT_GAP_MS = 1_500
const SHORT_GAP_PX_PER_MS = 0.008
const LONG_GAP_LOG_SCALE_PX = 8
const TRACK_PADDING = 16
const MIN_TRACK_WIDTH = 640
const USER_ENTRY_WIDTH = 76
const AGENT_ENTRY_MIN_WIDTH = 76
const ENTRY_GAP = 4
const TASK_MIN_WIDTH = 104
const DELEGATE_SOURCE_GAP = 8
const RUNTIME_ENTRY_TOP = 16
const RUNTIME_ENTRY_HEIGHT = 36
const USER_GAP_MARKER_THRESHOLD_MS = 8_000

export function compressTimelineGapPx(gapMs: number): number {
  const safeGapMs = Math.max(0, gapMs)
  if (safeGapMs <= SHORT_GAP_MS) {
    return safeGapMs * SHORT_GAP_PX_PER_MS
  }
  return SHORT_GAP_MS * SHORT_GAP_PX_PER_MS +
    LONG_GAP_LOG_SCALE_PX * Math.log1p(
      (safeGapMs - SHORT_GAP_MS) / SHORT_GAP_MS,
    )
}

function getDurationWidth(
  minimumWidth: number,
  durationMs: number,
  scaleMs: number,
  scalePx: number,
): number {
  return minimumWidth + scalePx * Math.log1p(
    Math.max(0, durationMs) / scaleMs,
  )
}

export interface PositionedRuntimeEntry {
  entry: RuntimeTraceEntry
  x: number
  width: number
}

export interface PositionedRuntimeTask {
  task: TaskProjection
  x: number
  width: number
  axisIndex: number
  axisTop: number
  contentTop: number
}

export interface RuntimeConnectorPoint {
  lane: RuntimeLane
  x: number
  y: number
}

export interface RuntimeConnector {
  id: string
  kind: 'submit' | 'delegate' | 'result'
  relatedEntryIds: string[]
  taskId?: string
  from: RuntimeConnectorPoint
  to: RuntimeConnectorPoint
}

export interface RuntimeUserGap {
  id: string
  entryId: string
  x: number
  durationMs: number
}

export interface ProjectedRuntimeConnector extends RuntimeConnector {
  path: string
  labelX: number
  labelY: number
}

export interface RuntimeTimelineLayout {
  width: number
  playheadX: number
  taskContentHeight: number
  entries: PositionedRuntimeEntry[]
  tasks: PositionedRuntimeTask[]
  userGaps: RuntimeUserGap[]
  connectors: RuntimeConnector[]
}

interface TimedEntry {
  entry: RuntimeTraceEntry
  startMs: number
  effectiveEndMs: number
}

interface TimedTask {
  task: TaskProjection
  startMs: number
  effectiveEndMs: number
  orderIndex: number
}

interface ConnectorCandidate {
  connector: RuntimeConnector
  delegateSourceId?: string
  sourceMinX?: number
  sourceMaxX?: number
}

function isActiveTask(task: TaskProjection): boolean {
  return task.status === 'pending' ||
    task.status === 'running' ||
    task.status === 'cancelling'
}

function getEffectiveEndMs(
  startMs: number,
  rawEndMs: number | undefined,
  active: boolean,
  nowMs: number,
): number {
  const endMs = active ? nowMs : rawEndMs
  return endMs === undefined || !Number.isFinite(endMs)
    ? startMs
    : Math.max(startMs, endMs)
}

function createConnector(
  id: string,
  kind: RuntimeConnector['kind'],
  from: RuntimeConnectorPoint,
  to: RuntimeConnectorPoint,
  relatedEntryIds: string[],
  taskId?: string,
): RuntimeConnector {
  return {
    id,
    kind,
    relatedEntryIds,
    ...(taskId === undefined ? {} : { taskId }),
    from,
    to,
  }
}

export function projectRuntimeConnector(
  connector: RuntimeConnector,
  {
    taskScrollTop,
    taskViewportHeight,
  }: {
    taskScrollTop: number
    taskViewportHeight: number
  },
): ProjectedRuntimeConnector | undefined {
  const projectPoint = (point: RuntimeConnectorPoint): RuntimeConnectorPoint =>
    point.lane === 'task'
      ? { ...point, y: point.y - taskScrollTop }
      : point
  const from = projectPoint(connector.from)
  const to = projectPoint(connector.to)
  const taskPoint = from.lane === 'task'
    ? from
    : to.lane === 'task'
      ? to
      : undefined
  if (
    taskPoint !== undefined &&
    (taskPoint.y < RUNTIME_LANE_TOPS.task ||
      taskPoint.y > RUNTIME_LANE_TOPS.task + taskViewportHeight)
  ) {
    return undefined
  }

  const dy = to.y - from.y
  const direction = dy < 0 ? -1 : 1
  const bend = Math.min(96, Math.max(32, Math.abs(dy) * 0.45))
  const control1 = { x: from.x, y: from.y + direction * bend }
  const control2 = { x: to.x, y: to.y - direction * bend }
  const cubicMidpoint = (start: number, first: number, second: number, end: number) =>
    start / 8 + 3 * first / 8 + 3 * second / 8 + end / 8

  return {
    ...connector,
    from,
    to,
    path: `M ${from.x} ${from.y} C ${control1.x} ${control1.y} ${control2.x} ${control2.y} ${to.x} ${to.y}`,
    labelX: cubicMidpoint(from.x, control1.x, control2.x, to.x),
    labelY: cubicMidpoint(from.y, control1.y, control2.y, to.y),
  }
}

export function buildRuntimeTimeline(
  trace: RuntimeTraceState,
  taskState: TaskProjectionState,
  nowMs: number,
): RuntimeTimelineLayout {
  const timedEntries = trace.entries.flatMap((entry): TimedEntry[] => {
    const startMs = Date.parse(entry.timestamp)
    if (!Number.isFinite(startMs)) {
      return []
    }
    const parsedEndMs = entry.endTimestamp === undefined
      ? undefined
      : Date.parse(entry.endTimestamp)
    return [{
      entry,
      startMs,
      effectiveEndMs: getEffectiveEndMs(
        startMs,
        parsedEndMs,
        entry.lane === 'agent' && entry.status === 'active',
        nowMs,
      ),
    }]
  })
  const timedTasks = getTaskList(taskState)
    .flatMap((task, orderIndex): TimedTask[] => {
      const startMs = Date.parse(task.createdAt)
      if (!Number.isFinite(startMs)) {
        return []
      }
      const parsedEndMs = task.completedAt === undefined
        ? undefined
        : Date.parse(task.completedAt)
      return [{
        task,
        startMs,
        orderIndex,
        effectiveEndMs: getEffectiveEndMs(
          startMs,
          parsedEndMs,
          isActiveTask(task),
          nowMs,
        ),
      }]
    })
    .sort((left, right) =>
      left.startMs - right.startMs || left.orderIndex - right.orderIndex,
    )

  const timelineBounds = [
    ...timedEntries.flatMap(({ startMs, effectiveEndMs }) =>
      [startMs, effectiveEndMs],
    ),
    ...timedTasks.flatMap(({ startMs, effectiveEndMs }) =>
      [startMs, effectiveEndMs],
    ),
  ]
  const timelineStartMs = timelineBounds.length === 0 ? 0 : Math.min(...timelineBounds)
  const timelineEndMs = timelineBounds.length === 0 ? 0 : Math.max(...timelineBounds)
  const anchors = Array.from(new Set([
    ...timedEntries.map(({ startMs }) => startMs),
    ...timedTasks.map(({ startMs }) => startMs),
    timelineStartMs,
    timelineEndMs,
  ])).sort((left, right) => left - right)
  const xByTime = new Map<number, number>()
  let nextX = TRACK_PADDING
  anchors.forEach((timeMs, index) => {
    if (index > 0) nextX += compressTimelineGapPx(timeMs - anchors[index - 1])
    xByTime.set(timeMs, nextX)
  })
  const xForTime = (timeMs: number): number => xByTime.get(timeMs) ?? TRACK_PADDING

  const rawEntries = timedEntries
    .filter(({ entry }) => entry.lane === 'user' || entry.lane === 'agent')
    .map(({ entry, startMs, effectiveEndMs }): PositionedRuntimeEntry => {
      return {
        entry,
        x: xForTime(startMs),
        width: entry.lane === 'user'
          ? USER_ENTRY_WIDTH
          : getDurationWidth(
              AGENT_ENTRY_MIN_WIDTH,
              effectiveEndMs - startMs,
              2_000,
              14,
            ),
      }
    })
  const positionedEntries = new Map<number, PositionedRuntimeEntry>()
  const entryLanes = ['user', 'agent'] as const
  entryLanes.forEach((lane) => {
    let previousRight = Number.NEGATIVE_INFINITY
    rawEntries
      .map((positioned, originalIndex) => ({ positioned, originalIndex }))
      .filter(({ positioned }) => positioned.entry.lane === lane)
      .sort((left, right) =>
        left.positioned.x - right.positioned.x ||
        left.originalIndex - right.originalIndex,
      )
      .forEach(({ positioned, originalIndex }) => {
        const minimumX = previousRight + ENTRY_GAP
        const x = positioned.x < minimumX
          ? minimumX
          : positioned.x
        positionedEntries.set(originalIndex, { ...positioned, x })
        previousRight = x + positioned.width
      })
  })
  const entries = rawEntries.map((positioned, originalIndex) =>
    positionedEntries.get(originalIndex) ?? positioned,
  )
  const entryStartMsById = new Map(timedEntries.map(({ entry, startMs }) =>
    [entry.id, startMs],
  ))
  const entryById = new Map(entries.map((positioned) => [positioned.entry.id, positioned]))
  const chronologicalUsers = timedEntries
    .filter(({ entry }) => entry.kind === 'user.submitted')
    .sort((left, right) => left.startMs - right.startMs)
  const userGaps = chronologicalUsers.flatMap((current, index): RuntimeUserGap[] => {
    if (index === 0) return []
    const durationMs = current.startMs - chronologicalUsers[index - 1].startMs
    const positioned = entryById.get(current.entry.id)
    if (durationMs <= USER_GAP_MARKER_THRESHOLD_MS || positioned === undefined) {
      return []
    }
    return [{
      id: `user-gap-${current.entry.id}`,
      entryId: current.entry.id,
      x: positioned.x,
      durationMs,
    }]
  })

  const tasks = timedTasks.map(({
    task,
    startMs,
    effectiveEndMs,
  }, axisIndex): PositionedRuntimeTask => {
    const x = xForTime(startMs)
    const width = getDurationWidth(
      TASK_MIN_WIDTH,
      effectiveEndMs - startMs,
      5_000,
      18,
    )
    const axisTop = RUNTIME_TASK_CONTENT_PADDING +
      axisIndex * (RUNTIME_TASK_AXIS_HEIGHT + RUNTIME_TASK_AXIS_GAP)
    const contentTop = axisTop + RUNTIME_TASK_BLOCK_OFFSET
    return {
      task,
      x,
      width,
      axisIndex,
      axisTop,
      contentTop,
    }
  })

  const taskById = new Map(tasks.map((positioned) => [positioned.task.taskId, positioned]))
  const firstAgentByMessageId = new Map<string, PositionedRuntimeEntry>()
  const mainAgentByMessageId = new Map<string, PositionedRuntimeEntry>()
  const firstAgentByTriggeringTaskId = new Map<string, PositionedRuntimeEntry>()
  entries.forEach((positioned) => {
    const { entry } = positioned
    if (entry.lane !== 'agent') return
    const triggeringTaskIds = entry.triggeringTaskIds
      ?? (entry.sourceTaskId === undefined ? [] : [entry.sourceTaskId])
    if (entry.messageId !== undefined) {
      if (!firstAgentByMessageId.has(entry.messageId)) {
        firstAgentByMessageId.set(entry.messageId, positioned)
      }
      if (
        triggeringTaskIds.length === 0 &&
        entry.sourceTaskId === undefined &&
        !mainAgentByMessageId.has(entry.messageId)
      ) {
        mainAgentByMessageId.set(entry.messageId, positioned)
      }
    }
    triggeringTaskIds.forEach((taskId) => {
      if (!firstAgentByTriggeringTaskId.has(taskId)) {
        firstAgentByTriggeringTaskId.set(taskId, positioned)
      }
    })
  })
  const findAgentByMessageId = (messageId: string | undefined) =>
    messageId === undefined
      ? undefined
      : mainAgentByMessageId.get(messageId) ?? firstAgentByMessageId.get(messageId)
  const findAgentBySourceTaskId = (taskId: string) =>
    firstAgentByTriggeringTaskId.get(taskId)
  const entryCenterX = ({ x, width }: PositionedRuntimeEntry) => x + width / 2
  const entryTopY = ({ entry }: PositionedRuntimeEntry) =>
    RUNTIME_LANE_TOPS[entry.lane] + RUNTIME_ENTRY_TOP
  const entryBottomY = (positionedEntry: PositionedRuntimeEntry) =>
    entryTopY(positionedEntry) + RUNTIME_ENTRY_HEIGHT
  const taskTopPoint = (
    positionedTask: PositionedRuntimeTask,
    edge: 'start' | 'end',
  ): RuntimeConnectorPoint => ({
    lane: 'task',
    x: positionedTask.x + (edge === 'end' ? positionedTask.width : 0),
    y: RUNTIME_LANE_TOPS.task + positionedTask.contentTop,
  })
  const connectorCandidates = timedEntries.flatMap(({
    entry,
  }): ConnectorCandidate[] => {
    if (entry.kind === 'user.submitted') {
      const positionedUser = entryById.get(entry.id)
      const targetAgent = findAgentByMessageId(entry.messageId)
      if (positionedUser === undefined || targetAgent === undefined) return []
      const from: RuntimeConnectorPoint = {
        lane: 'user',
        x: entryCenterX(positionedUser),
        y: entryBottomY(positionedUser),
      }
      const to: RuntimeConnectorPoint = {
        lane: 'agent',
        x: entryCenterX(targetAgent),
        y: entryTopY(targetAgent),
      }
      return [{
        connector: createConnector(
          entry.id,
          'submit',
          from,
          to,
          [positionedUser.entry.id, targetAgent.entry.id],
        ),
      }]
    }
    if (entry.kind !== 'task.delegated' && entry.kind !== 'task.succeeded') {
      return []
    }
    const positionedTask = entry.taskId === undefined
      ? undefined
      : taskById.get(entry.taskId)
    if (positionedTask === undefined) {
      return []
    }
    if (entry.kind === 'task.delegated') {
      const taskPoint = taskTopPoint(positionedTask, 'start')
      const sourceAgent = entryById.get(getAgentDelegationEntryId(
        entry.conversationTurnId ?? entry.originMessageId ?? entry.id,
      )) ?? findAgentByMessageId(
        entry.conversationTurnId
          ?? entry.originMessageId
          ?? positionedTask.task.conversationTurnId
          ?? positionedTask.task.originMessageId,
      )
      if (sourceAgent === undefined) return []
      const from: RuntimeConnectorPoint = {
        lane: 'agent',
        x: entryCenterX(sourceAgent),
        y: entryBottomY(sourceAgent),
      }
      return [{
        connector: createConnector(
          entry.id,
          'delegate',
          from,
          taskPoint,
          [sourceAgent.entry.id],
          positionedTask.task.taskId,
        ),
        delegateSourceId: sourceAgent.entry.id,
        sourceMinX: sourceAgent.x,
        sourceMaxX: sourceAgent.x + sourceAgent.width,
      }]
    }

    const targetAgent = findAgentBySourceTaskId(positionedTask.task.taskId)
    if (targetAgent === undefined) return []
    const taskPoint = taskTopPoint(positionedTask, 'end')
    const to: RuntimeConnectorPoint = {
      lane: 'agent',
      x: entryCenterX(targetAgent),
      y: entryBottomY(targetAgent),
    }
    return [{
      connector: createConnector(
        entry.id,
        'result',
        taskPoint,
        to,
        [targetAgent.entry.id],
        positionedTask.task.taskId,
      ),
    }]
  })

  const delegateGroups = new Map<string, number[]>()
  connectorCandidates.forEach(({ delegateSourceId }, index) => {
    if (delegateSourceId === undefined) return
    const indexes = delegateGroups.get(delegateSourceId) ?? []
    indexes.push(index)
    delegateGroups.set(delegateSourceId, indexes)
  })
  delegateGroups.forEach((indexes) => {
    const firstCandidate = connectorCandidates[indexes[0]]
    const sourceMinX = firstCandidate.sourceMinX!
    const sourceMaxX = firstCandidate.sourceMaxX!
    const spacing = indexes.length === 1
      ? 0
      : Math.min(DELEGATE_SOURCE_GAP, (sourceMaxX - sourceMinX) / (indexes.length - 1))
    const sourceCenterX = (sourceMinX + sourceMaxX) / 2
    indexes.forEach((candidateIndex, indexWithinGroup) => {
      const candidate = connectorCandidates[candidateIndex]
      const from = {
        ...candidate.connector.from,
        x: Math.min(
          sourceMaxX,
          Math.max(
            sourceMinX,
            sourceCenterX + (indexWithinGroup - (indexes.length - 1) / 2) * spacing,
          ),
        ),
      }
      connectorCandidates[candidateIndex] = {
        ...candidate,
        connector: { ...candidate.connector, from },
      }
    })
  })
  const connectors = connectorCandidates.map(({ connector }) => connector)

  const taskCount = tasks.length
  const taskContentHeight = 2 * RUNTIME_TASK_CONTENT_PADDING +
    taskCount * RUNTIME_TASK_AXIS_HEIGHT +
    Math.max(0, taskCount - 1) * RUNTIME_TASK_AXIS_GAP
  const packingDisplacement = entries.reduce((maximum, positioned) => {
    const startMs = entryStartMsById.get(positioned.entry.id)
    if (startMs === undefined) return maximum
    return Math.max(maximum, positioned.x - xForTime(startMs))
  }, 0)
  const rawPlayheadX = xForTime(timelineEndMs)
  const playheadX = rawPlayheadX + packingDisplacement
  const width = Math.max(
    MIN_TRACK_WIDTH,
    playheadX + TRACK_PADDING,
    ...entries.map(({ x, width: entryWidth }) => x + entryWidth + TRACK_PADDING),
    ...tasks.map(({ x, width: taskWidth }) => x + taskWidth + TRACK_PADDING),
    ...connectors.flatMap(({ from, to }) => [
      from.x + TRACK_PADDING,
      to.x + TRACK_PADDING,
    ]),
  )

  return {
    width,
    playheadX,
    taskContentHeight,
    entries,
    tasks,
    userGaps,
    connectors,
  }
}
