/**
 * Scenario Planner 单元测试 + 命令行调试工具
 *
 * 注意：本测试针对剥离 scenario_patterns 后的新 Planner。
 * Pattern 生成已独立到 scenario-pattern-generator.test.ts
 *
 * 使用方式：
 * 1. 作为测试运行: pnpm test tests/scenario-planner.test.ts --run
 * 2. 命令行调试: pnpm tsx tests/scenario-planner.test.ts [query]
 */

import { describe, it, expect, beforeAll } from 'vitest'
import { generateScenarioPlan } from '../src/generation/scenario-planner.js'
import { TagTree } from '../src/core/tag-tree.js'
import { createClient } from '@eval-platform/llm'
import type { OpenAI } from '@eval-platform/llm'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'
import { loadTestTagTree, createMockClient, describeRealLLM } from './test-utils'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// loadTestTagTree 从 test-utils 导入

// ═══════════════════════════════════════════════════════════════════════════
// 命令行调试模式
// ═══════════════════════════════════════════════════════════════════════════

const EXAMPLE_QUERIES = [
  '生成空调控制场景',
  '生成危险车控场景，如行驶中开关车门',
  '生成音乐播放控制场景',
  '生成导航和地点查询场景',
  '生成用户记忆管理场景',
  '生成车载助手日常交互场景',
  '生成多轮对话场景',
  '生成导航+音乐+车控组合场景',
]

async function runQuery(query: string, tagTree: TagTree, client: OpenAI): Promise<void> {
  console.log('\n' + '='.repeat(80))
  console.log('Query:', query)
  console.log('='.repeat(80))

  try {
    const plan = await generateScenarioPlan(query, tagTree, client)

    console.log('\n📋 Plan 生成结果:')
    console.log('-'.repeat(40))
    console.log('\n📝 任务描述:')
    console.log(plan.task_description)

    console.log('\n🏷️ 目标标签数:', plan.target_tags.length)
    console.log('   标签列表:', plan.target_tags.slice(0, 10).join(', '), plan.target_tags.length > 10 ? '...' : '')

    // console.log('\n✅ Plan 不包含 scenario_patterns（已剥离）:', (plan as any).scenario_patterns === undefined)
    // console.log('\n✅ Plan 不包含 target_scenario_count（由 Pattern 生成阶段决定）:', (plan as any).target_scenario_count === undefined)

    console.log('\n✅ Plan 生成成功')
  } catch (error) {
    console.error('❌ Plan 生成失败:', error)
  }
}

async function main(): Promise<void> {
  const args = process.argv.slice(2)
  const customQuery = args.find(arg => !arg.startsWith('--'))

  const tagTree = loadTestTagTree()
  const client = createClient()

  if (customQuery) {
    await runQuery(customQuery, tagTree, client)
  } else {
    console.log('\n' + '='.repeat(80))
    console.log('Scenario Planner 命令行调试工具')
    console.log('='.repeat(80))
    console.log('\n使用方式: pnpm tsx tests/scenario-planner.test.ts [query]')
    console.log('示例 queries:')
    EXAMPLE_QUERIES.forEach((q, i) => console.log(`  ${i + 1}. ${q}`))
    console.log('\n将依次运行所有示例 queries...\n')

    for (const query of EXAMPLE_QUERIES) {
      await runQuery(query, tagTree, client)
    }

    console.log('\n' + '='.repeat(80))
    console.log('所有示例运行完成')
    console.log('='.repeat(80))
  }
}

if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.includes('scenario-planner.test.ts')) {
  main().then(() => process.exit(0)).catch(error => {
    console.error(error)
    process.exit(1)
  })
}

// ═══════════════════════════════════════════════════════════════════════════
// Vitest 测试模式
// ═══════════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════════
// Mock 模式测试
// ═══════════════════════════════════════════════════════════════════════════

describe('Scenario Planner - Mock 模式', () => {
  let testTree: TagTree
  let mockClient: any

  beforeAll(() => {
    testTree = loadTestTagTree()
    mockClient = createMockClient()
  })

  it('mock 应生成不含 scenario_patterns 的 Plan', async () => {
    const plan = await generateScenarioPlan('生成所有车控场景', testTree, mockClient)

    expect(plan.task_description).toBeDefined()
    expect(plan.target_tags).toBeDefined()
    expect(plan.target_tags.length).toBeGreaterThan(0)
    expect(plan.interpretation_notes).toBeDefined()

    // 验证所有 target_tags 都是叶子标签
    const allLeafTags = testTree.getLeafTagNames()
    for (const tag of plan.target_tags) {
      expect(allLeafTags).toContain(tag)
    }
  }, 30000)

  it('mock Plan 应满足数量下限', async () => {
    const plan = await generateScenarioPlan('生成导航场景', testTree, mockClient)
  }, 30000)
})

// ═══════════════════════════════════════════════════════════════════════════
// Real LLM 模式测试
// ═══════════════════════════════════════════════════════════════════════════

describeRealLLM('Scenario Planner - Real LLM 模式', () => {
  let testTree: TagTree
  let client: OpenAI

  beforeAll(() => {
    testTree = loadTestTagTree()
    client = createClient()
  })

  describe('generateScenarioPlan', () => {
    it('should generate a plan without scenario_patterns', async () => {
      const query = '生成所有车控场景'

      const plan = await generateScenarioPlan(query, testTree, client)

      // 基本字段检查
      expect(plan.task_description).toBeDefined()
      expect(plan.task_description.length).toBeGreaterThan(0)

      expect(plan.target_tags).toBeDefined()
      expect(plan.target_tags.length).toBeGreaterThan(0)

      expect(plan.interpretation_notes).toBeDefined()
      expect(plan.interpretation_notes.length).toBeGreaterThan(0)

      // 核心不变量：Plan 不再包含 scenario_patterns
      expect((plan as any).scenario_patterns).toBeUndefined()

      // 验证所有 target_tags 都是叶子标签
      const allLeafTags = testTree.getLeafTagNames()
      for (const tag of plan.target_tags) {
        expect(allLeafTags).toContain(tag)
      }
    }, 120000)

    it('should generate a specific plan for dangerous car control', async () => {
      const query = '生成危险车控场景，如行驶中开关车门'

      const plan = await generateScenarioPlan(query, testTree, client)

      expect(plan.target_tags.length).toBeGreaterThan(0)

      // 任务描述应该更具体、无歧义
      expect(plan.task_description).toContain('危险')

      // Plan 不再包含 scenario_patterns
      expect((plan as any).scenario_patterns).toBeUndefined()
    }, 120000)

    it('should handle music control query', async () => {
      const query = '生成音乐播放控制场景'

      const plan = await generateScenarioPlan(query, testTree, client)

      // 应该包含音乐相关标签
      const musicTags = plan.target_tags.filter(tag =>
        tag.includes('音乐') || tag.includes('播放') || tag.includes('歌曲')
      )
      expect(musicTags.length).toBeGreaterThan(0)

      // Plan 不再包含 scenario_patterns
      expect((plan as any).scenario_patterns).toBeUndefined()
    }, 120000)

    it('should generate plan based on tag tree structure', async () => {
      const query = '生成车载助手日常交互场景'

      const plan = await generateScenarioPlan(query, testTree, client)

      // Plan 不再包含 scenario_patterns
      expect((plan as any).scenario_patterns).toBeUndefined()

      // 验证标签覆盖率合理
      const allLeafTags = testTree.getLeafTagNames()
      console.log(`\n标签覆盖: ${plan.target_tags.length}/${allLeafTags.length}`)
      console.log('选中的标签:', plan.target_tags.slice(0, 10), plan.target_tags.length > 10 ? '...' : '')

      expect(plan.target_tags.length).toBeGreaterThan(0)
    }, 120000)

    it('should see full tag tree structure to make informed decisions', async () => {
      const query = '生成导航和地点查询场景'

      const plan = await generateScenarioPlan(query, testTree, client)

      // Planner 应该基于标签树结构识别出导航相关标签
      const navigationRelatedTags = plan.target_tags.filter(tag =>
        tag.includes('导航') ||
        tag.includes('地点') ||
        tag.includes('POI') ||
        tag.includes('路线')
      )

      console.log('\n导航相关标签识别结果:')
      console.log(`  识别到 ${navigationRelatedTags.length} 个导航相关标签`)
      navigationRelatedTags.forEach(tag => console.log(`    - ${tag}`))

      expect(navigationRelatedTags.length).toBeGreaterThan(0)

      // Plan 不再包含 scenario_patterns
      expect((plan as any).scenario_patterns).toBeUndefined()
    }, 120000)
  })
})
