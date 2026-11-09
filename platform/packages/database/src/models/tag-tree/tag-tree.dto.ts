import { z } from 'zod'
import { CreateSchema, PageSchema, UpdateSchema, OutSchema } from '../../base/dto'

// ═══════════════════════════════════════════════════════════════════════════
// 标签树 Schema (Tag Tree)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 标签树节点 Schema - 递归定义
 */
export const TagTreeNodeSchema: z.ZodType<any> = z.lazy(() =>
  z.object({
    name: z.string().min(1, '标签名不能为空'),
    description: z.string().default(''),
    children: z.array(TagTreeNodeSchema).default([]),
  }),
)

/**
 * 标签树 Schema
 */
export const TagTreeSchema = z.object({
  root: TagTreeNodeSchema,
  tagging_guideline: z.string().default('请基于case目标与通过标准，从叶子标签中选择最有证据支持的标签。'),
})

const TagTreeDocSchema = z.object({
  name: z.string().min(1, '标签树名称不能为空'),
  description: z.string().optional(),
  tree: TagTreeSchema,
})

/**
 * 创建标签树 DTO
 */
export const CreateTagTreeSchema = TagTreeDocSchema.extend(CreateSchema.shape)

/**
 * 更新标签树 DTO（只能更新元数据，不能修改树结构）
 */
export const UpdateTagTreeSchema = CreateTagTreeSchema.partial()

/**
 * 输出标签树 DTO
 */
export const OutTagTreeSchema = TagTreeDocSchema.extend(OutSchema.shape)

export const ListTagTreeSchema = z.object({
  name: z.string().optional(),
})

export const PageTagTreeSchema = ListTagTreeSchema.extend(PageSchema.shape)

// ═══════════════════════════════════════════════════════════════════════════
// 类型导出
// ═══════════════════════════════════════════════════════════════════════════

export type TagTreeNode = z.infer<typeof TagTreeNodeSchema>
export type TagTree = z.infer<typeof TagTreeSchema>
export type OutTagTreeDto = z.infer<typeof OutTagTreeSchema>
export type CreateTagTreeDto = z.input<typeof CreateTagTreeSchema>
export type UpdateTagTreeDto = z.input<typeof UpdateTagTreeSchema>
export type ListTagTreeDto = z.infer<typeof ListTagTreeSchema>
export type PageTagTreeDto = z.infer<typeof PageTagTreeSchema>
