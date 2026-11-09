const DEFAULT_RIGHT_COLUMN_RATIO = 0.6
export const DEFAULT_RIGHT_COLUMN_SIZE = '60%'
export const RIGHT_COLUMN_MIN_WIDTH = 380
const LEFT_COLUMN_MIN_WIDTH = 380
export const SPLITTER_WIDTH = 10
export const SPLIT_COLUMN_GAP = 10
const SPLIT_LAYOUT_RESERVED_WIDTH = SPLITTER_WIDTH + SPLIT_COLUMN_GAP * 2
export const RESIZE_KEYBOARD_STEP = 32

export function maxRightColumnWidth(availableWidth: number): number {
  return Math.max(
    RIGHT_COLUMN_MIN_WIDTH,
    Math.round(availableWidth - LEFT_COLUMN_MIN_WIDTH - SPLIT_LAYOUT_RESERVED_WIDTH),
  )
}

export function clampRightColumnWidth(availableWidth: number, requestedWidth: number): number {
  const minWidth = RIGHT_COLUMN_MIN_WIDTH
  const maxWidth = maxRightColumnWidth(availableWidth)

  return Math.min(Math.max(Math.round(requestedWidth), minWidth), maxWidth)
}

export function defaultRightColumnWidth(availableWidth: number): number {
  return clampRightColumnWidth(availableWidth, availableWidth * DEFAULT_RIGHT_COLUMN_RATIO)
}
