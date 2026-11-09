/**
 * 基础场景生成示例
 *
 * 演示如何使用 generateScenarios 基于查询和标签树生成场景
 */

import { createClient } from '@eval-platform/llm'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'
import { TagTree, previewTagTree, generateScenarios } from '@eval-platform/makedata'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

async function main() {
  console.log('=== 基础场景生成示例 ===\n')

  // 加载标签树
  const tagTreePath = join(__dirname, 'data', 'vehicle-tag-tree.json')
  const tagTreeJson = JSON.parse(readFileSync(tagTreePath, 'utf-8'))
  const tagTree = TagTree.fromJSON(tagTreeJson)

  console.log('已加载标签树:')
  console.log(`  - 总节点数: ${tagTree.root.iterNodes().length}`)
  console.log(`  - 叶子标签数: ${tagTree.getLeafTagNames().length}`)
  console.log()

  // 显示标签树预览
  const preview = previewTagTree(tagTree, {
    showTree: true,
    showLeafList: false,
    title: '标签树结构',
  })
  console.log(preview.split('\n').slice(0, 30).join('\n'))
  console.log('... (省略更多层级)')
  console.log()

  // 创建 LLM 客户端
  const client = createClient()

  // 示例查询
  const query = '生成一些危险操作的场景，特别是危险的车控场景。'
  console.log('='.repeat(50))
  console.log('用户查询:', query)
  console.log('='.repeat(50))
  console.log()

  // 生成场景
  const scenarios = await generateScenarios(query, tagTree, client)

  // 打印结果
  console.log('\n=== 生成的场景列表 ===\n')
  for (const scenario of scenarios) {
    console.log(`[${scenario.scenario_id}] ${scenario.scenario_name}`)
    console.log(`描述: ${scenario.description}`)
    console.log(`标签: ${scenario.tags.join(', ')}`)
    console.log('-'.repeat(50))
  }

  console.log(`\n✅ 成功生成 ${scenarios.length} 个场景`)
}

main().catch(console.error)
