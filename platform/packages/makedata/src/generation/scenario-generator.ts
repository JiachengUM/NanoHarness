/**
 * 场景生成器（底层实现）
 *
 * 提供原始场景生成和批量生成+审核+修复的功能。
 * 这些函数通常不直接对外暴露，由 scenario-core.ts 统一调用。
 */

import { OpenAI, zodTextFormat, invokeWithRetry } from '@eval-platform/llm'
import { TagTree, previewTagTree } from '../core/tag-tree.js'
import { ScenarioListSchema, type Scenario } from '@eval-platform/database/models/scenario'
import { type GenerationGuidance } from '@eval-platform/database/models/scenario-judge'
import { getGenerationTemplate } from './prompt-templates.js'

export type { Scenario } from '@eval-platform/database/models/scenario'
export type { GenerationGuidance } from '@eval-platform/database/models/scenario-judge'

// 使用 zodTextFormat 从 Zod Schema 生成 OpenAI JSON Schema
const scenarioListJsonSchema = zodTextFormat(ScenarioListSchema, 'scenario_list')

const SCENARIO_LIST_SCHEMA: OpenAI.Responses.ResponseTextConfig = {
  format: scenarioListJsonSchema,
}

/**
 * 构建场景生成 Prompt
 *
 * @param query - 场景描述查询
 * @param tagTree - 标签树实例
 * @param guidance - 可选的指导意见（冷启动时为 undefined）
 */
export function buildScenarioGenerationPrompt(
  query: string,
  tagTree: TagTree,
  guidance?: GenerationGuidance
): string {
  // 获取标签树的可视化字符串
  const treeVisualization = previewTagTree(tagTree, {
    showTree: true,
    showLeafList: false,
    title: '车载助手评测标签树',
  })

  // 同时提供 JSON 结构的叶子标签列表供精确引用
  const leafTags = tagTree.getLeafTagNames()

  // 构建指导意见部分（如果有）
  let guidanceSection = ''
  if (guidance) {
    // 检查 guidance 中是否包含已生成场景信息
    const hasExistingScenarios = guidance.guidance.includes('【已生成场景参考】')
    
    guidanceSection = `
## 指导意见（基于上一轮生成结果的分析）

本次生成需要特别注意：
${guidance.guidance}

### 重点覆盖标签
${guidance.focus_tags.length > 0 ? guidance.focus_tags.join(', ') : '无特定要求'}

### 避免重复的标签（已充分覆盖）
${guidance.avoid_tags.length > 0 ? guidance.avoid_tags.slice(0, 20).join(', ') + (guidance.avoid_tags.length > 20 ? '...' : '') : '无'}

### 建议的场景类型
${guidance.scenario_types.length > 0 ? guidance.scenario_types.map(t => `- ${t}`).join('\n') : '根据设计需求自然设计'}

### 场景数量建议
${guidance.suggested_count ? `建议生成本批次 ${guidance.suggested_count} 个场景` : '根据需求自然决定'}

${hasExistingScenarios ? `### 避免重复要求
【重要】你必须确保生成的场景与「已生成场景参考」中的场景不同。从不同的角度、不同的情境、不同的标签组合来设计新场景。` : ''}

---
`
  }

  const expertBase = getGenerationTemplate()

  return `${expertBase}

现在，你需要基于这种专家级的产品思维，设计车载助手的评测场景。

## 场景细化设计需求
"""
${query}
"""

${guidanceSection}
## 可用标签树

### 完整树形结构（含层级关系）
\`\`\`
${treeVisualization}
\`\`\`

### 可用叶子标签清单（共 ${leafTags.length} 个）
${leafTags.map((tag, i) => `${i + 1}. ${tag}`).join('\n')}

## 场景设计原则

基于你的专家思维框架，设计场景时请遵循：

1. **场景驱动，非标签驱动**：先想车主真实会遇到的情境，再自然标注涉及的标签
2. **标签必须从叶子中选择**：只能使用「叶子标签清单」中的标签，不能自创
3. **标签组合需合理**：标签必须能在同一自然场景中共现，符合车载助手使用常识
4. **激活第一性原则**：评估场景时应用物理/生理/认知层面的分析
5. **应用安全判断原则**：区分真正的危险操作与合理的舒适操作，避免过度泛化"安全"概念
6. **覆盖多维度优先**：每个场景尽可能包含：
   - 至少1个产品功能类叶子（车控/导航/媒体/记忆/联网）
   - 至少1个通用对话能力类叶子（意图理解/对话推进）
   - 根据复杂度选择结构/难度类叶子（多轮对话/跨域联动等）
7. **⚠️ 标签选择服从任务描述（最高优先级）**：上方"场景细化设计需求"中的任务描述可能包含对交互模式、能力范围、主题、任务类型的限定。**标签选择必须与任务描述的限定一致**：
   - **识别限定**：仔细阅读任务描述，找出对交互模式（轮次/会话跨度）、能力范围（必须用/禁止用某能力）、主题范围、任务类型的限定词
   - **服从限定**：对每条限定，检查所选标签是否与之一致。若某标签的业务含义违反了某条限定，不得选择该标签
   - **辨析边界**：注意区分"限定"与"附带说明"。某限定禁止的是"用户主动要求执行某类动作"，那么该动作作为其他任务的自然副产物出现时，对应标签不构成违反
   - **自检**：选完标签后逐条对照任务描述，确认没有任何标签违反限定
${guidance ? `
8. **遵循指导意见**：本次生成应优先覆盖「重点覆盖标签」，避免使用「避免重复的标签」中已充分覆盖的标签` : ''}

## 专家级设计要求

- 场景必须是完全符合真实乘用车场景下的逻辑的
- 体现15年产品专家的深度洞察，避免表面化描述
- 符合行业常识和惯例，避免过度保守或过度开放

## 标签语义自审（输出前必须执行）

在最终确定每个场景的 tags 前，请逐条回顾所选标签的 description，问自己："这个标签的业务含义是否天然暗示了另一种标签或结构？"

**示例（不穷举）**：
- 选了"追问连续回答" → 它描述的是同一次对话内的追问，因此必须同时选"多轮对话"（如多轮对话_2到3轮）。
- 选了记忆类标签（如常用地点记忆、长期记忆调用）→ 它描述的是跨会话记忆能力，通常需要"多次多轮"来形成"生产→消费"闭环。
- 选了"多轮对话" → 场景结构上应是单会话内的多轮交互。
- 选了"多次多轮" → 场景结构上应是多次独立会话。

**动作**：检查当前标签组合是否存在"标签含义要求了某种结构，但组合里没体现"的情况。如果存在，请先调整 tags，再输出最终场景。不要依赖外部规则表，要靠对标签 description 的理解做常识推导。

## 输出要求

**【语言要求】所有内容必须使用中文输出**：
- 场景名称：10-20个汉字，简洁明了，概括场景核心（如"行驶中调节座椅按摩"）
- 描述：50-150个汉字，自然语言叙述车主行为和助手应展现的能力（体现专家级产品洞察）
- 标签：引用叶子标签清单中的中文标签名称，一字不差

**【内容要求】**：
- 场景数量：完全根据场景细化设计需求决定${guidance?.suggested_count ? `，本批次建议 ${guidance.suggested_count} 个` : ''}，不要强行凑数，如果用户没有明确数量要求，那么你必须穷举所有可能的场景，不要遗漏任何可能的场景，不要重复。
- 场景 ID：格式为 scenario-XXX（如 scenario-001, scenario-002）
- 场景名称：简洁明了，概括场景核心
- 描述：自然语言叙述车主行为和助手应展现的能力。描述中应体现专家级的产品洞察。
- 标签：每个场景 2-8 个标签，必须全部来自叶子标签清单

请基于你的专家经验和第一性原则，生成相应的场景列表。**确保所有文本内容（场景名称、描述、模式名称等）均使用中文输出。**
`.trim()
}

/**
 * 原始场景生成（不带审核修复）
 *
 * 这是最底层的生成函数，只负责调用 LLM 生成场景，不验证标签合法性。
 * 通常由 generateAndRefineBatch 调用，不建议直接使用。
 *
 * @param query - 场景描述查询
 * @param tagTree - 标签树实例
 * @param client - OpenAI 客户端
 * @param guidance - 可选的指导意见
 * @returns 原始场景列表（未审核）
 */
export async function generateRawScenarios(
  query: string,
  tagTree: TagTree,
  client: OpenAI,
  guidance?: GenerationGuidance,
  signal?: AbortSignal
): Promise<Scenario[]> {
  const prompt = buildScenarioGenerationPrompt(query, tagTree, guidance)

  const params: OpenAI.Responses.ResponseCreateParamsNonStreaming = {
    instructions: prompt,
    input: query,
    text: SCENARIO_LIST_SCHEMA,
    temperature: 0.7,
  }

  if (guidance) {
    console.log('[generateRawScenarios] 带指导生成，查询: ' + query.substring(0, 50) + '...')
    console.log('  重点标签: ' + guidance.focus_tags.slice(0, 8).join(', ') + (guidance.focus_tags.length > 8 ? '...' : ''))
    console.log('  避免标签: ' + guidance.avoid_tags.length + ' 个')
    console.log('  建议数量: ' + (guidance.suggested_count || '未指定'))
  } else {
    console.log('[generateRawScenarios] 冷启动生成，查询: ' + query)
  }

  // 使用带重试的 LLM 调用（处理 JSON 解析偶发错误）
  const result = await invokeWithRetry<{ scenarios: Scenario[] }>(client, params, 3, signal)

  // 基础验证：检查标签是否都是叶子标签
  const leafTags = new Set(tagTree.getLeafTagNames())
  const invalidScenarios: { scenarioId: string; invalidTags: string[] }[] = []

  for (const scenario of result.scenarios) {
    const invalidTags = scenario.tags.filter(tag => !leafTags.has(tag))
    if (invalidTags.length > 0) {
      invalidScenarios.push({ scenarioId: scenario.scenario_id, invalidTags })
    }
  }

  if (invalidScenarios.length > 0) {
    console.warn('[generateRawScenarios] 警告: 以下场景包含非叶子标签:')
    for (const { scenarioId, invalidTags } of invalidScenarios) {
      console.warn('  - ' + scenarioId + ': ' + invalidTags.join(', '))
    }
  }

  console.log('[generateRawScenarios] 生成完成: ' + result.scenarios.length + ' 个场景')

  return result.scenarios
}

/**
 * 批量生成 + 审核 + 修复
 *
 * 一个完整的批次流程：
 * 1. 生成一批场景
 * 2. 审核这批场景
 * 3. 修复有问题的场景
 * 4. 产出优质场景（全部通过审核）
 *
 * @param query - 场景设计需求
 * @param tagTree - 标签树
 * @param client - LLM 客户端
 * @param options - 批次选项
 * @returns 通过审核的优质场景
 */
export async function generateAndRefineBatch(
  query: string,
  tagTree: TagTree,
  client: OpenAI,
  options: {
    batchSize: number
    guidance?: GenerationGuidance
    maxRefineRounds?: number
    auditConcurrency?: number
    fixConcurrency?: number
    shouldStop?: () => boolean
    signal?: AbortSignal
  }
): Promise<{
  scenarios: Scenario[]
  generatedCount: number
  auditedCount: number
  fixedCount: number
}> {
  const {
    batchSize,
    guidance,
    maxRefineRounds = 2,
    auditConcurrency = 5,
    fixConcurrency = 3,
    shouldStop,
    signal,
  } = options

  const checkStopped = () => {
    if (shouldStop?.()) throw new Error('GENERATION_CANCELLED')
  }

  console.log('\n[generateAndRefineBatch] 启动批次流程')
  console.log('  目标批次大小: ' + batchSize)

  checkStopped()

  // Step 1: 生成
  console.log('\n  [1/3] 生成场景...')

  // 调整 guidance 中的建议数量为本批次大小
  const batchGuidance: GenerationGuidance | undefined = guidance
    ? { ...guidance, suggested_count: batchSize }
    : { focus_tags: [], avoid_tags: [], scenario_types: [], guidance: '', suggested_count: batchSize }

  const rawScenarios = await generateRawScenarios(query, tagTree, client, batchGuidance, signal)

  if (rawScenarios.length === 0) {
    console.log('  ⚠️ 未生成任何场景')
    return { scenarios: [], generatedCount: 0, auditedCount: 0, fixedCount: 0 }
  }

  console.log('  生成完成: ' + rawScenarios.length + ' 个场景')

  checkStopped()

  // Step 1.5: 程序化初筛（快速剔除明显有问题的场景，减少 LLM 审核负担）
  const { validateScenarioProgrammatic } = await import('./scenario-audit.js')
  const preScreenResults = rawScenarios.map(s => ({
    scenario: s,
    validation: validateScenarioProgrammatic(s, tagTree),
  }))

  const prePassedScenarios = preScreenResults
    .filter(r => r.validation.valid)
    .map(r => r.scenario)

  const preFailedScenarios = preScreenResults
    .filter(r => !r.validation.valid)
    .map(r => r.scenario)

  if (preFailedScenarios.length > 0) {
    console.log(`  [程序化初筛] 快速剔除 ${preFailedScenarios.length} 个明显有问题的场景：`)
    preScreenResults
      .filter(r => !r.validation.valid)
      .forEach(r => {
        const criticalIssues = r.validation.issues.filter(i => i.severity === 'CRITICAL')
        console.log(`    - ${r.scenario.scenario_id}: ${criticalIssues.map(i => i.description).join(', ')}`)
      })
  }
  console.log(`  [程序化初筛] ${prePassedScenarios.length}/${rawScenarios.length} 个场景进入 LLM 审核`)

  checkStopped()

  // Step 2 & 3: 审核 + 修复循环
  const { auditScenarios, fixScenariosByAudit } = await import('./scenario-audit.js')

  let passedScenarios: Scenario[] = []
  let remainingScenarios: Scenario[] = [...prePassedScenarios]
  let totalFixed = 0
  let round = 0

  while (round < maxRefineRounds && remainingScenarios.length > 0) {
    checkStopped()
    round++
    console.log('\n  [2-3/3] 审核-修复循环 (' + round + '/' + maxRefineRounds + ')')
    console.log('    待处理: ' + remainingScenarios.length + ' 个场景')

    // 审核（LLM 深度审核，只处理通过程序化初筛的场景）
    console.log('    开始审核...')
    const auditResults = await auditScenarios(remainingScenarios, tagTree, client, {
      concurrency: auditConcurrency,
      signal,
    })

    checkStopped()

    // 分类：通过 vs 未通过
    const passedIds = new Set(auditResults.filter(r => r.audit_pass).map(r => r.scenario_id))
    const justPassed = remainingScenarios.filter(s => passedIds.has(s.scenario_id))
    const failedScenarios = remainingScenarios.filter(s => !passedIds.has(s.scenario_id))

    passedScenarios.push(...justPassed)

    console.log('    本轮通过: ' + justPassed.length)
    console.log('    本轮未通过: ' + failedScenarios.length)

    if (failedScenarios.length === 0) {
      console.log('    所有场景已通过审核！')
      break
    }

    if (round >= maxRefineRounds) {
      console.log('    达到最大修复轮次，放弃 ' + failedScenarios.length + ' 个场景')
      break
    }

    // 获取失败场景的审核结果
    const failedAudits = auditResults.filter(r => !r.audit_pass)

    // 修复
    console.log('    开始修复...')
    const fixResults = await fixScenariosByAudit(failedScenarios, failedAudits, client, {
      maxRounds: 1,
      concurrency: fixConcurrency,
      signal,
    })

    checkStopped()

    // 准备下一轮：修复后的场景
    const fixedScenarios = fixResults
      .filter(r => !r.error && r.fixed_scenario)
      .map(r => r.fixed_scenario)

    totalFixed += fixedScenarios.length
    console.log('    修复后可用: ' + fixedScenarios.length + '/' + failedScenarios.length)

    remainingScenarios = fixedScenarios
  }

  console.log('\n[generateAndRefineBatch] 批次完成')
  console.log('  原始生成: ' + rawScenarios.length)
  console.log('  程序化初筛通过: ' + prePassedScenarios.length)
  console.log('  最终通过审核: ' + passedScenarios.length)
  console.log('  修复成功: ' + totalFixed)

  return {
    scenarios: passedScenarios,
    generatedCount: rawScenarios.length,
    auditedCount: passedScenarios.length,
    fixedCount: totalFixed,
  }
}
