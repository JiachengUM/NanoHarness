import { describe, expect, it } from 'vitest'
import {
  buildTimeScale,
  clampPanX,
  clipSpanToView,
  computeLiveWindowMs,
  computeOverlaps,
  followCursorView,
  formatDuration,
  formatRelative,
  projectCarState,
  projectDialogue,
  projectLiveSpans,
  projectTimelineSpans,
  projectToolSpans,
  REPLAY_ZOOM_MAX,
  zoomReplayView,
  type LaneSpan,
  type ReplayView,
} from './projections'
import {
  consoleReducer,
  initialConsoleState,
  type ConsoleState,
} from './consoleReducer'
import type { EventMeta, ScriptPlanItem, VisualizerEvent } from '../domain/events'

const T0 = '2026-08-26T10:00:00'

const meta = (seq: number, mockTime: string | null = null): EventMeta => ({
  seq,
  wallTime: '2026-08-26T10:00:00',
  mockTime,
})

function utterance(
  seq: number,
  role: string,
  startOffsetSec: number,
  endOffsetSec: number,
  extra: Partial<Extract<VisualizerEvent, { type: 'utterance' }>> = {},
): VisualizerEvent {
  const startedAt = new Date(Date.parse(T0) + startOffsetSec * 1000).toISOString()
  const endedAt = new Date(Date.parse(T0) + endOffsetSec * 1000).toISOString()
  return {
    ...meta(seq, startedAt),
    type: 'utterance',
    speakerKind: role.startsWith('fake_person') ? 'fake_person_speak' : 'assistant_reply',
    role,
    content: `话${seq}`,
    startedAt,
    endedAt,
    isPartial: false,
    interruptedByBargeIn: false,
    speechDuration: undefined,
    ttft: undefined,
    isProactive: false,
    segments: [],
    ...extra,
  }
}

function stateWith(
  events: VisualizerEvent[],
  initialCarInfo: Record<string, unknown> | null = null,
  carStateGroups: Record<string, string[]> | null = null,
  scriptPlan: ScriptPlanItem[] = [],
): ConsoleState {
  let state = initialConsoleState()
  state = consoleReducer(state, {
    type: 'event',
    event: {
      ...meta(0, T0),
      type: 'case_started',
      caseId: 'c1',
      caseName: '',
      caseDescription: '',
      t0: T0,
      sessionId: 's',
      initialCarInfo,
      carStateGroups,
      scriptPlan,
    },
  })
  for (const event of events) {
    state = consoleReducer(state, { type: 'event', event })
  }
  return state
}

describe('buildTimeScale · live 滑动窗口', () => {
  const live = (axisMs: number, windowMs = 20_000, widthPx = 800) =>
    buildTimeScale([utterance(1, 'fake_person:driver', 0, 10)], T0, {
      mode: 'live',
      axisMs,
      windowMs,
      widthPx,
    })

  it('无 t0 时返回空刻度', () => {
    const scale = buildTimeScale([], null, {
      mode: 'live',
      axisMs: 0,
      windowMs: 20_000,
      widthPx: 800,
    })
    expect(scale.empty).toBe(true)
    expect(scale.mode).toBe('live')
  })

  it('轴线恒居中 x=0.5：窗口 [axis-半窗, axis+半窗]，历史在左未来在右', () => {
    // 轴 25s + 20s 窗 → 可视 [15s, 35s]
    const scale = live(25_000)
    expect(scale.empty).toBe(false)
    expect(scale.viewStartMs).toBe(15_000)
    expect(scale.viewEndMs).toBe(35_000)
    expect(scale.axisMs).toBe(25_000)
    expect(scale.x(25_000)).toBeCloseTo(0.5)
    expect(scale.x(15_000)).toBeCloseTo(0)
    expect(scale.x(35_000)).toBeCloseTo(1)
    // 历史在左半（20s 在轴线左侧）
    expect(scale.x(20_000)).toBeCloseTo(0.25)
    // 未来在右半（30s 在轴线右侧）
    expect(scale.x(30_000)).toBeCloseTo(0.75)
    // endMs 不随轴外扩（窗口固定 20s，与事件边界无关）
    expect(scale.endMs).toBe(10_000)
  })

  it('x ↔ inverseX 互逆（窗口线性映射）', () => {
    const scale = live(25_000)
    expect(scale.inverseX(scale.x(18_000))).toBeCloseTo(18_000)
    expect(scale.inverseX(scale.x(32_000))).toBeCloseTo(32_000)
    // 拖拽中央（x=0.5）反算回轴线时刻
    expect(scale.inverseX(0.5)).toBeCloseTo(25_000)
  })

  it('轴=0（case 刚开始）：窗口 [-10s, +10s]，历史区为空', () => {
    const scale = live(0)
    expect(scale.viewStartMs).toBe(-10_000)
    expect(scale.viewEndMs).toBe(10_000)
    expect(scale.x(0)).toBeCloseTo(0.5)
    // T0 之前（负时间）映射到左半
    expect(scale.x(-5_000)).toBeCloseTo(0.25)
  })

  it('窗外时间同样可映射（可见性由 clipSpanToView 裁剪，x 不钳位）', () => {
    const scale = live(25_000)
    expect(scale.x(5_000)).toBeCloseTo(-0.5)
    expect(scale.x(45_000)).toBeCloseTo(1.5)
  })

  it('网格线：落在整数倍刻度上、随窗口流动；T0 原点线加粗', () => {
    // 20s 窗 + 800px → 密度选步长 2s
    const scale = live(25_000)
    const lines = scale.gridlines
    expect(lines.length).toBeGreaterThan(0)
    // 全部在窗口内且等距
    for (const line of lines) {
      expect(line.atMs).toBeGreaterThanOrEqual(15_000)
      expect(line.atMs).toBeLessThanOrEqual(35_000)
    }
    const step = lines[1].atMs - lines[0].atMs
    expect(step).toBe(2_000)
    expect(lines.some((l) => l.origin)).toBe(false) // 窗内无 T0

    // 轴 5s：窗口 [-5s, 15s] 含 T0 → 原点线存在
    const withOrigin = live(5_000)
    const origin = withOrigin.gridlines.find((l) => l.origin)
    expect(origin).toBeDefined()
    expect(origin?.atMs).toBe(0)
    expect(origin?.label).toBe('T0')
    // 负时间刻度标签带负号
    const negative = withOrigin.gridlines.find((l) => l.atMs < 0)
    expect(negative?.label).toMatch(/^-/)
  })

  it('widthPx ≤ 0 不画网格线（不影响刻度映射）', () => {
    const scale = live(25_000, 20_000, 0)
    expect(scale.gridlines).toEqual([])
    expect(scale.x(25_000)).toBeCloseTo(0.5)
  })
})

describe('computeLiveWindowMs（窗口自适应）', () => {
  it('基准 20s；窄轨道不缩，宽轨道按 25ms/px 扩大', () => {
    expect(computeLiveWindowMs(0)).toBe(20_000)
    expect(computeLiveWindowMs(400)).toBe(20_000) // 400×25=10s < 20s
    expect(computeLiveWindowMs(1200)).toBe(30_000) // 1200×25=30s > 20s
  })
})

describe('buildTimeScale · replay 全程视窗', () => {
  it('无事件（endMs=0）返回空刻度', () => {
    const scale = buildTimeScale([], T0, {
      mode: 'replay',
      cursorMs: 0,
      zoom: 1,
      panX: 0,
    })
    expect(scale.empty).toBe(true)
    expect(scale.mode).toBe('replay')
  })

  it('zoom=1 全程一览：线性轴 [0,1] 映射，viewStart/viewEnd = 全域', () => {
    const scale = buildTimeScale(
      [utterance(1, 'fake_person:driver', 0, 10), utterance(2, 'assistant', 10, 20)],
      T0,
      { mode: 'replay', cursorMs: 5_000, zoom: 1, panX: 0 },
    )
    expect(scale.endMs).toBe(20_000)
    expect(scale.axisMs).toBe(5_000) // 轴 = 回放游标
    expect(scale.viewStartMs).toBe(0)
    expect(scale.viewEndMs).toBe(20_000)
    expect(scale.x(0)).toBeCloseTo(0)
    expect(scale.x(10_000)).toBeCloseTo(0.5)
    expect(scale.x(20_000)).toBeCloseTo(1)
    expect(scale.inverseX(scale.x(12_345))).toBeCloseTo(12_345)
    expect(scale.segments).toHaveLength(1)
    expect(scale.segments[0].kind).toBe('normal')
  })

  it('zoom>1 视窗变换：viewStart/viewEnd 反算回时间，游标可被映射到任意屏幕位置', () => {
    // zoom=4, panX=0.375 → 视窗 [0.375, 0.625] → 时间 [7.5s, 12.5s]
    const scale = buildTimeScale(
      [utterance(1, 'fake_person:driver', 0, 10), utterance(2, 'assistant', 10, 20)],
      T0,
      { mode: 'replay', cursorMs: 10_000, zoom: 4, panX: 0.375 },
    )
    expect(scale.viewStartMs).toBeCloseTo(7_500)
    expect(scale.viewEndMs).toBeCloseTo(12_500)
    // 视窗两端贴屏幕边缘
    expect(scale.x(7_500)).toBeCloseTo(0)
    expect(scale.x(12_500)).toBeCloseTo(1)
    // 窗外时间不钳位（裁剪交给 clipSpanToView）
    expect(scale.x(2_000)).toBeCloseTo(-1.1)
    // inverseX 在视窗内互逆
    expect(scale.inverseX(scale.x(10_000))).toBeCloseTo(10_000)
    // domainX 与 zoom/pan 无关（缩放锚点坐标系）
    expect(scale.domainX(10_000)).toBeCloseTo(0.5)
  })

  it('含快进：normal 段按时长比例 + acceleration 段固定 6% 窄带；段边界连续', () => {
    const fiveDays = 5 * 24 * 3600 * 1000
    const scale = buildTimeScale(
      [
        utterance(1, 'fake_person:driver', 0, 10),
        {
          ...meta(2, null),
          type: 'acceleration',
          from: new Date(Date.parse(T0) + 10000).toISOString(),
          to: new Date(Date.parse(T0) + fiveDays).toISOString(),
        },
        utterance(3, 'fake_person:driver', 5 * 24 * 3600, 5 * 24 * 3600 + 10),
      ],
      T0,
      { mode: 'replay', cursorMs: 0, zoom: 1, panX: 0 },
    )
    expect(scale.endMs).toBe(fiveDays + 10_000)
    // 三段：normal(0-10s) / acceleration / normal(尾段)
    expect(scale.segments.map((s) => s.kind)).toEqual([
      'normal',
      'acceleration',
      'normal',
    ])
    // 快进段固定 6% 宽；两段 normal 时长相同各 47%
    const [first, accel, last] = scale.segments
    expect(accel.xEnd - accel.xStart).toBeCloseTo(0.06)
    expect(first.xEnd - first.xStart).toBeCloseTo(0.47)
    expect(last.xEnd - last.xStart).toBeCloseTo(0.47)
    // 映射连续性：快进起点 x == 前段终点 x
    expect(scale.x(10_000)).toBeCloseTo(first.xEnd)
    // 5 天被压进 6% 窄带
    const midAccel = scale.x(10_000 + 2.5 * 24 * 3600 * 1000)
    expect(midAccel).toBeGreaterThan(accel.xStart)
    expect(midAccel).toBeLessThan(accel.xEnd)
    // 快进带内反算：两端点互逆
    expect(scale.inverseX(accel.xStart)).toBeCloseTo(10_000, -2)
    expect(scale.inverseX(accel.xEnd)).toBeCloseTo(fiveDays, -2)
    expect(scale.inverseX(scale.x(fiveDays - 1000))).toBeCloseTo(fiveDays - 1000, -3)
  })

  it('回放模式不画网格线（刻度行由 segments 承担）', () => {
    const scale = buildTimeScale([utterance(1, 'assistant', 0, 10)], T0, {
      mode: 'replay',
      cursorMs: 0,
      zoom: 1,
      panX: 0,
    })
    expect(scale.gridlines).toEqual([])
  })
})

describe('clipSpanToView（视窗裁剪）', () => {
  // 轴 25s + 20s 窗 → 可视 [15s, 35s]
  const scale = buildTimeScale([utterance(1, 'fake_person:driver', 0, 10)], T0, {
    mode: 'live',
    axisMs: 25_000,
    windowMs: 20_000,
    widthPx: 0,
  })

  it('完全在窗外返回 null（左侧历史已滑出 / 右侧未来未到）', () => {
    expect(clipSpanToView(scale, 5_000, 10_000)).toBeNull()
    expect(clipSpanToView(scale, 40_000, 45_000)).toBeNull()
  })

  it('跨缘区间两端裁剪到 [0,1]', () => {
    // 左缘：[10s, 20s] → x [-0.25, 0.25] → 裁为 [0, 0.25]
    expect(clipSpanToView(scale, 10_000, 20_000)).toEqual({ x1: 0, x2: 0.25 })
    // 右缘：[30s, 40s] → x [0.75, 1.25] → 裁为 [0.75, 1]
    expect(clipSpanToView(scale, 30_000, 40_000)).toEqual({ x1: 0.75, x2: 1 })
  })

  it('进行中的增长条右端贴轴线（[20s, 25s] → [0.25, 0.5]）', () => {
    expect(clipSpanToView(scale, 20_000, 25_000)).toEqual({ x1: 0.25, x2: 0.5 })
  })

  it('点事件给最小渲染宽度；窗外点事件不渲染', () => {
    const pos = clipSpanToView(scale, 25_000, 25_000)
    expect(pos).not.toBeNull()
    expect(pos?.x1).toBeCloseTo(0.5)
    expect(pos!.x2).toBeGreaterThan(pos!.x1)
    expect(clipSpanToView(scale, 40_000, 40_000)).toBeNull()
  })
})

describe('回放视窗（clampPanX / zoomReplayView / followCursorView）', () => {
  it('clampPanX 钳制到 [0, 1-1/zoom]', () => {
    expect(clampPanX(-0.2, 1)).toBe(0)
    expect(clampPanX(0.9, 1)).toBe(0) // zoom=1 时无可平移范围
    expect(clampPanX(0.9, 4)).toBe(0.75)
    expect(clampPanX(-1, 4)).toBe(0)
  })

  it('zoomReplayView 锚定游标：缩放后游标的屏幕位置不动', () => {
    // 游标 domain 0.5 在视窗内 → 缩放 4× 后游标仍在 x=0.5
    const next = zoomReplayView({ zoom: 1, panX: 0 }, 4, 0.5)
    expect(next.zoom).toBe(4)
    expect(next.panX).toBeCloseTo(0.375)
    // 游标屏幕位置：(0.5 - 0.375) × 4 = 0.5 ✓
    // 反算游标视窗内位置
    const width = 1 / 4
    const cursorScreenX = (0.5 - next.panX) / width
    expect(cursorScreenX).toBeCloseTo(0.5)
  })

  it('zoomReplayView 游标在视窗外：锚定视窗中心（不把画面拽回游标）', () => {
    // 视窗 [0.6, 0.725]，游标 0.9 在外 → 锚点 = 视窗中心 0.6625
    const next = zoomReplayView({ zoom: 8, panX: 0.6 }, 4, 0.9)
    expect(next.zoom).toBe(4)
    expect(next.panX).toBeCloseTo(0.5375)
  })

  it('zoomReplayView 倍速钳制到 [1, REPLAY_ZOOM_MAX]', () => {
    expect(zoomReplayView({ zoom: 1, panX: 0 }, 0.5, 0.5).zoom).toBe(1)
    expect(zoomReplayView({ zoom: 1, panX: 0 }, 999, 0.5).zoom).toBe(
      REPLAY_ZOOM_MAX,
    )
  })

  it('followCursorView：游标在视窗内原样返回（引用不变）', () => {
    const view: ReplayView = { zoom: 4, panX: 0.25 }
    expect(followCursorView(view, 0.3)).toBe(view)
  })

  it('followCursorView：游标滑出视窗 → 平移使其居中', () => {
    const next = followCursorView({ zoom: 4, panX: 0.25 }, 0.9)
    expect(next).toEqual({ zoom: 4, panX: 0.75 })
    // 游标 0.9 居中：视窗 [0.775, 1.025→钳0.75]，0.9 在内
    expect(next.panX).toBeLessThanOrEqual(0.9)
    expect(next.panX + 0.25).toBeGreaterThanOrEqual(0.9)
  })

  it('followCursorView：zoom=1 全程可见恒不跟随', () => {
    expect(followCursorView({ zoom: 1, panX: 0 }, 0.99)).toEqual({
      zoom: 1,
      panX: 0,
    })
  })
})

describe('computeOverlaps', () => {
  it('检测假人×助手话语区间重叠窗口', () => {
    // 假人 0-10s；助手 6-20s → 重叠 6-10s
    const overlaps = computeOverlaps(
      [utterance(1, 'fake_person:driver', 0, 10), utterance(2, 'assistant', 6, 20)],
      T0,
    )
    expect(overlaps).toHaveLength(1)
    expect(overlaps[0].startMs).toBe(6000)
    expect(overlaps[0].endMs).toBe(10000)
  })

  it('不重叠的话语不产生窗口', () => {
    const overlaps = computeOverlaps(
      [utterance(1, 'fake_person:driver', 0, 5), utterance(2, 'assistant', 6, 20)],
      T0,
    )
    expect(overlaps).toEqual([])
  })
})

describe('projectTimelineSpans', () => {
  it('话语→对应泳道区间；快进/检查/车控→系统与车泳道', () => {
    const spans = projectTimelineSpans(
      [
        utterance(1, 'fake_person:driver', 0, 5),
        utterance(2, 'assistant', 6, 10),
        {
          ...meta(3, new Date(Date.parse(T0) + 12000).toISOString()),
          type: 'state_check',
          expectedFields: { 空调开启状态及模式: '制冷中' },
          actualFields: { 空调开启状态及模式: '制冷中' },
          passed: true,
          mismatches: {},
        },
        {
          ...meta(4, new Date(Date.parse(T0) + 13000).toISOString()),
          type: 'car_set_state',
          updatedFields: { 空调开启状态及模式: '制冷中' },
          source: null,
        },
        {
          ...meta(5, null),
          type: 'acceleration',
          from: new Date(Date.parse(T0) + 14000).toISOString(),
          to: new Date(Date.parse(T0) + 86400000).toISOString(),
        },
      ],
      T0,
    )
    const byLane = (lane: LaneSpan['lane']) =>
      spans.filter((s) => s.lane === lane)
    expect(byLane('fakePerson')).toHaveLength(1)
    expect(byLane('assistant')).toHaveLength(1)
    expect(byLane('car')).toHaveLength(2) // state_check + car_set_state
    expect(byLane('system')).toHaveLength(1) // acceleration
    expect(byLane('car')[0].tone).toBe('ok')
  })

  it('半截话 tone=partial；主动话语 tone=proactive', () => {
    const spans = projectTimelineSpans(
      [
        utterance(1, 'assistant', 0, 5, { isPartial: true, interruptedByBargeIn: true }),
        utterance(2, 'assistant', 6, 10, { isProactive: true }),
      ],
      T0,
    )
    expect(spans[0].tone).toBe('partial')
    expect(spans[1].tone).toBe('proactive')
  })

  it('工具调用不在通用泳道投影（专属工具子泳道，见 projectToolSpans）', () => {
    const t = (sec: number) => new Date(Date.parse(T0) + sec * 1000).toISOString()
    const spans = projectTimelineSpans(
      [
        {
          ...meta(1, t(10)),
          type: 'tool_call',
          toolName: 'set_reminder',
          toolArgs: { minutes: 35 },
        },
        {
          ...meta(2, t(13)),
          type: 'tool_result',
          toolName: 'set_reminder',
          result: '已设置',
          durationMs: 250,
        },
      ],
      T0,
    )
    expect(spans).toHaveLength(0)
  })

  it('流式停顿 tone=warn（警示色，不是失败红）', () => {
    const t = (sec: number) => new Date(Date.parse(T0) + sec * 1000).toISOString()
    const spans = projectTimelineSpans(
      [
        {
          ...meta(1, t(12)),
          type: 'long_pause',
          pauseSeconds: 3.2,
        },
      ],
      T0,
    )
    expect(spans[0]).toMatchObject({
      lane: 'system',
      kind: 'long_pause',
      tone: 'warn',
    })
  })

  it('未来剧本事件（劲舞团未来区）：axisMs 之后的预设事件 → tone=future 点事件；已发生的过滤', () => {
    const t = (sec: number) => new Date(Date.parse(T0) + sec * 1000).toISOString()
    const plan: ScriptPlanItem[] = [
      { kind: 'fake_person_speak', at: t(30), target: 'driver', label: 'driver：开下空调' },
      { kind: 'car_set_state', at: t(50), target: 'car', label: '剧本改车态：车速=60' },
      { kind: 'state_check', at: t(70), target: 'car', label: '状态检查：空调=制冷中' },
      { kind: 'car_set_state', at: t(20), target: 'car', label: '剧本改车态：车窗=开启' },
    ]
    // 轴线 25s：30s/50s/70s 的预设事件在未来区；20s 已过（由落盘事件接管）
    const spans = projectTimelineSpans([], T0, plan, 25_000)
    const futures = spans.filter((s) => s.kind === 'future')
    expect(futures).toHaveLength(3)
    expect(futures[0]).toMatchObject({
      lane: 'fakePerson',
      tone: 'future',
      startMs: 30_000,
      endMs: 30_000,
      label: 'driver：开下空调',
    })
    expect(futures[1]).toMatchObject({ lane: 'car', startMs: 50_000 })
    expect(futures[2]).toMatchObject({ lane: 'car', startMs: 70_000 })
    // axisMs=null（旧语义）：不生成未来事件
    expect(projectTimelineSpans([], T0, plan, null)).toHaveLength(0)
  })
})

describe('projectToolSpans（工具子泳道）', () => {
  const t = (sec: number) => new Date(Date.parse(T0) + sec * 1000).toISOString()

  it('call×result 配对成区间；未配对 call 执行中尾随 nowMs', () => {
    const spans = projectToolSpans(
      [
        {
          ...meta(1, t(10)),
          type: 'tool_call',
          toolName: 'set_reminder',
          toolArgs: { minutes: 35 },
        },
        {
          ...meta(2, t(13)),
          type: 'tool_result',
          toolName: 'set_reminder',
          result: '已设置',
          durationMs: 250,
        },
        {
          ...meta(3, t(20)),
          type: 'tool_call',
          toolName: 'virtual_car_control',
          toolArgs: { command: '开空调' },
        },
      ],
      T0,
      null, // 实时模式
      22_000, // nowMs
    )
    expect(spans).toHaveLength(2)
    // 配对成功 → 区间 [call, result]，结果/耗时回填
    expect(spans[0]).toMatchObject({
      toolName: 'set_reminder',
      startMs: 10_000,
      endMs: 13_000,
      pending: false,
      durationMs: 250,
    })
    expect(spans[0].resultText).toContain('已设置')
    expect(spans[0].argsText).toContain('minutes=35')
    // 未配对 call → 执行中，右端尾随 nowMs（条不断变长）
    expect(spans[1]).toMatchObject({
      startMs: 20_000,
      endMs: 22_000,
      pending: true,
    })
    expect(spans[1].resultText).toBeNull()
  })

  it('实时模式：未闭合工具随 nowMs 推进从左侧增长（endMs 不断变长）', () => {
    const events: VisualizerEvent[] = [
      { ...meta(1, t(10)), type: 'tool_call', toolName: 'poi_search', toolArgs: {} },
    ]
    const early = projectToolSpans(events, T0, null, 12_000)
    const later = projectToolSpans(events, T0, null, 18_000)
    // 起点不变，右端尾随 nowMs 增长——条随虚拟时间推进不断变长
    expect(early[0]).toMatchObject({ startMs: 10_000, endMs: 12_000, pending: true })
    expect(later[0]).toMatchObject({ startMs: 10_000, endMs: 18_000, pending: true })
  })

  it('多工具并行 → 行打包分到不同行；串行复用同一行', () => {
    const spans = projectToolSpans(
      [
        { ...meta(1, t(10)), type: 'tool_call', toolName: 'nav_a', toolArgs: {} },
        { ...meta(2, t(11)), type: 'tool_call', toolName: 'nav_b', toolArgs: {} },
        { ...meta(3, t(12)), type: 'tool_call', toolName: 'nav_c', toolArgs: {} },
        { ...meta(4, t(30)), type: 'tool_result', toolName: 'nav_a', result: 'a', durationMs: 1 },
        { ...meta(5, t(31)), type: 'tool_result', toolName: 'nav_b', result: 'b', durationMs: 1 },
        { ...meta(6, t(32)), type: 'tool_result', toolName: 'nav_c', result: 'c', durationMs: 1 },
        // nav_a 结束后的新调用 → 可复用第 0 行
        { ...meta(7, t(40)), type: 'tool_call', toolName: 'nav_d', toolArgs: {} },
        { ...meta(8, t(42)), type: 'tool_result', toolName: 'nav_d', result: 'd', durationMs: 1 },
      ],
      T0,
    )
    const byTool = new Map(spans.map((s) => [s.toolName, s]))
    expect(byTool.get('nav_a')?.row).toBe(0)
    expect(byTool.get('nav_b')?.row).toBe(1)
    expect(byTool.get('nav_c')?.row).toBe(2)
    expect(byTool.get('nav_d')?.row).toBe(0) // 复用已结束的行
  })

  it('同名并行工具按 task_id 精确配对（结果乱序不误配）', () => {
    const spans = projectToolSpans(
      [
        { ...meta(1, t(10)), type: 'tool_call', toolName: 'poi_search', toolArgs: { q: 'A' }, taskId: 't1' },
        { ...meta(2, t(11)), type: 'tool_call', toolName: 'poi_search', toolArgs: { q: 'B' }, taskId: 't2' },
        // 结果乱序返回（B 先于 A）：按 task_id 也应各配到正确 call
        { ...meta(3, t(20)), type: 'tool_result', toolName: 'poi_search', result: 'B结果', durationMs: 9000, taskId: 't2' },
        { ...meta(4, t(25)), type: 'tool_result', toolName: 'poi_search', result: 'A结果', durationMs: 15000, taskId: 't1' },
      ],
      T0,
    )
    expect(spans).toHaveLength(2)
    const byArgs = new Map(spans.map((s) => [s.argsText, s]))
    expect(byArgs.get('q=A')).toMatchObject({
      startMs: 10_000,
      endMs: 25_000,
      durationMs: 15000,
      resultText: 'A结果',
    })
    expect(byArgs.get('q=B')).toMatchObject({
      startMs: 11_000,
      endMs: 20_000,
      durationMs: 9000,
      resultText: 'B结果',
    })
  })

  it('回放裁剪：游标未到 call 展示完整确定区间；执行中尾随游标增长', () => {
    const spans = projectToolSpans(
      [
        { ...meta(1, t(10)), type: 'tool_call', toolName: 'nav_a', toolArgs: {} },
        { ...meta(2, t(16)), type: 'tool_result', toolName: 'nav_a', result: 'ok', durationMs: 1 },
        { ...meta(3, t(30)), type: 'tool_call', toolName: 'nav_b', toolArgs: {} },
        { ...meta(4, t(36)), type: 'tool_result', toolName: 'nav_b', result: 'ok', durationMs: 1 },
      ],
      T0,
      13_000, // 回放游标：nav_a 执行中，nav_b 未来已确定
    )
    expect(spans).toHaveLength(2)
    // 执行中：右端尾随游标（条随游标推进增长）
    expect(spans[0]).toMatchObject({
      toolName: 'nav_a',
      startMs: 10_000,
      endMs: 13_000,
      pending: true,
    })
    // 未来已确定：展示完整区间（不再按游标过滤隐藏）
    expect(spans[1]).toMatchObject({
      toolName: 'nav_b',
      startMs: 30_000,
      endMs: 36_000,
      pending: false,
    })
  })
})

describe('projectLiveSpans（live 增长条）', () => {
  it('正在说的话 → [开口时刻, now] 区间；缓冲清空后消失', () => {
    let state = stateWith([
      { ...meta(1, '2026-08-26T10:00:02'), type: 'fake_person_delta', target: 'driver', delta: '你好' },
      { ...meta(2, '2026-08-26T10:00:03'), type: 'assistant_delta', delta: '好的' },
    ])
    const spans = projectLiveSpans(state, 4_000)
    expect(spans).toHaveLength(2)
    expect(spans[0]).toMatchObject({ lane: 'fakePerson', startMs: 2_000, endMs: 4_000 })
    expect(spans[1]).toMatchObject({ lane: 'assistant', startMs: 3_000, endMs: 4_000 })

    // 话语落盘 → live 条消失（权威 utterance 区间接管）
    state = consoleReducer(state, {
      type: 'event',
      event: {
        ...meta(3, '2026-08-26T10:00:05'),
        type: 'utterance',
        speakerKind: 'fake_person_speak',
        role: 'fake_person:driver',
        content: '你好',
        startedAt: '2026-08-26T10:00:02',
        endedAt: '2026-08-26T10:00:04',
        isPartial: false,
        interruptedByBargeIn: false,
        speechDuration: 2,
        ttft: undefined,
        isProactive: false,
        segments: [],
      },
    })
    const after = projectLiveSpans(state, 5_000)
    expect(after).toHaveLength(1)
    expect(after[0].lane).toBe('assistant')
  })

  it('nowMs=null（非运行/回放）不产生 live 条', () => {
    const state = stateWith([
      { ...meta(1, '2026-08-26T10:00:02'), type: 'assistant_delta', delta: '好的' },
    ])
    expect(projectLiveSpans(state, null)).toEqual([])
  })
})

describe('projectDialogue', () => {
  it('落盘话语→气泡，打字机缓冲→末尾 live 气泡', () => {
    let state = stateWith([
      utterance(1, 'fake_person:driver', 0, 5),
      { ...meta(2), type: 'assistant_delta', delta: '正在说' },
    ])
    const bubbles = projectDialogue(state)
    expect(bubbles).toHaveLength(2)
    expect(bubbles[0]).toMatchObject({
      speaker: 'fakePerson',
      status: 'complete',
      isLive: false,
      label: '假人·driver',
    })
    expect(bubbles[1]).toMatchObject({
      speaker: 'assistant',
      status: 'speaking',
      isLive: true,
      content: '正在说',
    })
  })

  it('半截话区分打断与截断标记', () => {
    const state = stateWith([
      utterance(1, 'assistant', 0, 5, {
        isPartial: true,
        interruptedByBargeIn: true,
      }),
      utterance(2, 'assistant', 6, 10, {
        isPartial: true,
        interruptedByBargeIn: false,
      }),
    ])
    const bubbles = projectDialogue(state)
    expect(bubbles[0].kind).toBe('bubble')
    expect(bubbles[1].kind).toBe('bubble')
    if (bubbles[0].kind !== 'bubble' || bubbles[1].kind !== 'bubble') {
      throw new Error('期望气泡')
    }
    expect(bubbles[0].status).toBe('interrupted')
    expect(bubbles[1].status).toBe('truncated')
  })

  it('工具调用→卡片，tool_result 就近配对回填；未配对卡片保持执行中', () => {
    const state = stateWith([
      utterance(1, 'fake_person:driver', 0, 5),
      { ...meta(2), type: 'tool_call', toolName: 'set_reminder', toolArgs: { minutes: 35, text: '拿快递' } },
      { ...meta(3), type: 'tool_result', toolName: 'set_reminder', result: '已设置提醒', durationMs: 120 },
      { ...meta(4), type: 'tool_call', toolName: 'virtual_car_control', toolArgs: { command: '开空调' } },
    ])
    const entries = projectDialogue(state)
    expect(entries).toHaveLength(3)
    expect(entries[0].kind === 'tool').toBe(false)
    const card1 = entries[1]
    if (card1.kind !== 'tool') throw new Error('期望工具卡片')
    expect(card1.toolName).toBe('set_reminder')
    expect(card1.argsText).toContain('minutes=35')
    expect(card1.resultText).toBe('已设置提醒')
    expect(card1.durationMs).toBe(120)
    const card2 = entries[2]
    if (card2.kind !== 'tool') throw new Error('期望工具卡片')
    expect(card2.toolName).toBe('virtual_car_control')
    expect(card2.resultText).toBeNull()
  })

  it('同名并行工具卡片按 task_id 精确配对（结果乱序不误配）', () => {
    const t = (sec: number) =>
      new Date(Date.parse(T0) + sec * 1000).toISOString()
    const state = stateWith([
      { ...meta(1, t(10)), type: 'tool_call', toolName: 'poi_search', toolArgs: { q: 'A' }, taskId: 't1' },
      { ...meta(2, t(11)), type: 'tool_call', toolName: 'poi_search', toolArgs: { q: 'B' }, taskId: 't2' },
      { ...meta(3, t(20)), type: 'tool_result', toolName: 'poi_search', result: 'B结果', durationMs: 9000, taskId: 't2' },
      { ...meta(4, t(25)), type: 'tool_result', toolName: 'poi_search', result: 'A结果', durationMs: 15000, taskId: 't1' },
    ])
    const entries = projectDialogue(state)
    expect(entries).toHaveLength(2)
    const cards = entries.map((e) => {
      if (e.kind !== 'tool') throw new Error('期望工具卡片')
      return e
    })
    const byArgs = new Map(cards.map((c) => [c.argsText, c]))
    expect(byArgs.get('q=A')?.resultText).toBe('A结果')
    expect(byArgs.get('q=A')?.durationMs).toBe(15000)
    expect(byArgs.get('q=A')?.timeRangeText).toBe('T+10s → T+25s')
    expect(byArgs.get('q=B')?.resultText).toBe('B结果')
    expect(byArgs.get('q=B')?.durationMs).toBe(9000)
    expect(byArgs.get('q=B')?.timeRangeText).toBe('T+11s → T+20s')
  })

  it('对话流按虚拟时间排序：回灌话语(seq早/mock晚)与工具(seq晚/mock早)交叉也能正确排序', () => {
    const t = (sec: number) => new Date(Date.parse(T0) + sec * 1000).toISOString()
    // seq 顺序与 mock 时间相反：utterance 的 seq 在前、mock 晚；tool 的 seq 在后、mock 早
    const state = stateWith([
      utterance(1, 'assistant', 20, 25),
      { ...meta(2, t(16)), type: 'tool_call', toolName: '地点搜索工具', toolArgs: { q: 'A' }, taskId: 't1' },
      { ...meta(3, t(18)), type: 'tool_result', toolName: '地点搜索工具', result: 'R', durationMs: 2000, taskId: 't1' },
    ])
    const entries = projectDialogue(state)
    expect(entries).toHaveLength(2)
    expect(entries[0].kind).toBe('tool') // mock 16s < 20s
    expect(entries[1].kind).toBe('bubble') // mock 20s
    const card = entries[0]
    if (card.kind !== 'tool') throw new Error('期望工具卡片')
    expect(card.timeRangeText).toBe('T+16s → T+18s')
    const bubble = entries[1]
    if (bubble.kind !== 'bubble') throw new Error('期望气泡')
    expect(bubble.timeRangeText).toBe('T+20s → T+25s')
  })

  it('气泡带相对 T0 的虚拟时间区间（T+开始 → T+结束）', () => {
    const state = stateWith([
      utterance(1, 'fake_person:driver', 0, 5),
      utterance(2, 'assistant', 6.2, 10.8),
    ])
    const entries = projectDialogue(state)
    const bubble1 = entries[0]
    const bubble2 = entries[1]
    if (bubble1.kind !== 'bubble' || bubble2.kind !== 'bubble') {
      throw new Error('期望气泡')
    }
    expect(bubble1.timeRangeText).toBe('T+0s → T+5s')
    expect(bubble2.timeRangeText).toBe('T+6.2s → T+10.8s')
  })

  it('工具卡片带相对 T0 的调用区间；未配对卡片仅显示开始时刻', () => {
    const t = (sec: number) => new Date(Date.parse(T0) + sec * 1000).toISOString()
    const state = stateWith([
      { ...meta(1, t(10)), type: 'tool_call', toolName: 'set_reminder', toolArgs: { minutes: 35 } },
      { ...meta(2, t(13)), type: 'tool_result', toolName: 'set_reminder', result: '已设置', durationMs: 3000 },
      { ...meta(3, t(20)), type: 'tool_call', toolName: 'virtual_car_control', toolArgs: { command: '开空调' } },
    ])
    const entries = projectDialogue(state)
    const card1 = entries[0]
    const card2 = entries[1]
    if (card1.kind !== 'tool' || card2.kind !== 'tool') {
      throw new Error('期望工具卡片')
    }
    expect(card1.timeRangeText).toBe('T+10s → T+13s')
    expect(card2.timeRangeText).toBe('T+20s')
  })

  it('无 t0 时（未运行 case）时间区间为 null', () => {
    const state = initialConsoleState()
    state.utterances.push({
      ...meta(1),
      type: 'utterance',
      speakerKind: 'fake_person_speak',
      role: 'fake_person:driver',
      content: '你好',
      startedAt: '2026-08-26T10:00:00',
      endedAt: '2026-08-26T10:00:02',
      isPartial: false,
      interruptedByBargeIn: false,
      speechDuration: 2,
      ttft: undefined,
      isProactive: false,
      segments: [],
    })
    state.events.push(state.utterances[0])
    const entries = projectDialogue(state)
    const bubble = entries[0]
    if (bubble.kind !== 'bubble') throw new Error('期望气泡')
    expect(bubble.timeRangeText).toBeNull()
  })
})

describe('formatDuration / formatRelative', () => {
  it('分级格式化', () => {
    expect(formatDuration(1500)).toBe('1.5s')
    expect(formatDuration(9500)).toBe('9.5s')
    expect(formatDuration(65000)).toBe('1m5s')
    expect(formatDuration(3600000)).toBe('1h0m')
    expect(formatDuration(5 * 86400000)).toBe('5d0h')
  })

  it('相对 T0 表达', () => {
    expect(formatRelative(0)).toBe('T0 +0s')
    expect(formatRelative(-3000)).toBe('T0 -3s')
  })
})

describe('projectCarState（车态时间机）', () => {
  const t = (sec: number) => new Date(Date.parse(T0) + sec * 1000).toISOString()

  it('cursorMs=null（实时）：初值 + 全部增量合并为最新状态', () => {
    const state = stateWith(
      [
        { ...meta(1, t(5)), type: 'car_set_state', updatedFields: { 空调开启状态及模式: '制冷中' }, source: 'assistant' },
        { ...meta(2, t(8)), type: 'car_set_state', updatedFields: { 车内温度: '24摄氏度', 空调开启状态及模式: '制热中' }, source: 'script' },
      ],
      { 车内温度: '26摄氏度', 车窗状态: '关闭' },
    )
    const view = projectCarState(state.events, state.t0, null)
    const byKey = Object.fromEntries(view.entries.map((e) => [e.key, e.value]))
    expect(byKey).toEqual({
      车内温度: '24摄氏度',
      车窗状态: '关闭',
      空调开启状态及模式: '制热中',
    })
    // 最新变化是 8s 的这次改动（一次改了两个字段：温度 + 空调，都要高亮）
    expect(view.changedKeys).toEqual(['车内温度', '空调开启状态及模式'])
  })

  it('游标裁剪：只合并 mock_time ≤ cursorMs 的增量', () => {
    const state = stateWith(
      [
        { ...meta(1, t(5)), type: 'car_set_state', updatedFields: { 空调开启状态及模式: '制冷中' }, source: 'assistant' },
        { ...meta(2, t(8)), type: 'car_set_state', updatedFields: { 车内温度: '24摄氏度' }, source: 'script' },
      ],
      { 车内温度: '26摄氏度' },
    )
    // 游标 6s：只看到 5s 的空调变更，8s 的温度变更未生效
    const view = projectCarState(state.events, state.t0, 6000)
    expect(view.entries.find((e) => e.key === '空调开启状态及模式')?.value).toBe('制冷中')
    expect(view.entries.find((e) => e.key === '车内温度')?.value).toBe('26摄氏度')
    expect(view.changedKeys).toEqual(['空调开启状态及模式'])
  })

  it('旧事件流无 initialCarInfo：空表起步仍可合并增量', () => {
    const state = stateWith([
      { ...meta(1, t(3)), type: 'car_set_state', updatedFields: { 车窗状态: '开启' }, source: null },
    ])
    const view = projectCarState(state.events, state.t0, null)
    expect(view.entries).toHaveLength(1)
    expect(view.entries[0]).toMatchObject({ key: '车窗状态', value: '开启' })
  })

  it('无分组元数据：单组"全部状态"兜底（组内按插入序）', () => {
    const state = stateWith(
      [
        { ...meta(1, t(5)), type: 'car_set_state', updatedFields: { 空调温度: '24°C' }, source: null },
      ],
      { 车内温度: '26摄氏度', 车窗状态: '关闭' },
    )
    const view = projectCarState(state.events, state.t0, null)
    expect(view.groups).toHaveLength(1)
    expect(view.groups[0].name).toBe('全部状态')
    expect(view.groups[0].entries.map((e) => e.key)).toEqual([
      '车内温度',
      '车窗状态',
      '空调温度',
    ])
  })

  it('分组元数据：按组序收集，未归组字段进"其他"，组头标记 hasChange', () => {
    const state = stateWith(
      [
        { ...meta(1, t(5)), type: 'car_set_state', updatedFields: { 多媒体播放状态: '播放中' }, source: 'assistant' },
      ],
      {
        车内温度: '26摄氏度',
        多媒体播放状态: '停止中',
        正在播放的歌曲名: '无',
        当前位置: '上海平金中心',
      },
      {
        空调: ['车内温度'],
        媒体: ['多媒体播放状态', '正在播放的歌曲名'],
      },
    )
    const view = projectCarState(state.events, state.t0, null)
    expect(view.groups.map((g) => g.name)).toEqual(['空调', '媒体', '其他'])
    expect(view.groups[0].entries.map((e) => e.key)).toEqual(['车内温度'])
    // 组内按元数据 key 序（歌曲名在后），增量变更已合并
    expect(view.groups[1].entries.map((e) => [e.key, e.value])).toEqual([
      ['多媒体播放状态', '播放中'],
      ['正在播放的歌曲名', '无'],
    ])
    // "当前位置"未归组 → 其他
    expect(view.groups[2].entries.map((e) => e.key)).toEqual(['当前位置'])
    // 游标处刚变化的字段在媒体组 → 组头 hasChange
    expect(view.changedKeys).toEqual(['多媒体播放状态'])
    expect(view.groups[1].hasChange).toBe(true)
    expect(view.groups[0].hasChange).toBe(false)
  })

  it('变更来源数据链：entry.source / changedSource / changedAtMs 跟随 car_set_state.source', () => {
    const state = stateWith(
      [
        { ...meta(1, t(5)), type: 'car_set_state', updatedFields: { 空调开启状态及模式: '制冷中' }, source: 'assistant' },
        { ...meta(2, t(8)), type: 'car_set_state', updatedFields: { 车速: '60 km/h' }, source: 'script' },
        { ...meta(3, t(12)), type: 'car_set_state', updatedFields: { 车窗状态: '开启' }, source: null },
      ],
      { 空调开启状态及模式: '关闭' },
    )
    const view = projectCarState(state.events, state.t0, null)
    // 每个字段携带最近一次变更来源
    expect(view.entries.find((e) => e.key === '空调开启状态及模式')?.source).toBe('assistant')
    expect(view.entries.find((e) => e.key === '车速')?.source).toBe('script')
    // 旧事件流（source=null）与初始字段：source = null
    expect(view.entries.find((e) => e.key === '车窗状态')?.source).toBeNull()
    // 最近一次变化：12s 的车窗（来源未知）
    expect(view.changedKeys).toEqual(['车窗状态'])
    expect(view.changedAtMs).toBe(12_000)
    expect(view.changedSource).toBeNull()

    // 回放游标 9s：最近变化 = 8s 的剧本改车速（金色标记驱动数据）
    const replay = projectCarState(state.events, state.t0, 9_000)
    expect(replay.changedKeys).toEqual(['车速'])
    expect(replay.changedSource).toBe('script')
    expect(replay.changedAtMs).toBe(8_000)
  })
})

describe('projectDialogue · 回放裁剪', () => {
  const t = (sec: number) => new Date(Date.parse(T0) + sec * 1000).toISOString()

  it('游标裁剪：未开始不显示 / 说到一半按 segments 拼接 / 已完成全量显示', () => {
    const state = stateWith([
      utterance(1, 'fake_person:driver', 0, 4),
      utterance(2, 'assistant', 5, 10, {
        content: '好的已为您打开空调',
        segments: [
          [t(5), '好的'],
          [t(7), '已为您'],
          [t(9), '打开空调'],
        ],
      }),
      utterance(3, 'fake_person:driver', 12, 16),
    ])

    // 游标 2s：只有第一句（说到一半 → speaking 状态）
    let entries = projectDialogue(state, 2000)
    expect(entries).toHaveLength(1)
    let bubble = entries[0]
    if (bubble.kind !== 'bubble') throw new Error('期望气泡')
    expect(bubble.status).toBe('speaking')

    // 游标 8s：第一句完整 + 第二句说到一半（只有前两个 segment）
    entries = projectDialogue(state, 8000)
    expect(entries).toHaveLength(2)
    bubble = entries[1]
    if (bubble.kind !== 'bubble') throw new Error('期望气泡')
    expect(bubble.status).toBe('speaking')
    expect(bubble.content).toBe('好的已为您')

    // 游标 11s：第二句说完（完整内容）
    entries = projectDialogue(state, 11000)
    expect(entries).toHaveLength(2)
    bubble = entries[1]
    if (bubble.kind !== 'bubble') throw new Error('期望气泡')
    expect(bubble.status).toBe('complete')
    expect(bubble.content).toBe('好的已为您打开空调')

    // 游标 20s（终点后）：全部三句显示
    entries = projectDialogue(state, 20000)
    expect(entries).toHaveLength(3)
  })

  it('回放模式：工具卡片结果未到显示执行中，live 打字机气泡不显示', () => {
    let state = stateWith([
      { ...meta(1, t(10)), type: 'tool_call', toolName: 'set_reminder', toolArgs: { minutes: 35 } },
      { ...meta(2, t(13)), type: 'tool_result', toolName: 'set_reminder', result: '已设置', durationMs: 120 },
    ])
    // 模拟实时打字机缓冲存在
    state = consoleReducer(state, {
      type: 'event',
      event: { ...meta(3), type: 'assistant_delta', delta: '正在说' },
    })

    // 游标 11s：工具已调用但结果未到 → 执行中
    let entries = projectDialogue(state, 11000)
    expect(entries).toHaveLength(1)
    let card = entries[0]
    if (card.kind !== 'tool') throw new Error('期望工具卡片')
    expect(card.resultText).toBeNull()

    // 实时模式（cursorMs=null）：live 气泡显示 + 工具已配对
    entries = projectDialogue(state)
    expect(entries).toHaveLength(2)
    card = entries[0]
    if (card.kind !== 'tool') throw new Error('期望工具卡片')
    expect(card.resultText).toBe('已设置')
    const live = entries[1]
    if (live.kind !== 'bubble') throw new Error('期望气泡')
    expect(live.isLive).toBe(true)

    // 回放模式：live 气泡不显示
    entries = projectDialogue(state, 20000)
    expect(entries).toHaveLength(1)
    card = entries[0]
    if (card.kind !== 'tool') throw new Error('期望工具卡片')
    expect(card.resultText).toBe('已设置')
  })
})
