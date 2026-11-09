import type { FastifyPluginAsyncZod } from 'fastify-type-provider-zod'
import {
  datasetItemRepository,
  CreateDatasetItemSchema,
  UpdateDatasetItemSchema,
  PageDatasetItemSchema,
  ListDatasetItemSchema,
} from '@eval-platform/database'
import { HTTP_STATUS } from '../../constants/http-status'
import { IdParamsSchema } from '../../schema/params'

export const prefix = '/complex_reasoning_case'

export const datasetItemsRoutes: FastifyPluginAsyncZod = async (app) => {
  app.get(
    '/list',
    {
      schema: {
        querystring: ListDatasetItemSchema,
      },
    },
    async (req, reply) => {
      const result = await datasetItemRepository.listDatasetItems(req.query)
      return reply.success(result)
    },
  )

  app.get(
    '/page',
    {
      schema: {
        querystring: PageDatasetItemSchema,
      },
    },
    async (req, reply) => {
      const result = await datasetItemRepository.pageDatasetItems(req.query)
      return reply.success(result)
    },
  )

  app.get(
    '/:id',
    {
      schema: {
        params: IdParamsSchema,
      },
    },
    async (req, reply) => {
      const { id } = req.params
      const result = await datasetItemRepository.findById(id)
      if (!result) {
        return reply.fail(`Dataset item ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
      }
      return reply.success(result)
    },
  )

  app.post(
    '/',
    {
      schema: {
        body: CreateDatasetItemSchema,
      },
    },
    async (req, reply) => {
      const result = await datasetItemRepository.createDatasetItem(req.body)
      return reply.success(result, { statusCode: HTTP_STATUS.CREATED })
    },
  )

  app.put(
    '/:id',
    {
      schema: {
        params: IdParamsSchema,
        body: UpdateDatasetItemSchema,
      },
    },
    async (req, reply) => {
      const { id } = req.params
      const result = await datasetItemRepository.updateDatasetItem(id, req.body)
      if (!result) {
        return reply.fail(`Dataset item ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
      }
      return reply.success(result)
    },
  )

  app.delete(
    '/:id',
    {
      schema: {
        params: IdParamsSchema,
      },
    },
    async (req, reply) => {
      const { id } = req.params
      const ok = await datasetItemRepository.deleteDatasetItem(id)
      if (!ok) {
        return reply.fail(`Dataset item ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
      }
      return reply.success(true)
    },
  )
}

export default datasetItemsRoutes
