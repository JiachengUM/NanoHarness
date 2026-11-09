import { z } from 'zod'
import { CreateSchema, PageSchema, UpdateSchema, OutSchema } from '../../base/dto'

/**
 * 场景生成计划相关 DTO
 */

// ═══════════════════════════════════════════════════════════════════════════
// Schema 定义
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 单条硬约束
 */
export const HardConstraintSchema = z.object({
  /** 约束类型 */
  type: z
    .enum([
      'capability_required', // 必须使用的能力（如"联网搜索"）
      'capability_excluded', // 禁止使用的能力（如"不涉及其他技能"）
      'interaction_pattern', // 交互模式约束（如"单轮对话""至少5次搜索"）
      'theme', // 主题约束（如"出行生活""用车场景"）
      'difficulty', // 难度约束（如"常见复杂问题"）
      'other', // 其他
    ])
    .describe('硬约束类型'),
  /** 约束内容（中文，一句话描述） */
  description: z.string().min(1).describe('约束内容的中文描述'),
})
export type HardConstraint = z.infer<typeof HardConstraintSchema>

/**
 * 场景生成计划 Schema
 */
export const ScenarioPlanSchema = z.object({
  task_id: z.string().optional(),
  generation_task_run_id: z.string().optional(),
  original_query: z.string().min(1),
  task_description: z.string().min(1),
  target_tags: z.array(z.string()).min(1),
  interpretation_notes: z.string().min(1),
  /**
   * 从 query 中提取的硬约束列表
   * 这些约束必须贯穿 Pattern Generator / 场景生成 / Judge 全链路，
   * 任何场景若违反硬约束应被剔除或触发重新生成。
   */
  hard_constraints: z.array(HardConstraintSchema).default([]),
  status: z.enum(['pending', 'confirmed', 'generating', 'completed', 'cancelled']).default('pending'),
  tag_tree_name: z.string().min(1),
  target_scenario_count: z.number().optional(),
})

export const CreateScenarioPlanSchema = ScenarioPlanSchema.extend(CreateSchema.shape)

export const UpdateScenarioPlanSchema = ScenarioPlanSchema.partial().extend(UpdateSchema.shape)

export const OutScenarioPlanSchema = ScenarioPlanSchema.extend(OutSchema.shape)

/**
 * 创建 Plan 请求 Schema
 */
export const CreateScenarioPlanRequestSchema = z.object({
  query: z.string().min(1, '查询描述不能为空'),
  tag_tree_name: z.string().min(1, '标签树名称不能为空'),
  task_id: z.string().min(1, '任务ID不能为空'),
})

/**
 * 列表查询参数 Schema
 */
export const ListScenarioPlanSchema = z.object({
  task_id: z.string().optional(),
  generation_task_run_id: z.string().optional(),
  status: z.enum(['pending', 'confirmed', 'generating', 'completed', 'cancelled']).optional(),
})

export const PageScenarioPlanSchema = ListScenarioPlanSchema.extend(PageSchema.shape)

// ═══════════════════════════════════════════════════════════════════════════
// 类型导出
// ═══════════════════════════════════════════════════════════════════════════

export type ScenarioPlan = z.infer<typeof ScenarioPlanSchema>
export type OutScenarioPlanDto = z.infer<typeof OutScenarioPlanSchema>
export type CreateScenarioPlanDto = z.input<typeof CreateScenarioPlanSchema>
export type UpdateScenarioPlanDto = z.input<typeof UpdateScenarioPlanSchema>
export type ListScenarioPlanDto = z.infer<typeof ListScenarioPlanSchema>
export type PageScenarioPlanDto = z.infer<typeof PageScenarioPlanSchema>

export type CreateScenarioPlanRequest = z.infer<typeof CreateScenarioPlanRequestSchema>

// ═══════════════════════════════════════════════════════════════════════════
// LLM 输出 Schema（用于 zodTextFormat）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Planner LLM 输出 Schema
 * 用于约束 LLM 生成 Plan 的结构
 */
export const PlannerOutputSchema = z.object({
  plan: z.object({
    task_description: z
      .string()
      .describe(
        '改写后的详细任务描述，无歧义，可直接用于生成和判别。必须完整保留原始query中的所有硬性约束（能力、交互、主题、难度等）。',
      ),
    target_tags: z.array(z.string()).min(1).describe('目标覆盖的标签列表，应尽量全面'),
    interpretation_notes: z.string().describe('对原始query的理解注解，帮助用户确认需求'),
    hard_constraints: z
      .array(HardConstraintSchema)
      .describe(
        '从query中提取的硬性约束列表。必须覆盖query中所有明确或隐含的硬约束（必须用的能力、禁止用的能力、交互模式、主题、难度等）。绝大多数测试query都含硬约束，请仔细挖掘，不要轻易返回空数组。',
      ),
  }),
})

export type PlannerOutput = z.infer<typeof PlannerOutputSchema>
