import { describe, expect, it } from 'vitest'
import {
  consoleReducer,
  initialConsoleState,
  type ConsoleState,
} from './consoleReducer'
import type { EventMeta, VisualizerEvent } from '../domain/events'

const meta = (seq: number): EventMeta => ({
  seq,
  wallTime: `2026-08-26T10:00:${String(seq).padStart(2, '0')}`,
  mockTime: `2026-08-26T10:00:${String(seq).padStart(2, '0')}`,
})

/** 构造 case_started 事件（含初始车态快照）。 */
function caseStarted(
  seq: number,
  caseId = 'c1',
  initialCarInfo: Record<string, unknown> | null = null,
): VisualizerEvent {
  return {
    ...meta(seq),
    type: 'case_started',
    caseId,
    caseName: '',
    caseDescription: '',
    t0: '2026-08-26T10:00:00',
    sessionId: 's',
    initialCarInfo,
    carStateGroups: null,
    scriptPlan: [],
  }
}

function apply(
  state: ConsoleState,
  events: VisualizerEvent[],
): ConsoleState {
  return events.reduce(
    (acc, event) => consoleReducer(acc, { type: 'event', event }),
    state,
  )
}

describe('consoleReducer', () => {
  it('case_started 重置运行态并记录 t0', () => {
    const state = consoleReducer(initialConsoleState(), {
      type: 'event',
      event: caseStarted(1, 'builtin-interrupt', { 车内温度: '26摄氏度' }),
    })
    expect(state.run.status).toBe('running')
    expect(state.run.caseId).toBe('builtin-interrupt')
    expect(state.t0).toBe('2026-08-26T10:00:00')
    expect(state.utterances).toEqual([])
  })

  it('delta 累积打字机缓冲，utterance 落盘后清空对应缓冲', () => {
    let state = initialConsoleState()
    state = apply(state, [
      caseStarted(1),
      { ...meta(2), type: 'fake_person_delta', target: 'driver', delta: '你好' },
      { ...meta(3), type: 'fake_person_delta', target: 'driver', delta: '小涂' },
      { ...meta(4), type: 'assistant_delta', delta: '好' },
      { ...meta(5), type: 'assistant_delta', delta: '的' },
    ])
    // 首个 delta 记录开口时刻（时间线 live 增长条的起点）
    expect(state.liveFakePerson).toEqual({
      target: 'driver',
      text: '你好小涂',
      startedAt: '2026-08-26T10:00:02',
    })
    expect(state.liveAssistant).toEqual({
      text: '好的',
      startedAt: '2026-08-26T10:00:04',
    })

    // 假人话语落盘 → 清空假人缓冲，助手缓冲保留
    state = apply(state, [
      {
        ...meta(6),
        type: 'utterance',
        speakerKind: 'fake_person_speak',
        role: 'fake_person:driver',
        content: '你好小涂',
        startedAt: '2026-08-26T10:00:02',
        endedAt: '2026-08-26T10:00:04',
        isPartial: false,
        interruptedByBargeIn: false,
        speechDuration: 2,
        ttft: undefined,
        isProactive: false,
        segments: [],
      },
    ])
    expect(state.liveFakePerson).toBeNull()
    expect(state.liveAssistant).toEqual({
      text: '好的',
      startedAt: '2026-08-26T10:00:04',
    })
    expect(state.utterances).toHaveLength(1)

    // 助手话语落盘 → 清空助手缓冲
    state = apply(state, [
      {
        ...meta(7),
        type: 'utterance',
        speakerKind: 'assistant_reply',
        role: 'assistant',
        content: '好的',
        startedAt: '2026-08-26T10:00:05',
        endedAt: '2026-08-26T10:00:06',
        isPartial: false,
        interruptedByBargeIn: false,
        speechDuration: 1,
        ttft: 1,
        isProactive: false,
        segments: [],
      },
    ])
    expect(state.liveAssistant).toEqual({ text: '', startedAt: null })
    expect(state.utterances).toHaveLength(2)
  })

  it('case_finished 保存摘要并清空打字机缓冲', () => {
    let state = initialConsoleState()
    state = apply(state, [
      { ...meta(1), type: 'assistant_delta', delta: '半截' },
      {
        ...meta(2),
        type: 'case_finished',
        caseId: 'c1',
        error: null,
        stateCheckPassed: true,
        totalUtterances: 4,
        stateChecksPassed: 1,
        stateChecksFailed: 0,
        durationSeconds: 42.5,
      },
    ])
    expect(state.run.status).toBe('finished')
    expect(state.run.summary?.totalUtterances).toBe(4)
    expect(state.run.summary?.stateCheckPassed).toBe(true)
    expect(state.liveAssistant).toEqual({ text: '', startedAt: null })
  })

  it('run_error 置错误态；car_set_state 仅进事件流（车态由投影重建）', () => {
    let state = initialConsoleState()
    state = apply(state, [
      {
        ...meta(1),
        type: 'car_set_state',
        updatedFields: { 空调开启状态及模式: '制冷中' },
        source: null,
      },
      {
        ...meta(2),
        type: 'run_error',
        caseId: 'c1',
        message: 'boom',
      },
    ])
    expect(state.events).toHaveLength(2)
    expect(state.run.status).toBe('error')
    expect(state.run.errorMessage).toBe('boom')
  })

  it('未知事件进入事件流但不影响运行态（中立保留）', () => {
    const state = apply(initialConsoleState(), [
      {
        ...meta(1),
        type: 'unknown_event',
        kind: 'future_kind',
        payload: { x: 1 },
      },
    ])
    expect(state.events).toHaveLength(1)
    expect(state.run.status).toBe('idle')
  })

  it('judge 流转：judgeRequested→pending，judge_verdict→done，case_started 重置', () => {
    let state = initialConsoleState()
    state = consoleReducer(state, { type: 'judgeRequested' })
    expect(state.judge.status).toBe('pending')
    expect(state.judge.verdict).toBeNull()

    state = apply(state, [
      {
        ...meta(1),
        type: 'judge_verdict',
        verdict: {
          caseId: 'c1',
          overallPassed: true,
          score: 90,
          scoreBreakdown: null,
          assertionResults: [],
          summary: 'ok',
        },
        error: null,
      },
    ])
    expect(state.judge.status).toBe('done')
    expect(state.judge.verdict?.score).toBe(90)

    // 新 case 开始 → 评判状态重置
    state = apply(state, [caseStarted(2, 'c2')])
    expect(state.judge.status).toBe('idle')
    expect(state.judge.verdict).toBeNull()
  })

  it('judge_verdict 失败 → error 态并保存错误信息', () => {
    const state = apply(initialConsoleState(), [
      {
        ...meta(1),
        type: 'judge_verdict',
        verdict: null,
        error: 'LLM down',
      },
    ])
    expect(state.judge.status).toBe('error')
    expect(state.judge.verdict).toBeNull()
    expect(state.judge.errorMessage).toBe('LLM down')
  })

  it('casesLoaded 保留仍存在的选中项，否则选第一个', () => {
    const base = initialConsoleState()
    const state1 = consoleReducer(base, {
      type: 'casesLoaded',
      cases: [
        { id: 'a', caseName: 'A', caseDescription: '' },
        { id: 'b', caseName: 'B', caseDescription: '' },
      ],
    })
    expect(state1.selectedCaseId).toBe('a')

    const state2 = consoleReducer(
      { ...state1, selectedCaseId: 'b' },
      {
        type: 'casesLoaded',
        cases: [
          { id: 'a', caseName: 'A', caseDescription: '' },
          { id: 'b', caseName: 'B', caseDescription: '' },
        ],
      },
    )
    expect(state2.selectedCaseId).toBe('b')

    const state3 = consoleReducer(state2, {
      type: 'casesLoaded',
      cases: [{ id: 'a', caseName: 'A', caseDescription: '' }],
    })
    expect(state3.selectedCaseId).toBe('a')
  })
})

describe('consoleReducer · playback 回放状态机', () => {
  const finishedCase = (): ConsoleState => {
    // 跑完一个 case：case_started → case_finished（回放激活）
    let state = apply(initialConsoleState(), [
      caseStarted(1, 'c1', { 车内温度: '26摄氏度' }),
      {
        ...meta(2),
        type: 'case_finished',
        caseId: 'c1',
        error: null,
        stateCheckPassed: true,
        totalUtterances: 1,
        stateChecksPassed: 1,
        stateChecksFailed: 0,
        durationSeconds: 10,
      },
    ])
    return state
  }

  it('case_finished 激活回放（mode → paused），case_started 重置回 idle 但保留倍速', () => {
    let state = finishedCase()
    expect(state.playback.mode).toBe('paused')

    state = consoleReducer(state, { type: 'playbackSpeed', speed: 3 })
    state = apply(state, [caseStarted(3, 'c2')])
    expect(state.playback.mode).toBe('idle')
    expect(state.playback.cursorMs).toBe(0)
    expect(state.playback.speed).toBe(3)
  })

  it('运行中 playbackScrub 被忽略；结束后可定位游标', () => {
    const running = apply(initialConsoleState(), [caseStarted(1)])
    const scrubbed = consoleReducer(running, {
      type: 'playbackScrub',
      cursorMs: 5000,
    })
    expect(scrubbed.playback.cursorMs).toBe(0)

    const finished = finishedCase()
    const scrubbed2 = consoleReducer(finished, {
      type: 'playbackScrub',
      cursorMs: 5000,
    })
    expect(scrubbed2.playback.cursorMs).toBe(5000)
    expect(scrubbed2.playback.mode).toBe('paused')
  })

  it('playbackPlay 播放（可选从头），playbackPause 暂停，playbackSpeed 换倍速', () => {
    let state = finishedCase()
    state = consoleReducer(state, { type: 'playbackSpeed', speed: 2 })
    state = consoleReducer(state, { type: 'playbackPlay' })
    expect(state.playback.mode).toBe('playing')

    state = consoleReducer(state, { type: 'playbackPause' })
    expect(state.playback.mode).toBe('paused')

    // rewind=true → 从头播放
    state = consoleReducer(state, {
      type: 'playbackScrub',
      cursorMs: 9000,
    })
    state = consoleReducer(state, { type: 'playbackPlay', rewind: true })
    expect(state.playback.mode).toBe('playing')
    expect(state.playback.cursorMs).toBe(0)
    expect(state.playback.speed).toBe(2)
  })

  it('playbackTick 按增量推进游标，到终点钳制并自动暂停', () => {
    let state = finishedCase()
    state = consoleReducer(state, { type: 'playbackPlay' })

    state = consoleReducer(state, {
      type: 'playbackTick',
      deltaMs: 1200,
      maxMs: 10000,
    })
    expect(state.playback.cursorMs).toBe(1200)

    state = consoleReducer(state, {
      type: 'playbackTick',
      deltaMs: 99999,
      maxMs: 10000,
    })
    expect(state.playback.cursorMs).toBe(10000)
    expect(state.playback.mode).toBe('paused')

    // 暂停后 tick 不再推进
    const frozen = consoleReducer(state, {
      type: 'playbackTick',
      deltaMs: 500,
      maxMs: 10000,
    })
    expect(frozen.playback.cursorMs).toBe(10000)
  })

  it('playbackTick 快进段瞬间穿过（不按真实时间爬过数天）', () => {
    const fiveDays = 5 * 24 * 3600 * 1000
    const t0Ms = Date.parse('2026-08-26T10:00:00')
    // case：先说话，然后快进 5 天
    let state = apply(initialConsoleState(), [
      caseStarted(1, 'c1', null),
      {
        ...meta(2),
        type: 'acceleration',
        from: '2026-08-26T10:00:10',
        to: new Date(t0Ms + 10_000 + fiveDays).toISOString(),
      },
      {
        ...meta(3),
        type: 'case_finished',
        caseId: 'c1',
        error: null,
        stateCheckPassed: true,
        totalUtterances: 1,
        stateChecksPassed: 0,
        stateChecksFailed: 0,
        durationSeconds: 1,
      },
    ])
    // 快进段被记录为 [10s, 5天+10s]
    expect(state.accels).toEqual([{ fromMs: 10_000, toMs: fiveDays + 10_000 }])

    state = consoleReducer(state, { type: 'playbackPlay' })
    // 正常推进到快进段之前（9000ms < 10000ms）
    state = consoleReducer(state, {
      type: 'playbackTick',
      deltaMs: 9_000,
      maxMs: fiveDays + 20_000,
    })
    expect(state.playback.cursorMs).toBe(9_000)

    // 下一步落入快进段 [10s, 5天+10s) → 瞬间跳到快进终点，而不是爬过 5 天
    state = consoleReducer(state, {
      type: 'playbackTick',
      deltaMs: 2_000,
      maxMs: fiveDays + 20_000,
    })
    expect(state.playback.cursorMs).toBe(fiveDays + 10_000)
    expect(state.playback.mode).toBe('playing')
  })
})
