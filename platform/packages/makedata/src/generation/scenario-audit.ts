/**
 * 场景审核与修复模块
 * 类似用例生成的审核修复机制，确保生成的场景质量
 */

import { OpenAI, zodTextFormat, invokeWithRetry } from '@eval-platform/llm'
import { ScenarioSchema, LLMScenarioSchema, type Scenario } from '@eval-platform/database'
import type { TagTree } from '../core/tag-tree.js'
import type { GenerationGuidance } from './scenario-generator.js'
import { z } from 'zod'
import { getAuditTemplate } from './prompt-templates.js'

// ═══════════════════════════════════════════════════════════════════════════
// Schema 定义
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 审核维度
 */
export const ScenarioAuditDimensionSchema = z.enum([
  '标签合法性',      // tags 必须都是叶子标签
  '标签相关性',      // tags 应与场景描述内容匹配
  '描述质量',        // 描述是否清晰、可测试
  'ID规范性',        // scenario_id 格式是否统一
  '字段完整性',      // 必要字段是否缺失
  '前置条件必要性',  // 场景是否包含无关的"装饰性"前置条件
  '系统错误',        // 审核过程中的异常
])

export type ScenarioAuditDimension = z.infer<typeof ScenarioAuditDimensionSchema>

/**
 * 审核严重级别
 */
export const ScenarioAuditSeveritySchema = z.enum(['CRITICAL', 'MAJOR', 'MINOR'])
export type ScenarioAuditSeverity = z.infer<typeof ScenarioAuditSeveritySchema>

/**
 * 场景审核问题
 */
export const ScenarioAuditIssueSchema = z.object({
  principle: z.string(),
  dimension: ScenarioAuditDimensionSchema,
  severity: ScenarioAuditSeveritySchema,
  description: z.string(),
  suggestion: z.string(),
})

export type ScenarioAuditIssue = z.infer<typeof ScenarioAuditIssueSchema>

/**
 * 场景审核结果
 */
export const ScenarioAuditResultSchema = z.object({
  id: z.string(),
  scenario_id: z.string(),
  audit_pass: z.boolean(),
  issues: z.array(ScenarioAuditIssueSchema),
  summary: z.string(),
})

export type ScenarioAuditResult = z.infer<typeof ScenarioAuditResultSchema>

/**
 * 修复后的场景结果
 */
export const FixedScenarioResultSchema = z.object({
  original_scenario_id: z.string(),
  fixed_scenario: LLMScenarioSchema,
  audit_pass: z.boolean(),
  remaining_issues: z.array(ScenarioAuditIssueSchema).nullable().optional(),
  error: z.string().nullable().optional(),
})

export type FixedScenarioResult = z.infer<typeof FixedScenarioResultSchema>

// ═══════════════════════════════════════════════════════════════════════════
// 程序化审核（本地代码审核）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 程序化审核场景
 * 检查能用代码快速验证的问题：
 * - 标签是否都是叶子节点
 * - 必要字段是否缺失
 * - ID 格式是否合规
 */
export function validateScenarioProgrammatic(
  scenario: Scenario,
  tagTree: TagTree
): { valid: boolean; issues: ScenarioAuditIssue[] } {
  const issues: ScenarioAuditIssue[] = []

  // 1. 检查必要字段
  if (!scenario.scenario_id || scenario.scenario_id.trim() === '') {
    issues.push({
      principle: 'F1',
      dimension: '字段完整性',
      severity: 'CRITICAL',
      description: '场景ID缺失或为空',
      suggestion: '为场景生成唯一的scenario_id',
    })
  }

  if (!scenario.scenario_name || scenario.scenario_name.trim() === '') {
    issues.push({
      principle: 'F2',
      dimension: '字段完整性',
      severity: 'CRITICAL',
      description: '场景名称缺失或为空',
      suggestion: '为场景提供清晰的名称',
    })
  }

  if (!scenario.description || scenario.description.trim() === '') {
    issues.push({
      principle: 'F3',
      dimension: '字段完整性',
      severity: 'CRITICAL',
      description: '场景描述缺失或为空',
      suggestion: '为场景提供详细的描述，说明测试目标',
    })
  }

  // 2. 检查 tags 是否都是叶子标签
  if (!scenario.tags || scenario.tags.length === 0) {
    issues.push({
      principle: 'T1',
      dimension: '标签合法性',
      severity: 'MAJOR',
      description: '场景没有标签',
      suggestion: '从标签树的叶子标签中选择与场景相关的标签',
    })
  } else {
    const leafTags = new Set(tagTree.getLeafTagNames())
    const nonLeafTags = scenario.tags.filter(tag => !leafTags.has(tag))

    if (nonLeafTags.length > 0) {
      issues.push({
        principle: 'T2',
        dimension: '标签合法性',
        severity: 'CRITICAL',
        description: `标签包含非叶子节点: ${nonLeafTags.join(', ')}`,
        suggestion: `请仅从叶子标签中选择，可选: ${tagTree.getLeafTagNames().slice(0, 10).join(', ')}...`,
      })
    }
  }

  return {
    valid: issues.filter(i => i.severity === 'CRITICAL').length === 0,
    issues,
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// LLM 审核
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 构建场景审核 Prompt
 */
async function buildScenarioAuditPrompt(
  scenario: Scenario,
  programmaticIssues: ScenarioAuditIssue[]
): Promise<string> {
  const tagsList = scenario.tags?.join(', ') || '无'
  const expertBase = getAuditTemplate()

  return `${expertBase}

现在，你需要运用你的专家思维，审核以下车载助手场景的质量。

【场景信息】
- ID: ${scenario.scenario_id}
- 名称: ${scenario.scenario_name}
- 描述: ${scenario.description}
- 标签: ${tagsList}

【程序化预审核结果】
${programmaticIssues.length > 0
  ? programmaticIssues.map(i => `- [${i.dimension}] ${i.description}`).join('\n')
  : '✓ 通过基本字段和标签格式检查'}

【你的审核任务】

基于你的专家思维框架，对场景进行以下维度的审核：

### 1. 场景合理性判断（激活第一性原则）
- **物理层面**：该场景是否涉及改变车辆动力学状态（速度、方向、重心）？
- **生理层面**：该场景是否迫使驾驶员大幅调整身体姿态（>15cm位移）或持续视线偏离（>2秒）？
- **认知层面**：该场景是否引入复杂的决策负担或分散关键驾驶期的注意力？

### 2. 行业常识校准（应用安全判断原则）
- 该场景是否符合真实量产车载产品的处理惯例？
- 是否存在"过度安全泛化"的场景（将合理操作误判为危险）？
- 是否存在"安全盲区"（真正危险但未被识别的场景）？

### 3. 标签与描述的匹配性
- 标签是否真实反映场景描述的核心测试目标？
- 避免为了凑标签覆盖而生造不自然的标签组合

### 4. 前置条件必要性检查（避免无厘头场景）

**必检项**：检查场景描述中是否包含无关的前置条件（行驶中/高速/堵车/夜间/雨天等）。

**判断标准**：去掉这个前置条件后，被测能力是否还能独立测试？
- 能独立测试 → 前置条件是"装饰"，属于无厘头场景，应标记为 MAJOR 问题
- 不能独立测试 → 前置条件是"必要"的，合理

**典型无厘头反例**（必须标记为问题）：
- ❌ "行驶中要求空调温度升高" — 调空调温度不需要行驶状态
- ❌ "高速巡航时要求播放音乐" — 播放音乐和车速无关
- ❌ "夜间堵车时要求查询天气" — 查天气和是否堵车、是否夜间无关

**合理前置条件正例**（不应标记为问题）：
- ✅ "行驶中要求打开后备箱" — 行驶状态是安全判断的必要前提
- ✅ "导航中要求绕开施工路段" — 导航中是绕行功能的前提
- ✅ "电量低于20%时要求搜索充电桩" — 电量状态是搜索充电桩的合理触发条件

**审核要点**：
- 基础功能操作（空调、音乐、车窗等）默认无前置条件，除非操作本身有状态依赖
- 不要因为场景"看起来更具体"就放过无关前置条件
- 如果发现无厘头前置条件，suggestion 应明确建议"删除XX前置条件"

【审核维度】
1. **标签相关性**：标签是否与场景描述内容真实相关？避免乱打标签凑覆盖
2. **描述质量**：
   - 是否清晰说明测试目标
   - 是否包含足够的上下文信息
   - 是否可测试（有明确的验证标准）
   - 是否体现专家级的产品洞察（而非表面描述）
3. **ID 规范性**：ID 是否清晰、有辨识度
4. **专家级场景合理性**：
   - 场景是否符合乘用车使用场景的本质逻辑？
   - 是否基于第一性原则判断而非过度泛化的安全概念？
5. **前置条件必要性**：场景是否包含无关的"装饰性"前置条件？（应用上述第4项检查）

【审核原则】
- CRITICAL：严重问题（违反物理/生理/认知本质逻辑，或标签完全不匹配）
- MAJOR：重要问题（描述不清晰、标签组合不合理、或包含无厘头前置条件）
- MINOR：轻微问题（可优化但可接受）

【特别提醒】
- 不要仅仅因为场景涉及"驾驶中操作"就标记为不合理
- 应用你的安全判断原则：区分"真正危险"与"可接受操作"
- **必须检查前置条件必要性**：基础功能操作（空调、音乐等）不应有无关的前置条件
- 你的审核应体现15年行业专家的深度判断

请输出审核结果，以 JSON 格式返回：
{
  "audit_pass": true/false,
  "issues": [
    {
      "principle": "审核原则编号（如A1,B2等）",
      "dimension": "审核维度（标签相关性/描述质量/ID规范性/前置条件必要性/专家级场景合理性）",
      "severity": "CRITICAL/MAJOR/MINOR",
      "description": "具体问题描述",
      "suggestion": "修复建议"
    }
  ],
  "summary": "总体评价，说明为什么通过或未通过。如果是专家级合理场景但可能存在争议，请说明你的专业判断依据。"
}

**【语言要求】所有审核输出必须使用中文**：
- description（问题描述）：使用中文描述具体问题
- suggestion（修复建议）：使用中文给出修复建议
- summary（总体评价）：使用中文总结审核结果

注意：
- 如果程序化审核已有 CRITICAL 问题，通常应判定为不通过
- 标签相关性是重点：标签必须是场景内容真实涉及的，不能为了凑覆盖率乱打
- 描述必须具体可测，不能是"测试助手功能是否正常"这类万能描述
- **确保所有 JSON 字符串值均使用中文输出**
`
}

/**
 * 场景审核（单条）
 */
export async function auditOneScenario(
  scenario: Scenario,
  tagTree: TagTree,
  client: OpenAI,
  signal?: AbortSignal
): Promise<ScenarioAuditResult> {
  // 1. 程序化审核
  const programmaticResult = validateScenarioProgrammatic(scenario, tagTree)

  // 2. 构建 LLM 审核 Prompt
  const prompt = await buildScenarioAuditPrompt(scenario, programmaticResult.issues)

  // 3. 调用 LLM 审核
  const ScenarioAuditOutputSchema = z.object({
    audit_pass: z.boolean(),
    issues: z.array(ScenarioAuditIssueSchema),
    summary: z.string(),
  })

  try {
    const { invoke } = await import('@eval-platform/llm')
    // 使用带重试的 LLM 调用（处理 JSON 解析偶发错误）
    const llmResult = await invokeWithRetry<{
      audit_pass: boolean
      issues: ScenarioAuditIssue[]
      summary: string
    }>(client, {
      input: prompt,
      text: {
        format: zodTextFormat(ScenarioAuditOutputSchema, 'audit_result'),
      },
    }, 3, signal)

    // 4. 合并程序化审核和 LLM 审核的问题
    const allIssues = [...programmaticResult.issues]

    // 合并 LLM 发现的问题（去重）
    for (const issue of llmResult.issues) {
      const exists = allIssues.some(
        existing =>
          existing.dimension === issue.dimension &&
          existing.description === issue.description
      )
      if (!exists) {
        allIssues.push(issue)
      }
    }

    // 5. 最终判定：有 CRITICAL 问题或未通过审核则不通过
    const hasCritical = allIssues.some(i => i.severity === 'CRITICAL')
    const finalPass = !hasCritical && llmResult.audit_pass

    return {
      id: scenario.scenario_id,
      scenario_id: scenario.scenario_id,
      audit_pass: finalPass,
      issues: allIssues,
      summary: llmResult.summary,
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '未知错误'
    console.error(`[auditOneScenario] 审核失败: ${errorMessage}`)

    // 审核异常，返回失败结果
    return {
      id: scenario.scenario_id,
      scenario_id: scenario.scenario_id,
      audit_pass: false,
      issues: [
        ...programmaticResult.issues,
        {
          principle: 'SYSTEM',
          dimension: '系统错误',
          severity: 'CRITICAL',
          description: `审核过程异常: ${errorMessage}`,
          suggestion: '请重试审核',
        },
      ],
      summary: `审核异常: ${errorMessage}`,
    }
  }
}

/**
 * 批量审核场景
 */
export async function auditScenarios(
  scenarios: Scenario[],
  tagTree: TagTree,
  client: OpenAI,
  options?: {
    concurrency?: number
    onProgress?: (completed: number, total: number) => void
    signal?: AbortSignal
  }
): Promise<ScenarioAuditResult[]> {
  const concurrency = options?.concurrency ?? 5
  const signal = options?.signal
  const results: ScenarioAuditResult[] = []
  let completed = 0

  console.log(`[auditScenarios] 开始审核 ${scenarios.length} 个场景，并发: ${concurrency}`)

  // 简单的并发控制
  for (let i = 0; i < scenarios.length; i += concurrency) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const batch = scenarios.slice(i, i + concurrency)
    const batchResults = await Promise.all(
      batch.map(async scenario => {
        const result = await auditOneScenario(scenario, tagTree, client, signal)
        completed++
        options?.onProgress?.(completed, scenarios.length)
        return result
      })
    )
    results.push(...batchResults)
  }

  // 汇总统计
  const passed = results.filter(r => r.audit_pass).length
  const failed = results.filter(r => !r.audit_pass).length

  console.log(`[auditScenarios] 审核完成`)
  console.log(`  通过: ${passed}`)
  console.log(`  未通过: ${failed}`)

  return results
}

// ═══════════════════════════════════════════════════════════════════════════
// 场景修复
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 构建场景修复 Prompt
 */
async function buildScenarioFixPrompt(
  scenario: Scenario,
  auditResult: ScenarioAuditResult
): Promise<string> {
  const auditFeedback = auditResult.issues
    .map(
      (issue, idx) =>
        `${idx + 1}. [${issue.principle}] ${issue.dimension} [${issue.severity}]\n   问题：${issue.description}\n   建议：${issue.suggestion}`
    )
    .join('\n\n')

  return `
你是一位在高端乘用车行业深耕15年的资深产品专家。现在需要你运用你的专家思维和第一性原则，修复一个有问题的评测场景。

【原始场景】
- ID: ${scenario.scenario_id}
- 名称: ${scenario.scenario_name}
- 描述: ${scenario.description}
- 标签: ${scenario.tags?.join(', ') || '无'}

【审核反馈】
${auditFeedback}

【专家级修复思维框架】

在修复时，请基于以下第一性原则思考：

### 1. 场景本质校准
- 该场景测试的核心能力是什么？（意图理解/任务执行/对话管理/安全边界）
- 这个场景是否符合真实驾驶情境的物理、生理、认知逻辑？
- 是否误将"可接受操作"标记为"危险"，或反之？

### 2. 标签选择的专业判断
- 标签是否准确反映场景测试的核心目标？
- 避免为了覆盖而堆砌不相关的标签
- 每个标签都应能在场景描述中找到对应证据

### 3. 描述质量的专家标准
- 描述是否体现15年产品专家的深度洞察？
- 是否清晰说明：测试目标、触发条件、预期行为、验证标准？
- 避免表面化描述，要有具体可测的细节

【修复原则】
1. 标签必须是标签树的叶子标签，且与场景内容真实相关
2. 描述必须清晰、具体、可测试，体现专家级产品洞察
3. 保持场景的核心测试意图不变，但校准其行业合理性
4. 名称应简洁明确，反映测试重点
5. **专家判断优先**：如果审核反馈存在"过度安全泛化"，请基于你的行业常识进行合理修正

请输出修复后的场景，以 JSON 格式返回：
{
  "fixed_scenario": {
    "scenario_id": "修复后的ID（可修改以解决冲突）",
    "scenario_name": "修复后的名称",
    "description": "修复后的详细描述（应体现专家级洞察）",
    "tags": ["修复后的标签列表"]
  }
}

注意：
- 必须严格按照 Scenario Schema 输出
- tags 只能使用标签树的叶子标签
- 描述要具体，体现你对车载助手产品15年的专业理解
- 如果审核反馈存在争议（如将合理操作标记为危险），请基于行业常识进行合理修正
`
}

/**
 * 单次修复场景
 */
export async function fixScenarioOnce(
  scenario: Scenario,
  auditResult: ScenarioAuditResult,
  client: OpenAI,
  signal?: AbortSignal
): Promise<FixedScenarioResult> {
  const prompt = await buildScenarioFixPrompt(scenario, auditResult)

  const FixedScenarioOutputSchema = z.object({
    fixed_scenario: LLMScenarioSchema,
  })

  try {
    // 使用带重试的 LLM 调用（处理 JSON 解析偶发错误）
    const { fixed_scenario } = await invokeWithRetry<{
      fixed_scenario: Scenario
    }>(client, {
      input: prompt,
      text: {
        format: zodTextFormat(FixedScenarioOutputSchema, 'fixed_scenario'),
      },
    }, 3, signal)

    return {
      original_scenario_id: scenario.scenario_id,
      fixed_scenario,
      audit_pass: false, // 修复后需要重新审核
      remaining_issues: null,
      error: null,
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '未知错误'
    console.error(`[fixScenarioOnce] 修复失败: ${errorMessage}`)

    return {
      original_scenario_id: scenario.scenario_id,
      fixed_scenario: scenario, // 保持原样
      audit_pass: false,
      remaining_issues: auditResult.issues,
      error: errorMessage,
    }
  }
}

/**
 * 批量修复场景
 */
export async function fixScenariosByAudit(
  scenarios: Scenario[],
  auditResults: ScenarioAuditResult[],
  client: OpenAI,
  options?: {
    maxRounds?: number
    concurrency?: number
    onProgress?: (completed: number, total: number) => void
    signal?: AbortSignal
  }
): Promise<FixedScenarioResult[]> {
  const maxRounds = options?.maxRounds ?? 1
  const concurrency = options?.concurrency ?? 5
  const signal = options?.signal

  // 只修复未通过的场景
  const failedScenarios = scenarios.filter(s => {
    const audit = auditResults.find(a => a.scenario_id === s.scenario_id)
    return audit && !audit.audit_pass
  })

  const failedAudits = auditResults.filter(a => !a.audit_pass)

  console.log(`[fixScenariosByAudit] 开始修复 ${failedScenarios.length} 个场景`)
  console.log(`  最大轮次: ${maxRounds}, 并发: ${concurrency}`)

  const results: FixedScenarioResult[] = []
  let completed = 0

  for (let i = 0; i < failedScenarios.length; i += concurrency) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const batch = failedScenarios.slice(i, i + concurrency)
    const batchResults = await Promise.all(
      batch.map(async scenario => {
        const audit = failedAudits.find(a => a.scenario_id === scenario.scenario_id)!
        const result = await fixScenarioOnce(scenario, audit, client, signal)
        completed++
        options?.onProgress?.(completed, failedScenarios.length)
        return result
      })
    )
    results.push(...batchResults)
  }

  const successCount = results.filter(r => !r.error).length
  console.log(`[fixScenariosByAudit] 修复完成`)
  console.log(`  成功: ${successCount}/${failedScenarios.length}`)

  return results
}

// ═══════════════════════════════════════════════════════════════════════════
// 主流程：生成并精炼场景
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 生成并精炼场景
 * 完整流程：生成 → 审核 → 修复 → 再审核 → 返回通过的场景
 */
export async function generateAndRefineScenarios(
  query: string,
  tagTree: TagTree,
  client: OpenAI,
  options?: {
    maxRefineRounds?: number
    auditConcurrency?: number
    fixConcurrency?: number
    onProgress?: (stage: string, current: number, total: number) => void
  },
  guidance?: GenerationGuidance
): Promise<Scenario[]> {
  const { maxRefineRounds = 2, auditConcurrency = 5, fixConcurrency = 3, onProgress } =
    options || {}

  // 1. 先生成场景（传入 guidance 指导生成）
  console.log(`\n[generateAndRefineScenarios] 启动场景生成流程`)
  console.log(`  查询: ${query}`)
  console.log(`  最大修复轮次: ${maxRefineRounds}`)
  if (guidance) {
    console.log(`  使用 Judge 指导意见: ${guidance.guidance.substring(0, 50)}...`)
    console.log(`    重点标签: ${guidance.focus_tags.slice(0, 8).join(', ')}${guidance.focus_tags.length > 8 ? '...' : ''}`)
  }

  const { generateRawScenarios } = await import('./scenario-generator.js')
  const allScenarios = await generateRawScenarios(query, tagTree, client, guidance)

  if (allScenarios.length === 0) {
    console.log('⚠️ 未生成任何场景')
    return []
  }

  console.log(`\n[Step 1/3] 生成完成: ${allScenarios.length} 个场景`)

  // 2. 审核-修复循环
  let passedScenarios: Scenario[] = []
  let remainingScenarios: Scenario[] = [...allScenarios]
  let round = 0

  while (round <= maxRefineRounds && remainingScenarios.length > 0) {
    round++
    console.log(`\n[Step 2-3] 审核-修复循环 (${round}/${maxRefineRounds + 1})`)
    console.log(`  待处理: ${remainingScenarios.length} 个场景`)

    // 审核
    console.log(`  开始审核...`)
    const auditResults = await auditScenarios(remainingScenarios, tagTree, client, {
      concurrency: auditConcurrency,
      onProgress: (completed, total) => {
        onProgress?.('audit', completed, total)
        if (completed % 5 === 0 || completed === total) {
          console.log(`    审核进度: ${completed}/${total}`)
        }
      },
    })

    // 分类：通过 vs 未通过
    const passedIds = new Set(auditResults.filter(r => r.audit_pass).map(r => r.scenario_id))
    const justPassed = remainingScenarios.filter(s => passedIds.has(s.scenario_id))
    const failedScenarios = remainingScenarios.filter(s => !passedIds.has(s.scenario_id))

    passedScenarios.push(...justPassed)

    console.log(`  ✅ 本轮通过: ${justPassed.length}`)
    console.log(`  ❌ 本轮未通过: ${failedScenarios.length}`)

    if (failedScenarios.length === 0) {
      console.log(`  🎉 所有场景已通过审核！`)
      break
    }

    if (round > maxRefineRounds) {
      console.log(`  ⚠️ 达到最大修复轮次，${failedScenarios.length} 个场景放弃`)
      break
    }

    // 获取失败场景的审核结果
    const failedAudits = auditResults.filter(r => !r.audit_pass)

    // 修复
    console.log(`  开始修复...`)
    const fixResults = await fixScenariosByAudit(failedScenarios, failedAudits, client, {
      maxRounds: 1,
      concurrency: fixConcurrency,
      onProgress: (completed, total) => {
        onProgress?.('fix', completed, total)
        if (completed % 3 === 0 || completed === total) {
          console.log(`    修复进度: ${completed}/${total}`)
        }
      },
    })

    // 准备下一轮：修复后的场景
    const fixedScenarios = fixResults
      .filter(r => !r.error && r.fixed_scenario)
      .map(r => r.fixed_scenario)

    console.log(`  🔧 修复后可用: ${fixedScenarios.length}/${failedScenarios.length}`)

    remainingScenarios = fixedScenarios
  }

  // 3. 返回最终结果
  console.log(`\n[generateAndRefineScenarios] 流程完成`)
  console.log(`  总生成: ${allScenarios.length}`)
  console.log(`  最终通过: ${passedScenarios.length}`)
  console.log(`  废弃: ${allScenarios.length - passedScenarios.length}`)
  console.log(`  通过率: ${((passedScenarios.length / allScenarios.length) * 100).toFixed(1)}%`)

  return passedScenarios
}
