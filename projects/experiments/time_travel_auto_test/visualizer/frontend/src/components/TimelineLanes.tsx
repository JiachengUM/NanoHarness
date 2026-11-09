/**
 * TimelineLanes：虚拟时间线泳道图（右栏）——本可视化的特色面板。
 *
 * 实时模式（自动测试运行中）——流动的 ~20s 时间窗口：
 * - 当前虚拟时刻轴线恒固定画面中央；窗口 [过去半窗, 未来半窗] 随虚拟时间
 *   从右向左流动（秒级网格线随之流动，营造节拍感）
 * - 轴右侧是未来：剧本预设事件竖线从右缘飞入，抵达轴线即消失（由真实事件接管）
 * - 轴左侧是历史：事件块在轴线处生成并随时间左移——进行中的块右端贴轴线
 *   增长（长度与持续时间动态对齐），结束后定长继续左移，滑出左缘消失
 *
 * 回放模式（case 结束后，像视频播放器）：
 * - 泳道宽度 = 整个 case 的虚拟时间全程（快进段压缩为窄带），游标默认最左
 * - 拖拽时间线任意位置定位游标（对话流/虚拟车状态窗跟随回放）
 * - 横向缩放（×1~×64，锚定游标）+ 底部平移滑块：放大后滑动查看细节窗口
 * - 播放中视窗自动跟随游标
 *
 * 泳道：假人 / 助手（+工具子泳道组）/ 车（状态检查·车控）/ 系统（快进·停顿）。
 *
 * 【文字标注泳道设计】：
 * 每个泳道的轨道下方有一条"文字标注泳道"：事件块只呈现色块，文字说明放在
 * 下方标签里，通过一条从事件块底部连到标签的斜线关联。标签在同一行内按时间
 * 排布、重叠时左右错开，尽量不换行；仅当塞不下时才在文字泳道里折行（多行）。
 * 文字可换行、不省略号缩略。
 */
import { useEffect, useRef, useState } from 'react'
import type {
  LaneSpan,
  LiveSpanView,
  OverlapWindow,
  ReplayView,
  TimeScale,
  ToolSpanView,
} from '../app/projections'
import {
  clipSpanToView,
  formatRelative,
  formatDuration,
  REPLAY_ZOOM_MAX,
} from '../app/projections'

/** 回放倍速档位（对齐视频播放器习惯）。 */
export const PLAYBACK_SPEEDS = [1, 1.25, 1.5, 2, 3, 5]

/** 泳道标签列宽（px：label 52 + gap 6）——轨道左偏移量。 */
const LANE_LABEL_PX = 58
/** 轨道（事件块/点所在）高度（px）。 */
const TRACK_H = 24
/** 事件色块（区间）高度。 */
const BAR_H = 12
/** 点事件圆点直径。 */
const DOT_SIZE = 9
/** 文字标签行高（px，11px 字号）。 */
const LABEL_LINE_H = 16
/** 标签左右内边距（px）。 */
const LABEL_PAD_X = 6
/** 同行标签间最小水平间隙（px）。 */
const LABEL_GAP = 4
/** 标签最大换行宽度（px；超长文字在此宽度内折行）。 */
const LABEL_WRAP_MAX = 360

/** tone → 文字/连线颜色（与 styles.css 的 tone-* 背景保持一致的心智映射）。 */
const TONE_COLOR: Record<LaneSpan['tone'], string> = {
  info: '#9aa7bd',
  partial: '#fbbf24',
  proactive: '#a78bfa',
  accel: '#a78bfa',
  tool: '#fb923c',
  ok: '#34d399',
  fail: '#f87171',
  warn: '#f59e0b',
  future: '#fbbf24',
}

export interface PlaybackControl {
  /** 回放可用（run 完成后）。 */
  active: boolean
  mode: 'idle' | 'paused' | 'playing'
  cursorMs: number
  speed: number
}

export interface TimelineLanesProps {
  scale: TimeScale
  spans: LaneSpan[]
  overlaps: OverlapWindow[]
  /** 工具子泳道条（projectToolSpans：配对后的视图）。 */
  toolSpans: ToolSpanView[]
  /** live 增长条（实时正在说的话；回放模式传 []）。 */
  liveSpans: LiveSpanView[]
  playback: PlaybackControl
  /** 回放视窗（zoom/pan；实时模式忽略）。 */
  view: ReplayView
  onScrub: (cursorMs: number) => void
  onPlayPause: () => void
  onSpeed: (speed: number) => void
  onZoom: (zoom: number) => void
  onPan: (panX: number) => void
  /** 泳道轨道像素宽上报（实时窗口自适应 + 网格线密度）。 */
  onViewportWidth: (widthPx: number) => void
}

/** 某个事件 → 文字标注泳道里的一个条目（LaneSpan / ToolSpanView 统一形态）。 */
interface LabelItem {
  id: string
  startMs: number
  endMs: number
  text: string
  tone: LaneSpan['tone']
  title: string
  /** live 模式下快进直接过滤；pending 工具加虚线呼吸。 */
  extraClass?: string
}

/** 标签布局结果：一个已摆好位置的标签。 */
interface PlacedLabel {
  item: LabelItem
  /** 标签左缘（相对轨道，px）。 */
  leftPx: number
  /** 标签宽（px）。 */
  widthPx: number
  /** 标签文字估算行数（1 = 单行）。 */
  lines: number
  /** 标签顶（相对文字泳道顶部，px）。 */
  topPx: number
  /** 事件在轨道内的锚点 x（连线起点，px）。 */
  anchorPx: number
  /** 标签水平中心（连线终点 x，px）。 */
  centerPx: number
}

function toolTooltip(span: ToolSpanView): string {
  const lines = [`工具 ${span.toolName}`]
  if (span.argsText) lines.push(`入参：${span.argsText}`)
  if (span.resultText !== null) lines.push(`返回：${span.resultText}`)
  else lines.push('返回：（执行中）')
  if (span.durationMs !== null) {
    lines.push(`耗时：${formatDuration(span.durationMs)}`)
  }
  lines.push(
    `${formatRelative(span.startMs)}${span.pending ? ' → …' : ` → ${formatRelative(span.endMs)}`}`,
  )
  return lines.join('\n')
}

/** 结果内容摘要（条上"获得内容"展示用；压缩空白并截断防撑爆窄条布局）。 */
function summarizeResult(text: string): string {
  const t = text.replace(/\s+/g, ' ').trim()
  return t.length > 36 ? `${t.slice(0, 36)}…` : t
}

/** 事件文字标签：话语只显示说话人（内容在对话流/tooltip），其余显示 标签·详情。 */
function spanLabelText(span: LaneSpan): string {
  if (span.kind === 'utterance') return span.label
  return span.detail ? `${span.label} · ${span.detail}` : span.label
}

/** 工具文字标签：名称 + 执行中/耗时 + 结果摘要。 */
function toolLabelText(span: ToolSpanView): string {
  const elapsed = Math.max(0, span.endMs - span.startMs)
  const dur = formatDuration(span.durationMs ?? elapsed)
  const status = span.pending ? `执行中 ${dur}` : `✓ ${dur}`
  const result = span.resultText ? ` · ${summarizeResult(span.resultText)}` : ''
  return `⚙ ${span.toolName} ${status}${result}`
}

/** 单字符估算显示像素宽（CJK/全角 11px，其余 6.5px）。 */
function charWidth(ch: string): number {
  const code = ch.codePointAt(0) ?? 0
  if (code > 0x2e80 || (code >= 0x3000 && code <= 0x303f) || (code >= 0xff00 && code <= 0xffef)) {
    return 11
  }
  return 6.5
}

/** 估算文字单行像素宽（不含边框内边距）。 */
function measureTextPx(text: string): number {
  let w = 0
  for (const ch of text) w += charWidth(ch)
  return w
}

/** 事件在轨道内的锚点 x（连线起点）：区间取可见中点，点事件取点位。 */
function anchorPxFor(
  scale: TimeScale,
  startMs: number,
  endMs: number,
  trackPx: number,
): number | null {
  const pos = clipSpanToView(scale, startMs, endMs)
  if (!pos) return null
  const cx = endMs > startMs ? (pos.x1 + pos.x2) / 2 : pos.x1
  return cx * trackPx
}

/**
 * 标签布局：按时间升序把每个事件文字标签放到文字泳道里。
 * - 默认放在事件锚点正下方（左缘对齐锚点减半宽），clamp 到 [0, trackPx]。
 * - 与已放标签重叠时向右错开；错开仍超界则下移一行（文字泳道折行）。
 * - 超长文字在 LABEL_WRAP_MAX 宽度内折行（lines 增加，行高随之撑高）。
 */
function placeLabels(
  items: LabelItem[],
  scale: TimeScale,
  trackPx: number,
): { placed: PlacedLabel[]; totalHeight: number } {
  const placed: PlacedLabel[] = []
  if (trackPx <= 0) return { placed, totalHeight: 0 }
  const maxWrap = Math.min(trackPx, LABEL_WRAP_MAX)
  const sorted = [...items].sort((a, b) => a.startMs - b.startMs)
  const rows: { right: number; height: number }[] = []

  for (const item of sorted) {
    const anchor = anchorPxFor(scale, item.startMs, item.endMs, trackPx)
    if (anchor === null) continue
    const textPx = measureTextPx(item.text) + LABEL_PAD_X * 2
    let widthPx: number
    let lines: number
    if (textPx <= maxWrap) {
      widthPx = textPx
      lines = 1
    } else {
      widthPx = maxWrap
      lines = Math.ceil(textPx / maxWrap)
    }
    const labelH = lines * LABEL_LINE_H
    const clampLeft = (v: number) => Math.max(0, Math.min(trackPx - widthPx, v))
    let left = clampLeft(anchor - widthPx / 2)

    let rowIndex = rows.length
    for (let r = 0; r < rows.length; r++) {
      const row = rows[r]
      if (left >= row.right + LABEL_GAP) {
        rowIndex = r
        break
      }
      const shifted = row.right + LABEL_GAP
      if (shifted + widthPx <= trackPx) {
        left = shifted
        rowIndex = r
        break
      }
    }
    if (rowIndex === rows.length) {
      rows.push({ right: left + widthPx, height: labelH })
    } else {
      rows[rowIndex].right = left + widthPx
      if (labelH > rows[rowIndex].height) rows[rowIndex].height = labelH
    }

    let rowTop = 0
    for (let r = 0; r < rowIndex; r++) rowTop += rows[r].height
    const topPx = rowTop + (rows[rowIndex].height - labelH) / 2
    placed.push({
      item,
      leftPx: left,
      widthPx,
      lines,
      topPx,
      anchorPx: anchor,
      centerPx: left + widthPx / 2,
    })
  }
  const totalHeight = rows.reduce((s, r) => s + r.height, 0)
  return { placed, totalHeight }
}

export function TimelineLanes({
  scale,
  spans,
  overlaps,
  toolSpans,
  liveSpans,
  playback,
  view,
  onScrub,
  onPlayPause,
  onSpeed,
  onZoom,
  onPan,
  onViewportWidth,
}: TimelineLanesProps) {
  const scrubRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLDivElement>(null)
  const [trackPx, setTrackPx] = useState(0)

  // 轨道宽上报（ResizeObserver）：轨道 = 画布宽 − 左侧标签列（右侧无说明道）。
  useEffect(() => {
    if (scale.empty) return
    const el = canvasRef.current
    if (!el) return
    const report = () => {
      const track = el.getBoundingClientRect().width - LANE_LABEL_PX
      onViewportWidth(Math.max(0, track))
      setTrackPx(Math.max(0, track))
    }
    report()
    const observer = new ResizeObserver(report)
    observer.observe(el)
    return () => observer.disconnect()
  }, [onViewportWidth, scale.empty])

  /** 拖拽层内 x 坐标 → 相对毫秒（非线性段内反算）。 */
  const toCursorMs = (clientX: number): number => {
    const el = scrubRef.current
    if (!el) return 0
    const rect = el.getBoundingClientRect()
    const ratio = rect.width > 0 ? (clientX - rect.left) / rect.width : 0
    const clamped = Math.min(1, Math.max(0, ratio))
    return scale.inverseX(clamped)
  }

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!playback.active) return
    e.currentTarget.setPointerCapture(e.pointerId)
    onScrub(toCursorMs(e.clientX))
  }

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!playback.active || e.buttons !== 1) return
    onScrub(toCursorMs(e.clientX))
  }

  if (scale.empty) {
    return (
      <section className="timeline-lanes" aria-label="虚拟时间线">
        <header className="panel-header">
          <h2>虚拟时间线</h2>
          <span className="panel-subtitle">运行后呈现</span>
        </header>
        <div className="timeline-empty">
          <p className="empty-hint">时间线基于虚拟时间（mock_time），快进段会压缩为窄带。</p>
        </div>
      </section>
    )
  }

  /** 未来预设事件 icon（按所属泳道推断）。 */
  const futureIcon = (lane: LaneSpan['lane']): string =>
    lane === 'fakePerson'
      ? '👤'
      : lane === 'assistant'
        ? '💬'
        : lane === 'car'
          ? '🚗'
          : '⏱'

  /** 未来预设事件：live 只显示未来区（轴线右侧 → 右缘），渲染为"竖线 + 标签胶囊"。 */
  const renderFutureMarker = (span: LaneSpan) => {
    const x1 = scale.x(span.startMs)
    const inWindow =
      scale.mode === 'live' ? x1 >= 0.5 && x1 <= 1 : x1 >= 0 && x1 <= 1
    if (!inWindow) return null
    const opacity =
      scale.mode === 'live'
        ? Math.min(1, Math.max(0, (x1 - 0.5) / 0.12))
        : 1
    return (
      <div
        key={span.id}
        className="future-marker"
        style={{ left: `${x1 * 100}%`, opacity }}
        title={`${span.label}｜${formatRelative(span.startMs)}｜预设事件`}
      >
        <span className="future-marker-line" />
        <span className="future-marker-chip">
          <span className="future-marker-icon">{futureIcon(span.lane)}</span>
          <span className="future-marker-text">{span.label}</span>
        </span>
      </div>
    )
  }

  /** 事件色块（区间 / 点）：只呈现色块，文字在下方标注泳道。 */
  const renderTrackPiece = (piece: {
    id: string
    startMs: number
    endMs: number
    tone: LaneSpan['tone']
    title: string
    extraClass?: string
  }) => {
    if (scale.mode === 'live' && piece.extraClass === 'accel-filtered') return null
    const pos = clipSpanToView(scale, piece.startMs, piece.endMs)
    if (!pos) return null
    const isPoint = piece.endMs <= piece.startMs
    const dimmed = playback.active && piece.startMs > playback.cursorMs
    const aged =
      scale.mode === 'live' && pos.x2 <= 0.5
        ? Math.max(0.3, 1 - ((0.5 - pos.x2) / 0.5) * 0.7)
        : 1
    const centerY = TRACK_H / 2
    if (isPoint) {
      return (
        <div
          key={piece.id}
          className={`lane-dot tone-${piece.tone} ${dimmed ? 'span-dim' : ''}`}
          style={{
            left: `${pos.x1 * 100}%`,
            top: centerY - DOT_SIZE / 2,
            width: DOT_SIZE,
            height: DOT_SIZE,
            ...(scale.mode === 'live' ? { opacity: aged } : {}),
          }}
          title={piece.title}
        />
      )
    }
    return (
      <div
        key={piece.id}
        className={`lane-block tone-${piece.tone} ${piece.extraClass ?? ''} ${dimmed ? 'span-dim' : ''}`}
        style={{
          left: `${pos.x1 * 100}%`,
          width: `${(pos.x2 - pos.x1) * 100}%`,
          top: centerY - BAR_H / 2,
          height: BAR_H,
          ...(scale.mode === 'live' ? { opacity: aged } : {}),
        }}
        title={piece.title}
      />
    )
  }

  /** live 增长条（实时正在说的话）。 */
  const renderLiveSpan = (span: LiveSpanView) => {
    const pos = clipSpanToView(scale, span.startMs, span.endMs)
    if (!pos) return null
    return (
      <div
        key={span.id}
        className="lane-block tone-info lane-live-watch"
        style={{
          left: `${pos.x1 * 100}%`,
          width: `${(pos.x2 - pos.x1) * 100}%`,
          top: (TRACK_H - BAR_H) / 2,
          height: BAR_H,
        }}
        title={`正在说…｜${formatRelative(span.startMs)} → ${formatRelative(span.endMs)}`}
      />
    )
  }

  /** 文字标签 + leader 连线（stage 内的标注层）。 */
  const renderAnnotation = (placed: PlacedLabel[], annotationH: number) => {
    if (annotationH <= 0) return null
    return (
      <>
        <div className="lane-annotation" style={{ height: annotationH }}>
          {placed.map((p) => (
            <div
              key={p.item.id}
              className={`lane-label-pill ${playback.active && p.item.startMs > playback.cursorMs ? 'span-dim' : ''}`}
              style={{
                left: p.leftPx,
                width: p.widthPx,
                top: p.topPx,
                height: p.lines * LABEL_LINE_H,
                color: TONE_COLOR[p.item.tone],
                borderColor: `${TONE_COLOR[p.item.tone]}99`,
                whiteSpace: p.lines > 1 ? 'normal' : 'nowrap',
              }}
              title={p.item.title}
            >
              {p.item.text}
            </div>
          ))}
        </div>
        <svg className="lane-leader-svg" width="100%" height="100%">
          {placed.map((p) => (
            <line
              key={p.item.id}
              x1={p.anchorPx}
              y1={TRACK_H - 2}
              x2={p.centerPx}
              y2={TRACK_H + p.topPx + (p.lines * LABEL_LINE_H) / 2}
              stroke={TONE_COLOR[p.item.tone]}
              strokeOpacity={0.5}
              strokeWidth={1}
            />
          ))}
        </svg>
      </>
    )
  }

  /** 通用泳道渲染：轨道色块 + 下方文字标注 + 连线。 */
  const renderLane = (laneId: LaneSpan['lane'], label: string) => {
    const laneSpans = spans.filter((span) => span.lane === laneId)
    const futureSpans = laneSpans.filter((span) => span.kind === 'future')
    const items: LabelItem[] = laneSpans
      .filter((span) => span.kind !== 'future')
      .map((span) => ({
        id: span.id,
        startMs: span.startMs,
        endMs: span.endMs,
        text: spanLabelText(span),
        tone: span.tone,
        title: `${span.label}｜${formatRelative(span.startMs)}${
          span.detail ? `｜${span.detail}` : ''
        }`,
        extraClass:
          span.kind === 'acceleration' && scale.mode === 'live'
            ? 'accel-filtered'
            : undefined,
      }))
    const { placed, totalHeight } = placeLabels(items, scale, trackPx)
    return (
      <div className="timeline-lane">
        <span className="lane-label">{label}</span>
        <div className="lane-stage">
          <div className="lane-track">
            {items.map((item) =>
              renderTrackPiece({
                id: item.id,
                startMs: item.startMs,
                endMs: item.endMs,
                tone: item.tone,
                title: item.title,
                extraClass: item.extraClass,
              }),
            )}
            {futureSpans.map(renderFutureMarker)}
            {liveSpans
              .filter((span) => span.lane === laneId)
              .map(renderLiveSpan)}
          </div>
          {renderAnnotation(placed, totalHeight)}
        </div>
      </div>
    )
  }

  /** 工具子泳道组：一条工具泳道（低一层级），所有工具块共享一条轨道 + 一条标注。 */
  const renderToolGroup = () => {
    if (toolSpans.length === 0) return null
    const items: LabelItem[] = toolSpans.map((span) => ({
      id: span.id,
      startMs: span.startMs,
      endMs: span.endMs,
      text: toolLabelText(span),
      tone: 'tool',
      title: toolTooltip(span),
      extraClass: span.pending ? 'span-live' : undefined,
    }))
    const { placed, totalHeight } = placeLabels(items, scale, trackPx)
    return (
      <div className="tool-lane-group">
        <div className="timeline-lane timeline-lane--tool">
          <span className="lane-label tool-label">↳ 工具</span>
          <div className="lane-stage">
            <div className="lane-track tool-track">
              {items.map((item) =>
                renderTrackPiece({
                  id: item.id,
                  startMs: item.startMs,
                  endMs: item.endMs,
                  tone: 'tool',
                  title: item.title,
                  extraClass: item.extraClass,
                }),
              )}
            </div>
            {renderAnnotation(placed, totalHeight)}
          </div>
        </div>
      </div>
    )
  }

  // 回放游标屏幕位置（窗外时钳到边缘并降低透明度提示）
  const cursorX = playback.active ? scale.x(playback.cursorMs) : 0
  const cursorOffscreen =
    playback.active && (cursorX < 0 || cursorX > 1)
  const cursorLeft = Math.min(1, Math.max(0, cursorX))

  // live 快进提示：最近一次快进的"到达时刻"距此刻很近（<3s）时顶部浮现徽标
  const recentAccel = (() => {
    if (scale.mode !== 'live') return null
    let best: { fromMs: number; toMs: number } | null = null
    for (const accel of scale.accels) {
      const since = scale.axisMs - accel.toMs
      if (since >= 0 && since < 3000 && (best === null || accel.toMs > best.toMs)) {
        best = accel
      }
    }
    return best
  })()

  // 平移滑块（zoom=1 时无可平移范围，禁用）
  const panRange = view.zoom > 1 ? 1 - 1 / view.zoom : 0
  const panValue = panRange > 0 ? Math.min(1, Math.max(0, view.panX / panRange)) : 0

  return (
    <section className="timeline-lanes" aria-label="虚拟时间线">
      <header className="panel-header">
        <h2>虚拟时间线</h2>
        <span className="panel-subtitle">
          {scale.mode === 'live'
            ? `实时窗口 ±${formatDuration((scale.viewEndMs - scale.viewStartMs) / 2)}`
            : overlaps.length > 0
              ? `回放 · 重叠说话 ×${overlaps.length}`
              : '回放模式'}
        </span>
      </header>

      <div
        ref={canvasRef}
        className={`timeline-canvas ${scale.mode === 'live' ? 'timeline-live' : 'timeline-replay'}`}
      >
        {/* 背景层（网格线 + 快进带 + 重叠带）：与泳道轨道同坐标起点（避开标签列）。 */}
        <div className="track-overlay">
          {scale.mode === 'live' &&
            scale.gridlines.map((gridline) => (
              <div
                key={gridline.atMs}
                className={`timeline-gridline ${gridline.origin ? 'gridline-origin' : ''}`}
                style={{ left: `${scale.x(gridline.atMs) * 100}%` }}
              />
            ))}

          {scale.mode === 'replay' &&
            scale.accels.map((accel, index) => {
              const pos = clipSpanToView(scale, accel.fromMs, accel.toMs)
              if (!pos) return null
              return (
                <div
                  key={`accel-band-${index}`}
                  className="accel-band"
                  style={{
                    left: `${pos.x1 * 100}%`,
                    width: `${(pos.x2 - pos.x1) * 100}%`,
                  }}
                  title="时间快进段（压缩呈现）"
                />
              )
            })}

          {overlaps.map((overlap, index) => {
            const pos = clipSpanToView(scale, overlap.startMs, overlap.endMs)
            if (!pos) return null
            return (
              <div
                key={`overlap-${index}`}
                className="overlap-band"
                style={{
                  left: `${pos.x1 * 100}%`,
                  width: `${(pos.x2 - pos.x1) * 100}%`,
                }}
                title="双方同时说话"
              />
            )
          })}
        </div>

        {scale.mode === 'live' && (
          <div className="timeline-now-axis">
            <span className="timeline-now-label">
              现在 T+{formatDuration(scale.axisMs)}
            </span>
          </div>
        )}

        {recentAccel && (
          <div
            key={`accel-flash-${recentAccel.toMs}`}
            className="accel-flash"
            title={`时间快进至 ${formatRelative(recentAccel.toMs)}`}
          >
            ⏩ 快进 {formatDuration(recentAccel.toMs - recentAccel.fromMs)}
          </div>
        )}

        {/* 泳道：假人 / 助手（+工具子泳道组） / 车 / 系统 */}
        {renderLane('fakePerson', '假人')}
        <div className="assistant-group">
          {renderLane('assistant', '助手')}
          {renderToolGroup()}
        </div>
        {renderLane('car', '虚拟车')}
        {renderLane('system', '系统')}

        {/* 回放拖拽层（覆盖轨道区域；pointer capture 拖拽定位游标） */}
        {playback.active && (
          <div
            ref={scrubRef}
            className={`timeline-scrub-layer ${playback.mode === 'playing' ? 'scrub-playing' : ''}`}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
          >
            <div
              className={`playback-cursor ${cursorOffscreen ? 'cursor-offscreen' : ''}`}
              style={{ left: `${cursorLeft * 100}%` }}
            >
              <span className="playback-cursor-handle" title="拖拽定位虚拟时刻" />
            </div>
          </div>
        )}

        {/* 时间刻度行：live = 流动网格线标签；replay = 分段边界 */}
        <div className="timeline-axis">
          {scale.mode === 'live' && (
            <>
              <span className="timeline-zone-tag timeline-zone-tag-past">← 已发生</span>
              <span className="timeline-zone-tag timeline-zone-tag-future">即将发生 →</span>
            </>
          )}
          {scale.mode === 'live'
            ? scale.gridlines.map((gridline) => (
                <span
                  key={gridline.atMs}
                  className={`axis-tick ${gridline.origin ? 'tick-origin' : ''}`}
                  style={{ left: `${scale.x(gridline.atMs) * 100}%` }}
                >
                  {gridline.label}
                </span>
              ))
            : scale.segments.map((segment, index) => (
                <span
                  key={`tick-${index}`}
                  className={`axis-tick ${segment.kind === 'acceleration' ? 'tick-accel' : ''}`}
                  style={{ left: `${segment.xStart * 100}%` }}
                >
                  {formatRelative(segment.startMs)}
                </span>
              ))}
          {scale.mode === 'replay' && (
            <span className="axis-tick" style={{ left: '100%' }}>
              {formatRelative(scale.endMs)}
            </span>
          )}
        </div>
      </div>

      {/* 回放控制条（视频播放器样式 + 缩放/平移） */}
      {playback.active ? (
        <div className="playback-controls">
          <button
            type="button"
            className="playback-button"
            onClick={onPlayPause}
            title={playback.mode === 'playing' ? '暂停回放' : '播放回放'}
          >
            {playback.mode === 'playing' ? '⏸' : '▶'}
          </button>
          <span className="playback-time">
            {formatDuration(playback.cursorMs)} / {formatDuration(scale.endMs)}
          </span>
          <div className="zoom-controls" role="group" aria-label="时间轴横向缩放">
            <button
              type="button"
              className="zoom-button"
              onClick={() => onZoom(view.zoom / 2)}
              disabled={view.zoom <= 1}
              title="缩小（时间窗口拉远）"
            >
              −
            </button>
            <span className="zoom-label">{view.zoom}×</span>
            <button
              type="button"
              className="zoom-button"
              onClick={() => onZoom(view.zoom * 2)}
              disabled={view.zoom >= REPLAY_ZOOM_MAX}
              title="放大（时间窗口拉近）"
            >
              ＋
            </button>
          </div>
          <input
            type="range"
            className="pan-slider"
            min={0}
            max={1}
            step={0.001}
            value={panValue}
            disabled={view.zoom <= 1}
            onChange={(event) => onPan(Number(event.target.value) * panRange)}
            aria-label="平移时间窗口"
            title={view.zoom <= 1 ? '放大后可左右滑动查看' : '左右滑动查看时间窗口'}
          />
          <div className="playback-speeds" role="group" aria-label="回放倍速">
            {PLAYBACK_SPEEDS.map((speed) => (
              <button
                key={speed}
                type="button"
                className={`speed-option ${speed === playback.speed ? 'speed-active' : ''}`}
                onClick={() => onSpeed(speed)}
              >
                {speed}x
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="playback-controls playback-disabled">
          <span className="playback-hint">运行完成后时间线切换为回放模式（可拖拽 / 缩放 / 平移）</span>
        </div>
      )}

      {/* 图例 */}
      <footer className="timeline-legend">
        <span className="legend-item"><i className="legend-swatch tone-info" />话语</span>
        <span className="legend-item"><i className="legend-swatch tone-tool" />工具调用</span>
        <span className="legend-item"><i className="legend-swatch tone-partial" />半截话</span>
        <span className="legend-item"><i className="legend-swatch tone-proactive" />主动话语</span>
        <span className="legend-item"><i className="legend-swatch tone-accel" />快进</span>
        <span className="legend-item"><i className="legend-swatch tone-ok" />检查通过</span>
        <span className="legend-item"><i className="legend-swatch tone-warn" />流式停顿</span>
        <span className="legend-item"><i className="legend-swatch tone-fail" />检查失败</span>
        <span className="legend-item"><i className="legend-swatch legend-overlap" />重叠说话</span>
        <span className="legend-item"><i className="legend-swatch legend-future" />预设事件</span>
      </footer>
    </section>
  )
}