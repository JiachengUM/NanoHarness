import { useCallback, useEffect, useRef, useState } from 'react'

const RATIO_STORAGE_KEY = 'voice-test-config-panel-ratio'
const COLLAPSED_STORAGE_KEY = 'voice-test-config-panel-collapsed'
const DEFAULT_RATIO = 0.5
const MIN_RATIO = 0.28
const MAX_RATIO = 0.72

function loadStoredRatio(): number {
  const stored = localStorage.getItem(RATIO_STORAGE_KEY)
  if (!stored) {
    return DEFAULT_RATIO
  }
  const parsed = Number.parseFloat(stored)
  if (Number.isNaN(parsed)) {
    return DEFAULT_RATIO
  }
  return Math.min(MAX_RATIO, Math.max(MIN_RATIO, parsed))
}

function loadStoredCollapsed(): boolean {
  return localStorage.getItem(COLLAPSED_STORAGE_KEY) === 'true'
}

function clampRatio(value: number): number {
  return Math.min(MAX_RATIO, Math.max(MIN_RATIO, value))
}

export function useResizableSplit() {
  const containerRef = useRef<HTMLDivElement>(null)
  const draggingRef = useRef(false)
  const [ratio, setRatio] = useState(loadStoredRatio)
  const [collapsed, setCollapsed] = useState(loadStoredCollapsed)
  const [dragging, setDragging] = useState(false)

  useEffect(() => {
    localStorage.setItem(RATIO_STORAGE_KEY, String(ratio))
  }, [ratio])

  useEffect(() => {
    localStorage.setItem(COLLAPSED_STORAGE_KEY, String(collapsed))
  }, [collapsed])

  useEffect(() => {
    const onPointerMove = (event: PointerEvent) => {
      if (collapsed || !draggingRef.current || !containerRef.current) {
        return
      }
      const rect = containerRef.current.getBoundingClientRect()
      if (rect.width <= 0) {
        return
      }
      setRatio(clampRatio((event.clientX - rect.left) / rect.width))
    }

    const stopDragging = () => {
      if (!draggingRef.current) {
        return
      }
      draggingRef.current = false
      setDragging(false)
    }

    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', stopDragging)
    window.addEventListener('pointercancel', stopDragging)

    return () => {
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', stopDragging)
      window.removeEventListener('pointercancel', stopDragging)
    }
  }, [collapsed])

  const onDividerPointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (collapsed) {
        return
      }
      event.preventDefault()
      draggingRef.current = true
      setDragging(true)
      event.currentTarget.setPointerCapture(event.pointerId)
    },
    [collapsed],
  )

  const onDividerPointerUp = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    draggingRef.current = false
    setDragging(false)
  }, [])

  const onDividerDoubleClick = useCallback(() => {
    if (collapsed) {
      return
    }
    setRatio(DEFAULT_RATIO)
  }, [collapsed])

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => !prev)
  }, [])

  const configPanelStyle = collapsed
    ? undefined
    : {
        flex: `0 0 calc(${ratio * 100}% - 3px)`,
        width: `calc(${ratio * 100}% - 3px)`,
        maxWidth: `calc(${ratio * 100}% - 3px)`,
      }

  return {
    containerRef,
    configPanelStyle,
    collapsed,
    dragging,
    toggleCollapsed,
    onDividerPointerDown,
    onDividerPointerUp,
    onDividerDoubleClick,
  }
}
