/**
 * 完整流水线调试文件 - 从 Query 到场景再到用例
 *
 * 直接运行此文件进行端到端测试：
 * ```bash
 * npx tsx src/simple_run/full-pipeline.ts [query]
 * ```
 *
 * 使用示例：
 * - npx tsx src/simple_run/full-pipeline.ts                    # 使用默认 query
 * - npx tsx src/simple_run/full-pipeline.ts "生成空调场景"    # 指定 query
 * - npx tsx src/simple_run/full-pipeline.ts "生成危险车控场景" # 测试危险场景
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'
import { createClient } from '@eval-platform/llm'
import { TagTree } from '../core/tag-tree.js'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

/**
 * 加载示例车辆标签树
 */
function loadVehicleTagTree(): any {
  const treePath = join(__dirname, '../../examples/data/vehicle-tag-tree.json')
  return JSON.parse(readFileSync(treePath, 'utf-8'))
}

/**
 * 保存结果到 JSON 文件 (输出到 dist/generation 目录)
 */
function saveResultsToFile(
  scenarios: any[],
  cases: any[],
  query: string,
  extraInfo?: Record<string, any>
) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
  const safeQuery = query.replace(/[^\w\u4e00-\u9fa5]/g, '_').substring(0, 30)

  // 输出目录: dist/generation
  const outputDir = join(__dirname, '../../dist/generation')

  // 确保输出目录存在
  if (!existsSync(outputDir)) {
    mkdirSync(outputDir, { recursive: true })
  }

  // 1. 保存完整用例数据（可直接导入为 DatasetItem）
  const casesFilename = `pipeline-cases-${safeQuery}-${timestamp}.json`
  const casesFilepath = join(outputDir, casesFilename)

  const casesOutput = {
    generatedAt: new Date().toISOString(),
    query,
    datasetItems: cases.map(c => ({
      // DatasetItem 核心字段
      dataset_id: c.dataset_id,
      case_id: c.case_id,
      context_config: c.context_config,
      max_round: c.max_round,
      user_query_lists: c.user_query_lists,
      available_tools: c.available_tools,
      tools_to_test: c.tools_to_test,
      tags: c.tags,
      nl_assertion: c.nl_assertion,
      code_assertion: c.code_assertion,
      // 来源信息
      source_scenario_id: c.source_scenario_id,
      // 其他字段
      ...c,
    })),
  }

  writeFileSync(casesFilepath, JSON.stringify(casesOutput, null, 2), 'utf-8')
  console.log('\n[用例文件保存] 完整用例数据已保存到: ' + casesFilename)
  console.log('  路径: ' + casesFilepath)
  console.log('  包含字段: case_id, context_config, user_query_lists, nl_assertion, tags 等')

  // 2. 保存完整报告（包含场景摘要）
  const reportFilename = `pipeline-report-${safeQuery}-${timestamp}.json`
  const reportFilepath = join(outputDir, reportFilename)

  const reportOutput = {
    generatedAt: new Date().toISOString(),
    query,
    summary: {
      scenarioCount: scenarios.length,
      caseCount: cases.length,
      ...extraInfo,
    },
    scenarios: scenarios.map(s => ({
      scenario_id: s.scenario_id,
      scenario_name: s.scenario_name,
      description: s.description?.substring(0, 200) + (s.description?.length > 200 ? '...' : ''),
      tags: s.tags,
    })),
    cases: cases.map(c => ({
      case_id: c.case_id,
      case_name: c.case_name,
      source_scenario_id: c.source_scenario_id,
      tags: c.tags,
      max_round: c.max_round,
      user_query_count: c.user_query_lists?.length || 0,
      first_query: c.user_query_lists?.[0]?.user_query_list?.[0]?.content?.substring(0, 60) || 'N/A',
    })),
  }

  writeFileSync(reportFilepath, JSON.stringify(reportOutput, null, 2), 'utf-8')
  console.log('\n[报告文件保存] 摘要报告已保存到: ' + reportFilename)
  console.log('  路径: ' + reportFilepath)
}

/**
 * 主函数：完整流水线
 */
async function main() {
  console.log('========================================')
  console.log('   完整流水线：Query → 场景 → 用例')
  console.log('========================================\n')

  // 1. 加载标签树
  console.log('[1/4] 加载标签树...')
  const treeData = loadVehicleTagTree()
  const tagTree = TagTree.fromJSON(treeData)
  console.log('  根节点: ' + tagTree.root.name)
  console.log('  叶子标签: ' + tagTree.getLeafTagNames().length + ' 个\n')

  // 2. 获取查询
  const args = process.argv.slice(2)
  const customQuery = args.find(arg => !arg.startsWith('--'))
  const query = customQuery || '帮我生成5个时间规律发现的场景，不要太夸张和少见。'
  console.log('[2/4] 查询: ' + query + '\n')

  // 3. 创建 LLM 客户端
  console.log('[3/4] 创建 LLM 客户端...')
  const client = createClient()
  console.log('  创建成功\n')

  // ═══════════════════════════════════════════════════════════════════════════
  // Step 1: 生成场景
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('========================================')
  console.log('   Step 1: 生成场景')
  console.log('========================================\n')

  const { generateScenarios } = await import('../generation/scenario-core.js')

  // 快速验证模式：使用自定义 Plan 限制场景数量，加快测试
  // 正常模式：const scenarioResult = await generateScenarios(query, tagTree, client, {...})
  // 快速验证：先生成 Plan，然后修改目标数量
  const { generateScenarioPlan } = await import('../generation/scenario-planner.js')
  const quickPlan = await generateScenarioPlan(query, tagTree, client)

  const scenarioResult = await generateScenarios(query, tagTree, client, {
    plan: {
      ...quickPlan,
      task_id: `task-quick-${Date.now()}`,
      generation_task_run_id: `run-quick-${Date.now()}`,
      tag_tree_name: '',
    },
    maxIterations: 3,
    initialBatchSize: 5,
    maxRefineRoundsPerBatch: 1,
    onProgress: (info) => {
      const stageMap: Record<string, string> = {
        generating: '生成',
        auditing: '审核',
        fixing: '修复',
        judging: '判别',
      }
      const statusIcon = info.satisfied ? '✅' : (info.totalScenarios >= info.targetScenarioCount ? '⏳' : '🔄')
      console.log('\n[进度] 迭代 ' + info.iteration +
        ' | ' + stageMap[info.stage] +
        ' | 批次: ' + info.batchSize +
        ' | 进度: ' + info.progressPercentage + '%' +
        ' (' + info.totalScenarios + '/' + info.targetScenarioCount + ')' +
        ' | 覆盖: ' + info.coveragePercentage + '%' +
        ' ' + statusIcon)
    },
    onScenarioGenerated: async (scenario, info) => {
      console.log(`  [场景生成] ${scenario.scenario_name} (${info.totalScenarios}/${info.targetScenarioCount})`)
    },
  })

  console.log('\n========================================')
  console.log('   场景生成完成')
  console.log('========================================')
  console.log('  目标场景数: ' + scenarioResult.targetCount)
  console.log('  实际生成: ' + scenarioResult.actualCount)
  console.log('  达成率: ' + Math.round((scenarioResult.actualCount / scenarioResult.targetCount) * 100) + '%')
  console.log('  总迭代次数: ' + scenarioResult.totalIterations)
  console.log('  最终覆盖率: ' + scenarioResult.finalCoveragePercentage + '%')
  console.log('========================================\n')

  const scenarios = scenarioResult.scenarios

  if (scenarios.length === 0) {
    console.error('❌ 未生成任何场景，流程结束')
    return
  }

  // 打印前 5 个场景
  const displayScenarioCount = Math.min(5, scenarios.length)
  console.log('前 ' + displayScenarioCount + ' 个场景预览:')
  scenarios.slice(0, displayScenarioCount).forEach((scenario, index) => {
    console.log('\n[' + (index + 1) + '] ' + scenario.scenario_name)
    console.log('    ID: ' + scenario.scenario_id)
    console.log('    描述: ' + scenario.description.substring(0, 80) + '...')
    console.log('    标签: ' + scenario.tags.slice(0, 5).join(', ') + (scenario.tags.length > 5 ? '...' : ''))
  })

  if (scenarios.length > displayScenarioCount) {
    console.log('\n...还有 ' + (scenarios.length - displayScenarioCount) + ' 个场景')
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Step 2: 生成用例
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('\n========================================')
  console.log('   Step 2: 生成用例')
  console.log('========================================\n')

  const { generateAndRefineCases } = await import('../generation/case.js')
  const { auditCases, fixCasesByAudit } = await import('../audit/index.js')

  // 快速验证模式：每个场景生成 1 个用例
  const casesPerScenario = 1
  const targetTotalCases = scenarios.length * casesPerScenario

  console.log(`配置: 每个场景生成 ${casesPerScenario} 个用例`)
  console.log(`预计总用例数: ${targetTotalCases}\n`)

  const cases = await generateAndRefineCases(
    scenarios,
    casesPerScenario,
    tagTree,
    client,
    auditCases,
    fixCasesByAudit,
    'pipeline-test',
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
        console.log(`[用例进度] ${stageMap[info.stage] || info.stage} ${info.current}/${info.total} (${info.progressPercentage}%) ${icon} ${info.currentStep}`)
      },
      onCaseGenerated: async (caseItem, info) => {
        console.log(`  [用例生成] ${caseItem.case_id} (${info.totalPassedCases}/${targetTotalCases})`)
      },
    }
  )

  console.log('\n========================================')
  console.log('   用例生成完成')
  console.log('========================================')
  console.log('  目标用例数: ' + targetTotalCases)
  console.log('  实际生成: ' + cases.length)
  console.log('  达成率: ' + Math.round((cases.length / targetTotalCases) * 100) + '%')
  console.log('========================================\n')

  // 打印前 3 个用例
  const displayCaseCount = Math.min(3, cases.length)
  console.log('前 ' + displayCaseCount + ' 个用例预览:')
  cases.slice(0, displayCaseCount).forEach((c: any, index: number) => {
    console.log('\n[' + (index + 1) + '] ' + c.case_id)
    console.log('    ID: ' + c.case_id)
    console.log('    来源场景: ' + c.source_scenario_id)
    console.log('    标签: ' + (c.tags?.slice(0, 5).join(', ') || 'N/A') + (c.tags && c.tags.length > 5 ? '...' : ''))
    if (c.user_query_lists && c.user_query_lists.length > 0) {
      const firstQuery = c.user_query_lists[0].user_query_list?.[0]?.content
      console.log('    首句对话: ' + (firstQuery?.substring(0, 60) || 'N/A') + '...')
    }
  })

  if (cases.length > displayCaseCount) {
    console.log('\n...还有 ' + (cases.length - displayCaseCount) + ' 个用例')
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Step 3: 保存结果
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('\n========================================')
  console.log('   Step 3: 保存结果')
  console.log('========================================\n')

  saveResultsToFile(scenarios, cases, query, {
    scenarioIterations: scenarioResult.totalIterations,
    scenarioSatisfied: scenarioResult.satisfied,
    plan: {
      targetScenarioCount: scenarioResult.targetCount,
      targetTags: scenarioResult.plan.target_tags.length,
      scenarioPatterns: Object.keys(scenarioResult.patternCoverage).length,
    },
  })

  console.log('\n========================================')
  console.log('   完整流水线执行完成')
  console.log('========================================')
  console.log('✅ 场景生成: ' + scenarios.length + ' 个')
  console.log('✅ 用例生成: ' + cases.length + ' 个')
  console.log('========================================')
}

// 检测是否直接运行此文件
if (import.meta.url.startsWith('file:')) {
  const modulePath = fileURLToPath(import.meta.url)
  if (process.argv[1] === modulePath) {
    main().catch(error => {
      console.error('错误:', error)
      process.exit(1)
    })
  }
}
