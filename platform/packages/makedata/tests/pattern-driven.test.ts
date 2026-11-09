/**
 * Pattern 驱动场景生成逻辑的单元测试
 *
 * 不依赖真实 LLM 调用，验证：
 * 1. GenerationGuidance 类型包含 target_pattern 字段
 * 2. PatternCoverageInfo 接口正确
 * 3. analyzeRelevantTagCoverage 函数工作正常
 * 4. Plan 不包含 scenario_patterns
 * 5. database schema 中 GenerationGuidanceSchema 包含 target_pattern
 */

import { describe, it, expect, beforeAll } from 'vitest'
import { analyzeRelevantTagCoverage, type PatternCoverageInfo } from '../src/generation/scenario-judge.js'
import { GenerationGuidanceSchema, LLMJudgementOutputSchema } from '@eval-platform/database/models/scenario-judge'
import { generateScenarioPlan } from '../src/generation/scenario-planner.js'
import { TagTree } from '../src/core/tag-tree.js'
import { createClient } from '@eval-platform/llm'
import type { OpenAI } from '@eval-platform/llm'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'
import type { Scenario } from '@eval-platform/database/models/scenario'
import { loadTestTagTree, createMockClient, describeRealLLM } from './test-utils'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// ═══════════════════════════════════════════════════════════════════════════
// 纯逻辑测试（不依赖 LLM）
// ═══════════════════════════════════════════════════════════════════════════

describe('Pattern 驱动逻辑 - 纯单元测试', () => {
  describe('GenerationGuidance 类型与 Schema', () => {
    it('GenerationGuidanceSchema 应包含 target_pattern 字段', () => {
      // 解析 schema 的 shape
      const shape = GenerationGuidanceSchema.shape
      expect(shape).toHaveProperty('target_pattern')
      // target_pattern 应为可选 + nullable
      const targetPatternSchema = shape.target_pattern
      expect(targetPatternSchema).toBeDefined()
    })

    it('LLMJudgementOutputSchema 的 refinement_direction 不应包含 target_pattern（已改为程序化选择）', () => {
      const refinementDir = LLMJudgementOutputSchema.shape.judgement.shape.refinement_direction
      expect(refinementDir).toBeDefined()
      // refinement_direction 是 nullable，unwrap 后检查 shape
      const innerShape = (refinementDir as any)._def?.innerType?.shape || (refinementDir as any).shape
      // target_pattern 已从 LLM Schema 移除，改由代码程序化选择
      expect(innerShape).not.toHaveProperty('target_pattern')
    })

    it('应能构造带 target_pattern 的 GenerationGuidance', () => {
      const guidance = {
        focus_tags: ['温度增减调节'],
        avoid_tags: [],
        scenario_types: ['单轮直达'],
        guidance: '聚焦单轮直达',
        suggested_count: 5,
        target_pattern: '单轮直达空调控制场景',
      }

      const parsed = GenerationGuidanceSchema.parse(guidance)
      expect(parsed.target_pattern).toBe('单轮直达空调控制场景')
    })

    it('应能构造不带 target_pattern 的 GenerationGuidance（向后兼容）', () => {
      const guidance = {
        focus_tags: ['温度增减调节'],
        avoid_tags: [],
        scenario_types: [],
        guidance: '继续生成',
      }

      const parsed = GenerationGuidanceSchema.parse(guidance)
      expect(parsed.target_pattern).toBeUndefined()
    })

    it('target_pattern 应支持 null 值', () => {
      const guidance = {
        focus_tags: [],
        avoid_tags: [],
        scenario_types: [],
        guidance: '测试',
        target_pattern: null,
      }

      const parsed = GenerationGuidanceSchema.parse(guidance)
      expect(parsed.target_pattern).toBeNull()
    })
  })

  describe('PatternCoverageInfo 接口', () => {
    it('应能正确构造 PatternCoverageInfo', () => {
      const info: PatternCoverageInfo = {
        scenario_patterns: ['pattern-A', 'pattern-B', 'pattern-C'],
        patternScenarioCount: new Map([
          ['pattern-A', 3],
          ['pattern-B', 0],
          ['pattern-C', 1],
        ]),
      }

      expect(info.scenario_patterns.length).toBe(3)
      expect(info.patternScenarioCount.get('pattern-A')).toBe(3)
      expect(info.patternScenarioCount.get('pattern-B')).toBe(0)
      expect(info.patternScenarioCount.get('pattern-C')).toBe(1)
    })

    it('应能正确识别 pattern 缺口', () => {
      const info: PatternCoverageInfo = {
        scenario_patterns: ['A', 'B', 'C', 'D'],
        patternScenarioCount: new Map([
          ['A', 2],
          ['B', 0],  // 缺口
          ['C', 1],
          ['D', 0],  // 缺口
        ]),
      }

      const gaps = info.scenario_patterns.filter(p => (info.patternScenarioCount.get(p) || 0) === 0)
      expect(gaps).toEqual(['B', 'D'])
    })

    it('应能正确识别最缺的 pattern', () => {
      const info: PatternCoverageInfo = {
        scenario_patterns: ['A', 'B', 'C'],
        patternScenarioCount: new Map([
          ['A', 5],
          ['B', 1],  // 最缺
          ['C', 3],
        ]),
      }

      const sorted = [...info.scenario_patterns].sort((a, b) =>
        (info.patternScenarioCount.get(a) || 0) - (info.patternScenarioCount.get(b) || 0)
      )
      expect(sorted[0]).toBe('B')
    })

    it('应能正确判断是否所有 pattern 都已覆盖', () => {
      const allCovered: PatternCoverageInfo = {
        scenario_patterns: ['A', 'B'],
        patternScenarioCount: new Map([['A', 2], ['B', 1]]),
      }
      const allCoveredCheck = [...allCovered.patternScenarioCount.values()].every(c => c >= 1)
      expect(allCoveredCheck).toBe(true)

      const hasGap: PatternCoverageInfo = {
        scenario_patterns: ['A', 'B'],
        patternScenarioCount: new Map([['A', 2], ['B', 0]]),
      }
      const hasGapCheck = [...hasGap.patternScenarioCount.values()].every(c => c >= 1)
      expect(hasGapCheck).toBe(false)
    })
  })

  describe('analyzeRelevantTagCoverage', () => {
    const relevantTags = ['温度增减调节', '精确地点直达', '常用地点记忆']

    it('应正确统计空场景列表', () => {
      const stats = analyzeRelevantTagCoverage([], relevantTags)
      expect(stats.coveredTags.size).toBe(0)
      expect(stats.uncoveredTags).toEqual(relevantTags)
      expect(stats.avgTagsPerScenario).toBe(0)
    })

    it('应正确统计部分覆盖', () => {
      const scenarios: Scenario[] = [
        {
          scenario_id: 's1',
          scenario_name: '场景1',
          description: '描述',
          tags: ['温度增减调节', '其他无关标签'],
        },
        {
          scenario_id: 's2',
          scenario_name: '场景2',
          description: '描述',
          tags: ['精确地点直达'],
        },
      ]

      const stats = analyzeRelevantTagCoverage(scenarios, relevantTags)
      expect(stats.coveredTags.size).toBe(2)
      expect(stats.coveredTags.has('温度增减调节')).toBe(true)
      expect(stats.coveredTags.has('精确地点直达')).toBe(true)
      expect(stats.uncoveredTags).toEqual(['常用地点记忆'])
      expect(stats.tagCoverage['温度增减调节']).toBe(1)
      expect(stats.tagCoverage['精确地点直达']).toBe(1)
    })

    it('应正确统计多次覆盖', () => {
      const scenarios: Scenario[] = [
        { scenario_id: 's1', scenario_name: 'n1', description: 'd', tags: ['温度增减调节'] },
        { scenario_id: 's2', scenario_name: 'n2', description: 'd', tags: ['温度增减调节', '精确地点直达'] },
        { scenario_id: 's3', scenario_name: 'n3', description: 'd', tags: ['温度增减调节'] },
      ]

      const stats = analyzeRelevantTagCoverage(scenarios, relevantTags)
      expect(stats.tagCoverage['温度增减调节']).toBe(3)
      expect(stats.tagCoverage['精确地点直达']).toBe(1)
      expect(stats.avgTagsPerScenario).toBeCloseTo((3 + 1) / 3, 2)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Plan 校验测试（Mock 模式 - 快速验证代码逻辑）
// ═══════════════════════════════════════════════════════════════════════════

describe('Plan 校验 - Mock 模式', () => {
  let testTree: TagTree
  let mockClient: any

  beforeAll(() => {
    testTree = loadTestTagTree()
    mockClient = createMockClient()
  })

  it('Plan 不应包含 scenario_patterns（Mock 验证）', async () => {
    const query = '生成车载助手日常交互场景'
    const plan = await generateScenarioPlan(query, testTree, mockClient)

    console.log(`  target_tags.length: ${plan.target_tags.length}`)

    // 核心不变量：Plan 不再包含 scenario_patterns
    expect((plan as any).scenario_patterns).toBeUndefined()
  }, 30000)
})

// ═══════════════════════════════════════════════════════════════════════════
// Plan 校验测试（Real LLM 模式 - 真实跑通功能）
// ═══════════════════════════════════════════════════════════════════════════

describeRealLLM('Plan 校验 - Real LLM 模式', () => {
  let testTree: TagTree
  let client: OpenAI

  beforeAll(() => {
    testTree = loadTestTagTree()
    client = createClient()
  })

  it('Plan 不应包含 scenario_patterns（Real LLM 验证）', async () => {
    const query = '生成车载助手日常交互场景'
    const plan = await generateScenarioPlan(query, testTree, client)

    console.log(`  target_tags.length: ${plan.target_tags.length}`)

    // 核心不变量：Plan 不再包含 scenario_patterns
    expect((plan as any).scenario_patterns).toBeUndefined()
  }, 120000)
})
