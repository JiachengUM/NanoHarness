import type { FastifyPluginAsyncZod } from 'fastify-type-provider-zod'
import {
  datasetRepository,
  CreateDatasetSchema,
  UpdateDatasetSchema,
  PageDatasetSchema,
  ListDatasetSchema,
} from '@eval-platform/database'
import { HTTP_STATUS } from '../../constants/http-status'
import { IdParamsSchema } from '../../schema/params'

export const prefix = '/complex_reasoning_dataset'

const datasetRoutes: FastifyPluginAsyncZod = async (app) => {
  // 直接注册路由，不再嵌套
  app.get('/list', { schema: { querystring: ListDatasetSchema } }, async (req, reply) => {
    const result = await datasetRepository.listDatasets(req.query)
    return reply.success(result)
  })

  app.get('/page', { schema: { querystring: PageDatasetSchema } }, async (req, reply) => {
    const result = await datasetRepository.pageDatasets(req.query)
    return reply.success(result)
  })

  app.get('/:id', { schema: { params: IdParamsSchema } }, async (req, reply) => {
    const { id } = req.params
    const result = await datasetRepository.findById(id)
    if (!result) {
      return reply.fail(`Dataset ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(result)
  })

  app.post('/', { schema: { body: CreateDatasetSchema } }, async (req, reply) => {
    const result = await datasetRepository.createDataset(req.body)
    return reply.success(result, { statusCode: HTTP_STATUS.CREATED })
  })

  app.put('/:id', { schema: { params: IdParamsSchema, body: UpdateDatasetSchema } }, async (req, reply) => {
    const { id } = req.params
    const result = await datasetRepository.updateDataset(id, req.body)
    if (!result) {
      return reply.fail(`Dataset ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(result)
  })

  app.delete('/:id', { schema: { params: IdParamsSchema } }, async (req, reply) => {
    const { id } = req.params
    const ok = await datasetRepository.deleteDataset(id)
    if (!ok) {
      return reply.fail(`Dataset ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(true)
  })
}

export default datasetRoutes
