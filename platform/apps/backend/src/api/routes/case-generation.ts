import type { FastifyPluginAsyncZod } from 'fastify-type-provider-zod'
import { z } from 'zod'
import {
  scenarioRepository,
  tagTreeRepository,
  datasetRepository,
  datasetItemRepository,
  generationTaskRunRepository,
  GenerationTaskRunStatusEnum,
} from '@eval-platform/database'
import { generateAndRefineCases, TagTree, auditCases, fixCasesByAudit } from '@eval-platform/makedata'
import { createClient } from '@eval-platform/llm'
import { HTTP_STATUS } from '../../constants/http-status'
import { sseTaskManager, handleSseStreamSubscription } from '../../services/generation/sse-helpers'

// URL 前缀: /api/case-generation
export const prefix = '/case-generation'

// ═══════════════════════════════════════════════════════════════════════════
// Schema 定义
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 启动用例生成任务请求 Schema
 */
export const StartCasesGenerationStreamSchema = z.object({
  // 关联的 Plan（用于反查 taskRunId）
  scenarioPlanId: z.string().optional(),

  // 显式指定 taskRunId（与 scenarioPlanId 二选一）
  generationTaskRunId: z.string().optional(),

  // 业务参数
  scenarioIds: z.array(z.string().min(1)).min(1, '至少需要一个场景ID'),
  datasetId: z.string().min(1, '数据集ID不能为空'),
  casesPerScenario: z.number().int().positive().optional().default(1),
  tagTreeName: z.string().min(1, '标签树名称不能为空'),

  // 可选的迭代控制参数（用于测试）
  maxIterations: z.number().int().positive().optional(),
  maxRefineRoundsPerBatch: z.number().int().nonnegative().optional(),
  auditConcurrency: z.number().int().positive().optional(),
  fixConcurrency: z.number().int().positive().optional(),
})

export const CancelCasesGenerationSchema = z.object({
  scenarioPlanId: z.string().optional(),
  generationTaskRunId: z.string().optional(),
})

// 流式输出的事件类型
const SSE_EVENT_TYPES = {
  CASE: 'case', // 新生成的用例
  PROGRESS: 'progress', // 进度更新
  COMPLETE: 'complete', // 生成完成
  ERROR: 'error', // 错误
} as const

// 取消标记集合（内存 Set，单实例有效）
const cancelledGenerationKeys = new Set<string>()

// ═══════════════════════════════════════════════════════════════════════════
// 类型导出
// ═══════════════════════════════════════════════════════════════════════════

export type StartCasesGenerationStreamRequest = z.infer<typeof StartCasesGenerationStreamSchema>

// ═══════════════════════════════════════════════════════════════════════════
// 后台任务执行函数（与 HTTP 连接解耦）
// ═══════════════════════════════════════════════════════════════════════════

interface RunCaseGenerationParams {
  scenarios: Array<{
    scenario_id: string
    scenario_name: string
    description: string
    tags: string[]
  }>
  casesPerScenario: number
  tagTree: TagTree
  datasetId: string
  generationTaskRunId: string
  scenarioPlanId?: string
  maxIterations?: number
  maxRefineRoundsPerBatch?: number
  auditConcurrency?: number
  fixConcurrency?: number
}

async function runCaseGenerationTask(params: RunCaseGenerationParams) {
  const {
    scenarios,
    casesPerScenario,
    tagTree,
    datasetId,
    generationTaskRunId,
    scenarioPlanId,
    maxIterations,
    maxRefineRoundsPerBatch,
    auditConcurrency,
    fixConcurrency,
  } = params

  const generationKeys = [scenarioPlanId ? `plan:${scenarioPlanId}` : '', `run:${generationTaskRunId}`].filter(Boolean)

  const isCancelled = () => generationKeys.some((key) => cancelledGenerationKeys.has(key))

  const client = createClient()
  const allCases: any[] = []

  try {
    // 使用流式生成，每当生成一个合格用例就推送
    await generateAndRefineCases(scenarios, casesPerScenario, tagTree, client, auditCases, fixCasesByAudit, datasetId, {
      maxIterations: maxIterations ?? 3,
      maxRefineRoundsPerBatch: maxRefineRoundsPerBatch ?? 1,
      auditConcurrency: auditConcurrency ?? 2,
      fixConcurrency: fixConcurrency ?? 2,

      // 进度回调
      onProgress: async (info) => {
        if (isCancelled()) return
        await sseTaskManager.emit(generationTaskRunId, {
          type: SSE_EVENT_TYPES.PROGRESS,
          data: {
            stage: info.stage,
            current: info.current,
            total: info.total,
            progressPercentage: info.progressPercentage,
            currentStep: info.currentStep,
            currentScenarioName: info.currentScenarioName,
          },
        })
      },

      // 流式用例回调：每生成一个合格用例就推送
      onCaseGenerated: async (caseItem, info) => {
        if (isCancelled()) return

        // 保存到数据库
        let savedCase: any = null
        let saveError: string | null = null

        try {
          const saveData: any = {
            dataset_id: datasetId,
            case_id: caseItem.case_id,
            context_config: caseItem.context_config || {},
            max_round: caseItem.max_round || 1,
            user_query_lists: caseItem.user_query_lists,
            expected_script: caseItem.expected_script,
            nl_assertion: caseItem.nl_assertion,
            code_assertion: caseItem.code_assertion,
            case_description: caseItem.case_description,
            tags: caseItem.tags || [],
          }
          // 添加场景追溯信息（如果存在）
          if (caseItem.source_scenario_id) {
            saveData.source_scenario_id = caseItem.source_scenario_id
            saveData.source_scenario_name = caseItem.source_scenario_name
          }
          savedCase = await datasetItemRepository.createDatasetItem(saveData)
          allCases.push(savedCase)
        } catch (error) {
          const errorMsg = error instanceof Error ? error.message : String(error)
          console.warn(`保存用例 ${caseItem.case_id} 失败:`, error)
          saveError = errorMsg
        }

        // 立即推送给客户端（无论保存成功与否）
        await sseTaskManager.emit(generationTaskRunId, {
          type: SSE_EVENT_TYPES.CASE,
          data: {
            caseItem: {
              case_id: caseItem.case_id,
              dataset_id: datasetId,
              source_scenario_id: caseItem.source_scenario_id,
              source_scenario_name: caseItem.source_scenario_name,
              max_round: caseItem.max_round,
              user_query_lists: caseItem.user_query_lists,
              expected_script: caseItem.expected_script,
              nl_assertion: caseItem.nl_assertion,
              tags: caseItem.tags,
              _saved: savedCase !== null,
              _saveError: saveError,
            },
            scenarioId: info.scenarioId,
            scenarioName: info.scenarioName,
            iteration: info.iteration,
            totalPassedCases: info.totalPassedCases,
          },
        })
      },
    })

    // 发送完成事件
    if (!isCancelled()) {
      await sseTaskManager.emit(generationTaskRunId, {
        type: SSE_EVENT_TYPES.COMPLETE,
        data: {
          totalGenerated: allCases.length,
          totalScenarios: scenarios.length,
          casesPerScenario,
        },
      })
    }

    // 标记任务终态
    if (isCancelled()) {
      sseTaskManager.markDone(generationTaskRunId, 'cancelled')
    } else {
      // 更新生成任务运行状态为完成
      await generationTaskRunRepository.updateById(generationTaskRunId, {
        status: GenerationTaskRunStatusEnum.completed,
      })
      sseTaskManager.markDone(generationTaskRunId, 'completed')
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '未知错误'
    const cancelled = errorMessage === 'GENERATION_CANCELLED' || isCancelled()
    if (cancelled) {
      sseTaskManager.markDone(generationTaskRunId, 'cancelled')
      return
    }
    console.error('[Generate Cases Stream Error]', error)

    await sseTaskManager.emit(generationTaskRunId, {
      type: SSE_EVENT_TYPES.ERROR,
      data: {
        message: `用例生成失败: ${errorMessage}`,
        code: 'GENERATION_ERROR',
      },
    })

    sseTaskManager.markDone(generationTaskRunId, 'failed')
  } finally {
    generationKeys.forEach((key) => cancelledGenerationKeys.delete(key))
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 路由实现
// ═══════════════════════════════════════════════════════════════════════════

const caseGenerationRoutes: FastifyPluginAsyncZod = async (app) => {
  // ─────────────────────────────────────────────────────────────────────
  // POST /cancel —— 取消任务
  // ─────────────────────────────────────────────────────────────────────
  app.post(
    '/cancel',
    {
      schema: {
        body: CancelCasesGenerationSchema,
      },
    },
    async (req, reply) => {
      const { scenarioPlanId, generationTaskRunId } = req.body
      if (!scenarioPlanId && !generationTaskRunId) {
        return reply.fail('请提供 scenarioPlanId 或 generationTaskRunId', {
          statusCode: HTTP_STATUS.BAD_REQUEST,
        })
      }
      if (scenarioPlanId) cancelledGenerationKeys.add(`plan:${scenarioPlanId}`)
      if (generationTaskRunId) cancelledGenerationKeys.add(`run:${generationTaskRunId}`)
      if (generationTaskRunId) sseTaskManager.requestCancel(generationTaskRunId)
      return reply.success(true)
    },
  )

  // ─────────────────────────────────────────────────────────────────────
  // POST /start —— 启动用例生成任务，立即返回 taskRunId
  //
  // 任务在后台 setImmediate 中执行，与连接解耦，连接断了任务继续跑。
  // 前端拿到 taskRunId 后，用 GET /:taskRunId/stream 订阅实时事件。
  // ─────────────────────────────────────────────────────────────────────
  app.post(
    '/start',
    {
      schema: {
        body: StartCasesGenerationStreamSchema,
      },
    },
    async (req, reply) => {
      const {
        scenarioPlanId,
        generationTaskRunId: explicitTaskRunId,
        scenarioIds,
        datasetId,
        casesPerScenario,
        tagTreeName,
        maxIterations,
        maxRefineRoundsPerBatch,
        auditConcurrency,
        fixConcurrency,
      } = req.body

      console.log('[StartCaseGeneration]', req.body)

      // 1. 验证数据集存在
      const dataset = await datasetRepository.findById(datasetId)
      if (!dataset) {
        return reply.fail('数据集不存在', { statusCode: HTTP_STATUS.NOT_FOUND })
      }

      // 2. 加载标签树（必填）
      // 2. 加载标签树（Schema 已保证必传）
      const tagTreeDoc = await tagTreeRepository.findByName(tagTreeName)
      if (!tagTreeDoc) {
        return reply.fail('标签树不存在', { statusCode: HTTP_STATUS.NOT_FOUND })
      }
      const tagTree = TagTree.fromJSON(tagTreeDoc.tree)

      // 3. 从数据库加载场景列表
      const scenarios: Array<{
        scenario_id: string
        scenario_name: string
        description: string
        tags: string[]
      }> = []
      const notFoundIds: string[] = []
      for (const scenarioId of scenarioIds) {
        const scenario = await scenarioRepository.findByScenarioId(scenarioId)
        if (scenario) {
          scenarios.push({
            scenario_id: scenario.scenario_id,
            scenario_name: scenario.scenario_name,
            description: scenario.description,
            tags: scenario.tags,
          })
        } else {
          notFoundIds.push(scenarioId)
        }
      }

      if (notFoundIds.length > 0) {
        return reply.fail(`场景不存在: ${notFoundIds.join(', ')}`, {
          statusCode: HTTP_STATUS.NOT_FOUND,
        })
      }

      if (scenarios.length === 0) {
        return reply.fail('没有可用场景', { statusCode: HTTP_STATUS.BAD_REQUEST })
      }

      // 4. 解析 taskRunId
      // 优先使用显式传入的 generationTaskRunId，否则要求 scenarioPlanId 关联
      let taskRunId: string | undefined = explicitTaskRunId

      if (!taskRunId && scenarioPlanId) {
        // 从 plan 反查 taskRunId（需要 scenarioPlanRepository）
        // 这里复用 generation-task-run 路由已有的反查能力
        const taskRun = await generationTaskRunRepository.findGenerationTaskRunByScenarioPlanId(scenarioPlanId)
        if (taskRun) {
          taskRunId = taskRun.id.toString()
        }
      }

      if (!taskRunId) {
        return reply.fail('未提供 generationTaskRunId，且无法从 scenarioPlanId 反查到任务运行记录', {
          statusCode: HTTP_STATUS.BAD_REQUEST,
        })
      }

      // 防重复启动：若任务已 running，直接返回
      if (sseTaskManager.isRunning(taskRunId)) {
        return reply.success({ taskRunId, alreadyRunning: true })
      }

      // 5. 更新任务状态为 running
      await generationTaskRunRepository.updateById(taskRunId, {
        status: GenerationTaskRunStatusEnum.running,
      })

      // 6. 注册任务并启动后台执行
      sseTaskManager.register(taskRunId)
      sseTaskManager.startTask(taskRunId, () =>
        runCaseGenerationTask({
          scenarios,
          casesPerScenario,
          tagTree,
          datasetId,
          generationTaskRunId: taskRunId!,
          scenarioPlanId,
          maxIterations,
          maxRefineRoundsPerBatch,
          auditConcurrency,
          fixConcurrency,
        }),
      )

      return reply.success({ taskRunId })
    },
  )

  // ─────────────────────────────────────────────────────────────────────
  // GET /:taskRunId/stream —— 订阅实时事件流（SSE）
  //
  // - 不回放历史事件（前端只关心当前及之后的事件）
  // - 若任务已结束，发送终态事件并关闭
  // - 若任务在运行，订阅 EventEmitter，只推新事件
  // ─────────────────────────────────────────────────────────────────────
  app.get(
    '/:taskRunId/stream',
    {
      schema: {
        params: z.object({
          taskRunId: z.string().min(1),
        }),
      },
    },
    async (req, reply) => {
      const { taskRunId } = req.params
      await handleSseStreamSubscription(reply, taskRunId, req, SSE_EVENT_TYPES)
    },
  )
}

export default caseGenerationRoutes
