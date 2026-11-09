/**
 * 场景生成调试文件
 *
 * 直接运行此文件进行调试：
 * ```bash
 * npx tsx src/simple_run/scenario.ts [query]
 * ```
 *
 * 使用示例：
 * - npx tsx src/simple_run/scenario.ts                    # 使用默认 query
 * - npx tsx src/simple_run/scenario.ts "生成空调场景"    # 指定 query
 */

import { readFileSync, writeFileSync } from 'fs'
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
 * 保存场景结果到 JSON 文件
 */
function saveScenariosToFile(
  scenarios: any[],
  mode: string,
  extraInfo?: Record<string, any>
) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
  const filename = `generated-scenarios-${mode}-${timestamp}.json`
  const filepath = join(__dirname, filename)

  const output = {
    generatedAt: new Date().toISOString(),
    mode,
    totalScenarios: scenarios.length,
    ...extraInfo,
    scenarios,
  }

  writeFileSync(filepath, JSON.stringify(output, null, 2), 'utf-8')
  console.log('\n[文件保存] 场景结果已保存到: ' + filename)
  console.log('  路径: ' + filepath)
}

/**
 * 调试：完整迭代生成流程
 */
async function mainIterative() {
  console.log('========================================')
  console.log('   调试：完整迭代生成流程')
  console.log('========================================\n')

  // 1. 加载标签树
  console.log('[1/3] 加载标签树...')
  const treeData = loadVehicleTagTree()
  const tagTree = TagTree.fromJSON(treeData)
  console.log('  根节点: ' + tagTree.root.name)
  console.log('  叶子标签: ' + tagTree.getLeafTagNames().length + ' 个\n')

  // 2. 示例查询（支持命令行参数传入）
  const args = process.argv.slice(2)
  const customQuery = args.find(arg => !arg.startsWith('--'))
  const query = customQuery || '生成你能想到的所有行驶过程中的危险车控场景。'
  console.log('[2/3] 查询: ' + query + '\n')

  // 3. 创建 LLM 客户端
  console.log('[3/3] 创建 LLM 客户端...')
  const client = createClient()
  console.log('  创建成功\n')

  // 4. 完整迭代生成
  console.log('启动完整迭代生成...\n')
  const { generateScenarios } = await import('../generation/scenario-core.js')

  const result = await generateScenarios(query, tagTree, client, {
    maxIterations: 50,                    // 安全上限：50轮迭代（实际以Plan目标为准）
    initialBatchSize: 5,                // 每批5个
    maxRefineRoundsPerBatch: 2,         // 每批审核修复2轮
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
        ' ' + statusIcon +
        ' | ' + info.currentStep)
    },
  })

  console.log('\n\n========================================')
  console.log('   最终结果')
  console.log('========================================')
  console.log('  目标场景数: ' + result.targetCount)
  console.log('  实际生成: ' + result.actualCount)
  console.log('  达成率: ' + Math.round((result.actualCount / result.targetCount) * 100) + '%')
  console.log('  总迭代次数: ' + result.totalIterations)
  console.log('  最终覆盖率: ' + result.finalCoveragePercentage + '%')
  console.log('  满足需求: ' + (result.satisfied ? '是' : '否'))
  console.log('========================================\n')

  // 5. 打印前10个场景
  const displayCount = Math.min(10, result.scenarios.length)
  console.log('前 ' + displayCount + ' 个场景预览:')
  result.scenarios.slice(0, displayCount).forEach((scenario, index) => {
    console.log('\n[' + (index + 1) + '] ' + scenario.scenario_name)
    console.log('    ID: ' + scenario.scenario_id)
    console.log('    描述: ' + scenario.description.substring(0, 80) + '...')
    console.log('    标签: ' + scenario.tags.slice(0, 5).join(', ') + (scenario.tags.length > 5 ? '...' : ''))
  })

  if (result.scenarios.length > displayCount) {
    console.log('\n...还有 ' + (result.scenarios.length - displayCount) + ' 个场景')
  }

  // 6. 保存结果到文件
  saveScenariosToFile(result.scenarios, 'iterative', {
    query,
    totalIterations: result.totalIterations,
    targetCount: result.targetCount,
    actualCount: result.actualCount,
    finalCoveragePercentage: result.finalCoveragePercentage,
    satisfied: result.satisfied,
  })

  console.log('\n========================================')
  console.log('   调试完成')
  console.log('========================================')
}

/**
 * 主入口
 */
async function main() {
  await mainIterative()
}

// 检测是否直接运行此文件
if (import.meta.url.startsWith('file:')) {
  const modulePath = fileURLToPath(import.meta.url)
  if (process.argv[1] === modulePath) {
    main()
  }
}
