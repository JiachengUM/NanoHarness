/**
 * 集成测试：完整场景生成流程
 *
 * 双模式：
 * 1. Mock 模式：快速验证 Plan → Patterns → Generate → Audit → Fix → Judge 流程逻辑
 * 2. Real LLM 模式：真实调用 LLM 跑通完整流程
 *
 * 运行方式：
 * - pnpm test              → 仅运行 Mock 测试
 * - pnpm test:real         → 运行包含 Real LLM 的所有测试
 */

import { describe, it, expect, beforeAll } from 'vitest'
import { generateScenarioPlan } from '../src/generation/index.js'
import { generateScenarioPatterns } from '../src/generation/scenario-pattern-generator.js'
import { generateScenarios } from '../src/generation/index.js'
import {
  loadTestTagTree,
  createMockClient,
  buildMockPatterns,
  describeRealLLM,
} from './test-utils'
import { TagTree } from '../src/core/tag-tree.js'
import { createClient } from '@eval-platform/llm'
import type { OpenAI } from '@eval-platform/llm'
import type { ScenarioPlan } from '@eval-platform/database/models/scenario-plan'

// ═══════════════════════════════════════════════════════════════════════════
// 超时工具（Real LLM 用）
// ═══════════════════════════════════════════════════════════════════════════

const TIMEOUT_PER_PATTERN = 60000
const TIMEOUT_BASE = 60000
const TIMEOUT_PHASE2 = 180000

function calcTestTimeout(patternCount: number): number {
  return TIMEOUT_BASE + patternCount * TIMEOUT_PER_PATTERN + TIMEOUT_PHASE2
}

const TEST_PATTERNS = buildMockPatterns().slice(0, 4)

/**
 * 构建精简测试 Plan（不含 scenario_patterns）
 */
function buildTestPlan(query: string, planData: any): ScenarioPlan {
  return {
    original_query: query,
    task_description: planData.task_description || query,
    target_tags: planData.target_tags.slice(0, 4),
    interpretation_notes: planData.interpretation_notes,
    status: 'confirmed' as const,
    task_id: `task-test-${Date.now()}`,
    generation_task_run_id: `run-test-${Date.now()}`,
    tag_tree_name: 'test-tree',
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Mock 模式集成测试
// ═══════════════════════════════════════════════════════════════════════════

describe('Integration: Mock 模式 - Plan → Patterns → Generate', () => {
  let testTree: TagTree
  let mockClient: any

  beforeAll(() => {
    testTree = loadTestTagTree()
    mockClient = createMockClient({ defaultScenarioCount: 4, defaultAuditPass: true })
  })

  it('mock 完整链路：Plan → Patterns → 场景生成', async () => {
    const query = '生成空调温度调节场景'

    // Step 1: Generate Plan（不含 patterns）
    const planData = await generateScenarioPlan(query, testTree, mockClient)
    expect((planData as any).scenario_patterns).toBeUndefined()

    const plan = buildTestPlan(query, planData)

    // Step 2: Generate Patterns（独立步骤）
    const { patterns, targetScenarioCount } = await generateScenarioPatterns(
      { ...plan, task_id: 'test', generation_task_run_id: 'test', tag_tree_name: 'test' } as ScenarioPlan,
      testTree,
      mockClient
    )
    expect(patterns.length).toBeGreaterThan(0)
    expect(targetScenarioCount).toBeGreaterThanOrEqual(patterns.length)

    // Step 3: Generate Scenarios
    const result = await generateScenarios(query, testTree, mockClient, {
      plan,
      patterns,
      maxIterations: 2,
      initialBatchSize: 3,
      maxRefineRoundsPerBatch: 1,
    })

    expect(result.scenarios.length).toBeGreaterThan(0)
    expect(result.plan.task_id).toBe(plan.task_id)

    // 验证场景质量
    const leafTags = new Set(testTree.getLeafTagNames())
    for (const scenario of result.scenarios) {
      expect(scenario.scenario_id).toBeDefined()
      expect(scenario.scenario_name).toBeDefined()
      expect(scenario.pattern).toBeDefined()
      for (const tag of scenario.tags) {
        expect(leafTags).toContain(tag)
      }
    }

    console.log(`\nMock 集成测试通过: ${result.scenarios.length} 个场景`)
    console.log(`  Pattern 覆盖:`, result.patternCoverage)
  }, 60000)

  it('mock 流式回调应正确触发', async () => {
    const query = '生成音乐播放场景'
    const planData = await generateScenarioPlan(query, testTree, mockClient)
    const plan = buildTestPlan(query, planData)

    let scenarioCount = 0
    let progressCount = 0
    let seenPhase1 = false
    let seenFinal100 = false
    let patternsReceived = false
    let lastProgress = -1  // 追踪上一次进度，验证单调递增

    await generateScenarios(query, testTree, mockClient, {
      plan,
      patterns: TEST_PATTERNS,
      maxIterations: 2,
      initialBatchSize: 2,
      maxRefineRoundsPerBatch: 1,
      onPatternsGenerated: () => { patternsReceived = true },
      onProgress: (info) => {
        progressCount++
        expect(info.progressPercentage).toBeGreaterThanOrEqual(0)
        expect(info.progressPercentage).toBeLessThanOrEqual(100)
        // 验证进度单调递增（不会回退）
        expect(info.progressPercentage).toBeGreaterThanOrEqual(lastProgress)
        lastProgress = info.progressPercentage
        if (info.phase === 'pattern_sweep') seenPhase1 = true
        if (info.progressPercentage === 100 && info.satisfied) seenFinal100 = true
      },
      onScenarioGenerated: async (scenario) => {
        scenarioCount++
        expect(scenario.scenario_id).toBeDefined()
        expect(scenario.pattern).toBeDefined()
      },
    })

    expect(scenarioCount).toBeGreaterThan(0)
    expect(progressCount).toBeGreaterThan(0)
    expect(seenPhase1).toBe(true)
    expect(seenFinal100).toBe(true)

    console.log(`\nMock 流式回调测试通过：${scenarioCount} 个场景，${progressCount} 次进度更新`)
  }, 60000)
})

// ═══════════════════════════════════════════════════════════════════════════
// Real LLM 模式集成测试
// ═══════════════════════════════════════════════════════════════════════════

describeRealLLM('Integration: Real LLM 模式 - Plan → Patterns → Generate', () => {
  let testTree: TagTree
  let client: OpenAI

  beforeAll(() => {
    testTree = loadTestTagTree()
    client = createClient()
  })

  it('real 完整链路：Plan → Patterns → 场景生成', async () => {
    const query = '生成空调温度调节场景'

    // Step 1: Generate Plan
    const planData = await generateScenarioPlan(query, testTree, client)
    expect((planData as any).scenario_patterns).toBeUndefined()

    const plan = buildTestPlan(query, planData)

    // Step 2: Generate Patterns
    const { patterns } = await generateScenarioPatterns(
      { ...plan, task_id: 'test', generation_task_run_id: 'test', tag_tree_name: 'test' } as ScenarioPlan,
      testTree,
      client
    )
    expect(patterns.length).toBeGreaterThan(0)
    console.log(`  生成 ${patterns.length} 个 patterns`)

    // Step 3: Generate Scenarios
    const progressEvents: any[] = []
    const result = await generateScenarios(query, testTree, client, {
      plan,
      patterns: patterns.slice(0, 4), // 限制 pattern 数避免超时
      maxIterations: 3,
      initialBatchSize: 3,
      maxRefineRoundsPerBatch: 1,
      onProgress: (info) => {
        progressEvents.push(info)
      },
    })

    expect(result.scenarios.length).toBeGreaterThan(0)
    expect(result.plan.task_id).toBe(plan.task_id)

    const leafTags = new Set(testTree.getLeafTagNames())
    for (const scenario of result.scenarios) {
      expect(scenario.scenario_id).toBeDefined()
      expect(scenario.pattern).toBeDefined()
      for (const tag of scenario.tags) {
        expect(leafTags).toContain(tag)
      }
    }

    const coveredTags = new Set<string>()
    for (const scenario of result.scenarios) {
      for (const tag of scenario.tags) coveredTags.add(tag)
    }
    const targetTagCoverage = plan.target_tags.filter(tag => coveredTags.has(tag))
    console.log(`  目标标签覆盖: ${targetTagCoverage.length}/${plan.target_tags.length}`)
    console.log(`  场景数量: ${result.actualCount}/${result.targetCount}`)
    console.log(`  Pattern 覆盖:`, result.patternCoverage)
  }, calcTestTimeout(4))

  it('real 自动生成 Plan + Patterns（无显式传入）', async () => {
    const query = '生成导航场景'
    const planData = await generateScenarioPlan(query, testTree, client)
    const plan = buildTestPlan(query, planData)

    // 不传 patterns，让 generateScenarios 自动生成
    const result = await generateScenarios(query, testTree, client, {
      plan,
      maxIterations: 1,
      initialBatchSize: 2,
      maxRefineRoundsPerBatch: 1,
    })

    expect(result.scenarios.length).toBeGreaterThan(0)
    expect(result.plan).toBeDefined()

    console.log(`  Plan 场景数: ${result.targetCount}`)
    console.log(`  实际生成: ${result.actualCount}`)
    console.log(`  Pattern 数: ${Object.keys(result.patternCoverage).length}`)
  }, calcTestTimeout(4))

  it('real 流式回调应正确触发', async () => {
    const query = '生成音乐播放场景'
    const planData = await generateScenarioPlan(query, testTree, client)
    const plan = buildTestPlan(query, planData)

    let scenarioCount = 0
    let progressCount = 0
    let seenPhase1 = false
    let seenFinal100 = false

    await generateScenarios(query, testTree, client, {
      plan,
      patterns: TEST_PATTERNS,
      maxIterations: 2,
      initialBatchSize: 2,
      maxRefineRoundsPerBatch: 1,
      onProgress: (info) => {
        progressCount++
        expect(info.progressPercentage).toBeGreaterThanOrEqual(0)
        expect(info.progressPercentage).toBeLessThanOrEqual(100)
        if (info.phase === 'pattern_sweep') seenPhase1 = true
        if (info.progressPercentage === 100 && info.satisfied) seenFinal100 = true
      },
      onScenarioGenerated: async (scenario) => {
        scenarioCount++
        expect(scenario.scenario_id).toBeDefined()
        expect(scenario.pattern).toBeDefined()
      },
    })

    expect(scenarioCount).toBeGreaterThan(0)
    expect(progressCount).toBeGreaterThan(0)
    expect(seenPhase1).toBe(true)
    expect(seenFinal100).toBe(true)

    console.log(`\nReal 流式回调测试通过：${scenarioCount} 个场景，${progressCount} 次进度更新`)
  }, calcTestTimeout(4))
})
