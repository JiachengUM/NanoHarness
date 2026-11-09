import type { AgentConsoleEvent } from '../domain/events'

export type RuntimeLane = 'user' | 'agent' | 'task'

export type RuntimeTraceKind =
  | 'user.submitted'
  | 'agent.activity'
  | 'agent.delegated'
  | 'task.delegated'
  | 'task.succeeded'
  | 'task.failed'
  | 'task.cancel.requested'
  | 'task.cancelled'

export type RuntimeTraceStatus =
  | 'submitted'
  | 'active'
  | 'complete'
  | 'interrupted'
  | 'failed'
  | 'cancelling'
  | 'cancelled'

export interface RuntimeTraceEntry {
  id: string
  kind: RuntimeTraceKind
  lane: RuntimeLane
  label: string
  status: RuntimeTraceStatus
  timestamp: string
  endTimestamp?: string
  terminalEventId?: string
  messageId?: string
  taskId?: string
  originMessageId?: string
  sourceTaskId?: string
  conversationTurnId?: string
  outputRunId?: string
  triggeringTaskIds?: string[]
}

export interface RuntimeTraceState {
  entries: RuntimeTraceEntry[]
}

export interface RuntimeSubmission {
  input: string
  userMessageId: string
  assistantMessageId: string
  timestamp: string
}

export interface RuntimeSubmissionFailure {
  userMessageId: string
  assistantMessageId: string
  timestamp: string
}

type AgentTextEvent = Extract<
  AgentConsoleEvent,
  { type: 'agent.text.start' | 'agent.text.delta' | 'agent.text.done' }
>

type TaskCreatedEvent = Extract<AgentConsoleEvent, { type: 'task.created' }>

type TaskEvent = Extract<AgentConsoleEvent, { taskId: string }>

function compareRuntimeTimestamps(left: string, right: string): number {
  const millisecondDifference = Date.parse(left) - Date.parse(right)
  if (millisecondDifference !== 0) {
    return millisecondDifference
  }
  return left < right ? -1 : left > right ? 1 : 0
}

function getAgentActivityLabel(triggeringTaskIds: string[]): string {
  return triggeringTaskIds.length === 0
    ? 'Agent 简短回复'
    : '基于任务结果回复'
}

function triggeringTaskIdsFor(event: AgentTextEvent): string[] {
  return event.triggeringTaskIds
    ?? (event.sourceTaskId === undefined ? [] : [event.sourceTaskId])
}

function sameTaskIds(left: string[] | undefined, right: string[]): boolean {
  return (left ?? []).length === right.length
    && (left ?? []).every((taskId, index) => taskId === right[index])
}

export function initialRuntimeTraceState(): RuntimeTraceState {
  return { entries: [] }
}

export function getAgentDelegationEntryId(groupId: string): string {
  return `agent-delegated:${groupId}`
}

function recordSubmission(
  state: RuntimeTraceState,
  submission: RuntimeSubmission,
  interruptActiveAgent: boolean,
): RuntimeTraceState {
  const id = `user:${submission.userMessageId}`
  if (state.entries.some((entry) => entry.id === id)) {
    return state
  }

  const existingEntries = interruptActiveAgent
    ? state.entries.map((entry) => {
        if (
          entry.kind === 'agent.activity'
          && entry.status === 'active'
          && (entry.triggeringTaskIds?.length ?? 0) === 0
          && entry.sourceTaskId === undefined
        ) {
          return {
            ...entry,
            status: 'interrupted' as const,
            endTimestamp: submission.timestamp,
          }
        }
        return entry
      })
    : state.entries

  return {
    entries: [
      ...existingEntries,
      {
        id,
        kind: 'user.submitted',
        lane: 'user',
        label: submission.input,
        status: 'submitted',
        timestamp: submission.timestamp,
        messageId: submission.assistantMessageId,
      },
    ],
  }
}

export function recordRuntimeSubmission(
  state: RuntimeTraceState,
  submission: RuntimeSubmission,
): RuntimeTraceState {
  return recordSubmission(state, submission, true)
}

export function recordQueuedRuntimeSubmission(
  state: RuntimeTraceState,
  submission: RuntimeSubmission,
): RuntimeTraceState {
  return recordSubmission(state, submission, false)
}

export function markRuntimeSubmissionFailed(
  state: RuntimeTraceState,
  failure: RuntimeSubmissionFailure,
): RuntimeTraceState {
  const index = state.entries.findIndex(
    (entry) =>
      entry.id === `user:${failure.userMessageId}`
      && entry.kind === 'user.submitted'
      && entry.messageId === failure.assistantMessageId,
  )
  if (index < 0 || state.entries[index].status === 'failed') {
    return state
  }

  return {
    entries: state.entries.map((entry, entryIndex) =>
      entryIndex === index
        ? {
            ...entry,
            status: 'failed' as const,
            endTimestamp: failure.timestamp,
          }
        : entry,
    ),
  }
}

function applyAgentTextEvent(
  state: RuntimeTraceState,
  event: AgentTextEvent,
): RuntimeTraceState {
  if (state.entries.some(
    (entry) => entry.id === event.id || entry.terminalEventId === event.id,
  )) {
    return state
  }

  const outputRunId = event.outputRunId ?? event.messageId
  const eventTriggeringTaskIds = triggeringTaskIdsFor(event)
  const eventConversationTurnId =
    event.conversationTurnId ?? event.originMessageId

  let latestIndex = -1
  for (let index = state.entries.length - 1; index >= 0; index -= 1) {
    const entry = state.entries[index]
    if (
      entry.kind === 'agent.activity'
      && (entry.outputRunId ?? entry.messageId) === outputRunId
    ) {
      latestIndex = index
      break
    }
  }

  const appendActivity = (): RuntimeTraceState => ({
    entries: [...state.entries, {
      id: event.id,
      kind: 'agent.activity',
      lane: 'agent',
      label: getAgentActivityLabel(eventTriggeringTaskIds),
      status: event.type === 'agent.text.done' ? 'complete' : 'active',
      timestamp: event.timestamp,
      messageId: event.messageId,
      outputRunId,
      triggeringTaskIds: eventTriggeringTaskIds,
      ...(eventConversationTurnId === undefined
        ? {}
        : { conversationTurnId: eventConversationTurnId }),
      ...(event.type === 'agent.text.done'
        ? { endTimestamp: event.timestamp, terminalEventId: event.id }
        : {}),
      ...(event.originMessageId !== undefined
        ? { originMessageId: event.originMessageId }
        : {}),
      ...(event.sourceTaskId !== undefined
        ? { sourceTaskId: event.sourceTaskId }
        : {}),
    }],
  })

  if (latestIndex < 0) {
    return appendActivity()
  }

  const latest = state.entries[latestIndex]
  if (latest.status === 'interrupted') {
    return state
  }

  const isEarlierStart =
    event.type === 'agent.text.start' &&
    compareRuntimeTimestamps(event.timestamp, latest.timestamp) < 0
  const sourceTaskId = event.sourceTaskId ?? latest.sourceTaskId
  const originMessageId = event.originMessageId ?? latest.originMessageId
  const conversationTurnId =
    event.conversationTurnId ?? latest.conversationTurnId ?? originMessageId
  const triggeringTaskIds = (
    event.triggeringTaskIds !== undefined || event.sourceTaskId !== undefined
  )
    ? eventTriggeringTaskIds
    : (latest.triggeringTaskIds ?? eventTriggeringTaskIds)

  if (latest.status === 'active') {
    if (
      event.type !== 'agent.text.start' &&
      compareRuntimeTimestamps(event.timestamp, latest.timestamp) < 0
    ) {
      return state
    }

    const relationshipChanged =
      sourceTaskId !== latest.sourceTaskId ||
      originMessageId !== latest.originMessageId ||
      conversationTurnId !== latest.conversationTurnId ||
      !sameTaskIds(latest.triggeringTaskIds, triggeringTaskIds)
    if (!isEarlierStart && event.type !== 'agent.text.done' && !relationshipChanged) {
      return state
    }

    const next: RuntimeTraceEntry = {
      ...latest,
      label: getAgentActivityLabel(triggeringTaskIds),
      outputRunId,
      triggeringTaskIds,
      ...(conversationTurnId === undefined ? {} : { conversationTurnId }),
      ...(isEarlierStart ? { id: event.id, timestamp: event.timestamp } : {}),
      ...(event.originMessageId !== undefined
        ? { originMessageId: event.originMessageId }
        : {}),
      ...(event.sourceTaskId !== undefined
        ? { sourceTaskId: event.sourceTaskId }
        : {}),
      ...(event.type === 'agent.text.done'
        ? {
            status: 'complete' as const,
            endTimestamp: event.timestamp,
            terminalEventId: event.id,
          }
        : {}),
    }

    return {
      entries: state.entries.map((entry, index) =>
        index === latestIndex ? next : entry,
      ),
    }
  }

  if (isEarlierStart) {
    const next: RuntimeTraceEntry = {
      ...latest,
      id: event.id,
      label: getAgentActivityLabel(triggeringTaskIds),
      outputRunId,
      triggeringTaskIds,
      ...(conversationTurnId === undefined ? {} : { conversationTurnId }),
      timestamp: event.timestamp,
      ...(event.originMessageId !== undefined
        ? { originMessageId: event.originMessageId }
        : {}),
      ...(event.sourceTaskId !== undefined
        ? { sourceTaskId: event.sourceTaskId }
        : {}),
    }
    return {
      entries: state.entries.map((entry, index) =>
        index === latestIndex ? next : entry,
      ),
    }
  }

  const latestEndTimestamp = latest.endTimestamp ?? latest.timestamp
  if (compareRuntimeTimestamps(event.timestamp, latestEndTimestamp) <= 0) {
    const relationshipChanged =
      sourceTaskId !== latest.sourceTaskId ||
      originMessageId !== latest.originMessageId ||
      conversationTurnId !== latest.conversationTurnId ||
      !sameTaskIds(latest.triggeringTaskIds, triggeringTaskIds)
    if (event.type !== 'agent.text.start' || !relationshipChanged) {
      return state
    }

    const next: RuntimeTraceEntry = {
      ...latest,
      label: getAgentActivityLabel(triggeringTaskIds),
      outputRunId,
      triggeringTaskIds,
      ...(conversationTurnId === undefined ? {} : { conversationTurnId }),
      ...(event.originMessageId !== undefined
        ? { originMessageId: event.originMessageId }
        : {}),
      ...(event.sourceTaskId !== undefined
        ? { sourceTaskId: event.sourceTaskId }
        : {}),
    }
    return {
      entries: state.entries.map((entry, index) =>
        index === latestIndex ? next : entry,
      ),
    }
  }

  return appendActivity()
}

function appendTaskMarker(
  state: RuntimeTraceState,
  event: TaskEvent,
  kind: RuntimeTraceKind,
  label: string,
  status: RuntimeTraceStatus,
): RuntimeTraceState {
  const entry: RuntimeTraceEntry = {
    id: event.id,
    kind,
    lane: 'task',
    label,
    status,
    timestamp: event.timestamp,
    taskId: event.taskId,
    ...(event.conversationTurnId !== undefined
      ? { conversationTurnId: event.conversationTurnId }
      : {}),
    ...(event.type === 'task.created' && event.originMessageId !== undefined
      ? { originMessageId: event.originMessageId }
      : {}),
  }

  return state.entries.some((existing) => existing.id === entry.id)
    ? state
    : { entries: [...state.entries, entry] }
}

function applyTaskCreatedEvent(
  state: RuntimeTraceState,
  event: TaskCreatedEvent,
): RuntimeTraceState {
  if (state.entries.some((entry) => entry.id === event.id)) {
    return state
  }

  const groupId = event.conversationTurnId ?? event.originMessageId ?? event.id
  const delegationEntryId = getAgentDelegationEntryId(groupId)
  const entries = [...state.entries]

  if (!entries.some((entry) => entry.id === delegationEntryId)) {
    entries.push({
      id: delegationEntryId,
      kind: 'agent.delegated',
      lane: 'agent',
      label: '发起任务',
      status: 'complete',
      timestamp: event.timestamp,
      endTimestamp: event.timestamp,
      ...(event.originMessageId !== undefined
        ? { messageId: event.originMessageId }
        : {}),
      ...(event.conversationTurnId !== undefined
        ? {
            messageId: event.conversationTurnId,
            conversationTurnId: event.conversationTurnId,
          }
        : {}),
    })
  }

  entries.push({
    id: event.id,
    kind: 'task.delegated',
    lane: 'task',
    label: event.title,
    status: 'active',
    timestamp: event.timestamp,
    taskId: event.taskId,
    ...(event.originMessageId !== undefined
      ? { originMessageId: event.originMessageId }
      : {}),
    ...(event.conversationTurnId !== undefined
      ? { conversationTurnId: event.conversationTurnId }
      : {}),
  })

  return { entries }
}

export function applyRuntimeEvent(
  state: RuntimeTraceState,
  event: AgentConsoleEvent,
): RuntimeTraceState {
  switch (event.type) {
    case 'agent.text.start':
    case 'agent.text.delta':
    case 'agent.text.done':
      return applyAgentTextEvent(state, event)

    case 'task.created':
      return applyTaskCreatedEvent(state, event)

    case 'task.success':
      return appendTaskMarker(state, event, 'task.succeeded', '任务完成', 'complete')

    case 'task.failure':
      return appendTaskMarker(state, event, 'task.failed', '任务失败', 'failed')

    case 'task.cancel.requested':
      return appendTaskMarker(
        state,
        event,
        'task.cancel.requested',
        '正在取消',
        'cancelling',
      )

    case 'task.cancelled':
      return appendTaskMarker(state, event, 'task.cancelled', '已取消', 'cancelled')

    default:
      return state
  }
}
