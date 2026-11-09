/**
 * 事件领域模型：后端 event_bus.py 信封 → 前端强类型事件。
 *
 * 双时间戳是本框架特色：
 * - wallTime：真实墙钟（实时模式坐标系）
 * - mockTime：虚拟时间（回放模式坐标系）——快进后的对话时间跨度可达数天
 *
 * 中立观察者原则：未知 kind 不丢弃，归一化为 unknown_event 保留在事件流里。
 */
import {
  asBoolean,
  asNumber,
  asOptionalNumber,
  asOptionalString,
  asRecord,
  asString,
} from '../utils/unknown'

/** 后端事件信封（event_bus.py emit 的 JSON 形态）。 */
export interface EventEnvelope {
  seq: number
  wall_time: string
  mock_time: string | null
  kind: string
  payload: Record<string, unknown>
}

/** 每个归一化事件都携带的信封元数据。 */
export interface EventMeta {
  seq: number
  wallTime: string
  mockTime: string | null
}

/** 剧本时间表条目（case_started 携带）：锚点驱动的预设事件预览。 */
export interface ScriptPlanItem {
  kind: 'fake_person_speak' | 'car_set_state' | 'state_check' | (string & {})
  /** 锚点时刻（ISO；相对 t0 定位）。 */
  at: string
  /** 事件目标（假人 role_id / 'car'）。 */
  target: string
  /** 展示文字（如台词、改车态 k=v）。 */
  label: string
}

/** 车态变更来源（三色区分：剧本=金 / 助手=红 / 假人=蓝）。 */
export type CarChangeSource = 'script' | 'assistant' | 'fake_person'

/** 层2：case 生命周期。 */
export interface CaseStartedEvent extends EventMeta {
  type: 'case_started'
  caseId: string
  caseName: string
  caseDescription: string
  t0: string
  sessionId: string
  /** 初始车态快照（车态时间机初值；旧事件流可能缺失 → null）。 */
  initialCarInfo: Record<string, unknown> | null
  /** car_info key 展示分组（有序：组名 → key 列表）；虚拟车状态面板分层展示。 */
  carStateGroups: Record<string, string[]> | null
  /** 剧本时间表（锚点驱动预设事件）；时间线"未来区"竖线的来源。 */
  scriptPlan: ScriptPlanItem[]
}

export interface CaseFinishedEvent extends EventMeta {
  type: 'case_finished'
  caseId: string
  error: string | null
  stateCheckPassed: boolean
  totalUtterances: number
  stateChecksPassed: number
  stateChecksFailed: number
  durationSeconds: number
}

export interface CaseCancelledEvent extends EventMeta {
  type: 'case_cancelled'
  caseId: string
  reason: string
}

export interface RunErrorEvent extends EventMeta {
  type: 'run_error'
  caseId: string
  message: string
}

/** 层1：话语落盘（完整一句话，含时间区间与成因标记）。 */
export interface UtteranceEvent extends EventMeta {
  type: 'utterance'
  speakerKind: string
  role: string
  content: string
  startedAt: string
  endedAt: string
  isPartial: boolean
  interruptedByBargeIn: boolean
  speechDuration: number | undefined
  ttft: number | undefined
  isProactive: boolean
  /** [[iso, delta], ...] chunk 级时间戳（流式回复时非空）。 */
  segments: [string, string][]
}

/** 层2：chunk 逐字到达（打字机效果的实时感来源）。 */
export interface FakePersonDeltaEvent extends EventMeta {
  type: 'fake_person_delta'
  target: string
  delta: string
}

export interface AssistantDeltaEvent extends EventMeta {
  type: 'assistant_delta'
  delta: string
}

/** 层1：虚拟车 / 系统 / 工具。 */
export interface StateCheckEvent extends EventMeta {
  type: 'state_check'
  expectedFields: Record<string, unknown>
  actualFields: Record<string, unknown>
  passed: boolean
  mismatches: Record<string, Record<string, unknown>>
}

export interface CarSetStateEvent extends EventMeta {
  type: 'car_set_state'
  updatedFields: Record<string, unknown>
  /** 变更来源：script=剧本（上帝视角）/ assistant=助手车控 / fake_person=假人；null=未知（旧事件流）。 */
  source: CarChangeSource | null
}

export interface AccelerationEvent extends EventMeta {
  type: 'acceleration'
  from: string
  to: string
}

export interface SystemEvent extends EventMeta {
  type: 'system'
  systemKind: string
  description: string
}

export interface ToolCallEvent extends EventMeta {
  type: 'tool_call'
  toolName: string
  toolArgs: Record<string, unknown>
  /** 异步任务 id（精确配对 call/result；旧事件流或同步路径缺失）。 */
  taskId?: string | null
}

export interface ToolResultEvent extends EventMeta {
  type: 'tool_result'
  toolName: string
  result: unknown
  durationMs: number | undefined
  /** 异步任务 id（精确配对 call/result；旧事件流或同步路径缺失）。 */
  taskId?: string | null
}

export interface LongPauseEvent extends EventMeta {
  type: 'long_pause'
  pauseSeconds: number
}

/** 层3：终局评判（judge_case 命令 → Judge LLM → 直接发回发起连接）。 */
export interface AssertionResultView {
  assertion: string
  assertionType: 'must_pass' | 'bonus' | string
  passed: boolean
  reasoning: string
  evidence: string[]
}

export interface ScoreBreakdownView {
  mustPassTotal: number
  mustPassPassed: number
  bonusTotal: number
  bonusPassed: number
  stateCheckTotal: number
  stateCheckPassed: number
  score: number
  passed: boolean
}

export interface JudgeVerdictData {
  caseId: string
  overallPassed: boolean
  score: number
  scoreBreakdown: ScoreBreakdownView | null
  assertionResults: AssertionResultView[]
  summary: string
}

export interface JudgeVerdictEvent extends EventMeta {
  type: 'judge_verdict'
  verdict: JudgeVerdictData | null
  error: string | null
}

/** 未知 kind：中立保留。 */
export interface UnknownEvent extends EventMeta {
  type: 'unknown_event'
  kind: string
  payload: Record<string, unknown>
}

export type VisualizerEvent =
  | CaseStartedEvent
  | CaseFinishedEvent
  | CaseCancelledEvent
  | RunErrorEvent
  | UtteranceEvent
  | FakePersonDeltaEvent
  | AssistantDeltaEvent
  | StateCheckEvent
  | CarSetStateEvent
  | AccelerationEvent
  | SystemEvent
  | ToolCallEvent
  | ToolResultEvent
  | LongPauseEvent
  | JudgeVerdictEvent
  | UnknownEvent

/** 把后端信封归一化为强类型事件（宽松解析：字段缺失给默认值，UI 不炸）。 */
export function normalizeEvent(envelope: EventEnvelope): VisualizerEvent {
  const meta: EventMeta = {
    seq: envelope.seq,
    wallTime: envelope.wall_time,
    mockTime: envelope.mock_time,
  }
  const payload = asRecord(envelope.payload)

  switch (envelope.kind) {
    case 'case_started':
      return {
        ...meta,
        type: 'case_started',
        caseId: asString(payload.case_id),
        caseName: asString(payload.case_name),
        caseDescription: asString(payload.case_description),
        t0: asString(payload.t0),
        sessionId: asString(payload.session_id),
        initialCarInfo:
          payload.initial_car_info !== undefined &&
          payload.initial_car_info !== null &&
          typeof payload.initial_car_info === 'object'
            ? (payload.initial_car_info as Record<string, unknown>)
            : null,
        carStateGroups: normalizeCarStateGroups(payload.car_state_groups),
        scriptPlan: normalizeScriptPlan(payload.script_plan),
      }
    case 'case_finished':
      return {
        ...meta,
        type: 'case_finished',
        caseId: asString(payload.case_id),
        error: asOptionalString(payload.error) ?? null,
        stateCheckPassed: asBoolean(payload.state_check_passed),
        totalUtterances: asNumber(payload.total_utterances) ?? 0,
        stateChecksPassed: asNumber(payload.state_checks_passed) ?? 0,
        stateChecksFailed: asNumber(payload.state_checks_failed) ?? 0,
        durationSeconds: asNumber(payload.duration_seconds) ?? 0,
      }
    case 'case_cancelled':
      return {
        ...meta,
        type: 'case_cancelled',
        caseId: asString(payload.case_id),
        reason: asString(payload.reason),
      }
    case 'run_error':
      return {
        ...meta,
        type: 'run_error',
        caseId: asString(payload.case_id),
        message: asString(payload.message),
      }
    case 'utterance':
      return {
        ...meta,
        type: 'utterance',
        speakerKind: asString(payload.speaker_kind),
        role: asString(payload.role),
        content: asString(payload.content),
        startedAt: asString(payload.started_at),
        endedAt: asString(payload.ended_at),
        isPartial: asBoolean(payload.is_partial),
        interruptedByBargeIn: asBoolean(payload.interrupted_by_barge_in),
        speechDuration: asOptionalNumber(payload.speech_duration),
        ttft: asOptionalNumber(payload.ttft),
        isProactive: asBoolean(payload.is_proactive),
        segments: Array.isArray(payload.segments)
          ? payload.segments.filter(
              (s): s is [string, string] =>
                Array.isArray(s) &&
                typeof s[0] === 'string' &&
                typeof s[1] === 'string',
            )
          : [],
      }
    case 'fake_person_delta':
      return {
        ...meta,
        type: 'fake_person_delta',
        target: asString(payload.target),
        delta: asString(payload.delta),
      }
    case 'assistant_delta':
      return {
        ...meta,
        type: 'assistant_delta',
        delta: asString(payload.delta),
      }
    case 'state_check':
      return {
        ...meta,
        type: 'state_check',
        expectedFields: asRecord(payload.expected_fields),
        actualFields: asRecord(payload.actual_fields),
        passed: asBoolean(payload.passed),
        mismatches: asRecord(payload.mismatches) as Record<
          string,
          Record<string, unknown>
        >,
      }
    case 'car_set_state':
      return {
        ...meta,
        type: 'car_set_state',
        updatedFields: asRecord(payload.updated_fields),
        source: normalizeCarChangeSource(payload.source),
      }
    case 'acceleration':
      return {
        ...meta,
        type: 'acceleration',
        from: asString(payload.from),
        to: asString(payload.to),
      }
    case 'system':
      return {
        ...meta,
        type: 'system',
        systemKind: asString(payload.kind),
        description: asString(payload.description),
      }
    case 'tool_call':
      return {
        ...meta,
        type: 'tool_call',
        toolName: asString(payload.tool_name),
        toolArgs: asRecord(payload.tool_args),
        taskId: asOptionalString(payload.task_id) ?? null,
      }
    case 'tool_result':
      return {
        ...meta,
        type: 'tool_result',
        toolName: asString(payload.tool_name),
        result: payload.result,
        durationMs: asOptionalNumber(payload.duration_ms),
        taskId: asOptionalString(payload.task_id) ?? null,
      }
    case 'long_pause':
      return {
        ...meta,
        type: 'long_pause',
        pauseSeconds: asNumber(payload.pause_seconds) ?? 0,
      }
    case 'judge_verdict': {
      const error = asOptionalString(payload.error)
      // 成功时 payload 即 JudgeVerdict 平铺 JSON（含 case_id）；失败时仅 error
      return {
        ...meta,
        type: 'judge_verdict',
        verdict:
          error === undefined && payload.case_id !== undefined
            ? normalizeVerdict(payload)
            : null,
        error: error ?? null,
      }
    }
    default:
      return {
        ...meta,
        type: 'unknown_event',
        kind: envelope.kind,
        payload,
      }
  }
}

/** role 形如 "fake_person:driver" / "assistant"——判断假人话语。 */
export function isFakePersonRole(role: string): boolean {
  return role.startsWith('fake_person')
}

/** car_state_groups：{组名: [key...]}，组内 key 数组须全为字符串。 */
function normalizeCarStateGroups(
  raw: unknown,
): Record<string, string[]> | null {
  if (raw === null || raw === undefined || typeof raw !== 'object') {
    return null
  }
  const groups: Record<string, string[]> = {}
  for (const [name, keys] of Object.entries(raw as Record<string, unknown>)) {
    if (Array.isArray(keys)) {
      const list = keys.filter((k): k is string => typeof k === 'string')
      if (list.length > 0) groups[name] = list
    }
  }
  return Object.keys(groups).length > 0 ? groups : null
}

/** script_plan：[{kind, at, target, label}]，字段宽松解析（缺 at 的条目丢弃）。 */
function normalizeScriptPlan(raw: unknown): ScriptPlanItem[] {
  if (!Array.isArray(raw)) return []
  const plan: ScriptPlanItem[] = []
  for (const item of raw) {
    if (item === null || typeof item !== 'object') continue
    const record = item as Record<string, unknown>
    const at = asString(record.at)
    if (!at) continue
    plan.push({
      kind: asString(record.kind) || 'unknown',
      at,
      target: asString(record.target),
      label: asString(record.label),
    })
  }
  return plan
}

/** 车态变更来源：仅认 script/assistant/fake_person，其余归为未知（null）。 */
function normalizeCarChangeSource(raw: unknown): CarChangeSource | null {
  return raw === 'script' || raw === 'assistant' || raw === 'fake_person'
    ? raw
    : null
}

/** 从 role 提取说话人显示名（"fake_person:driver" → "假人·driver"）。 */
export function speakerLabel(role: string): string {
  if (isFakePersonRole(role)) {
    const persona = role.split(':')[1] ?? ''
    return persona ? `假人·${persona}` : '假人'
  }
  return '助手'
}

/** JudgeVerdict 平铺 JSON（snake_case）→ JudgeVerdictData（camelCase）。 */
function normalizeVerdict(raw: Record<string, unknown>): JudgeVerdictData {
  const breakdown = asRecord(raw.score_breakdown)
  const assertions = Array.isArray(raw.assertion_results)
    ? raw.assertion_results
    : []
  return {
    caseId: asString(raw.case_id),
    overallPassed: raw.overall_passed === true,
    score: asNumber(raw.score) ?? 0,
    scoreBreakdown:
      breakdown.score !== undefined
        ? {
            mustPassTotal: asNumber(breakdown.must_pass_total) ?? 0,
            mustPassPassed: asNumber(breakdown.must_pass_passed) ?? 0,
            bonusTotal: asNumber(breakdown.bonus_total) ?? 0,
            bonusPassed: asNumber(breakdown.bonus_passed) ?? 0,
            stateCheckTotal: asNumber(breakdown.state_check_total) ?? 0,
            stateCheckPassed: asNumber(breakdown.state_check_passed) ?? 0,
            score: asNumber(breakdown.score) ?? 0,
            passed: breakdown.passed === true,
          }
        : null,
    assertionResults: assertions.map((item): AssertionResultView => {
      const record = asRecord(item)
      return {
        assertion: asString(record.assertion),
        assertionType: asString(record.assertion_type),
        passed: record.passed === true,
        reasoning: asString(record.reasoning),
        evidence: Array.isArray(record.evidence)
          ? record.evidence.map((e) => String(e))
          : [],
      }
    }),
    summary: asString(raw.summary),
  }
}
