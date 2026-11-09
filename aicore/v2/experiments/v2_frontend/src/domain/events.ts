import type { PlanConsoleEvent } from './planEvents'

export type { PlanConsoleEvent } from './planEvents'

export type TaskStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'cancelling'
  | 'cancelled'

export interface EventBase {
  id: string
  timestamp: string
}

export interface FrontendEventCorrelation {
  conversationTurnId?: string
  outputRunId?: string
  triggeringTaskIds?: string[]
}

export interface AgentTextStartEvent extends EventBase, FrontendEventCorrelation {
  type: 'agent.text.start'
  messageId: string
  originMessageId?: string
  sourceTaskId?: string
}

export interface AgentTextDeltaEvent extends EventBase, FrontendEventCorrelation {
  type: 'agent.text.delta'
  messageId: string
  originMessageId?: string
  sourceTaskId?: string
  delta: string
}

export interface AgentTextDoneEvent extends EventBase, FrontendEventCorrelation {
  type: 'agent.text.done'
  messageId: string
  originMessageId?: string
  sourceTaskId?: string
}

export interface TaskCreatedEvent extends EventBase, FrontendEventCorrelation {
  type: 'task.created'
  taskId: string
  toolName: string
  title: string
  arguments: Record<string, unknown>
  originMessageId?: string
}

export interface TaskStartEvent extends EventBase, FrontendEventCorrelation {
  type: 'task.start'
  taskId: string
}

export interface TaskProgressEvent extends EventBase, FrontendEventCorrelation {
  type: 'task.progress'
  taskId: string
  progress?: number
  message: string
  rawProgress?: unknown
}

export interface TaskSuccessEvent extends EventBase, FrontendEventCorrelation {
  type: 'task.success'
  taskId: string
  result: unknown
}

export interface TaskFailureEvent extends EventBase, FrontendEventCorrelation {
  type: 'task.failure'
  taskId: string
  error: string
}

export interface TaskCancelRequestedEvent extends EventBase, FrontendEventCorrelation {
  type: 'task.cancel.requested'
  taskId: string
  reason: string
}

export interface TaskCancelledEvent extends EventBase, FrontendEventCorrelation {
  type: 'task.cancelled'
  taskId: string
  reason: string
}

export type AgentConsoleEvent =
  | AgentTextStartEvent
  | AgentTextDeltaEvent
  | AgentTextDoneEvent
  | TaskCreatedEvent
  | TaskStartEvent
  | TaskProgressEvent
  | TaskSuccessEvent
  | TaskFailureEvent
  | TaskCancelRequestedEvent
  | TaskCancelledEvent
  | PlanConsoleEvent

export function isTaskEvent(
  event: AgentConsoleEvent,
): event is Extract<AgentConsoleEvent, { taskId: string }> {
  return 'taskId' in event
}
