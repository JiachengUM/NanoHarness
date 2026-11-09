/**
 * 端到端调试测试：Query → Plan → 场景生成 → 用例生成
 *
 * 设计目标：
 * 1. 方便随时换 query 调试，观察完整链路的中间产物
 * 2. 打印关键中间产物信息（中文），便于人工审查
 * 3. 单独成文件，不影响其他测试
 * 4. 跑完整的真实 Plan，不做 pattern 数裁剪（慢但完整）
 *
 * 双模式：
 * - Mock 模式（默认）：快速验证链路代码逻辑
 * - Real LLM 模式（RUN_REAL_LLM=true）：真实跑通功能
 *
 * 运行命令：
 *   pnpm test tests/e2e-debug.test.ts          # Mock
 *   pnpm test:real tests/e2e-debug.test.ts     # Real LLM
 */

import { it, expect, beforeAll } from 'vitest'
import { generateScenarios, generateCasesFromScenarios, TagTree } from '../src'
import { generateScenarioPlan } from '../src/generation/scenario-planner.js'
import { generateScenarioPatterns } from '../src/generation/scenario-pattern-generator.js'
import {
  loadTestTagTree,
  describeRealLLM,
  describeMock,
  createMockClient,
  buildMockPatterns,
} from './test-utils'
import { createClient } from '@eval-platform/llm'
import type { OpenAI } from '@eval-platform/llm'
import type { ScenarioPlan } from '@eval-platform/database/models/scenario-plan'
import type { Scenario } from '@eval-platform/database/models/scenario'
import type { CaseWithScenario } from '@eval-platform/database'

// ═══════════════════════════════════════════════════════════════════════════
// 调试参数（随时修改）
// ═══════════════════════════════════════════════════════════════════════════

/** 测试用的 query（换这个就能调试不同需求） */
const QUERY = '生成空调温度调节和导航到常用地点的交互场景'

/** 每个场景生成几个用例 */
const CASES_PER_SCENARIO = 2

/** 阶段 2 最大迭代次数 */
const MAX_ITERATIONS = 3

/** 初始批次大小 */
const INITIAL_BATCH_SIZE = 3

/** 审核-修复最大轮次（每批次内部） */
const MAX_REFINE_ROUNDS = 1

// ═══════════════════════════════════════════════════════════════════════════
// 超时设置
// ═══════════════════════════════════════════════════════════════════════════

const E2E_TIMEOUT = 5400000  // 90 分钟（Real LLM）
const MOCK_E2E_TIMEOUT = 120000  // 2 分钟（Mock）

// ═══════════════════════════════════════════════════════════════════════════
// 公共工具
// ═══════════════════════════════════════════════════════════════════════════

function logUserQueryLists(cases: CaseWithScenario[]) {
  cases.forEach((c, i) => {
    console.log(`\n    ── 用例 ${i + 1} ──────────────────────`)
    console.log(`    用例 ID: ${c.case_id}`)
    console.log(`    来源场景: ${c.source_scenario_name}`)
    console.log(`    标签: ${c.tags?.join('、') || '无'}`)

    console.log(`    用户查询轮次: ${c.user_query_lists.length} 轮`)
    c.user_query_lists.forEach((turn, turnIdx) => {
      console.log(`      轮次 ${turnIdx + 1}:`)
      const messages = Array.isArray(turn) ? turn : turn.user_query_list
      messages.forEach((q, qIdx) => {
        console.log(`        查询 ${qIdx + 1} [${q.role || 'user'}]: ${q.content}`)
      })
      if (!Array.isArray(turn) && (turn.mock_time || Object.keys(turn.mock_info || {}).length > 0)) {
        if (turn.mock_time) console.log(`        mock_time: ${turn.mock_time}`)
        if (turn.mock_info && Object.keys(turn.mock_info).length > 0) {
          console.log(`        mock_info: ${JSON.stringify(turn.mock_info)}`)
        }
      }
    })

    if (c.expected_script) {
      if (Array.isArray(c.expected_script)) {
        console.log(`    期望脚本: ${c.expected_script.length} 步`)
        c.expected_script.forEach((step, stepIdx) => {
          const stepStr = JSON.stringify(step)
          console.log(`      步骤 ${stepIdx + 1}: ${stepStr.slice(0, 150)}${stepStr.length > 150 ? '...' : ''}`)
        })
      } else {
        const scriptStr = String(c.expected_script)
        console.log(`    期望脚本: ${scriptStr.slice(0, 200)}${scriptStr.length > 200 ? '...' : ''}`)
      }
    }

    console.log(`    自然语言断言: ${c.nl_assertion.length} 条`)
    c.nl_assertion.forEach((assertion, aIdx) => {
      console.log(`      断言 ${aIdx + 1}: ${assertion}`)
    })

    console.log(`    用例描述: ${c.case_description}`)

    if (c.context_config) {
      const configStr = JSON.stringify(c.context_config)
      console.log(`    上下文配置: ${configStr.slice(0, 200)}${configStr.length > 200 ? '...' : ''}`)
    }
  })
}

async function runE2ePipeline(options: {
  query: string
  testTree: TagTree
  client: OpenAI
  patterns?: string[]
  maxIterations: number
  timeoutLabel: string
}) {
  const { query, testTree, client, patterns: providedPatterns, maxIterations, timeoutLabel } = options

  console.log(`\n${'═'.repeat(80)}`)
  console.log(`  端到端调试开始 (${timeoutLabel})`)
  console.log(`  Query: ${query}`)
  console.log(`  每场景用例数: ${CASES_PER_SCENARIO}`)
  console.log(`  阶段 2 最大迭代: ${maxIterations}`)
  console.log(`${'═'.repeat(80)}\n`)

  // 步骤 0: 生成 Plan
  console.log('┌──────────────────────────────────────────┐')
  console.log('│  步骤 0: 生成 Plan                        │')
  console.log('└──────────────────────────────────────────┘')

  const planData = await generateScenarioPlan(query, testTree, client)
  const plan: ScenarioPlan = {
    ...planData,
    task_id: `debug-task-${Date.now()}`,
    generation_task_run_id: `debug-run-${Date.now()}`,
    tag_tree_name: 'test-tree',
    status: 'confirmed',
  }

  console.log(`    任务描述: ${plan.task_description}`)
  console.log(`    目标标签数: ${plan.target_tags.length}`)
  console.log(`    需求理解: ${plan.interpretation_notes}`)

  // 步骤 0.5: Patterns
  let patterns = providedPatterns
  let targetScenarioCount: number
  if (patterns) {
    targetScenarioCount = Math.max(10, patterns.length, plan.target_tags.length * 2)
    console.log(`\n  [使用预设 Patterns] ${patterns.length} 个，目标场景数（参考下限）: ${targetScenarioCount}`)
  } else {
    const patternResult = await generateScenarioPatterns(plan, testTree, client)
    patterns = patternResult.patterns
    targetScenarioCount = patternResult.targetScenarioCount
    console.log(`\n  [生成 Patterns] ${patterns.length} 个，目标场景数（参考下限）: ${targetScenarioCount}`)
    patterns.forEach((p, i) => console.log(`    ${i + 1}. ${p}`))
  }

  // 步骤 1: 场景生成
  console.log('\n┌──────────────────────────────────────────┐')
  console.log('│  步骤 1: 场景生成                          │')
  console.log('└──────────────────────────────────────────┘\n')

  const allGeneratedScenarios: Scenario[] = []
  const scenarioResult = await generateScenarios(query, testTree, client, {
    plan,
    patterns,
    maxIterations,
    initialBatchSize: INITIAL_BATCH_SIZE,
    maxRefineRoundsPerBatch: MAX_REFINE_ROUNDS,
    onProgress: (info) => {
      const phaseLabel = info.phase === 'pattern_sweep' ? '阶段1-巡游' : '阶段2-深化'
      const patternLabel = info.currentPattern ? ` [${info.currentPattern}]` : ''
      const satisfiedLabel = info.satisfied ? ' ✅' : ''
      console.log(`  [进度] ${phaseLabel} 迭代${info.iteration} | 场景数: ${info.totalScenarios}/${info.targetScenarioCount} | 覆盖率: ${info.coveragePercentage}% | 进度: ${info.progressPercentage}%${patternLabel}${satisfiedLabel}`)
    },
    onScenarioGenerated: async (scenario) => {
      allGeneratedScenarios.push(scenario)
      console.log(`  [新场景 ${allGeneratedScenarios.length}] ${scenario.scenario_name} (${scenario.tags.join('、')})`)
    },
  })

  const scenarios = scenarioResult.scenarios
  console.log(`\n  [场景生成完成] ${scenarioResult.actualCount}/${scenarioResult.targetCount}，覆盖率 ${scenarioResult.finalCoveragePercentage}%`)

  expect(scenarios.length).toBeGreaterThan(0)
  expect(scenarioResult.plan.task_id).toBe(plan.task_id)

  // 步骤 2: 用例生成
  console.log('\n┌──────────────────────────────────────────┐')
  console.log(`│  步骤 2: 用例生成（每场景 ${CASES_PER_SCENARIO} 个）        │`)
  console.log('└──────────────────────────────────────────┘\n')

  const cases = await generateCasesFromScenarios(scenarios, CASES_PER_SCENARIO, client, 'e2e-debug', testTree)
  console.log(`\n  [用例生成完成] ${cases.length} 个用例`)
  logUserQueryLists(cases)

  expect(cases.length).toBeGreaterThan(0)
  expect(cases[0].user_query_lists.length).toBeGreaterThan(0)
  expect(cases[0].nl_assertion.length).toBeGreaterThan(0)

  const scenarioIds = new Set(scenarios.map(s => s.scenario_id))
  for (const c of cases) {
    expect(scenarioIds.has(c.source_scenario_id)).toBe(true)
  }

  // 步骤 3: 汇总
  console.log('\n┌──────────────────────────────────────────┐')
  console.log('│  步骤 3: 端到端汇总                        │')
  console.log('└──────────────────────────────────────────┘')
  console.log(`\n  [链路完整性]`)
  console.log(`    Query → Plan: ✓`)
  console.log(`    Plan → 场景: ✓ (${scenarios.length} 个)`)
  console.log(`    场景 → 用例: ✓ (${cases.length} 个)`)
  console.log(`    用例 → 场景追溯: ✓ (全部可追溯)`)
  console.log(`\n${'═'.repeat(80)}`)
  console.log(`  端到端调试完成 ✓ (${timeoutLabel})`)
  console.log(`${'═'.repeat(80)}\n`)

  return { plan, patterns: patterns!, scenarioResult, scenarios, cases }
}

// ═══════════════════════════════════════════════════════════════════════════
// Mock 模式（默认运行，快速验证链路）
// ═══════════════════════════════════════════════════════════════════════════

describeMock('端到端调试：Query → Plan → 场景 → 用例（Mock）', () => {
  let testTree: TagTree
  let mockClient: ReturnType<typeof createMockClient>
  const mockPatterns = buildMockPatterns().slice(0, 3)

  beforeAll(() => {
    testTree = loadTestTagTree()
    mockClient = createMockClient({ defaultScenarioCount: 2, defaultAuditPass: true })
  })

  it('mock 完整链路：Query → Plan → 场景生成 → 用例生成', async () => {
    await runE2ePipeline({
      query: QUERY,
      testTree,
      client: mockClient,
      patterns: mockPatterns,
      maxIterations: 1,
      timeoutLabel: 'Mock',
    })
  }, MOCK_E2E_TIMEOUT)
})

// ═══════════════════════════════════════════════════════════════════════════
// Real LLM 模式（RUN_REAL_LLM=true 时运行）
// ═══════════════════════════════════════════════════════════════════════════

describeRealLLM('端到端调试：Query → Plan → 场景 → 用例', () => {
  let testTree: TagTree
  let client: OpenAI

  beforeAll(() => {
    testTree = loadTestTagTree()
    client = createClient()
  })

  it('完整链路：Query → Plan → 场景生成 → 用例生成', async () => {
    const { scenarioResult, scenarios, cases } = await runE2ePipeline({
      query: QUERY,
      testTree,
      client,
      maxIterations: MAX_ITERATIONS,
      timeoutLabel: 'Real LLM',
    })

    const coveredPatterns = Object.values(scenarioResult.patternCoverage).filter(c => c > 0).length
    const totalPatterns = Object.keys(scenarioResult.patternCoverage).length
    console.log(`\n  [质量指标] Pattern 覆盖: ${coveredPatterns}/${totalPatterns}，每场景平均用例: ${(cases.length / scenarios.length).toFixed(1)}`)
  }, E2E_TIMEOUT)
})
