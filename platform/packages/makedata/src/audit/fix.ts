/**
 * 用例修复 - 基于审核结果修复用例
 *
 * 输入：用例列表 + 审核结果 + 标签树 + 修复原则
 * 输出：修复后的用例列表
 */

import { OpenAI, zodTextFormat } from '@eval-platform/llm'
import { invokeWithRetry } from '@eval-platform/llm'
import { CaseWithScenarioSchema, type CaseWithScenario } from '@eval-platform/database'
import { type CaseAuditResult, type AuditIssue, type FixedCaseResult } from '@eval-platform/database/models/case-audit'
import type { TagTree } from '../core/tag-tree.js'
import { loadWritingPrinciples, loadAuditPrinciples, loadKeyConstraints } from '../principles/index.js'
import { z } from 'zod'

// 修复后的用例包装 Schema（用于 LLM 输出）
const FixedCaseOutputSchema = z.object({
  fixed_case: CaseWithScenarioSchema,
})

// 使用 zodTextFormat 从 Zod Schema 生成 OpenAI JSON Schema
const fixedCaseJsonSchema = zodTextFormat(FixedCaseOutputSchema, 'fixed_case')

const FIXED_CASE_SCHEMA: OpenAI.Responses.ResponseTextConfig = {
  format: fixedCaseJsonSchema,
}

/**
 * 构建修复 Prompt
 */
async function buildFixPrompt(
  originalCase: CaseWithScenario,
  auditResult: CaseAuditResult,
  roundNum: number
): Promise<string> {
  const keyConstraints = await loadKeyConstraints()
  const fixPrinciples = await loadWritingPrinciples()

  const auditFeedback = auditResult.issues
    .map(
      (issue, idx) =>
        `${idx + 1}. [${issue.principle}] ${issue.dimension} [${issue.severity}]\n   问题：${issue.description}\n   建议：${issue.suggestion}`
    )
    .join('\n\n')

  return `
你是一个车机助手评测用例修复专家。请根据审核反馈修复一个有问题的case。

## 🚨 关键约束（修复时必须严格遵守，违反则修复无效）

${keyConstraints || '【关键约束加载失败，请参考完整原则】'}

---

## 修复规范（精简版）

${fixPrinciples}

---

## 【关键要求：必须直接采纳审核反馈中的 suggestion】

审核反馈中每条issue都有suggestion字段，里面是具体的改写建议。你必须直接采纳这些建议：
- 如果suggestion说"删除该条断言" → 必须删除
- 如果suggestion给出了具体的断言文本 → 直接使用该文本
- 如果suggestion说"仅保留第X条" → nl_assertion只保留那一条，其余全部删除

---

## 【修复步骤】

第一步：逐条处理审核反馈中的每个issue，按suggestion执行修改。

第二步：处理nl_assertion时：
- 先"全部删除"被审核标记为通用/无区分力的断言
- 再根据suggestion写入新的专属断言
- 不要在旧断言基础上修改——删干净再写

第三步：处理tags时：
- 删除审核反馈明确指出"无对应case内容支撑"的标签
- 删除审核反馈明确指出"与主轴不符"的标签
- 删除审核反馈明确指出"应为XX而非YY"的标签中的YY，替换为XX
- 补充审核反馈明确指出"缺少/遗漏"的标签

第四步：检查user_query_lists：
- 确保每项只有1条user消息
- 多会话场景确保结构正确（生产→消费闭环）
- **普通场景不需要mock_time**（设为null），仅时间/条件规律发现场景才需要
- **冷启动台词自然性**：冷启动台词必须是真人一口气会说出的话。若审核发现"念清单式"不自然台词（单句内多次反复改变同一目标且无犹豫语气），应拆为冷启动第一句 + expected_script 后续轮次。拆分时注意：保留自然的并行多任务（如"导航到公司，顺便放点轻音乐"）和带犹豫语气的自然改口（如"导航到公司，噢不，导航到虹桥机场先"），只拆"多次反复改变同一目标"的部分
- **expected_script 后续轮次台词自然性**：expected_script 中每个"用户："行的台词同样必须像真人对车机说的话，不只冷启动第一句才需要自然。发现技术化/书面化/指令式表述（如"再问下当前座椅设置""查询当前任务状态""请反馈当前导航进度""确认座椅模式""反馈剩余时间"）或机械组合"功能名+动作"（如"查询加油站信息"）时，改为口语化、结果导向的短句（如"现在啥状态""调好了吗""还有多久到""加油站找到了吗""座椅调到啥模式了"）

第五步：检查expected_script：
- 「用户：」后只能是口述台词
- 「管家：（...）」包含导演说明
- **多轮场景必须展开为交替剧本**：涉及中途插话/取消/查询/改口/多任务并行等需要中途交互的标签时，expected_script 必须逐轮写"用户：xxx 管家：（期望…）"的交替结构，不能只写一行概括
- **单次多轮不标"第N轮"**：单会话内的多轮交互直接交替写，不要标注"第一轮""第二轮"（会让假人误以为是多次多轮）
- **多次多轮用"（重启新的对话……）"分隔**：不要用"第一会话""第二会话"等标注，改为独立一行"（重启新的对话……）"分隔各会话段
- **剧本首句=冷启动台词（强制一致性）**：expected_script 第一句"用户：xxx"必须与 user_query_lists[0] 的冷启动台词**逐字一致**；多次多轮场景每个"（重启新的对话……）"段的首句必须与对应 session 冷启动台词逐字一致。若审核发现不一致：以 user_query_lists 的冷启动台词为准，改写 expected_script 首句使其逐字相同；若剧本首句本该是冷启动台词但因为剧本遗漏了某些轮次导致首句变成了后续轮次的内容，应补全剧本从冷启动台词开始展开
- **任务持续性与可取消性**：若场景测"取消任务/询问任务进度/中途插话改任务/任务优先级调度"，检查被操作的对象是否为**持续任务**（导航/搜索/播放/提醒）。若发现用瞬间车控任务（开按摩/调空调/开车窗等）冒充可取消/可查询状态：①引入一个持续任务（如导航）作为前置状态；②将"取消/询问/改任务"的对象改为该持续任务；③若场景确实只想测车控并行，改写 case_description 和 tags，去掉"任务状态管理/取消/优先级调度"等表述
- **架空前置检查**：检查冷启动台词或剧本里是否有"取消之前的XX""查询刚才那个任务"等带定语引用前置任务的台词。若被引用的任务在本 case 内（user_query_lists 或 expected_script 前序轮次）从未建立过，属架空前置，二选一修复：①补全生产端——在 expected_script 前序轮次或新增冷启动补上被引用任务的建立过程，形成闭环；②去除架空引用——改写冷启动台词，去掉"之前的XX"架空定语，改为从零发起的指令（如"导航到三亚湾附近酒店"，不提"取消之前的"）
- **人设前导段检查（若使用）**：expected_script 开头若有非"用户：/管家："的前导段，检查：①前导段和正文用空行分隔（若无空行，补上）；②前导段只写演绎规则（用户性格/应对策略/重试规则/环境约束），若混入了助手行为/判分点，移到"管家：（...）"或 nl_assertion；③前导段不得架空前置（禁止"假设你之前已经XX"），若发现按架空前置处理

第六步：修复后自查——确认上述关键约束（K0-K12）全部满足，不要修好A问题却引入B问题。

---

## 【原始用例】
${JSON.stringify(
  {
    case_id: originalCase.case_id,
    case_description: originalCase.case_description,
    context_config: originalCase.context_config,
    max_round: originalCase.max_round,
    user_query_lists: originalCase.user_query_lists,
    expected_script: originalCase.expected_script,
    nl_assertion: originalCase.nl_assertion,
    tags: originalCase.tags,
  },
  null,
  2
)}

---

## 【审核反馈】（第${roundNum}轮修复）
${auditFeedback}

---

请输出修复后的完整case JSON（不要输出其他内容，不要输出markdown代码块标记）：
`.trim()
}

/**
 * 修复单个用例（单次）
 */
export async function fixCaseOnce(
  originalCase: CaseWithScenario,
  auditResult: CaseAuditResult,
  roundNum: number,
  client: OpenAI,
  signal?: AbortSignal
): Promise<CaseWithScenario> {
  const prompt = await buildFixPrompt(originalCase, auditResult, roundNum)

  const params: OpenAI.Responses.ResponseCreateParamsNonStreaming = {
    instructions: prompt,
    input: `修复用例: ${originalCase.case_id}`,
    text: FIXED_CASE_SCHEMA,
    temperature: 0.0,
  }

  const result = await invokeWithRetry<{ fixed_case: Partial<CaseWithScenario> }>(client, params, 3, signal)

  // 保留原始用例的不可变字段，合并修复后的字段
  return {
    ...originalCase,
    ...result.fixed_case,
    dataset_id: originalCase.dataset_id,
    source_scenario_id: originalCase.source_scenario_id,
    source_scenario_name: originalCase.source_scenario_name,
  }
}

/**
 * 修复用例循环（多轮修复直到通过或达到最大轮次）
 *
 * @param originalCase - 原始用例
 * @param initialAudit - 初始审核结果（可选）
 * @param tagTree - 标签树
 * @param client - OpenAI 客户端
 * @param auditOneCase - 审核函数（用于重新审核）
 * @param maxRounds - 最大修复轮次，默认 5
 * @returns 修复结果
 */
export async function fixCaseLoop(
  originalCase: CaseWithScenario,
  initialAudit: CaseAuditResult | null,
  tagTree: TagTree,
  client: OpenAI,
  auditOneCase: (caseItem: CaseWithScenario, tagTree: TagTree, client: OpenAI, signal?: AbortSignal) => Promise<CaseAuditResult>,
  maxRounds: number = 5,
  signal?: AbortSignal
): Promise<FixedCaseResult> {
  // 第0轮：如果需要，先审核
  let currentAudit: CaseAuditResult
  if (initialAudit) {
    currentAudit = initialAudit
  } else {
    console.log(`  [${originalCase.case_id}] 第0轮：审核原始case...`)
    currentAudit = await auditOneCase(originalCase, tagTree, client, signal)
  }

  if (currentAudit.audit_pass) {
    console.log(`  [${originalCase.case_id}] 原始case已通过审核，无需修复`)
    return {
      original_id: originalCase.case_id,
      original_case_id: originalCase.case_id,
      fixed_case: originalCase,
      audit_rounds: 0,
      final_pass: true,
    }
  }

  console.log(
    `  [${originalCase.case_id}] 原始case审核未通过，共 ${currentAudit.issues.length} 个问题`
  )

  let currentCase = originalCase
  let roundNum = 0

  for (roundNum = 1; roundNum <= maxRounds; roundNum++) {
    if (signal?.aborted) {
      console.log(`  [${originalCase.case_id}] 已取消，停止修复`)
      break
    }
    console.log(`  [${originalCase.case_id}] 第${roundNum}轮修复...`)

    // 修复
    try {
      const fixedCase = await fixCaseOnce(currentCase, currentAudit, roundNum, client, signal)
      currentCase = fixedCase
    } catch (error) {
      return {
        original_id: originalCase.case_id,
        original_case_id: originalCase.case_id,
        fixed_case: currentCase,
        audit_rounds: roundNum,
        final_pass: false,
        error: `修复失败: ${error}`,
        remaining_issues: currentAudit.issues,
      }
    }

    // 重新审核
    console.log(`  [${originalCase.case_id}] 第${roundNum}轮审核修复后的case...`)
    const newAudit = await auditOneCase(currentCase, tagTree, client, signal)

    if (newAudit.audit_pass) {
      console.log(`  [${originalCase.case_id}] ✅ 第${roundNum}轮修复后审核通过！`)
      return {
        original_id: originalCase.case_id,
        original_case_id: originalCase.case_id,
        fixed_case: currentCase,
        audit_rounds: roundNum,
        final_pass: true,
      }
    }

    console.log(
      `  [${originalCase.case_id}] 第${roundNum}轮修复后仍有 ${newAudit.issues.length} 个问题`
    )
    currentAudit = newAudit
  }

  // 达到最大轮次仍未通过
  console.log(`  [${originalCase.case_id}] ⚠️ 达到最大修复轮次(${maxRounds})，仍未通过审核`)
  return {
    original_id: originalCase.case_id,
    original_case_id: originalCase.case_id,
    fixed_case: currentCase,
    audit_rounds: roundNum,
    final_pass: false,
    remaining_issues: currentAudit.issues,
  }
}

/**
 * 批量修复用例
 *
 * @param cases - 用例列表
 * @param auditResults - 审核结果列表
 * @param tagTree - 标签树
 * @param client - OpenAI 客户端
 * @param auditOneCase - 审核函数
 * @param options - 配置选项
 * @returns 修复结果列表
 */
export async function fixCasesByAudit(
  cases: CaseWithScenario[],
  auditResults: CaseAuditResult[],
  tagTree: TagTree,
  client: OpenAI,
  auditOneCase: (caseItem: CaseWithScenario, tagTree: TagTree, client: OpenAI, signal?: AbortSignal) => Promise<CaseAuditResult>,
  options?: {
    maxRounds?: number
    concurrency?: number
    onProgress?: (completed: number, total: number) => void
    signal?: AbortSignal
  }
): Promise<FixedCaseResult[]> {
  const { maxRounds = 5, concurrency = 5, signal } = options || {}

  console.log(`[fixCasesByAudit] 开始修复 ${cases.length} 个用例`)
  console.log(`  最大轮次: ${maxRounds}, 并发: ${concurrency}`)

  const auditMap = new Map(auditResults.map(r => [r.case_id, r]))
  const results: FixedCaseResult[] = []
  let completed = 0

  // 简单的并发控制
  const runInBatches = async (batch: CaseWithScenario[]) => {
    const batchResults = await Promise.all(
      batch.map(async caseItem => {
        const auditResult = auditMap.get(caseItem.case_id)
        if (!auditResult) {
          completed++
          options?.onProgress?.(completed, cases.length)
          return {
            original_id: caseItem.case_id,
            original_case_id: caseItem.case_id,
            fixed_case: caseItem,
            audit_rounds: 0,
            final_pass: false,
            error: '未找到对应的审核结果',
          } as FixedCaseResult
        }

        // 如果已通过，跳过
        if (auditResult.audit_pass) {
          completed++
          options?.onProgress?.(completed, cases.length)
          return {
            original_id: caseItem.case_id,
            original_case_id: caseItem.case_id,
            fixed_case: caseItem,
            audit_rounds: 0,
            final_pass: true,
          } as FixedCaseResult
        }

        const result = await fixCaseLoop(
          caseItem,
          auditResult,
          tagTree,
          client,
          auditOneCase,
          maxRounds,
          signal
        )

        completed++
        options?.onProgress?.(completed, cases.length)
        return result
      })
    )
    return batchResults
  }

  // 分批处理
  for (let i = 0; i < cases.length; i += concurrency) {
    if (signal?.aborted) {
      console.log(`[fixCasesByAudit] 已取消，停止后续修复`)
      break
    }
    const batch = cases.slice(i, i + concurrency)
    const batchResults = await runInBatches(batch)
    results.push(...batchResults)

    const progress = Math.round((completed / cases.length) * 100)
    console.log(`  进度: ${completed}/${cases.length} (${progress}%)`)
  }

  // 汇总统计
  const passed = results.filter(r => r.final_pass).length
  const failed = results.filter(r => !r.final_pass && !r.error).length
  const errors = results.filter(r => r.error).length

  console.log(`[fixCasesByAudit] 修复完成`)
  console.log(`  修复后通过: ${passed}`)
  console.log(`  修复后未通过: ${failed}`)
  console.log(`  异常: ${errors}`)

  return results
}
