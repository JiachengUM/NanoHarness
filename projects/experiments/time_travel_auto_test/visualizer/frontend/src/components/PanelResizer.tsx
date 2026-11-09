/**
 * PanelResizer：面板间拖拽条（用户自行调整面板尺寸）。
 *
 * orientation="horizontal"：水平拖拽条（上下两栏，纵向增量 px 调高度）
 * orientation="vertical"：垂直拖拽条（左右两栏，横向增量 px 调宽度）
 *
 * pointer capture 拖拽；尺寸值由 App 持久化到 localStorage（不同屏幕各自适配）。
 */
import { useRef } from 'react'

export interface PanelResizerProps {
  /** 增量（px）→ 上方/左侧面板尺寸调整（horizontal=纵向增量，vertical=横向增量）。 */
  onResize: (deltaPx: number) => void
  /** 无障碍标签（如"调整时间线面板高度"）。 */
  label: string
  /** 拖拽条方向：horizontal=调高度，vertical=调宽度。 */
  orientation?: 'horizontal' | 'vertical'
}

export function PanelResizer({
  onResize,
  label,
  orientation = 'horizontal',
}: PanelResizerProps) {
  const lastPos = useRef<number | null>(null)
  // vertical：拖横向增量（clientX）；horizontal：拖纵向增量（clientY）
  const axis = orientation === 'vertical' ? 'clientX' : 'clientY'

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    lastPos.current = e[axis]
  }

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (lastPos.current === null || e.buttons !== 1) return
    const delta = e[axis] - lastPos.current
    lastPos.current = e[axis]
    if (delta !== 0) onResize(delta)
  }

  const endDrag = () => {
    lastPos.current = null
  }

  return (
    <div
      className={`panel-resizer panel-resizer-${orientation}`}
      role="separator"
      aria-orientation={orientation}
      aria-label={label}
      title={orientation === 'vertical' ? '拖拽调整面板宽度' : '拖拽调整面板高度'}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
    />
  )
}
