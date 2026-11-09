import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import {
  DEFAULT_RIGHT_COLUMN_SIZE,
  RESIZE_KEYBOARD_STEP,
  RIGHT_COLUMN_MIN_WIDTH,
  SPLIT_COLUMN_GAP,
  SPLITTER_WIDTH,
  clampRightColumnWidth,
  defaultRightColumnWidth,
  maxRightColumnWidth,
} from './splitLayout'

export function useSplitLayout() {
  const consoleShellRef = useRef<HTMLElement | null>(null)
  const [rightColumnWidth, setRightColumnWidth] = useState<number | null>(null)
  const [layoutWidth, setLayoutWidth] = useState<number | null>(null)
  const [isResizingLayout, setIsResizingLayout] = useState(false)

  const measureLayoutWidth = useCallback(() => {
    const shell = consoleShellRef.current
    if (!shell) return 0

    const styles = window.getComputedStyle(shell)
    const paddingLeft = Number.parseFloat(styles.paddingLeft) || 0
    const paddingRight = Number.parseFloat(styles.paddingRight) || 0

    return Math.max(0, shell.clientWidth - paddingLeft - paddingRight)
  }, [])

  const syncSplitLayout = useCallback(() => {
    const width = measureLayoutWidth()
    if (width <= 0) return

    setLayoutWidth(width)
    setRightColumnWidth((current) =>
      clampRightColumnWidth(width, current ?? defaultRightColumnWidth(width)),
    )
  }, [measureLayoutWidth])

  useEffect(() => {
    syncSplitLayout()
    window.addEventListener('resize', syncSplitLayout)
    return () => window.removeEventListener('resize', syncSplitLayout)
  }, [syncSplitLayout])

  const resizeRightColumnTo = useCallback((clientX: number) => {
    const shell = consoleShellRef.current
    if (!shell) return

    const width = measureLayoutWidth()
    if (width <= 0) return

    const styles = window.getComputedStyle(shell)
    const paddingRight = Number.parseFloat(styles.paddingRight) || 0
    const contentRight = shell.getBoundingClientRect().right - paddingRight
    const requestedWidth = contentRight - clientX - SPLIT_COLUMN_GAP - SPLITTER_WIDTH / 2

    setLayoutWidth(width)
    setRightColumnWidth(clampRightColumnWidth(width, requestedWidth))
  }, [measureLayoutWidth])

  const resetSplitLayout = useCallback(() => {
    const width = measureLayoutWidth()
    if (width <= 0) {
      setRightColumnWidth(null)
      setLayoutWidth(null)
      return
    }

    setLayoutWidth(width)
    setRightColumnWidth(defaultRightColumnWidth(width))
  }, [measureLayoutWidth])

  const resizeRightColumnBy = useCallback((delta: number) => {
    const width = measureLayoutWidth()
    if (width <= 0) return

    setLayoutWidth(width)
    setRightColumnWidth((current) =>
      clampRightColumnWidth(width, (current ?? defaultRightColumnWidth(width)) + delta),
    )
  }, [measureLayoutWidth])

  const handleResizePointerDown = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault()
    setIsResizingLayout(true)
    resizeRightColumnTo(event.clientX)

    const handlePointerMove = (moveEvent: PointerEvent) => {
      moveEvent.preventDefault()
      resizeRightColumnTo(moveEvent.clientX)
    }
    const stopResizing = () => {
      setIsResizingLayout(false)
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', stopResizing)
      window.removeEventListener('pointercancel', stopResizing)
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopResizing)
    window.addEventListener('pointercancel', stopResizing)
  }, [resizeRightColumnTo])

  const handleResizeKeyDown = useCallback((event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      resizeRightColumnBy(RESIZE_KEYBOARD_STEP)
      return
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      resizeRightColumnBy(-RESIZE_KEYBOARD_STEP)
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      resetSplitLayout()
    }
  }, [resetSplitLayout, resizeRightColumnBy])

  const rightColumnSize = rightColumnWidth === null ? DEFAULT_RIGHT_COLUMN_SIZE : `${rightColumnWidth}px`
  const splitLayoutStyle = {
    '--right-column-size': rightColumnSize,
  } as CSSProperties
  const rightColumnMaxWidth = layoutWidth === null ? undefined : maxRightColumnWidth(layoutWidth)

  return {
    consoleShellRef,
    handleResizeKeyDown,
    handleResizePointerDown,
    isResizingLayout,
    resetSplitLayout,
    resizerAria: {
      max: rightColumnMaxWidth,
      min: RIGHT_COLUMN_MIN_WIDTH,
      now: rightColumnWidth ?? undefined,
    },
    splitLayoutStyle,
  }
}
