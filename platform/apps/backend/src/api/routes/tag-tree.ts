import type { FastifyPluginAsyncZod } from 'fastify-type-provider-zod'
import { z } from 'zod'
import { tagTreeRepository, CreateTagTreeSchema, UpdateTagTreeSchema, TagTreeDoc } from '@eval-platform/database'
import { HTTP_STATUS } from '../../constants/http-status'
import { IdParamsSchema } from '../../schema/params'
import { previewTagTree, TagTree } from '@eval-platform/makedata'

export const prefix = '/tag-tree'

export const ListTagTreeSchema = z.object({
  name: z.string().optional(),
})

export const PageTagTreeSchema = ListTagTreeSchema.extend({
  page: z.coerce.number().int().positive().default(1),
  page_size: z.coerce.number().int().positive().max(100).default(10),
})

export type TagTreeBrief = Omit<TagTreeDoc, 'tree'>

const tagTreeRoutes: FastifyPluginAsyncZod = async (app) => {
  app.get('/list', { schema: { querystring: ListTagTreeSchema } }, async (req, reply) => {
    const result = await tagTreeRepository.listTagTrees(req.query)
    return reply.success(result)
  })

  app.get('/page', { schema: { querystring: PageTagTreeSchema } }, async (req, reply) => {
    const result = await tagTreeRepository.pageTagTrees(req.query)
    return reply.success(result)
  })

  app.get('/export/:id', { schema: { params: IdParamsSchema } }, async (req, reply) => {
    const { id } = req.params
    const tagTreeDoc = await tagTreeRepository.findById(id)
    if (!tagTreeDoc) {
      return reply.fail(`TagTree ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    const tagTree = TagTree.fromJSON(tagTreeDoc.tree)
    const json = tagTree.toJSON()
    const filename = `${tagTreeDoc.name}.json`

    const encodedFilename = encodeURIComponent(filename)
    reply.header('Content-Type', 'application/json')
    reply.header('Content-Disposition', `attachment; filename="${encodedFilename}"`)
    reply.header('Content-Length', Buffer.byteLength(json, 'utf-8'))

    return reply.send(json)
  })

  app.get('/:id', { schema: { params: IdParamsSchema } }, async (req, reply) => {
    const { id } = req.params
    const result = await tagTreeRepository.findById(id)
    if (!result) {
      return reply.fail(`TagTree ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(result)
  })

  app.post('/', { schema: { body: CreateTagTreeSchema } }, async (req, reply) => {
    try {
      const { name } = req.body
      const existing = await tagTreeRepository.findByName(name)
      if (existing) {
        return reply.fail(`标签树 "${name}" 已存在`, { statusCode: HTTP_STATUS.CONFLICT })
      }
      const result = await tagTreeRepository.createTagTree(req.body)
      return reply.success(result, { statusCode: HTTP_STATUS.CREATED })
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '未知错误'
      return reply.fail(errorMessage, { statusCode: HTTP_STATUS.INTERNAL_SERVER_ERROR })
    }
  })

  app.put('/:id', { schema: { params: IdParamsSchema, body: UpdateTagTreeSchema } }, async (req, reply) => {
    const { id } = req.params

    if (req.body.name) {
      const existing = await tagTreeRepository.findByName(req.body.name)
      if (existing && existing.id !== id) {
        return reply.fail(`标签树名称 "${req.body.name}" 已被使用`, { statusCode: HTTP_STATUS.CONFLICT })
      }
    }

    const result = await tagTreeRepository.updateTagTree(id, req.body)
    if (!result) {
      return reply.fail(`TagTree ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(result)
  })

  app.delete('/:id', { schema: { params: IdParamsSchema } }, async (req, reply) => {
    const { id } = req.params
    const ok = await tagTreeRepository.deleteTagTree(id)
    if (!ok) {
      return reply.fail(`TagTree ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(true)
  })

  app.get('/list-brief', async (req, reply) => {
    const trees = await tagTreeRepository.listTagTrees()

    const briefList: TagTreeBrief[] = trees.map((item) => {
      const { tree, ...rest } = item
      return rest as TagTreeBrief
    })

    return reply.success(briefList)
  })

  app.get(
    '/:name/preview',
    {
      schema: {
        params: z.object({
          name: z.string().min(1, '标签树名称不能为空'),
        }),
      },
    },
    async (req, reply) => {
      const { name } = req.params

      const tagTreeDoc = await tagTreeRepository.findByName(name)
      if (!tagTreeDoc) {
        return reply.fail(`标签树 "${name}" 不存在`, { statusCode: HTTP_STATUS.NOT_FOUND })
      }

      const tagTree = TagTree.fromJSON(tagTreeDoc.tree)
      const preview = previewTagTree(tagTree, {
        showTree: true,
        showLeafList: true,
        title: `标签树: ${name}`,
      })

      return reply.success(preview)
    },
  )
}

export default tagTreeRoutes
