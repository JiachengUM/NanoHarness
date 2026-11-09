/**
 * 实时虚拟时钟：运行中的"当前虚拟时刻"平滑推进。
 *
 * 信封双时间戳是外推的锚点：最近一个携带虚拟时间的事件给出
 * (wall_time, mock_time)，虚拟时间与真实时间 1:1 自然流逝，
 * 故 now = mock + (Date.now() - wall)。事件每次到达自动重锚（消除漂移），
 * 快进由 acceleration 事件把锚点跳到未来，外推随即从新时刻继续。
 *
 * 返回值约定：相对 T0 的毫秒（与 buildTimeScale / projectLiveSpans /
 * projectToolSpans 的事件时间戳同坐标系）。内部把绝对 wall/mock 外推结果
 * 减 t0 转换——若把绝对 epoch 毫秒直接传给时间线刻度（axisMs 相对 T0），
 * 事件块的 x 会算成巨大负数导致窗口错乱。t0 缺失或无法解析时返回 null。
 *
 * 用途：实时游标 + live 增长条（话语/执行中工具）随时间不断变长的坐标系。
 */
import { useEffect, useMemo, useState } from 'react'
import type { ConsoleState } from './consoleReducer'

const TICK_MS = 100

export function useNowTicker(
  running: boolean,
  events: ConsoleState['events'],
  t0: string | null,
): number | null {
  // 锚点：最近一个可解析虚拟时间的事件
  const anchor = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i -= 1) {
      const event = events[i]
      const mockIso =
        event.type === 'utterance'
          ? event.endedAt
          : event.type === 'acceleration'
            ? event.to
            : event.mockTime
      if (!mockIso || !event.wallTime) continue
      const mockMs = Date.parse(mockIso)
      const wallMs = Date.parse(event.wallTime)
      if (Number.isNaN(mockMs) || Number.isNaN(wallMs)) continue
      return { mockMs, wallMs }
    }
    return null
  }, [events])

  const t0Ms = t0 ? Date.parse(t0) : NaN

  const [nowMs, setNowMs] = useState<number | null>(null)

  useEffect(() => {
    if (!running || anchor === null || Number.isNaN(t0Ms)) {
      setNowMs(null)
      return
    }
    // 绝对虚拟时刻外推 → 减 t0 转相对（与事件时间戳同一坐标系）
    const extrapolate = () =>
      anchor.mockMs - t0Ms + (Date.now() - anchor.wallMs)
    setNowMs(extrapolate()) // 事件到达即重锚，消除外推漂移
    const timer = setInterval(() => setNowMs(extrapolate()), TICK_MS)
    return () => clearInterval(timer)
  }, [running, anchor, t0Ms])

  return nowMs
}