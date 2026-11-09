/**
 * usePlaybackEngine：rAF 回放引擎——按倍速推进回放游标（视频播放器内核）。
 *
 * - playing 时每帧 dispatch playbackTick（deltaMs = 真实dt × speed）
 * - 到达 maxMs 由 reducer 钳制并自动暂停（mode → paused → effect 卸载）
 * - 单帧真实 dt 钳制上限：tab 切后台 rAF 停摆，恢复时 dt 巨大——
 *   钳到 250ms 避免回放瞬间跳到结尾（用户体验：切回来顶多快进一小段）
 */
import { useEffect, useRef } from 'react'
import type { ConsoleAction, PlaybackState } from './consoleReducer'

/** 单帧真实时间增量上限（毫秒）。 */
const MAX_REAL_FRAME_MS = 250

export function usePlaybackEngine(
  playback: Pick<PlaybackState, 'mode' | 'speed'>,
  maxMs: number,
  dispatch: (action: ConsoleAction) => void,
): void {
  const dispatchRef = useRef(dispatch)
  dispatchRef.current = dispatch

  useEffect(() => {
    if (playback.mode !== 'playing') return
    const speed = playback.speed
    let raf = 0
    let last: number | null = null

    const step = (now: number) => {
      if (last !== null) {
        const realDt = Math.min(now - last, MAX_REAL_FRAME_MS)
        dispatchRef.current({
          type: 'playbackTick',
          deltaMs: realDt * speed,
          maxMs,
        })
      }
      last = now
      raf = requestAnimationFrame(step)
    }

    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [playback.mode, playback.speed, maxMs])
}
