/**
 * Scenario Planner - 场景生成计划器
 *
 * 将用户模糊 query 转换为结构化的生成计划。
 * Planner 直接看到完整的标签树结构，自主：
 * 1. 理解标签树层级和分类
 * 2. 识别与 query 相关的标签
 * 3. 生成完整的 Plan（不再包含 scenario_patterns，patterns 由独立的 Pattern Generator 生成）
 */

import { OpenAI, zodTextFormat, invokeWithRetry } from '@eval-platform/llm'
import {
  PlannerOutputSchema,
  type PlannerOutput,
  type ScenarioPlan,
} from '@eval-platform/database/models/scenario-plan'
import { TagTree, previewTagTree } from '../core/tag-tree.js'
import { getPlanningTemplate } from './prompt-templates.js'

// 使用 zodTextFormat 从 Zod Schema 生成 OpenAI JSON Schema
const plannerOutputJsonSchema = zodTextFormat(PlannerOutputSchema, 'planner_output')

const PLANNER_OUTPUT_SCHEMA: OpenAI.Responses.ResponseTextConfig = {
  format: plannerOutputJsonSchema,
}

/**
 * 构建 Planner Prompt
 * 通用化设计：不绑定具体标签树结构，让 LLM 自主分析标签树
 * 注意：本 Prompt 不再要求生成 scenario_patterns，patterns 由独立的 Pattern Generator 负责
 */
function buildPlannerPrompt(query: string, tagTree: TagTree): string {
  // 获取完整的标签树可视化（包含层级结构）
  const treeVisualization = previewTagTree(tagTree, {
    showTree: true,
    showLeafList: true,
    title: '完整标签树结构',
  })

  const allLeafTags = tagTree.getLeafTagNames()

  const expertBase = getPlanningTemplate()

  return `${expertBase}

你的任务是将用户的模糊需求转换为详细的、可执行的场景生成计划。

## 用户原始需求
"""${query}"""

## 完整标签树结构
以下是你可使用的完整标签体系，包含层级分类和所有叶子标签：

${'```'}
${treeVisualization}
${'```'}

## 你的分析任务

基于标签树的层级结构和你的专家思维框架，自主分析以下维度：

### 1. 理解标签树的整体架构（专家视角）
分析标签树的顶层划分，识别两大核心维度：
- **产品功能维度**：具体的业务功能标签（如车控、导航、媒体等具体能力）
- **通用能力维度**：与具体业务解耦的通用对话 Agent 能力（如意图理解、对话推进、任务编排、上下文记忆等）

**专家级洞察**：理解这些维度如何交叉组合形成真实的车载交互场景。

### 2. 识别交互复杂度维度（激活第一性原则）
从标签树中自主发现复杂度分层标签，基于物理/生理/认知层面分析：
- **单轮 vs 多轮**：最简单的单轮直达 vs 渐进复杂的多轮对话
- **单次会话 vs 跨会话**：单一会话内完成 vs 需要跨多轮/多会话延续（记忆累积）
- **单任务 vs 多任务/长链路**：单一目标直达 vs 多步骤依赖 vs 复杂任务编排
- **显式 vs 隐式**：用户明确表达 vs 需要推断隐含意图
- **正常 vs 异常/边界**：标准流程 vs 边界条件/异常处理/安全合规

**专家级校准**：应用你的安全判断原则，区分"真正的边界条件"与"过度泛化的安全概念"。

### 3. 识别相关标签（基于行业常识）
基于用户 query 和标签树描述中的**行业惯例**，从叶子标签列表中精确选出所有相关的标签名称。

**关键原则**：
- 不要仅因标签字面包含关键词就选择，要理解其背后的**功能本质**
- 应用安全判断原则：区分真正影响驾驶安全的操作与可被接受的操作
- 参考标签描述中的"行业惯例"（description 中的例子体现了真实使用模式）

## 输出要求

**【语言要求】所有输出必须使用中文**：
- **task_description**: 详细、准确、无歧义的中文生成任务描述，必须体现专家级的产品洞察和行业常识
- **interpretation_notes**: 你对用户需求的理解，以及对标签树结构的分析摘要，应体现15年专家的行业洞察

请生成一个场景生成计划，必须满足：

- **target_tags**: **【关键】必须从上述叶子标签列表中精确选择，只能使用列表中存在的中文标签名称，一字不差。** 选择时参考标签描述中的行业惯例，应用你的专家判断原则
- **task_description**: 详细、准确、无歧义的生成任务描述，Generator 和 Judge 将直接使用。必须体现专家级的产品洞察和行业常识。**必须完整保留原始query中的所有硬性约束**（数量、能力、主题、交互模式、难度等限定词），不得在改写中丢失或弱化。
- **interpretation_notes**: 你对用户需求的理解，以及对标签树结构的分析摘要，应体现15年专家的行业洞察
- **hard_constraints**: **【关键】从原始query中提取所有硬性约束**。每条约束按以下类型分类：
  - \`capability_required\`: 必须使用的能力（如 query 要求"仅通过X解决""必须用X工具"）
  - \`capability_excluded\`: 禁止使用的能力（如 query 要求"不涉及Y""不要Z类"）
  - \`interaction_pattern\`: 交互模式约束（如 query 要求"单轮对话""至少N次X""一次性"）
  - \`theme\`: 主题约束（如 query 限定"XX场景""XX相关"）
  - \`difficulty\`: 难度约束（如 query 要求"常见""不要太偏""复杂"）
  - \`other\`: 其他无法归类的硬约束
  
  **提取原则**：
  - **宁多勿漏**：query中任何明确的、隐含的、限定性的要求都应提取为硬约束。这些约束将贯穿后续所有环节（Pattern Generator、场景生成、Judge），违反硬约束的场景会被剔除。
  - **必须主动挖掘**：不要只看字面关键词。要理解 query 的**意图**，把隐含的限定也提取出来。例如（以下为通用示例，与本次 query 无关）：
    - "我想测助手能不能用好X工具" → 隐含 \`capability_required: 仅使用X工具\`
    - "不要是Y类的问题" → 隐含 \`capability_excluded: 禁止用户明确要求执行Y类任务\`（注：Y作为其他任务的副产物出现时不一定算违反，需根据语义判断）
    - "至少N次X操作" → \`interaction_pattern: 单轮内至少N次X操作\`
    - "一次性X" → \`interaction_pattern: 单轮对话\`（若"一次性"修饰的是对话轮次）
    - "不涉及任何其他Z" → \`capability_excluded: 不混入Z等其他能力\`
    - "XX场景""XX相关" → \`theme: XX主题\`
    - "常见""不要太偏""复杂""简单" → \`difficulty: 对应难度/性质限定\`
  - **无硬约束时**：若 query 确实没有任何限定（如"随便生成一些车载场景"），才返回空数组 \`[]\`。但**绝大多数测试 query 都含有硬约束**，请务必仔细挖掘。
  - **宁可多提取**：即使某条要求边界模糊（如"不要太偏"），也应提取为硬约束，让下游自行判断；不要因为"不确定算不算硬约束"就放弃提取。

## ⚠️ 硬约束提取强制扫描步骤（输出前必须执行）

在输出 plan 之前，**必须**对原始 query 执行以下扫描，并将扫描结果填入 hard_constraints：

1. **逐句扫描**：把 query 拆成句子/分句，逐句检查是否含限定词。
2. **限定词清单**（按类型）：
   - 数量/频次词："至少N次""一次性""最多""最少" → interaction_pattern
   - 能力要求词："只用""仅通过""必须使用""能不能用好" → capability_required
   - 能力排除词："不要""不涉及""排除""除了" → capability_excluded
   - 主题词："XX相关""XX类""属于XX" → theme
   - 难度/性质词："常见""不要太偏""复杂""简单" → difficulty
   - 交互模式词："单轮""多轮""一次性""串行""依赖" → interaction_pattern
3. **隐含挖掘**：除字面词外，还要理解 query 意图，挖掘隐含限定（如"我想测助手能不能用好X工具"隐含"仅用X工具"）。
4. **汇总**：把扫描到的所有限定汇总为 hard_constraints 数组。**只有当 query 确实无任何限定时才返回空数组**——这种情况极少。

## 重要原则

1. **自主分析**：不假设标签树的固定结构，根据实际提供的标签树自主分析
2. **精确匹配**：target_tags 必须精确匹配叶子标签列表，参考 description 中的行业惯例
3. **专家判断优先**：应用你的安全判断原则，区分真正的危险与合理操作
4. **结构无关**：适用于任何类似的评测标签体系
5. **中文输出**：所有文本字段（task_description、interpretation_notes、hard_constraints.description）必须使用中文
6. **硬约束完整保留**：task_description 必须完整体现所有硬约束，hard_constraints 必须结构化列出所有硬约束

请基于标签树的实际结构和你的15年行业专家经验，生成场景生成计划。**确保所有文本内容均使用中文输出。**
`
}

/**
 * 生成场景生成计划
 *
 * @param query - 用户原始查询
 * @param tagTree - 标签树实例
 * @param client - OpenAI 客户端
 * @returns 生成的 Plan（不包含 task_id / generation_task_run_id / scenario_patterns，需要外部补充）
 */
export async function generateScenarioPlan(
  query: string,
  tagTree: TagTree,
  client: OpenAI
): Promise<Omit<ScenarioPlan, 'task_id' | 'generation_task_run_id' | 'createdAt' | 'updatedAt'>> {
  console.log('\n========================================')
  console.log('   Scenario Planner')
  console.log('========================================')
  console.log(`  原始 Query: "${query.substring(0, 50)}${query.length > 50 ? '...' : ''}"`)

  const allLeafTags = tagTree.getLeafTagNames()
  console.log(`  标签树: ${allLeafTags.length} 个叶子标签`)

  // 生成 Plan（LLM 直接看到完整标签树，自主识别相关标签）
  console.log('\n[生成场景生成计划...]')
  const prompt = buildPlannerPrompt(query, tagTree)

  const output = await invokeWithRetry<PlannerOutput>(
    client,
    {
      input: prompt,
      text: PLANNER_OUTPUT_SCHEMA,
      temperature: 0.7,
    },
    3
  )

  const plan = output.plan

  // 验证 target_tags 都是有效的叶子标签
  const validLeafTags = new Set(allLeafTags)
  const invalidTags = plan.target_tags.filter(tag => !validLeafTags.has(tag))
  if (invalidTags.length > 0) {
    console.warn(`  [警告] Plan 包含无效标签，移除 ${invalidTags.length} 个`)
    plan.target_tags = plan.target_tags.filter(tag => validLeafTags.has(tag))
  }

  // 兜底：确保 hard_constraints 字段存在
  const hardConstraints = plan.hard_constraints || []

  console.log('\n========================================')
  console.log('   Plan 生成完成')
  console.log('========================================')
  console.log(`  目标场景数: 待 Pattern 生成后决定`)
  console.log(`  目标标签数: ${plan.target_tags.length}`)
  console.log(`  硬约束数: ${hardConstraints.length}`)
  if (hardConstraints.length > 0) {
    console.log(`  [硬约束列表]`)
    hardConstraints.forEach((c, i) => {
      console.log(`    ${i + 1}. [${c.type}] ${c.description}`)
    })
  }
  console.log('========================================\n')

  return {
    original_query: query,
    task_description: plan.task_description,
    target_tags: plan.target_tags,
    interpretation_notes: plan.interpretation_notes,
    hard_constraints: hardConstraints,
    status: 'pending',
    tag_tree_name: '', // 需要外部填充
  }
}
