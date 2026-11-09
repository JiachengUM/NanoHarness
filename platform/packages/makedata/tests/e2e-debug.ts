/**
 * 端到端调试脚本：Query → Plan → 场景生成 → 用例生成
 *
 * 设计目标：
 * 1. 可以直接用 node/tsx 运行，不依赖 vitest
 * 2. 方便随时换 query 调试，观察完整链路的中间产物
 * 3. 打印关键中间产物信息（中文），便于人工审查
 * 4. 支持 pattern 裁剪加速调试
 * 5. 保存产物到 JSON 文件供批量查看
 *
 * 使用方式：
 * - 修改下方 QUERY 变量即可换 query 调试
 * - 修改 MAX_PATTERNS 控制保留几个 pattern（0=不裁剪）
 * - 修改 CASES_PER_SCENARIO 控制每个场景生成几个用例
 *
 * 运行命令：
 *   pnpm e2e
 *   或
 *   npx tsx tests/e2e-debug.ts
 */

import { generateScenarios, generateAndRefineCases } from '../src/index.ts'
import { generateScenarioPlan } from '../src/generation/scenario-planner.ts'
import { generateScenarioPatterns } from '../src/generation/scenario-pattern-generator.ts'
import { auditCases, fixCasesByAudit } from '../src/audit/index.ts'
import { TagTree } from '../src/core/tag-tree.ts'
import { createClient } from '@eval-platform/llm'
import type { OpenAI } from '@eval-platform/llm'
import type { ScenarioPlan } from '@eval-platform/database/models/scenario-plan'
import type { Scenario } from '@eval-platform/database/models/scenario'
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

function loadTestTagTree(): TagTree {
  const treePath = join(__dirname, '../examples/data/vehicle-tag-tree.json')
  const treeData = JSON.parse(readFileSync(treePath, 'utf-8'))
  return TagTree.fromJSON(treeData)
}

// ═══════════════════════════════════════════════════════════════════════════
// 调试参数（随时修改）
// ═══════════════════════════════════════════════════════════════════════════

/** 测试用的 query（换这个就能调试不同需求） */
const QUERY = '我现在想展现车载助手的多任务并行能力以及用户可以随时插话让助手做新的事情或者就是闲聊，取消正在做的事情，以及询问当前正在做的事情的情景。尽量生成足够复杂，足够体现用户犹豫不决，优柔寡断，随意插话，不太有耐心的那种对话情景，以便深度考验助手应对这种用户的能力。'

/** 是否跳过用例生成（只调试场景生成时设为 true，加速） */
const SKIP_CASE_GENERATION = false

/** 每个场景生成几个用例 */
const CASES_PER_SCENARIO = 5

/** 保留的 pattern 数量上限（裁剪加速调试，设为 0 表示不裁剪） */
const MAX_PATTERNS = 0

/** 阶段 2 最大迭代次数 */
const MAX_ITERATIONS = 3

/** 初始批次大小 */
const INITIAL_BATCH_SIZE = 5

/** 审核-修复最大轮次（每批次内部） */
const MAX_REFINE_ROUNDS = 2

// ═══════════════════════════════════════════════════════════════════════════
// 主函数
// ═══════════════════════════════════════════════════════════════════════════

async function main() {
  console.log(`\n${'═'.repeat(80)}`)
  console.log(`  端到端调试开始`)
  console.log(`  Query: ${QUERY}`)
  console.log(`  每场景用例数: ${CASES_PER_SCENARIO}`)
  console.log(`  Pattern 上限: ${MAX_PATTERNS === 0 ? '不裁剪' : `${MAX_PATTERNS} 个`}`)
  console.log(`  阶段 2 最大迭代: ${MAX_ITERATIONS}`)
  console.log(`${'═'.repeat(80)}\n`)

  const testTree = loadTestTagTree()
  const client = createClient()

  const tScriptStart = Date.now()

  // ─────────────────────────────────────────────────────────────────
  // 步骤 0: 生成 Plan
  // ─────────────────────────────────────────────────────────────────
  console.log('┌──────────────────────────────────────────┐')
  console.log('│  步骤 0: 生成 Plan                        │')
  console.log('└──────────────────────────────────────────┘')
  console.log(`\n  原始 Query: ${QUERY}`)

  const tPlanStart = Date.now()
  const planData = await generateScenarioPlan(QUERY, testTree, client)
  const tPlanDone = Date.now()
  console.log(`  ⏱️  Plan 生成耗时: ${((tPlanDone - tPlanStart) / 1000).toFixed(1)}s`)

  console.log(`\n  [Plan 原始信息]`)
  console.log(`    任务描述: ${planData.task_description}`)
  console.log(`    目标场景数: 待 Pattern 生成后确定`)
  console.log(`    目标标签数: ${planData.target_tags.length}`)
  console.log(`    目标标签: ${planData.target_tags.join('、')}`)
  console.log(`    需求理解注解: ${planData.interpretation_notes}`)

  const plan: ScenarioPlan = {
    ...planData,
    task_id: `debug-task-${Date.now()}`,
    tag_tree_name: 'test-tree',
    status: 'confirmed',
  }

  // 独立生成 Patterns
  console.log(`\n  [生成场景模式列表...]`)
  const tPatternStart = Date.now()
  const { patterns: generatedPatterns, targetScenarioCount } = await generateScenarioPatterns(plan, testTree, client)
  const tPatternDone = Date.now()
  console.log(`  ⏱️  Pattern 生成耗时: ${((tPatternDone - tPatternStart) / 1000).toFixed(1)}s`)
  let patterns = generatedPatterns
  console.log(`\n  [场景模式列表]`)
  patterns.forEach((p: string, i: number) => {
    console.log(`    ${i + 1}. ${p}`)
  })

  console.log(`\n  [最终 Plan]`)
  console.log(`    目标场景数（参考下限）: ${targetScenarioCount}`)
  console.log(`    目标标签数: ${plan.target_tags.length}`)
  console.log(`    场景模式数: ${patterns.length}`)

  // 裁剪 patterns 加速调试（只保留前 MAX_PATTERNS 个）
  if (MAX_PATTERNS > 0 && patterns.length > MAX_PATTERNS) {
    const originalCount = patterns.length
    patterns = patterns.slice(0, MAX_PATTERNS)
    console.log(`    [裁剪] patterns: ${originalCount} → ${MAX_PATTERNS}（加速调试）`)
  }

  // 估算预计耗时
  const estimatedSeconds = 60 + patterns.length * 90 + 300 + 300
  console.log(`\n  [预计耗时] 基于 ${patterns.length} 个 pattern，约 ${Math.round(estimatedSeconds / 60)} 分钟`)

  // ─────────────────────────────────────────────────────────────────
  // 步骤 1: 场景生成（Pattern 巡游 + Judge 驱动）
  // ─────────────────────────────────────────────────────────────────
  console.log('\n┌──────────────────────────────────────────┐')
  console.log('│  步骤 1: 场景生成                          │')
  console.log('│  （阶段 1: Pattern 巡游 + 阶段 2: Judge）  │')
  console.log('└──────────────────────────────────────────┘\n')

  const allGeneratedScenarios: Scenario[] = []

  const tScenarioGenStart = Date.now()
  let tFirstScenario: number | null = null

  const scenarioResult = await generateScenarios(QUERY, testTree, client, {
    plan,
    patterns,
    maxIterations: MAX_ITERATIONS,
    initialBatchSize: INITIAL_BATCH_SIZE,
    maxRefineRoundsPerBatch: MAX_REFINE_ROUNDS,
    onProgress: (info) => {
      const phaseLabel = info.phase === 'pattern_sweep' ? '阶段1-巡游' : '阶段2-深化'
      const patternLabel = info.currentPattern ? ` [${info.currentPattern}]` : ''
      const satisfiedLabel = info.satisfied ? ' ✅' : ''
      console.log(`  [进度] ${phaseLabel} 迭代${info.iteration} | 场景数: ${info.totalScenarios}/${info.targetScenarioCount} | 覆盖率: ${info.coveragePercentage}% | 进度: ${info.progressPercentage}%${patternLabel}${satisfiedLabel}`)
      console.log(`         ${info.currentStep}`)
    },
    onScenarioGenerated: async (scenario, info) => {
      if (tFirstScenario === null) {
        tFirstScenario = Date.now()
        const sincePlan = ((tFirstScenario - tPatternDone) / 1000).toFixed(1)
        const sinceStart = ((tFirstScenario - tScriptStart) / 1000).toFixed(1)
        console.log(`\n  ⏱️  ===== 首个流式场景出现 =====`)
        console.log(`  ⏱️  Plan完成 → 首个场景: ${sincePlan}s`)
        console.log(`  ⏱️  脚本启动 → 首个场景: ${sinceStart}s`)
        console.log(`  ⏱️  =============================\n`)
      }
      allGeneratedScenarios.push(scenario)
      const provisionalLabel = info.isProvisional ? ' (临时)' : ' (最终)'
      console.log(`\n  [新场景 ${allGeneratedScenarios.length}]${provisionalLabel} ─────────────────────`)
      console.log(`    ID: ${scenario.scenario_id}`)
      console.log(`    名称: ${scenario.scenario_name}`)
      console.log(`    描述: ${scenario.description}`)
      console.log(`    标签: ${scenario.tags.join('、')}`)
      console.log(`    归属 Pattern: ${info.pattern}`)
      console.log(`    当前累计: ${info.totalScenarios} 个 | 覆盖率: ${info.coveragePercentage}%`)
    },
  })

  const scenarios = scenarioResult.scenarios

  console.log('\n┌──────────────────────────────────────────┐')
  console.log('│  步骤 1 完成：场景生成结果                 │')
  console.log('└──────────────────────────────────────────┘')
  console.log(`\n  [生成统计]`)
  console.log(`    目标场景数（下限）: ${scenarioResult.targetCount}`)
  console.log(`    实际生成（最终）: ${scenarioResult.actualCount}`)
  console.log(`    流式推送（临时）: ${allGeneratedScenarios.length}`)
  console.log(`    去重移除: ${allGeneratedScenarios.length - scenarioResult.actualCount} 个`)
  console.log(`    达成率: ${Math.round((scenarioResult.actualCount / scenarioResult.targetCount) * 100)}%`)
  console.log(`    标签覆盖率: ${scenarioResult.finalCoveragePercentage}%`)
  console.log(`    阶段 2 总迭代: ${scenarioResult.totalIterations} 轮`)
  console.log(`    是否满足需求: ${scenarioResult.satisfied ? '是 ✓' : '否'}`)

  console.log(`\n  [Pattern 覆盖统计]`)
  for (const [pattern, count] of Object.entries(scenarioResult.patternCoverage)) {
    const bar = '█'.repeat(Math.min(count, 20))
    console.log(`    ${pattern}: ${count} 个 ${bar}`)
  }
  const coveredPatterns = Object.values(scenarioResult.patternCoverage).filter(c => c > 0).length
  const totalPatterns = Object.keys(scenarioResult.patternCoverage).length
  console.log(`\n    Pattern 覆盖率: ${coveredPatterns}/${totalPatterns} (${Math.round((coveredPatterns / totalPatterns) * 100)}%)`)

  console.log(`\n  [全部场景列表]`)
  scenarios.forEach((s, i) => {
    console.log(`    ${i + 1}. [${s.scenario_id}] ${s.scenario_name}`)
    console.log(`       标签: ${s.tags.join('、')}`)
    console.log(`       描述: ${s.description}`)
  })

  // ─────────────────────────────────────────────────────────────────
  // 步骤 2: 用例生成（可跳过）
  // ─────────────────────────────────────────────────────────────────
  if (SKIP_CASE_GENERATION) {
    console.log('\n┌──────────────────────────────────────────┐')
    console.log('│  步骤 2: 用例生成（已跳过）                │')
    console.log('└──────────────────────────────────────────┘')

    // 保存场景产物到 JSON
    const distDir = join(__dirname, '..', 'dist')
    if (!existsSync(distDir)) mkdirSync(distDir, { recursive: true })
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
    const safeQuery = QUERY.substring(0, 30).replace(/[^\w\u4e00-\u9fa5]/g, '_')
    const scenariosFileName = `e2e-scenarios-${safeQuery}-${timestamp}.json`
    const scenariosFile = {
      query: QUERY,
      generated_at: new Date().toISOString(),
      plan: {
        task_description: plan.task_description,
        target_tags: plan.target_tags,
        scenario_patterns: patterns,
        interpretation_notes: plan.interpretation_notes,
        hard_constraints: plan.hard_constraints || [],
      },
      scenario_stats: {
        target_count: scenarioResult.targetCount,
        actual_count: scenarioResult.actualCount,
        provisional_pushed: allGeneratedScenarios.length,
        dedup_removed: allGeneratedScenarios.length - scenarioResult.actualCount,
        final_coverage_percentage: scenarioResult.finalCoveragePercentage,
        satisfied: scenarioResult.satisfied,
        total_iterations: scenarioResult.totalIterations,
        pattern_coverage: scenarioResult.patternCoverage,
      },
      scenarios: scenarios.map(s => ({
        scenario_id: s.scenario_id,
        scenario_name: s.scenario_name,
        description: s.description,
        tags: s.tags,
      })),
    }
    const scenariosPath = join(distDir, scenariosFileName)
    writeFileSync(scenariosPath, JSON.stringify(scenariosFile, null, 2), 'utf-8')
    console.log(`\n  [产物保存] 场景文件: ${scenariosPath}`)

    console.log(`\n${'═'.repeat(80)}`)
    console.log(`  端到端调试完成 ✓（仅场景生成，跳过用例）`)
    console.log(`${'═'.repeat(80)}\n`)
    return
  }

  console.log('\n┌──────────────────────────────────────────┐')
  console.log(`│  步骤 2: 用例生成（每场景 ${CASES_PER_SCENARIO} 个）        │`)
  console.log('└──────────────────────────────────────────┘\n')

  const cases = await generateAndRefineCases(
    scenarios,
    CASES_PER_SCENARIO,
    testTree,
    client,
    auditCases,
    fixCasesByAudit,
    'e2e-debug',
    {
      maxIterations: 3,
      maxRefineRoundsPerBatch: 1,
      onProgress: (info) => {
        const stageMap: Record<string, string> = {
          generating: '生成',
          auditing: '审核',
          fixing: '修复',
          completed: '完成',
        }
        const icon = info.stage === 'completed' ? '✅' : '🔄'
        const scenarioLabel = info.currentScenarioName ? ` [${info.currentScenarioName}]` : ''
        console.log(`  [用例进度] ${stageMap[info.stage] || info.stage} ${info.current}/${info.total} (${info.progressPercentage}%)${scenarioLabel} ${icon}`)
        console.log(`            ${info.currentStep}`)
      },
      onCaseGenerated: async (caseItem, info) => {
        console.log(`    [新用例] ${caseItem.case_id} (累计 ${info.totalPassedCases} 个)`)
      },
    }
  )

  console.log('\n┌──────────────────────────────────────────┐')
  console.log('│  步骤 2 完成：用例生成结果                 │')
  console.log('└──────────────────────────────────────────┘')
  console.log(`\n  [用例统计]`)
  console.log(`    场景数: ${scenarios.length}`)
  console.log(`    生成用例数: ${cases.length}`)
  console.log(`    每场景平均: ${(cases.length / scenarios.length).toFixed(1)} 个`)

  console.log(`\n  [全部用例列表]`)
  cases.forEach((c, i) => {
    console.log(`\n    ── 用例 ${i + 1} ──────────────────────`)
    console.log(`    用例 ID: ${c.case_id}`)
    console.log(`    来源场景 ID: ${c.source_scenario_id}`)
    console.log(`    标签: ${c.tags?.join('、') || '无'}`)

    // 打印 user_query_lists
    console.log(`    用户查询轮次: ${c.user_query_lists.length} 轮`)
    c.user_query_lists.forEach((turn, turnIdx) => {
      console.log(`      轮次 ${turnIdx + 1}:`)
      // 兼容两种形式：纯消息数组 和 DialogueRoundConfig
      const messages = Array.isArray(turn) ? turn : turn.user_query_list
      messages.forEach((q, qIdx) => {
        console.log(`        查询 ${qIdx + 1} [${q.role || 'user'}]: ${q.content}`)
      })
      // 如果是 DialogueRoundConfig，打印 mock_time/mock_info
      if (!Array.isArray(turn)) {
        if (turn.mock_time) console.log(`        ⏰ mock_time: ${turn.mock_time}`)
        if (turn.mock_info && Object.keys(turn.mock_info).length > 0) {
          console.log(`        🚗 mock_info: ${JSON.stringify(turn.mock_info)}`)
        }
      }
    })

    // 打印 expected_script（字符串）
    if (c.expected_script && c.expected_script.length > 0) {
      const scriptPreview = c.expected_script.length > 200
        ? c.expected_script.slice(0, 200) + '...'
        : c.expected_script
      console.log(`    期望脚本: ${c.expected_script.length} 字符`)
      console.log(`      ${scriptPreview.replace(/\n/g, '\n      ')}`)
    }

    // 打印 nl_assertion
    console.log(`    自然语言断言: ${c.nl_assertion.length} 条`)
    c.nl_assertion.forEach((assertion, aIdx) => {
      console.log(`      断言 ${aIdx + 1}: ${assertion}`)
    })

    // 打印 context_config（如果有）
    if (c.context_config) {
      const configStr = JSON.stringify(c.context_config)
      console.log(`    上下文配置: ${configStr.slice(0, 200)}${configStr.length > 200 ? '...' : ''}`)
    }
  })

  // ─────────────────────────────────────────────────────────────────
  // 步骤 3: 汇总
  // ─────────────────────────────────────────────────────────────────
  console.log('\n┌──────────────────────────────────────────┐')
  console.log('│  步骤 3: 端到端汇总                        │')
  console.log('└──────────────────────────────────────────┘')
  console.log(`\n  [链路完整性]`)
  console.log(`    Query → Plan: ✓`)
  console.log(`    Plan → 场景: ✓ (${scenarios.length} 个)`)
  console.log(`    场景 → 用例: ✓ (${cases.length} 个)`)

  // 验证每个用例都能追溯到来源场景
  const scenarioIds = new Set(scenarios.map(s => s.scenario_id))
  let allTraceable = true
  for (const c of cases) {
    if (!scenarioIds.has(c.source_scenario_id)) {
      allTraceable = false
      console.log(`    用例 → 场景追溯: ✗ (用例 ${c.case_id} 无法追溯到场景)`)
    }
  }
  if (allTraceable) {
    console.log(`    用例 → 场景追溯: ✓ (全部可追溯)`)
  }

  console.log(`\n  [质量指标]`)
  console.log(`    标签覆盖率: ${scenarioResult.finalCoveragePercentage}%`)
  console.log(`    Pattern 覆盖: ${coveredPatterns}/${totalPatterns} 个 pattern 有场景`)
  console.log(`    每场景平均用例数: ${(cases.length / scenarios.length).toFixed(1)}`)

  // ─────────────────────────────────────────────────────────────────
  // 保存产物到 JSON 文件（供批量查看）
  // ─────────────────────────────────────────────────────────────────
  const distDir = join(__dirname, '..', 'dist')
  if (!existsSync(distDir)) {
    mkdirSync(distDir, { recursive: true })
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
  const safeQuery = QUERY.substring(0, 30).replace(/[^\w\u4e00-\u9fa5]/g, '_')
  const casesFileName = `e2e-cases-${safeQuery}-${timestamp}.json`
  const reportFileName = `e2e-report-${safeQuery}-${timestamp}.json`

  // 1. 用例文件：纯 case 数组，可直接导入平台
  const casesPath = join(distDir, casesFileName)
  writeFileSync(casesPath, JSON.stringify(cases, null, 2), 'utf-8')

  // 2. 报告文件（纯统计，便于横向对比）
  const reportFile = {
    query: QUERY,
    generated_at: new Date().toISOString(),
    plan: {
      task_description: plan.task_description,
      target_tags: plan.target_tags,
      interpretation_notes: plan.interpretation_notes,
      hard_constraints: plan.hard_constraints || [],
      scenario_patterns: patterns,
    },
    summary: {
      scenario_target: scenarioResult.targetCount,
      scenario_actual: scenarioResult.actualCount,
      scenario_provisional: allGeneratedScenarios.length,
      scenario_dedup_removed: allGeneratedScenarios.length - scenarioResult.actualCount,
      case_total: cases.length,
      case_per_scenario_avg: Number((cases.length / scenarios.length).toFixed(2)),
      tag_coverage_percentage: scenarioResult.finalCoveragePercentage,
      pattern_covered: coveredPatterns,
      pattern_total: totalPatterns,
      satisfied: scenarioResult.satisfied,
      total_iterations: scenarioResult.totalIterations,
    },
    pattern_coverage: scenarioResult.patternCoverage,
    scenarios_brief: scenarios.map(s => ({
      id: s.scenario_id,
      name: s.scenario_name,
      tags: s.tags,
    })),
  }
  const reportPath = join(distDir, reportFileName)
  writeFileSync(reportPath, JSON.stringify(reportFile, null, 2), 'utf-8')

  console.log(`\n  [产物保存]`)
  console.log(`    用例文件: ${casesPath}（${cases.length} 个用例，纯 case 数组）`)
  console.log(`    报告文件: ${reportPath}`)

  console.log(`\n${'═'.repeat(80)}`)
  console.log(`  端到端调试完成 ✓`)
  console.log(`${'═'.repeat(80)}\n`)
}

// 运行主函数
main().catch(err => {
  console.error('\n❌ 端到端调试失败:', err)
  process.exit(1)
})
