import type { AgentConsoleEvent } from '../domain/events'
import { isPlanConsoleEvent } from '../domain/planEvents'
import {
  applyTaskEvent,
  initialTaskProjectionState,
  type TaskProjectionState,
} from '../domain/projection'
import {
  applyPlanEvent,
  initialPlannerState,
  type PlannerState,
} from './planDagReducer'
import {
  applyRuntimeEvent,
  initialRuntimeTraceState,
  markRuntimeSubmissionFailed,
  recordQueuedRuntimeSubmission,
  recordRuntimeSubmission,
  type RuntimeTraceState,
} from './runtimeTraceReducer'

export interface ChatMessage {
  id: string
  messageId?: string
  role: 'user' | 'assistant'
  content: string
  sourceTaskId?: string
  sourceTaskTitle?: string
  status: 'streaming' | 'complete' | 'interrupted'
  createdAt: string
  voiceMessageKind?: 'agent' | 'quick-response'
  voiceTurnId?: string
  voiceAssistantMessageId?: string
}

export interface Toast {
  id: string
  message: string
  level: 'info' | 'error'
}

export interface ConsoleState {
  messages: ChatMessage[]
  tasks: TaskProjectionState
  planner: PlannerState
  runtimeTrace: RuntimeTraceState
  selectedTaskId?: string
  activeAssistantMessageId?: string
  isPlaying: boolean
  registeredAssistantMessageIds: string[]
  acceptedPlaybackMessageId?: string
  acceptedPlaybackRevision: number
  toasts: Toast[]
}

export type ConsoleAction =
  | {
      type: 'startConversation'
      input: string
      userMessageId: string
      assistantMessageId: string
      timestamp?: string
    }
  | {
      type: 'appendVoiceUserMessage'
      turnId: string
      userMessageId: string
      text: string
      assistantMessageId?: string
      timestamp: string
    }
  | {
      type: 'appendVoiceFeedbackMessage'
      turnId: string | null
      feedbackId: string
      text: string
      timestamp: string
    }
  | {
      type: 'markVoiceSubmitFailed'
      turnId: string
      userMessageId: string
      assistantMessageId: string
      timestamp: string
    }
  | { type: 'event'; event: AgentConsoleEvent }
  | { type: 'selectTask'; taskId?: string }
  | { type: 'selectPlanPage'; pageId: string }
  | { type: 'reset' }
  | { type: 'toast'; toast: Toast }
  | { type: 'dismissToast'; toastId: string }

export function initialConsoleState(): ConsoleState {
  return {
    messages: [],
    tasks: initialTaskProjectionState(),
    planner: initialPlannerState(),
    runtimeTrace: initialRuntimeTraceState(),
    isPlaying: false,
    registeredAssistantMessageIds: [],
    acceptedPlaybackRevision: 0,
    toasts: [],
  }
}

type AgentTextEvent = Extract<
  AgentConsoleEvent,
  { type: 'agent.text.start' | 'agent.text.delta' | 'agent.text.done' }
>

function isAgentTextEvent(event: AgentConsoleEvent): event is AgentTextEvent {
  return (
    event.type === 'agent.text.start' ||
    event.type === 'agent.text.delta' ||
    event.type === 'agent.text.done'
  )
}

function shouldAcceptAgentTextEvent(
  state: ConsoleState,
  event: AgentTextEvent,
): boolean {
  if (event.sourceTaskId !== undefined || (event.triggeringTaskIds?.length ?? 0) > 0) {
    return true
  }
  if (!state.registeredAssistantMessageIds.includes(event.messageId)) {
    return false
  }
  if (event.type === 'agent.text.start') {
    return true
  }
  return state.messages.some(
    (message) =>
      message.role === 'assistant'
      && message.sourceTaskId === undefined
      && (message.messageId ?? message.id) === event.messageId
      && message.status === 'streaming',
  )
}

function findStreamingAssistantIndex(messages: ChatMessage[], messageId: string): number {
  return messages.findIndex(
    (m) =>
      m.role === 'assistant' &&
      (m.messageId ?? m.id) === messageId &&
      m.status === 'streaming',
  )
}

function createAssistantMessageId(messages: ChatMessage[], messageId: string): string {
  if (!messages.some((message) => message.id === messageId)) {
    return messageId
  }

  const nextIndex = messages.filter(
    (message) => message.role === 'assistant' && (message.messageId ?? message.id) === messageId,
  ).length + 1

  return `${messageId}#${nextIndex}`
}

function upsertAgentMessage(
  messages: ChatMessage[],
  event: AgentTextEvent,
  sourceTaskTitle?: string,
): ChatMessage[] {
  const primaryTaskId = event.sourceTaskId ?? event.triggeringTaskIds?.[0]
  const source = {
    sourceTaskId: primaryTaskId,
    sourceTaskTitle,
  }
  // For agent.text.start on a completed message, create a new bubble
  if (event.type === 'agent.text.start') {
    const streamingIdx = findStreamingAssistantIndex(messages, event.messageId)
    if (streamingIdx >= 0) {
      // Already have a streaming placeholder — reuse it
      return messages
    }
    // Append a new streaming bubble (handles both first-time and multi-reply)
    return [...messages, {
      id: createAssistantMessageId(messages, event.messageId),
      messageId: event.messageId,
      role: 'assistant' as const,
      content: '',
      ...source,
      status: 'streaming' as const,
      createdAt: event.timestamp,
    }]
  }

  // For delta/done, find the last streaming assistant message with this messageId
  const streamingIdx = findStreamingAssistantIndex(messages, event.messageId)
  if (streamingIdx < 0) {
    // No streaming message found — create one on the fly
    return [...messages, {
      id: createAssistantMessageId(messages, event.messageId),
      messageId: event.messageId,
      role: 'assistant' as const,
      content: event.type === 'agent.text.delta' ? event.delta : '',
      ...source,
      status: event.type === 'agent.text.done' ? 'complete' as const : 'streaming' as const,
      createdAt: event.timestamp,
    }]
  }

  const current = messages[streamingIdx]
  const content =
    event.type === 'agent.text.delta'
      ? `${current.content}${event.delta}`
      : current.content
  const shouldAdoptReplyTimestamp =
    event.type === 'agent.text.delta' &&
    current.content.length === 0 &&
    event.delta.length > 0
  const next: ChatMessage = {
    ...current,
    sourceTaskId: primaryTaskId ?? current.sourceTaskId,
    sourceTaskTitle: sourceTaskTitle ?? current.sourceTaskTitle,
    content,
    status: event.type === 'agent.text.done' ? 'complete' : 'streaming',
    createdAt: shouldAdoptReplyTimestamp ? event.timestamp : current.createdAt,
  }
  return messages.map((m, i) => (i === streamingIdx ? next : m))
}

function applyAgentTextEvent(
  state: ConsoleState,
  event: AgentConsoleEvent,
): ChatMessage[] {
  if (!isAgentTextEvent(event)) {
    return state.messages
  }
  if (!shouldAcceptAgentTextEvent(state, event)) {
    return state.messages
  }
  const primaryTaskId = event.sourceTaskId ?? event.triggeringTaskIds?.[0]
  const sourceTaskTitle = primaryTaskId
    ? state.tasks.byId[primaryTaskId]?.title
    : undefined
  return upsertAgentMessage(state.messages, event, sourceTaskTitle)
}

function findVoiceUserMessage(
  state: ConsoleState,
  userMessageId: string,
  turnId: string,
): ChatMessage | undefined {
  return state.messages.find(
    (message) =>
      message.id === userMessageId
      && message.role === 'user'
      && message.voiceTurnId === turnId,
  )
}

function deriveAssistantPlayback(
  messages: ChatMessage[],
  registeredAssistantMessageIds: string[],
): Pick<
  ConsoleState,
  'activeAssistantMessageId' | 'isPlaying'
> {
  let activeAssistantMessageId: string | undefined
  for (const message of messages) {
    if (
      message.role === 'assistant'
      && message.sourceTaskId === undefined
      && message.status === 'streaming'
      && registeredAssistantMessageIds.includes(message.messageId ?? message.id)
    ) {
      activeAssistantMessageId = message.messageId ?? message.id
    }
  }
  return {
    activeAssistantMessageId,
    isPlaying: activeAssistantMessageId !== undefined,
  }
}

function advanceAcceptedPlayback(
  state: ConsoleState,
  messageId: string | undefined,
): Pick<ConsoleState, 'acceptedPlaybackMessageId' | 'acceptedPlaybackRevision'> {
  return {
    acceptedPlaybackMessageId: messageId,
    acceptedPlaybackRevision: state.acceptedPlaybackRevision + 1,
  }
}

export function consoleReducer(
  state: ConsoleState,
  action: ConsoleAction,
): ConsoleState {
  switch (action.type) {
    case 'startConversation': {
      const createdAt = action.timestamp ?? new Date().toISOString()
      // Seal any previous streaming assistant message before the new turn starts.
      const messages = state.messages.map((message) =>
        message.role === 'assistant'
        && message.sourceTaskId === undefined
        && message.status === 'streaming'
          ? { ...message, status: 'interrupted' as const }
          : message,
      )
      const nextMessages: ChatMessage[] = [
        ...messages,
        {
          id: action.userMessageId,
          role: 'user',
          content: action.input,
          status: 'complete',
          createdAt,
        },
        {
          id: action.assistantMessageId,
          messageId: action.assistantMessageId,
          role: 'assistant',
          content: '',
          status: 'streaming',
          createdAt,
        },
      ]
      const registeredAssistantMessageIds = [action.assistantMessageId]

      return {
        ...state,
        messages: nextMessages,
        runtimeTrace: recordRuntimeSubmission(state.runtimeTrace, {
          input: action.input,
          userMessageId: action.userMessageId,
          assistantMessageId: action.assistantMessageId,
          timestamp: createdAt,
        }),
        registeredAssistantMessageIds,
        ...deriveAssistantPlayback(nextMessages, registeredAssistantMessageIds),
        ...advanceAcceptedPlayback(state, action.assistantMessageId),
      }
    }

    case 'appendVoiceUserMessage': {
      if (state.messages.some((message) => message.id === action.userMessageId)) {
        return state
      }
      const messages = state.messages.map((message) =>
        message.role === 'assistant'
        && message.sourceTaskId === undefined
        && message.status === 'streaming'
          ? { ...message, status: 'interrupted' as const }
          : message,
      )
      const voiceUser: ChatMessage = {
        id: action.userMessageId,
        role: 'user',
        content: action.text,
        status: 'complete',
        createdAt: action.timestamp,
        voiceMessageKind: 'agent',
        voiceTurnId: action.turnId,
        ...(action.assistantMessageId
          ? { voiceAssistantMessageId: action.assistantMessageId }
          : {}),
      }
      const nextMessages: ChatMessage[] = action.assistantMessageId
        ? [
            ...messages,
            voiceUser,
            {
              id: action.assistantMessageId,
              messageId: action.assistantMessageId,
              role: 'assistant',
              content: '',
              status: 'streaming',
              createdAt: action.timestamp,
              voiceMessageKind: 'agent',
            },
          ]
        : [...messages, voiceUser]
      const registeredAssistantMessageIds = action.assistantMessageId
        ? [action.assistantMessageId]
        : []
      const playback = deriveAssistantPlayback(
        nextMessages,
        registeredAssistantMessageIds,
      )
      return {
        ...state,
        messages: nextMessages,
        runtimeTrace: action.assistantMessageId
          ? recordQueuedRuntimeSubmission(state.runtimeTrace, {
              input: action.text,
              userMessageId: action.userMessageId,
              assistantMessageId: action.assistantMessageId,
              timestamp: action.timestamp,
            })
          : state.runtimeTrace,
        registeredAssistantMessageIds,
        ...playback,
        ...advanceAcceptedPlayback(state, playback.activeAssistantMessageId),
      }
    }

    case 'appendVoiceFeedbackMessage': {
      if (state.messages.some((message) => message.id === action.feedbackId)) {
        return state
      }
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id: action.feedbackId,
            role: 'assistant',
            content: action.text,
            status: 'complete',
            createdAt: action.timestamp,
            voiceMessageKind: 'quick-response',
            voiceTurnId: action.turnId ?? undefined,
          },
        ],
      }
    }

    case 'markVoiceSubmitFailed': {
      const voiceUser = findVoiceUserMessage(state, action.userMessageId, action.turnId)
      if (
        !voiceUser
        || voiceUser.voiceAssistantMessageId !== action.assistantMessageId
      ) {
        return state
      }
      const assistantMatches = (message: ChatMessage) => (
        message.role === 'assistant'
        && (message.messageId ?? message.id) === action.assistantMessageId
      )
      const messages = state.messages
        .filter((message) => !(assistantMatches(message) && message.content.length === 0))
        .map((message) => {
          if (assistantMatches(message) && message.status === 'streaming') {
            return { ...message, status: 'interrupted' as const }
          }
          return message
        })
      const registeredAssistantMessageIds = state.registeredAssistantMessageIds.filter(
        (messageId) => messageId !== action.assistantMessageId,
      )
      const playback = deriveAssistantPlayback(messages, registeredAssistantMessageIds)
      return {
        ...state,
        messages,
        runtimeTrace: markRuntimeSubmissionFailed(state.runtimeTrace, {
          userMessageId: action.userMessageId,
          assistantMessageId: action.assistantMessageId,
          timestamp: action.timestamp,
        }),
        registeredAssistantMessageIds,
        ...playback,
        ...advanceAcceptedPlayback(state, playback.activeAssistantMessageId),
      }
    }

    case 'event': {
      const shouldApplyRuntimeEvent =
        !isAgentTextEvent(action.event) ||
        shouldAcceptAgentTextEvent(state, action.event)
      const messages = applyAgentTextEvent(state, action.event)
      const acceptedTopLevelPlaybackMessageId =
        shouldApplyRuntimeEvent
        && isAgentTextEvent(action.event)
        && action.event.sourceTaskId === undefined
        && (
          action.event.type === 'agent.text.start'
          || action.event.type === 'agent.text.delta'
        )
          ? action.event.messageId
          : undefined
      return {
        ...state,
        messages,
        tasks: applyTaskEvent(state.tasks, action.event),
        planner: isPlanConsoleEvent(action.event)
          ? applyPlanEvent(state.planner, action.event)
          : state.planner,
        runtimeTrace: shouldApplyRuntimeEvent
          ? applyRuntimeEvent(state.runtimeTrace, action.event)
          : state.runtimeTrace,
        ...deriveAssistantPlayback(messages, state.registeredAssistantMessageIds),
        ...(acceptedTopLevelPlaybackMessageId !== undefined
          ? advanceAcceptedPlayback(state, acceptedTopLevelPlaybackMessageId)
          : {}),
      }
    }

    case 'selectTask':
      if (action.taskId === undefined) {
        const { selectedTaskId: _, ...rest } = state
        return rest
      }
      return { ...state, selectedTaskId: action.taskId }

    case 'selectPlanPage':
      return state.planner.pages.some((page) => page.id === action.pageId)
        ? {
            ...state,
            planner: { ...state.planner, activePageId: action.pageId },
          }
        : state

    case 'reset':
      return initialConsoleState()

    case 'toast':
      return { ...state, toasts: [...state.toasts, action.toast] }

    case 'dismissToast':
      return { ...state, toasts: state.toasts.filter((t) => t.id !== action.toastId) }
  }
}
