import type { FastifyPluginAsyncZod } from 'fastify-type-provider-zod'
import {
  generationTaskRunRepository,
  CreateGenerationTaskRunSchema,
  UpdateGenerationTaskRunSchema,
  PageGenerationTaskRunSchema,
  ListGenerationTaskRunSchema,
} from '@eval-platform/database'
import { HTTP_STATUS } from '../../constants/http-status'
import { IdParamsSchema } from '../../schema/params'

export const prefix = '/generation-task-run'

const generationTaskRunRoutes: FastifyPluginAsyncZod = async (app) => {
  app.get('/list', { schema: { querystring: ListGenerationTaskRunSchema } }, async (req, reply) => {
    const result = await generationTaskRunRepository.listGenerationTaskRuns(req.query)
    return reply.success(result)
  })

  app.get('/page', { schema: { querystring: PageGenerationTaskRunSchema } }, async (req, reply) => {
    const result = await generationTaskRunRepository.pageGenerationTaskRuns(req.query)
    return reply.success(result)
  })

  app.get('/:id', { schema: { params: IdParamsSchema } }, async (req, reply) => {
    const { id } = req.params
    const result = await generationTaskRunRepository.findById(id)
    if (!result) {
      return reply.fail(`GenerationTaskRun ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(result)
  })

  app.post('/', { schema: { body: CreateGenerationTaskRunSchema } }, async (req, reply) => {
    const result = await generationTaskRunRepository.createGenerationTaskRun(req.body)
    return reply.success(result, { statusCode: HTTP_STATUS.CREATED })
  })

  app.put('/:id', { schema: { params: IdParamsSchema, body: UpdateGenerationTaskRunSchema } }, async (req, reply) => {
    const { id } = req.params
    const result = await generationTaskRunRepository.updateGenerationTaskRun(id, req.body)
    if (!result) {
      return reply.fail(`GenerationTaskRun ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(result)
  })

  app.delete('/:id', { schema: { params: IdParamsSchema } }, async (req, reply) => {
    const { id } = req.params
    const ok = await generationTaskRunRepository.deleteGenerationTaskRun(id)
    if (!ok) {
      return reply.fail(`GenerationTaskRun ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(true)
  })
}

export default generationTaskRunRoutes