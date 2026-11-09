import type { FastifyPluginAsyncZod } from 'fastify-type-provider-zod'
import { z } from 'zod'
import {
  tagTreeRepository,
  scenarioRepository,
  scenarioPlanRepository,
  generationTaskRunRepository,
  GenerationTaskRunStatusEnum,
  CreateScenarioDto,
  OutScenarioPlanDto,
  OutTagTreeDto,
} from '@eval-platform/database'
import { generateScenarios, TagTree } from '@eval-platform/makedata'
import { createClient } from '@eval-platform/llm'
import { HTTP_STATUS } from '../../constants/http-status'

// URL 前缀: /api/scenario-generation-stream
export const prefix = '/scenario-generation-stream'

// ═══════════════════════════════════════════════════════════════════════════
// Schema 定义
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 流式场景生成请求 Schema
 *
 * 支持两种方式：
 * 1. 提供 scenarioPlanId：使用已生成的 Plan
 * 2. 提供 query + tagTreeName：自动生成 Plan
 */
export const GenerateScenariosStreamRequestSchema = z.object({
  // 方式1：使用已有的 Plan
  scenarioPlanId: z.string().optional(),
  generationTaskRunId: z.string().optional(),

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
  PATTERNS: 'patterns', // Pattern 生成完成（Plan 的下游产物）
  SCENARIO: 'scenario', // 新生成的场景
  PROGRESS: 'progress', // 进度更新（基于 Plan 的进度）
  COMPLETE: 'complete', // 生成完成
  ERROR: 'error', // 错误
  SCENARIO_DELETED: 'scenario_deleted', // 场景被去重移除
} as const

const cancelledGenerationKeys = new Set<string>()
const generationAbortControllers = new Map<string, AbortController>()

// ═══════════════════════════════════════════════════════════════════════════
// 类型导出
// ═══════════════════════════════════════════════════════════════════════════

export type GenerateScenariosStreamRequest = z.infer<typeof GenerateScenariosStreamRequestSchema>

// ═══════════════════════════════════════════════════════════════════════════
// SSE 辅助函数
// ═══════════════════════════════════════════════════════════════════════════

async function sendSSEEvent(reply: any, event: any, generationTaskRunId?: string, isClientDisconnected = false) {
  console.log('sendSSEEvent', generationTaskRunId, event)
  if (generationTaskRunId) {
    const generationTaskRun = await generationTaskRunRepository.findById(generationTaskRunId)
    if (generationTaskRun) {
      generationTaskRun.events.push(event)
      console.log('updateGenerationTaskRunById', generationTaskRunId, generationTaskRun)
      await generationTaskRunRepository.updateById(generationTaskRunId, generationTaskRun)
    }
  }

  // 客户端已断开时不写 SSE，但事件仍存储到 DB
  if (isClientDisconnected) return

  const data = JSON.stringify(event)
  reply.raw.write(`data: ${data}\n\n`)
}

function endSSE(reply: any) {
  reply.raw.end()
}

// ═══════════════════════════════════════════════════════════════════════════
// 路由实现
// ═══════════════════════════════════════════════════════════════════════════

const scenarioGenerationStreamRoutes: FastifyPluginAsyncZod = async (app) => {
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
      if (scenarioPlanId) {
        cancelledGenerationKeys.add(`plan:${scenarioPlanId}`)
        generationAbortControllers.get(`plan:${scenarioPlanId}`)?.abort()
      }
      if (generationTaskRunId) {
        cancelledGenerationKeys.add(`run:${generationTaskRunId}`)
        generationAbortControllers.get(`run:${generationTaskRunId}`)?.abort()
      }
      return reply.success(true)
    },
  )

  app.post(
    '/',
    {
      schema: {
        body: GenerateScenariosStreamRequestSchema,
      },
    },
    async (req, reply) => {
      const {
        scenarioPlanId,
        generationTaskRunId,
        query,
        tagTreeName,
        saveToDb,
        maxIterations,
        initialBatchSize,
        maxRefineRoundsPerBatch,
      } = req.body

      console.log('GenerateScenariosStreamRequest', req.body)

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
        // 使用已有 Plan
        const existingPlan = await scenarioPlanRepository.findScenarioPlanById(scenarioPlanId)
        if (!existingPlan) {
          return reply.fail('Plan 不存在', { statusCode: HTTP_STATUS.NOT_FOUND })
        }

        plan = existingPlan
        effectiveQuery = plan.original_query

        // 加载标签树
        tagTreeDoc = await tagTreeRepository.findByName(plan.tag_tree_name)
        if (!tagTreeDoc) {
          return reply.fail('Plan 关联的标签树不存在', { statusCode: HTTP_STATUS.NOT_FOUND })
        }

        // 更新 Plan 状态为生成中
        await scenarioPlanRepository.updatePlan(scenarioPlanId, { status: 'generating' })
        // 更新生成任务运行记录状态为 running
        if (plan.generation_task_run_id) {
          await generationTaskRunRepository.updateGenerationTaskRun(plan.generation_task_run_id, {
            status: GenerationTaskRunStatusEnum.running,
          })
        }
      } else {
        // 自动生成 Plan（需要 query 和 tagTreeName）
        tagTreeDoc = await tagTreeRepository.findByName(tagTreeName!)
        if (!tagTreeDoc) {
          return reply.fail('标签树不存在', { statusCode: HTTP_STATUS.NOT_FOUND })
        }
      }

      const tagTree = TagTree.fromJSON(tagTreeDoc.tree)
      const generationKeys = [
        scenarioPlanId ? `plan:${scenarioPlanId}` : '',
        generationTaskRunId ? `run:${generationTaskRunId}` : '',
      ].filter(Boolean)

      let isClientDisconnected = false
      const markClientDisconnected = () => {
        isClientDisconnected = true
        // 客户端断开时不 abort LLM 请求，后端任务继续执行
        // 只有 POST /cancel 才会 abort
      }
      const isCancelled = () => generationKeys.some((key) => cancelledGenerationKeys.has(key))

      // 创建 AbortController，用于中断 LLM HTTP 请求（仅 POST /cancel 触发）
      const generationAbortController = new AbortController()
      generationKeys.forEach((key) => generationAbortControllers.set(key, generationAbortController))

      req.raw.on('close', markClientDisconnected)
      req.raw.on('aborted', markClientDisconnected)

      // 2. 设置 SSE 响应头
      reply.raw.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      })

      // 3. 发送 Plan 信息（如果有，此时客户端还未断开）
      if (plan) {
        await sendSSEEvent(
          reply,
          {
            type: SSE_EVENT_TYPES.PLAN,
            data: {
              scenarioPlanId: plan.id,
              target_tags: plan.target_tags,
              task_description: plan.task_description,
              interpretation_notes: plan.interpretation_notes,
            },
          },
          generationTaskRunId,
        )
      }

      // 4. 创建 LLM 客户端并开始生成
      const client = createClient()
      const savedScenarios: any[] = []

      // SSE 事件发送闭包：客户端断开后仍存储事件到 DB，但不写 SSE 流
      const emit = async (event: any) => {
        await sendSSEEvent(reply, event, generationTaskRunId, isClientDisconnected)
      }

      try {
        const result = await generateScenarios(effectiveQuery, tagTree!, client, {
          plan: (plan as any) || undefined,
          maxIterations,
          initialBatchSize,
          maxRefineRoundsPerBatch,
          shouldStop: () => isCancelled(),
          signal: generationAbortController.signal,

          // Pattern 生成完成回调 - 通过 SSE 推给前端
          onPatternsGenerated: async (patterns, targetScenarioCount) => {
            if (isCancelled()) return
            // 持久化 targetScenarioCount 到 plan，供轮询恢复时计算进度
            if (plan) {
              await scenarioPlanRepository.updatePlan(plan.id, { target_scenario_count: targetScenarioCount } as any)
            }
            await emit({
              type: SSE_EVENT_TYPES.PATTERNS,
              data: { patterns, targetScenarioCount },
            })
          },

          // 进度回调 - 包含基于 Plan 的进度
          onProgress: async (info) => {
            if (isCancelled()) return
            await emit({
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

          // 流式场景回调
          onScenarioGenerated: async (scenario, info) => {
            if (isCancelled()) return
            if (!saveToDb) {
              await emit({
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
                // 回写 scenario_id，确保后续 onScenarioDeleted 能正确匹配 DB 和前端
                scenario.scenario_id = saved.scenario_id
                await emit({
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
                await emit({
                  type: SSE_EVENT_TYPES.ERROR,
                  data: {
                    message: `场景 ${scenario.scenario_id} 保存失败`,
                    code: 'SAVE_ERROR',
                  },
                })
              }
            }
          },

          // 场景被去重移除回调 - 同步删除 DB 记录并通知前端
          onScenarioDeleted: async (scenarioId, scenarioName, reason) => {
            if (isCancelled()) return
            if (saveToDb) {
              // 从 savedScenarios 数组查找并移除
              const idx = savedScenarios.findIndex((s) => s.scenario_id === scenarioId)
              if (idx >= 0) {
                const saved = savedScenarios[idx]
                savedScenarios.splice(idx, 1)
                // 用 Mongo _id 从 DB 删除
                await scenarioRepository.deleteScenario(saved.id)
              }
            }
            // 推送删除事件给前端
            await emit({
              type: SSE_EVENT_TYPES.SCENARIO_DELETED,
              data: { scenarioId, scenarioName, reason },
            })
          },
        })

        // 5. 更新 Plan 状态为完成（如果使用了 Plan）
        if (plan && !isCancelled()) {
          await scenarioPlanRepository.updatePlan(plan.id, {
            status: 'completed',
          })
        }

        // 6. 发送完成事件
        if (!isCancelled()) {
          await emit({
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

        if (!isClientDisconnected) {
          endSSE(reply)
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : '未知错误'
        const isAbortError = error instanceof DOMException && error.name === 'AbortError'
        const cancelled = errorMessage === 'GENERATION_CANCELLED' || isAbortError || isCancelled()
        if (cancelled) {
          if (plan) {
            await scenarioPlanRepository.updatePlan(plan.id, { status: 'cancelled' })
          }
          if (!reply.raw.writableEnded) {
            endSSE(reply)
          }
          return
        }
        console.error('[Generate Scenarios Stream Error]', error)

        await emit({
          type: SSE_EVENT_TYPES.ERROR,
          data: {
            message: `场景生成失败: ${errorMessage}`,
            code: 'GENERATION_ERROR',
          },
        })

        endSSE(reply)
      } finally {
        generationKeys.forEach((key) => {
          cancelledGenerationKeys.delete(key)
          generationAbortControllers.delete(key)
        })
        req.raw.off('close', markClientDisconnected)
        req.raw.off('aborted', markClientDisconnected)
      }
    },
  )
}

export default scenarioGenerationStreamRoutes
