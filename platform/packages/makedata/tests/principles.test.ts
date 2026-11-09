import { describe, it, expect } from 'vitest'
import {
  loadWritingPrinciples,
  loadAuditPrinciples,
  loadCompositeSkill,
} from '../src/principles'

describe('Principles', () => {
  describe('loadWritingPrinciples', () => {
    it('should load writing principles from markdown file', async () => {
      const principles = await loadWritingPrinciples()
      expect(principles).toBeDefined()
      expect(typeof principles).toBe('string')
      expect(principles.length).toBeGreaterThan(0)
    })

    it('should contain expected content', async () => {
      const principles = await loadWritingPrinciples()
      // 原则文档应该包含关键章节
      expect(principles).toContain('用例')
    })
  })

  describe('loadAuditPrinciples', () => {
    it('should load audit principles from markdown file', async () => {
      const principles = await loadAuditPrinciples()
      expect(principles).toBeDefined()
      expect(typeof principles).toBe('string')
      expect(principles.length).toBeGreaterThan(0)
    })

    it('should contain audit-related content', async () => {
      const principles = await loadAuditPrinciples()
      // 审核原则应该包含相关关键词
      expect(principles).toContain('审核')
    })
  })

  describe('loadCompositeSkill', () => {
    it('should load composite case skill from markdown file', async () => {
      const skill = await loadCompositeSkill()
      expect(skill).toBeDefined()
      expect(typeof skill).toBe('string')
      expect(skill.length).toBeGreaterThan(0)
    })
  })
})
