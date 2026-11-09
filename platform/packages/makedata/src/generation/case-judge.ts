/**
 * 用例判别者模块
 *
 * 评估当前每个场景的用例数量是否达标，指导补充生成。
 *
 * 核心原则：
 * 1. 每个场景的合格用例数必须达到用户要求的数量
 * 2. 判别针对每个场景独立统计
 * 3. 生成指导意见聚焦于为数量不足的场景补充用例
 */

import type { OpenAI } from '@eval-platform/llm'
import type { CaseWithScenario } from '@eval-platform/database'
import type { Scenario } from '@eval-platform/database/models/scenario'

/**
 * 场景用例数量统计
 */
export interface ScenarioCaseCount {
  /** 场景 ID */
  scenarioId: string
  /** 场景名称 */
  scenarioName: string
  /** 期望用例数 */
  expectedCount: number
  /** 当前合格用例数 */
  currentCount: number
  /** 缺口数量 */
  deficit: number
  /** 是否达标 */
  satisfied: boolean
}

/**
 * 用例生成指导意见
 */
export interface CaseGenerationGuidance {
  /** 需要补充用例的场景列表 */
  scenariosToReplenish: Array<{
    scenarioId: string
    scenarioName: string
    needCount: number
  }>
  /** 自然语言生成指导 */
  guidance: string
  /** 总共还需要生成的用例数 */
  totalNeeded: number
}

/**
 * 用例判别结果
 */
export interface CaseJudgementResult {
  /** 是否所有场景的用例数都达标 */
  satisfied: boolean
  /** 各场景的用例统计 */
  scenarioCounts: ScenarioCaseCount[]
  /** 缺口总数 */
  totalDeficit: number
  /** 指导意见（若 satisfied=false） */
  guidance: CaseGenerationGuidance | null
  /** 满足原因（若 satisfied=true） */
  stopReason?: string
}

/**
 * 统计每个场景的当前用例数量
 */
function countCasesByScenario(
  cases: CaseWithScenario[],
  scenarios: Scenario[],
  casesPerScenario: number
): ScenarioCaseCount[] {
  // 按场景 ID 分组统计
  const caseMap = new Map<string, CaseWithScenario[]>()
  for (const caseItem of cases) {
    const scenarioId = caseItem.source_scenario_id
    if (!caseMap.has(scenarioId)) {
      caseMap.set(scenarioId, [])
    }
    caseMap.get(scenarioId)!.push(caseItem)
  }

  // 为每个场景生成统计
  return scenarios.map(scenario => {
    const currentCount = caseMap.get(scenario.scenario_id)?.length || 0
    const deficit = Math.max(0, casesPerScenario - currentCount)

    return {
      scenarioId: scenario.scenario_id,
      scenarioName: scenario.scenario_name,
      expectedCount: casesPerScenario,
      currentCount,
      deficit,
      satisfied: currentCount >= casesPerScenario,
    }
  })
}

/**
 * 判别用例生成进度
 *
 * 评估当前每个场景的合格用例数是否达标，给出补充生成指导。
 */
export function judgeCaseGeneration(
  cases: CaseWithScenario[],
  scenarios: Scenario[],
  casesPerScenario: number
): CaseJudgementResult {
  // 1. 统计每个场景的用例数
  const scenarioCounts = countCasesByScenario(cases, scenarios, casesPerScenario)

  // 2. 判断是否全部达标
  const allSatisfied = scenarioCounts.every(s => s.satisfied)
  const totalDeficit = scenarioCounts.reduce((sum, s) => sum + s.deficit, 0)

  // 3. 如果不达标，构建指导意见
  let guidance: CaseGenerationGuidance | null = null
  if (!allSatisfied) {
    const scenariosToReplenish = scenarioCounts
      .filter(s => !s.satisfied)
      .map(s => ({
        scenarioId: s.scenarioId,
        scenarioName: s.scenarioName,
        needCount: s.deficit,
      }))

    guidance = {
      scenariosToReplenish,
      guidance: `为以下 ${scenariosToReplenish.length} 个场景补充用例：${scenariosToReplenish
        .map(s => `${s.scenarioName}(${s.needCount}个)`)
        .join('、')}`,
      totalNeeded: totalDeficit,
    }
  }

  return {
    satisfied: allSatisfied,
    scenarioCounts,
    totalDeficit,
    guidance,
    stopReason: allSatisfied
      ? `所有 ${scenarios.length} 个场景均已达到 ${casesPerScenario} 个用例`
      : undefined,
  }
}

/**
 * 打印用例统计报告
 */
export function printCaseCountReport(result: CaseJudgementResult): void {
  console.log('\n=== 用例生成进度报告 ===')
  console.log(`总体状态: ${result.satisfied ? '✓ 达标' : '✗ 有缺口'}`)
  console.log(`总缺口: ${result.totalDeficit} 个用例\n`)

  console.log('各场景明细:')
  for (const stat of result.scenarioCounts) {
    const status = stat.satisfied ? '✓' : '✗'
    console.log(
      `  ${status} ${stat.scenarioName}: ${stat.currentCount}/${stat.expectedCount}` +
        (stat.deficit > 0 ? ` (缺 ${stat.deficit})` : '')
    )
  }

  if (result.guidance) {
    console.log(`\n指导意见: ${result.guidance.guidance}`)
  }
  console.log('======================\n')
}
