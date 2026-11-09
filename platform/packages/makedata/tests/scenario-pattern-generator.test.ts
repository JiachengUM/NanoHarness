/**
 * Scenario Pattern Generator 测试 - 双模式
 *
 * 1. Mock 模式：快速验证 pattern 生成代码逻辑
 * 2. Real LLM 模式：真实调用 LLM 验证 pattern 生成效果
 *
 * 运行方式：
 * - pnpm test              → 仅运行 Mock 测试
 * - pnpm test:real         → 运行包含 Real LLM 的所有测试
 */

import { describe, it, expect, beforeAll } from 'vitest'
import { TagTree } from '../src'
import { generateScenarioPatterns } from '../src/generation/scenario-pattern-generator.js'
import {
  loadTestTagTree,
  createMockClient,
  buildMockPlanData,
  describeRealLLM,
} from './test-utils'
import { createClient } from '@eval-platform/llm'
import type { ScenarioPlan } from '@eval-platform/database/models/scenario-plan'
import type { OpenAI } from '@eval-platform/llm'

/**
 * 构建测试用 Plan（不含 scenario_patterns）
 */
function buildTestPlan(query: string): ScenarioPlan {
  const base = buildMockPlanData(query)
  return {
    ...base,
    task_id: `test-task-${Date.now()}`,
    generation_task_run_id: `test-run-${Date.now()}`,
  } as ScenarioPlan
}

// ═══════════════════════════════════════════════════════════════════════════
// Mock 模式测试
// ═══════════════════════════════════════════════════════════════════════════

describe('Scenario Pattern Generator - Mock 模式', () => {
  let testTree: TagTree
  let mockClient: any

  beforeAll(() => {
    testTree = loadTestTagTree()
    mockClient = createMockClient()
  })

  it('mock 应基于 Plan 生成场景模式列表', async () => {
    const plan = buildTestPlan('生成空调和导航相关场景')
    const { patterns, targetScenarioCount } = await generateScenarioPatterns(plan, testTree, mockClient)

    expect(Array.isArray(patterns)).toBe(true)
    expect(patterns.length).toBeGreaterThan(0)
    expect(targetScenarioCount).toBeGreaterThanOrEqual(patterns.length)

    patterns.forEach((p, i) => {
      expect(typeof p).toBe('string')
      expect(p.length).toBeGreaterThan(0)
      console.log(`  Mock Pattern ${i + 1}: ${p}`)
    })

    console.log(`\nMock 生成 ${patterns.length} 个场景模式`)
  }, 30000)

  it('mock patterns 应互不重复', async () => {
    const plan = buildTestPlan('生成涉及不同功能的场景')
    const { patterns } = await generateScenarioPatterns(plan, testTree, mockClient)

    expect(patterns.length).toBeGreaterThanOrEqual(3)
    const uniquePatterns = new Set(patterns)
    expect(uniquePatterns.size).toBe(patterns.length)
  }, 30000)
})

// ═══════════════════════════════════════════════════════════════════════════
// Real LLM 模式测试
// ═══════════════════════════════════════════════════════════════════════════

describeRealLLM('Scenario Pattern Generator - Real LLM 模式', () => {
  let testTree: TagTree
  let client: OpenAI

  beforeAll(() => {
    testTree = loadTestTagTree()
    client = createClient()
  })

  it('real 应基于 Plan 生成场景模式列表', async () => {
    const plan = buildTestPlan('生成空调和导航相关场景')
    const { patterns, targetScenarioCount } = await generateScenarioPatterns(plan, testTree, client)

    expect(Array.isArray(patterns)).toBe(true)
    expect(patterns.length).toBeGreaterThan(0)
    expect(targetScenarioCount).toBeGreaterThanOrEqual(patterns.length)

    patterns.forEach((p, i) => {
      expect(typeof p).toBe('string')
      expect(p.length).toBeGreaterThan(0)
      console.log(`  Real Pattern ${i + 1}: ${p}`)
    })

    console.log(`\nReal 生成 ${patterns.length} 个场景模式`)
  }, 120000)

  it('real patterns 应覆盖多种复杂度', async () => {
    const plan = buildTestPlan('生成涉及不同功能的车载助手场景')
    const { patterns } = await generateScenarioPatterns(plan, testTree, client)

    expect(patterns.length).toBeGreaterThanOrEqual(3)
    const uniquePatterns = new Set(patterns)
    expect(uniquePatterns.size).toBe(patterns.length)

    console.log(`\nReal 生成 ${patterns.length} 个不重复的场景模式`)
  }, 120000)
})
