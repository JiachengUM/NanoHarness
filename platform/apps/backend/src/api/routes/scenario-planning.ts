import type { FastifyPluginAsyncZod } from 'fastify-type-provider-zod'
import {
  scenarioPlanRepository,
  tagTreeRepository,
  CreateScenarioPlanRequestSchema,
  ListScenarioPlanSchema,
  PageScenarioPlanSchema,
  CreateScenarioPlanSchema,
  UpdateScenarioPlanSchema,
  generationTaskRepository,
  generationTaskRunRepository,
  CreateGenerationTaskRunDto,
  GenerationTaskRunStatusEnum,
} from '@eval-platform/database'
import { generateScenarioPlan, TagTree } from '@eval-platform/makedata'
import { createClient } from '@eval-platform/llm'
import { HTTP_STATUS } from '../../constants/http-status'
import { IdParamsSchema } from '../../schema/params'

export const prefix = '/scenario-planning'

const scenarioPlanningRoutes: FastifyPluginAsyncZod = async (app) => {
  app.get('/list', { schema: { querystring: ListScenarioPlanSchema } }, async (req, reply) => {
    const result = await scenarioPlanRepository.listPlans(req.query)
    return reply.success(result)
  })

  app.get('/page', { schema: { querystring: PageScenarioPlanSchema } }, async (req, reply) => {
    const result = await scenarioPlanRepository.pagePlans(req.query)
    return reply.success(result)
  })

  app.get('/:id', { schema: { params: IdParamsSchema } }, async (req, reply) => {
    const { id } = req.params
    const result = await scenarioPlanRepository.findScenarioPlanById(id)
    if (!result) {
      return reply.fail(`ScenarioPlan ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(result)
  })

  app.post('/', { schema: { body: CreateScenarioPlanSchema } }, async (req, reply) => {
    const result = await scenarioPlanRepository.createPlan(req.body)
    return reply.success(result, { statusCode: HTTP_STATUS.CREATED })
  })

  app.put('/:id', { schema: { params: IdParamsSchema, body: UpdateScenarioPlanSchema } }, async (req, reply) => {
    const { id } = req.params
    const result = await scenarioPlanRepository.updatePlan(id, req.body)
    if (!result) {
      return reply.fail(`Plan ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(result)
  })

  app.delete('/:id', { schema: { params: IdParamsSchema } }, async (req, reply) => {
    const { id } = req.params
    const ok = await scenarioPlanRepository.deletePlan(id)
    if (!ok) {
      return reply.fail(`Plan ${id} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }
    return reply.success(true)
  })

  /**
   * POST /api/scenario-planning/generate
   * 使用 LLM 生成场景生成计划
   */
  app.post(
    '/generate',
    {
      schema: {
        body: CreateScenarioPlanRequestSchema,
      },
    },
    async (req, reply) => {
      const { query, tag_tree_name, task_id } = req.body

      const tagTreeDoc = await tagTreeRepository.findByName(tag_tree_name)
      if (!tagTreeDoc) {
        return reply.fail('标签树不存在', { statusCode: HTTP_STATUS.NOT_FOUND })
      }

      const generationTask = await generationTaskRepository.findById(task_id)
      if (!generationTask) {
        return reply.fail('生成任务不存在', { statusCode: HTTP_STATUS.NOT_FOUND })
      }

      // 创建生成任务运行记录
      const data: CreateGenerationTaskRunDto = {
        query,
        tag_tree_id: tagTreeDoc.id,
        generation_task_id: task_id,
        status: GenerationTaskRunStatusEnum.running,
      }
      const generationTaskRun = await generationTaskRunRepository.createGenerationTaskRun(data)

      const tagTree = TagTree.fromJSON(tagTreeDoc.tree)
      const client = createClient()

      try {
        const generatedPlan = await generateScenarioPlan(query, tagTree, client)

        const scenarioPlan = {
          ...generatedPlan,
          task_id: generationTask.id,
          generation_task_run_id: generationTaskRun.id,
          tag_tree_name,
        }

        const result = await scenarioPlanRepository.createPlan(scenarioPlan)

        return reply.success(result)
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : '未知错误'
        console.error('[Generate Scenario Plan Error]', error)
        return reply.fail(`生成 Plan 失败: ${errorMessage}`, {
          statusCode: HTTP_STATUS.INTERNAL_SERVER_ERROR,
        })
      }
    },
  )
}

export default scenarioPlanningRoutes
