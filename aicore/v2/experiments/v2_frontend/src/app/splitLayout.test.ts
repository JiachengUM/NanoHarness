import { describe, expect, it } from 'vitest'
import {
  DEFAULT_RIGHT_COLUMN_SIZE,
  defaultRightColumnWidth,
  maxRightColumnWidth,
} from './splitLayout'

describe('splitLayout', () => {
  it('uses a 60% default right column', () => {
    expect(DEFAULT_RIGHT_COLUMN_SIZE).toBe('60%')
    expect(defaultRightColumnWidth(1248)).toBe(749)
  })

  it('clamps the 60% default against the left-column minimum', () => {
    expect(defaultRightColumnWidth(960)).toBe(550)
    expect(maxRightColumnWidth(960)).toBe(550)
  })
})
