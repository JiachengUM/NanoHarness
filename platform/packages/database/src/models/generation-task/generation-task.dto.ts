import { z } from 'zod'
import { CreateSchema, UpdateSchema, PageSchema, PageParamDto, OutSchema } from '../../base/dto'

export const GenerationTaskSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
})

export const CreateGenerationTaskSchema = GenerationTaskSchema.extend(CreateSchema.shape)

export const UpdateGenerationTaskSchema = GenerationTaskSchema.partial().extend(UpdateSchema.shape)

export const OutGenerationTaskSchema = GenerationTaskSchema.extend(OutSchema.shape)

export const ListGenerationTaskSchema = z.object({
  name: z.string().optional(),
})

export const PageGenerationTaskSchema = ListGenerationTaskSchema.extend(PageSchema.shape)

export type OutGenerationTaskDto = z.infer<typeof OutGenerationTaskSchema>
export type CreateGenerationTaskDto = z.input<typeof CreateGenerationTaskSchema>
export type UpdateGenerationTaskDto = z.input<typeof UpdateGenerationTaskSchema>
export type ListGenerationTaskDto = z.infer<typeof ListGenerationTaskSchema>
export type PageGenerationTaskDto = ListGenerationTaskDto & PageParamDto
