/**
 * 控制台核心 reducer：事件即 action（对齐 v2_frontend 模式）。
 *
 * 单一 reducer 扇出多投影：
 * - utterances / live 缓冲 → 对话流（ChatStream）
 * - events → 虚拟时间线（TimelineLanes）+ 车态时间机（CarStatePanel）
 * - playback → 回放模式状态机（拖拽定位 / 倍速回放）
 * - run → 运行控制状态（RunConsole）
 */
import type { CaseSummary, ConnectionState } from '../adapters/visualizerClient'
import type {
  CaseFinishedEvent,
  JudgeVerdictData,
  ScriptPlanItem,
  VisualizerEvent,
} from '../domain/events'

export interface Toast {
  id: string
  message: string
  level: 'info' | 'error'
}

export type RunStatus =
  | 'idle'
  | 'running'
  | 'finished'
  | 'cancelled'
  | 'error'

export interface RunState {
  status: RunStatus
  caseId: string
  caseName: string
  startedAt: string | null
  /** case_finished 的完整摘要（finished 时非空）。 */
  summary: CaseFinishedEvent | null
  errorMessage: string
}

export type JudgeStatus = 'idle' | 'pending' | 'done' | 'error'

/** 终局评判状态（judge_case 命令 → judge_verdict 事件）。 */
export interface JudgeState {
  status: JudgeStatus
  verdict: JudgeVerdictData | null
  errorMessage: string
}

/**
 * 回放模式状态机（case 完成后激活，像视频播放器）：
 * - idle：未运行 / 运行中（游标无意义，实时投影走"最新"语义）
 * - paused：可拖拽定位游标，观察任意虚拟时刻的车态/对话流
 * - playing：rAF 引擎按倍速推进 cursorMs，对话流/车态窗跟随回放
 */
export interface PlaybackState {
  mode: 'idle' | 'paused' | 'playing'
  /** 回放游标（相对 T0 的毫秒）。 */
  cursorMs: number
  /** 回放倍速（1 = 常速；引擎按 cursor += 真实dt × speed 推进）。 */
  speed: number
}

/** 快进段（相对 T0 毫秒）——回放播放时瞬间穿过，不按真实时间爬过数天。 */
export interface AccelSpan {
  fromMs: number
  toMs: number
}

export interface ConsoleState {
  connection: ConnectionState
  cases: CaseSummary[]
  selectedCaseId: string
  run: RunState
  /** 虚拟时间锚点 T0（case_started.t0）。 */
  t0: string | null
  /** 剧本时间表（锚点驱动预设事件）：时间线"未来区"竖线的来源。 */
  scriptPlan: ScriptPlanItem[]
  /** 层1：落盘话语（对话流权威记录）。 */
  utterances: Extract<VisualizerEvent, { type: 'utterance' }>[]
  /** 层2：假人打字机缓冲（当前正在说的一句话；startedAt = 开口时刻的虚拟时间）。 */
  liveFakePerson: { target: string; text: string; startedAt: string | null } | null
  /** 层2：助手打字机缓冲（多流并发时为混合实时流，落盘 utterance 为权威记录）。 */
  liveAssistant: { text: string; startedAt: string | null }
  /** 全部归一化事件（时间线投影 + 车态时间机 + 原始事件流的来源）。 */
  events: VisualizerEvent[]
  /** 回放模式（拖拽定位 / 倍速回放）。 */
  playback: PlaybackState
  /** 快进段（相对 T0 毫秒）：回放播放时瞬间穿过。 */
  accels: AccelSpan[]
  /** 终局评判（Judge LLM）状态。 */
  judge: JudgeState
  toasts: Toast[]
}

export type ConsoleAction =
  | { type: 'connection'; state: ConnectionState }
  | { type: 'casesLoaded'; cases: CaseSummary[] }
  | { type: 'selectCase'; caseId: string }
  | { type: 'event'; event: VisualizerEvent }
  | { type: 'judgeRequested' }
  | { type: 'localError'; message: string }
  | { type: 'dismissToast'; toastId: string }
  | { type: 'resetRun' }
  | { type: 'playbackScrub'; cursorMs: number }
  | { type: 'playbackPlay'; rewind?: boolean }
  | { type: 'playbackPause' }
  | { type: 'playbackSpeed'; speed: number }
  | { type: 'playbackTick'; deltaMs: number; maxMs: number }

/** 原始事件流水保留上限（防止长 case 内存膨胀）。 */
const MAX_EVENTS = 5000

/** 回放可用的运行态（事件流已完整，游标可自由定位）。 */
function playbackAvailable(status: RunStatus): boolean {
  return status === 'finished' || status === 'cancelled' || status === 'error'
}

export function initialConsoleState(): ConsoleState {
  return {
    connection: 'connecting',
    cases: [],
    selectedCaseId: '',
    run: {
      status: 'idle',
      caseId: '',
      caseName: '',
      startedAt: null,
      summary: null,
      errorMessage: '',
    },
    t0: null,
    scriptPlan: [],
    utterances: [],
    liveFakePerson: null,
    liveAssistant: { text: '', startedAt: null },
    events: [],
    playback: { mode: 'idle', cursorMs: 0, speed: 1 },
    accels: [],
    judge: { status: 'idle', verdict: null, errorMessage: '' },
    toasts: [],
  }
}

function applyEvent(
  state: ConsoleState,
  event: VisualizerEvent,
): ConsoleState {
  // 所有事件（含 unknown_event）都进入事件流（中立保留）
  const events =
    state.events.length >= MAX_EVENTS
      ? state.events
      : [...state.events, event]

  switch (event.type) {
    case 'case_started':
      return {
        ...state,
        events,
        run: {
          status: 'running',
          caseId: event.caseId,
          caseName: event.caseName,
          startedAt: event.wallTime,
          summary: null,
          errorMessage: '',
        },
        t0: event.t0,
        scriptPlan: event.scriptPlan,
        utterances: [],
        liveFakePerson: null,
        liveAssistant: { text: '', startedAt: null },
        playback: { mode: 'idle', cursorMs: 0, speed: state.playback.speed },
        accels: [],
        judge: { status: 'idle', verdict: null, errorMessage: '' },
      }

    case 'case_finished':
      return {
        ...state,
        events,
        run: {
          ...state.run,
          status: 'finished',
          summary: event,
          errorMessage: event.error ?? '',
        },
        liveFakePerson: null,
        liveAssistant: { text: '', startedAt: null },
        playback: { ...state.playback, mode: 'paused' },
        // 服务器在 case 自然完成后自动发起终局评判——先置 pending，
        // judge_verdict 事件到达时覆盖为 done / error
        judge: { status: 'pending', verdict: null, errorMessage: '' },
      }

    case 'case_cancelled':
      return {
        ...state,
        events,
        run: { ...state.run, status: 'cancelled' },
        liveFakePerson: null,
        liveAssistant: { text: '', startedAt: null },
        playback: { ...state.playback, mode: 'paused' },
      }

    case 'run_error':
      return {
        ...state,
        events,
        run: {
          ...state.run,
          status: 'error',
          errorMessage: event.message,
        },
        playback: { ...state.playback, mode: 'paused' },
      }

    case 'fake_person_delta': {
      const current = state.liveFakePerson
      // target 变化 = 新一句话开始（旧缓冲丢弃，正常不会发生——speak_done 即落盘）
      // 首个 delta 的 mockTime = 开口时刻（时间线 live 增长条的起点）
      const sameTarget = current !== null && current.target === event.target
      const text = sameTarget ? current.text + event.delta : event.delta
      const startedAt = sameTarget ? current.startedAt : event.mockTime
      return {
        ...state,
        events,
        liveFakePerson: { target: event.target, text, startedAt },
      }
    }

    case 'assistant_delta': {
      const current = state.liveAssistant
      const startedAt = current.text === '' ? event.mockTime : current.startedAt
      return {
        ...state,
        events,
        liveAssistant: { text: current.text + event.delta, startedAt },
      }
    }

    case 'utterance': {
      // 话语落盘 = 权威记录；清空对应通道的打字机缓冲
      const isFake = event.role.startsWith('fake_person')
      return {
        ...state,
        events,
        utterances: [...state.utterances, event],
        liveFakePerson: isFake ? null : state.liveFakePerson,
        liveAssistant: isFake ? state.liveAssistant : { text: '', startedAt: null },
      }
    }

    case 'judge_verdict':
      return {
        ...state,
        events,
        judge: event.verdict
          ? { status: 'done', verdict: event.verdict, errorMessage: '' }
          : {
              status: 'error',
              verdict: null,
              errorMessage: event.error ?? '评判失败（未知错误）',
            },
      }

    case 'acceleration': {
      // 快进段入 accels（相对 T0 毫秒）——回放播放时瞬间穿过不爬行数天
      const t0Ms = state.t0 ? Date.parse(state.t0) : NaN
      if (!Number.isNaN(t0Ms)) {
        const fromMs = Date.parse(event.from) - t0Ms
        const toMs = Date.parse(event.to) - t0Ms
        if (!Number.isNaN(fromMs) && !Number.isNaN(toMs) && toMs > fromMs) {
          return { ...state, events, accels: [...state.accels, { fromMs, toMs }] }
        }
      }
      return { ...state, events }
    }

    default:
      // state_check / system / tool_call / tool_result /
      // car_set_state / long_pause / unknown_event：仅进入事件流
      // （车态由投影按游标从事件流重建，不在 reducer 累积——单一真相源）
      return { ...state, events }
  }
}

export function consoleReducer(
  state: ConsoleState,
  action: ConsoleAction,
): ConsoleState {
  switch (action.type) {
    case 'connection':
      return { ...state, connection: action.state }

    case 'casesLoaded': {
      const stillExists = action.cases.some(
        (c) => c.id === state.selectedCaseId,
      )
      return {
        ...state,
        cases: action.cases,
        selectedCaseId: stillExists
          ? state.selectedCaseId
          : (action.cases[0]?.id ?? ''),
      }
    }

    case 'selectCase':
      return { ...state, selectedCaseId: action.caseId }

    case 'event':
      return applyEvent(state, action.event)

    case 'judgeRequested':
      // 发出 judge_case 命令（命令被拒时由 localError 提示）
      return {
        ...state,
        judge: { status: 'pending', verdict: null, errorMessage: '' },
      }

    case 'localError':
      return {
        ...state,
        toasts: [
          ...state.toasts,
          {
            id: `toast-${Date.now()}-${Math.random().toString(16).slice(2)}`,
            message: action.message,
            level: 'error',
          },
        ],
      }

    case 'dismissToast':
      return {
        ...state,
        toasts: state.toasts.filter((t) => t.id !== action.toastId),
      }

    case 'resetRun':
      return {
        ...state,
        run: initialConsoleState().run,
        t0: null,
        scriptPlan: [],
        utterances: [],
        liveFakePerson: null,
        liveAssistant: { text: '', startedAt: null },
        events: [],
        playback: { mode: 'idle', cursorMs: 0, speed: state.playback.speed },
        accels: [],
        judge: { status: 'idle', verdict: null, errorMessage: '' },
      }

    case 'playbackScrub':
      // 拖拽/点击时间线定位（播放状态保持——视频习惯：拖完接着播）
      if (!playbackAvailable(state.run.status)) return state
      return {
        ...state,
        playback: {
          ...state.playback,
          cursorMs: Math.max(0, action.cursorMs),
        },
      }

    case 'playbackPlay': {
      if (!playbackAvailable(state.run.status)) return state
      // 游标已到终点 → 从头播放
      const cursorMs =
        action.rewind
          ? 0
          : state.playback.cursorMs
      return {
        ...state,
        playback: { ...state.playback, mode: 'playing', cursorMs },
      }
    }

    case 'playbackPause':
      return {
        ...state,
        playback: { ...state.playback, mode: 'paused' },
      }

    case 'playbackSpeed':
      return {
        ...state,
        playback: { ...state.playback, speed: action.speed },
      }

    case 'playbackTick': {
      // rAF 引擎推进（deltaMs 已含倍速）；到终点自动暂停
      const pb = state.playback
      if (pb.mode !== 'playing') return state
      let next = pb.cursorMs + Math.max(0, action.deltaMs)
      // 快进段瞬间穿过：真实测试里快进是瞬时的（不从 T+3s 爬满 5 天）。
      // 游标一旦落入快进段 [from, to) 立即跳到 to；多段时循环直到稳定。
      let jumped = true
      while (jumped) {
        jumped = false
        for (const accel of state.accels) {
          if (next >= accel.fromMs && next < accel.toMs) {
            next = accel.toMs
            jumped = true
          }
        }
      }
      if (next >= action.maxMs) {
        return {
          ...state,
          playback: { ...pb, cursorMs: action.maxMs, mode: 'paused' },
        }
      }
      return { ...state, playback: { ...pb, cursorMs: next } }
    }

    default:
      return state
  }
}
