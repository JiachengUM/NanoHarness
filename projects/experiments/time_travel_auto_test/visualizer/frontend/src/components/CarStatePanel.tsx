/**
 * CarStatePanel：虚拟车状态观察窗（右栏中部）。
 *
 * 显示"游标时刻"的虚拟车全量状态——像视频逐帧观察车的状态：
 * - 实时模式：跟随最新事件（游标 = 终点）
 * - 回放模式：跟随拖拽/倍速回放的游标，观察任意虚拟时刻
 * - 分层分组展示（case_started.car_state_groups 元数据驱动）：
 *   每组一个可折叠区块，组内字段多列网格排布——字段量大时可读
 *
 * 动态高亮（2 秒）：字段被"设置车态"或"状态检查"命中时——
 * - 所在分组临时置顶展示（"哪块被动了"一眼可见）
 * - 设置车态（car_set_state）= 蓝色加粗
 * - 状态检查（state_check）：对齐设置效果，通过 = 绿色加粗 / 未通过 = 红色加粗
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type {
  CarStateEntry,
  CarStateGroupView,
  CarStateHighlight,
  CarStateView,
} from '../app/projections'
import { formatDuration } from '../app/projections'

/** 变更闪烁持续时间（毫秒）。 */
const FLASH_MS = 2000

export interface CarStatePanelProps {
  view: CarStateView
  /** 当前观察时刻文本（如 "T+12.3s"）；null = 未运行。 */
  cursorText: string | null
  /** 回放中（playing）时观察时刻持续跳动。 */
  playing: boolean
}

/** 高亮来源 → 闪烁样式类（设置=蓝 / 检查通过=绿 / 检查失败=红）。 */
function highlightClass(highlight: CarStateHighlight): string {
  if (highlight.kind === 'set') return 'car-flash-set'
  return highlight.passed ? 'car-flash-check-pass' : 'car-flash-check-fail'
}

function formatValue(value: unknown): string {
  if (value === null) return 'null'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

/** 车态颜色图例：说明键值对的持久色与闪烁高亮色。 */
function CarStateLegend() {
  return (
    <div className="car-state-legend" aria-label="车态颜色图例">
      <span className="car-state-legend-item">
        <span className="car-state-legend-swatch legend-white" />
        普通状态（初始值 / 助手工具设置）
      </span>
      <span className="car-state-legend-item">
        <span className="car-state-legend-swatch legend-gold" />
        上帝视角剧本设置
      </span>
      <span className="car-state-legend-item">
        <span className="car-state-legend-swatch legend-blue" />
        刚设置车态（闪烁）
      </span>
      <span className="car-state-legend-item">
        <span className="car-state-legend-swatch legend-green" />
        状态检查通过（闪烁）
      </span>
      <span className="car-state-legend-item">
        <span className="car-state-legend-swatch legend-red" />
        状态检查未通过（闪烁）
      </span>
    </div>
  )
}

function CarStateRow({
  entry,
  flash,
}: {
  entry: CarStateEntry
  /** 当前闪烁中的高亮（keys + 来源）；null = 无闪烁。 */
  flash: CarStateHighlight | null
}) {
  const isFlash = flash !== null && flash.keys.includes(entry.key)
  const cls = isFlash ? highlightClass(flash) : ''
  // 持久色：上帝视角剧本（script）直接改的字段用金色，其余（助手工具/初始/假人）默认普通色
  const sourceCls = entry.source === 'script' ? 'car-source-script' : ''
  return (
    <div
      className={`car-state-row ${isFlash ? `car-state-flash ${cls}` : ''} ${sourceCls}`}
      title={`变化于 T+${formatDuration(Math.max(entry.changedAtMs, 0))}${
        entry.source ? `（来源：${entry.source}）` : ''
      }`}
    >
      <dt>{entry.key}</dt>
      <dd>
        {formatValue(entry.value)}
        {isFlash && <span className="car-state-changed-mark" />}
      </dd>
    </div>
  )
}

function CarStateGroup({
  group,
  flash,
}: {
  group: CarStateGroupView
  flash: CarStateHighlight | null
}) {
  const flashInGroup =
    flash !== null && group.entries.some((e) => flash.keys.includes(e.key))
  return (
    <details className="car-state-group" open>
      <summary className="car-state-group-header">
        <span className="car-state-group-name">{group.name}</span>
        <span className="car-state-group-count">{group.entries.length}项</span>
        {flashInGroup && flash !== null && (
          <span className={`car-state-changed-mark ${highlightClass(flash)}`} />
        )}
      </summary>
      <dl>
        {group.entries.map((entry) => (
          <CarStateRow key={entry.key} entry={entry} flash={flash} />
        ))}
      </dl>
    </details>
  )
}

export function CarStatePanel({ view, cursorText, playing }: CarStatePanelProps) {
  // 动态高亮：游标扫过"设置车态 / 状态检查"时刻 → 闪烁被命中字段 + 分组置顶，2 秒后恢复。
  // 实时模式由事件到达驱动；回放模式由游标扫过事件时刻驱动（来回拖也能看到）。
  const [flash, setFlash] = useState<CarStateHighlight | null>(null)
  const lastHighlightId = useRef('')

  // 稳定身份串：游标处最近一次高亮的内容（来源 + 通过态 + 字段集）。
  // keys 数组每次重建，串成字符串作依赖，避免每帧都触发 effect。
  const highlightId = view.highlight
    ? `${view.highlight.kind}|${view.highlight.passed}|${view.highlight.keys.join(',')}`
    : ''

  useEffect(() => {
    if (highlightId === lastHighlightId.current) return
    lastHighlightId.current = highlightId
    if (highlightId === '') {
      // 游标退回「首个事件之前」：清除残留高亮
      setFlash(null)
      return
    }
    setFlash(view.highlight)
  }, [highlightId, view.highlight])

  useEffect(() => {
    if (flash === null) return
    const timer = setTimeout(() => setFlash(null), FLASH_MS)
    return () => clearTimeout(timer)
  }, [flash])

  // 闪烁期间：被命中字段所在分组临时置顶
  const orderedGroups = useMemo(() => {
    if (flash === null) return view.groups
    const index = view.groups.findIndex((group) =>
      group.entries.some((e) => flash.keys.includes(e.key)),
    )
    if (index <= 0) return view.groups
    const ordered = [...view.groups]
    const [hit] = ordered.splice(index, 1)
    return [hit, ...ordered]
  }, [view.groups, flash])

  return (
    <section className="car-state-panel" aria-label="虚拟车状态">
      <header className="panel-header">
        <h2>虚拟车状态</h2>
        <span className={`panel-subtitle ${playing ? 'car-state-live' : ''}`}>
          {cursorText !== null
            ? `${playing ? '▸ ' : ''}观察时刻 ${cursorText}`
            : '运行后呈现'}
        </span>
      </header>
      <CarStateLegend />
      {view.entries.length === 0 ? (
        <p className="empty-hint">跟随虚拟时间线游标，展示任意时刻的车机状态。</p>
      ) : (
        <div className="car-state-list">
          {orderedGroups.map((group) => (
            <CarStateGroup key={group.name} group={group} flash={flash} />
          ))}
        </div>
      )}
    </section>
  )
}