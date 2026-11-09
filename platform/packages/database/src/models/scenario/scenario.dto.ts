import { z } from 'zod'
import { PageSchema, PageParamDto, OutSchema } from './../../base/dto'

// ═══════════════════════════════════════════════════════════════════════════
// 场景 Schema (Scenario)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 场景信息 Schema
 * 对应老项目数据合成流程的「环节3：场景模板与覆盖采样」输出
 */
export const ScenarioSchema = z.object({
  scenario_id: z.string().min(1, '场景ID不能为空'),
  scenario_name: z.string().min(1, '场景名称不能为空'),
  description: z.string().min(1, '场景描述不能为空'),
  tags: z.array(z.string()).min(1, '至少需要一个标签'),
  /** 该场景归属的场景模式（由 Pattern Generator 生成时填充，LLM 不生成此字段） */
  pattern: z.string().optional(),
})

/**
 * LLM 场景输出 Schema（不含 pattern 字段，因为 pattern 由程序后填充）
 * 用于 zodTextFormat 转 OpenAI JSON Schema（strict mode 要求所有字段 required）
 */
export const LLMScenarioSchema = z.object({
  scenario_id: z.string().min(1, '场景ID不能为空'),
  scenario_name: z.string().min(1, '场景名称不能为空'),
  description: z.string().min(1, '场景描述不能为空'),
  tags: z.array(z.string()).min(1, '至少需要一个标签'),
})

/**
 * 场景列表包装 Schema（用于 LLM JSON Schema 输出）
 * 使用 LLMScenarioSchema（不含 pattern），pattern 由程序在生成后填充
 */
export const ScenarioListSchema = z.object({
  scenarios: z.array(LLMScenarioSchema).min(1, '至少需要一个场景'),
})

/**
 * 场景生成配置选项 Schema
 */
export const ScenarioGenerationOptionsSchema = z.object({
  count: z.number().int().positive().optional(),
  categories: z.array(z.string()).optional(),
  requireCrossDomain: z.boolean().default(true),
  temperature: z.number().min(0).max(2).default(0.7),
})

/**
 * 创建场景 DTO（入库用）
 */
export const CreateScenarioSchema = z.object({
  scenario_id: z.string().min(1, '场景ID不能为空'),
  scenario_name: z.string().min(1, '场景名称不能为空'),
  description: z.string().min(1, '场景描述不能为空'),
  tags: z.array(z.string()).min(1, '至少需要一个标签'),
  /** 该场景归属的场景模式 */
  pattern: z.string().optional(),
  // 可选：关联的标签树 ID
  tag_tree_id: z.string().optional(),
  // 可选：来源 query
  source_query: z.string().optional(),
  // 可选：关联的生成任务 ID
  generation_task_id: z.string().optional(),
  // 可选：关联的场景生成计划 ID
  scenario_plan_id: z.string().optional(),
})

/**
 * 输出场景 DTO
 */
export const OutScenarioSchema = CreateScenarioSchema.extend(OutSchema.shape)

/**
 * 更新场景 DTO
 */
export const UpdateScenarioSchema = CreateScenarioSchema.partial()

/**
 * 查询场景列表 DTO
 */
export const ListScenarioSchema = z.object({
  keyword: z.string().optional(),
  tag: z.string().optional(),
  tag_tree_id: z.string().optional(),
  generation_task_id: z.string().optional(),
  // 可选：关联的场景生成计划 ID
  scenario_plan_id: z.string().optional(),
  generation_task_run_id: z.string().optional(),
})

/**
 * 分页查询场景 DTO
 */
export const PageScenarioSchema = ListScenarioSchema.extend(PageSchema.shape)

/**
 * 批量创建场景 DTO
 */
export const BatchCreateScenarioSchema = z.object({
  items: z.array(CreateScenarioSchema).min(1, '至少需要一个场景'),
})

/**
 * 批量更新场景 DTO - 单项
 */
export const BatchUpdateScenarioItemSchema = UpdateScenarioSchema.extend({
  id: z.string().min(1, '场景ID不能为空'),
})

/**
 * 批量更新场景 DTO
 */
export const BatchUpdateScenarioSchema = z.object({
  items: z.array(BatchUpdateScenarioItemSchema).min(1, '至少需要一个场景'),
})

/**
 * 批量删除场景 DTO
 */
export const BatchDeleteScenarioSchema = z.object({
  ids: z.array(z.string()).min(1, '至少需要一个场景ID'),
})

// ═══════════════════════════════════════════════════════════════════════════
// 类型导出
// ═══════════════════════════════════════════════════════════════════════════

export type Scenario = z.infer<typeof ScenarioSchema>
export type ScenarioList = z.infer<typeof ScenarioListSchema>
export type ScenarioGenerationOptions = z.infer<typeof ScenarioGenerationOptionsSchema>
export type OutScenarioDto = z.infer<typeof OutScenarioSchema>
export type CreateScenarioDto = z.input<typeof CreateScenarioSchema>
export type UpdateScenarioDto = z.input<typeof UpdateScenarioSchema>
export type ListScenarioDto = z.infer<typeof ListScenarioSchema>
export type PageScenarioDto = z.infer<typeof PageScenarioSchema> & PageParamDto
export type BatchCreateScenarioDto = z.infer<typeof BatchCreateScenarioSchema>
export type BatchUpdateScenarioItemDto = z.infer<typeof BatchUpdateScenarioItemSchema>
export type BatchUpdateScenarioDto = z.infer<typeof BatchUpdateScenarioSchema>
export type BatchDeleteScenarioDto = z.infer<typeof BatchDeleteScenarioSchema>
