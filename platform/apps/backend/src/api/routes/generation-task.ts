import type { FastifyPluginAsyncZod } from 'fastify-type-provider-zod'
import {
  generationTaskRepository,
  CreateGenerationTaskSchema,
  UpdateGenerationTaskSchema,
  PageGenerationTaskSchema,
  ListGenerationTaskSchema,
} from '@eval-platform/database'
import { HTTP_STATUS } from '../../constants/http-status'
import { IdParamsSchema } from '../../schema/params'

export const prefix = '/generation-task'

const generationTaskRoutes: FastifyPluginAsyncZod = async (app) => {
  app.get('/list', { schema: { querystring: ListGenerationTaskSchema } }, async (req, reply) => {
    const result = await generationTaskRepository.listGenerationTasks(req.query)
    return reply.success(result)
  })

  app.get('/page', { schema: { querystring: PageGenerationTaskSchema } }, async (req, reply) => {
    const result = await generationTaskRepository.pageGenerationTasks(req.query)
    return reply.success(result)
  })

  app.get('/:id', { schema: { params: IdParamsSchema } }, async (req, reply) => {
    const { id } = req.params
    const result = await generationTaskRepository.findById(id)
    if (!result) {
      return reply.fail(`GenerationTask ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(result)
  })

  app.post('/', { schema: { body: CreateGenerationTaskSchema } }, async (req, reply) => {
    const result = await generationTaskRepository.createGenerationTask(req.body)
    return reply.success(result, { statusCode: HTTP_STATUS.CREATED })
  })

  app.put('/:id', { schema: { params: IdParamsSchema, body: UpdateGenerationTaskSchema } }, async (req, reply) => {
    const { id } = req.params
    const result = await generationTaskRepository.updateGenerationTask(id, req.body)
    if (!result) {
      return reply.fail(`GenerationTask ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(result)
  })

  app.delete('/:id', { schema: { params: IdParamsSchema } }, async (req, reply) => {
    const { id } = req.params
    const ok = await generationTaskRepository.deleteGenerationTask(id)
    if (!ok) {
      return reply.fail(`GenerationTask ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(true)
  })
}

export default generationTaskRoutes