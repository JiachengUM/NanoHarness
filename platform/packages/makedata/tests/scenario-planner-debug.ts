/**
 * Scenario Planner 命令行调试工具
 *
 * 使用方式：
 *   pnpm tsx tests/scenario-planner-debug.ts [query]
 *
 * 示例：
 *   pnpm tsx tests/scenario-planner-debug.ts "生成空调控制场景"
 *   pnpm tsx tests/scenario-planner-debug.ts "生成危险车控场景"
 *   pnpm tsx tests/scenario-planner-debug.ts "生成记忆管理场景"
 */

import { generateScenarioPlan } from '../src/generation/scenario-planner.js'
import { generateScenarioPatterns } from '../src/generation/scenario-pattern-generator.js'
import { TagTree } from '../src/core/tag-tree.js'
import { createClient } from '@eval-platform/llm'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

function loadTestTagTree(): TagTree {
  const treePath = join(__dirname, '../examples/data/vehicle-tag-tree.json')
  const treeData = JSON.parse(readFileSync(treePath, 'utf-8'))
  return TagTree.fromJSON(treeData)
}

/**
 * 示例 Query 列表 - 覆盖不同复杂度
 */
const EXAMPLE_QUERIES = [
  // 简单功能直达
  '生成空调控制场景',
  // 具体危险场景
  '生成危险车控场景，如行驶中开关车门',
  // 媒体控制
  '生成音乐播放控制场景',
  // 导航场景
  '生成导航和地点查询场景',
  // 记忆相关
  '生成用户记忆管理场景',
  // 复杂组合
  '生成车载助手日常交互场景',
  // 模糊任务
  '生成多轮对话场景',
  // 跨功能组合
  '生成导航+音乐+车控组合场景',
  // 边界测试
  '生成模糊需求理解场景',
  // 安全场景
  '生成安全合规拒绝场景',
]

/**
 * 运行单个 Query 并打印完整 Plan
 */
async function runQuery(query: string, tagTree: TagTree): Promise<void> {
  const client = createClient()

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
    console.log('   前20个标签:', plan.target_tags.slice(0, 20).join(', '))
    if (plan.target_tags.length > 20) {
      console.log(`   ... 共 ${plan.target_tags.length} 个标签`)
    }

    const { patterns, targetScenarioCount } = await generateScenarioPatterns(
      { ...plan, task_id: 'debug', generation_task_run_id: 'debug', tag_tree_name: tagTree.root.name } as any,
      tagTree,
      client
    )
    console.log('\n🎨 场景模式列表:')
    patterns.forEach((pattern, i) => {
      console.log(`   ${(i + 1).toString().padStart(2, '0')}. ${pattern}`)
    })

    console.log('\n💡 理解说明:')
    console.log(plan.interpretation_notes)

    console.log('\n✅ Plan 生成成功')
    console.log(`   - 标签覆盖: ${plan.target_tags.length} 个相关标签`)
    console.log(`   - 场景目标（参考下限）: ${targetScenarioCount} 个场景`)
    console.log(`   - 模式数量: ${patterns.length} 种场景模式`)
  } catch (error) {
    console.error('\n❌ Plan 生成失败:', error)
  }
}

/**
 * 主入口
 */
async function main(): Promise<void> {
  const args = process.argv.slice(2)
  const customQuery = args.find(arg => !arg.startsWith('--'))

  const tagTree = loadTestTagTree()

  if (customQuery) {
    // 运行用户指定的 query
    console.log('\n' + '='.repeat(80))
    console.log('Scenario Planner 命令行调试')
    console.log('='.repeat(80))
    await runQuery(customQuery, tagTree)
  } else {
    // 运行所有示例 queries
    console.log('\n' + '='.repeat(80))
    console.log('Scenario Planner 命令行调试工具')
    console.log('='.repeat(80))
    console.log('\n使用方式: pnpm tsx tests/scenario-planner-debug.ts [query]')
    console.log('\n示例 queries:')
    EXAMPLE_QUERIES.forEach((q, i) => console.log(`  ${(i + 1).toString().padStart(2, '0')}. ${q}`))
    console.log('\n将依次运行所有示例 queries...\n')

    for (const query of EXAMPLE_QUERIES) {
      await runQuery(query, tagTree)
    }

    console.log('\n' + '='.repeat(80))
    console.log('所有示例运行完成')
    console.log('='.repeat(80))
  }
}

// 运行主函数
main().then(() => process.exit(0)).catch(error => {
  console.error('Fatal error:', error)
  process.exit(1)
})
