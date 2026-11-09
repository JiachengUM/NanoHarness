type FocusWrapState = {
  currentIndex: number
  focusableCount: number
  backwards: boolean
}

export function getFocusWrapIndex({
  currentIndex,
  focusableCount,
  backwards,
}: FocusWrapState): number | undefined {
  if (focusableCount <= 0) return undefined
  if (currentIndex < 0 || currentIndex >= focusableCount) {
    return backwards ? focusableCount - 1 : 0
  }
  if (backwards && currentIndex === 0) return focusableCount - 1
  if (!backwards && currentIndex === focusableCount - 1) return 0
  return undefined
}
