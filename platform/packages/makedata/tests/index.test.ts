import { describe, it, expect } from 'vitest'

// 测试主出口导出
describe('Index exports', () => {
  it('should export core components', async () => {
    const index = await import('../src/index')

    expect(index.TagTree).toBeDefined()
    expect(index.TagTreeNode).toBeDefined()
    expect(index.previewTagTree).toBeDefined()
  })

  it('should export generation functions', async () => {
    const index = await import('../src/index')

    expect(index.generateScenarios).toBeDefined()
    expect(index.generateCasesFromScenarios).toBeDefined()
    expect(index.generateAndRefineCases).toBeDefined()
  })

  it('should export audit functions', async () => {
    const index = await import('../src/index')

    expect(index.auditCases).toBeDefined()
    expect(index.auditOneCase).toBeDefined()
    expect(index.fixCasesByAudit).toBeDefined()
    expect(index.fixCaseLoop).toBeDefined()
  })

  it('should export validation functions', async () => {
    const index = await import('../src/index')

    expect(index.validateCaseSchema).toBeDefined()
    expect(index.validateTags).toBeDefined()
    expect(index.validateInteractionChain).toBeDefined()
  })

  it('should export principle loaders', async () => {
    const index = await import('../src/index')

    expect(index.loadWritingPrinciples).toBeDefined()
    expect(index.loadAuditPrinciples).toBeDefined()
    expect(index.loadCompositeSkill).toBeDefined()
  })
})
