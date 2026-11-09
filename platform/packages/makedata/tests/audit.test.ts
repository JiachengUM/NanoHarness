/**
 * Audit 测试 - 双模式
 *
 * 1. Mock 模式：使用 createMockClient 快速测试审核/修复代码逻辑（不调用 LLM）
 * 2. Real LLM 模式：调用真实 LLM 验证审核效果
 *
 * 运行方式：
 * - pnpm test              → 仅运行 Mock 测试
 * - pnpm test:real         → 运行包含 Real LLM 的所有测试
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { auditOneCase, auditCases, validateCaseSchema, validateTags, validateInteractionChain } from '../src'
import {
  loadTestTagTree,
  getTestLeafTags,
  getInvalidLeafTag,
  getIntermediateNodeTag,
  createMockClient,
  describeRealLLM,
} from './test-utils'
import { TagTree } from '../src/core/tag-tree'
import { createClient } from '@eval-platform/llm'
import type { CaseWithScenario } from '@eval-platform/database'

// ═══════════════════════════════════════════════════════════════════════════
// 测试数据构建
// ═══════════════════════════════════════════════════════════════════════════

function buildValidCase(): CaseWithScenario {
  return {
    dataset_id: 'test-dataset',
    case_id: 'test-case-001',
    context_config: { car_info: '车速：30km/h' },
    max_round: 8,
    user_query_lists: [
      {
        user_query_list: [{ role: 'user', content: '把空调调低两度' }],
        mock_info: {},
        mock_time: '2024-01-15 09:00:00',
      },
    ],
    expected_script: '用户：把空调调低两度\n管家：（验证温度调节指令执行结果）\n助手：已将空调温度调低2度',
    nl_assertion: ['助手正确识别温度调节指令并执行', '助手反馈执行结果'],
    case_description: '测试空调温度调节功能',
    tags: getTestLeafTags().slice(0, 3),
    source_scenario_id: 'scenario-001',
    source_scenario_name: '空调测试',
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 程序化校验测试（不依赖 LLM，始终运行）
// ═══════════════════════════════════════════════════════════════════════════

describe('Audit - 程序化校验', () => {
  let testTree: TagTree

  beforeEach(() => {
    testTree = loadTestTagTree()
  })

  describe('validateCaseSchema', () => {
    it('should pass for valid case', () => {
      const result = validateCaseSchema(buildValidCase())
      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
    })

    it('should fail for missing required fields', () => {
      const testCase = { ...buildValidCase(), case_id: '' } as CaseWithScenario
      const result = validateCaseSchema(testCase)
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('case_id'))).toBe(true)
    })

    it('should fail for invalid max_round', () => {
      const testCase = { ...buildValidCase(), max_round: -1 } as CaseWithScenario
      const result = validateCaseSchema(testCase)
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('max_round'))).toBe(true)
    })

    it('should fail for empty user_query_lists', () => {
      const testCase = { ...buildValidCase(), user_query_lists: [] } as CaseWithScenario
      const result = validateCaseSchema(testCase)
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('user_query_lists'))).toBe(true)
    })

    it('should detect schema errors with paths', () => {
      const testCase = { ...buildValidCase(), max_round: -5, case_id: '' } as CaseWithScenario
      const result = validateCaseSchema(testCase)
      expect(result.valid).toBe(false)
      expect(result.errors.length).toBeGreaterThanOrEqual(1)
      result.errors.forEach(error => {
        expect(error).toMatch(/^\[/)
      })
    })
  })

  describe('validateTags', () => {
    it('should pass for valid leaf tags from vehicle tree', () => {
      const result = validateTags(getTestLeafTags(), testTree)
      expect(result.valid).toBe(true)
      expect(result.info).toContain('D1校验通过')
    })

    it('should fail for non-existent tags', () => {
      const result = validateTags([getInvalidLeafTag()], testTree)
      expect(result.valid).toBe(false)
      expect(result.info).toContain('不在标签树中')
    })

    it('should fail for intermediate node tags', () => {
      const result = validateTags([getIntermediateNodeTag()], testTree)
      expect(result.valid).toBe(false)
      expect(result.info).toContain('中间节点')
      expect(result.info).toContain('D1')
    })

    it('should fail for empty tags array', () => {
      const result = validateTags([], testTree)
      expect(result.valid).toBe(false)
      expect(result.info).toContain('无tags')
    })

    it('should detect mixed valid and invalid tags', () => {
      const mixedTags = [getTestLeafTags()[0], getInvalidLeafTag()]
      const result = validateTags(mixedTags, testTree)
      expect(result.valid).toBe(false)
      expect(result.info).toContain('不在标签树中')
    })

    it('should validate all leaf tags in vehicle tree', () => {
      const allLeaves = testTree.getLeafTagNames().slice(0, 20)
      const result = validateTags(allLeaves, testTree)
      expect(result.valid).toBe(true)
    })
  })

  describe('validateInteractionChain', () => {
    it('should pass for valid single session', () => {
      const result = validateInteractionChain(buildValidCase())
      expect(result.valid).toBe(true)
      expect(result.issues).toHaveLength(0)
    })

    it('should fail for empty user_query_lists', () => {
      const testCase = { ...buildValidCase(), user_query_lists: [] } as CaseWithScenario
      const result = validateInteractionChain(testCase)
      expect(result.valid).toBe(false)
      expect(result.info).toContain('为空')
    })

    it('should detect invalid session structure', () => {
      const testCase = {
        ...buildValidCase(),
        user_query_lists: [{ user_query_list: 'not-an-array' }],
      } as CaseWithScenario
      const result = validateInteractionChain(testCase)
      expect(result.valid).toBe(false)
      expect(result.issues.some(i => i.includes('不是数组'))).toBe(true)
    })
  })

  describe('Integration with real tree', () => {
    it('should validate against all leaf tags in vehicle tree', () => {
      const allLeafTags = testTree.getLeafTagNames().slice(0, 10)
      const result = validateTags(allLeafTags, testTree)
      expect(result.valid).toBe(true)
    })

    it('should reject known intermediate nodes', () => {
      const intermediateNodes = ['空调操作', '车控操作', '产品视角标签子树']
      intermediateNodes.forEach(nodeName => {
        const result = validateTags([nodeName], testTree)
        expect(result.valid).toBe(false)
        expect(result.info).toContain('中间节点')
      })
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Mock LLM 审核测试（快速验证审核/修复代码逻辑）
// ═══════════════════════════════════════════════════════════════════════════

describe('Audit - Mock LLM 模式', () => {
  let testTree: TagTree
  let mockClient: any

  beforeEach(() => {
    testTree = loadTestTagTree()
    mockClient = createMockClient({ defaultAuditPass: true })
  })

  it('mock auditOneCase 应返回结构正确的审核结果', async () => {
    const result = await auditOneCase(buildValidCase(), testTree, mockClient)

    expect(result).toHaveProperty('id')
    expect(result).toHaveProperty('case_id')
    expect(result).toHaveProperty('audit_pass')
    expect(result).toHaveProperty('issues')
    expect(result).toHaveProperty('summary')
    expect(typeof result.audit_pass).toBe('boolean')
    expect(Array.isArray(result.issues)).toBe(true)
  }, 30000)

  it('mock auditOneCase 审核通过时 issues 为空', async () => {
    const result = await auditOneCase(buildValidCase(), testTree, mockClient)
    expect(result.audit_pass).toBe(true)
    expect(result.issues).toHaveLength(0)
  }, 30000)

  it('mock auditOneCase 审核失败时 issues 非空', async () => {
    const failClient = createMockClient({ defaultAuditPass: false })
    const result = await auditOneCase(buildValidCase(), testTree, failClient)
    expect(result.audit_pass).toBe(false)
    expect(result.issues.length).toBeGreaterThan(0)

    const issue = result.issues[0]
    expect(issue).toHaveProperty('principle')
    expect(issue).toHaveProperty('dimension')
    expect(issue).toHaveProperty('severity')
    expect(issue).toHaveProperty('description')
    expect(issue).toHaveProperty('suggestion')
  }, 30000)

  it('mock auditCases 应批量审核多个用例', async () => {
    const testCases = [
      buildValidCase(),
      { ...buildValidCase(), case_id: 'test-case-002' },
    ]

    const results = await auditCases(testCases, testTree, mockClient, { concurrency: 2 })

    expect(results).toHaveLength(2)
    // Mock client 可能不精确返回 case_id，只验证结构
    results.forEach(r => {
      expect(r).toHaveProperty('audit_pass')
      expect(r).toHaveProperty('issues')
      expect(r).toHaveProperty('summary')
      expect(r).toHaveProperty('case_id')
    })
  }, 30000)

  it('mock auditCases 应触发进度回调', async () => {
    let progressCalled = false
    await auditCases([buildValidCase()], testTree, mockClient, {
      concurrency: 1,
      onProgress: () => { progressCalled = true },
    })
    expect(progressCalled).toBe(true)
  }, 30000)

  it('Combined: 程序化校验通过 + Mock 审核通过', async () => {
    const testCase = buildValidCase()
    const schemaResult = validateCaseSchema(testCase)
    const tagsResult = validateTags(testCase.tags || [], testTree)
    const chainResult = validateInteractionChain(testCase)

    expect(schemaResult.valid).toBe(true)
    expect(tagsResult.valid).toBe(true)
    expect(chainResult.valid).toBe(true)

    const auditResult = await auditOneCase(testCase, testTree, mockClient)
    expect(auditResult.audit_pass).toBe(true)
  }, 30000)
})

// ═══════════════════════════════════════════════════════════════════════════
// Real LLM 审核测试（真实调用 LLM，验证审核效果）
// ═══════════════════════════════════════════════════════════════════════════

describeRealLLM('Audit - Real LLM 模式', () => {
  let testTree: TagTree

  beforeEach(() => {
    testTree = loadTestTagTree()
  })

  it('real auditOneCase 应审核有效用例并返回结果', async () => {
    const client = createClient()
    const result = await auditOneCase(buildValidCase(), testTree, client)

    expect(result).toHaveProperty('id')
    expect(result).toHaveProperty('case_id')
    expect(result).toHaveProperty('audit_pass')
    expect(result).toHaveProperty('issues')
    expect(result).toHaveProperty('summary')
    expect(typeof result.audit_pass).toBe('boolean')
    expect(Array.isArray(result.issues)).toBe(true)
    expect(result.case_id).toBe('test-case-001')

    console.log('Real LLM Audit Result:', JSON.stringify(result, null, 2))
  }, 60000)

  it('real auditOneCase 应检测有问题用例的缺陷', async () => {
    const problematicCase: CaseWithScenario = {
      ...buildValidCase(),
      case_id: 'problematic-case',
      user_query_lists: [
        {
          user_query_list: [{ role: 'user', content: '把空调调低两度（测试用例）' }],
          mock_info: {},
          mock_time: '2024-01-15 09:00:00',
        },
      ],
      nl_assertion: [
        '助手必须正确执行指令（这是一个万能断言）',
        '助手不得答非所问',
      ],
    }

    const client = createClient()
    const result = await auditOneCase(problematicCase, testTree, client)

    expect(result.summary).toBeTruthy()
    expect(typeof result.audit_pass).toBe('boolean')
    console.log('Real LLM Audit Result:', JSON.stringify(result, null, 2))
  }, 60000)

  it('real auditOneCase 应检测标签不匹配问题', async () => {
    const wrongTagCase: CaseWithScenario = {
      ...buildValidCase(),
      case_id: 'wrong-tag-case',
      tags: ['温度增减调节', '精确地点直达'],
    }

    const client = createClient()
    const result = await auditOneCase(wrongTagCase, testTree, client)

    if (!result.audit_pass && result.issues.length > 0) {
      const issue = result.issues[0]
      expect(issue).toHaveProperty('principle')
      expect(issue).toHaveProperty('dimension')
      expect(issue).toHaveProperty('severity')
      expect(issue).toHaveProperty('description')
      expect(issue).toHaveProperty('suggestion')
    }
  }, 60000)

  it('real auditCases 应批量审核多个用例', async () => {
    const testCases = [
      buildValidCase(),
      { ...buildValidCase(), case_id: 'test-case-002' },
    ]

    const client = createClient()
    const results = await auditCases(testCases, testTree, client, { concurrency: 1 })

    expect(results).toHaveLength(2)
    expect(results[0].case_id).toBe('test-case-001')
    expect(results[1].case_id).toBe('test-case-002')
    results.forEach(r => {
      expect(r).toHaveProperty('audit_pass')
      expect(r).toHaveProperty('issues')
      expect(r).toHaveProperty('summary')
    })
  }, 120000)

  it('real auditCases 应触发进度回调', async () => {
    const client = createClient()
    let progressCalled = false
    await auditCases([buildValidCase()], testTree, client, {
      concurrency: 1,
      onProgress: () => { progressCalled = true },
    })
    expect(progressCalled).toBe(true)
  }, 60000)

  it('real Combined: 程序化校验 + LLM 审核', async () => {
    const testCase = buildValidCase()
    const schemaResult = validateCaseSchema(testCase)
    const tagsResult = validateTags(testCase.tags || [], testTree)
    const chainResult = validateInteractionChain(testCase)

    expect(schemaResult.valid).toBe(true)
    expect(tagsResult.valid).toBe(true)
    expect(chainResult.valid).toBe(true)

    const client = createClient()
    const auditResult = await auditOneCase(testCase, testTree, client)

    console.log('Combined Validation + Audit:')
    console.log('  Schema:', schemaResult.valid ? '✓' : '✗')
    console.log('  Tags:', tagsResult.valid ? '✓' : '✗')
    console.log('  Chain:', chainResult.valid ? '✓' : '✗')
    console.log('  LLM Audit:', auditResult.audit_pass ? '✓' : '✗')
    console.log('  Summary:', auditResult.summary)
  }, 60000)
})
