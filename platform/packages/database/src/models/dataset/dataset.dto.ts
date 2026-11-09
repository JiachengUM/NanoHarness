import { z } from 'zod'
import { CreateSchema, UpdateSchema, PageSchema, PageParamDto, OutSchema } from '../../base/dto'

export const DatasetSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  item_count: z.number().default(0),
})

// ── 创建 ────────────────────────────────────────────────────────────────

export const CreateDatasetSchema = DatasetSchema.extend(CreateSchema.shape)

// ── 更新 (所有字段可选) ───────────────────────────────────────────────────

export const UpdateDatasetSchema = DatasetSchema.partial().extend(UpdateSchema.shape)

// ── 输出 ────────────────────────────────────────────────────────────────

export const OutDatasetSchema = DatasetSchema.extend(OutSchema.shape)

// ── 列表 / 分页 查询参数 ───────────────────────────────────────────────────

export const ListDatasetSchema = z.object({
  name: z.string().optional(),
})

export const PageDatasetSchema = ListDatasetSchema.extend(PageSchema.shape)

// ── 推断类型 ──────────────────────────────────────────────────────────────

export type OutDatasetDto = z.infer<typeof OutDatasetSchema>
export type CreateDatasetDto = z.input<typeof CreateDatasetSchema>
export type UpdateDatasetDto = z.input<typeof UpdateDatasetSchema>
export type ListDatasetDto = z.infer<typeof ListDatasetSchema>
export type PageDatasetDto = ListDatasetDto & PageParamDto
