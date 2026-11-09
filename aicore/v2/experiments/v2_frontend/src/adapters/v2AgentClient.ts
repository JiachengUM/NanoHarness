import type { AgentConsoleEvent } from '../domain/events'
import type {
  AgentMode,
  DiagnosisDecision,
  DiagnosisProcessErrorKind,
  DiagnosisSource,
  PlanConsoleEvent,
  PlanDefinition,
  PlanStepDefinition,
  PlanStepSkippedEvent,
} from '../domain/planEvents'
import { asNumber, asRecord, asString, formatCriterion } from '../utils/unknown'
import type {
  VoiceEvent,
  VoiceFeedbackPayload,
  VoiceFeedbackMode,
  VoicePhase,
} from '../voice/voiceTypes'
import commandProtocol from '../../protocol/client_commands.json'
import { PROTOCOL_VERSION, type AgentCommand } from './clientCommands'
import {
  traceBrowserLatency,
  type LatencyTraceContext,
} from '../utils/latencyTrace'

export interface BackendConsoleEvent {
  id: string
  type: string
  timestamp: string
  payload: Record<string, unknown>
}

export interface LiveAgentClientOptions {
  baseUrl?: string
  fetchImpl?: typeof fetch
  webSocketFactory?: AgentWebSocketFactory
}

export interface LiveAgentRunOptions {
  input: string
  messageId: string
  onEvent(event: AgentConsoleEvent): void
  onError?(error: unknown): void
}

export interface LiveVoiceStartOptions {
  onEvent?(event: AgentConsoleEvent): void
  onVoiceEvent(event: VoiceEvent): void
  onVoiceAudio?(chunk: ArrayBuffer): void
  onError?(error: unknown): void
}

export interface SessionResetResult {
  agentMode: AgentMode
  runtimeProfile: RuntimeProfile
}

export type RuntimeProfile =
  | 'react_s2s'
  | 'plact_s2s'
  | 'react_duplex_shell'
  | 'plact_duplex_shell'
  | 'duplex_native'

export type TaskCancelOutcomeStatus =
  | 'accepted'
  | 'already_terminal'
  | 'not_found'
  | 'failed'

export interface TaskCancelResult {
  status: TaskCancelOutcomeStatus
  taskId: string
  terminalStatus?: string
  reason?: string
  requestedEvent?: Extract<
    AgentConsoleEvent,
    { type: 'task.cancel.requested' }
  >
}

export interface LiveAgentClient {
  start(options: LiveAgentRunOptions): void
  startVoice(options: LiveVoiceStartOptions): Promise<void>
  openVoiceMicrophone(): Promise<void>
  closeVoiceMicrophone(): Promise<void>
  notifyVoicePlaybackEnded(): Promise<void>
  stopVoice(): Promise<void>
  sendVoiceTextQuery(input: string): Promise<void>
  sendVoiceAudio(chunk: ArrayBuffer): Promise<void>
  cancelTask(taskId: string): Promise<TaskCancelResult>
  resetSession(agentMode: AgentMode): Promise<SessionResetResult>
  resetRuntime(runtimeProfile: RuntimeProfile): Promise<SessionResetResult>
  checkHealth(): Promise<boolean>
  dispose(): void
}

interface AgentWebSocket {
  readyState: number
  binaryType?: BinaryType
  onopen: ((event: Event) => void) | null
  onmessage: ((event: MessageEvent) => void) | null
  onerror: ((event: Event) => void) | null
  onclose: ((event: CloseEvent) => void) | null
  send(data: string | ArrayBuffer): void
  close(): void
}

type AgentWebSocketFactory = (url: string) => AgentWebSocket
type AckStatus = 'accepted' | 'completed' | 'rejected'

interface ServerAckMessage {
  v: number
  kind: 'ack'
  command_id: string
  command: AgentCommand | string
  ok: boolean
  status: AckStatus
  payload?: Record<string, unknown>
  error?: {
    code?: string
    message?: string
    retryable?: boolean
  }
}

interface PendingCommand {
  command: AgentCommand
  traceContext: LatencyTraceContext
  resolve(message: ServerAckMessage): void
  reject(error: Error): void
}

const defaultBaseUrl =
  import.meta.env.VITE_V2_AGENT_BASE_URL ?? 'http://127.0.0.1:8799'

const SOCKET_CONNECTING = 0
const SOCKET_OPEN = 1
const SOCKET_CLOSED = 3
const disposedSocketMessage = 'Live agent WebSocket disposed'
const voiceEventTypes: ReadonlySet<VoiceEvent['type']> = new Set([
  'voice.ready',
  'voice.phase',
  'voice.asr.delta',
  'voice.asr.final',
  'voice.feedback',
  'voice.playback.duck',
  'voice.playback.restore',
  'voice.submit.failed',
  'voice.interrupted',
  'voice.error',
])

const voiceFeedbackModes: ReadonlySet<VoiceFeedbackMode> = new Set([
  'duplex',
])
const voicePhases: ReadonlySet<VoicePhase> = new Set([
  'idle',
  'mic_pending',
  'listening',
  'processing',
  'speaking',
  'interrupted',
  'error',
])
const ackStatuses: ReadonlySet<AckStatus> = new Set([
  'accepted',
  'completed',
  'rejected',
])
const commandSuccessStatuses = new Map<AgentCommand, Exclude<AckStatus, 'rejected'>>(
  commandProtocol.commands.map((descriptor) => [
    descriptor.command as AgentCommand,
    descriptor.success_status as Exclude<AckStatus, 'rejected'>,
  ]),
)

function stringifyProgress(value: unknown): string {
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'number') {
    return `${value}%`
  }
  const record = asRecord(value)
  const message = asString(record.message)
  if (message) {
    return message
  }
  return JSON.stringify(value)
}

function progressPercent(value: unknown): number | undefined {
  if (typeof value === 'number') {
    return value
  }
  const record = asRecord(value)
  const progressPercentValue = record.progress_percent ?? record.progressPercent ?? record.progress
  return typeof progressPercentValue === 'number' ? progressPercentValue : undefined
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : []
}

function optionalString(value: unknown): string | undefined {
  const result = asString(value)
  return result || undefined
}

function requiredString(value: unknown, field: string): string {
  const result = asString(value)
  if (!result) {
    throw new Error(`Invalid ${field}: expected a non-empty string`)
  }
  return result
}

function normalizeDiagnosisProcessErrorKind(
  value: unknown,
): DiagnosisProcessErrorKind | undefined {
  if (value === null || value === undefined) {
    return undefined
  }
  const kind = requiredString(
    value,
    'plan.step.diagnosis.started process_error_kind',
  )
  switch (kind) {
    case 'params':
    case 'condition':
    case 'execution':
    case 'projection':
      return kind
    default:
      throw new Error(
        `Invalid plan.step.diagnosis.started process_error_kind: ${kind}`,
      )
  }
}

function normalizeDiagnosisSource(value: unknown): DiagnosisSource {
  const source = requiredString(
    value,
    'plan.step.diagnosis.completed source',
  )
  switch (source) {
    case 'rule':
    case 'llm':
    case 'fallback':
      return source
    default:
      throw new Error(`Invalid plan.step.diagnosis.completed source: ${source}`)
  }
}

function normalizeDiagnosisDecision(value: unknown): DiagnosisDecision {
  const decision = asRecord(value)
  const outcome = requiredString(
    decision.outcome,
    'plan.step.diagnosis.completed decision.outcome',
  )
  switch (outcome) {
    case 'replan':
      return {
        outcome,
        failedAssumption: requiredString(
          decision.failed_assumption,
          'plan.step.diagnosis.completed decision.failed_assumption',
        ),
        retryDirection: requiredString(
          decision.retry_direction,
          'plan.step.diagnosis.completed decision.retry_direction',
        ),
      }
    case 'skip_unsolvable':
      return {
        outcome,
        unsolvableReason: requiredString(
          decision.unsolvable_reason,
          'plan.step.diagnosis.completed decision.unsolvable_reason',
        ),
      }
    case 'accept_degraded':
      return {
        outcome,
        limitation: requiredString(
          decision.limitation,
          'plan.step.diagnosis.completed decision.limitation',
        ),
      }
    default:
      throw new Error(`Invalid plan.step.diagnosis.completed outcome: ${outcome}`)
  }
}

function normalizePlanDefinition(value: unknown): PlanDefinition {
  const raw = asRecord(value)
  const rawSteps = Array.isArray(raw.steps) ? raw.steps : []
  return {
    goal: asString(raw.goal),
    raw: value,
    steps: rawSteps.map((item): PlanStepDefinition => {
      const step = asRecord(item)
      return {
        stepId: asString(step.step_id),
        stepGoal: asString(step.step_goal),
        op: asString(step.op),
        dependsOn: stringArray(step.depends_on),
        rawInputs: asRecord(step.inputs),
        outputSpec: step.outputs,
        condition: optionalString(step.condition),
        successCheck: formatCriterion(step.success_check),
      }
    }),
  }
}

function normalizePlanEvent(
  envelope: BackendConsoleEvent,
): PlanConsoleEvent | null {
  const payload = envelope.payload
  const isDiagnosisEvent =
    envelope.type === 'plan.step.diagnosis.started' ||
    envelope.type === 'plan.step.diagnosis.completed'
  const messageId = optionalString(payload.message_id)
  const round = asNumber(payload.round)
  if (!messageId || round === undefined || !Number.isInteger(round) || round < 0) {
    if (isDiagnosisEvent) {
      if (!messageId) {
        throw new Error(`Invalid ${envelope.type} message_id: expected a non-empty string`)
      }
      throw new Error(`Invalid ${envelope.type} round: expected a non-negative integer`)
    }
    return null
  }
  const context = {
    id: envelope.id,
    timestamp: envelope.timestamp,
    messageId,
    round,
  }

  switch (envelope.type) {
    case 'plact.round.start':
      return {
        ...context,
        type: 'plact.round.start',
        repairContext: payload.repair_context ?? undefined,
      }
    case 'plan.created':
      return {
        ...context,
        type: 'plan.created',
        plan: normalizePlanDefinition(payload.plan),
      }
    case 'plan.step.started':
      return {
        ...context,
        type: 'plan.step.started',
        stepId: asString(payload.step_id),
        stepGoal: asString(payload.step_goal),
        resolvedInputs: asRecord(payload.resolved_inputs),
      }
    case 'plan.step.diagnosis.started':
      return {
        ...context,
        type: 'plan.step.diagnosis.started',
        stepId: requiredString(
          payload.step_id,
          'plan.step.diagnosis.started step_id',
        ),
        stepGoal: requiredString(
          payload.step_goal,
          'plan.step.diagnosis.started step_goal',
        ),
        successCheck: formatCriterion(payload.success_check),
        failureMessage: requiredString(
          payload.failure_message,
          'plan.step.diagnosis.started failure_message',
        ),
        processErrorKind: normalizeDiagnosisProcessErrorKind(
          payload.process_error_kind,
        ),
      }
    case 'plan.step.diagnosis.completed':
      return {
        ...context,
        type: 'plan.step.diagnosis.completed',
        stepId: requiredString(
          payload.step_id,
          'plan.step.diagnosis.completed step_id',
        ),
        stepGoal: requiredString(
          payload.step_goal,
          'plan.step.diagnosis.completed step_goal',
        ),
        source: normalizeDiagnosisSource(payload.source),
        decision: normalizeDiagnosisDecision(payload.decision),
      }
    case 'plan.step.done':
      return {
        ...context,
        type: 'plan.step.done',
        stepId: asString(payload.step_id),
        stepGoal: asString(payload.step_goal),
        rawInputs: asRecord(payload.raw_inputs),
        resolvedInputs: asRecord(payload.resolved_inputs),
        toolOutput: payload.tool_output,
        conceptOutput: asRecord(payload.concept_output),
        processError: payload.process_error ?? undefined,
        unmet: payload.unmet ?? undefined,
      }
    case 'plan.step.skipped':
      return {
        ...context,
        type: 'plan.step.skipped',
        stepId: asString(payload.step_id),
        stepGoal: asString(payload.step_goal),
        reason: asString(payload.reason) as PlanStepSkippedEvent['reason'],
        condition: optionalString(payload.condition),
      }
    case 'plan.runner.error':
      return {
        ...context,
        type: 'plan.runner.error',
        errors: Array.isArray(payload.errors) ? payload.errors : [],
      }
    case 'plact.errors':
      return {
        ...context,
        type: 'plact.errors',
        errors: Array.isArray(payload.errors) ? payload.errors : [],
        policy: asString(payload.policy),
      }
    case 'plact.finish':
      return {
        ...context,
        type: 'plact.finish',
        response: payload.response,
        forced: payload.forced === true,
        reason: optionalString(payload.reason),
      }
    default:
      return null
  }
}

export function normalizeBackendEvent(
  envelope: BackendConsoleEvent,
  messageId: string,
): AgentConsoleEvent | null {
  const payload = envelope.payload
  const resolvedMessageId = asString(payload.message_id, messageId)
  const originMessageId = optionalString(payload.origin_message_id)
  const sourceTaskId = optionalString(payload.source_task_id)
  const conversationTurnId = Object.hasOwn(payload, 'conversation_turn_id')
    ? optionalString(payload.conversation_turn_id)
    : originMessageId
  const outputRunId = Object.hasOwn(payload, 'output_run_id')
    ? optionalString(payload.output_run_id)
    : resolvedMessageId
  const rawTriggeringTaskIds = payload.triggering_task_ids
  const triggeringTaskIds = Array.isArray(rawTriggeringTaskIds)
    ? [...new Set(rawTriggeringTaskIds.filter(
        (taskId): taskId is string => typeof taskId === 'string' && taskId.length > 0,
      ))]
    : sourceTaskId === undefined ? [] : [sourceTaskId]
  const correlation = {
    ...(conversationTurnId === undefined ? {} : { conversationTurnId }),
    ...(outputRunId === undefined ? {} : { outputRunId }),
    triggeringTaskIds,
  }
  const planEvent = normalizePlanEvent(envelope)
  if (planEvent) {
    return planEvent
  }

  switch (envelope.type) {
    case 'agent.out.text.start':
      return {
        id: envelope.id,
        type: 'agent.text.start',
        timestamp: envelope.timestamp,
        messageId: resolvedMessageId,
        originMessageId,
        sourceTaskId,
        ...correlation,
      }

    case 'agent.out.text.delta':
      return {
        id: envelope.id,
        type: 'agent.text.delta',
        timestamp: envelope.timestamp,
        messageId: resolvedMessageId,
        originMessageId,
        sourceTaskId,
        ...correlation,
        delta: asString(payload.delta),
      }

    case 'agent.out.text.done':
      return {
        id: envelope.id,
        type: 'agent.text.done',
        timestamp: envelope.timestamp,
        messageId: resolvedMessageId,
        originMessageId,
        sourceTaskId,
        ...correlation,
      }

    case 'task.created': {
      const toolName = asString(payload.name, asString(payload.task_id, 'unknown_task'))
      return {
        id: envelope.id,
        type: 'task.created',
        timestamp: envelope.timestamp,
        taskId: asString(payload.task_id),
        toolName,
        title: toolName,
        arguments: asRecord(payload.arguments),
        originMessageId,
        ...correlation,
      }
    }

    case 'task.start':
      return {
        id: envelope.id,
        type: 'task.start',
        timestamp: envelope.timestamp,
        taskId: asString(payload.task_id),
        ...correlation,
      }

    case 'task.progress': {
      const progressValue = payload.progress
      const event: AgentConsoleEvent = {
        id: envelope.id,
        type: 'task.progress',
        timestamp: envelope.timestamp,
        taskId: asString(payload.task_id),
        message: stringifyProgress(progressValue),
        ...correlation,
      }
      const percent = progressPercent(progressValue)
      if (percent !== undefined) {
        event.progress = percent
      }
      if (progressValue && typeof progressValue === 'object') {
        event.rawProgress = progressValue
      }
      return event
    }

    case 'task.success':
      return {
        id: envelope.id,
        type: 'task.success',
        timestamp: envelope.timestamp,
        taskId: asString(payload.task_id),
        result: payload.result,
        ...correlation,
      }

    case 'task.failure':
      return {
        id: envelope.id,
        type: 'task.failure',
        timestamp: envelope.timestamp,
        taskId: asString(payload.task_id),
        error: asString(payload.error, JSON.stringify(payload.error)),
        ...correlation,
      }

    case 'task.cancelled':
      return {
        id: envelope.id,
        type: 'task.cancelled',
        timestamp: envelope.timestamp,
        taskId: asString(payload.task_id),
        reason: asString(payload.reason, 'Task was cancelled'),
        ...correlation,
      }

    default:
      return null
  }
}

function createAcceptedCancelEvent(
  taskId: string,
): Extract<AgentConsoleEvent, { type: 'task.cancel.requested' }> {
  return {
    id: `live-cancel-request-${taskId}`,
    type: 'task.cancel.requested',
    timestamp: new Date().toISOString(),
    taskId,
    reason: '用户点击取消',
  }
}

function parseTaskCancelOutcomeStatus(value: string): TaskCancelOutcomeStatus {
  switch (value) {
    case 'accepted':
    case 'already_terminal':
    case 'not_found':
    case 'failed':
      return value
    default:
      return 'failed'
  }
}

function toWebSocketUrl(baseUrl: string): string {
  const browserOrigin =
    typeof window === 'undefined'
      ? 'http://127.0.0.1'
      : window.location.origin
  const url = new URL(baseUrl, browserOrigin)
  const basePath = url.pathname.replace(/\/+$/, '')

  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = `${basePath}/v2/frontend/ws`
  url.search = ''
  url.hash = ''
  return url.toString()
}

function ackError(message: ServerAckMessage): Error {
  const detail = message.error?.message ?? `Command ${message.command} was rejected`
  const code = message.error?.code
  return new Error(code ? `${code}: ${detail}` : detail)
}

function isDisposedSocketError(error: unknown): boolean {
  return error instanceof Error && error.message === disposedSocketMessage
}

function assertRecord(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(message)
  }
  return value as Record<string, unknown>
}

function isVoiceEventType(value: unknown): value is VoiceEvent['type'] {
  return typeof value === 'string' && voiceEventTypes.has(value as VoiceEvent['type'])
}

function strictVoiceValue<T extends string>(
  value: unknown,
  knownValues: ReadonlySet<T>,
): T | null {
  return typeof value === 'string' && knownValues.has(value as T)
    ? (value as T)
    : null
}

function requiredNonEmptyString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0
    ? value
    : null
}

function isNonNegativeSafeInteger(value: unknown): value is number {
  return typeof value === 'number'
    && Number.isSafeInteger(value)
    && value >= 0
}

function payloadExtensions(
  payload: Record<string, unknown>,
  knownKeys: readonly string[],
): Record<string, unknown> {
  const extensions = { ...payload }
  for (const key of knownKeys) {
    delete extensions[key]
  }
  return extensions
}

function normalizeVoiceFeedbackPayload(
  payload: Record<string, unknown>,
): VoiceFeedbackPayload | null {
  const turnId = payload.turn_id === null
    ? null
    : requiredNonEmptyString(payload.turn_id)
  const feedbackId = requiredNonEmptyString(payload.feedback_id)
  const text = requiredNonEmptyString(payload.text)
  const mode = strictVoiceValue(payload.mode, voiceFeedbackModes)
  if (
    (turnId === null && payload.turn_id !== null)
    || feedbackId === null
    || text === null
    || mode === null
  ) {
    return null
  }
  return {
    ...payloadExtensions(payload, [
      'turn_id',
      'feedback_id',
      'text',
      'mode',
    ]),
    turn_id: turnId,
    feedback_id: feedbackId,
    text,
    mode,
  }
}

function normalizeVoiceEvent(message: Record<string, unknown>): VoiceEvent | null {
  if (asString(message.kind) !== 'voice' || !isVoiceEventType(message.type)) {
    return null
  }
  const payload = asRecord(message.payload)
  const envelope = { v: 1 as const, kind: 'voice' as const }

  switch (message.type) {
    case 'voice.ready': {
      const normalizedPayload = payloadExtensions(payload, [
        'input_sample_rate',
        'output_sample_rate',
        'output_format',
      ])
      const inputSampleRate = asNumber(payload.input_sample_rate)
      const outputSampleRate = asNumber(payload.output_sample_rate)
      if (inputSampleRate !== undefined) {
        normalizedPayload.input_sample_rate = inputSampleRate
      }
      if (outputSampleRate !== undefined) {
        normalizedPayload.output_sample_rate = outputSampleRate
      }
      if (payload.output_format === 'f32le') {
        normalizedPayload.output_format = 'f32le'
      }
      return { ...envelope, type: message.type, payload: normalizedPayload }
    }

    case 'voice.phase': {
      const phase = strictVoiceValue(payload.phase, voicePhases)
      if (phase === null) {
        return null
      }
      return {
        ...envelope,
        type: message.type,
        payload: {
          ...payloadExtensions(payload, ['phase']),
          phase,
        },
      }
    }

    case 'voice.asr.delta': {
      const text = requiredNonEmptyString(payload.text)
      if (text === null) {
        return null
      }
      return {
        ...envelope,
        type: message.type,
        payload: {
          ...payloadExtensions(payload, ['text']),
          text,
        },
      }
    }

    case 'voice.asr.final': {
      const turnId = requiredNonEmptyString(payload.turn_id)
      const userMessageId = requiredNonEmptyString(payload.user_message_id)
      const text = requiredNonEmptyString(payload.text)
      if (turnId === null || userMessageId === null || text === null) {
        return null
      }
      const assistantMessageId = optionalString(payload.assistant_message_id)
      return {
        ...envelope,
        type: message.type,
        payload: {
          ...payloadExtensions(payload, [
            'turn_id',
            'user_message_id',
            'assistant_message_id',
            'text',
          ]),
          turn_id: turnId,
          user_message_id: userMessageId,
          text,
          ...(assistantMessageId ? { assistant_message_id: assistantMessageId } : {}),
        },
      }
    }

    case 'voice.feedback': {
      const normalizedPayload = normalizeVoiceFeedbackPayload(payload)
      return normalizedPayload === null
        ? null
        : { ...envelope, type: message.type, payload: normalizedPayload }
    }

    case 'voice.playback.duck':
    case 'voice.playback.restore':
      return { ...envelope, type: message.type, payload }

    case 'voice.submit.failed': {
      const turnId = requiredNonEmptyString(payload.turn_id)
      const userMessageId = requiredNonEmptyString(payload.user_message_id)
      const assistantMessageId = requiredNonEmptyString(
        payload.assistant_message_id,
      )
      if (
        turnId === null
        || userMessageId === null
        || assistantMessageId === null
        || payload.code !== 'AGENT_SUBMIT_FAILED'
      ) {
        return null
      }
      return {
        ...envelope,
        type: message.type,
        payload: {
          ...payloadExtensions(payload, [
            'turn_id',
            'user_message_id',
            'assistant_message_id',
            'code',
          ]),
          turn_id: turnId,
          user_message_id: userMessageId,
          assistant_message_id: assistantMessageId,
          code: 'AGENT_SUBMIT_FAILED',
        },
      }
    }

    case 'voice.interrupted': {
      const reason = optionalString(payload.reason)
      const messageId = optionalString(payload.message_id)
      return {
        ...envelope,
        type: message.type,
        payload: {
          ...payloadExtensions(payload, ['reason', 'message_id']),
          ...(reason ? { reason } : {}),
          ...(messageId ? { message_id: messageId } : {}),
        },
      }
    }

    case 'voice.error': {
      const errorMessage = optionalString(payload.message)
      const errorDetail = optionalString(payload.error)
      return {
        ...envelope,
        type: message.type,
        payload: {
          ...payloadExtensions(payload, ['message', 'error']),
          ...(errorMessage ? { message: errorMessage } : {}),
          ...(errorDetail ? { error: errorDetail } : {}),
        },
      }
    }
  }
}

interface ServerContext {
  sessionId: string
  generation: number
}

function readServerContext(value: Record<string, unknown>): ServerContext | null {
  const sessionId = requiredNonEmptyString(value.session_id)
  if (sessionId === null || !isNonNegativeSafeInteger(value.generation)) {
    return null
  }
  return { sessionId, generation: value.generation }
}

function invalidAck(reason: string): Error {
  return new Error(`Invalid ACK: ${reason}`)
}

function validateAckMessage(
  message: Record<string, unknown>,
  pending: PendingCommand,
): ServerAckMessage | Error {
  if (message.v !== PROTOCOL_VERSION) {
    return invalidAck('protocol version mismatch')
  }
  if (message.command !== pending.command) {
    return invalidAck('command mismatch')
  }
  if (typeof message.ok !== 'boolean') {
    return invalidAck('ok must be boolean')
  }
  const status = strictVoiceValue(message.status, ackStatuses)
  if (status === null) {
    return invalidAck('unknown status')
  }
  const expectedSuccessStatus = commandSuccessStatuses.get(pending.command)
  if (
    expectedSuccessStatus === undefined
    || (message.ok && status !== expectedSuccessStatus)
    || (!message.ok && status !== 'rejected')
  ) {
    return invalidAck('ok and status are inconsistent')
  }
  if (
    message.payload !== undefined
    && (
      message.payload === null
      || typeof message.payload !== 'object'
      || Array.isArray(message.payload)
    )
  ) {
    return invalidAck('payload must be an object')
  }
  if (
    message.error !== undefined
    && (
      message.error === null
      || typeof message.error !== 'object'
      || Array.isArray(message.error)
    )
  ) {
    return invalidAck('error must be an object')
  }
  const payload = asRecord(message.payload)
  if ('session_id' in payload || 'generation' in payload) {
    if (readServerContext(payload) === null) {
      return invalidAck('session context is malformed')
    }
  }
  return {
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: asString(message.command_id),
    command: pending.command,
    ok: message.ok,
    status,
    payload,
    error: message.error as ServerAckMessage['error'],
  }
}

function matchesVoiceContext(
  message: Record<string, unknown>,
  currentSessionId: string,
  currentGeneration: number | undefined,
): boolean {
  if (message.v !== 1 || !currentSessionId || currentGeneration === undefined) {
    return false
  }
  const context = readServerContext(message)
  return context !== null
    && context.sessionId === currentSessionId
    && context.generation === currentGeneration
}

export function createLiveAgentClient(
  options: LiveAgentClientOptions = {},
): LiveAgentClient {
  const baseUrl = (options.baseUrl ?? defaultBaseUrl).replace(/\/+$/, '')
  const fetchImpl = options.fetchImpl ?? fetch
  const webSocketFactory: AgentWebSocketFactory =
    options.webSocketFactory ?? ((url: string) => new WebSocket(url))
  const wsUrl = toWebSocketUrl(baseUrl)
  const pendingCommands = new Map<string, PendingCommand>()
  let socket: AgentWebSocket | null = null
  let openPromise: Promise<AgentWebSocket> | null = null
  let commandSeq = 0
  let latestMessageId = ''
  let currentSessionId = ''
  let currentGeneration: number | undefined
  const tracedFirstDeltaMessageIds = new Set<string>()
  let activeOnEvent: ((event: AgentConsoleEvent) => void) | null = null
  let activeOnError: ((error: unknown) => void) | null = null
  let activeOnVoiceEvent: ((event: VoiceEvent) => void) | null = null
  let activeOnVoiceAudio: ((chunk: ArrayBuffer) => void) | null = null
  let activeOnVoiceError: ((error: unknown) => void) | null = null
  let intentionalClose = false

  const reportSocketError = (error: unknown) => {
    activeOnError?.(error)
    if (activeOnVoiceError && activeOnVoiceError !== activeOnError) {
      activeOnVoiceError(error)
    }
  }

  const rejectPendingCommands = (error: Error) => {
    pendingCommands.forEach((pending) => pending.reject(error))
    pendingCommands.clear()
  }

  const resolvePendingCommandsForDispose = () => {
    pendingCommands.forEach((pending, commandId) => {
      pending.resolve({
        v: PROTOCOL_VERSION,
        kind: 'ack',
        command_id: commandId,
        command: pending.command,
        ok: true,
        status: 'completed',
        payload: {},
      })
    })
    pendingCommands.clear()
  }

  const handleServerMessage = (rawData: unknown) => {
    if (rawData instanceof ArrayBuffer) {
      activeOnVoiceAudio?.(rawData)
      return
    }

    const rawText = typeof rawData === 'string' ? rawData : String(rawData)
    const message = assertRecord(JSON.parse(rawText), 'Live agent WebSocket message must be an object')
    const kind = asString(message.kind)

    if (kind === 'hello') {
      if (message.v !== PROTOCOL_VERSION) {
        return
      }
      const context = readServerContext(message)
      if (context === null) {
        return
      }
      currentSessionId = context.sessionId
      currentGeneration = context.generation
      return
    }

    if (kind === 'voice') {
      if (!matchesVoiceContext(message, currentSessionId, currentGeneration)) {
        return
      }
      const voiceEvent = normalizeVoiceEvent(message)
      if (voiceEvent === null) {
        return
      }
      const voicePayload = asRecord(voiceEvent.payload)
      const voiceTraceContext = {
        message_id: optionalString(voicePayload.message_id),
        session_id: currentSessionId || undefined,
        generation: currentGeneration,
      }
      if (voiceEvent.type === 'voice.ready') {
        traceBrowserLatency('voice.ready', voiceTraceContext)
      } else if (voiceEvent.type === 'voice.interrupted') {
        traceBrowserLatency('voice.interrupted.received', voiceTraceContext)
      }
      if (voiceEvent.type === 'voice.asr.final') {
        const assistantMessageId = asString(voiceEvent.payload.assistant_message_id)
        if (assistantMessageId) {
          latestMessageId = assistantMessageId
        }
      }
      activeOnVoiceEvent?.(voiceEvent)
      return
    }

    if (kind === 'ack') {
      const commandId = asString(message.command_id)
      const pending = commandId ? pendingCommands.get(commandId) : undefined
      if (!pending || !commandId) {
        return
      }
      pendingCommands.delete(commandId)
      const ack = validateAckMessage(message, pending)
      if (ack instanceof Error) {
        pending.reject(ack)
        return
      }
      const ackPayload = ack.payload ?? {}
      const ackContext = readServerContext(ackPayload)
      if (ackContext !== null) {
        currentSessionId = ackContext.sessionId
        currentGeneration = ackContext.generation
      }
      traceBrowserLatency('ws.command.ack', {
        ...pending.traceContext,
        session_id: currentSessionId || undefined,
        generation: currentGeneration,
      })
      if (ack.ok) {
        pending.resolve(ack)
      } else {
        pending.reject(ackError(ack))
      }
      return
    }

    if (kind === 'event') {
      const backendEvent = message.event as BackendConsoleEvent
      const event = normalizeBackendEvent(backendEvent, latestMessageId)
      if (event) {
        if (
          event.type === 'agent.text.delta' &&
          !tracedFirstDeltaMessageIds.has(event.messageId)
        ) {
          tracedFirstDeltaMessageIds.add(event.messageId)
          traceBrowserLatency('agent.first_delta', {
            message_id: event.messageId,
            origin_message_id: event.originMessageId,
            task_id: event.sourceTaskId,
            session_id: currentSessionId || undefined,
            generation: currentGeneration,
          })
        } else if (event.type === 'task.cancelled') {
          traceBrowserLatency('task.cancelled.received', {
            task_id: event.taskId,
            session_id: currentSessionId || undefined,
            generation: currentGeneration,
          })
        }
        activeOnEvent?.(event)
      }
      return
    }

    if (kind === 'error') {
      const commandId = asString(message.command_id)
      const pending = commandId ? pendingCommands.get(commandId) : undefined
      const errorRecord = asRecord(message.error)
      const error = new Error(asString(errorRecord.message, 'Live agent WebSocket error'))
      if (pending && commandId) {
        pendingCommands.delete(commandId)
        pending.reject(error)
      } else {
        reportSocketError(error)
      }
    }
  }

  const ensureSocket = (): Promise<AgentWebSocket> => {
    if (socket?.readyState === SOCKET_OPEN) {
      return Promise.resolve(socket)
    }
    if (socket?.readyState === SOCKET_CONNECTING && openPromise) {
      return openPromise
    }

    intentionalClose = false
    const nextSocket = webSocketFactory(wsUrl)
    if ('binaryType' in nextSocket) {
      nextSocket.binaryType = 'arraybuffer'
    }
    socket = nextSocket
    openPromise = new Promise((resolve, reject) => {
      nextSocket.onopen = () => {
        openPromise = null
        resolve(nextSocket)
      }
      nextSocket.onmessage = (event) => {
        try {
          handleServerMessage(event.data)
        } catch (error: unknown) {
          reportSocketError(error)
        }
      }
      nextSocket.onerror = () => {
        const error = new Error('Live agent WebSocket connection failed')
        if (nextSocket.readyState !== SOCKET_OPEN) {
          openPromise = null
          reject(error)
        }
        reportSocketError(error)
      }
      nextSocket.onclose = () => {
        if (socket === nextSocket) {
          socket = null
        }
        openPromise = null
        rejectPendingCommands(new Error('Live agent WebSocket closed'))
        if (!intentionalClose) {
          reportSocketError(new Error('Live agent WebSocket closed'))
        }
      }
    })

    return openPromise
  }

  const sendCommand = async (
    command: AgentCommand,
    payload: Record<string, unknown>,
  ): Promise<ServerAckMessage> => {
    const commandId = `cmd-${++commandSeq}`
    const traceContext: LatencyTraceContext = {
      command_id: commandId,
      command,
      message_id: optionalString(payload.message_id),
      task_id: optionalString(payload.task_id),
      session_id: currentSessionId || undefined,
      generation: currentGeneration,
    }
    const envelope = {
      v: PROTOCOL_VERSION,
      kind: 'command',
      command_id: commandId,
      command,
      payload,
    }

    const ackPromise = new Promise<ServerAckMessage>((resolve, reject) => {
      pendingCommands.set(commandId, { command, traceContext, resolve, reject })
    })

    try {
      const liveSocket = await ensureSocket()
      if (liveSocket.readyState !== SOCKET_OPEN) {
        throw new Error('Live agent WebSocket is not open')
      }
      liveSocket.send(JSON.stringify(envelope))
      traceBrowserLatency('ws.command.sent', traceContext)
      if (command === 'task.cancel') {
        traceBrowserLatency('task.cancel.sent', traceContext)
      }
    } catch (error: unknown) {
      pendingCommands.delete(commandId)
      throw error
    }

    return ackPromise
  }

  const closeSocket = () => {
    intentionalClose = true
    resolvePendingCommandsForDispose()
    if (socket && socket.readyState !== SOCKET_CLOSED) {
      socket.close()
    }
    socket = null
    openPromise = null
  }

  return {
    start({ input, messageId, onEvent, onError }) {
      latestMessageId = messageId
      activeOnEvent = onEvent
      activeOnError = onError ?? null

      void sendCommand('agent.run', {
        query: input,
        message_id: messageId,
      }).catch((error: unknown) => {
        if (isDisposedSocketError(error)) {
          return
        }
        onError?.(error)
      })
    },

    async startVoice({ onEvent, onVoiceEvent, onVoiceAudio, onError }) {
      activeOnEvent = onEvent ?? null
      activeOnError = onError ?? null
      activeOnVoiceEvent = onVoiceEvent
      activeOnVoiceAudio = onVoiceAudio ?? null
      activeOnVoiceError = onError ?? null

      await sendCommand('voice.start', {})
    },

    async openVoiceMicrophone() {
      await sendCommand('voice.mic.open', {})
    },

    async closeVoiceMicrophone() {
      await sendCommand('voice.mic.close', {})
    },

    async notifyVoicePlaybackEnded() {
      await sendCommand('voice.playback.ended', {})
    },

    async stopVoice() {
      await sendCommand('voice.stop', {})
    },

    async sendVoiceTextQuery(input: string) {
      await sendCommand('voice.text.query', {
        query: input,
      })
    },

    async sendVoiceAudio(chunk: ArrayBuffer) {
      const liveSocket = await ensureSocket()
      if (liveSocket.readyState !== SOCKET_OPEN) {
        throw new Error('Live agent WebSocket is not open')
      }
      liveSocket.send(chunk)
    },

    async cancelTask(taskId: string) {
      const ack = await sendCommand('task.cancel', { task_id: taskId })
      const payload = asRecord(ack.payload)
      const outcome = asRecord(payload.outcome)
      const rawStatus = asString(outcome.status)
      const status = parseTaskCancelOutcomeStatus(rawStatus)
      const terminalStatus = asString(outcome.terminal_status).trim() || undefined
      const backendReason = asString(outcome.reason).trim() || undefined
      const reason = rawStatus === status
        ? backendReason
        : backendReason ?? `Unknown task cancel outcome: ${rawStatus || 'missing'}`
      return {
        status,
        taskId,
        terminalStatus,
        reason,
        requestedEvent: status === 'accepted'
          ? createAcceptedCancelEvent(taskId)
          : undefined,
      }
    },

    async resetSession(agentMode: AgentMode) {
      const ack = await sendCommand('session.reset', { agent_mode: agentMode })
      const payload = asRecord(ack.payload)
      tracedFirstDeltaMessageIds.clear()
      return {
        agentMode: asString(payload.agent_mode, agentMode) as AgentMode,
        runtimeProfile: asString(payload.runtime_profile) as RuntimeProfile,
      }
    },

    async resetRuntime(runtimeProfile: RuntimeProfile) {
      const ack = await sendCommand('session.reset', {
        runtime_profile: runtimeProfile,
      })
      const payload = asRecord(ack.payload)
      tracedFirstDeltaMessageIds.clear()
      return {
        agentMode: asString(payload.agent_mode, 'react') as AgentMode,
        runtimeProfile: asString(
          payload.runtime_profile,
          runtimeProfile,
        ) as RuntimeProfile,
      }
    },

    async checkHealth() {
      try {
        const response = await fetchImpl(`${baseUrl}/docs`, {
          method: 'HEAD',
          signal: AbortSignal.timeout(3000),
        })
        return response.ok
      } catch {
        return false
      }
    },

    dispose() {
      closeSocket()
    },
  }
}
