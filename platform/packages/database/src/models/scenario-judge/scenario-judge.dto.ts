import { z } from 'zod'

// ═══════════════════════════════════════════════════════════════════════════
// 场景判别 Schema (Scenario Judgement)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 标签覆盖统计 Schema
 * 动态记录每个标签的覆盖次数
 */
export const TagCoverageSchema = z.record(z.string(), z.number())

/**
 * 维度覆盖统计 Schema
 * 各功能维度的覆盖情况统计
 */
export const DimensionCoverageSchema = z.object({
  car_control: z.number(),
  navigation: z.number(),
  media: z.number(),
  memory: z.number(),
  联网查询: z.number(),
  dialogue: z.number(),
  structure: z.number(),
  safety: z.number(),
})

/**
 * 缺口分析 Schema
 */
export const GapAnalysisSchema = z.object({
  /** 未被覆盖的相关标签 */
  uncovered_relevant_tags: z.array(z.string()),
  /** Query 意图满足度 (0-100) */
  query_intent_fulfillment: z.number().min(0).max(100),
  /** 覆盖深度分 (0-100)，避免蜻蜓点水 */
  coverage_depth_score: z.number().min(0).max(100),
  /** 综合建议 */
  suggestion: z.string(),
})

/**
 * 指导意见 Schema
 * Judge 给出的下一轮生成指导
 */
export const GenerationGuidanceSchema = z.object({
  /** 重点覆盖的标签 */
  focus_tags: z.array(z.string()),
  /** 避免重复的标签（已充分覆盖） */
  avoid_tags: z.array(z.string()),
  /** 建议的场景类型 */
  scenario_types: z.array(z.string()),
  /** 自然语言生成指导 */
  guidance: z.string(),
  /** 建议生成数量 */
  suggested_count: z.number().int().optional(),
  /**
   * 下一轮应聚焦的场景模式（来自 Plan.scenario_patterns）
   * Pattern 驱动的迭代生成模式下，Judge 必须指定（除非 satisfied=true）
   */
  target_pattern: z.string().nullable().optional(),
  /**
   * 被判为语义重复的场景 ID 列表（流式输出后由 Judge 评估，主流程会移除这些场景）
   * 判断标准：核心测试意图相同（即使场景名不同）
   */
  duplicate_scenarios: z.array(z.string()).optional(),
})

/**
 * 判别结果 Schema
 * Judge 对当前场景集合的综合评估
 */
export const JudgementResultSchema = z.object({
  /** 是否满足设计需求 */
  satisfied: z.boolean(),

  /** 当前统计 */
  current_stats: z.object({
    /** 场景总数 */
    total_scenarios: z.number().int().nonnegative(),
    /** 相关标签总数 */
    relevant_tag_count: z.number().int().nonnegative(),
    /** 已覆盖的相关标签数 */
    covered_relevant_tags: z.number().int().nonnegative(),
    /** 相关标签覆盖率 (0-100) */
    coverage_percentage: z.number().min(0).max(100),
    /** 平均每场景标签数 */
    avg_tags_per_scenario: z.number(),
  }),

  /** 缺口分析 */
  gap_analysis: GapAnalysisSchema,

  /**
   * 指导意见
   * 若 satisfied=true，此项为 null
   */
  guidance: GenerationGuidanceSchema.nullable(),

  /** 满足原因（若 satisfied=true） */
  stop_reason: z.string().optional(),
})

/**
 * LLM 输出的原始判别结果 Schema（内部使用）
 * 用于解析 LLM 返回的原始数据
 */
export const LLMJudgementOutputSchema = z.object({
  judgement: z.object({
    satisfied: z.boolean(),
    gap_analysis: z.object({
      uncovered_relevant_tags: z.array(z.string()).nullable(),
      query_intent_fulfillment: z.number().nullable(),
      coverage_depth_score: z.number().nullable(),
      suggestion: z.string().nullable().describe('覆盖度分析建议，必须使用中文'),
    }),
    refinement_direction: z
      .object({
        next_batch_size: z.number().nullable(),
        focus_tags: z.array(z.string()).nullable(),
        avoid_tags: z.array(z.string()).nullable(),
        scenario_types: z.array(z.string()).nullable(),
        generation_guidance: z.string().nullable().describe('生成指导建议，必须使用中文'),
        stop_reason: z.string().nullable().describe('停止原因，必须使用中文'),
        /** 被判为语义重复的场景 ID 列表 */
        duplicate_scenarios: z.array(z.string()).nullable(),
      })
      .nullable(),
  }),
})

// ═══════════════════════════════════════════════════════════════════════════
// 类型导出
// ═══════════════════════════════════════════════════════════════════════════

export type TagCoverage = z.infer<typeof TagCoverageSchema>
export type DimensionCoverage = z.infer<typeof DimensionCoverageSchema>
export type GapAnalysis = z.infer<typeof GapAnalysisSchema>
export type GenerationGuidance = z.infer<typeof GenerationGuidanceSchema>
export type JudgementResult = z.infer<typeof JudgementResultSchema>
export type LLMJudgementOutput = z.infer<typeof LLMJudgementOutputSchema>
