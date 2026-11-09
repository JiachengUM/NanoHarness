import { describe, expect, test, vi } from 'vitest'
import {
  createLiveAgentClient,
  normalizeBackendEvent,
  type BackendConsoleEvent,
} from './v2AgentClient'
import { PROTOCOL_VERSION } from './clientCommands'
import {
  applyVoiceEvent,
  initialVoiceState,
  openVoiceDraft,
} from '../voice/voiceReducer'

const timestamp = '2026-06-16T10:30:00'

function envelope(type: string, payload: Record<string, unknown> = {}): BackendConsoleEvent {
  return {
    id: `backend-${type}`,
    type,
    timestamp,
    payload: {
      event_id: `backend-${type}`,
      timestamp,
      type,
      ...payload,
    },
  }
}

describe('normalizeBackendEvent', () => {
  test('normalizes agent text events and preserves session-bound message ids', () => {
    expect(normalizeBackendEvent(envelope('agent.out.text.start'), 'agent-current')).toMatchObject({
      type: 'agent.text.start',
      messageId: 'agent-current',
    })
    expect(
      normalizeBackendEvent(
        envelope('agent.out.text.delta', {
          message_id: 'agent-previous',
          delta: 'partial',
        }),
        'agent-current',
      ),
    ).toMatchObject({
      type: 'agent.text.delta',
      messageId: 'agent-previous',
      delta: 'partial',
    })
    expect(normalizeBackendEvent(envelope('agent.out.text.done'), 'agent-current')).toMatchObject({
      type: 'agent.text.done',
      messageId: 'agent-current',
    })

    expect(
      normalizeBackendEvent(
        envelope('agent.out.text.delta', {
          message_id: 'task-result-poi-1',
          origin_message_id: 'agent-origin',
          source_task_id: 'poi-1',
          delta: '后台结果',
        }),
        'agent-current',
      ),
    ).toMatchObject({
      type: 'agent.text.delta',
      messageId: 'task-result-poi-1',
      originMessageId: 'agent-origin',
      sourceTaskId: 'poi-1',
      conversationTurnId: 'agent-origin',
      outputRunId: 'task-result-poi-1',
      triggeringTaskIds: ['poi-1'],
      delta: '后台结果',
    })
  })

  test('normalizes explicit multi-task correlation without inventing a turn', () => {
    expect(
      normalizeBackendEvent(
        envelope('agent.out.text.delta', {
          message_id: 'native-assistant-turn-2',
          conversation_turn_id: null,
          output_run_id: 'activation-1',
          triggering_task_ids: ['task-a', 'task-b', 'task-a', ''],
          delta: '聚合结果',
        }),
        'agent-current',
      ),
    ).toMatchObject({
      type: 'agent.text.delta',
      messageId: 'native-assistant-turn-2',
      outputRunId: 'activation-1',
      triggeringTaskIds: ['task-a', 'task-b'],
      delta: '聚合结果',
    })
    expect(
      normalizeBackendEvent(
        envelope('agent.out.text.delta', {
          conversation_turn_id: null,
          output_run_id: 'activation-1',
          triggering_task_ids: ['task-a'],
        }),
        'agent-current',
      ),
    ).not.toHaveProperty('conversationTurnId')
  })

  test('normalizes task events used by the task board projection', () => {
    expect(
      normalizeBackendEvent(
        envelope('task.created', {
          task_id: 'task-1',
          name: 'tool',
          arguments: { value: true },
          origin_message_id: 'agent-origin',
        }),
        'agent-current',
      ),
    ).toMatchObject({
      type: 'task.created',
      taskId: 'task-1',
      toolName: 'tool',
      arguments: { value: true },
      originMessageId: 'agent-origin',
    })
    expect(
      normalizeBackendEvent(envelope('task.progress', { task_id: 'task-1', progress: 60 }), 'agent-current'),
    ).toMatchObject({
      type: 'task.progress',
      taskId: 'task-1',
      progress: 60,
      message: '60%',
    })
    expect(
      normalizeBackendEvent(
        envelope('task.progress', {
          task_id: 'task-1',
          progress: {
            message: 'worker halfway',
            progress_percent: 45,
            phase: 'execution',
          },
        }),
        'agent-current',
      ),
    ).toMatchObject({
      type: 'task.progress',
      taskId: 'task-1',
      progress: 45,
      message: 'worker halfway',
      rawProgress: {
        message: 'worker halfway',
        phase: 'execution',
      },
    })
    expect(
      normalizeBackendEvent(envelope('task.success', { task_id: 'task-1', result: { ok: true } }), 'agent-current'),
    ).toMatchObject({
      type: 'task.success',
      taskId: 'task-1',
      result: { ok: true },
    })
    expect(
      normalizeBackendEvent(envelope('task.failure', { task_id: 'task-1', error: 'failed' }), 'agent-current'),
    ).toMatchObject({
      type: 'task.failure',
      taskId: 'task-1',
      error: 'failed',
    })
    expect(
      normalizeBackendEvent(envelope('task.cancelled', { task_id: 'task-1', reason: 'cancelled' }), 'agent-current'),
    ).toMatchObject({
      type: 'task.cancelled',
      taskId: 'task-1',
      reason: 'cancelled',
    })
  })

  test('ignores unknown backend events', () => {
    expect(normalizeBackendEvent(envelope('debug.trace'), 'agent-current')).toBeNull()
  })

  test('normalizes Plan definitions without dropping schema fields', () => {
    expect(normalizeBackendEvent(envelope('plan.created', {
      message_id: 'agent-1',
      round: 1,
      plan: {
        goal: 'find and navigate',
        steps: [{
          step_id: 'lookup',
          step_goal: 'find a place',
          op: '地点搜索工具',
          depends_on: [],
          inputs: { query: 'coffee' },
          outputs: {
            is_list: true,
            concept: { name: 'Place', attributes: [{ name: 'address' }] },
          },
          condition: null,
          success_check: '(.lookup.outputs.Place | length) > 0',
        }],
      },
    }), 'fallback')).toEqual(expect.objectContaining({
      type: 'plan.created',
      messageId: 'agent-1',
      round: 1,
      plan: {
        goal: 'find and navigate',
        steps: [expect.objectContaining({
          stepId: 'lookup',
          stepGoal: 'find a place',
          op: '地点搜索工具',
          dependsOn: [],
          rawInputs: { query: 'coffee' },
          outputSpec: expect.objectContaining({ is_list: true }),
          successCheck: '(.lookup.outputs.Place | length) > 0',
        })],
        raw: expect.any(Object),
      },
    }))
  })

  test('preserves all runtime evidence in plan.step.done', () => {
    const toolOutput = { data: [{ name: 'A' }], error: null }
    const conceptOutput = { Place: [{ name: 'A', address: 'full address' }] }
    const processError = { kind: 'projection', message: 'bad shape' }
    const unmet = {
      verdict: 'degraded',
      success_check: 'true',
      message: 'partial match',
      reason: 'only one candidate',
    }

    expect(normalizeBackendEvent(envelope('plan.step.done', {
      message_id: 'agent-1',
      round: 0,
      step_id: 'lookup',
      step_goal: 'find a place',
      raw_inputs: { query: '${user.query}' },
      resolved_inputs: { query: 'coffee' },
      tool_output: toolOutput,
      concept_output: conceptOutput,
      process_error: processError,
      unmet,
    }), 'fallback')).toEqual(expect.objectContaining({
      type: 'plan.step.done',
      rawInputs: { query: '${user.query}' },
      resolvedInputs: { query: 'coffee' },
      toolOutput,
      conceptOutput,
      processError,
      unmet,
    }))
  })

  test('normalizes plan step diagnosis started with an absent process error kind', () => {
    expect(normalizeBackendEvent(envelope('plan.step.diagnosis.started', {
      message_id: 'agent-1',
      round: 2,
      step_id: 'lookup',
      step_goal: 'find a place',
      success_check: '(.lookup.outputs.Place | length) > 0',
      failure_message: 'no candidates',
      process_error_kind: null,
    }), 'fallback')).toEqual({
      id: 'backend-plan.step.diagnosis.started',
      timestamp,
      messageId: 'agent-1',
      round: 2,
      type: 'plan.step.diagnosis.started',
      stepId: 'lookup',
      stepGoal: 'find a place',
      successCheck: '(.lookup.outputs.Place | length) > 0',
      failureMessage: 'no candidates',
      processErrorKind: undefined,
    })
  })

  test.each([
    'params',
    'condition',
    'execution',
    'projection',
  ] as const)('normalizes the %s diagnosis process error kind', (processErrorKind) => {
    expect(normalizeBackendEvent(envelope('plan.step.diagnosis.started', {
      message_id: 'agent-1',
      round: 2,
      step_id: 'lookup',
      step_goal: 'find a place',
      success_check: 'true',
      failure_message: `${processErrorKind} failed`,
      process_error_kind: processErrorKind,
    }), 'fallback')).toEqual(expect.objectContaining({
      type: 'plan.step.diagnosis.started',
      processErrorKind,
    }))
  })

  test('normalizes a completed replan diagnosis without guessing fields', () => {
    expect(normalizeBackendEvent(envelope('plan.step.diagnosis.completed', {
      message_id: 'agent-1',
      round: 2,
      step_id: 'lookup',
      step_goal: 'find a place',
      source: 'llm',
      decision: {
        outcome: 'replan',
        failed_assumption: 'the search radius was sufficient',
        retry_direction: 'expand the search radius',
      },
    }), 'fallback')).toEqual({
      id: 'backend-plan.step.diagnosis.completed',
      timestamp,
      messageId: 'agent-1',
      round: 2,
      type: 'plan.step.diagnosis.completed',
      stepId: 'lookup',
      stepGoal: 'find a place',
      source: 'llm',
      decision: {
        outcome: 'replan',
        failedAssumption: 'the search radius was sufficient',
        retryDirection: 'expand the search radius',
      },
    })
  })

  test.each([
    [
      'skip_unsolvable',
      {
        outcome: 'skip_unsolvable',
        unsolvable_reason: 'the requested place does not exist',
      },
      {
        outcome: 'skip_unsolvable',
        unsolvableReason: 'the requested place does not exist',
      },
    ],
    [
      'accept_degraded',
      {
        outcome: 'accept_degraded',
        limitation: 'route duration is unavailable',
      },
      {
        outcome: 'accept_degraded',
        limitation: 'route duration is unavailable',
      },
    ],
  ])('normalizes a completed %s diagnosis decision', (_, decision, expected) => {
    expect(normalizeBackendEvent(envelope('plan.step.diagnosis.completed', {
      message_id: 'agent-1',
      round: 2,
      step_id: 'lookup',
      step_goal: 'find a place',
      source: 'rule',
      decision,
    }), 'fallback')).toEqual(expect.objectContaining({
      type: 'plan.step.diagnosis.completed',
      source: 'rule',
      decision: expected,
    }))
  })

  test('rejects a completed diagnosis with an invalid source before its decision', () => {
    expect(() => normalizeBackendEvent(envelope('plan.step.diagnosis.completed', {
      message_id: 'agent-1',
      round: 2,
      step_id: 'lookup',
      step_goal: 'find a place',
      source: 'cache',
      decision: {
        outcome: 'replan',
        failed_assumption: 'the search radius was sufficient',
        retry_direction: 'expand the search radius',
      },
    }), 'fallback')).toThrow(/source/)
  })

  test('rejects a completed diagnosis with an unknown outcome', () => {
    expect(() => normalizeBackendEvent(envelope('plan.step.diagnosis.completed', {
      message_id: 'agent-1',
      round: 2,
      step_id: 'lookup',
      step_goal: 'find a place',
      source: 'rule',
      decision: { outcome: 'retry_step' },
    }), 'fallback')).toThrow('Invalid plan.step.diagnosis.completed outcome')
  })

  test('rejects invalid diagnosis process kinds and missing decision fields', () => {
    expect(() => normalizeBackendEvent(envelope('plan.step.diagnosis.started', {
      message_id: 'agent-1',
      round: 2,
      step_id: 'lookup',
      step_goal: 'find a place',
      success_check: 'true',
      failure_message: 'projection failed',
      process_error_kind: 'timeout',
    }), 'fallback')).toThrow(/process_error_kind/)

    expect(() => normalizeBackendEvent(envelope('plan.step.diagnosis.completed', {
      message_id: 'agent-1',
      round: 2,
      step_id: 'lookup',
      step_goal: 'find a place',
      source: 'fallback',
      decision: {
        outcome: 'replan',
        failed_assumption: 'the search radius was sufficient',
      },
    }), 'fallback')).toThrow(/retry_direction/)
  })

  describe.each([
    [
      'plan.step.diagnosis.started',
      {
        step_id: 'lookup',
        step_goal: 'find a place',
        success_check: 'true',
        failure_message: 'no candidates',
        process_error_kind: null,
      },
    ],
    [
      'plan.step.diagnosis.completed',
      {
        step_id: 'lookup',
        step_goal: 'find a place',
        source: 'rule',
        decision: {
          outcome: 'accept_degraded',
          limitation: 'route duration is unavailable',
        },
      },
    ],
  ] as const)('%s context validation', (type, payload) => {
    test.each([
      ['missing message_id', { round: 0 }],
      ['empty message_id', { message_id: '', round: 0 }],
      ['missing round', { message_id: 'agent-1' }],
      ['non-integer round', { message_id: 'agent-1', round: 1.5 }],
      ['negative round', { message_id: 'agent-1', round: -1 }],
    ] as const)('throws for %s', (invalidContext, context) => {
      const invalidField = invalidContext.includes('message_id')
        ? 'message_id'
        : 'round'

      expect(() => normalizeBackendEvent(envelope(type, {
        ...payload,
        ...context,
      }), 'fallback')).toThrow(invalidField)
    })
  })

  test('rejects Plan events without explicit transport correlation', () => {
    expect(normalizeBackendEvent(envelope('plan.created', {
      round: 0,
      plan: { goal: 'misattributed', steps: [] },
    }), 'agent-latest')).toBeNull()
    expect(normalizeBackendEvent(envelope('plan.created', {
      message_id: 'agent-1',
      plan: { goal: 'missing round', steps: [] },
    }), 'agent-latest')).toBeNull()
    expect(normalizeBackendEvent(envelope('plan.created', {
      message_id: 'agent-1',
      round: -1,
      plan: { goal: 'invalid round', steps: [] },
    }), 'agent-latest')).toBeNull()
  })
})

class FakeAgentWebSocket {
  readyState = 0
  binaryType?: BinaryType
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  sent: Array<string | ArrayBuffer> = []

  constructor(readonly url: string) {}

  open() {
    this.readyState = 1
    this.onopen?.(new Event('open'))
  }

  receive(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) } as MessageEvent)
  }

  receiveRaw(data: unknown) {
    this.onmessage?.({ data } as MessageEvent)
  }

  send(data: string | ArrayBuffer) {
    this.sent.push(data)
  }

  close() {
    this.readyState = 3
    this.onclose?.({} as CloseEvent)
  }
}

function websocketHarness() {
  let socket: FakeAgentWebSocket | null = null
  const webSocketFactory = vi.fn((url: string) => {
    socket = new FakeAgentWebSocket(url)
    return socket
  })
  return {
    webSocketFactory,
    socket: () => {
      if (!socket) {
        throw new Error('WebSocket was not created')
      }
      return socket
    },
  }
}

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
}

function sentText(socket: FakeAgentWebSocket, index: number): string {
  const data = socket.sent[index]
  if (typeof data !== 'string') {
    throw new Error(`Expected sent[${index}] to be a string command`)
  }
  return data
}

function receiveHello(
  socket: FakeAgentWebSocket,
  sessionId = 'voice-session-1',
  generation = 1,
) {
  socket.receive({
    v: PROTOCOL_VERSION,
    kind: 'hello',
    connection_id: 'connection-1',
    session_id: sessionId,
    generation,
  })
}

function receiveVoiceEvent(
  socket: FakeAgentWebSocket,
  type: string,
  payload: Record<string, unknown>,
  sessionId = 'voice-session-1',
  generation = 1,
) {
  socket.receive({
    v: 1,
    kind: 'voice',
    session_id: sessionId,
    generation,
    type,
    payload,
  })
}

function latencyRecords(info: ReturnType<typeof vi.spyOn>): Array<Record<string, unknown>> {
  return info.mock.calls
    .filter((call) => call[0] === '[v2-latency]')
    .map((call) => call[1] as Record<string, unknown>)
}

test('live agent client sends the frontend message id over a WebSocket command', async () => {
  const harness = websocketHarness()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  client.start({
    input: 'hello',
    messageId: 'agent-current',
    onEvent: vi.fn(),
  })
  harness.socket().open()
  await flushPromises()

  expect(harness.webSocketFactory).toHaveBeenCalledWith('ws://backend.test/v2/frontend/ws')
  const command = JSON.parse(sentText(harness.socket(), 0))
  expect(command).toMatchObject({
    v: PROTOCOL_VERSION,
    kind: 'command',
    command: 'agent.run',
    payload: {
      query: 'hello',
      message_id: 'agent-current',
    },
  })
  expect(command.command_id).toEqual(expect.any(String))
  expect(command.command_id).not.toBe('agent-current')
})

test('live agent client preserves a same-origin backend mount prefix', async () => {
  const harness = websocketHarness()
  const fetchImpl = vi.fn(async () => ({ ok: true }) as Response)
  vi.stubGlobal('window', {
    location: {
      origin: 'https://mind.example.test',
    },
  })

  try {
    const client = createLiveAgentClient({
      baseUrl: '/api/v2-agent',
      fetchImpl,
      webSocketFactory: harness.webSocketFactory,
    })

    client.start({
      input: 'hello',
      messageId: 'agent-mounted',
      onEvent: vi.fn(),
    })
    harness.socket().open()
    await flushPromises()

    expect(harness.webSocketFactory).toHaveBeenCalledWith(
      'wss://mind.example.test/api/v2-agent/v2/frontend/ws',
    )
    await expect(client.checkHealth()).resolves.toBe(true)
    expect(fetchImpl).toHaveBeenCalledWith(
      '/api/v2-agent/docs',
      expect.objectContaining({ method: 'HEAD' }),
    )
    client.dispose()
  } finally {
    vi.unstubAllGlobals()
  }
})

test('live agent client normalizes WebSocket event messages', async () => {
  const harness = websocketHarness()
  const onEvent = vi.fn()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  client.start({
    input: 'hello',
    messageId: 'agent-current',
    onEvent,
  })
  harness.socket().open()
  await flushPromises()

  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'event',
    event: envelope('agent.out.text.delta', {
      message_id: 'agent-current',
      delta: 'partial',
    }),
  })

  expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({
    type: 'agent.text.delta',
    messageId: 'agent-current',
    delta: 'partial',
  }))
})

test('live agent client reports malformed completed diagnoses through onError', async () => {
  const harness = websocketHarness()
  const onEvent = vi.fn()
  const onError = vi.fn()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  client.start({
    input: 'hello',
    messageId: 'agent-current',
    onEvent,
    onError,
  })
  harness.socket().open()
  await flushPromises()

  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'event',
    event: envelope('plan.step.diagnosis.completed', {
      message_id: 'agent-current',
      round: 0,
      step_id: 'lookup',
      step_goal: 'find a place',
      source: 'llm',
      decision: { outcome: 'retry_step' },
    }),
  })

  expect(onError).toHaveBeenCalledOnce()
  expect(onError).toHaveBeenCalledWith(expect.objectContaining({
    message: expect.stringContaining('Invalid plan.step.diagnosis.completed outcome'),
  }))
  expect(onEvent).not.toHaveBeenCalled()
})

test.each([
  [
    'plan.step.diagnosis.started',
    {
      step_id: 'lookup',
      step_goal: 'find a place',
      success_check: 'true',
      failure_message: 'no candidates',
      process_error_kind: null,
    },
  ],
  [
    'plan.step.diagnosis.completed',
    {
      step_id: 'lookup',
      step_goal: 'find a place',
      source: 'rule',
      decision: {
        outcome: 'accept_degraded',
        limitation: 'route duration is unavailable',
      },
    },
  ],
] as const)('live agent client reports invalid context for %s through onError', async (type, payload) => {
  const harness = websocketHarness()
  const onEvent = vi.fn()
  const onError = vi.fn()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  client.start({
    input: 'hello',
    messageId: 'agent-current',
    onEvent,
    onError,
  })
  harness.socket().open()
  await flushPromises()

  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'event',
    event: envelope(type, { ...payload, round: 0 }),
  })

  expect(onError).toHaveBeenCalledOnce()
  expect(onError).toHaveBeenCalledWith(expect.objectContaining({
    message: expect.stringContaining('message_id'),
  }))
  expect(onEvent).not.toHaveBeenCalled()
})

test('live agent client traces commands, first delta, and task cancellation by ids', async () => {
  const info = vi.spyOn(console, 'info').mockImplementation(() => undefined)
  const harness = websocketHarness()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  client.start({ input: 'sensitive user text', messageId: 'agent-current', onEvent: vi.fn() })
  harness.socket().open()
  await flushPromises()

  const runCommand = JSON.parse(sentText(harness.socket(), 0))
  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: runCommand.command_id,
    command: 'agent.run',
    ok: true,
    status: 'accepted',
    payload: { message_id: 'agent-current', session_id: 'sess-1', generation: 3 },
  })
  harness.socket().receive({
    kind: 'event',
    event: envelope('agent.out.text.delta', { message_id: 'agent-current', delta: 'first' }),
  })
  harness.socket().receive({
    kind: 'event',
    event: envelope('agent.out.text.delta', { message_id: 'agent-current', delta: 'second' }),
  })

  const cancelOperation = client.cancelTask('task-1')
  await flushPromises()
  const cancelCommand = JSON.parse(sentText(harness.socket(), 1))
  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: cancelCommand.command_id,
    command: 'task.cancel',
    ok: true,
    status: 'completed',
    payload: { task_id: 'task-1', outcome: { status: 'accepted' } },
  })
  await cancelOperation
  harness.socket().receive({
    kind: 'event',
    event: envelope('task.cancelled', { task_id: 'task-1', reason: 'cancelled' }),
  })

  const records = latencyRecords(info)
  expect(records).toEqual(expect.arrayContaining([
    expect.objectContaining({
      event: 'ws.command.sent',
      command_id: runCommand.command_id,
      command: 'agent.run',
      message_id: 'agent-current',
    }),
    expect.objectContaining({
      event: 'ws.command.ack',
      command_id: runCommand.command_id,
      command: 'agent.run',
    }),
    expect.objectContaining({ event: 'task.cancel.sent', task_id: 'task-1' }),
    expect.objectContaining({ event: 'task.cancelled.received', task_id: 'task-1' }),
  ]))
  expect(records.filter((record) => record.event === 'agent.first_delta')).toEqual([
    expect.objectContaining({ message_id: 'agent-current' }),
  ])
  expect(JSON.stringify(records)).not.toContain('sensitive user text')

  client.dispose()
  info.mockRestore()
})

test('live agent client traces voice ready and sticky interruption receipt', async () => {
  const info = vi.spyOn(console, 'info').mockImplementation(() => undefined)
  const harness = websocketHarness()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  const operation = client.startVoice({ onVoiceEvent: vi.fn() })
  harness.socket().open()
  receiveHello(harness.socket(), 'sess-voice', 4)
  await flushPromises()
  const command = JSON.parse(sentText(harness.socket(), 0))
  harness.socket().receive({
    v: 1,
    kind: 'voice',
    session_id: 'sess-voice',
    generation: 4,
    type: 'voice.ready',
    payload: {},
  })
  harness.socket().receive({
    v: 1,
    kind: 'voice',
    session_id: 'sess-voice',
    generation: 4,
    type: 'voice.interrupted',
    payload: { message_id: 'agent-old' },
  })
  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: command.command_id,
    command: 'voice.start',
    ok: true,
    status: 'completed',
    payload: {},
  })
  await operation

  expect(latencyRecords(info)).toEqual(expect.arrayContaining([
    expect.objectContaining({
      event: 'voice.ready',
      session_id: 'sess-voice',
      generation: 4,
    }),
    expect.objectContaining({
      event: 'voice.interrupted.received',
      message_id: 'agent-old',
      session_id: 'sess-voice',
      generation: 4,
    }),
  ]))

  client.dispose()
  info.mockRestore()
})

test('live agent client does not report pending agent run as failed during disposal', async () => {
  const harness = websocketHarness()
  const onError = vi.fn()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  client.start({
    input: 'hello',
    messageId: 'agent-current',
    onEvent: vi.fn(),
    onError,
  })
  harness.socket().open()
  await flushPromises()

  client.dispose()
  await flushPromises()

  expect(onError).not.toHaveBeenCalled()
})

test('live agent client resolves pending control commands during disposal', async () => {
  const harness = websocketHarness()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  const stopPromise = client.stopVoice()
  harness.socket().open()
  await flushPromises()

  client.dispose()

  await expect(stopPromise).resolves.toBeUndefined()
})

test('live agent client resolves task cancel from WebSocket ack outcome', async () => {
  vi.setSystemTime(new Date('2026-06-16T10:32:00.000Z'))
  const harness = websocketHarness()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  const cancelPromise = client.cancelTask('task-1')
  harness.socket().open()
  await flushPromises()

  const command = JSON.parse(sentText(harness.socket(), 0))
  expect(command).toMatchObject({
    kind: 'command',
    command: 'task.cancel',
    payload: { task_id: 'task-1' },
  })

  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: command.command_id,
    command: 'task.cancel',
    ok: true,
    status: 'completed',
    payload: {
      task_id: 'task-1',
      outcome: { status: 'accepted' },
    },
  })

  await expect(cancelPromise).resolves.toMatchObject({
    status: 'accepted',
    taskId: 'task-1',
    requestedEvent: {
      id: 'live-cancel-request-task-1',
      type: 'task.cancel.requested',
      taskId: 'task-1',
    },
  })
  vi.useRealTimers()
})

test('live agent client preserves a terminal task cancel outcome without faking cancellation', async () => {
  const harness = websocketHarness()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  const cancelPromise = client.cancelTask('task-finished')
  harness.socket().open()
  await flushPromises()

  const command = JSON.parse(sentText(harness.socket(), 0))
  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: command.command_id,
    command: 'task.cancel',
    ok: true,
    status: 'completed',
    payload: {
      task_id: 'task-finished',
      outcome: {
        status: 'already_terminal',
        terminal_status: 'success',
      },
    },
  })

  await expect(cancelPromise).resolves.toEqual({
    status: 'already_terminal',
    taskId: 'task-finished',
    terminalStatus: 'success',
    reason: undefined,
    requestedEvent: undefined,
  })
})

test('live agent client sends the selected mode in the v2 session reset command', async () => {
  const harness = websocketHarness()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  const resetPromise = client.resetSession('react')
  harness.socket().open()
  await flushPromises()

  const command = JSON.parse(sentText(harness.socket(), 0))
  expect(command).toMatchObject({
    v: PROTOCOL_VERSION,
    kind: 'command',
    command: 'session.reset',
    payload: { agent_mode: 'react' },
  })

  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: command.command_id,
    command: 'session.reset',
    ok: true,
    status: 'completed',
    payload: {
      session_id: 'sess-new',
      generation: 2,
      agent_mode: 'react',
      runtime_profile: 'react_duplex_shell',
    },
  })

  await expect(resetPromise).resolves.toEqual({
    agentMode: 'react',
    runtimeProfile: 'react_duplex_shell',
  })
})

test('live agent client sends the selected runtime profile in session reset', async () => {
  const harness = websocketHarness()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  const resetPromise = client.resetRuntime('duplex_native')
  harness.socket().open()
  await flushPromises()

  const command = JSON.parse(sentText(harness.socket(), 0))
  expect(command).toMatchObject({
    v: PROTOCOL_VERSION,
    kind: 'command',
    command: 'session.reset',
    payload: { runtime_profile: 'duplex_native' },
  })

  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: command.command_id,
    command: 'session.reset',
    ok: true,
    status: 'completed',
    payload: {
      session_id: 'sess-native',
      generation: 2,
      agent_mode: 'react',
      runtime_profile: 'duplex_native',
    },
  })

  await expect(resetPromise).resolves.toEqual({
    agentMode: 'react',
    runtimeProfile: 'duplex_native',
  })
})

test('live agent client starts voice and dispatches voice events from the shared WebSocket', async () => {
  const harness = websocketHarness()
  const onVoiceEvent = vi.fn()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  const startPromise = client.startVoice({ onVoiceEvent })
  harness.socket().open()
  receiveHello(harness.socket())
  await flushPromises()

  expect(harness.socket().binaryType).toBe('arraybuffer')
  const command = JSON.parse(harness.socket().sent[0] as string)
  expect(command).toMatchObject({
    v: PROTOCOL_VERSION,
    kind: 'command',
    command: 'voice.start',
    payload: {},
  })

  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: command.command_id,
    command: 'voice.start',
    ok: true,
    status: 'completed',
    payload: {
      sample_rate: 16000,
    },
  })

  await expect(startPromise).resolves.toBeUndefined()

  harness.socket().receive({
    v: 1,
    kind: 'voice',
    session_id: 'voice-session-1',
    generation: 1,
    type: 'voice.asr.delta',
    payload: {
      text: 'partial voice',
    },
  })

  expect(onVoiceEvent).toHaveBeenCalledWith({
    v: 1,
    kind: 'voice',
    type: 'voice.asr.delta',
    payload: {
      text: 'partial voice',
    },
  })
})

test('live agent client preserves the backend speaking voice phase', async () => {
  const harness = websocketHarness()
  const onVoiceEvent = vi.fn()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })
  const startPromise = client.startVoice({ onVoiceEvent })
  harness.socket().open()
  receiveHello(harness.socket())
  await flushPromises()
  const startCommand = JSON.parse(sentText(harness.socket(), 0))
  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: startCommand.command_id,
    command: 'voice.start',
    ok: true,
    status: 'completed',
    payload: {},
  })
  await startPromise

  receiveVoiceEvent(harness.socket(), 'voice.phase', { phase: 'speaking' })

  expect(onVoiceEvent).toHaveBeenCalledWith({
    v: 1,
    kind: 'voice',
    type: 'voice.phase',
    payload: { phase: 'speaking' },
  })
})

test('voice final establishes Agent message correlation before text events arrive', async () => {
  const harness = websocketHarness()
  const onEvent = vi.fn()
  const onVoiceEvent = vi.fn()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })
  const startPromise = client.startVoice({ onEvent, onVoiceEvent })
  harness.socket().open()
  receiveHello(harness.socket())
  await flushPromises()
  const startCommand = JSON.parse(sentText(harness.socket(), 0))
  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: startCommand.command_id,
    command: 'voice.start',
    ok: true,
    status: 'completed',
    payload: {},
  })
  await startPromise

  receiveVoiceEvent(harness.socket(), 'voice.asr.final', {
    turn_id: 'turn-1',
    user_message_id: 'user-1',
    assistant_message_id: 'assistant-voice-1',
    text: '查一下天气',
  })
  harness.socket().receive({
    kind: 'event',
    event: envelope('agent.out.text.delta', { delta: '晴天' }),
  })

  expect(onVoiceEvent).toHaveBeenCalledOnce()
  expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({
    type: 'agent.text.delta',
    messageId: 'assistant-voice-1',
    delta: '晴天',
  }))
})

test.each([
  ['wrong version', { v: PROTOCOL_VERSION - 1, command: 'voice.stop', ok: true, status: 'completed' }],
  ['wrong command', { v: PROTOCOL_VERSION, command: 'voice.start', ok: true, status: 'completed' }],
  ['wrong success status', { v: PROTOCOL_VERSION, command: 'voice.stop', ok: true, status: 'accepted' }],
  ['inconsistent rejection', { v: PROTOCOL_VERSION, command: 'voice.stop', ok: false, status: 'completed' }],
] as const)('matched command rejects a malformed ACK with %s', async (_, ackFields) => {
  const harness = websocketHarness()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })
  const stopPromise = client.stopVoice()
  harness.socket().open()
  await flushPromises()
  const stopCommand = JSON.parse(sentText(harness.socket(), 0))

  harness.socket().receive({
    kind: 'ack',
    command_id: stopCommand.command_id,
    payload: {},
    ...ackFields,
  })

  await expect(stopPromise).rejects.toThrow(/Invalid ACK/)
})

test('live agent client sends voice text query commands', async () => {
  const harness = websocketHarness()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  const queryPromise = client.sendVoiceTextQuery('hello text')
  harness.socket().open()
  await flushPromises()

  const command = JSON.parse(sentText(harness.socket(), 0))
  expect(command).toMatchObject({
    v: PROTOCOL_VERSION,
    kind: 'command',
    command: 'voice.text.query',
    payload: {
      query: 'hello text',
    },
  })

  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: command.command_id,
    command: 'voice.text.query',
    ok: true,
    status: 'completed',
    payload: {},
  })

  await expect(queryPromise).resolves.toBeUndefined()
})

test('live agent client sends voice audio after the shared WebSocket opens', async () => {
  const harness = websocketHarness()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })
  const chunk = new ArrayBuffer(4)

  const sendPromise = client.sendVoiceAudio(chunk)
  expect(harness.socket().sent).toHaveLength(0)

  harness.socket().open()
  await expect(sendPromise).resolves.toBeUndefined()

  expect(harness.socket().sent).toEqual([chunk])
})

test('live agent client dispatches incoming binary voice audio from the shared WebSocket', async () => {
  const harness = websocketHarness()
  const onVoiceAudio = vi.fn()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })
  const chunk = new ArrayBuffer(8)

  const startPromise = client.startVoice({
    onVoiceEvent: vi.fn(),
    onVoiceAudio,
  })
  harness.socket().open()
  await flushPromises()

  const command = JSON.parse(harness.socket().sent[0] as string)
  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: command.command_id,
    command: 'voice.start',
    ok: true,
    status: 'completed',
    payload: {},
  })
  await expect(startPromise).resolves.toBeUndefined()

  harness.socket().receiveRaw(chunk)

  expect(onVoiceAudio).toHaveBeenCalledWith(chunk)
})

test('live agent client sends voice microphone control commands and resolves their acks', async () => {
  const harness = websocketHarness()
  const client = createLiveAgentClient({
    baseUrl: 'http://backend.test',
    webSocketFactory: harness.webSocketFactory,
  })

  const openPromise = client.openVoiceMicrophone()
  harness.socket().open()
  await flushPromises()
  const openCommand = JSON.parse(harness.socket().sent[0] as string)
  expect(openCommand).toMatchObject({
    kind: 'command',
    command: 'voice.mic.open',
    payload: {},
  })
  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: openCommand.command_id,
    command: 'voice.mic.open',
    ok: true,
    status: 'completed',
    payload: {},
  })
  await expect(openPromise).resolves.toBeUndefined()

  const closePromise = client.closeVoiceMicrophone()
  await flushPromises()
  const closeCommand = JSON.parse(harness.socket().sent[1] as string)
  expect(closeCommand).toMatchObject({
    kind: 'command',
    command: 'voice.mic.close',
    payload: {},
  })
  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: closeCommand.command_id,
    command: 'voice.mic.close',
    ok: true,
    status: 'completed',
    payload: {},
  })
  await expect(closePromise).resolves.toBeUndefined()

  const stopPromise = client.stopVoice()
  await flushPromises()
  const stopCommand = JSON.parse(harness.socket().sent[2] as string)
  expect(stopCommand).toMatchObject({
    kind: 'command',
    command: 'voice.stop',
    payload: {},
  })
  harness.socket().receive({
    v: PROTOCOL_VERSION,
    kind: 'ack',
    command_id: stopCommand.command_id,
    command: 'voice.stop',
    ok: true,
    status: 'completed',
    payload: {},
  })
  await expect(stopPromise).resolves.toBeUndefined()
})
