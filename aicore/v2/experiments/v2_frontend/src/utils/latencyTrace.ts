export type BrowserLatencyEvent =
  | 'ui.submit'
  | 'ws.command.sent'
  | 'ws.command.ack'
  | 'agent.first_delta'
  | 'voice.ready'
  | 'tts.playback.start'
  | 'voice.interrupted.received'
  | 'tts.playback.stop'
  | 'task.cancel.sent'
  | 'task.cancelled.received'

export interface LatencyTraceContext {
  command_id?: string
  command?: string
  message_id?: string
  origin_message_id?: string
  task_id?: string
  session_id?: string
  generation?: number
}

export interface BrowserLatencyTrace extends LatencyTraceContext {
  event: BrowserLatencyEvent
  clock: 'browser'
  at_ms: number
}

export function buildBrowserLatencyTrace(
  event: BrowserLatencyEvent,
  context: LatencyTraceContext = {},
  atMs = performance.now(),
): BrowserLatencyTrace {
  const record: BrowserLatencyTrace = {
    event,
    clock: 'browser',
    at_ms: atMs,
  }

  if (context.command_id !== undefined) record.command_id = context.command_id
  if (context.command !== undefined) record.command = context.command
  if (context.message_id !== undefined) record.message_id = context.message_id
  if (context.origin_message_id !== undefined) {
    record.origin_message_id = context.origin_message_id
  }
  if (context.task_id !== undefined) record.task_id = context.task_id
  if (context.session_id !== undefined) record.session_id = context.session_id
  if (context.generation !== undefined) record.generation = context.generation

  return record
}

export function traceBrowserLatency(
  event: BrowserLatencyEvent,
  context: LatencyTraceContext = {},
): BrowserLatencyTrace {
  const record = buildBrowserLatencyTrace(event, context)
  console.info('[v2-latency]', record)
  return record
}
