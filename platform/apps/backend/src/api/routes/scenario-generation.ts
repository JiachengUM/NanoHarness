import type { FastifyPluginAsyncZod } from 'fastify-type-provider-zod'
import { z } from 'zod'
import {
  tagTreeRepository,
  scenarioRepository,
  scenarioPlanRepository,
  type ScenarioPlanDoc,
  type TagTreeDoc,
  generationTaskRunRepository,
  GenerationTaskRunStatusEnum,
  CreateScenarioDto,
  OutScenarioPlanDto,
  OutTagTreeDto,
} from '@eval-platform/database'
import { generateScenarios, TagTree } from '@eval-platform/makedata'
import { createClient } from '@eval-platform/llm'
import { HTTP_STATUS } from '../../constants/http-status'
import { sseTaskManager, handleSseStreamSubscription } from '../../services/generation/sse-helpers'

// URL 前缀: /api/scenario-generation
export const prefix = '/scenario-generation'

// ═══════════════════════════════════════════════════════════════════════════
// Schema 定义
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 启动生成任务请求 Schema
 *
 * 支持两种方式：
 * 1. 提供 scenarioPlanId：使用已生成的 Plan
 * 2. 提供 query + tagTreeName：自动生成 Plan
 */
export const StartScenarioGenerationStreamSchema = z.object({
  // 方式1：使用已有的 Plan
  scenarioPlanId: z.string().optional(),

  // 方式2：自动生成 Plan（需要 query 和 tagTreeName）
  query: z.string().min(1, '场景生成描述不能为空').optional(),
  tagTreeName: z.string().min(1, '标签树名称不能为空').optional(),

  // 通用参数
  saveToDb: z.boolean().optional().default(false),

  // 可选的迭代控制参数
  maxIterations: z.number().int().positive().optional(),
  initialBatchSize: z.number().int().positive().optional(),
  maxRefineRoundsPerBatch: z.number().int().nonnegative().optional(),
})

export const CancelScenarioGenerationSchema = z.object({
  scenarioPlanId: z.string().optional(),
  generationTaskRunId: z.string().optional(),
})

// 流式输出的事件类型
const SSE_EVENT_TYPES = {
  PLAN: 'plan', // Plan 信息（开始生成前）
  PATTERNS: 'patterns', // 生成模式
  SCENARIO: 'scenario', // 新生成的场景
  PROGRESS: 'progress', // 进度更新（基于 Plan 的进度）
  COMPLETE: 'complete', // 生成完成
  ERROR: 'error', // 错误
} as const

// 取消标记集合（内存 Set，单实例有效）
// 由 /cancel 路由写入，runFn 内通过 isCancelled() 轮询检查
const cancelledGenerationKeys = new Set<string>()

// ═══════════════════════════════════════════════════════════════════════════
// 类型导出
// ═══════════════════════════════════════════════════════════════════════════

export type StartScenarioGenerationStreamRequest = z.infer<typeof StartScenarioGenerationStreamSchema>

// ═══════════════════════════════════════════════════════════════════════════
// 后台任务执行函数（与 HTTP 连接解耦）
// ═══════════════════════════════════════════════════════════════════════════

interface RunGenerationParams {
  effectiveQuery: string
  tagTree: TagTree
  plan: OutScenarioPlanDto | null
  generationTaskRunId: string
  scenarioPlanId?: string
  tagTreeDoc: OutTagTreeDto
  saveToDb: boolean
  maxIterations?: number
  initialBatchSize?: number
  maxRefineRoundsPerBatch?: number
}

async function runGenerationTask(params: RunGenerationParams) {
  const {
    effectiveQuery,
    tagTree,
    plan,
    generationTaskRunId,
    scenarioPlanId,
    tagTreeDoc,
    saveToDb,
    maxIterations,
    initialBatchSize,
    maxRefineRoundsPerBatch,
  } = params

  const generationKeys = [scenarioPlanId ? `plan:${scenarioPlanId}` : '', `run:${generationTaskRunId}`].filter(Boolean)

  const isCancelled = () => generationKeys.some((key) => cancelledGenerationKeys.has(key))

  const client = createClient()
  const savedScenarios: any[] = []

  try {
    // 发送 Plan 信息
    if (plan) {
      await sseTaskManager.emit(generationTaskRunId, {
        type: SSE_EVENT_TYPES.PLAN,
        data: {
          scenarioPlanId: plan.id,
          target_tags: plan.target_tags,
          task_description: plan.task_description,
          interpretation_notes: plan.interpretation_notes,
        },
      })
    }

    const result = await generateScenarios(effectiveQuery, tagTree, client, {
      plan: (plan as any) || undefined,
      maxIterations,
      initialBatchSize,
      maxRefineRoundsPerBatch,
      shouldStop: () => isCancelled(),

      // Pattern 生成完成回调 - 通过 SSE 推给前端
      onPatternsGenerated: async (patterns) => {
        if (isCancelled()) return
        await sseTaskManager.emit(generationTaskRunId, {
          type: SSE_EVENT_TYPES.PATTERNS,
          data: { patterns },
        })
      },

      onProgress: async (info) => {
        if (isCancelled()) return
        await sseTaskManager.emit(generationTaskRunId, {
          type: SSE_EVENT_TYPES.PROGRESS,
          data: {
            iteration: info.iteration,
            batchSize: info.batchSize,
            totalScenarios: info.totalScenarios,
            targetScenarioCount: info.targetScenarioCount,
            progressPercentage: info.progressPercentage,
            coveragePercentage: info.coveragePercentage,
            satisfied: info.satisfied,
            stage: info.stage,
            currentStep: info.currentStep,
            stepProgress: info.stepProgress,
          },
        })
      },

      onScenarioGenerated: async (scenario, info) => {
        if (isCancelled()) return
        if (!saveToDb) {
          await sseTaskManager.emit(generationTaskRunId, {
            type: SSE_EVENT_TYPES.SCENARIO,
            data: {
              scenario,
              iteration: info.iteration,
              totalScenarios: info.totalScenarios,
              targetScenarioCount: info.targetScenarioCount,
              progressPercentage: info.progressPercentage,
              coveragePercentage: info.coveragePercentage,
            },
          })
        } else {
          // 保存到数据库
          let retryCount = 0
          let saved = null
          let scenarioToSave: CreateScenarioDto = {
            ...scenario,
            pattern: scenario.pattern,
            tag_tree_id: tagTreeDoc.id,
            generation_task_id: plan?.task_id?.toString(),
            scenario_plan_id: plan?.id?.toString(),
            source_query: effectiveQuery,
          }

          while (retryCount < 3) {
            try {
              saved = await scenarioRepository.createScenario(scenarioToSave)
              break
            } catch (error: any) {
              if (error.code === 11000 || (error.message && error.message.includes('duplicate'))) {
                retryCount++
                const timestamp = Date.now()
                const randomSuffix = Math.random().toString(36).substring(2, 6)
                scenarioToSave.scenario_id = `${scenario.scenario_id}_${timestamp}_${randomSuffix}`
              } else {
                console.warn(`保存场景失败: ${error.message}`)
                break
              }
            }
          }

          if (saved) {
            savedScenarios.push(saved)
            await sseTaskManager.emit(generationTaskRunId, {
              type: SSE_EVENT_TYPES.SCENARIO,
              data: {
                scenario: {
                  scenario_id: saved.scenario_id,
                  scenario_name: saved.scenario_name,
                  description: saved.description,
                  tags: saved.tags,
                  pattern: saved.pattern,
                },
                iteration: info.iteration,
                totalScenarios: savedScenarios.length,
                targetScenarioCount: info.targetScenarioCount,
                progressPercentage: Math.round((savedScenarios.length / info.targetScenarioCount) * 100),
                coveragePercentage: info.coveragePercentage,
              },
            })
          } else {
            await sseTaskManager.emit(generationTaskRunId, {
              type: SSE_EVENT_TYPES.ERROR,
              data: {
                message: `场景 ${scenario.scenario_id} 保存失败`,
                code: 'SAVE_ERROR',
              },
            })
          }
        }
      },
    })

    // 更新 Plan 状态为完成
    if (plan && !isCancelled()) {
      await scenarioPlanRepository.updatePlan(plan.id, { status: 'completed' })
    }

    // 发送完成事件
    if (!isCancelled()) {
      await sseTaskManager.emit(generationTaskRunId, {
        type: SSE_EVENT_TYPES.COMPLETE,
        data: {
          scenarioPlanId: plan?.id || null,
          targetCount: result.targetCount,
          actualCount: result.actualCount,
          achievementRate: Math.round((result.actualCount / result.targetCount) * 100),
          totalIterations: result.totalIterations,
          finalCoveragePercentage: result.finalCoveragePercentage,
          satisfied: result.satisfied,
        },
      })
    }

    // 标记任务完成
    if (isCancelled()) {
      if (plan) {
        await scenarioPlanRepository.updatePlan(plan.id, { status: 'cancelled' })
      }
      sseTaskManager.markDone(generationTaskRunId, 'cancelled')
    } else {
      sseTaskManager.markDone(generationTaskRunId, 'completed')
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '未知错误'
    const cancelled = errorMessage === 'GENERATION_CANCELLED' || isCancelled()
    if (cancelled) {
      if (plan) {
        await scenarioPlanRepository.updatePlan(plan.id, { status: 'cancelled' })
      }
      sseTaskManager.markDone(generationTaskRunId, 'cancelled')
      return
    }
    console.error('[Generate Scenarios Stream Error]', error)

    await sseTaskManager.emit(generationTaskRunId, {
      type: SSE_EVENT_TYPES.ERROR,
      data: {
        message: `场景生成失败: ${errorMessage}`,
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

const scenarioGenerationRoutes: FastifyPluginAsyncZod = async (app) => {
  // ─────────────────────────────────────────────────────────────────────
  // POST /cancel —— 取消任务
  // ─────────────────────────────────────────────────────────────────────
  app.post(
    '/cancel',
    {
      schema: {
        body: CancelScenarioGenerationSchema,
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
  // POST /start —— 启动生成任务，立即返回 taskRunId
  //
  // 任务在后台 setImmediate 中执行，与连接解耦，连接断了任务继续跑。
  // 前端拿到 taskRunId 后，用 GET /:taskRunId/stream 订阅实时事件。
  // ─────────────────────────────────────────────────────────────────────
  app.post(
    '/start',
    {
      schema: {
        body: StartScenarioGenerationStreamSchema,
      },
    },
    async (req, reply) => {
      const { scenarioPlanId, query, tagTreeName, saveToDb, maxIterations, initialBatchSize, maxRefineRoundsPerBatch } =
        req.body

      console.log('[StartScenarioGeneration]', req.body)

      // 验证参数
      if (!scenarioPlanId && (!query || !tagTreeName)) {
        return reply.fail('请提供 scenarioPlanId 或 query + tagTreeName', {
          statusCode: HTTP_STATUS.BAD_REQUEST,
        })
      }

      // 1. 获取 Plan 和标签树
      let plan: OutScenarioPlanDto | null = null
      let tagTreeDoc: OutTagTreeDto | null = null
      let effectiveQuery: string = query || ''

      if (scenarioPlanId) {
        const existingPlan = await scenarioPlanRepository.findScenarioPlanById(scenarioPlanId)
        if (!existingPlan) {
          return reply.fail('Plan 不存在', { statusCode: HTTP_STATUS.NOT_FOUND })
        }

        plan = existingPlan
        effectiveQuery = plan.original_query

        // 复用已有的 generation_task_run_id，没有的话报错（要求前端先创建）
        if (!plan.generation_task_run_id) {
          return reply.fail('Plan 未关联 generation_task_run_id，请先创建任务运行记录', {
            statusCode: HTTP_STATUS.BAD_REQUEST,
          })
        }

        const taskRunId = plan.generation_task_run_id.toString()

        // 防重复启动：若任务已 running，直接返回
        if (sseTaskManager.isRunning(taskRunId)) {
          return reply.success({ taskRunId, plan, alreadyRunning: true })
        }

        // 加载标签树
        tagTreeDoc = await tagTreeRepository.findByName(plan.tag_tree_name)
        if (!tagTreeDoc) {
          return reply.fail('Plan 关联的标签树不存在', { statusCode: HTTP_STATUS.NOT_FOUND })
        }

        // 更新 Plan 状态为生成中
        await scenarioPlanRepository.updatePlan(scenarioPlanId, { status: 'generating' })
        await generationTaskRunRepository.updateGenerationTaskRun(taskRunId, {
          status: GenerationTaskRunStatusEnum.running,
        })

        // 2. 注册任务并启动后台执行
        sseTaskManager.register(taskRunId)
        sseTaskManager.startTask(taskRunId, () =>
          runGenerationTask({
            effectiveQuery,
            tagTree: TagTree.fromJSON(tagTreeDoc!.tree),
            plan,
            generationTaskRunId: taskRunId,
            scenarioPlanId,
            tagTreeDoc: tagTreeDoc!,
            saveToDb,
            maxIterations,
            initialBatchSize,
            maxRefineRoundsPerBatch,
          }),
        )

        return reply.success({ taskRunId, plan })
      } else {
        // 方式2：自动生成 Plan（需要 query 和 tagTreeName）
        // 这条路径需要先生成 Plan，再创建 generationTaskRun
        return reply.fail(
          '当前仅支持 scenarioPlanId 模式，请先调用 /scenario-planning 创建 Plan 并关联 generationTaskRun',
          { statusCode: HTTP_STATUS.BAD_REQUEST },
        )
      }
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

export default scenarioGenerationRoutes
