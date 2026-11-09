import { z } from 'zod'

export const PageSchema = z.object({
  page: z.coerce.number().int().positive().default(1),
  page_size: z.coerce.number().int().positive().max(100).default(10),
})

export const CreateSchema = z.object({
  creator: z.string().default('system'),
})

export const UpdateSchema = CreateSchema

export const OutSchema = z.object({
  id: z.string(),
  creator: z.string(),
  created_time: z.date(),
  updated_time: z.date(),
})

export type PageDto = z.infer<typeof PageSchema>

export type PageParamDto = Partial<PageDto>

export type OutDto = z.infer<typeof OutSchema>
