/**
 * 完整数据合成流程示例
 *
 * 演示：场景生成 → 用例生成 → 审核 → 修复 → 输出通过用例
 */

import { createClient } from '@eval-platform/llm'
import { readFileSync, writeFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'
import {
  TagTree,
  previewTagTree,
  generateScenarios,
  generateAndRefineCases,
  auditCases,
  fixCasesByAudit,
} from '@eval-platform/makedata'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

async function main() {
  console.log('=== 完整数据合成流程示例 ===\n')

  // ========== 1. 加载标签树 ==========
  const tagTreePath = join(__dirname, 'data', 'vehicle-tag-tree.json')
  const tagTreeJson = JSON.parse(readFileSync(tagTreePath, 'utf-8'))
  const tagTree = TagTree.fromJSON(tagTreeJson)

  console.log('📖 标签树已加载:')
  console.log(`  - 总节点数: ${tagTree.root.iterNodes().length}`)
  console.log(`  - 叶子标签数: ${tagTree.getLeafTagNames().length}`)
  console.log()

  // 创建 LLM 客户端
  const client = createClient()

  // ========== 2. 生成场景 ==========
  console.log('='.repeat(50))
  console.log('步骤1: 生成场景')
  console.log('='.repeat(50))
  console.log()

  const query = '生成2个日常通勤场景，涉及空调温度调节和音乐点播'
  const scenarios = await generateScenarios(query, tagTree, client)

  console.log(`\n✅ 生成 ${scenarios.length} 个场景:`)
  for (const s of scenarios) {
    console.log(`  - [${s.scenario_id}] ${s.scenario_name}`)
  }
  console.log()

  // ========== 3. 生成用例 + 审核 + 修复 ==========
  console.log('='.repeat(50))
  console.log('步骤2-4: 生成用例 → 审核 → 修复')
  console.log('='.repeat(50))
  console.log()

  const refinedCases = await generateAndRefineCases(
    scenarios,
    2, // 每个场景2个用例
    tagTree,
    client,
    auditCases,
    fixCasesByAudit,
    'demo-dataset-refined',
    {
      maxRefineRounds: 2, // 最多修复2轮
      auditConcurrency: 5,
      fixConcurrency: 3,
    }
  )

  // ========== 4. 输出结果 ==========
  console.log('='.repeat(50))
  console.log('最终结果')
  console.log('='.repeat(50))
  console.log()
  console.log(`审核通过用例: ${refinedCases.length} 个`)
  for (const c of refinedCases) {
    console.log(`  - [${c.case_id}]`)
    console.log(`    来源: ${c.source_scenario_name}`)
    console.log(`    标签: ${c.tags?.slice(0, 5).join(', ')}${(c.tags?.length || 0) > 5 ? '...' : ''}`)
  }

  // 保存结果
  if (refinedCases.length > 0) {
    const outputPath = join(__dirname, 'data', 'refined-cases.json')
    writeFileSync(outputPath, JSON.stringify(refinedCases, null, 2), 'utf-8')
    console.log(`\n💾 用例已保存到: ${outputPath}`)
  }
}

main().catch(console.error)
