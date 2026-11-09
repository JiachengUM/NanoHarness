/**
 * 纯函数投影：ConsoleState → 各面板视图模型。
 *
 * 对话流投影（projectDialogue）与时间线投影（projectTimeline）分离，
 * 保证投影逻辑可独立测试（事件序列 → 视图断言）。
 */
import type { ConsoleState } from './consoleReducer'
import {
  isFakePersonRole,
  speakerLabel,
  type AccelerationEvent,
  type CarChangeSource,
  type ScriptPlanItem,
  type UtteranceEvent,
} from '../domain/events'

// ---------------- 对话流投影 ----------------

export type BubbleStatus =
  | 'speaking'   // 打字机进行中（层2 live 缓冲）
  | 'complete'   // 完整落盘
  | 'interrupted' // 半截话：被用户插话打断（助手自中断旧流）
  | 'truncated'  // 半截话：超时截断（测试基建兜底）

export interface ChatBubble {
  id: string
  kind: 'bubble'
  speaker: 'fakePerson' | 'assistant'
  label: string
  content: string
  startedAt: string | null
  /** 相对 T0 的虚拟时间区间（如 "T+3.2s → T+8.7s"）；t0 缺失或 live 时为 null。 */
  timeRangeText: string | null
  status: BubbleStatus
  isProactive: boolean
  isLive: boolean
}

export interface ToolCard {
  id: string
  kind: 'tool'
  toolName: string
  argsText: string
  resultText: string | null
  durationMs: number | null
  /** 相对 T0 的虚拟时间区间（调用→返回；未配对时仅开始时刻）。 */
  timeRangeText: string | null
}

/** 时间快进标记（对话流内）：快进区间两侧的对话由此分隔，避免看起来像持续对话。 */
export interface AccelerationEntry {
  id: string
  kind: 'acceleration'
  /** 快进时长（ms；from/to 缺失时 null）。 */
  durationMs: number | null
  /** 相对 T0 的虚拟时间区间文本（如 "T+12.0s → T+2h10m"）。 */
  timeRangeText: string | null
  /** 回放游标仍在快进区间内（实时模式恒 false——事件落盘时快进已完成）。 */
  ongoing: boolean
}

/**
 * 剧本事件（对话流内）：车态变更 / 状态检查等脚本侧动作。
 * 与对话气泡、工具卡片混排，但用独立样式区隔——这些不是"说了什么"，
 * 而是剧本在后台对虚拟世界/状态的直接操作，刻意与对话内容块拉开视觉。
 */
export interface ScriptEventEntry {
  id: string
  kind: 'script'
  /** 剧本事件子类：car_set_state=上帝视角改车态 / state_check=状态检查。 */
  scriptKind: 'car_set_state' | 'state_check'
  /** 标题（如"剧本·车态变更" / "状态检查"）。 */
  label: string
  /** 详情（字段 k=v 列表）。 */
  detail: string
  /** 相对 T0 的虚拟时刻文本（点事件，如 "T+5.0s"）。 */
  timeRangeText: string | null
  /** state_check 是否通过；car_set_state 恒 null（无通过/失败语义）。 */
  passed: boolean | null
}

export type DialogueEntry =
  | ChatBubble
  | ToolCard
  | AccelerationEntry
  | ScriptEventEntry

/** 相对 T0 的虚拟时间区间文本："T+3.2s → T+8.7s"。 */
function formatTimeRange(
  t0Ms: number,
  startIso: string | null,
  endIso: string | null,
): string | null {
  const start = timeMs(startIso, t0Ms)
  if (start === null) return null
  const end = endIso ? timeMs(endIso, t0Ms) : null
  const startText = `T+${formatDuration(Math.max(start, 0))}`
  if (end === null || end <= start) return startText
  return `${startText} → T+${formatDuration(end)}`
}

/** 回放中"说到一半"的内容：拼接时刻 ≤ 游标的 chunk（无 segments 降级全文）。 */
function partialContent(
  segments: [string, string][],
  cursorMs: number,
  t0Ms: number,
): string {
  if (segments.length === 0) return ''
  let text = ''
  for (const [iso, delta] of segments) {
    const at = timeMs(iso, t0Ms)
    if (at !== null && at <= cursorMs) {
      text += delta
    }
  }
  return text
}

// ---------------- 车态时间机（回放核心） ----------------

export interface CarStateEntry {
  key: string
  value: unknown
  /** 该字段最近一次变化时刻（相对 T0 毫秒；初始字段为 0）。 */
  changedAtMs: number
  /** 最近一次变更来源（剧本=金/助手=红/假人=蓝；null=初始值或旧事件流未知）。 */
  source: CarChangeSource | null
}

export interface CarStateGroupView {
  name: string
  entries: CarStateEntry[]
  /** 组内含游标处刚变化的字段（组头琥珀点提示）。 */
  hasChange: boolean
}

/** 游标处最近的「设置车态 / 状态检查」统一高亮描述（驱动面板动态渲染）。 */
export interface CarStateHighlight {
  /** 高亮字段集：设置=被改字段 / 检查=被验证字段。 */
  keys: string[]
  /** 高亮来源：设置车态（蓝）或状态检查（绿/红）。 */
  kind: 'set' | 'check'
  /** kind='check' 时：检查是否通过；kind='set' 恒 null。 */
  passed: boolean | null
}

export interface CarStateView {
  entries: CarStateEntry[]
  /** 分层分组视图（组序 = case_started.car_state_groups 序；无元数据时单组兜底）。 */
  groups: CarStateGroupView[]
  /** 游标处最近一次 car_set_state "时刻"的全部字段（向后兼容；同一事件可能一次改多字段）。 */
  changedKeys: string[]
  /** 最近一次 car_set_state 变化时刻（相对 T0 毫秒；无变化时 0）。 */
  changedAtMs: number
  /** 最近一次 car_set_state 变化来源（向后兼容）。 */
  changedSource: CarChangeSource | null
  /** 游标处最近一次「设置车态 / 状态检查」的统一高亮（set=蓝 / check=绿·红）。 */
  highlight: CarStateHighlight | null
}

/**
 * 车态时间机：重建游标时刻的虚拟车全量状态。
 * 初值 = case_started.initial_car_info，增量 = mock_time ≤ cursorMs 的
 * car_set_state 事件按序合并（助手车控与剧本 set_state 统一走这条链路）。
 *
 * 分组视图（虚拟车字段多，分层展示）：
 * - 有 car_state_groups 元数据：按组序收集（组内按元数据 key 序），
 *   未归组字段收进"其他"组（末尾）
 * - 无元数据（旧事件流）：单组"全部状态"按插入序展示
 */
export function projectCarState(
  events: ConsoleState['events'],
  t0: string | null,
  cursorMs: number | null,
): CarStateView {
  // 初值（case_started 携带；旧事件流缺失时空表起步）
  let initial: Record<string, unknown> = {}
  let groupsMeta: Record<string, string[]> | null = null
  const t0Ms = t0 ? Date.parse(t0) : NaN
  const hasT0 = !Number.isNaN(t0Ms)
  for (const event of events) {
    if (event.type === 'case_started') {
      if (event.initialCarInfo) initial = event.initialCarInfo
      if (event.carStateGroups) groupsMeta = event.carStateGroups
      break
    }
  }

  const state = new Map<string, CarStateEntry>()
  const order: string[] = []
  const touch = (
    key: string,
    value: unknown,
    atMs: number,
    source: CarChangeSource | null,
  ) => {
    const existing = state.get(key)
    if (existing) {
      existing.value = value
      existing.changedAtMs = atMs
      existing.source = source
    } else {
      state.set(key, { key, value, changedAtMs: atMs, source })
      order.push(key)
    }
  }
  for (const [key, value] of Object.entries(initial)) {
    touch(key, value, 0, null)
  }

  // 最近一次变化"时刻"的全部字段（同一 car_set_state 可能一次改多字段，
  // 全部都要高亮，而不是只点亮最后遍历到的那个字段）
  let changedKeys: string[] = []
  let changedSource: CarChangeSource | null = null
  let lastChangeMs = -1
  for (const event of events) {
    if (event.type !== 'car_set_state') continue
    const at = hasT0 && event.mockTime ? timeMs(event.mockTime, t0Ms) : null
    if (at === null) continue
    if (cursorMs !== null && at > cursorMs) continue // 游标之后的变化不生效
    const keys = Object.keys(event.updatedFields)
    for (const [key, value] of Object.entries(event.updatedFields)) {
      touch(key, value, at, event.source)
    }
    if (at > lastChangeMs) {
      // 更晚的变化时刻：重置为该时刻的字段集
      lastChangeMs = at
      changedKeys = keys.slice()
      changedSource = event.source
    } else if (at === lastChangeMs) {
      // 同一时刻的多个事件（罕见）：合并字段集
      for (const key of keys) {
        if (!changedKeys.includes(key)) changedKeys.push(key)
      }
      changedSource = event.source
    }
  }

  // 最近一次状态检查（只驱动「高亮」，不改变车态值——检查是读/校验，不改状态）
  let checkHighlight: { keys: string[]; atMs: number; passed: boolean } | null = null
  for (const event of events) {
    if (event.type !== 'state_check') continue
    const at = hasT0 && event.mockTime ? timeMs(event.mockTime, t0Ms) : null
    if (at === null) continue
    if (cursorMs !== null && at > cursorMs) continue // 游标之后的检查不生效
    const keys = Object.keys(event.expectedFields)
    if (checkHighlight === null || at > checkHighlight.atMs) {
      checkHighlight = { keys: keys.slice(), atMs: at, passed: event.passed }
    } else if (at === checkHighlight.atMs) {
      for (const key of keys) {
        if (!checkHighlight.keys.includes(key)) checkHighlight.keys.push(key)
      }
    }
  }

  // 统一高亮：设置车态（蓝）与状态检查（绿/红）取更晚者
  const checkAtMs = checkHighlight?.atMs ?? -1
  let highlight: CarStateHighlight | null = null
  if (checkHighlight !== null && checkAtMs >= lastChangeMs) {
    highlight = {
      keys: checkHighlight.keys,
      kind: 'check',
      passed: checkHighlight.passed,
    }
  } else if (lastChangeMs >= 0) {
    highlight = { keys: changedKeys, kind: 'set', passed: null }
  }

  const entries = order.map((key) => state.get(key)!)
  const highlightKeys = highlight?.keys ?? []
  return {
    entries,
    groups: groupCarStateEntries(entries, groupsMeta, highlightKeys),
    changedKeys,
    changedAtMs: lastChangeMs > 0 ? lastChangeMs : 0,
    changedSource,
    highlight,
  }
}

/** 全量字段 → 分组视图（组序保持元数据顺序；未归组字段进"其他"）。 */
function groupCarStateEntries(
  entries: CarStateEntry[],
  groupsMeta: Record<string, string[]> | null,
  changedKeys: string[],
): CarStateGroupView[] {
  if (!groupsMeta || entries.length === 0) {
    return [
      { name: '全部状态', entries, hasChange: changedKeys.length > 0 },
    ]
  }
  const byKey = new Map(entries.map((e) => [e.key, e]))
  const claimed = new Set<string>()
  const groups: CarStateGroupView[] = []
  for (const [name, keys] of Object.entries(groupsMeta)) {
    const groupEntries: CarStateEntry[] = []
    for (const key of keys) {
      const entry = byKey.get(key)
      if (entry) {
        groupEntries.push(entry)
        claimed.add(key)
      }
    }
    if (groupEntries.length > 0) {
      groups.push({
        name,
        entries: groupEntries,
        hasChange: groupEntries.some((e) => changedKeys.includes(e.key)),
      })
    }
  }
  const rest = entries.filter((e) => !claimed.has(e.key))
  if (rest.length > 0) {
    groups.push({
      name: '其他',
      entries: rest,
      hasChange: rest.some((e) => changedKeys.includes(e.key)),
    })
  }
  return groups
}

/**
 * 对话流条目：落盘话语气泡 + 工具调用卡片（按事件到达序混排）
 * + 末尾的打字机气泡。tool_result 按 toolName FIFO 就近配对到未配对的 tool_call。
 *
 * cursorMs（回放模式）：
 * - null → 实时模式：全量显示 + live 打字机气泡（现状行为）
 * - 数字 → 回放模式：按游标裁剪——说完的完整显示、说到一半的按 segments
 *   部分渲染（status='speaking'）、未开始的不显示；工具卡片 result 未到
 *   显示"执行中"；live 气泡不显示（回放基于落盘权威记录）
 */
export function projectDialogue(
  state: ConsoleState,
  cursorMs: number | null = null,
): DialogueEntry[] {
  // toolName → 待配对卡片（含各自开始时刻的相对毫秒）
  const pendingByTool = new Map<string, { card: ToolCard; startMs: number }[]>()
  // task_id → 待配对卡片（并行同名工具精确配对）；缺失时回退 toolName FIFO
  const pendingByTask = new Map<string, { card: ToolCard; startMs: number }>()
  const t0Ms = state.t0 ? Date.parse(state.t0) : NaN
  const hasT0 = !Number.isNaN(t0Ms)
  const replay = cursorMs !== null

  // 统一「排序时间戳」：按事件结束时间排序（话语按说完、快进按终点、工具按返回）。
  // 先收集再排序——回灌 utterance / 异步工具 result 的落盘 seq 与虚拟时间
  // 可能交叉，按 seq 排列会导致对话流乱序。
  // 按结束时间而非开口时间排序的意义：跨多个工具执行窗口的长助话语（如
  // "正在为你查询…"贯穿 11.5s→34.1s）应排在其期间完成的那些事件之后，而不是
  // 按开口时间插在第一个工具与后续工具之间。
  const items: Array<{ entry: DialogueEntry; sortMs: number }> = []
  const toolCards: Array<{ card: ToolCard }> = []
  // 工具卡片排序用结束时间（返回时刻）；result 未到前退回调用时刻。
  const toolEndMs = new Map<ToolCard, number>()

  for (const event of state.events) {
    if (event.type === 'utterance') {
      const isFake = isFakePersonRole(event.role)
      const startMs = hasT0 ? timeMs(event.startedAt, t0Ms) : null
      const endMs = hasT0 ? timeMs(event.endedAt, t0Ms) : null
      if (replay && startMs !== null && startMs > cursorMs) continue // 未开始
      const speaking =
        replay && endMs !== null && endMs > cursorMs // 说到一半
      const status: BubbleStatus = speaking
        ? 'speaking'
        : !event.isPartial
          ? 'complete'
          : event.interruptedByBargeIn
            ? 'interrupted'
            : 'truncated'
      const content = speaking
        ? partialContent(event.segments, cursorMs, t0Ms)
        : event.content
      items.push({
        entry: {
          id: `utt-${event.seq}`,
          kind: 'bubble',
          speaker: isFake ? 'fakePerson' : 'assistant',
          label: speakerLabel(event.role),
          content,
          startedAt: event.startedAt,
          timeRangeText: hasT0
            ? formatTimeRange(t0Ms, event.startedAt, event.endedAt)
            : null,
          status,
          isProactive: event.isProactive,
          isLive: false,
        },
        sortMs: endMs ?? startMs ?? Number.POSITIVE_INFINITY,
      })
    } else if (event.type === 'acceleration') {
      // 时间快进标记：按事件到达序混排在话语之间——快进两侧的
      // 对话由此视觉分隔（不然像一段持续的对话）
      const fromMs = hasT0 ? timeMs(event.from, t0Ms) : null
      if (replay && fromMs !== null && fromMs > cursorMs) continue // 快进未发生
      const toMs = hasT0 ? timeMs(event.to, t0Ms) : null
      items.push({
        entry: {
          id: `accel-${event.seq}`,
          kind: 'acceleration',
          durationMs:
            fromMs !== null && toMs !== null ? Math.max(0, toMs - fromMs) : null,
          timeRangeText: hasT0
            ? formatTimeRange(t0Ms, event.from, event.to)
            : null,
          ongoing: replay && toMs !== null ? toMs > cursorMs : false,
        },
        sortMs: toMs ?? fromMs ?? Number.POSITIVE_INFINITY,
      })
    } else if (event.type === 'tool_call') {
      const startMs = hasT0 && event.mockTime ? timeMs(event.mockTime, t0Ms) : null
      if (replay && startMs !== null && startMs > cursorMs) continue // 调用未甩出
      const card: ToolCard = {
        id: `tool-${event.seq}`,
        kind: 'tool',
        toolName: event.toolName,
        argsText: formatFields(event.toolArgs),
        resultText: null,
        durationMs: null,
        timeRangeText:
          startMs !== null
            ? `T+${formatDuration(Math.max(startMs, 0))}`
            : null,
      }
      toolCards.push({ card })
      toolEndMs.set(card, startMs ?? Number.POSITIVE_INFINITY)
      const pendingItem = { card, startMs: startMs ?? 0 }
      const taskId = event.taskId ?? null
      if (taskId) {
        pendingByTask.set(taskId, pendingItem)
      } else {
        const queue = pendingByTool.get(event.toolName)
        if (queue) {
          queue.push(pendingItem)
        } else {
          pendingByTool.set(event.toolName, [pendingItem])
        }
      }
    } else if (event.type === 'tool_result') {
      const resultMs =
        hasT0 && event.mockTime ? timeMs(event.mockTime, t0Ms) : null
      if (replay && resultMs !== null && resultMs > cursorMs) {
        continue // 结果未到：卡片保持"执行中"
      }
      const taskId = event.taskId ?? null
      let pendingItem: { card: ToolCard; startMs: number } | undefined
      if (taskId) {
        pendingItem = pendingByTask.get(taskId)
        if (pendingItem) pendingByTask.delete(taskId)
      } else {
        pendingItem = pendingByTool.get(event.toolName)?.shift()
      }
      if (pendingItem) {
        const { card, startMs } = pendingItem
        card.resultText =
          typeof event.result === 'string'
            ? event.result
            : JSON.stringify(event.result)
        card.durationMs = event.durationMs ?? null
        const endMs = resultMs
        if (endMs !== null) toolEndMs.set(card, endMs)
        if (endMs !== null && endMs > startMs) {
          card.timeRangeText = `T+${formatDuration(Math.max(startMs, 0))} → T+${formatDuration(endMs)}`
        }
      }
    } else if (event.type === 'car_set_state') {
      // 上帝视角剧本改车态（source=script）进入对话流；助手车控（source=assistant）
      // 已由工具卡片体现，不再重复渲染（避免同一次车控在对话流出现两次）。
      if (event.source !== 'script') continue
      const atMs = hasT0 && event.mockTime ? timeMs(event.mockTime, t0Ms) : null
      if (replay && atMs !== null && atMs > cursorMs) continue
      items.push({
        entry: {
          id: `script-car-${event.seq}`,
          kind: 'script',
          scriptKind: 'car_set_state',
          label: '剧本·车态变更',
          detail: formatFieldsFull(event.updatedFields),
          timeRangeText: hasT0 ? formatPointTime(atMs) : null,
          passed: null,
        },
        sortMs: atMs ?? Number.POSITIVE_INFINITY,
      })
    } else if (event.type === 'state_check') {
      const atMs = hasT0 && event.mockTime ? timeMs(event.mockTime, t0Ms) : null
      if (replay && atMs !== null && atMs > cursorMs) continue
      items.push({
        entry: {
          id: `script-check-${event.seq}`,
          kind: 'script',
          scriptKind: 'state_check',
          label: '状态检查',
          detail: formatFieldsFull(event.expectedFields),
          timeRangeText: hasT0 ? formatPointTime(atMs) : null,
          passed: event.passed,
        },
        sortMs: atMs ?? Number.POSITIVE_INFINITY,
      })
    }
  }

  // 工具卡片并入并按时间升序排序（稳定排序：同时刻保留先话语后工具的插入序）
  for (const { card } of toolCards) {
    items.push({
      entry: card,
      sortMs: toolEndMs.get(card) ?? Number.POSITIVE_INFINITY,
    })
  }
  items.sort((a, b) => a.sortMs - b.sortMs)
  const entries: DialogueEntry[] = items.map((item) => item.entry)

  // 打字机气泡（层2 缓冲）追加在末尾——落盘后缓冲清空，不会与权威记录重复。
  // 回放模式不显示（回放基于落盘事件，实时缓冲与虚拟时间无关）。
  if (replay) {
    return entries
  }
  if (state.liveFakePerson && state.liveFakePerson.text !== '') {
    entries.push({
      id: 'live-fake-person',
      kind: 'bubble',
      speaker: 'fakePerson',
      label: `假人·${state.liveFakePerson.target || 'driver'}`,
      content: state.liveFakePerson.text,
      startedAt: null,
      timeRangeText: null,
      status: 'speaking',
      isProactive: false,
      isLive: true,
    })
  }
  if (state.liveAssistant.text !== '') {
    entries.push({
      id: 'live-assistant',
      kind: 'bubble',
      speaker: 'assistant',
      label: '助手',
      content: state.liveAssistant.text,
      startedAt: null,
      timeRangeText: null,
      status: 'speaking',
      isProactive: false,
      isLive: true,
    })
  }
  return entries
}

// ---------------- 时间线投影 ----------------

export type LaneId = 'fakePerson' | 'assistant' | 'car' | 'system'

export interface LaneSpan {
  id: string
  lane: LaneId
  kind: string
  label: string
  detail: string
  startMs: number
  endMs: number
  tone:
    | 'ok'
    | 'fail'
    | 'info'
    | 'proactive'
    | 'partial'
    | 'accel'
    | 'tool'
    | 'warn'
    | 'future'
}

export interface TimeSegmentView {
  kind: 'normal' | 'acceleration'
  startMs: number
  endMs: number
  xStart: number
  xEnd: number
}

export type TimelineMode = 'live' | 'replay'

/** live 流动网格线：秒级刻度随虚拟时间从右向左流动（节拍感）。 */
export interface Gridline {
  atMs: number
  label: string
  /** T0 原点线（加粗呈现）。 */
  origin: boolean
}

export interface TimeScale {
  mode: TimelineMode
  /** 空刻度（未运行 case / 回放无事件）：面板显示占位。 */
  empty: boolean
  /** 可视窗口（相对 T0 毫秒）：live = [now-半窗, now+半窗] 滑动窗口；replay = 视窗边界反算回时间。 */
  viewStartMs: number
  viewEndMs: number
  /** 全域终点（相对 T0 毫秒）：回放总时长与游标钳制的上界。 */
  endMs: number
  /** 轴线时刻：live = 当前虚拟时刻（恒映射 x=0.5）；replay = 回放游标。 */
  axisMs: number
  /** 快进段列表（背景带渲染，窗口裁剪走 clipSpanToView）。 */
  accels: { fromMs: number; toMs: number }[]
  /** 分段视图（回放刻度行；坐标已含 zoom/pan 视窗映射；live 恒 []）。 */
  segments: TimeSegmentView[]
  /** live 网格线（replay 恒 []——刻度行由 segments 承担）。 */
  gridlines: Gridline[]
  /** 相对 T0 毫秒 → 0..1 屏幕位置（窗外时间同样映射，可见性裁剪由 clipSpanToView 负责）。 */
  x(relativeMs: number): number
  /** 0..1 屏幕位置 → 相对 T0 毫秒（拖拽游标反算；快进段内线性插值）。 */
  inverseX(x: number): number
  /** 相对 T0 毫秒 → 全域归一化位置（回放缩放锚点用；live 与 x 等价）。 */
  domainX(relativeMs: number): number
}

export interface OverlapWindow {
  startMs: number
  endMs: number
}

/** 快进段固定占轴宽比例（时间跨度可达数天，必须压缩呈现）。 */
const ACCEL_SEGMENT_WIDTH = 0.06

/** live 窗口基准跨度：过去 10s + 未来 10s（宽屏经 computeLiveWindowMs 自适应扩大）。 */
export const LIVE_WINDOW_BASE_MS = 20_000
/** live 窗口密度（毫秒/像素）。 */
const LIVE_MS_PER_PX = 25

/** live 窗口跨度：基准 20s；轨道更宽时按密度自适应扩大（未来/过去各半）。 */
export function computeLiveWindowMs(widthPx: number): number {
  return Math.max(LIVE_WINDOW_BASE_MS, Math.round(widthPx * LIVE_MS_PER_PX))
}

/** 网格线候选步长（毫秒，1-2-5 序列）。 */
const GRIDLINE_STEPS_MS = [
  100, 200, 500, 1_000, 2_000, 5_000, 10_000, 15_000, 30_000,
  60_000, 120_000, 300_000, 600_000, 1_800_000, 3_600_000,
]
/** 网格线最小像素间距（再密就读不清了）。 */
const GRIDLINE_MIN_PX = 70

/** live 网格线：窗口内按密度选步长，落在整数倍刻度上（随窗口平移流动）。 */
function computeGridlines(
  viewStartMs: number,
  viewEndMs: number,
  widthPx: number,
): Gridline[] {
  if (widthPx <= 0 || viewEndMs <= viewStartMs) return []
  const rawStep = ((viewEndMs - viewStartMs) / widthPx) * GRIDLINE_MIN_PX
  const step =
    GRIDLINE_STEPS_MS.find((s) => s >= rawStep) ??
    GRIDLINE_STEPS_MS[GRIDLINE_STEPS_MS.length - 1]
  const lines: Gridline[] = []
  for (
    let at = Math.ceil(viewStartMs / step) * step;
    at <= viewEndMs;
    at += step
  ) {
    lines.push({
      atMs: at,
      label:
        at === 0
          ? 'T0'
          : at < 0
            ? `-${formatDuration(-at)}`
            : formatDuration(at),
      origin: at === 0,
    })
  }
  return lines
}

function timeMs(iso: string | null, t0Ms: number): number | null {
  if (!iso) return null
  const parsed = Date.parse(iso)
  return Number.isNaN(parsed) ? null : parsed - t0Ms
}

function emptyScale(mode: TimelineMode): TimeScale {
  const x = () => 0
  return {
    mode,
    empty: true,
    viewStartMs: 0,
    viewEndMs: 0,
    endMs: 0,
    axisMs: 0,
    accels: [],
    segments: [],
    gridlines: [],
    x,
    inverseX: () => 0,
    domainX: x,
  }
}

/** 快进段（按 from 升序；防重叠：起点钳到上一段终点之后）。 */
function collectAccels(
  events: ConsoleState['events'],
  t0Ms: number,
): { from: number; to: number }[] {
  const raw = events
    .filter((e): e is AccelerationEvent => e.type === 'acceleration')
    .map((e) => ({
      from: timeMs(e.from, t0Ms) ?? 0,
      to: timeMs(e.to, t0Ms) ?? 0,
    }))
    .filter((a) => a.to > a.from)
    .sort((a, b) => a.from - b.from)
  const accels: { from: number; to: number }[] = []
  for (const accel of raw) {
    const last = accels[accels.length - 1]
    const from = last ? Math.max(accel.from, last.to) : accel.from
    if (accel.to > from) accels.push({ from, to: accel.to })
  }
  return accels
}

/**
 * 全域分段映射（回放）：normal 段按时长比例分宽，acceleration 段固定小宽度。
 * 这是虚拟时间线可读的关键——30s 对话与 5 天快进同轴共存。
 */
function buildDomainMapping(
  endMs: number,
  accels: { from: number; to: number }[],
): {
  segments: TimeSegmentView[]
  xRaw: (relativeMs: number) => number
  inverseRaw: (u: number) => number
} {
  const segments: TimeSegmentView[] = []
  let cursor = 0
  for (const accel of accels) {
    if (accel.from > cursor) {
      segments.push({
        kind: 'normal',
        startMs: cursor,
        endMs: accel.from,
        xStart: 0,
        xEnd: 0,
      })
    }
    segments.push({
      kind: 'acceleration',
      startMs: accel.from,
      endMs: accel.to,
      xStart: 0,
      xEnd: 0,
    })
    cursor = accel.to
  }
  if (endMs > cursor) {
    segments.push({ kind: 'normal', startMs: cursor, endMs, xStart: 0, xEnd: 0 })
  }

  // 分宽：acceleration 段固定宽，normal 段按时长比例分剩余
  const accelWidth = Math.min(
    0.5,
    segments.filter((s) => s.kind === 'acceleration').length * ACCEL_SEGMENT_WIDTH,
  )
  const normalTotal = segments
    .filter((s) => s.kind === 'normal')
    .reduce((sum, s) => sum + (s.endMs - s.startMs), 0)
  let xCursor = 0
  for (const segment of segments) {
    const width =
      segment.kind === 'acceleration'
        ? ACCEL_SEGMENT_WIDTH
        : normalTotal > 0
          ? ((segment.endMs - segment.startMs) / normalTotal) * (1 - accelWidth)
          : 0
    segment.xStart = xCursor
    segment.xEnd = xCursor + width
    xCursor = segment.xEnd
  }

  const xRaw = (relativeMs: number): number => {
    for (const segment of segments) {
      if (
        relativeMs >= segment.startMs &&
        relativeMs <= segment.endMs &&
        segment.endMs > segment.startMs
      ) {
        const ratio =
          (relativeMs - segment.startMs) / (segment.endMs - segment.startMs)
        return segment.xStart + ratio * (segment.xEnd - segment.xStart)
      }
    }
    if (relativeMs <= 0) return 0
    for (const segment of segments) {
      if (relativeMs < segment.startMs) return segment.xStart
    }
    return xCursor
  }
  // 拖拽游标反算：全域位置 → 相对毫秒（段内线性插值；快进段拖到末尾 =
  // 快进完成时刻——语义正确）
  const inverseRaw = (u: number): number => {
    if (u <= 0) return 0
    for (const segment of segments) {
      if (u >= segment.xStart && u <= segment.xEnd) {
        if (segment.endMs <= segment.startMs) return segment.startMs
        const ratio = (u - segment.xStart) / (segment.xEnd - segment.xStart)
        return segment.startMs + ratio * (segment.endMs - segment.startMs)
      }
    }
    return endMs
  }
  return { segments, xRaw, inverseRaw }
}

/** live 滑动窗口选项。 */
export interface LiveScaleOptions {
  mode: 'live'
  /** 当前虚拟时刻（相对 T0 毫秒）。 */
  axisMs: number
  /** 窗口总跨度（毫秒）：过去/未来各半（computeLiveWindowMs 产物）。 */
  windowMs: number
  /** 泳道轨道像素宽（网格线密度自适应；≤0 不画网格线）。 */
  widthPx: number
}

/** 回放视窗选项。 */
export interface ReplayScaleOptions {
  mode: 'replay'
  /** 回放游标（相对 T0 毫秒）。 */
  cursorMs: number
  /** 横向缩放倍数（1 = 全程一览）。 */
  zoom: number
  /** 视窗左缘（全域归一化位置，越界自动钳制）。 */
  panX: number
}

export type ScaleOptions = LiveScaleOptions | ReplayScaleOptions

// ---------------- 回放视窗（zoom / pan） ----------------

/** 回放视窗状态：zoom 缩放倍数 + panX 视窗左缘（全域归一化位置）。 */
export interface ReplayView {
  zoom: number
  panX: number
}

/** 缩放倍数上限（快进带内已无更细粒度内容）。 */
export const REPLAY_ZOOM_MAX = 64

/** panX 钳制到合法视窗范围 [0, 1-1/zoom]。 */
export function clampPanX(panX: number, zoom: number): number {
  const width = 1 / Math.max(1, zoom)
  return Math.min(Math.max(0, panX), Math.max(0, 1 - width))
}

/**
 * 缩放视窗：游标在视窗内 → 锚定游标（游标的屏幕位置缩放后不动）；
 * 否则锚定视窗中心（用户已平移到别处，别把画面拽回去）。
 */
export function zoomReplayView(
  view: ReplayView,
  nextZoom: number,
  cursorDomainX: number,
): ReplayView {
  const zoom = Math.min(REPLAY_ZOOM_MAX, Math.max(1, nextZoom))
  const oldWidth = 1 / Math.max(1, view.zoom)
  const newWidth = 1 / zoom
  const anchor =
    cursorDomainX >= view.panX && cursorDomainX <= view.panX + oldWidth
      ? cursorDomainX
      : view.panX + oldWidth / 2
  const ratio = oldWidth > 0 ? (anchor - view.panX) / oldWidth : 0.5
  return { zoom, panX: clampPanX(anchor - ratio * newWidth, zoom) }
}

/** 播放时视窗自动跟随：游标滑出视窗 → 平移视窗使游标居中；在视窗内原样返回。 */
export function followCursorView(
  view: ReplayView,
  cursorDomainX: number,
): ReplayView {
  const width = 1 / Math.max(1, view.zoom)
  if (cursorDomainX >= view.panX && cursorDomainX <= view.panX + width) {
    return view
  }
  return {
    zoom: view.zoom,
    panX: clampPanX(cursorDomainX - width / 2, view.zoom),
  }
}

/**
 * 时间线刻度（两种模式）：
 *
 * live 滑动窗口：轴线恒 x=0.5，窗口 [axis-半窗, axis+半窗] 随虚拟时间从右
 * 向左流动——未来预设事件从右缘飞入、抵达轴线消失；事件块在轴线处生成
 * 并向左移动（进行中的右端贴轴线增长，结束后定长左移滑出左缘）。
 * 线性映射（快进不压缩——窗口只有 20s 量级，快进表现为窗口整体跳变）。
 *
 * replay 全程视窗：全域分段映射（normal 按时长比例 + 快进压缩窄带）后，
 * 再经 zoom/pan 视窗变换——zoom=1 一览全程，放大后平移查看细节窗口。
 */
export function buildTimeScale(
  events: ConsoleState['events'],
  t0: string | null,
  options: ScaleOptions,
): TimeScale {
  if (!t0) return emptyScale(options.mode)
  const t0Ms = Date.parse(t0)
  if (Number.isNaN(t0Ms)) return emptyScale(options.mode)

  const accels = collectAccels(events, t0Ms)
  let endMs = 0
  for (const span of collectSpanTimes(events, t0Ms)) {
    endMs = Math.max(endMs, span.end)
  }
  for (const accel of accels) {
    endMs = Math.max(endMs, accel.to)
  }

  if (options.mode === 'live') {
    const half = Math.max(1, options.windowMs) / 2
    const axis = options.axisMs
    const viewStartMs = axis - half
    const viewEndMs = axis + half
    const x = (relativeMs: number): number =>
      0.5 + (relativeMs - axis) / (2 * half)
    return {
      mode: 'live',
      empty: false,
      viewStartMs,
      viewEndMs,
      endMs,
      axisMs: axis,
      accels: accels.map((a) => ({ fromMs: a.from, toMs: a.to })),
      segments: [],
      gridlines: computeGridlines(viewStartMs, viewEndMs, options.widthPx),
      x,
      inverseX: (xPos) => axis + (xPos - 0.5) * 2 * half,
      domainX: x,
    }
  }

  if (endMs <= 0) return emptyScale('replay')
  const zoom = Math.max(1, options.zoom)
  const viewWidth = 1 / zoom
  const panX = clampPanX(options.panX, zoom)
  const { segments, xRaw, inverseRaw } = buildDomainMapping(endMs, accels)
  return {
    mode: 'replay',
    empty: false,
    viewStartMs: inverseRaw(panX),
    viewEndMs: inverseRaw(panX + viewWidth),
    endMs,
    axisMs: options.cursorMs,
    accels: accels.map((a) => ({ fromMs: a.from, toMs: a.to })),
    segments: segments.map((s) => ({
      ...s,
      xStart: (s.xStart - panX) * zoom,
      xEnd: (s.xEnd - panX) * zoom,
    })),
    gridlines: [],
    x: (relativeMs) => (xRaw(relativeMs) - panX) * zoom,
    inverseX: (xPos) => inverseRaw(panX + xPos / zoom),
    domainX: xRaw,
  }
}

// ---------------- 窗口内可见性裁剪 ----------------

/** 点事件最小渲染宽度（屏幕百分比）。 */
const MIN_SPAN_WIDTH = 0.5

export interface SpanX {
  x1: number
  x2: number
}

/**
 * 事件区间 → 视窗内屏幕位置：完全在窗外返回 null；跨缘两端裁剪到 [0,1]；
 * 点事件给最小渲染宽度。泳道渲染统一走这里（live 滑动窗口与 replay
 * 缩放视窗共用——事件块从右缘进、左缘出）。
 */
export function clipSpanToView(
  scale: TimeScale,
  startMs: number,
  endMs: number,
): SpanX | null {
  const x1 = scale.x(startMs)
  if (endMs <= startMs) {
    if (x1 < 0 || x1 > 1) return null
    return { x1, x2: Math.min(x1 + MIN_SPAN_WIDTH / 100, 1) }
  }
  const x2 = scale.x(endMs)
  if (x2 <= 0 || x1 >= 1) return null
  return { x1: Math.max(x1, 0), x2: Math.min(x2, 1) }
}

function collectSpanTimes(
  events: ConsoleState['events'],
  t0Ms: number,
): { start: number; end: number }[] {
  const spans: { start: number; end: number }[] = []
  for (const event of events) {
    if (event.type === 'utterance') {
      const start = timeMs(event.startedAt, t0Ms)
      const end = timeMs(event.endedAt, t0Ms)
      if (start !== null && end !== null) {
        spans.push({ start, end })
      }
    } else if (event.mockTime) {
      const at = timeMs(event.mockTime, t0Ms)
      if (at !== null) {
        spans.push({ start: at, end: at })
      }
    }
  }
  return spans
}

/** 事件 → 泳道 spans（utterance 呈现为区间，其余为点事件）。
 *
 * 工具调用不在此投影——见 projectToolSpans（专属工具子泳道）。
 *
 * scriptPlan + axisMs（劲舞团未来区）：预设事件中尚未发生（at > axisMs）
 * 的条目投影为 tone='future' 的点事件——渲染为半透明竖线 + 无框文字，
 * 随时间推进从右向左飞向居中的当前时刻轴线。已发生（≤ axisMs）的条目
 * 由落盘事件接管，不重复显示。
 */
export function projectTimelineSpans(
  events: ConsoleState['events'],
  t0: string | null,
  scriptPlan: ScriptPlanItem[] = [],
  axisMs: number | null = null,
): LaneSpan[] {
  if (!t0) return []
  const t0Ms = Date.parse(t0)
  if (Number.isNaN(t0Ms)) return []

  const spans: LaneSpan[] = []

  for (const event of events) {
    const at = event.mockTime ? timeMs(event.mockTime, t0Ms) : null
    switch (event.type) {
      case 'utterance': {
        const start = timeMs(event.startedAt, t0Ms) ?? 0
        const end = timeMs(event.endedAt, t0Ms) ?? start
        const isFake = isFakePersonRole(event.role)
        const tone: LaneSpan['tone'] = event.isPartial
          ? 'partial'
          : event.isProactive
            ? 'proactive'
            : 'info'
        spans.push({
          id: `span-${event.seq}`,
          lane: isFake ? 'fakePerson' : 'assistant',
          kind: 'utterance',
          label: speakerLabel(event.role),
          detail: event.content,
          startMs: start,
          endMs: Math.max(end, start),
          tone,
        })
        break
      }
      case 'acceleration': {
        const from = timeMs(event.from, t0Ms) ?? 0
        const to = timeMs(event.to, t0Ms) ?? from
        spans.push({
          id: `span-${event.seq}`,
          lane: 'system',
          kind: 'acceleration',
          label: '时间快进',
          detail: `⏩ ${formatDuration(to - from)}`,
          startMs: from,
          endMs: Math.max(to, from),
          tone: 'accel',
        })
        break
      }
      case 'state_check': {
        if (at === null) break
        spans.push({
          id: `span-${event.seq}`,
          lane: 'car',
          kind: 'state_check',
          label: '状态检查',
          detail: formatFields(event.expectedFields),
          startMs: at,
          endMs: at,
          tone: event.passed ? 'ok' : 'fail',
        })
        break
      }
      case 'car_set_state': {
        if (at === null) break
        spans.push({
          id: `span-${event.seq}`,
          lane: 'car',
          kind: 'car_set_state',
          label: '车态变更',
          detail: formatFields(event.updatedFields),
          startMs: at,
          endMs: at,
          tone: 'info',
        })
        break
      }
      case 'system': {
        if (at === null) break
        spans.push({
          id: `span-${event.seq}`,
          lane: 'system',
          kind: 'system',
          label: event.systemKind || '系统事件',
          detail: event.description,
          startMs: at,
          endMs: at,
          tone: 'info',
        })
        break
      }
      case 'long_pause': {
        if (at === null) break
        // 流式停顿是流畅度观察（警示色），不是失败——失败红只留给真正的错误
        spans.push({
          id: `span-${event.seq}`,
          lane: 'system',
          kind: 'long_pause',
          label: '流式停顿',
          detail: `${event.pauseSeconds.toFixed(1)}s`,
          startMs: at,
          endMs: at,
          tone: 'warn',
        })
        break
      }
      default:
        break
    }
  }

  // 未来剧本事件（劲舞团未来区）：预设且未发生 → 半透明竖线点事件
  if (axisMs !== null) {
    for (const item of scriptPlan) {
      const atMs = timeMs(item.at, t0Ms)
      if (atMs === null || atMs <= axisMs) continue
      spans.push({
        id: `plan-${item.kind}-${item.at}-${item.target}`,
        lane: planLane(item),
        kind: 'future',
        label: item.label,
        detail: '',
        startMs: atMs,
        endMs: atMs,
        tone: 'future',
      })
    }
  }
  return spans
}

/** 剧本时间表条目 → 泳道：假人话语进假人泳道，车态/检查进车泳道，其余进系统泳道。 */
function planLane(item: ScriptPlanItem): LaneId {
  if (item.kind === 'fake_person_speak') return 'fakePerson'
  if (item.kind === 'car_set_state' || item.kind === 'state_check') return 'car'
  return 'system'
}

// ---------------- 工具子泳道投影（助手下层的低一层级泳道） ----------------

export interface ToolSpanView {
  id: string
  toolName: string
  argsText: string
  resultText: string | null
  durationMs: number | null
  startMs: number
  /** 执行中（result 未到）：实时 = nowMs，回放 = cursorMs（条随时间/游标增长）。 */
  endMs: number
  /** result 未落盘（执行中——右端脉冲，时间线/游标推进时增长）。 */
  pending: boolean
  /** 并行行号（0-based，行打包：时间重叠的工具分到不同行）。 */
  row: number
}

/**
 * 工具调用区间化：tool_call × tool_result 栈式配对（LIFO，与轨迹渲染一致）。
 *
 * 行打包：按 call 时刻排序后贪心分配——执行中的条视为占满整行
 * （endMs 会随 nowMs/游标增长，防止后到的并行条错分到同一行）；
 * 已完成的条按真实区间参与分配。
 *
 * cursorMs（回放模式，所有事件已确定）：
 * - 游标未到 call（未来）→ 展示完整确定区间（pending=false，渲染层按
 *   startMs > cursorMs 加 dim 区分「待回放」，与未来话语一致）
 * - call ≤ 游标 < result → 执行中（endMs = 游标，条随游标增长）
 * - ≥ result → 完整区间
 */
export function projectToolSpans(
  events: ConsoleState['events'],
  t0: string | null,
  cursorMs: number | null = null,
  nowMs: number | null = null,
): ToolSpanView[] {
  if (!t0) return []
  const t0Ms = Date.parse(t0)
  if (Number.isNaN(t0Ms)) return []
  const replay = cursorMs !== null

  // 配对：call → {startMs, ...}；result 到达时闭合
  interface PendingCall {
    seq: number
    startMs: number
    toolName: string
    argsText: string
    endMs: number | null
    resultText: string | null
    durationMs: number | null
    row: number
  }
  const calls: PendingCall[] = []
  // task_id 优先精确配对（并行同名工具不误配）；缺失时回退 toolName FIFO
  const openByTask = new Map<string, PendingCall>()
  const openByName = new Map<string, PendingCall[]>()
  for (const event of events) {
    if (event.type === 'tool_call') {
      const startMs = event.mockTime ? timeMs(event.mockTime, t0Ms) : null
      if (startMs === null) continue
      const call: PendingCall = {
        seq: event.seq,
        startMs,
        toolName: event.toolName,
        argsText: formatFields(event.toolArgs),
        endMs: null,
        resultText: null,
        durationMs: null,
        row: 0, // 行打包阶段统一分配
      }
      calls.push(call)
      const taskId = event.taskId ?? null
      if (taskId) {
        openByTask.set(taskId, call)
      } else {
        const queue = openByName.get(event.toolName)
        if (queue) queue.push(call)
        else openByName.set(event.toolName, [call])
      }
    } else if (event.type === 'tool_result') {
      const atMs = event.mockTime ? timeMs(event.mockTime, t0Ms) : null
      if (atMs === null) continue
      const taskId = event.taskId ?? null
      let call: PendingCall | undefined
      if (taskId) {
        call = openByTask.get(taskId)
        if (call) openByTask.delete(taskId)
      } else {
        call = openByName.get(event.toolName)?.shift()
      }
      if (call) {
        call.endMs = atMs
        call.resultText =
          typeof event.result === 'string'
            ? event.result
            : JSON.stringify(event.result)
        call.durationMs = event.durationMs ?? null
      }
    }
  }

  // 行打包（按 call 时刻贪心；执行中条占满整行）
  const rowEnds: number[] = [] // 每行最后占用时刻（Infinity = 该行有执行中条）
  const sorted = [...calls].sort((a, b) => a.startMs - b.startMs)
  for (const call of sorted) {
    let row = rowEnds.findIndex((end) => call.startMs >= end)
    if (row === -1) {
      row = rowEnds.length
      rowEnds.push(0)
    }
    rowEnds[row] = call.endMs !== null ? call.endMs : Number.POSITIVE_INFINITY
    call.row = row
  }

  return sorted.map((call): ToolSpanView => {
    const start = call.startMs
    const knownEnd = call.endMs
    let endMs: number
    let pending: boolean

    if (!replay) {
      // 实时模式：未闭合的执行中（尾随 nowMs 增长），已闭合的完整区间
      endMs = knownEnd ?? (nowMs ?? start)
      pending = knownEnd === null
    } else if (start > cursorMs) {
      // 回放 + 未来事件（结果已确定）：展示完整区间而非按游标过滤；
      // 未闭合（result 从未落盘）退化为 start 处点标记
      endMs = knownEnd ?? start
      pending = knownEnd === null
    } else if (knownEnd === null || knownEnd > cursorMs) {
      // 回放 + 执行中（未闭合或结果未到）：条尾随游标增长
      endMs = cursorMs
      pending = true
    } else {
      // 回放 + 已完成：完整区间
      endMs = knownEnd
      pending = false
    }

    return {
      id: `tool-${call.seq}`,
      toolName: call.toolName,
      argsText: call.argsText,
      resultText: call.resultText,
      durationMs: call.durationMs,
      startMs: start,
      endMs: Math.max(endMs, start),
      pending,
      row: call.row,
    }
  })
}

// ---------------- live 增长条投影（实时话语） ----------------

export interface LiveSpanView {
  id: string
  lane: 'fakePerson' | 'assistant'
  /** 开口时刻（首个 delta 的 mockTime；缺失时不渲染——由调用方过滤）。 */
  startMs: number
  endMs: number
}

/**
 * 正在说的话 → 时间线增长条：[开口时刻, now]。
 * 落盘后由 utterance 权威区间无缝接管（reducer 同刻清空 live 缓冲）。
 * 回放模式不适用（回放基于落盘 segments 裁剪，见 projectDialogue）。
 */
export function projectLiveSpans(
  state: ConsoleState,
  nowMs: number | null,
): LiveSpanView[] {
  if (nowMs === null || !state.t0) return []
  const t0Ms = Date.parse(state.t0)
  if (Number.isNaN(t0Ms)) return []

  const spans: LiveSpanView[] = []
  const startOf = (iso: string | null): number | null => {
    if (!iso) return null
    const parsed = Date.parse(iso)
    return Number.isNaN(parsed) ? null : parsed - t0Ms
  }
  const fakeStart = startOf(state.liveFakePerson?.startedAt ?? null)
  if (state.liveFakePerson && state.liveFakePerson.text !== '' && fakeStart !== null) {
    spans.push({
      id: 'live-fake-person',
      lane: 'fakePerson',
      startMs: Math.min(fakeStart, nowMs),
      endMs: nowMs,
    })
  }
  const assistantStart = startOf(state.liveAssistant.startedAt)
  if (state.liveAssistant.text !== '' && assistantStart !== null) {
    spans.push({
      id: 'live-assistant',
      lane: 'assistant',
      startMs: Math.min(assistantStart, nowMs),
      endMs: nowMs,
    })
  }
  return spans
}

/** 重叠说话窗口：假人话语区间 × 助手话语区间求交（本框架核心展示点）。 */
export function computeOverlaps(
  events: ConsoleState['events'],
  t0: string | null,
): OverlapWindow[] {
  if (!t0) return []
  const t0Ms = Date.parse(t0)
  if (Number.isNaN(t0Ms)) return []

  const fakeSpans = events
    .filter(
      (e): e is UtteranceEvent =>
        e.type === 'utterance' && isFakePersonRole(e.role),
    )
    .map((e) => ({
      start: timeMs(e.startedAt, t0Ms) ?? 0,
      end: timeMs(e.endedAt, t0Ms) ?? 0,
    }))
  const assistantSpans = events
    .filter(
      (e): e is UtteranceEvent =>
        e.type === 'utterance' && !isFakePersonRole(e.role),
    )
    .map((e) => ({
      start: timeMs(e.startedAt, t0Ms) ?? 0,
      end: timeMs(e.endedAt, t0Ms) ?? 0,
    }))

  const overlaps: OverlapWindow[] = []
  for (const fake of fakeSpans) {
    for (const assistant of assistantSpans) {
      const start = Math.max(fake.start, assistant.start)
      const end = Math.min(fake.end, assistant.end)
      if (end > start) {
        overlaps.push({ startMs: start, endMs: end })
      }
    }
  }
  return overlaps
}

// ---------------- 格式化 ----------------

export function formatDuration(ms: number): string {
  const seconds = ms / 1000
  if (seconds < 60) {
    return Number.isInteger(seconds)
      ? `${seconds}s`
      : `${seconds.toFixed(1)}s`
  }
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) {
    return `${minutes}m${Math.round(seconds % 60)}s`
  }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours}h${minutes % 60}m`
  }
  const days = Math.floor(hours / 24)
  return `${days}d${hours % 24}h`
}

export function formatRelative(ms: number): string {
  const sign = ms < 0 ? '-' : '+'
  return `T0 ${sign}${formatDuration(Math.abs(ms))}`
}

function formatFields(fields: Record<string, unknown>): string {
  const entries = Object.entries(fields)
  if (entries.length === 0) return ''
  return entries
    .slice(0, 3)
    .map(([key, value]) => `${key}=${String(value)}`)
    .join('，')
}

/** 剧本事件字段完整展开（不截断——上帝视角可能一次改多个车态字段）。 */
function formatFieldsFull(fields: Record<string, unknown>): string {
  const entries = Object.entries(fields)
  if (entries.length === 0) return ''
  return entries.map(([key, value]) => `${key}=${String(value)}`).join('，')
}

/** 点事件相对 T0 时刻文本："T+5.0s"；atMs 缺失时 null。 */
function formatPointTime(atMs: number | null): string | null {
  if (atMs === null) return null
  return `T+${formatDuration(Math.max(atMs, 0))}`
}
