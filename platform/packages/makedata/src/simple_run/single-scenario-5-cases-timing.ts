/**
 * 单个场景生成 5 个用例的计时测试脚本
 *
 * 直接运行：
 * ```bash
 * npx tsx src/simple_run/single-scenario-5-cases-timing.ts
 * ```
 *
 * 输出：
 * - 从脚本启动到第一个用例生成的耗时
 * - 从第一个用例到 5 个用例全部完成的耗时
 * - 总耗时
 * - 用例列表保存到 dist/timing/
 */

import { existsSync, mkdirSync, writeFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'
import { createClient } from '@eval-platform/llm'
import type { Scenario } from '@eval-platform/database'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

/**
 * 默认测试场景：跨会话临时地址与家地址导航优先级
 */
function getDefaultScenario(): Scenario {
  return {
    scenario_id: `scenario-timing-${Date.now()}`,
    scenario_name: '跨会话临时地址与家地址导航优先级',
    description: '用户先在某会话中告知临时居住地址，随后在独立会话中说"导航回家"，验证助手是否能优先使用最新临时地址发起导航，而非默认家地址。',
    tags: ['长期记忆调用', '常用地点记忆', '精确地点直达', '多次多轮_2次会话'],
  }
}

/**
 * 保存结果到文件
 */
function saveResults(scenario: Scenario, cases: any[], timing: Record<string, number>) {
  const outputDir = join(__dirname, '../../dist/timing')
  if (!existsSync(outputDir)) {
    mkdirSync(outputDir, { recursive: true })
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
  const safeName = scenario.scenario_name.replace(/[^\w\u4e00-\u9fa5]/g, '_').substring(0, 30)
  const filename = `single-scenario-5-cases-${safeName}-${timestamp}.json`
  const filepath = join(outputDir, filename)

  const output = {
    generatedAt: new Date().toISOString(),
    scenario,
    timing: {
      startToFirstCaseMs: timing.startToFirstCaseMs,
      firstCaseToAllCasesMs: timing.firstCaseToAllCasesMs,
      totalMs: timing.totalMs,
      startToFirstCaseSec: +(timing.startToFirstCaseMs / 1000).toFixed(2),
      firstCaseToAllCasesSec: +(timing.firstCaseToAllCasesMs / 1000).toFixed(2),
      totalSec: +(timing.totalMs / 1000).toFixed(2),
    },
    cases: cases.map(c => ({
      case_id: c.case_id,
      case_description: c.case_description,
      tags: c.tags,
      max_round: c.max_round,
      first_query: Array.isArray(c.user_query_lists?.[0])
        ? c.user_query_lists[0][0]?.content
        : c.user_query_lists?.[0]?.user_query_list?.[0]?.content,
      context_config: c.context_config,
      user_query_lists: c.user_query_lists,
      expected_script: c.expected_script,
      nl_assertion: c.nl_assertion,
    })),
  }

  writeFileSync(filepath, JSON.stringify(output, null, 2), 'utf-8')
  console.log(`\n[结果保存] ${filepath}`)
}

/**
 * 主函数
 */
async function main() {
  const scenario = getDefaultScenario()
  const count = 5

  console.log('========================================')
  console.log('  单个场景 5 用例生成计时测试')
  console.log('========================================')
  console.log(`场景: ${scenario.scenario_name}`)
  console.log(`目标用例数: ${count}\n`)

  const startTime = performance.now()
  let firstCaseTime: number | null = null

  const { generateCasesForScenario } = await import('../generation/case.js')
  const client = createClient()

  const cases = await generateCasesForScenario(
    scenario,
    count,
    client,
    'single-scenario-timing',
    undefined,
    (firstCase) => {
      firstCaseTime = performance.now()
      console.log('\n----------------------------------------')
      console.log('  首个用例已生成')
      console.log('----------------------------------------')
      console.log(`case_id: ${firstCase.case_id}`)
      console.log(`case_description: ${firstCase.case_description}`)
      console.log(`⏱️ 启动 → 首个用例: ${((firstCaseTime - startTime) / 1000).toFixed(2)}s`)
    }
  )

  const endTime = performance.now()
  const totalMs = endTime - startTime
  const startToFirstCaseMs = firstCaseTime ? firstCaseTime - startTime : 0
  const firstCaseToAllCasesMs = firstCaseTime ? endTime - firstCaseTime : 0

  console.log('\n========================================')
  console.log('  生成完成')
  console.log('========================================')
  console.log(`实际生成用例数: ${cases.length}`)
  console.log(`⏱️ 启动 → 首个用例: ${(startToFirstCaseMs / 1000).toFixed(2)}s`)
  console.log(`⏱️ 首个用例 → 全部完成: ${(firstCaseToAllCasesMs / 1000).toFixed(2)}s`)
  console.log(`⏱️ 总耗时: ${(totalMs / 1000).toFixed(2)}s`)

  if (cases.length > 0) {
    console.log('\n用例列表:')
    cases.forEach((c, i) => {
      const firstQuery = Array.isArray(c.user_query_lists?.[0])
        ? c.user_query_lists[0][0]?.content
        : c.user_query_lists?.[0]?.user_query_list?.[0]?.content
      console.log(`  ${i + 1}. ${c.case_id} | ${firstQuery?.substring(0, 40) || ''}`)
    })
  }

  saveResults(scenario, cases, {
    startToFirstCaseMs,
    firstCaseToAllCasesMs,
    totalMs,
  })
}

main().catch((error) => {
  console.error('运行失败:', error)
  process.exit(1)
})
