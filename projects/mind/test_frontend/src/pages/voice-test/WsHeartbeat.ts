/**
 * WebSocket 应用层心跳（ping/pong）独立模块。
 *
 * 背景：浏览器 JS 不暴露原生 WebSocket ping/pong control frame，
 * 半开连接（拔网线/WiFi 切换）时 onclose/onerror 均不触发，
 * 需应用层 ping/pong + 超时判定来兜底 UI 状态。
 *
 * 设计要点：
 * - 前端主动发 ping，后端主循环空闲秒回 pong（与业务完全解耦，不误判 case 转换）
 * - 任意 WS 消息（含业务消息）都视为连接活跃，触发 reset，减少不必要的 ping
 * - 超时判定基于"连续 N 次 pong 未收到"，避免单次网络抖动误杀
 * - 与业务代码解耦：只暴露 start/stop/onMessage，不依赖任何业务状态
 */

export type HeartbeatOptions = {
  /** ping 发送间隔（ms），默认 10s */
  intervalMs: number
  /** 单次 pong 等待超时（ms），默认 5s */
  timeoutMs: number
  /** 连续未响应次数上限，达到即判定断开，默认 2 */
  maxMissed: number
  /** 判定断开回调（由调用方处理 UI 清理） */
  onTimeout: () => void
}

const DEFAULT_OPTIONS: Omit<HeartbeatOptions, 'onTimeout'> = {
  intervalMs: 10_000,
  timeoutMs: 5_000,
  maxMissed: 2,
}

export class WsHeartbeat {
  private ws: WebSocket
  private opts: HeartbeatOptions
  private pingTimer: number | null = null
  private pongTimer: number | null = null
  private missed = 0
  private alive = false

  constructor(ws: WebSocket, opts: Partial<HeartbeatOptions> & { onTimeout: () => void }) {
    this.ws = ws
    this.opts = { ...DEFAULT_OPTIONS, ...opts }
  }

  /** 启动心跳：开始周期性 ping 调度 */
  start(): void {
    if (this.alive) return
    this.alive = true
    this.missed = 0
    console.info('[VT] heartbeat start: interval=%dms timeout=%dms maxMissed=%d', this.opts.intervalMs, this.opts.timeoutMs, this.opts.maxMissed)
    this.schedulePing()
  }

  /**
   * 收到任何 WS 消息时调用。
   * - pong 消息：明确响应，reset 计数
   * - 业务消息：视为连接活跃，同样 reset（优化：减少不必要的 ping）
   */
  onMessage(data: unknown): void {
    if (!this.alive) return
    if (typeof data === 'string') {
      try {
        const msg = JSON.parse(data) as { type?: string }
        if (msg.type === 'pong') {
          this.reset()
          return
        }
      } catch {
        // 非 JSON：二进制音频帧，视为活跃
      }
    }
    // 业务消息（phase/asr/tts/log 等）也视为连接活跃
    this.reset()
  }

  /** 停止心跳：清空所有计时器，不再触发 onTimeout */
  stop(): void {
    if (!this.alive) return
    console.info('[VT] heartbeat stop')
    this.alive = false
    this.clearTimers()
  }

  // ------------------------------------------------------------------
  // 内部调度
  // ------------------------------------------------------------------

  private schedulePing(): void {
    this.clearPingTimer()
    this.pingTimer = window.setTimeout(() => this.sendPing(), this.opts.intervalMs)
  }

  private sendPing(): void {
    if (!this.alive) return
    // ws 已不处于 OPEN：等业务层 onclose/onerror 兜底，不再发 ping
    if (this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[VT] heartbeat skip: ws not OPEN (state=%d)', this.ws.readyState)
      return
    }
    const ts = Date.now()
    try {
      this.ws.send(JSON.stringify({ type: 'ping', ts }))
      console.debug('[VT] send ping ts=%d', ts)
    } catch {
      // send 抛错通常意味着连接已关闭，等业务层 onclose 兜底
      console.warn('[VT] heartbeat send error, wait onclose')
      return
    }
    // 启动单次 pong 超时等待
    this.pongTimer = window.setTimeout(() => {
      this.missed++
      if (this.missed >= this.opts.maxMissed) {
        // 达到上限：判定断开，通知业务层清理
        console.warn('[VT] heartbeat timeout: missed=%d/%d, triggering onTimeout', this.missed, this.opts.maxMissed)
        this.alive = false
        this.clearTimers()
        this.opts.onTimeout()
        return
      }
      // 未达上限：继续下一轮 ping 调度
      console.warn('[VT] heartbeat pong timeout: missed=%d/%d, will retry', this.missed, this.opts.maxMissed)
      this.schedulePing()
    }, this.opts.timeoutMs)
  }

  /** 收到任何活跃信号后重置：清 pong 计时、重新计时下一轮 ping */
  private reset(): void {
    this.missed = 0
    this.clearPongTimer()
    if (this.alive) {
      this.schedulePing()
    }
  }

  private clearTimers(): void {
    this.clearPingTimer()
    this.clearPongTimer()
  }

  private clearPingTimer(): void {
    if (this.pingTimer !== null) {
      window.clearTimeout(this.pingTimer)
      this.pingTimer = null
    }
  }

  private clearPongTimer(): void {
    if (this.pongTimer !== null) {
      window.clearTimeout(this.pongTimer)
      this.pongTimer = null
    }
  }
}
