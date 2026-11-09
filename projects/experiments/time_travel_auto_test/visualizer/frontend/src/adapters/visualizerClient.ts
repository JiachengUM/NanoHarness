/**
 * 可视化 WS 客户端：命令-ACK + 事件流（对齐 run_server.py 协议）。
 *
 * 协议（单条 WebSocket，为语音测试预留多路复用）：
 * - 上行: {kind:"command", command_id, command, payload}
 *   - list_cases / run_case / stop_case
 * - 下行:
 *   - {kind:"hello", server_time}
 *   - {kind:"event", event: 信封}   → onEvent(normalizeEvent(...))
 *   - {kind:"ack", command_id, ok, status, payload}
 *   - {kind:"error", message}
 */
import {
  normalizeEvent,
  type EventEnvelope,
  type VisualizerEvent,
} from '../domain/events'
import { asRecord, asString, errorMessage } from '../utils/unknown'

export interface CaseSummary {
  id: string
  caseName: string
  caseDescription: string
}

export interface RunCaseOptions {
  caseId: string
  assistantKind?: 'mock' | 'v2' | 'adapter_v2' | 'v2_adapter'
  chunkDelay?: number
  fastMode?: boolean
  useStreaming?: boolean
}

export type ConnectionState = 'connecting' | 'open' | 'closed'

export interface VisualizerClientOptions {
  /** ws://host/ws；默认从 location 推导（dev 走 vite 代理，生产同源挂载）。 */
  url?: string
  webSocketFactory?: (url: string) => VisualizerWebSocket
  now?: () => string
}

export interface VisualizerClient {
  connect(): Promise<void>
  listCases(): Promise<CaseSummary[]>
  runCase(options: RunCaseOptions): Promise<{ caseId: string }>
  stopCase(): Promise<{ wasRunning: boolean }>
  judgeCase(): Promise<void>
  onEvent(listener: (event: VisualizerEvent) => void): void
  onConnectionChange(listener: (state: ConnectionState) => void): void
  onError(listener: (message: string) => void): void
  dispose(): void
}

/** 最小 WebSocket 接口（便于测试注入 mock）。 */
export interface VisualizerWebSocket {
  readyState: number
  onopen: ((event: Event) => void) | null
  onmessage: ((event: MessageEvent) => void) | null
  onerror: ((event: Event) => void) | null
  onclose: ((event: CloseEvent) => void) | null
  send(data: string): void
  close(): void
}

interface AckMessage {
  commandId: string
  ok: boolean
  status: string
  payload: Record<string, unknown>
  message: string
}

interface PendingCommand {
  resolve(ack: AckMessage): void
  reject(error: Error): void
}

const SOCKET_CONNECTING = 0
const SOCKET_OPEN = 1

function defaultWebSocketUrl(): string {
  const protocol = typeof window !== 'undefined'
    && window.location.protocol === 'https:'
    ? 'wss:'
    : 'ws:'
  const host = typeof window !== 'undefined' ? window.location.host : '127.0.0.1:8800'
  return `${protocol}//${host}/ws`
}

function parseAck(raw: Record<string, unknown>): AckMessage {
  return {
    commandId: asString(raw.command_id),
    ok: raw.ok === true,
    status: asString(raw.status),
    payload: asRecord(raw.payload),
    message: asString(asRecord(raw.payload).message),
  }
}

export function createVisualizerClient(
  options: VisualizerClientOptions = {},
): VisualizerClient {
  const url = options.url ?? defaultWebSocketUrl()
  const webSocketFactory =
    options.webSocketFactory ?? ((wsUrl: string) => new WebSocket(wsUrl) as unknown as VisualizerWebSocket)

  let socket: VisualizerWebSocket | null = null
  let connectPromise: Promise<void> | null = null
  let commandSeq = 0
  let disposed = false
  const pendingCommands = new Map<string, PendingCommand>()

  let eventListener: ((event: VisualizerEvent) => void) | null = null
  let connectionListener: ((state: ConnectionState) => void) | null = null
  let errorListener: ((message: string) => void) | null = null

  const setConnection = (state: ConnectionState) => {
    connectionListener?.(state)
  }

  const rejectPendingCommands = (error: Error) => {
    pendingCommands.forEach((pending) => pending.reject(error))
    pendingCommands.clear()
  }

  const handleServerMessage = (rawData: unknown) => {
    const rawText = typeof rawData === 'string' ? rawData : String(rawData)
    let message: Record<string, unknown>
    try {
      message = JSON.parse(rawText)
    } catch {
      errorListener?.(`无法解析服务器消息: ${rawText.slice(0, 120)}`)
      return
    }
    const kind = asString(message.kind)

    if (kind === 'hello') {
      return
    }

    if (kind === 'event') {
      const envelope = asRecord(message.event) as unknown as EventEnvelope
      if (typeof envelope.seq === 'number' && typeof envelope.kind === 'string') {
        eventListener?.(normalizeEvent(envelope))
      }
      return
    }

    if (kind === 'ack') {
      const ack = parseAck(message)
      const pending = ack.commandId ? pendingCommands.get(ack.commandId) : undefined
      if (!pending || !ack.commandId) {
        return
      }
      pendingCommands.delete(ack.commandId)
      if (ack.ok) {
        pending.resolve(ack)
      } else {
        pending.reject(
          new Error(ack.message || `命令被拒绝（${ack.status}）`),
        )
      }
      return
    }

    if (kind === 'error') {
      errorListener?.(asString(message.message, '服务器错误'))
    }
  }

  const ensureSocket = (): Promise<VisualizerWebSocket> => {
    if (socket?.readyState === SOCKET_OPEN) {
      return Promise.resolve(socket)
    }
    if (socket?.readyState === SOCKET_CONNECTING && connectPromise) {
      return connectPromise.then(() => {
        if (!socket || socket.readyState !== SOCKET_OPEN) {
          throw new Error('可视化服务器连接失败')
        }
        return socket
      })
    }
    if (disposed) {
      return Promise.reject(new Error('客户端已销毁'))
    }

    setConnection('connecting')
    const nextSocket = webSocketFactory(url)
    socket = nextSocket
    connectPromise = new Promise<void>((resolve, reject) => {
      nextSocket.onopen = () => {
        connectPromise = null
        setConnection('open')
        resolve()
      }
      nextSocket.onmessage = (event) => {
        try {
          handleServerMessage(event.data)
        } catch (error: unknown) {
          errorListener?.(errorMessage(error))
        }
      }
      nextSocket.onerror = () => {
        if (nextSocket.readyState !== SOCKET_OPEN) {
          connectPromise = null
          setConnection('closed')
          reject(new Error('可视化服务器连接失败'))
        }
      }
      nextSocket.onclose = () => {
        if (socket === nextSocket) {
          socket = null
        }
        connectPromise = null
        setConnection('closed')
        rejectPendingCommands(new Error('可视化服务器连接已断开'))
      }
    })
    return connectPromise.then(() => nextSocket)
  }

  const sendCommand = async (
    command: string,
    payload: Record<string, unknown>,
  ): Promise<AckMessage> => {
    const commandId = `cmd-${++commandSeq}`
    const envelope = {
      kind: 'command',
      command_id: commandId,
      command,
      payload,
    }
    const ackPromise = new Promise<AckMessage>((resolve, reject) => {
      pendingCommands.set(commandId, { resolve, reject })
    })
    try {
      const liveSocket = await ensureSocket()
      if (liveSocket.readyState !== SOCKET_OPEN) {
        throw new Error('可视化服务器连接未就绪')
      }
      liveSocket.send(JSON.stringify(envelope))
    } catch (error: unknown) {
      pendingCommands.delete(commandId)
      throw error
    }
    return ackPromise
  }

  return {
    async connect() {
      await ensureSocket()
    },

    async listCases() {
      const ack = await sendCommand('list_cases', {})
      const cases = Array.isArray(ack.payload.cases) ? ack.payload.cases : []
      return cases
        .map((item): CaseSummary => {
          const record = asRecord(item)
          return {
            id: asString(record.id),
            caseName: asString(record.case_name),
            caseDescription: asString(record.case_description),
          }
        })
        .filter((item) => item.id !== '')
    },

    async runCase(options) {
      await sendCommand('run_case', {
        case_id: options.caseId,
        assistant_kind: options.assistantKind ?? 'mock',
        chunk_delay: options.chunkDelay ?? 0.05,
        fast_mode: options.fastMode ?? false,
        use_streaming: options.useStreaming ?? true,
      })
      return { caseId: options.caseId }
    },

    async stopCase() {
      const ack = await sendCommand('stop_case', {})
      return { wasRunning: ack.payload.was_running === true }
    },

    async judgeCase() {
      // ack 只表示评判任务已受理；verdict 经 judge_verdict 事件异步返回
      await sendCommand('judge_case', {})
    },

    onEvent(listener) {
      eventListener = listener
    },

    onConnectionChange(listener) {
      connectionListener = listener
    },

    onError(listener) {
      errorListener = listener
    },

    dispose() {
      disposed = true
      rejectPendingCommands(new Error('客户端已销毁'))
      if (socket && socket.readyState !== 3) {
        socket.close()
      }
      socket = null
      connectPromise = null
    },
  }
}
