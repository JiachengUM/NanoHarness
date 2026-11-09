import { z } from 'zod'
import { CreateSchema, UpdateSchema, PageSchema, PageParamDto, OutSchema } from '../../base/dto'

export const GenerationTaskRunStatusSchema = z.enum(['pending', 'running', 'completed', 'failed'])

export const GenerationTaskRunSchema = z.object({
  generation_task_id: z.string().min(1, 'Generate task id is required'),
  query: z.string().min(1, 'Query is required'),
  tag_tree_id: z.string().min(1, 'Tag tree id is required'),
  status: GenerationTaskRunStatusSchema.default('pending'),
  progress: z.number().optional(),
  events: z.array(z.record(z.string(), z.unknown())).default([]),
})

export const CreateGenerationTaskRunSchema = GenerationTaskRunSchema.extend(CreateSchema.shape)

export const UpdateGenerationTaskRunSchema = GenerationTaskRunSchema.partial().extend(UpdateSchema.shape)

export const OutGenerationTaskRunSchema = GenerationTaskRunSchema.extend(OutSchema.shape)

export const ListGenerationTaskRunSchema = z.object({
  generation_task_id: z.string().optional(),
  status: z.string().optional(),
})

export const PageGenerationTaskRunSchema = ListGenerationTaskRunSchema.extend(PageSchema.shape)

export const GenerationTaskRunStatusEnum = GenerationTaskRunStatusSchema.enum
export type OutGenerationTaskRunDto = z.infer<typeof OutGenerationTaskRunSchema>
export type CreateGenerationTaskRunDto = z.input<typeof CreateGenerationTaskRunSchema>
export type UpdateGenerationTaskRunDto = z.input<typeof UpdateGenerationTaskRunSchema>
export type ListGenerationTaskRunDto = z.infer<typeof ListGenerationTaskRunSchema>
export type PageGenerationTaskRunDto = ListGenerationTaskRunDto & PageParamDto
