import type { FastifyPluginAsyncZod } from 'fastify-type-provider-zod'
import { z } from 'zod'
import {
  scenarioRepository,
  datasetItemRepository,
  tagTreeRepository,
  CreateScenarioSchema,
  UpdateScenarioSchema,
  ListScenarioSchema,
  PageScenarioSchema,
  BatchCreateScenarioSchema,
  BatchUpdateScenarioSchema,
  BatchDeleteScenarioSchema,
  generationTaskRepository,
} from '@eval-platform/database'
import { HTTP_STATUS } from '../../constants/http-status'

export const prefix = '/scenario-management'

// ═══════════════════════════════════════════════════════════════════════════
// Schema 定义
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 路径参数：标签树名称
 */
export const TagTreeNameParamsSchema = z.object({
  tagTreeName: z.string().min(1, '标签树名称不能为空'),
})

/**
 * 路径参数：场景ID
 */
export const ScenarioIdParamsSchema = z.object({
  scenarioId: z.string().min(1, '场景ID不能为空'),
})

/**
 * 路径参数：生成任务 ID
 */
export const GenerationTaskIdParamsSchema = z.object({
  generationTaskId: z.string().min(1, '生成任务ID不能为空'),
})

/**
 * 场景简要信息
 */
export const ScenarioBriefSchema = z.object({
  scenario_id: z.string(),
  scenario_name: z.string(),
  description: z.string(),
  tags: z.array(z.string()),
  pattern: z.string().optional(),
  generation_task_id: z.string().optional(),
  createdAt: z.date().optional(),
  updatedAt: z.date().optional(),
})

/**
 * 用例简要信息
 */
export const CaseBriefSchema = z.object({
  case_id: z.string(),
  dataset_id: z.string(),
  case_description: z.string().optional(),
  tags: z.array(z.string()).optional(),
  max_round: z.number(),
  createdAt: z.date().optional(),
  updatedAt: z.date().optional(),
})

// ═══════════════════════════════════════════════════════════════════════════
// 类型导出
// ═══════════════════════════════════════════════════════════════════════════

export type ScenarioBrief = z.infer<typeof ScenarioBriefSchema>
export type CaseBrief = z.infer<typeof CaseBriefSchema>

// ═══════════════════════════════════════════════════════════════════════════
// 路由实现
// ═══════════════════════════════════════════════════════════════════════════

const scenarioManagementRoutes: FastifyPluginAsyncZod = async (app) => {
  /**
   * GET /api/scenario-management/by-tag-tree/:tagTreeName
   * 获取属于某标签树的所有场景
   */
  app.get<{ Params: { tagTreeName: string } }>('/by-tag-tree/:tagTreeName', async (req, reply) => {
    const { tagTreeName } = req.params

    // 验证标签树存在
    const tagTree = await tagTreeRepository.findByName(tagTreeName)
    if (!tagTree) {
      return reply.fail(`标签树 "${tagTreeName}" 不存在`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }

    // 查询属于该标签树的场景
    const scenarios = await scenarioRepository.listScenarios({ tag_tree_id: tagTree.id })

    const briefList: ScenarioBrief[] = scenarios.map((s) => ({
      scenario_id: s.scenario_id,
      scenario_name: s.scenario_name,
      description: s.description,
      tags: s.tags,
      pattern: s.pattern,
      generation_task_id: s.generation_task_id?.toString(),
      createdAt: (s as any).created_time,
      updatedAt: (s as any).updated_time,
    }))

    return reply.success(briefList)
  })

  /**
   * GET /api/scenario-management/by-generation-task/:generationTaskId
   * 获取属于某生成任务的所有场景
   */
  app.get<{ Params: { generationTaskId: string } }>(
    '/by-generation-task/:generationTaskId',
    {
      schema: {
        params: GenerationTaskIdParamsSchema,
      },
    },
    async (req, reply) => {
      const { generationTaskId } = req.params

      const task = await generationTaskRepository.findById(generationTaskId)
      if (!task) {
        return reply.fail(`GenerationTask ${generationTaskId} not found`, { statusCode: HTTP_STATUS.NOT_FOUND })
      }

      const scenarios = await scenarioRepository.listScenarios({ generation_task_id: generationTaskId })

      const briefList: ScenarioBrief[] = scenarios.map((s) => ({
        scenario_id: s.scenario_id,
        scenario_name: s.scenario_name,
        description: s.description,
        tags: s.tags,
        generation_task_id: s.generation_task_id?.toString(),
        createdAt: (s as any).created_time,
        updatedAt: (s as any).updated_time,
      }))

      return reply.success(briefList)
    },
  )

  /**
   * GET /api/scenario-management/:scenarioId/cases
   * 获取属于某场景的所有用例
   */
  app.get<{ Params: { scenarioId: string } }>('/:scenarioId/cases', async (req, reply) => {
    const { scenarioId } = req.params

    // 验证场景存在
    const scenario = await scenarioRepository.findByScenarioId(scenarioId)
    if (!scenario) {
      return reply.fail(`场景 "${scenarioId}" 不存在`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }

    // 查询属于该场景的用例
    const cases = await datasetItemRepository.listDatasetItems({
      source_scenario_id: scenarioId,
    })

    const briefList: CaseBrief[] = cases.map((c) => ({
      case_id: c.case_id,
      dataset_id: c.dataset_id,
      case_description: c.case_description,
      tags: c.tags,
      max_round: c.max_round,
      createdAt: (c as any).created_time,
      updatedAt: (c as any).updated_time,
    }))

    return reply.success(briefList)
  })

  /**
   * GET /api/scenario-management/list
   * 获取所有场景列表
   */
  app.get('/list', { schema: { querystring: ListScenarioSchema } }, async (req, reply) => {
    const result = await scenarioRepository.listScenarios(req.query)
    return reply.success(result)
  })

  /**
   * GET /api/scenario-management/page
   * 获取所有场景分页列表
   */
  app.get('/page', { schema: { querystring: PageScenarioSchema } }, async (req, reply) => {
    const result = await scenarioRepository.pageScenarios(req.query)
    return reply.success(result)
  })

  /**
   * POST /api/scenario-management
   * 新增场景
   */
  app.post<{ Body: z.infer<typeof CreateScenarioSchema> }>('/', async (req, reply) => {
    try {
      const scenario = await scenarioRepository.createScenario(req.body)
      return reply.success(scenario, { statusCode: HTTP_STATUS.CREATED })
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '未知错误'
      // 可能是唯一键冲突
      if (errorMessage.includes('duplicate') || errorMessage.includes('E11000')) {
        return reply.fail(`场景ID已存在`, { statusCode: HTTP_STATUS.CONFLICT })
      }
      return reply.fail(errorMessage, { statusCode: HTTP_STATUS.INTERNAL_SERVER_ERROR })
    }
  })

  /**
   * PUT /api/scenario-management/:id
   * 更新场景
   */
  app.put<{ Params: { id: string }; Body: z.infer<typeof UpdateScenarioSchema> }>('/:id', async (req, reply) => {
    const { id } = req.params

    const updated = await scenarioRepository.updateScenario(id, req.body)
    if (!updated) {
      return reply.fail(`场景不存在`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }

    return reply.success(updated)
  })

  /**
   * DELETE /api/scenario-management/:id
   * 删除场景
   */
  app.delete<{ Params: { id: string } }>('/:id', async (req, reply) => {
    const { id } = req.params

    const ok = await scenarioRepository.deleteScenario(id)
    if (!ok) {
      return reply.fail(`场景不存在`, { statusCode: HTTP_STATUS.NOT_FOUND })
    }

    return reply.success(true)
  })

  /**
   * POST /api/scenario-management/batch
   * 批量新增场景
   */
  app.post<{ Body: z.infer<typeof BatchCreateScenarioSchema> }>(
    '/batch',
    { schema: { body: BatchCreateScenarioSchema } },
    async (req, reply) => {
      try {
        const scenarios = await scenarioRepository.batchCreateScenarios(req.body)
        return reply.success(scenarios, { statusCode: HTTP_STATUS.CREATED })
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : '未知错误'
        if (errorMessage.includes('duplicate') || errorMessage.includes('E11000')) {
          return reply.fail(`场景ID已存在`, { statusCode: HTTP_STATUS.CONFLICT })
        }
        return reply.fail(errorMessage, { statusCode: HTTP_STATUS.INTERNAL_SERVER_ERROR })
      }
    },
  )

  /**
   * PUT /api/scenario-management/batch
   * 批量更新场景
   */
  app.put<{ Body: z.infer<typeof BatchUpdateScenarioSchema> }>(
    '/batch',
    { schema: { body: BatchUpdateScenarioSchema } },
    async (req, reply) => {
      const modifiedCount = await scenarioRepository.batchUpdateScenarios(req.body)
      return reply.success({ modified_count: modifiedCount })
    },
  )

  /**
   * DELETE /api/scenario-management/batch
   * 批量删除场景
   */
  app.delete<{ Body: z.infer<typeof BatchDeleteScenarioSchema> }>(
    '/batch',
    { schema: { body: BatchDeleteScenarioSchema } },
    async (req, reply) => {
      const deletedCount = await scenarioRepository.batchDeleteScenarios(req.body)
      return reply.success({ deleted_count: deletedCount })
    },
  )
}

export default scenarioManagementRoutes
