import { CreateSchema, UpdateSchema, PageSchema, PageParamDto, OutSchema } from './../../base/dto'
import { z } from 'zod'

export const DEFAULT_MAX_ROUND = 1

// ═══════════════════════════════════════════════════════════════════════════
// 基础消息结构 Schema（DatasetItem 子结构）
// ═══════════════════════════════════════════════════════════════════════════

export const MessageSchema = z.object({
  role: z.enum(['user', 'assistant', 'system']),
  content: z.string(),
})

export const DialogueRoundConfigSchema = z.object({
  user_query_list: z.array(MessageSchema).min(1, 'user_query_list must have at least one message'),
  mock_info: z.record(z.string(), z.unknown()).default({}),
  mock_time: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/, 'mock_time must be YYYY-MM-DD HH:MM:SS')
    .nullable()
    .optional(),
})

export const UserQuerySessionSchema = z.union([
  z.array(MessageSchema).min(1, 'session must have at least one message'),
  DialogueRoundConfigSchema,
])

// ═══════════════════════════════════════════════════════════════════════════
// DatasetItem / 测试用例 Schema
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 基础用例 Schema
 */
export const DatasetItemSchema = z.object({
  dataset_id: z.string().min(1, 'dataset_id is required'),
  case_id: z.string().min(1, 'case_id is required'),
  context_config: z.record(z.string(), z.unknown()).default({}),
  max_round: z.coerce.number().int().positive().default(DEFAULT_MAX_ROUND),
  user_query_lists: z.array(UserQuerySessionSchema).min(1, 'user_query_lists must have at least one session'),
  expected_script: z.string().default(''),
  nl_assertion: z.array(z.string()).default([]),
  code_assertion: z.record(z.string(), z.unknown()).nullable().optional(),
  case_description: z.string().default(''),
  tags: z.array(z.string()).default([]),
})

/**
 * 带场景追溯的用例 Schema
 */
export const CaseWithScenarioSchema = DatasetItemSchema.extend({
  source_scenario_id: z.string().min(1, '来源场景ID不能为空'),
  source_scenario_name: z.string().min(1, '来源场景名称不能为空'),
})

/**
 * 用例生成配置 Schema
 */
export const CaseGenerationConfigSchema = z.object({
  casesPerScenario: z.number().int().positive(),
  temperature: z.number().min(0).max(2).default(0.7),
})

// ═══════════════════════════════════════════════════════════════════════════
// CRUD 操作 Schema
// ═══════════════════════════════════════════════════════════════════════════

export const CreateDatasetItemSchema = DatasetItemSchema.extend(CreateSchema.shape)

export const UpdateDatasetItemSchema = DatasetItemSchema.partial().extend(UpdateSchema.shape)

export const OutDatasetItemSchema = DatasetItemSchema.extend(OutSchema.shape)

export const ListDatasetItemSchema = z.object({
  dataset_id: z.string().optional(),
  keyword: z.string().optional(),
  source_scenario_id: z.string().optional(),
})

export const PageDatasetItemSchema = ListDatasetItemSchema.extend(PageSchema.shape)

// ═══════════════════════════════════════════════════════════════════════════
// 类型导出
// ═══════════════════════════════════════════════════════════════════════════

export type Message = z.infer<typeof MessageSchema>
export type DialogueRoundConfig = z.infer<typeof DialogueRoundConfigSchema>
export type UserQuerySession = z.infer<typeof UserQuerySessionSchema>

export type DatasetItemDto = z.infer<typeof DatasetItemSchema>
export type CaseWithScenario = z.infer<typeof CaseWithScenarioSchema>
export type CaseGenerationConfig = z.infer<typeof CaseGenerationConfigSchema>

export type OutDatasetItemDto = z.infer<typeof OutDatasetItemSchema>
export type CreateDatasetItemDto = z.input<typeof CreateDatasetItemSchema>
export type UpdateDatasetItemDto = z.input<typeof UpdateDatasetItemSchema>
export type ListDatasetItemDto = z.infer<typeof ListDatasetItemSchema>
export type PageDatasetItemDto = ListDatasetItemDto & PageParamDto
