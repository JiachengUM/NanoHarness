/**
 * 场景判别者模块（重构版）
 *
 * 核心原则：
 * 1. 完全不依赖硬编码维度/标签，所有判断基于标签树本身
 * 2. 判别针对"query相关的标签子集"，而非整个标签树
 * 3. 细化方向聚焦于补全query相关的未覆盖标签
 */

import { OpenAI, zodTextFormat, invokeWithRetry } from '@eval-platform/llm'
import { type Scenario } from '@eval-platform/database'
import {
  type JudgementResult,
  type GenerationGuidance,
  LLMJudgementOutputSchema,
  TagCoverageSchema,
} from '@eval-platform/database/models/scenario-judge'
import type { HardConstraint } from '@eval-platform/database/models/scenario-plan'
import type { TagTree } from '../core/tag-tree.js'
import { z } from 'zod'
import { getAuditTemplate, buildHardConstraintsSection } from './prompt-templates.js'

// ═══════════════════════════════════════════════════════════════════════════
// 重新导出类型（方便使用者）
// ═══════════════════════════════════════════════════════════════════════════

export type { JudgementResult, GenerationGuidance }
export { TagCoverageSchema }

// ═══════════════════════════════════════════════════════════════════════════
// 动态识别相关标签子集
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 识别与 query 相关的标签子集
 * 使用 LLM 分析 query 意图，返回相关的标签列表
 */
export async function identifyRelevantTags(
  query: string,
  allLeafTags: string[],
  tagTree: TagTree,
  client: OpenAI
): Promise<{
  relevantTags: string[]
  reasoning: string
}> {
  const prompt = `
你是一个场景设计需求分析专家。请分析用户的设计需求，识别出哪些标签是相关的。

【用户设计需求】
${query}

【可用标签列表】（共 ${allLeafTags.length} 个）
${allLeafTags.join(', ')}

【标签树结构预览】
${previewTagTreeStructure(tagTree)}

【任务】
1. 理解用户需求的领域和意图
2. 从标签列表中选出与需求相关的标签
3. 确保选出的标签能完整支撑用户的评测目标

【输出要求】
返回 JSON 格式，包含：
- relevant_tags: 相关标签数组（从上面列表中选择）
- reasoning: 选择理由，说明为什么这些标签与需求相关

注意：
- 只选择真正相关的标签，不要为了覆盖而多选
- 如果需求很明确（指向某类具体功能），就选与该功能相关的标签
- 如果需求是泛化的（如"日常使用场景"），可以选更多功能标签
`

  const RelevantTagsOutputSchema = z.object({
    relevant_tags: z.array(z.string()),
    reasoning: z.string(),
  })

  try {
    // 使用带重试的 LLM 调用（处理 JSON 解析偶发错误）
    const result = await invokeWithRetry<{
      relevant_tags: string[]
      reasoning: string
    }>(client, {
      input: prompt,
      text: {
        format: zodTextFormat(RelevantTagsOutputSchema, 'output'),
      },
    }, 3)

    // 验证返回的标签确实在列表中
    const validTags = result.relevant_tags.filter(tag => allLeafTags.includes(tag))
    
    console.log(`[识别相关标签] 需求: "${query.substring(0, 50)}..."`)
    console.log(`  相关标签: ${validTags.length}/${allLeafTags.length}`)
    console.log(`  理由: ${result.reasoning.substring(0, 100)}...`)

    return {
      relevantTags: validTags,
      reasoning: result.reasoning,
    }
  } catch (error) {
    console.error('[identifyRelevantTags] LLM 识别失败，回退到全部标签:', error)
    // 失败时回退到全部标签（保守策略）
    return {
      relevantTags: allLeafTags,
      reasoning: 'LLM 识别失败，使用全部标签作为回退',
    }
  }
}

/**
 * 为 Prompt 生成标签树结构预览
 */
function previewTagTreeStructure(tagTree: TagTree, maxDepth = 3): string {
  const lines: string[] = []
  
  function traverse(node: any, depth: number, prefix: string = '') {
    if (depth > maxDepth) return
    
    const isLeaf = !node.children || node.children.length === 0
    const marker = isLeaf ? '🍃' : '📁'
    lines.push(`${prefix}${marker} ${node.name}`)
    
    if (node.children) {
      for (const child of node.children.slice(0, isLeaf ? 0 : 5)) {
        traverse(child, depth + 1, prefix + '  ')
      }
      if (node.children.length > 5 && !isLeaf) {
        lines.push(`${prefix}  ...还有 ${node.children.length - 5} 个子节点`)
      }
    }
  }
  
  traverse(tagTree.root, 0)
  return lines.join('\n')
}

// ═══════════════════════════════════════════════════════════════════════════
// 程序化统计（仅针对相关标签子集）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 统计相关标签的覆盖情况
 */
export function analyzeRelevantTagCoverage(
  scenarios: Scenario[],
  relevantTags: string[]
): {
  tagCoverage: Record<string, number>
  coveredTags: Set<string>
  uncoveredTags: string[]
  avgTagsPerScenario: number
} {
  const relevantTagSet = new Set(relevantTags)
  const tagCoverage: Record<string, number> = {}
  const coveredTags = new Set<string>()

  // 统计每个相关标签的覆盖次数
  for (const scenario of scenarios) {
    for (const tag of scenario.tags) {
      if (relevantTagSet.has(tag)) {
        tagCoverage[tag] = (tagCoverage[tag] || 0) + 1
        coveredTags.add(tag)
      }
    }
  }

  // 找出未覆盖的相关标签
  const uncoveredTags = relevantTags.filter(tag => !coveredTags.has(tag))

  // 计算平均每场景标签数（只统计相关标签）
  let totalRelevantTags = 0
  for (const scenario of scenarios) {
    for (const tag of scenario.tags) {
      if (relevantTagSet.has(tag)) {
        totalRelevantTags++
      }
    }
  }
  const avgTagsPerScenario = scenarios.length > 0 ? totalRelevantTags / scenarios.length : 0

  return {
    tagCoverage,
    coveredTags,
    uncoveredTags,
    avgTagsPerScenario,
  }
}

/**
 * 评估覆盖深度（避免蜻蜓点水）
 * 检查是否有标签被覆盖得过于浅显（如只出现1次）
 */
function calculateCoverageDepth(
  tagCoverage: Record<string, number>,
  totalScenarios: number
): number {
  if (totalScenarios === 0 || Object.keys(tagCoverage).length === 0) return 0

  const coverages = Object.values(tagCoverage)
  
  // 计算平均覆盖次数
  const avgCoverage = coverages.reduce((a, b) => a + b, 0) / coverages.length
  
  // 计算有多少标签被"充分覆盖"（至少2次）
  const wellCovered = coverages.filter(c => c >= 2).length
  const wellCoveredRatio = wellCovered / coverages.length
  
  // 综合评分：平均覆盖 * 充分覆盖比例
  return Math.round((Math.min(avgCoverage / 2, 1) * 50 + wellCoveredRatio * 50))
}

// ═══════════════════════════════════════════════════════════════════════════
// 独立的场景去重检测（从 Judge 中拆出，LLM 全局识别重复组）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 重复场景组的判断结果
 *
 * 注意：OpenAI strict JSON schema 要求所有字段必须 required，可选字段用 nullable 而非 optional
 */
interface DuplicateGroup {
  /** 一组语义重复的场景 ID 列表（至少 2 个） */
  scenario_ids: string[]
  /** 在该组中保留的场景 ID（必须是 scenario_ids 中的一个） */
  keep: string
  /** 判断理由（中文） */
  reasoning: string
}

const DuplicateDetectionSchema = z.object({
  duplicate_groups: z.array(z.object({
    scenario_ids: z.array(z.string()),
    keep: z.string(),
    reasoning: z.string().describe('判断理由，必须使用中文'),
  })),
})

/**
 * 独立的场景去重检测函数
 *
 * 从 Judge 中拆出，只做一件事：识别语义重复的场景组并返回应移除的 ID。
 *
 * 策略：
 * - 不做程序化预筛（标签表述不一致会让 Jaccard 失效，例如 "单轮任务" vs "单轮对话"）
 * - 直接把所有场景的 ID + 名称 + 标签 + 描述交给 LLM
 * - LLM 自己聚类成重复组，每组保留一个
 * - 程序化回退仅在 LLM 调用失败时启用
 *
 * @returns 应被移除的 scenario_id 列表
 */
export async function detectDuplicateScenarios(
  scenarios: Scenario[],
  client: OpenAI,
): Promise<string[]> {
  if (scenarios.length < 2) return []

  console.log(`  [去重检测] 共 ${scenarios.length} 个场景，调用 LLM 全局识别重复组...`)

  const prompt = buildDuplicateDetectionPrompt(scenarios)

  try {
    const result = await invokeWithRetry<{ duplicate_groups: DuplicateGroup[] }>(client, {
      input: prompt,
      text: {
        format: zodTextFormat(DuplicateDetectionSchema, 'duplicate_detection'),
      },
    }, 3)

    // 用 set 防止同一 ID 被多个组重复计入
    const removeIds = new Set<string>()
    // 用 set 防止同一场景被分到多个组（取首次归属）
    const assignedIds = new Set<string>()
    let validGroupCount = 0

    for (const group of result.duplicate_groups) {
      // 仅处理合法的重复组（>=2 个 ID，且 keep 在列表中，且所有 ID 都存在于 scenarios 中）
      if (!Array.isArray(group.scenario_ids) || group.scenario_ids.length < 2) continue
      if (!group.keep || !group.scenario_ids.includes(group.keep)) continue

      const validIds = group.scenario_ids.filter(id =>
        scenarios.some(s => s.scenario_id === id) && !assignedIds.has(id)
      )
      if (validIds.length < 2) continue

      validGroupCount++
      assignedIds.add(group.keep)
      for (const id of validIds) {
        assignedIds.add(id)
        if (id !== group.keep) {
          removeIds.add(id)
        }
      }
      const removedList = validIds.filter(id => id !== group.keep)
      console.log(`    [重复组 ${validGroupCount}] 保留 ${group.keep}，移除 ${removedList.join(', ')}`)
      console.log(`              理由: ${group.reasoning}`)
    }

    console.log(`  [去重检测] LLM 识别 ${validGroupCount} 个重复组，共移除 ${removeIds.size} 个场景`)
    return [...removeIds]
  } catch (error) {
    console.error('  [去重检测] LLM 判断失败，回退到程序化规则:', error)
    return fallbackDedupByTags(findSuspectedDuplicatePairs(scenarios))
  }
}

/**
 * 程序化预筛疑似重复对（仅用于 LLM 失败时的回退）
 *
 * 规则：
 * 1. 标签完全相同 → 强疑似
 * 2. 标签 Jaccard 相似度 >= 0.7 → 中疑似
 * 3. 场景名相似度 >= 0.8 且标签重叠 >= 0.5 → 弱疑似
 */
function findSuspectedDuplicatePairs(scenarios: Scenario[]): Array<{ a: Scenario; b: Scenario; reason: string }> {
  const pairs: Array<{ a: Scenario; b: Scenario; reason: string }> = []

  for (let i = 0; i < scenarios.length; i++) {
    for (let j = i + 1; j < scenarios.length; j++) {
      const a = scenarios[i]
      const b = scenarios[j]
      const reason = checkSuspectedDuplicate(a, b)
      if (reason) {
        pairs.push({ a, b, reason })
      }
    }
  }

  return pairs
}

/**
 * 检查两个场景是否疑似重复（仅用于 LLM 失败时的回退）
 */
function checkSuspectedDuplicate(a: Scenario, b: Scenario): string | null {
  const setA = new Set(a.tags)
  const setB = new Set(b.tags)
  const intersection = new Set([...setA].filter(x => setB.has(x)))
  const union = new Set([...setA, ...setB])
  const jaccard = union.size === 0 ? 0 : intersection.size / union.size

  // 规则 1: 标签完全相同
  if (jaccard === 1) {
    return '标签完全相同'
  }

  // 规则 2: 标签 Jaccard 相似度 >= 0.7
  if (jaccard >= 0.7) {
    return `标签高度重叠 (Jaccard=${jaccard.toFixed(2)})`
  }

  // 规则 3: 场景名高度相似 且 标签重叠 >= 0.5
  const nameSim = calculateNameSimilarity(a.scenario_name, b.scenario_name)
  if (nameSim >= 0.8 && jaccard >= 0.5) {
    return `场景名高度相似 (${nameSim.toFixed(2)}) 且标签重叠 (${jaccard.toFixed(2)})`
  }

  return null
}

/**
 * 计算两个场景名的相似度（基于字符集的 Jaccard）
 */
function calculateNameSimilarity(a: string, b: string): number {
  const setA = new Set(a)
  const setB = new Set(b)
  const intersection = new Set([...setA].filter(x => setB.has(x)))
  const union = new Set([...setA, ...setB])
  return union.size === 0 ? 0 : intersection.size / union.size
}

/**
 * 构建去重检测的 LLM prompt（全局视角）
 *
 * 让 LLM 直接看全部场景列表，自己聚类成重复组。
 * 这样可以避免基于标签 Jaccard 的预筛失效问题
 * （例如 "单轮任务" 和 "单轮对话" 表述不一致但语义相同）。
 */
function buildDuplicateDetectionPrompt(scenarios: Scenario[]): string {
  const scenariosText = scenarios.map((s, i) => {
    return `### 场景 ${i + 1}
ID: ${s.scenario_id}
名称: ${s.scenario_name}
标签: ${s.tags.join('、')}
描述: ${s.description}`
  }).join('\n\n')

  return `你是测试场景的资深审核专家。你的唯一任务是：从下方场景列表中识别出**真正语义重复**的场景组。

**【语言要求】所有输出必须使用中文，特别是 reasoning 字段必须使用中文描述判断理由。**

## 核心设计原则

**场景描述的是"任务结构"，具体内容/参数/上下文的泛化是用例生成时的任务。**

一个场景可以生成多个用例（不同参数值、不同具体内容、不同环境上下文）。因此场景层面只关注"任务结构"，具体查询内容、参数值、场景上下文的差异**不构成不同场景**。

## 关键概念：任务结构

**任务结构**指的是完成一件事所需的操作结构，包括：
1. **交互轮次**：单轮直达 / 多轮确认 / 跨会话记忆
2. **任务复杂度**：单一任务 / 并行多任务 / 串行依赖任务
3. **查询结构**：简单直接查询 / 多步依赖查询 / 并列多源查询 / 条件筛选查询
4. **能力维度**：基础直达 / 口语别称理解 / 模糊指令理解 / 显式意图识别

**同样任务结构 + 同样能力维度 = 同一场景**（即使具体内容不同）
**不同任务结构 或 不同能力维度 = 不同场景**

## 判断标准

两个场景**当且仅当以下条件全部相同时**才视为重复：
1. **任务结构相同**（交互轮次、任务复杂度、查询结构一致）
2. **能力维度相同**（如都是测"基础直达"，而非一个测基础直达、另一个测口语别称理解）
3. **操作对象所属模块相同**（如都是同一个功能模块）

**以下差异不构成不同场景**（应视为重复）：
- 查询的具体内容不同（如查天气 vs 查新闻 vs 查股票，都是"单轮直接查询外部信息"）→ 用例层面泛化
- 参数值不同（如数值、幅度、级别差异）→ 用例层面泛化
- 场景上下文不同（如不同环境、不同人员、不同时段）→ 用例层面泛化
- 措辞不同（同一意图的不同表达）→ 同一意图

**以下差异构成不同场景**（不应视为重复）：
- 查询结构不同（如"单步直接查询" vs "多步依赖查询" vs "并列多源查询" vs "条件筛选查询"）
- 交互模式不同（如"单轮" vs "多轮确认" vs "跨会话记忆"）
- 任务复杂度不同（如"单纯执行一个任务" vs "并行执行多个任务" vs "串行依赖任务"）
- 能力维度不同（如"基础直达" vs "口语别称理解" vs "模糊指令理解"）
- 操作对象所属模块不同（不同功能模块）

## 典型重复示例（必须归入同一重复组）

- "单轮查询天气" 与 "单轮查询新闻" 与 "单轮查询股票" → **重复**（都是单轮直接查询外部信息，任务结构相同，具体查询内容是用例层面的事）
- "执行 A 操作增加 1 档" 与 "执行 A 操作增加" → 重复（档位数差异是用例层面的事）
- "把 A 设为 24" 与 "把 A 调到 24" 与 "把 A 设为 25" → 重复（参数值差异是用例层面的事，措辞差异也是同一意图）
- "场景 X 下执行 A 操作" 与 "场景 Y 下执行 A 操作" → **重复**（场景上下文差异是用例层面的事）
- "多人情况下查询 A" 与 "单人情况下查询 A" → **重复**（人员数差异是用例层面的事）

## 典型不重复示例（不要归入同一组）

- "单步直接查询 A" 与 "多步依赖查询 A（先查 X，再基于结果查 Y）" → **不重复**（查询结构不同）
- "单步直接查询 A" 与 "并列多源查询 A（同时查多个数据源对比）" → **不重复**（查询结构不同）
- "单步直接查询 A" 与 "条件筛选查询 A（按距离/评分/价格等条件筛选）" → **不重复**（查询结构不同）
- "增加 A" 与 "减少 A" → 不重复（操作方向不同）
- "单轮执行 A" 与 "多轮执行 A（含确认）" → 不重复（交互模式不同）
- "操作 A" 与 "操作 B" → 不重复（操作对象不同）
- "执行 A" 与 "执行 A 同时执行 B" → 不重复（任务复杂度不同）
- "标准指令执行 A（测基础直达）" 与 "口语指令执行 A（测口语别称理解）" → **不重复**（能力维度不同）

## 重要原则

- **场景描述任务结构**：具体查询内容、参数值、场景上下文、人员数、环境等细节是用例层面的泛化任务，不构成不同场景
- **任务结构是关键**：同样任务结构 + 同样能力维度 = 同一场景；不同任务结构或不同能力维度 = 不同场景
- **查询结构差异是不同场景**：单步直接、多步依赖、并列多源、条件筛选是不同的任务结构
- **每组保留 1 个**：在每个重复组中选 1 个描述最清晰、信息最完整的场景作为 keep，其余移除
- **若全无重复**：返回空数组 \`"duplicate_groups": []\`

## 待判断的场景列表（共 ${scenarios.length} 个）

${scenariosText}

## 输出要求

返回 JSON，包含 duplicate_groups 数组。每个元素表示一个重复组：

{
  "duplicate_groups": [
    {
      "scenario_ids": ["场景A的ID", "场景B的ID", "场景C的ID"],
      "keep": "场景A的ID",
      "reasoning": "为什么这些场景是重复的，以及为什么保留这个（中文）"
    }
  ]
}

注意：
- scenario_ids 必须包含 2 个或以上场景 ID
- keep 必须是 scenario_ids 中的一个
- 每个场景只能出现在一个重复组中
- 若无任何重复，返回空数组 []
- **reasoning 字段必须使用中文描述判断理由，不要使用英文**`
}

/**
 * 程序化回退：标签完全相同的对，保留第一个，移除其余
 * 仅在 LLM 调用失败时启用
 */
function fallbackDedupByTags(
  suspectedPairs: Array<{ a: Scenario; b: Scenario; reason: string }>,
): string[] {
  const removeIds = new Set<string>()
  const keepIds = new Set<string>()

  for (const pair of suspectedPairs) {
    if (!pair.reason.includes('标签完全相同')) continue

    if (keepIds.has(pair.a.scenario_id)) {
      removeIds.add(pair.b.scenario_id)
    } else if (keepIds.has(pair.b.scenario_id)) {
      removeIds.add(pair.a.scenario_id)
    } else {
      keepIds.add(pair.a.scenario_id)
      removeIds.add(pair.b.scenario_id)
    }
  }

  console.log(`  [去重检测-回退] 程序化规则移除 ${removeIds.size} 个场景`)
  return [...removeIds]
}

// ═══════════════════════════════════════════════════════════════════════════
// LLM 判别者（基于相关标签子集）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Pattern 覆盖信息（用于 Pattern 均衡度评估）
 */
export interface PatternCoverageInfo {
  /** Plan 中定义的全部场景模式 */
  scenario_patterns: string[]
  /** 每个 pattern 当前已有的场景数 */
  patternScenarioCount: Map<string, number>
}


/**
 * 构建判别 Prompt
 */
function buildJudgementPrompt(
  query: string,
  scenarios: Scenario[],
  relevantTags: string[],
  coverageStats: ReturnType<typeof analyzeRelevantTagCoverage>,
  patternInfo?: PatternCoverageInfo
): string {
  const scenarioSummaries = scenarios.map((s, i) =>
    `${i + 1}. ${s.scenario_name} [${s.tags.filter(t => relevantTags.includes(t)).join(', ')}]`
  ).join('\n')

  const topCovered = Object.entries(coverageStats.tagCoverage)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15)
    .map(([tag, count]) => `${tag}(${count})`)
    .join(', ')

  const uncoveredPreview = coverageStats.uncoveredTags.slice(0, 20)
  const expertBase = getAuditTemplate()

  // Pattern 均衡度评估信息（若提供了 patternInfo）
  const patternSection = patternInfo && patternInfo.scenario_patterns.length > 0
    ? (() => {
        const totalScenarios = scenarios.length
        const avgPerPattern = totalScenarios / patternInfo.scenario_patterns.length
        const patternLines = patternInfo.scenario_patterns.map((p, i) => {
          const count = patternInfo.patternScenarioCount.get(p) || 0
          const marker = count === 0 ? ' ← 缺口！' : count < avgPerPattern * 0.5 ? ' ← 偏少' : ''
          return `${i + 1}. ${p} — 当前 ${count} 个场景${marker}`
        }).join('\n')
        return `
【场景模式（Pattern）覆盖均衡度】
Plan 定义的场景模式共 ${patternInfo.scenario_patterns.length} 个，场景总数 ${totalScenarios}，平均每模式 ${avgPerPattern.toFixed(1)} 个：
${patternLines}
`
      })()
    : ''

  return `${expertBase}

现在需要你运用你的专家思维和第一性原则，评估当前场景集合是否充分满足设计需求。

【用户设计需求】
${query}

【相关标签范围】（共 ${relevantTags.length} 个与需求相关的标签）
${relevantTags.join(', ')}

【当前覆盖统计】
- 场景总数: ${scenarios.length}
- 已覆盖相关标签: ${coverageStats.coveredTags.size}/${relevantTags.length} (${((coverageStats.coveredTags.size / relevantTags.length) * 100).toFixed(1)}%)
- 平均每场景相关标签数: ${coverageStats.avgTagsPerScenario.toFixed(1)}

【覆盖详情】
- 高频标签: ${topCovered || '无'}
- 未覆盖标签: ${uncoveredPreview.join(', ') || '无'}${coverageStats.uncoveredTags.length > 20 ? ` ...还有 ${coverageStats.uncoveredTags.length - 20} 个` : ''}
${patternSection}
【已生成场景列表】
${scenarioSummaries || '（暂无场景）'}

【你的评估任务】

基于你的专家思维框架，从以下维度进行评估：

### 1. 覆盖质量判断（深度 vs 广度）
- **物理/功能覆盖**：场景是否覆盖了真实驾驶情境的核心功能维度？
- **认知/交互覆盖**：场景是否覆盖了不同复杂度级别的交互模式？
- **边界覆盖**：场景是否识别了真正的边界条件（基于物理/生理/认知限制）而非过度泛化的"安全"概念？

### 2. 场景合理性校准（应用安全判断原则）
- 已生成的场景是否符合行业惯例和常识？
- 是否存在"过度安全泛化"的场景（将合理操作误判为危险）？
- 是否存在"安全盲区"（真正危险但未被识别的场景）？

### 3. 意图对齐评估
- 场景内容与用户 query 的设计目标是否一致？
- 是否生成了与目标无关的"凑数"场景？

### 4. 边际收益判断
- 继续生成是否还能带来实质性的覆盖提升？
- 还是已经进入"重复模式"（生成相似度高的冗余场景）？

### 5. Pattern 均衡度评估${patternSection ? '（重点关注）' : '（本次未提供 pattern 信息，跳过）'}
${patternSection ? `- 若某 pattern 场景数为 0，建议在 generation_guidance 中指出需要补全
- 若某 pattern 场景数明显偏少（< 平均值的 50%），建议补全
- 若所有 pattern 均衡（每个 >= 2 个）+ 标签全覆盖 → 可判定 satisfied = true
- 注意：pattern 的选择由代码自动完成（选场景数最少的），你不需要指定具体 pattern 名称` : ''}

【已生成场景列表（含 scenario_id、标签、完整描述，便于对比）】
${scenarios.map((s, i) => `${i + 1}. [ID: ${s.scenario_id}]
   名称: ${s.scenario_name}
   标签: ${s.tags.join('、')}
   描述: ${s.description}`).join('\n\n')}

【评估标准】
判断是否"满足设计需求"的核心标准：
1. **充分覆盖度**：核心/高频标签是否已覆盖，且覆盖是基于合理的场景设计
2. **覆盖深度**：重要标签是否有适当数量的场景覆盖（避免蜻蜓点水，也避免过度堆砌）
3. **场景质量**：场景是否符合第一性原则（物理、生理、认知逻辑）
5. **意图对齐**：场景内容与用户 query 的设计目标一致
6. **边际收益**：继续生成是否还能显著提升覆盖（非重复性提升）
${patternSection ? '7. **Pattern 均衡度**：每个 scenario_pattern 是否都有至少 1 个场景覆盖' : ''}

注意：
- 只需要关注"相关标签"的覆盖，无关标签无需考虑
- **专家判断优先于数字指标**：覆盖率80%+但如果存在明显质量或合理性问题，仍可判定为不满足
- 应用你的安全判断原则：警惕"过度安全泛化"和"安全盲区"
- 警惕"为凑数量而降低质量"的倾向
- 若覆盖率已达 80%+ 且场景质量符合专家标准，可考虑满足
${patternSection ? '- **Pattern 缺口优先级最高**：即使标签覆盖率达标，只要有 pattern 场景数为 0，仍应判定为不满足' : ''}
- **重复场景必须放入 duplicate_scenarios**，即使 satisfied=true 也要输出重复场景列表

【输出要求】
以 JSON 格式输出判别结果，包含：
1. satisfied: 是否满足设计需求（基于专家级综合判断）
2. gap_analysis: 缺口分析（针对未覆盖的核心标签和质量缺陷）
3. refinement_direction: 若不满足，给出基于第一性原则的细化方向
   - duplicate_scenarios: **必填**，被判为语义重复的 scenario_id 列表（若无重复，返回空数组 []）

**【语言要求】所有判别输出必须使用中文**：
- gap_analysis.uncovered_relevant_tags: 未覆盖标签列表（引用中文标签名）
- gap_analysis.query_intent_fulfillment: 使用中文描述意图满足度
- gap_analysis.coverage_depth_score: 使用中文描述覆盖深度评估
- gap_analysis.suggestion: 使用中文给出改进建议
- refinement_direction.generation_guidance: 使用中文给出生成指导
- refinement_direction.stop_reason: 使用中文说明停止/继续的理由

确保所有 JSON 字符串值均使用中文输出。
`
}

/**
 * 判别当前场景覆盖度（基于相关标签子集）
 *
 * @param scenarios - 当前已生成的场景列表
 * @param query - 设计需求（通常为 Plan.task_description）
 * @param tagTree - 标签树
 * @param client - LLM 客户端
 * @param providedRelevantTags - 可选：已识别的相关标签（来自 Plan.target_tags）
 * @param patternInfo - 可选：Pattern 覆盖信息，用于 Pattern 均衡度评估
 */
export async function judgeScenarioCoverage(
  scenarios: Scenario[],
  query: string,
  tagTree: TagTree,
  client: OpenAI,
  providedRelevantTags?: string[],  // 可选：传入已识别的相关标签，避免重复识别
  patternInfo?: PatternCoverageInfo  // 可选：Pattern 覆盖信息
): Promise<JudgementResult> {
  const allLeafTags = tagTree.getLeafTagNames()

  // 1. 确定相关标签子集
  let relevantTags: string[]
  let reasoning: string

  if (providedRelevantTags && providedRelevantTags.length > 0) {
    // 使用传入的相关标签（来自 Plan.target_tags，保持一致性）
    relevantTags = providedRelevantTags.filter(tag => allLeafTags.includes(tag))
    reasoning = '使用 Plan 中已识别的目标标签'
    console.log(`[judgeScenarioCoverage] 使用传入的相关标签: ${relevantTags.length} 个`)
  } else {
    // 自行识别相关标签（向后兼容）
    const result = await identifyRelevantTags(query, allLeafTags, tagTree, client)
    relevantTags = result.relevantTags
    reasoning = result.reasoning
  }

  if (relevantTags.length === 0) {
    console.warn('[judgeScenarioCoverage] 未识别到相关标签，使用全部标签')
    relevantTags = [...allLeafTags]
  }

  // 2. 统计相关标签的覆盖情况
  const coverageStats = analyzeRelevantTagCoverage(scenarios, relevantTags)
  
  // 3. 计算覆盖率
  const coveragePercentage = Math.round(
    (coverageStats.coveredTags.size / relevantTags.length) * 100
  )
  
  // 4. 计算覆盖深度
  const depthScore = calculateCoverageDepth(
    coverageStats.tagCoverage, 
    scenarios.length
  )

  // 5. 构建 Prompt 进行 LLM 判别
  const prompt = buildJudgementPrompt(query, scenarios, relevantTags, coverageStats, patternInfo)

  // 使用从 database 导入的 LLMJudgementOutputSchema
  // 该 Schema 定义了 LLM 输出的原始判别结果结构

  try {
    // 使用带重试的 LLM 调用（处理 JSON 解析偶发错误）
    const { judgement } = await invokeWithRetry<{
      judgement: {
        satisfied: boolean
        gap_analysis: {
          uncovered_relevant_tags?: string[]
          query_intent_fulfillment?: number
          coverage_depth_score?: number
          suggestion?: string
        }
        refinement_direction?: {
          next_batch_size?: number
          focus_tags?: string[]
          avoid_tags?: string[]
          scenario_types?: string[]
          generation_guidance?: string
          stop_reason?: string
          duplicate_scenarios?: string[] | null
        }
      }
    }>(client, {
      input: prompt,
      text: {
        format: zodTextFormat(LLMJudgementOutputSchema, 'judgement'),
      },
    }, 3)

    // 6. 合并程序化统计（确保数据准确），转换为新的 Guidance 接口
    const satisfied = judgement.satisfied

    // 解析 duplicate_scenarios（无论 satisfied 与否，都可能有重复场景需要移除）
    const duplicateScenarios = judgement.refinement_direction?.duplicate_scenarios || []

    // 构建 guidance（若不满足）
    let guidance: GenerationGuidance | null = null
    if (!satisfied && judgement.refinement_direction) {
      const rd = judgement.refinement_direction

      // target_pattern 由代码程序化选择（不再依赖 LLM 输出）
      // 策略：优先选"未覆盖标签最多"的 pattern，其次选场景数最少的
      let targetPattern: string | undefined = undefined
      if (patternInfo && patternInfo.scenario_patterns.length > 0) {
        const uncoveredTags = coverageStats.uncoveredTags
        const uncoveredSet = new Set(uncoveredTags)

        targetPattern = [...patternInfo.scenario_patterns].sort((a, b) => {
          // 获取该 pattern 的所有场景
          const aScenarios = scenarios.filter(s => s.pattern === a)
          const bScenarios = scenarios.filter(s => s.pattern === b)

          // 计算该 pattern 的场景未覆盖的 uncovered 标签数（越多越需要补）
          const aUncoveredCount = uncoveredTags.filter(tag =>
            !aScenarios.some(s => s.tags.includes(tag))
          ).length
          const bUncoveredCount = uncoveredTags.filter(tag =>
            !bScenarios.some(s => s.tags.includes(tag))
          ).length

          // 先按未覆盖标签数降序（最需要补的优先），再按场景数升序（最少的优先）
          if (bUncoveredCount !== aUncoveredCount) {
            return bUncoveredCount - aUncoveredCount
          }
          return (patternInfo.patternScenarioCount.get(a) || 0) - (patternInfo.patternScenarioCount.get(b) || 0)
        })[0]

        const targetScenarios = scenarios.filter(s => s.pattern === targetPattern)
        const targetUncovered = uncoveredTags.filter(tag =>
          !targetScenarios.some(s => s.tags.includes(tag))
        ).length
        console.log(`[judgeScenarioCoverage] 程序化选择 pattern: "${targetPattern}"（${patternInfo.patternScenarioCount.get(targetPattern) || 0} 个场景，${targetUncovered} 个未覆盖标签待补）`)
      }

      guidance = {
        focus_tags: rd.focus_tags || coverageStats.uncoveredTags.slice(0, 15),
        avoid_tags: rd.avoid_tags || Object.entries(coverageStats.tagCoverage)
          .filter(([_, count]) => count >= 3)
          .map(([tag]) => tag)
          .slice(0, 10),
        scenario_types: rd.scenario_types || [],
        guidance: rd.generation_guidance || `补充未覆盖的 ${coverageStats.uncoveredTags.length} 个相关标签`,
        suggested_count: rd.next_batch_size || Math.min(10, Math.max(3, Math.ceil(coverageStats.uncoveredTags.length / 5))),
        target_pattern: targetPattern,
        duplicate_scenarios: duplicateScenarios,
      }
    } else if (satisfied && duplicateScenarios.length > 0) {
      // satisfied=true 但仍有重复场景需要移除：构造一个最小 guidance 只携带 duplicate_scenarios
      guidance = {
        focus_tags: [],
        avoid_tags: [],
        scenario_types: [],
        guidance: '',
        duplicate_scenarios: duplicateScenarios,
      }
    }

    return {
      satisfied,
      current_stats: {
        total_scenarios: scenarios.length,
        relevant_tag_count: relevantTags.length,
        covered_relevant_tags: coverageStats.coveredTags.size,
        coverage_percentage: coveragePercentage,
        avg_tags_per_scenario: coverageStats.avgTagsPerScenario,
      },
      gap_analysis: {
        uncovered_relevant_tags: coverageStats.uncoveredTags,
        query_intent_fulfillment: judgement.gap_analysis?.query_intent_fulfillment || coveragePercentage,
        coverage_depth_score: depthScore,
        suggestion: judgement.gap_analysis?.suggestion || 
          `已覆盖 ${coverageStats.coveredTags.size}/${relevantTags.length} 个相关标签，覆盖率 ${coveragePercentage}%`,
      },
      guidance,
      stop_reason: satisfied ? (judgement.refinement_direction?.stop_reason || '覆盖率和深度满足要求') : undefined,
    }
  } catch (error) {
    console.error('[judgeScenarioCoverage] LLM 判别失败，使用程序化回退:', error)

    // 程序化回退逻辑
    const satisfied = coveragePercentage >= 80 && depthScore >= 60

    // 程序化回退：选"未覆盖标签最多 + 场景数最少"的 pattern
    let fallbackTargetPattern: string | undefined = undefined
    if (!satisfied && patternInfo && patternInfo.scenario_patterns.length > 0) {
      const uncoveredTags = coverageStats.uncoveredTags
      fallbackTargetPattern = [...patternInfo.scenario_patterns].sort((a, b) => {
        const aScenarios = scenarios.filter(s => s.pattern === a)
        const bScenarios = scenarios.filter(s => s.pattern === b)
        const aUncovered = uncoveredTags.filter(tag => !aScenarios.some(s => s.tags.includes(tag))).length
        const bUncovered = uncoveredTags.filter(tag => !bScenarios.some(s => s.tags.includes(tag))).length
        if (bUncovered !== aUncovered) return bUncovered - aUncovered
        return (patternInfo.patternScenarioCount.get(a) || 0) - (patternInfo.patternScenarioCount.get(b) || 0)
      })[0]
    }

    // 程序化回退：构建 guidance
    const guidance: GenerationGuidance | null = satisfied ? null : {
      focus_tags: coverageStats.uncoveredTags.slice(0, 15),
      avoid_tags: Object.entries(coverageStats.tagCoverage)
        .filter(([_, count]) => count >= 3)
        .map(([tag]) => tag),
      scenario_types: [],
      guidance: `重点补充未覆盖的 ${coverageStats.uncoveredTags.length} 个相关标签`,
      suggested_count: Math.min(10, Math.max(3, Math.ceil(coverageStats.uncoveredTags.length / 5))),
      target_pattern: fallbackTargetPattern,
    }

    return {
      satisfied,
      current_stats: {
        total_scenarios: scenarios.length,
        relevant_tag_count: relevantTags.length,
        covered_relevant_tags: coverageStats.coveredTags.size,
        coverage_percentage: coveragePercentage,
        avg_tags_per_scenario: coverageStats.avgTagsPerScenario,
      },
      gap_analysis: {
        uncovered_relevant_tags: coverageStats.uncoveredTags,
        query_intent_fulfillment: coveragePercentage,
        coverage_depth_score: depthScore,
        suggestion: `程序化评估：覆盖率 ${coveragePercentage}%，深度分 ${depthScore}`,
      },
      guidance,
      stop_reason: satisfied ? `覆盖率达 ${coveragePercentage}%，满足需求` : undefined,
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 硬约束校验：剔除违反 query 硬约束的场景
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 单个场景的硬约束校验结果
 */
const ScenarioConstraintCheckSchema = z.object({
  scenario_id: z.string(),
  /** 是否满足所有硬约束 */
  satisfied: z.boolean(),
  /** 违反的约束序号列表（1-based，对应传入的硬约束列表序号；满足时为空数组） */
  violated_constraint_indices: z.array(z.number()).default([]),
  /** 判定理由（中文） */
  reasoning: z.string(),
})

const HardConstraintCheckOutputSchema = z.object({
  checks: z.array(ScenarioConstraintCheckSchema),
})

export type ScenarioConstraintCheck = z.infer<typeof ScenarioConstraintCheckSchema>

/**
 * 基于 Plan 的 hard_constraints 校验场景列表，返回违反硬约束的 scenario_id 列表
 *
 * 让 LLM 逐个场景对照硬约束列表判定。若硬约束为空，直接返回空列表（无操作）。
 * LLM 失败时回退：不剔除任何场景（保守策略，避免误删）。
 *
 * @returns 应被移除的 scenario_id 列表
 */
export async function filterScenariosByHardConstraints(
  scenarios: Scenario[],
  hardConstraints: HardConstraint[],
  client: OpenAI,
): Promise<string[]> {
  if (hardConstraints.length === 0 || scenarios.length === 0) return []

  console.log(`  [硬约束校验] 共 ${scenarios.length} 个场景，${hardConstraints.length} 条硬约束，调用 LLM 逐个判定...`)

  const constraintsSection = buildHardConstraintsSection(hardConstraints)

  const scenariosText = scenarios.map((s, i) => {
    return `### 场景 ${i + 1}
ID: ${s.scenario_id}
名称: ${s.scenario_name}
标签: ${s.tags.join('、')}
描述: ${s.description}`
  }).join('\n\n')

  const prompt = `你是测试场景的资深审核专家。你的任务是：逐个判定下方每个场景**是否满足所有硬性约束**。

**【语言要求】所有输出必须使用中文，特别是 reasoning 字段必须使用中文描述判定理由。**

${constraintsSection}

## 判定规则

- 对每个场景，逐条对照硬约束列表（按上述编号 1, 2, 3...）。
- 若场景违反**任一条**硬约束，则 \`satisfied=false\`，并在 \`violated_constraint_indices\` 中列出违反的约束编号（1-based）。
- 若场景满足所有硬约束，则 \`satisfied=true\`，\`violated_constraint_indices\` 为空数组。
- 判定依据：场景的名称、标签、描述共同体现的测试意图。**标签里有相关能力≠场景以该能力为核心**——要看场景描述的主任务是什么。例如约束要求"仅使用能力A"，但场景描述的主任务是能力B，标签虽含A但仍违反约束。

## 典型判定示例

以下为通用示例（具体约束文本以实际 hard_constraints 为准）：

- 硬约束"必须使用能力A" + 场景主任务是能力B（标签虽含A）→ **违反**（主任务不是A）
- 硬约束"禁止使用能力B" + 场景主任务混入了能力B → **违反**（混入了被禁止的能力）
- 硬约束"单轮对话" + 场景标签含"跨会话"或"多轮" → **违反**（交互模式不符）
- 硬约束"主题为T" + 场景主题明显属于T之外领域 → **违反**（主题不符）
- 硬约束"非X类" + 场景主任务是用户主动要求执行X → **违反**（用户主动要求了被排除的任务类型）

## 待判定的场景列表（共 ${scenarios.length} 个）

${scenariosText}

## 输出要求

返回 JSON，包含 checks 数组，每个元素对应一个场景的判定结果：

{
  "checks": [
    {
      "scenario_id": "场景ID",
      "satisfied": true/false,
      "violated_constraint_indices": [违反的约束编号列表],
      "reasoning": "中文判定理由"
    }
  ]
}

注意：
- 必须为每个场景输出一条判定
- reasoning 必须使用中文
- violated_constraint_indices 中的编号对应上方硬约束列表的序号（1-based）`

  try {
    const result = await invokeWithRetry<z.infer<typeof HardConstraintCheckOutputSchema>>(client, {
      input: prompt,
      text: {
        format: zodTextFormat(HardConstraintCheckOutputSchema, 'hard_constraint_check'),
      },
    }, 3)

    const removeIds: string[] = []
    const validScenarioIds = new Set(scenarios.map(s => s.scenario_id))

    for (const check of result.checks) {
      if (!validScenarioIds.has(check.scenario_id)) continue
      if (!check.satisfied) {
        removeIds.push(check.scenario_id)
        const violatedNums = (check.violated_constraint_indices || []).join(',')
        console.log(`    [违反约束] ${check.scenario_id} (违反第 ${violatedNums} 条) — ${check.reasoning}`)
      }
    }

    console.log(`  [硬约束校验] 判定 ${removeIds.length}/${scenarios.length} 个场景违反硬约束，将剔除`)
    return removeIds
  } catch (error) {
    console.error('  [硬约束校验] LLM 判定失败，回退到不剔除（保守策略）:', (error as Error).message)
    return []
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 导出类型
// ═══════════════════════════════════════════════════════════════════════════

export type TagCoverage = Record<string, number>
