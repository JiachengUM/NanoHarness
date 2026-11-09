/**
 * 场景生成模块
 *
 * 主入口：generateScenarios
 * 完整封装了「生成→审核→修复→判别→迭代」的整个流程。
 *
 * 使用示例：
 * ```typescript
 * import { generateScenarios } from '@eval-platform/makedata'
 *
 * const result = await generateScenarios(
 *   '生成危险车控场景',
 *   tagTree,
 *   client,
 *   { maxIterations: 10 }
 * )
 *
 * console.log(`生成 ${result.scenarios.length} 个优质场景`)
 * console.log(`覆盖 ${result.finalCoveragePercentage}% 相关标签`)
 * ```
 */

// 主入口：完整迭代生成
export {
  generateScenarios,
  type GenerateScenariosOptions,
  type GenerateScenariosResult,
} from './scenario-core.js'

// 底层生成器（高级使用）
export {
  generateRawScenarios,
  generateAndRefineBatch,
  buildScenarioGenerationPrompt,
  type GenerationGuidance,
} from './scenario-generator.js'

// 判别器（高级使用）
export {
  judgeScenarioCoverage,
  analyzeRelevantTagCoverage,
  type JudgementResult,
  type TagCoverage,
} from './scenario-judge.js'

// 审核器（高级使用）
export {
  auditScenarios,
  auditOneScenario,
  fixScenariosByAudit,
  type ScenarioAuditResult,
  type ScenarioAuditIssue,
  type ScenarioAuditDimension,
  type ScenarioAuditSeverity,
} from './scenario-audit.js'

// 用例生成
export {
  generateCasesFromScenarios,
  generateAndRefineCases,
} from './case.js'

// 用例判别器（高级使用）
export {
  judgeCaseGeneration,
  printCaseCountReport,
  type CaseJudgementResult,
  type CaseGenerationGuidance,
  type ScenarioCaseCount,
} from './case-judge.js'

// Scenario Planner（场景生成计划器）
export {
  generateScenarioPlan,
} from './scenario-planner.js'

// Scenario Pattern Generator（场景模式生成器）
export {
  generateScenarioPatterns,
} from './scenario-pattern-generator.js'
