/**
 * Scenario Pattern Generator - 场景模式生成器
 *
 * 基于 Plan（已剥离 scenario_patterns）独立生成场景模式列表。
 * 这是 Plan 的下游产物，作为场景生成循环的「执行蓝图」。
 *
 * 设计目的：
 * - 把 scenario_patterns 从 Plan 中剥离，降低用户在 Plan 确认环节的认知负担
 * - Plan 只描述「测什么、测多少、怎么理解」，patterns 由 Plan 派生
 * - 用户无需介入 patterns 生成，全自动执行
 */

import { OpenAI, zodTextFormat, invokeWithRetry } from '@eval-platform/llm'
import { z } from 'zod'
import type { ScenarioPlan } from '@eval-platform/database/models/scenario-plan'
import { TagTree, previewTagTree } from '../core/tag-tree.js'
import { getFullExpertIdentity, getThinkingFramework, EXPERT_OUTPUT_STANDARDS, buildHardConstraintsSection, buildHardConstraintsDesignRule } from './prompt-templates.js'

/**
 * Pattern Generator LLM 输出 Schema
 */
const PatternOutputSchema = z.object({
  scenario_patterns: z
    .array(z.string())
    .min(1)
    .describe('场景模式列表，每个模式描述清晰具体（如"单轮直达空调开关控制场景"）'),
})

type PatternOutput = z.infer<typeof PatternOutputSchema>

const patternOutputJsonSchema = zodTextFormat(PatternOutputSchema, 'pattern_output')

const PATTERN_OUTPUT_SCHEMA: OpenAI.Responses.ResponseTextConfig = {
  format: patternOutputJsonSchema,
}

/**
 * 构建 Pattern Generator Prompt
 *
 * 基于 Plan 的 task_description / target_tags / interpretation_notes + 完整标签树，
 * 设计从最简单到最复杂的全谱系场景模式。
 */
function buildPatternGeneratorPrompt(plan: ScenarioPlan, tagTree: TagTree): string {
  const treeVisualization = previewTagTree(tagTree, {
    showTree: true,
    showLeafList: false,
    title: '完整标签树结构（含层级关系）',
  })

  const expertBase = `${getFullExpertIdentity()}

${getThinkingFramework()}

${EXPERT_OUTPUT_STANDARDS}`

  return `${expertBase}

现在，你需要基于已经确认的场景生成计划（Plan），设计多样化的场景模式矩阵。

## 已确认的 Plan 信息

### 任务描述
${plan.task_description}

### 目标覆盖标签（共 ${plan.target_tags.length} 个）
${plan.target_tags.map((t, i) => `${i + 1}. ${t}`).join('\n')}

### 需求理解与专家洞察
${plan.interpretation_notes}

${buildHardConstraintsSection(plan.hard_constraints)}

## 完整标签树结构
${'```'}
${treeVisualization}
${'```'}

## 你的设计任务

基于 Plan 的复杂度维度分析，在 **task_description 和硬约束允许的范围内**设计**尽量丰富、多样化**的场景模式。

### ⚠️ 谱系覆盖服从 task_description（最高优先级）

下方"谱系覆盖"是一个**参考框架**，不是机械清单。**所有 pattern 必须严格遵守 task_description 和硬约束中的限定**。

**如何识别 task_description 中的限定**：仔细阅读 task_description，找出其中对以下方面的限定词：
- **交互模式限定**：如对话轮次、会话跨度、调用次数等
- **能力范围限定**：如必须使用某能力、禁止使用某能力、排除某类技能等
- **主题范围限定**：如限定在某个主题领域、排除某类问题等
- **任务类型限定**：如限定查询类、操作类、拒绝类等
- **难度/性质限定**：如常见问题、复杂问题、边界情况等

**服从规则**：对识别出的每条限定，生成的 pattern 必须在该限定范围内设计。若某限定排除了某类 pattern，则该类 pattern 不得出现。

**边界判断**：注意区分"限定"与"附带说明"。某限定禁止的是"用户主动要求执行某类动作"，那么该动作作为其他任务的自然副产物出现时，并不构成违反。对每条限定都做类似辨析，避免过度收紧或过度放宽。

**自检**：设计每个 pattern 前，先问自己"这个 pattern 是否违反 task_description 的任何限定？"若违反，立即剔除。

### 🔥 发散思维引导（在约束范围内穷举情境）

**不要每个维度只设计 1-2 个 pattern 就停手**。一个合格的 Pattern Generator 应该像专家做产品调研一样，**穷举 task_description 主题下的各类真实情境**，再把每个情境与下方维度交叉。

**第一步：情境穷举**。先在 task_description 主题下，列出主题所涵盖的真实具体情境。穷举方法：

1. **主题领域拆解**：把 task_description 的主题拆成它自然涵盖的若干子领域。一个广泛主题通常包含 5-15 个子领域，一个狭窄主题可能只有 1-3 个。
2. **子领域情境化**：每个子领域再细化为车主真实会遇到的具体情境（不是抽象类别，是落到"某次具体出行/某次具体用车"级别的场景）。
3. **穷举完所有子领域**：不要只覆盖前 2-3 个子领域就停手。必须遍历所有拆出的子领域。

**第二步：情境 × 维度交叉**。把穷举出的每个情境，与下方"谱系覆盖参考框架"的维度做交叉，派生出多个 pattern。同一个情境与不同维度交叉，会产生不同的 pattern。

**示例（仅说明交叉方法，不限定主题）**：若某情境为 X，则：
- X × 任务复杂度 → "X 单任务直达场景"、"X 多步骤依赖场景"、"X 长链路场景"
- X × 意图表达 → "X 显式意图场景"、"X 隐式推断场景"
- X × 流程类型 → "X 标准流程场景"、"X 边界条件场景"

### 谱系覆盖参考框架（在约束范围内适用）

在 task_description 和硬约束允许的范围内，尽量覆盖以下维度：
- **交互轮次**：从单轮直达 → 多轮渐进 → 跨轮延续（若 task_description 限定单轮，则只取"单轮直达"）
- **会话跨度**：从单次会话完成 → 跨会话记忆依赖（若 task_description 限定单轮，则只取"单次会话"）
- **任务复杂度**：从单任务直达 → 多步骤依赖 → 多任务并行编排 → 长链路任务
- **意图表达**：从显式明确表达 → 隐式需要推断 → 高度模糊需要澄清
- **流程类型**：从标准正常流程 → 真正的边界条件 → 异常处理 → 安全合规拒绝
- **能力组合**：在 task_description 允许的能力范围内做交叉组合

${buildHardConstraintsDesignRule(plan.hard_constraints)}

## 专家级设计原则

- 每个场景模式应体现 15 年产品专家的深度洞察
- 模式描述应具体、可测，避免笼统的"测试 XX 功能"
- **应用安全判断原则**：区分真正的危险操作与合理的舒适操作，避免过度泛化
- **数量预期**：pattern 数量应**与 task_description 主题的泛化空间相称**。主题越广（涵盖的子领域越多），pattern 应越多。具体参考：
  - 主题涵盖 1-3 个子领域（狭窄）：5-15 个 pattern
  - 主题涵盖 4-7 个子领域（中等）：15-30 个 pattern
  - 主题涵盖 8+ 个子领域（广泛）：30-60+ 个 pattern
  - 若拿不准主题广度，宁可多生成。不要止步于 10-15 个就停手。
- **必须使用中文描述场景模式**（如"跨会话记忆空调偏好场景"）

## 输出要求

**【语言要求】所有输出必须使用中文**：
- **scenario_patterns**: 基于上述分析的中文场景模式列表，每个模式描述清晰具体（如"单轮直达空调开关控制场景"、"多轮温度调节场景"）

请基于 Plan 和标签树结构，生成全面的场景模式列表。**确保所有文本内容均使用中文输出。**
`
}

/**
 * 基于已确认的 Plan 生成场景模式列表
 *
 * @param plan - 已确认的场景生成计划（不含 scenario_patterns）
 * @param tagTree - 标签树实例
 * @param client - OpenAI 客户端
 * @returns 场景模式列表（string[]）
 */
/**
 * Pattern Generator 返回值
 */
export interface ScenarioPatternResult {
  /** 场景模式列表 */
  patterns: string[]
  /** 目标场景数（由 Pattern Generator 基于 pattern 数和标签数计算） */
  targetScenarioCount: number
}

/**
 * 基于已确认的 Plan 生成场景模式列表和目标场景数
 *
 * @param plan - 已确认的场景生成计划
 * @param tagTree - 标签树实例
 * @param client - OpenAI 客户端
 * @returns { patterns, targetScenarioCount }
 */
export async function generateScenarioPatterns(
  plan: ScenarioPlan,
  tagTree: TagTree,
  client: OpenAI
): Promise<ScenarioPatternResult> {
  console.log('\n========================================')
  console.log('   Scenario Pattern Generator')
  console.log('========================================')
  console.log(`  Plan 目标标签数: ${plan.target_tags.length}`)

  const prompt = buildPatternGeneratorPrompt(plan, tagTree)

  console.log('\n[生成场景模式列表...]')

  const output = await invokeWithRetry<PatternOutput>(
    client,
    {
      input: prompt,
      text: PATTERN_OUTPUT_SCHEMA,
      temperature: 0.7,
    },
    3
  )

  const patterns = output.scenario_patterns

  // 基于 pattern 数计算目标场景数
  // 不变量：targetScenarioCount >= patterns.length（每个 pattern 至少 1 个场景）
  // 同时兼顾标签覆盖维度：每个标签至少被覆盖 2 次
  const minByPatterns = patterns.length
  const minByTags = plan.target_tags.length * 2
  const targetScenarioCount = Math.max(10, minByPatterns, minByTags)

  console.log('\n========================================')
  console.log('   Pattern 生成完成')
  console.log('========================================')
  console.log(`  场景模式数: ${patterns.length}`)
  console.log(`  目标场景数: ${targetScenarioCount}（max(10, ${minByPatterns}, ${minByTags})）`)
  patterns.forEach((p, i) => console.log(`    ${i + 1}. ${p}`))
  console.log('========================================\n')

  return { patterns, targetScenarioCount }
}
