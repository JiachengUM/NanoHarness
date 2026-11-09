/**
 * Scenario Planner 调试文件
 *
 * 直接运行此文件进行 Planner 测试：
 * ```bash
 * npx tsx src/simple_run/planner.ts [query]
 * ```
 *
 * 使用示例：
 * - npx tsx src/simple_run/planner.ts                    # 使用默认 query
 * - npx tsx src/simple_run/planner.ts "生成空调场景"     # 指定 query
 * - npx tsx src/simple_run/planner.ts "生成记忆场景"     # 测试记忆相关
 */

import { readFileSync, writeFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'
import { createClient } from '@eval-platform/llm'
import { TagTree } from '../core/tag-tree.js'
import { generateScenarioPlan } from '../generation/scenario-planner.js'
import { generateScenarioPatterns } from '../generation/scenario-pattern-generator.js'

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
 * 保存 Plan 结果到 JSON 文件
 */
function savePlanToFile(
  plan: any,
  query: string,
  extraInfo?: Record<string, any>
) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
  const safeQuery = query.replace(/[^\w\u4e00-\u9fa5]/g, '_').substring(0, 30)
  const filename = `generated-plan-${safeQuery}-${timestamp}.json`
  const filepath = join(__dirname, filename)

  const output = {
    generatedAt: new Date().toISOString(),
    query,
    ...extraInfo,
    plan,
  }

  writeFileSync(filepath, JSON.stringify(output, null, 2), 'utf-8')
  console.log('\n[文件保存] Plan 结果已保存到: ' + filename)
  console.log('  路径: ' + filepath)
}

/**
 * 主函数：测试 Scenario Planner
 */
async function main() {
  console.log('========================================')
  console.log('   Scenario Planner 调试')
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
  const query = customQuery || '我想生成所有可能威胁行驶中安全的，应该被助手拒绝执行的场景。'
  console.log('[2/3] 查询: ' + query + '\n')

  // 3. 创建 LLM 客户端
  console.log('[3/3] 创建 LLM 客户端...')
  const client = createClient()
  console.log('  创建成功\n')

  // 4. 生成 Plan
  console.log('========================================')
  console.log('   生成 Scenario Plan')
  console.log('========================================\n')

  const plan = await generateScenarioPlan(query, tagTree, client)

  // 5. 打印结果
  console.log('\n========================================')
  console.log('   Plan 生成结果')
  console.log('========================================')

  console.log('\n📝 任务描述:')
  console.log(plan.task_description)

  console.log('\n🏷️ 目标标签数: ' + plan.target_tags.length)
  console.log('   前20个标签: ' + plan.target_tags.slice(0, 20).join(', '))
  if (plan.target_tags.length > 20) {
    console.log('   ... 共 ' + plan.target_tags.length + ' 个标签')
  }

  console.log('\n[生成场景模式列表...]')
  const { patterns, targetScenarioCount } = await generateScenarioPatterns(
    { ...plan, task_id: 'debug-task', generation_task_run_id: 'debug-run', tag_tree_name: tagTree.root.name } as any,
    tagTree,
    client
  )
  console.log('\n🎨 场景模式列表 (' + patterns.length + ' 种):')
  patterns.forEach((pattern, i) => {
    console.log('   ' + (i + 1).toString().padStart(2, '0') + '. ' + pattern)
  })

  console.log('\n💡 理解说明:')
  console.log(plan.interpretation_notes)

  console.log('\n========================================')
  console.log('   Plan 统计')
  console.log('========================================')
  console.log('  目标场景数（参考下限）: ' + targetScenarioCount)
  console.log('  相关标签数: ' + plan.target_tags.length)
  console.log('  场景模式数: ' + patterns.length)
  console.log('========================================\n')

  // 6. 保存结果到文件
  savePlanToFile(plan, query, {
    tagTreeName: tagTree.root.name,
    totalLeafTags: tagTree.getLeafTagNames().length,
    relevantTagRatio: Math.round((plan.target_tags.length / tagTree.getLeafTagNames().length) * 100) + '%',
  })

  console.log('========================================')
  console.log('   Planner 调试完成')
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
