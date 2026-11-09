import { readFileSync } from 'node:fs'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import {
  CAPABILITY_EXPERIENCES,
  CapabilityGuide,
} from './CapabilityGuide'

describe('CapabilityGuide', () => {
  it('offers three concise multi-turn experiences without auto-submitting them', () => {
    const onTry = vi.fn()
    const markup = renderToStaticMarkup(
      <CapabilityGuide
        variant="empty"
        onClose={vi.fn()}
        onTry={onTry}
      />,
    )

    expect(CAPABILITY_EXPERIENCES).toHaveLength(3)
    expect(CAPABILITY_EXPERIENCES.map(({ prompts }) => prompts.length))
      .toEqual([2, 3, 2])
    expect(markup).toContain('任务开始后，也可以继续聊')
    expect(markup).toContain('随时问进度')
    expect(markup).toContain('取消指定任务')
    expect(markup).toContain('直接修改条件')
    expect(markup.match(/>体验<\/button>/g)).toHaveLength(3)
    expect(markup).toContain('<summary>为什么它能做到</summary>')
    expect(onTry).not.toHaveBeenCalled()
  })

  it('exposes a non-modal dialog and disables trials when input is unavailable', () => {
    const markup = renderToStaticMarkup(
      <CapabilityGuide
        disabled
        variant="popover"
        onClose={vi.fn()}
        onTry={vi.fn()}
      />,
    )

    expect(markup).toContain('role="dialog"')
    expect(markup).toContain('aria-modal="false"')
    expect(markup).toContain('id="capability-guide-surface"')
    expect(markup.match(/>连接后体验<\/button>/g)).toHaveLength(3)
    expect(markup.match(/disabled=""/g)).toHaveLength(3)
  })

  it('uses one material layer and solid inner capability rows', () => {
    const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8')
    const popoverRule = css.match(/\.capability-popover\s*\{([^}]*)\}/s)?.[1] ?? ''
    const itemRule = css.match(/\.capability-item\s*\{([^}]*)\}/s)?.[1] ?? ''

    expect(popoverRule).toMatch(/backdrop-filter:\s*blur\(28px\)/)
    expect(popoverRule).toMatch(/transform-origin:\s*top right/)
    expect(itemRule).toMatch(/background:\s*#f4f7fc/)
    expect(itemRule).not.toMatch(/backdrop-filter:/)
    expect(css).toMatch(
      /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.capability-popover\s*\{[^}]*animation:\s*none/s,
    )
    expect(css).toMatch(
      /@media \(prefers-reduced-transparency: reduce\)[\s\S]*?\.capability-popover,[\s\S]*?\.capability-guide-empty\s*\{[^}]*background:\s*var\(--color-surface\)/s,
    )
  })
})
