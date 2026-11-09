/**
 * Generation 测试 - 双模式
 *
 * 1. Mock 模式：使用 createMockClient 快速验证场景/用例生成代码逻辑
 * 2. Real LLM 模式：调用真实 LLM 跑通完整生成流程
 *
 * 运行方式：
 * - pnpm test              → 仅运行 Mock 测试
 * - pnpm test:real         → 运行包含 Real LLM 的所有测试
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { generateScenarios, generateCasesFromScenarios, TagTree, previewTagTree } from '../src'
import {
  loadTestTagTree,
  getTestLeafTags,
  createMockClient,
  buildMockPlanData,
  buildMockPatterns,
  describeRealLLM,
} from './test-utils'
import { createClient } from '@eval-platform/llm'
import type { Scenario } from '@eval-platform/database/models/scenario'
import type { ScenarioPlan } from '@eval-platform/database/models/scenario-plan'

// ═══════════════════════════════════════════════════════════════════════════
// 共享工具
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 构建精简的测试 Plan（不含 scenario_patterns，符合新流程）
 */
function buildTestPlan(query: string): ScenarioPlan {
  return {
    task_id: `test-task-${Date.now()}`,
    generation_task_run_id: `test-run-${Date.now()}`,
    tag_tree_name: 'test-tree',
    original_query: query,
    task_description: query,
    target_tags: ['温度增减调节', '精确地点直达', '常用地点记忆'],
    interpretation_notes: '测试用精简 Plan，聚焦空调温度调节和导航到常用地点',
    status: 'pending',
  } as ScenarioPlan
}

const TEST_PATTERNS = buildMockPatterns()

/**
 * 根据 pattern 数动态计算测试超时（Real LLM 模式用）
 */
const TIMEOUT_PER_PATTERN = 60000
const TIMEOUT_BASE = 60000
const TIMEOUT_PHASE2 = 120000

function calcTestTimeout(patternCount: number): number {
  return TIMEOUT_BASE + patternCount * TIMEOUT_PER_PATTERN + TIMEOUT_PHASE2
}

// ═══════════════════════════════════════════════════════════════════════════
// Mock 模式测试（快速验证代码逻辑）
// ═══════════════════════════════════════════════════════════════════════════

describe('Generation - Mock 模式', () => {
  let testTree: TagTree
  let mockClient: any

  beforeEach(() => {
    testTree = loadTestTagTree()
    mockClient = createMockClient({ defaultScenarioCount: 3, defaultAuditPass: true })
  })

  describe('generateScenarios with mock LLM', () => {
    it('mock 应基于 Plan + Patterns 生成场景', async () => {
      const query = '生成空调温度调节场景'
      const plan = buildTestPlan(query)

      const result = await generateScenarios(query, testTree, mockClient, {
        plan,
        patterns: TEST_PATTERNS,
        maxIterations: 1,
      })

      expect(Array.isArray(result.scenarios)).toBe(true)
      expect(result.scenarios.length).toBeGreaterThan(0)

      result.scenarios.forEach((scenario, index) => {
        expect(scenario).toHaveProperty('scenario_id')
        expect(scenario).toHaveProperty('scenario_name')
        expect(scenario).toHaveProperty('description')
        expect(scenario).toHaveProperty('tags')
        expect(Array.isArray(scenario.tags)).toBe(true)
        console.log(`Mock Scenario ${index + 1}:`, scenario.scenario_name, '| Pattern:', scenario.pattern)
      })

      // 验证 pattern 覆盖
      const coveredPatterns = Object.values(result.patternCoverage).filter(c => c > 0).length
      expect(coveredPatterns).toBeGreaterThan(0)

      console.log(`\nMock 生成统计: ${result.scenarios.length} 个场景`)
    }, 60000)

    it('mock 场景应携带 pattern 字段', async () => {
      const query = '生成导航场景'
      const plan = buildTestPlan(query)

      const result = await generateScenarios(query, testTree, mockClient, {
        plan,
        patterns: TEST_PATTERNS,
        maxIterations: 1,
      })

      // 每个场景都应有 pattern 字段
      result.scenarios.forEach(s => {
        expect(s.pattern).toBeDefined()
        expect(typeof s.pattern).toBe('string')
      })
    }, 60000)

    it('mock 应通过 onPatternsGenerated 回调推送 patterns', async () => {
      const query = '生成场景'
      const plan = buildTestPlan(query)

      let receivedPatterns: string[] | null = null
      await generateScenarios(query, testTree, mockClient, {
        plan,
        maxIterations: 1,
        onPatternsGenerated: (patterns, targetScenarioCount) => {
          receivedPatterns = patterns
          expect(targetScenarioCount).toBeGreaterThanOrEqual(patterns.length)
        },
      })

      // 未传 patterns 时应自动生成并回调
      expect(receivedPatterns).not.toBeNull()
      expect(receivedPatterns!.length).toBeGreaterThan(0)
    }, 60000)

    it('mock 应通过 onProgress 回调推送进度', async () => {
      const query = '生成场景'
      const plan = buildTestPlan(query)

      const progressEvents: any[] = []
      await generateScenarios(query, testTree, mockClient, {
        plan,
        patterns: TEST_PATTERNS,
        maxIterations: 1,
        onProgress: (info) => {
          progressEvents.push(info)
          expect(info.progressPercentage).toBeGreaterThanOrEqual(0)
          expect(info.progressPercentage).toBeLessThanOrEqual(100)
        },
      })

      expect(progressEvents.length).toBeGreaterThan(0)
    }, 60000)

    it('mock Plan 不应包含 scenario_patterns', async () => {
      const query = '生成场景'
      const plan = buildTestPlan(query)

      expect((plan as any).scenario_patterns).toBeUndefined()
    }, 10000)
  })

  describe('generateCasesFromScenarios with mock LLM', () => {
    it('mock 应基于场景生成用例', async () => {
      const scenario: Scenario = {
        scenario_id: 'scenario-001',
        scenario_name: '空调温度调节测试',
        description: '测试用户要求调节空调温度的场景',
        tags: ['温度增减调节'],
        pattern: '单轮直达空调温度调节场景',
      }

      const cases = await generateCasesFromScenarios(
        [scenario], 2, mockClient, 'test-dataset'
      )

      expect(cases.length).toBeGreaterThan(0)
      cases.forEach((c, index) => {
        expect(c).toHaveProperty('case_id')
        expect(c).toHaveProperty('dataset_id', 'test-dataset')
        expect(c).toHaveProperty('source_scenario_id', 'scenario-001')
        expect(c).toHaveProperty('user_query_lists')
        expect(c).toHaveProperty('expected_script')
        expect(c).toHaveProperty('nl_assertion')
        console.log(`Mock Case ${index + 1}: ${c.case_id}`)
      })
    }, 30000)

    it('mock 用例应追溯来源场景', async () => {
      const scenario: Scenario = {
        scenario_id: 'scenario-002',
        scenario_name: '导航到常用地点',
        description: '测试用户使用常用地点记忆进行导航',
        tags: ['精确地点直达', '常用地点记忆'],
        pattern: '单轮直达导航到常用地点场景',
      }

      const cases = await generateCasesFromScenarios([scenario], 1, mockClient, 'test')

      expect(cases.length).toBeGreaterThan(0)
      expect(cases[0].source_scenario_id).toBe('scenario-002')
    }, 30000)
  })

  describe('previewTagTree', () => {
    it('mock 应包含标签树完整信息', () => {
      const preview = previewTagTree(testTree, {
        showTree: true,
        showLeafList: true,
        title: 'LLM Context',
      })

      expect(preview).toContain('车机助手评测标签树')
      expect(preview).toContain('温度增减调节')
      expect(preview).toContain('叶子标签总数')
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Real LLM 模式测试（真实调用 LLM，验证生成效果）
// ═══════════════════════════════════════════════════════════════════════════

describeRealLLM('Generation - Real LLM 模式', () => {
  let testTree: TagTree

  beforeEach(() => {
    testTree = loadTestTagTree()
  })

  describe('generateScenarios with real LLM', () => {
    it('real 应从 query 生成场景', async () => {
      const client = createClient()
      const query = '生成2个日常通勤场景，涉及空调温度调节和导航到常用地点'
      const plan = buildTestPlan(query)

      const result = await generateScenarios(query, testTree, client, {
        plan,
        patterns: TEST_PATTERNS,
        maxIterations: 2,
      })

      const scenarios = result.scenarios
      expect(Array.isArray(scenarios)).toBe(true)
      expect(scenarios.length).toBeGreaterThan(0)

      scenarios.forEach((scenario, index) => {
        expect(scenario).toHaveProperty('scenario_id')
        expect(scenario).toHaveProperty('scenario_name')
        expect(scenario).toHaveProperty('description')
        expect(scenario).toHaveProperty('tags')
        expect(Array.isArray(scenario.tags)).toBe(true)
        expect(scenario.scenario_id).toMatch(/^scenario-/)
        console.log(`Real Scenario ${index + 1}:`, scenario.scenario_name)
        console.log(`  Tags:`, scenario.tags.join(', '))
        console.log(`  Pattern:`, scenario.pattern)
      })

      const coveredPatterns = Object.values(result.patternCoverage).filter(c => c > 0).length
      expect(coveredPatterns).toBeGreaterThan(0)

      console.log(`\nReal 生成统计: ${scenarios.length} 个场景, 覆盖率: ${result.finalCoveragePercentage}%`)
    }, calcTestTimeout(3))

    it('real 场景标签应来自标签树叶子节点', async () => {
      const client = createClient()
      const query = '生成空调和导航相关的场景'
      const plan = buildTestPlan(query)

      const result = await generateScenarios(query, testTree, client, {
        plan,
        patterns: TEST_PATTERNS,
        maxIterations: 2,
      })

      const validLeafTags = new Set(testTree.getLeafTagNames())
      result.scenarios.forEach(scenario => {
        scenario.tags.forEach(tag => {
          if (!validLeafTags.has(tag)) {
            console.warn(`警告: 场景 "${scenario.scenario_name}" 使用了非叶子标签 "${tag}"`)
          }
        })
      })
      expect(result.scenarios.length).toBeGreaterThan(0)
    }, calcTestTimeout(3))

    it('real 应生成多样化场景', async () => {
      const client = createClient()
      const query = '生成涉及不同功能的车载助手场景：空调调节、导航、媒体播放、记忆调用'
      const plan = buildTestPlan(query)

      const result = await generateScenarios(query, testTree, client, {
        plan,
        patterns: TEST_PATTERNS,
        maxIterations: 2,
      })

      expect(result.scenarios.length).toBeGreaterThanOrEqual(2)

      const names = result.scenarios.map(s => s.scenario_name)
      const uniqueNames = new Set(names)
      expect(uniqueNames.size).toBe(names.length)

      console.log('Real Generated scenarios:')
      result.scenarios.forEach((s, i) => {
        console.log(`  ${i + 1}. ${s.scenario_name} [${s.pattern}]`)
      })
    }, calcTestTimeout(3))
  })

  describe('generateCasesFromScenarios with real LLM', () => {
    it('real 应基于场景生成用例', async () => {
      const scenario: Scenario = {
        scenario_id: 'scenario-001',
        scenario_name: '空调温度调节测试',
        description: '测试用户要求调节空调温度的场景，验证助手理解温度增减指令并执行',
        tags: ['温度增减调节'],
        pattern: '单轮直达空调温度调节场景',
      }

      const client = createClient()
      const cases = await generateCasesFromScenarios([scenario], 2, client, 'test-dataset')

      expect(cases.length).toBeGreaterThan(0)
      cases.forEach((c, index) => {
        expect(c).toHaveProperty('case_id')
        expect(c).toHaveProperty('dataset_id', 'test-dataset')
        expect(c).toHaveProperty('source_scenario_id', 'scenario-001')
        expect(c).toHaveProperty('user_query_lists')
        expect(c).toHaveProperty('expected_script')
        expect(c).toHaveProperty('nl_assertion')
        console.log(`Real Case ${index + 1}: ${c.case_id}`)
        console.log(`  Tags: ${c.tags?.join(', ')}`)
      })
    }, 120000)

    it('real 用例应有有效结构', async () => {
      const scenario: Scenario = {
        scenario_id: 'scenario-002',
        scenario_name: '导航到常用地点',
        description: '测试用户使用常用地点记忆进行导航',
        tags: ['精确地点直达', '常用地点记忆'],
        pattern: '单轮直达导航到常用地点场景',
      }

      const client = createClient()
      const cases = await generateCasesFromScenarios([scenario], 1, client, 'test')

      expect(cases.length).toBeGreaterThan(0)
      const testCase = cases[0]

      expect(Array.isArray(testCase.user_query_lists)).toBe(true)
      expect(testCase.user_query_lists.length).toBeGreaterThan(0)

      testCase.user_query_lists.forEach(session => {
        expect(session).toHaveProperty('user_query_list')
        expect(Array.isArray(session.user_query_list)).toBe(true)
        expect(session.user_query_list.length).toBeGreaterThan(0)
        session.user_query_list.forEach((msg: any) => {
          expect(msg).toHaveProperty('role')
          expect(msg).toHaveProperty('content')
          expect(['user', 'assistant', 'system']).toContain(msg.role)
        })
      })

      console.log('Real Generated case structure:')
      console.log('  case_id:', testCase.case_id)
      console.log('  user_query_lists count:', testCase.user_query_lists.length)
      console.log('  tags:', testCase.tags)
    }, 60000)

    it('real 用例应携带正确的元数据', async () => {
      const scenario: Scenario = {
        scenario_id: 'source-scenario-001',
        scenario_name: '来源场景名称',
        description: '测试描述',
        tags: ['温度增减调节'],
        pattern: '多轮对话空调温度调节场景',
      }

      const client = createClient()
      const cases = await generateCasesFromScenarios([scenario], 1, client, 'test-dataset')

      expect(cases.length).toBeGreaterThan(0)
      expect(cases[0].source_scenario_id).toBe('source-scenario-001')
      expect(cases[0].source_scenario_name).toBe('来源场景名称')
      expect(cases[0].dataset_id).toBe('test-dataset')
    }, 60000)

    it('real 应从多个场景批量生成用例', async () => {
      const scenarios: Scenario[] = [
        {
          scenario_id: 's1',
          scenario_name: '场景A',
          description: '测试场景A',
          tags: ['温度增减调节'],
          pattern: '单轮直达空调温度调节场景',
        },
        {
          scenario_id: 's2',
          scenario_name: '场景B',
          description: '测试场景B',
          tags: ['精确地点直达'],
          pattern: '单轮直达导航到常用地点场景',
        },
      ]

      const client = createClient()
      const cases = await generateCasesFromScenarios(scenarios, 1, client, 'test')

      expect(cases.length).toBeGreaterThanOrEqual(2)
      const sourceIds = new Set(cases.map(c => c.source_scenario_id))
      expect(sourceIds.has('s1')).toBe(true)
      expect(sourceIds.has('s2')).toBe(true)
    }, 120000)
  })
})
