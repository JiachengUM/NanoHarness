import { describe, expect, it } from 'vitest'
import {
  createVisualizerClient,
  type VisualizerWebSocket,
} from './visualizerClient'

/** 可编程 mock WebSocket：记录发送，测试手动触发 onmessage。 */
class MockWebSocket implements VisualizerWebSocket {
  readyState = 1 // 默认已打开（由 factory 后手动置 0 模拟连接过程）
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  sent: string[] = []

  constructor(public url: string) {}

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.readyState = 3
    this.onclose?.({} as CloseEvent)
  }

  /** 模拟服务器下行消息。 */
  serverMessage(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }

  /** 模拟连接打开。 */
  serverAccept(): void {
    this.readyState = 1
    this.onopen?.({} as Event)
    this.serverMessage({ kind: 'hello', server_time: '2026-08-26T10:00:00' })
  }
}

describe('createVisualizerClient', () => {
  it('连接后 listCases 收到 ACK 并归一化 case 列表', async () => {
    let mock: MockWebSocket | null = null
    const client = createVisualizerClient({
      url: 'ws://test/ws',
      webSocketFactory: (url) => {
        mock = new MockWebSocket(url)
        return mock
      },
    })
    const connectPromise = client.connect()
    mock!.serverAccept()
    await connectPromise

    const casesPromise = client.listCases()
    await new Promise((resolve) => setTimeout(resolve, 0)) // 等 send 执行（命令在 await 后发出）
    const sent = JSON.parse(mock!.sent[0])
    expect(sent.kind).toBe('command')
    expect(sent.command).toBe('list_cases')
    mock!.serverMessage({
      kind: 'ack',
      command_id: sent.command_id,
      ok: true,
      status: 'completed',
      payload: {
        cases: [
          { id: 'c1', case_name: '开空调', case_description: 'd1' },
          { id: 'c2', case_name: '时间加速', case_description: 'd2' },
        ],
      },
    })
    const cases = await casesPromise
    expect(cases).toEqual([
      { id: 'c1', caseName: '开空调', caseDescription: 'd1' },
      { id: 'c2', caseName: '时间加速', caseDescription: 'd2' },
    ])
    client.dispose()
  })

  it('事件流：onEvent 收到归一化事件（含 mock_time）', async () => {
    let mock: MockWebSocket | null = null
    const client = createVisualizerClient({
      url: 'ws://test/ws',
      webSocketFactory: (url) => {
        mock = new MockWebSocket(url)
        return mock
      },
    })
    const events: unknown[] = []
    client.onEvent((event) => events.push(event))
    const connectPromise = client.connect()
    mock!.serverAccept()
    await connectPromise

    mock!.serverMessage({
      kind: 'event',
      event: {
        seq: 3,
        wall_time: '2026-08-26T10:00:00',
        mock_time: '2026-08-26T10:00:05',
        kind: 'assistant_delta',
        payload: { delta: '好的' },
      },
    })
    expect(events).toHaveLength(1)
    expect(events[0]).toMatchObject({
      type: 'assistant_delta',
      seq: 3,
      delta: '好的',
    })
    client.dispose()
  })

  it('runCase 发送完整参数且 ACK 失败时 reject', async () => {
    let mock: MockWebSocket | null = null
    const client = createVisualizerClient({
      url: 'ws://test/ws',
      webSocketFactory: (url) => {
        mock = new MockWebSocket(url)
        return mock
      },
    })
    const connectPromise = client.connect()
    mock!.serverAccept()
    await connectPromise

    const runPromise = client.runCase({
      caseId: 'builtin-interrupt',
      assistantKind: 'v2',
      fastMode: true,
    })
    await new Promise((resolve) => setTimeout(resolve, 0)) // 等 send 执行
    const sent = JSON.parse(mock!.sent[0])
    expect(sent.command).toBe('run_case')
    expect(sent.payload).toEqual({
      case_id: 'builtin-interrupt',
      assistant_kind: 'v2',
      chunk_delay: 0.05,
      fast_mode: true,
      use_streaming: true,
    })
    mock!.serverMessage({
      kind: 'ack',
      command_id: sent.command_id,
      ok: false,
      status: 'rejected',
      payload: { message: '已有 case 正在运行，请先停止' },
    })
    await expect(runPromise).rejects.toThrow('已有 case 正在运行')
    client.dispose()
  })

  it('断线时 pending 命令被 reject 且连接状态变 closed', async () => {
    let mock: MockWebSocket | null = null
    const client = createVisualizerClient({
      url: 'ws://test/ws',
      webSocketFactory: (url) => {
        mock = new MockWebSocket(url)
        return mock
      },
    })
    const states: string[] = []
    client.onConnectionChange((state) => states.push(state))
    const connectPromise = client.connect()
    mock!.serverAccept()
    await connectPromise

    const casesPromise = client.listCases()
    mock!.onclose?.({} as CloseEvent)
    await expect(casesPromise).rejects.toThrow('断开')
    expect(states).toContain('closed')
    client.dispose()
  })
})
