/**
 * 场景生成核心流程（基于 Plan，Pattern 驱动）
 *
 * 这是对外暴露的主入口，封装完整的「Plan → Pattern 巡游 → Judge 驱动深化 → 收敛」流程。
 *
 * 使用方式：
 * ```typescript
 * // 方式1：自动生成 Plan
 * const result = await generateScenarios(query, tagTree, client)
 *
 * // 方式2：使用已确认的 Plan
 * const result = await generateScenarios(query, tagTree, client, { plan })
 * ```
 *
 * 内部流程（两阶段模型）：
 *
 * **阶段 1: Pattern 首轮巡游（强制完成，不计入 maxIterations）**
 * - 顺序遍历 Plan.scenario_patterns 中的每个 pattern
 * - 每个 pattern 组合定向 query（task_description + pattern + interpretation_notes）
 * - 生成到"至少 1 个合格场景"为止，最多 2 批兜底
 * - 不看 target，不看 Judge，必须走完所有 pattern
 *
 * **阶段 2: Judge 全局驱动的深化（计入 maxIterations）**
 * - Judge 全局评估三维度：pattern 均衡 / 标签覆盖 / 多样性
 * - Judge 强制指定 target_pattern + focus_tags + suggested_count
 * - 按 Judge guidance 生成下一批，每轮重新评估
 *
 * **阶段 3: 收敛停止（两必要条件全满足）**
 * - ① 每个 pattern >= 1 个场景（阶段 1 保证）
 * - ② 标签覆盖 = 100% OR Judge.satisfied = true
 *
 * targetScenarioCount 不再作为停止的必要条件，仅用于安全阀和进度展示。
 * 这样 LLM 可以尽量多尽量全地生成场景，不受总数限制。
 *
 * 安全阀：
 * - 迭代次数 > maxIterations（仅约束阶段 2）
 * - 总场景数 > max(10 * targetScenarioCount, patterns.length * 15)
 */

import type { OpenAI } from '@eval-platform/llm'
import type { Scenario } from '@eval-platform/database/models/scenario'
import type { ScenarioPlan } from '@eval-platform/database/models/scenario-plan'
import type { TagTree } from '../core/tag-tree.js'
import type { GenerationGuidance } from './scenario-generator.js'
import { buildHardConstraintsSection, buildHardConstraintsDesignRule } from './prompt-templates.js'
import pLimit from 'p-limit'

export type { Scenario } from '@eval-platform/database/models/scenario'
export type { GenerationGuidance } from './scenario-generator.js'

/**
 * 场景生成选项
 */
export interface GenerateScenariosOptions {
  /** 预生成的 Plan（如不提供则自动生成） */
  plan?: ScenarioPlan
  /**
   * 预生成的场景模式列表（patterns）。
   * - 如未提供 plan：自动生成 plan
   * - 如未提供 patterns：基于 plan 自动生成 patterns（调用 generateScenarioPatterns）
   * patterns 是 Plan 的下游产物，作为场景生成循环的「执行蓝图」。
   */
  patterns?: string[]
  /** 最大迭代次数（默认 10，仅约束阶段 2） */
  maxIterations?: number
  /** 初始批次大小（默认 5） */
  initialBatchSize?: number
  /** 审核-修复最大轮次（每批次内部，默认 2） */
  maxRefineRoundsPerBatch?: number
  /** 审核并发数（默认 5） */
  auditConcurrency?: number
  /** 修复并发数（默认 3） */
  fixConcurrency?: number
  /** 进度回调 - 包含基于 Plan 的进度 */
  onProgress?: (info: {
    iteration: number
    batchSize: number
    totalScenarios: number
    targetScenarioCount: number
    progressPercentage: number // 基于 Plan 的进度: total / target
    coveragePercentage: number
    satisfied: boolean
    stage: 'generating' | 'auditing' | 'fixing' | 'judging' | 'pattern_generating'
    /** 当前聚焦的 pattern（若有） */
    currentPattern?: string
    /** 当前阶段 */
    phase?: 'pattern_sweep' | 'judge_driven'
    /** 当前正在做什么的人话描述，可直接展示给用户 */
    currentStep: string
    /** 当前步骤内的子进度（0-100），如批量审核中已审核 60%；不提供时前端可不展示子进度 */
    stepProgress?: number
  }) => void
  /** 流式回调：每当生成一个优质场景时调用 */
  onScenarioGenerated?: (scenario: Scenario, info: {
    iteration: number
    totalScenarios: number
    targetScenarioCount: number
    progressPercentage: number
    coveragePercentage: number
    /** 该场景归属的 pattern */
    pattern?: string
    /**
     * 是否为临时结果（可能被 Judge 去重移除）
     * - true: 运行中流式推送的临时场景，最终结果可能少于临时数
     * - false: 最终确定结果（当前阶段总是 true，最终通过返回值给出确定列表）
     */
    isProvisional: boolean
  }) => void | Promise<void>
  /** Pattern 生成完成回调：把生成的 patterns 推给前端展示 */
  /** Pattern 生成完成回调：把生成的 patterns 和 targetScenarioCount 推给前端展示 */
  onPatternsGenerated?: (patterns: string[], targetScenarioCount: number) => void
  /** 外部中断信号：返回 true 时立即终止生成流程 */
  shouldStop?: () => boolean
  /** 场景被去重移除时调用（阶段2 语义去重） */
  onScenarioDeleted?: (scenarioId: string, scenarioName: string, reason?: string) => void | Promise<void>
  /** AbortSignal，用于中断正在进行的 LLM HTTP 请求 */
  signal?: AbortSignal
}

/**
 * 场景生成结果
 */
export interface GenerateScenariosResult {
  /** 所有通过审核的优质场景 */
  scenarios: Scenario[]
  /** 使用的 Plan */
  plan: ScenarioPlan
  /** 总迭代次数（仅阶段 2） */
  totalIterations: number
  /** 最终相关标签覆盖率 */
  finalCoveragePercentage: number
  /** 是否满足设计需求 */
  satisfied: boolean
  /** 实际生成数量 vs 计划数量 */
  targetCount: number
  actualCount: number
  /** Pattern 覆盖统计 */
  patternCoverage: Record<string, number>
}

/**
 * 构建定向 query：task_description + 当前 pattern + interpretation_notes + hard_constraints
 *
 * 让每批生成有明确方向，充分发挥 Plan 的作战蓝图作用。
 * 硬约束被显式注入，确保场景生成时严格遵守 query 的硬性要求。
 */
function buildOrientedQuery(plan: ScenarioPlan, pattern: string): string {
  const hardConstraintsSection = buildHardConstraintsSection(plan.hard_constraints)
  const hardConstraintsRule = buildHardConstraintsDesignRule(plan.hard_constraints)

  return `## 任务描述
${plan.task_description}

## 本次生成的场景模式（请聚焦此模式）
${pattern}

## 需求理解与专家洞察
${plan.interpretation_notes}
${hardConstraintsSection ? `\n${hardConstraintsSection}` : ''}
${hardConstraintsRule ? `\n${hardConstraintsRule}` : ''}
`.trim()
}

/**
 * 场景生成主入口
 *
 * @param query - 场景设计需求描述（如未提供 plan，用于生成 plan）
 * @param tagTree - 标签树实例
 * @param client - OpenAI 客户端
 * @param options - 生成选项
 * @returns 生成结果
 */
export async function generateScenarios(
  query: string,
  tagTree: TagTree,
  client: OpenAI,
  options: GenerateScenariosOptions = {}
): Promise<GenerateScenariosResult> {
  const {
    plan: providedPlan,
    patterns: providedPatterns,
    maxIterations = 10,
    initialBatchSize = 25,  // 增大批次大小，单次生成更多场景（原为 8）
    maxRefineRoundsPerBatch = 2,
    auditConcurrency = 35,   // 豆包 API 限制 50，峰值设 40，分配 35 给审核
    fixConcurrency = 20,      // 修复分配 20
    onProgress,
    onScenarioGenerated,
    onPatternsGenerated,
    shouldStop,
    onScenarioDeleted,
    signal,
  } = options

  const ensureNotStopped = () => {
    if (shouldStop?.()) {
      throw new Error('GENERATION_CANCELLED')
    }
  }

  /**
   * 进度计算（阶段制，保证单调递增，不会回退）
   *
   * 非线性生成过程无法精确计算百分比，采用阶段制给体感进度：
   * - Pattern 生成:  0% → 5%
   * - 阶段1 巡游:    5% → 60%
   * - 阶段2 深化:    60% → 95%
   * - 完成:          100%
   *
   * 关键：使用 maxProgress 保证进度只增不减
   */
  let maxProgress = 0

  function calculateProgress(
    phase: 'pattern_generating' | 'pattern_sweep' | 'judge_driven',
    completedPatterns: number,
    totalPatterns: number,
    coveragePercentage: number
  ): number {
    let progress: number

    if (phase === 'pattern_generating') {
      // Pattern 生成阶段: 0% → 5%
      progress = 3
    } else if (phase === 'pattern_sweep') {
      // 阶段 1: 5% → 60%
      progress = 5 + Math.round((completedPatterns / totalPatterns) * 55)
    } else {
      // 阶段 2: 60% → 95%
      progress = 60 + Math.round((coveragePercentage / 100) * 35)
    }

    // 保证单调递增，不会回退
    maxProgress = Math.max(maxProgress, progress)
    return maxProgress
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Step 0: 获取 Plan（如未提供则自动生成）
  // ═══════════════════════════════════════════════════════════════════════════
  let plan: ScenarioPlan

  if (providedPlan) {
    plan = providedPlan
    console.log('\n========================================')
    console.log('   场景生成启动（使用提供的 Plan）')
    console.log('========================================')
  } else {
    console.log('\n========================================')
    console.log('   场景生成启动（自动生成 Plan）')
    console.log('========================================')

    const { generateScenarioPlan } = await import('./scenario-planner.js')
    const generatedPlan = await generateScenarioPlan(query, tagTree, client)

    // 构造完整 Plan（补充 metadata）
    plan = {
      ...generatedPlan,
      task_id: `task-${Date.now()}`,
      tag_tree_name: '', // 需要外部填充
    } as ScenarioPlan
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Step 0.5: 获取 Patterns 和 targetScenarioCount
  // ═══════════════════════════════════════════════════════════════════════════
  let patterns: string[]
  let targetScenarioCount: number  // 由 Pattern Generator 决定，非 Plan 字段
  if (providedPatterns && providedPatterns.length > 0) {
    patterns = providedPatterns
    targetScenarioCount = Math.max(10, patterns.length, plan.target_tags.length * 2)
    console.log(`  使用外部提供的 Patterns: ${patterns.length} 个`)
  } else {
    console.log('\n========================================')
    console.log('   自动生成 Patterns（基于 Plan）')
    console.log('========================================')

    onProgress?.({
      iteration: 0,
      batchSize: 0,
      totalScenarios: 0,
      targetScenarioCount: 0, // 待 Pattern 生成后确定
      progressPercentage: calculateProgress('pattern_generating', 0, 0, 0),
      coveragePercentage: 0,
      satisfied: false,
      stage: 'pattern_generating',
      currentStep: '正在基于 Plan 生成场景模式（Patterns）...',
    })

    const { generateScenarioPatterns } = await import('./scenario-pattern-generator.js')
    const patternResult = await generateScenarioPatterns(plan, tagTree, client)
    patterns = patternResult.patterns
    targetScenarioCount = patternResult.targetScenarioCount
    onPatternsGenerated?.(patterns, targetScenarioCount)
  }

  // 安全阀：基于 targetScenarioCount 和 patterns 数取最大值，防止无限生成
  const maxSafeCount = Math.max(targetScenarioCount * 10, patterns.length * 15)

  console.log(`  Plan Task ID: ${plan.task_id || 'auto-generated'}`)
  console.log(`  目标场景数: ${targetScenarioCount}`)
  console.log(`  目标标签数: ${plan.target_tags.length}`)
  console.log(`  场景模式数: ${patterns.length}`)
  console.log(`  安全上限: ${maxIterations} 轮迭代（阶段2）| ${maxSafeCount} 个场景`)
  console.log('========================================\n')

  // ═══════════════════════════════════════════════════════════════════════════
  // 公共状态
  // ═══════════════════════════════════════════════════════════════════════════
  let allScenarios: Scenario[] = []
  const existingIds = new Set<string>()
  // 共享的场景名去重集合：实时维护，支持阶段1并发随产随推的正确去重
  // （check + add 在同一同步段内完成，无 await 间隔，并发安全）
  const existingNames = new Set<string>()
  const relevantTags = plan.target_tags

  // Pattern 覆盖追踪
  const patternScenarioCount = new Map<string, number>()
  for (const pattern of patterns) {
    patternScenarioCount.set(pattern, 0)
  }
  // scenario_id -> pattern 归属记录
  const scenarioPatternMap = new Map<string, string>()

  let lastKnownCoveragePercentage = 0

  const { judgeScenarioCoverage, analyzeRelevantTagCoverage, detectDuplicateScenarios, filterScenariosByHardConstraints } = await import('./scenario-judge.js')
  const { generateAndRefineBatch } = await import('./scenario-generator.js')

  /**
   * 处理一批新生成的场景：去重 + 流式输出 + 更新 pattern 统计
   *
   * 去重策略：
   * - scenario_id 重复时，**重新分配唯一 ID**（而非丢弃），因为内容可能不同，只是 ID 撞了
   * - scenario_name 完全相同才视为真正的重复，跳过
   *
   * @returns 新增的场景数
   */
  async function ingestBatchScenarios(
    batchScenarios: Scenario[],
    pattern: string,
    iteration: number
  ): Promise<number> {
    let addedCount = 0
    // 使用共享 existingNames（实时维护），不再每次调用快照 allScenarios
    // 以支持阶段 1 并发随产随推时跨 pattern 的正确去重

    for (const scenario of batchScenarios) {
      // 真正的重复：场景名完全相同，跳过（同步 check，并发安全）
      if (existingNames.has(scenario.scenario_name)) {
        console.log(`    [去重] 跳过重复场景（名称相同）: ${scenario.scenario_name}`)
        continue
      }

      // scenario_id 撞了但内容不同：重新分配唯一 ID
      if (existingIds.has(scenario.scenario_id)) {
        const newId = `scenario-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
        console.log(`    [去重] scenario_id 冲突，重新分配: ${scenario.scenario_id} → ${newId}`)
        scenario.scenario_id = newId
      }

      allScenarios.push(scenario)
      existingIds.add(scenario.scenario_id)
      existingNames.add(scenario.scenario_name)
      scenarioPatternMap.set(scenario.scenario_id, pattern)
      patternScenarioCount.set(pattern, (patternScenarioCount.get(pattern) || 0) + 1)
      addedCount++

      const currentStats = analyzeRelevantTagCoverage(allScenarios, relevantTags)
      const currentCoverage = Math.round((currentStats.coveredTags.size / relevantTags.length) * 100)
      const currentProgress = Math.round((allScenarios.length / targetScenarioCount) * 100)

      await onScenarioGenerated?.(scenario, {
        iteration,
        totalScenarios: allScenarios.length,
        targetScenarioCount: targetScenarioCount,
        progressPercentage: currentProgress,
        coveragePercentage: currentCoverage,
        pattern,
        isProvisional: true,
      })
    }
    return addedCount
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 阶段 1: Pattern 首轮巡游（强制完成，不计入 maxIterations）
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('\n════════════════════════════════════════════')
  console.log('  阶段 1: Pattern 首轮巡游（并发优化）')
  console.log('════════════════════════════════════════════\n')

  const patternsList = patterns
  const maxBatchAttemptsPerPattern = 3  // 每个 pattern 最多 3 批兜底（含失败重试）

  // 阶段 1 每个 pattern 的最低目标：1 个（保证覆盖）
  // 不强制固定数量——不同 pattern 的可泛化空间不同：
  //   空间大的 pattern（如"单轮直达空调控制"）一次能产出 10+ 个场景
  //   空间小的 pattern（如"行驶中开门拒绝"）可能只有 1-2 个
  // LLM 会根据 pattern 自然泛化，代码只保证至少 1 个合格场景
  const patternTargetCount = 1
  console.log(`  阶段 1 每个 pattern 最低目标: ${patternTargetCount} 个（LLM 自然泛化，不强制凑数）`)
  console.log(`  并发限制: 同时处理 ${Math.min(25, patterns.length)} 个 pattern（豆包 API 峰值 40 并发）\n`)

  // 创建并发限制器
  // 豆包 API 限制 50，峰值设 40，pattern 并发占 25
  // pattern 25 + 审核 35 = 60（有重叠，实际峰值约 40）
  const patternLimit = pLimit(25)

  // 阶段1已完成 pattern 计数器（并发安全：JS 单线程，++操作原子）
  let phase1CompletedPatterns = 0

  // 并发处理所有 pattern（随产随推，无需收集结果到合并阶段）
  await Promise.all(
    patterns.map((pattern, pIdx) => patternLimit(async () => {
      ensureNotStopped()
      console.log(`\n--- Pattern ${pIdx + 1}/${patterns.length}: ${pattern} ---`)

      let patternAccumulated = 0  // 本 pattern 已累计合格场景数
      const orientedQuery = buildOrientedQuery(plan, pattern)

      for (let attempt = 1; attempt <= maxBatchAttemptsPerPattern; attempt++) {
        ensureNotStopped()
        // 已达本 pattern 目标，跳走
        if (patternAccumulated >= patternTargetCount) break

        // 剩余需要的场景数（目标 1，但 LLM 可能一次产出多个，都是有效产出）
        const remainingNeeded = patternTargetCount - patternAccumulated
        const batchSz = Math.min(initialBatchSize, Math.max(3, remainingNeeded))

        console.log(`  [尝试 ${attempt}/${maxBatchAttemptsPerPattern}] 生成 pattern: ${pattern}，本批目标 ${batchSz} 个`)

        // 阶段 1 进度：基于实际已完成的 pattern 数（单调递增）
        const phase1Progress = calculateProgress(
          'pattern_sweep',
          phase1CompletedPatterns,
          patterns.length,
          lastKnownCoveragePercentage
        )

        onProgress?.({
          iteration: 0,
          batchSize: batchSz,
          totalScenarios: allScenarios.length,
          targetScenarioCount: targetScenarioCount,
          progressPercentage: phase1Progress,
          coveragePercentage: lastKnownCoveragePercentage,
          satisfied: false,
          stage: 'generating',
          currentPattern: pattern,
          phase: 'pattern_sweep',
          currentStep: `正在生成场景（阶段1：${phase1CompletedPatterns}/${patterns.length} 个模式已完成，当前: ${pattern}）`,
        })

        // 阶段 1 也传入已生成场景摘要，避免 LLM 生成重复场景
        // 并发模式下随产随推：allScenarios 已包含本 pattern 及其他并发 pattern 已产出的场景
        const existingScenariosSummary = allScenarios.length > 0
          ? allScenarios.slice(-20).map(s => {
              const intent = s.description.substring(0, 80).replace(/\n/g, ' ')
              return `- ${s.scenario_name} — ${intent}${s.description.length > 80 ? '...' : ''}`
            }).join('\n')
          : '暂无已生成场景'

        const sweepGuidance: GenerationGuidance = {
          focus_tags: [],
          avoid_tags: [],
          scenario_types: [pattern],
          guidance: `本次聚焦生成场景模式：${pattern}

【已生成场景参考】（请确保新场景与这些在核心测试意图上不同，包括 scenario_id 必须唯一）：
${existingScenariosSummary}`,
          suggested_count: batchSz,
        }

        const batchResult = await generateAndRefineBatch(
          orientedQuery,
          tagTree,
          client,
          {
            batchSize: batchSz,
            guidance: sweepGuidance,
            maxRefineRounds: maxRefineRoundsPerBatch,
            auditConcurrency,
            fixConcurrency,
            shouldStop,
            signal,
          }
        )

        console.log(`  [结果] 本批次产出 ${batchResult.scenarios.length} 个优质场景`)

        if (batchResult.scenarios.length > 0) {
          // 为每个场景填充 pattern 字段
          for (const s of batchResult.scenarios) {
            s.pattern = pattern
          }
          // 随产随推：立即去重 + 流式输出（不缓冲到本地，避免阶段1全程无流式输出）
          const addedNow = await ingestBatchScenarios(batchResult.scenarios, pattern, 0)
          patternAccumulated += addedNow
          console.log(`  ✅ Pattern "${pattern}" 产出 ${patternAccumulated} 个合格场景（本轮新增 ${addedNow}，去重 ${batchResult.scenarios.length - addedNow}）`)
        }

        if (patternAccumulated < patternTargetCount && attempt < maxBatchAttemptsPerPattern) {
          console.log(`  ⚠️ 本 pattern 暂无合格场景，重试...`)
        }
      }

      if (patternAccumulated === 0) {
        console.warn(`  ⚠️ Pattern "${pattern}" ${maxBatchAttemptsPerPattern} 批后仍无合格场景，跳过`)
      } else {
        console.log(`  ✅ Pattern "${pattern}" 阶段1完成，共 ${patternAccumulated} 个场景`)
      }

      // 本 pattern 完成，递增已完成计数器
      phase1CompletedPatterns++
    }))
  )

  // 阶段 1 已随产随推：每个 pattern 的批次产出后立即通过 ingestBatchScenarios
  // 去重 + 流式推送到前端，无需在全部 pattern 完成后再合并
  console.log(`\n--- 阶段 1 流式推送完成 ---`)
  console.log(`  [阶段1累计] 共 ${allScenarios.length} 个场景`)

  // 阶段 1 结束后计算覆盖率（用于进度显示）
  {
    const stats = analyzeRelevantTagCoverage(allScenarios, relevantTags)
    lastKnownCoveragePercentage = Math.round((stats.coveredTags.size / relevantTags.length) * 100)
  }

  console.log(`\n════════════════════════════════════════════`)
  console.log(`  阶段 1 完成: ${allScenarios.length} 个场景`)
  console.log(`  Pattern 覆盖: ${[...patternScenarioCount.values()].filter(c => c > 0).length}/${patterns.length} 个 pattern 有场景`)
  console.log(`  标签覆盖: ${lastKnownCoveragePercentage}%`)
  console.log(`════════════════════════════════════════════\n`)

  // ═══════════════════════════════════════════════════════════════════════════
  // 阶段 2: Judge 全局驱动的深化（计入 maxIterations）
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('\n════════════════════════════════════════════')
  console.log('  阶段 2: Judge 全局驱动的深化')
  console.log('════════════════════════════════════════════\n')

  let iteration = 0
  let satisfied = false

  while (iteration < maxIterations) {
    ensureNotStopped()
    iteration++

    // 硬性安全阀
    if (allScenarios.length >= maxSafeCount) {
      console.log(`  ⚠️ 已达到场景数量安全上限 (${maxSafeCount})，停止生成`)
      break
    }

    console.log(`\n--- 阶段 2 迭代 ${iteration}/${maxIterations} ---`)
    console.log(`  当前: ${allScenarios.length}/${targetScenarioCount} (${Math.round((allScenarios.length / targetScenarioCount) * 100)}%)`)

    // Judge 全局评估（传入 pattern 覆盖信息）
    const currentStatsBeforeJudge = analyzeRelevantTagCoverage(allScenarios, relevantTags)
    const currentCoverageBeforeJudge = Math.round((currentStatsBeforeJudge.coveredTags.size / relevantTags.length) * 100)

    console.log('  [Judge] 全局评估覆盖度 + Pattern 均衡度...')

    // 阶段 2 进度：基于标签覆盖率（50% - 99%）
    const phase2ProgressJudging = calculateProgress(
      'judge_driven',
      patterns.length,
      patterns.length,
      currentCoverageBeforeJudge
    )

    onProgress?.({
      iteration,
      batchSize: 0,
      totalScenarios: allScenarios.length,
      targetScenarioCount: targetScenarioCount,
      progressPercentage: phase2ProgressJudging,
      coveragePercentage: currentCoverageBeforeJudge,
      satisfied: false,
      stage: 'judging',
      phase: 'judge_driven',
      currentStep: `正在去除重复场景并评估覆盖率（阶段2，第 ${iteration} 轮）`,
    })

    const patternInfo = {
      scenario_patterns: patterns,
      patternScenarioCount,
    }

    // ── 独立的场景去重检测（在 Judge 之前执行）──
    // 从 Judge 中拆出，只做一件事：判断场景对是否语义重复
    // 策略：程序化预筛疑似重复对 + 强制 LLM 逐对二选一判断
    const duplicateIds = await detectDuplicateScenarios(allScenarios, client)
    if (duplicateIds.length > 0) {
      const dupIdSet = new Set(duplicateIds)
      const beforeCount = allScenarios.length
      allScenarios = allScenarios.filter(s => {
        if (dupIdSet.has(s.scenario_id)) {
          // 同步更新 pattern 统计
          const p = scenarioPatternMap.get(s.scenario_id)
          if (p) {
            patternScenarioCount.set(p, Math.max(0, (patternScenarioCount.get(p) || 0) - 1))
          }
          scenarioPatternMap.delete(s.scenario_id)
          existingIds.delete(s.scenario_id)
          existingNames.delete(s.scenario_name)
          // 通知外部（SSE 路由同步删除 DB 记录 + 前端移除）
          onScenarioDeleted?.(s.scenario_id, s.scenario_name, '语义重复')
          return false
        }
        return true
      })
      const removedCount = beforeCount - allScenarios.length
      console.log(`  [去重] 独立检测判定 ${duplicateIds.length} 个语义重复场景，实际移除 ${removedCount} 个`)
      for (const id of duplicateIds) {
        console.log(`    - 移除: ${id}`)
      }
    }

    // ── 硬约束校验（在去重之后、Judge 之前执行）──
    // 剔除违反 query 硬约束的场景（如 query 限定仅使用能力A，却生成了以能力B为主任务的场景）
    if (plan.hard_constraints && plan.hard_constraints.length > 0) {
      const violatedIds = await filterScenariosByHardConstraints(allScenarios, plan.hard_constraints, client)
      if (violatedIds.length > 0) {
        const violatedSet = new Set(violatedIds)
        const beforeCount = allScenarios.length
        allScenarios = allScenarios.filter(s => {
          if (violatedSet.has(s.scenario_id)) {
            const p = scenarioPatternMap.get(s.scenario_id)
            if (p) {
              patternScenarioCount.set(p, Math.max(0, (patternScenarioCount.get(p) || 0) - 1))
            }
            scenarioPatternMap.delete(s.scenario_id)
            existingIds.delete(s.scenario_id)
            return false
          }
          return true
        })
        const removedCount = beforeCount - allScenarios.length
        console.log(`  [硬约束] 校验判定 ${violatedIds.length} 个场景违反硬约束，实际移除 ${removedCount} 个`)
      }
    }

    const judgement = await judgeScenarioCoverage(
      allScenarios,
      plan.task_description,
      tagTree,
      client,
      relevantTags,
      patternInfo
    )

    const coveragePercentage = judgement.current_stats.coverage_percentage
    lastKnownCoveragePercentage = coveragePercentage

    // 检查停止必要条件
    // targetScenarioCount 不再作为停止的必要条件，仅用于安全阀和进度展示
    // 停止条件：patterns 全覆盖 AND (标签全覆盖 OR Judge满意)
    const allPatternsCovered = [...patternScenarioCount.values()].every(c => c >= 1)
    const fullyCovered = coveragePercentage >= 100
    const cannotImprove = judgement.satisfied || !judgement.guidance

    console.log(`    标签覆盖: ${judgement.current_stats.covered_relevant_tags}/${relevantTags.length} (${coveragePercentage}%)`)
    console.log(`    Pattern 覆盖: ${[...patternScenarioCount.values()].filter(c => c > 0).length}/${patterns.length}`)
    console.log(`    场景总数: ${allScenarios.length}（参考下限 ${targetScenarioCount}）`)

    // 两必要条件全满足才停止（target 仅作参考，不再是必要条件）
    if (allPatternsCovered && (fullyCovered || cannotImprove)) {
      satisfied = true
      console.log('  ✅ 停止条件满足（pattern全覆盖 + 标签全覆盖/Judge满意），停止生成')
      break
    }

    // 获取 Judge guidance（必含 target_pattern，除非 satisfied）
    const guidance = judgement.guidance
    if (!guidance) {
      console.log('  ⚠️ Judge 未给出 guidance，停止生成')
      break
    }

    // 阶段 2 需要 target_pattern（由代码程序化选择，不再依赖 LLM）
    if (!guidance.target_pattern) {
      console.warn('  ⚠️ 无法确定 target_pattern（patterns 列表为空），停止生成')
      break
    }

    const targetPattern: string = guidance.target_pattern!
    const patternCount = patternScenarioCount.get(targetPattern) || 0
    console.log(`    下一轮聚焦 pattern: ${targetPattern}（当前 ${patternCount} 个场景）`)
    console.log(`    重点标签: ${guidance.focus_tags.slice(0, 6).join(', ')}${guidance.focus_tags.length > 6 ? '...' : ''}`)

    // 确定本批次生成参数
    const batchSize = Math.min(
      guidance.suggested_count || 5,
      maxSafeCount - allScenarios.length
    )

    if (batchSize <= 0) {
      console.log('  已达到安全上限，停止生成')
      break
    }

    // 构建定向 query（基于 target_pattern）
    const orientedQuery = buildOrientedQuery(plan, targetPattern)

    // 构建增强 guidance：加入已生成场景摘要避免重复
    // 摘要包含：归属 Pattern + 场景名 + 核心测试意图（描述前 80 字），信息更丰富便于 LLM 避免语义重复
    const existingScenariosSummary = allScenarios.length > 0
      ? allScenarios.slice(-20).map(s => {
          const p = scenarioPatternMap.get(s.scenario_id) || '未分类'
          const intent = s.description.substring(0, 80).replace(/\n/g, ' ')
          return `- [${p}] ${s.scenario_name} — ${intent}${s.description.length > 80 ? '...' : ''}`
        }).join('\n')
      : '暂无已生成场景'

    const enhancedGuidance: GenerationGuidance = {
      ...guidance,
      guidance: `${guidance.guidance}

【已生成场景参考】（请确保新场景与这些在核心测试意图上不同）：
${existingScenariosSummary}`,
    }

    // 阶段 2 生成阶段进度（使用 Judge 评估的覆盖率）
    const phase2ProgressGenerating = calculateProgress(
      'judge_driven',
      patterns.length,
      patterns.length,
      coveragePercentage
    )

    onProgress?.({
      iteration,
      batchSize,
      totalScenarios: allScenarios.length,
      targetScenarioCount: targetScenarioCount,
      progressPercentage: phase2ProgressGenerating,
      coveragePercentage,
      satisfied: false,
      stage: 'generating',
      currentPattern: targetPattern,
      phase: 'judge_driven',
      currentStep: `正在按"${targetPattern}"生成场景（阶段2，第 ${iteration} 轮）`,
    })

    // 生成 + 审核 + 修复
    console.log(`  [生成+审核+修复] 按 pattern "${targetPattern}" 生成 ${batchSize} 个场景...`)

    const batchResult = await generateAndRefineBatch(
      orientedQuery,
      tagTree,
      client,
      {
        batchSize,
        guidance: enhancedGuidance,
        maxRefineRounds: maxRefineRoundsPerBatch,
        auditConcurrency,
        fixConcurrency,
        shouldStop,
        signal,
      }
    )

    console.log(`  [结果] 本批次产出 ${batchResult.scenarios.length} 个优质场景`)

    if (batchResult.scenarios.length === 0) {
      console.warn('  ⚠️ 本批次未产出任何优质场景')
      continue
    }

    // 去重 + 流式输出 + 记录归属（归属到 target_pattern）
    ensureNotStopped()
    // 为每个场景填充 pattern 字段
    for (const s of batchResult.scenarios) {
      s.pattern = targetPattern
    }
    const added = await ingestBatchScenarios(batchResult.scenarios, targetPattern, iteration)
    if (added < batchResult.scenarios.length) {
      console.log(`  [去重] 本批次有效新增: ${added}/${batchResult.scenarios.length}`)
    }
    console.log(`  [累计] 优质场景总数: ${allScenarios.length}`)

    // 进度回调（生成后）
    onProgress?.({
      iteration,
      batchSize,
      totalScenarios: allScenarios.length,
      targetScenarioCount: targetScenarioCount,
      progressPercentage: phase2ProgressGenerating,
      coveragePercentage,
      satisfied: false,
      stage: 'generating',
      currentPattern: targetPattern,
      phase: 'judge_driven',
      currentStep: `已按"${targetPattern}"生成 ${batchResult.scenarios.length} 个场景，累计 ${allScenarios.length}/${targetScenarioCount}`,
    })
  }

  // 循环退出后：发送最终的 100% 进度（真正停止才到 100%）
  onProgress?.({
    iteration,
    batchSize: 0,
    totalScenarios: allScenarios.length,
    targetScenarioCount: targetScenarioCount,
    progressPercentage: 100,
    coveragePercentage: lastKnownCoveragePercentage,
    satisfied: true,
    stage: 'judging',
    phase: 'judge_driven',
    currentStep: `场景生成完成，共 ${allScenarios.length} 个场景`,
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Step 2: 返回最终结果
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('\n========================================')
  console.log('     场景生成完成')
  console.log('========================================')
  console.log(`  目标数量（下限）: ${targetScenarioCount}`)
  console.log(`  实际生成: ${allScenarios.length}`)
  const finalAchievementRate = Math.round((allScenarios.length / targetScenarioCount) * 100)
  console.log(`  达成率: ${finalAchievementRate}%`)
  console.log(`  阶段 2 总迭代: ${iteration} 轮`)

  const finalStats = analyzeRelevantTagCoverage(allScenarios, relevantTags)
  const finalCoverage = Math.round((finalStats.coveredTags.size / relevantTags.length) * 100)

  console.log(`  标签覆盖率: ${finalCoverage}%`)
  console.log(`  Pattern 覆盖:`)
  for (const [pattern, count] of patternScenarioCount.entries()) {
    console.log(`    - ${pattern}: ${count} 个`)
  }
  console.log(`  满足需求: ${satisfied ? '是 ✓' : '否'}`)
  console.log('========================================\n')

  // 转换 patternCoverage 为普通对象
  const patternCoverageObj: Record<string, number> = {}
  for (const [pattern, count] of patternScenarioCount.entries()) {
    patternCoverageObj[pattern] = count
  }

  return {
    scenarios: allScenarios,
    plan,
    totalIterations: iteration,
    finalCoveragePercentage: finalCoverage,
    satisfied,
    targetCount: targetScenarioCount,
    actualCount: allScenarios.length,
    patternCoverage: patternCoverageObj,
  }
}

export default generateScenarios
