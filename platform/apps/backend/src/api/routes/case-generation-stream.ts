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

// URL 前缀: /api/case-generation-stream
export const prefix = '/case-generation-stream'

// ═══════════════════════════════════════════════════════════════════════════
// Schema 定义
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 流式用例生成请求 Schema
 */
export const GenerateCasesStreamRequestSchema = z.object({
  generationTaskRunId: z.string().optional(),
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

/**
 * 取消用例生成请求 Schema
 */
export const CancelCaseGenerationSchema = z.object({
  datasetId: z.string().optional(),
  generationTaskRunId: z.string().optional(),
})

// 流式输出的事件类型
const SSE_EVENT_TYPES = {
  CASE: 'case', // 新生成的用例
  PROGRESS: 'progress', // 进度更新
  COMPLETE: 'complete', // 生成完成
  ERROR: 'error', // 错误
} as const

// 取消用例生成用的 key 集合和 AbortController 管理
const cancelledCaseGenerationKeys = new Set<string>()
const caseGenerationAbortControllers = new Map<string, AbortController>()

// ═══════════════════════════════════════════════════════════════════════════
// 类型导出
// ═══════════════════════════════════════════════════════════════════════════

export type GenerateCasesStreamRequest = z.infer<typeof GenerateCasesStreamRequestSchema>

// ═══════════════════════════════════════════════════════════════════════════
// SSE 辅助函数
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 发送 SSE 事件
 */
async function sendSSEEvent(reply: any, event: any, generationTaskRunId?: string, isClientDisconnected = false) {
  if (generationTaskRunId) {
    const generationTaskRun = await generationTaskRunRepository.findById(generationTaskRunId)
    if (generationTaskRun) {
      generationTaskRun.events.push(event)
      await generationTaskRunRepository.updateById(generationTaskRunId, generationTaskRun)
    }
  }

  // 客户端已断开时不写 SSE，但事件仍存储到 DB
  if (isClientDisconnected) return

  const data = JSON.stringify(event)
  reply.raw.write(`data: ${data}\n\n`)
}

/**
 * 结束 SSE 连接
 */
function endSSE(reply: any) {
  reply.raw.end()
}

// ═══════════════════════════════════════════════════════════════════════════
// 路由实现
// ═══════════════════════════════════════════════════════════════════════════

const caseGenerationStreamRoutes: FastifyPluginAsyncZod = async (app) => {
  /**
   * POST /api/case-generation-stream/cancel
   * 取消用例生成任务（中断 LLM HTTP 请求）
   */
  app.post(
    '/cancel',
    {
      schema: {
        body: CancelCaseGenerationSchema,
      },
    },
    async (req, reply) => {
      const { datasetId, generationTaskRunId } = req.body
      if (!datasetId && !generationTaskRunId) {
        return reply.fail('请提供 datasetId 或 generationTaskRunId', {
          statusCode: HTTP_STATUS.BAD_REQUEST,
        })
      }
      if (datasetId) {
        cancelledCaseGenerationKeys.add(`dataset:${datasetId}`)
        caseGenerationAbortControllers.get(`dataset:${datasetId}`)?.abort()
      }
      if (generationTaskRunId) {
        cancelledCaseGenerationKeys.add(`run:${generationTaskRunId}`)
        caseGenerationAbortControllers.get(`run:${generationTaskRunId}`)?.abort()
      }
      return reply.success(true)
    },
  )

  /**
   * POST /api/case-generation-stream
   * 流式生成用例（SSE）
   *
   * 每生成一个合格用例，就会通过 SSE 实时推送给客户端
   */
  app.post(
    '/',
    {
      schema: {
        body: GenerateCasesStreamRequestSchema,
      },
    },
    async (req, reply) => {
      const {
        generationTaskRunId,
        scenarioIds,
        datasetId,
        casesPerScenario,
        tagTreeName,
        maxIterations,
        maxRefineRoundsPerBatch,
        auditConcurrency,
        fixConcurrency,
      } = req.body

      // 1. 验证数据集存在
      const dataset = await datasetRepository.findById(datasetId)
      if (!dataset) {
        return reply.fail('数据集不存在', { statusCode: HTTP_STATUS.NOT_FOUND })
      }

      // 2. 加载标签树（必传）
      const tagTreeDoc = await tagTreeRepository.findByName(tagTreeName)
      if (!tagTreeDoc) {
        return reply.fail('标签树不存在', { statusCode: HTTP_STATUS.NOT_FOUND })
      }
      const tagTree = TagTree.fromJSON(tagTreeDoc.tree)

      // 取消信号管理（与场景生成一致的解耦设计：客户端断开不中断后端，只有 POST /cancel 才中断）
      const caseGenerationKeys = [
        datasetId ? `dataset:${datasetId}` : '',
        generationTaskRunId ? `run:${generationTaskRunId}` : '',
      ].filter(Boolean)

      let isClientDisconnected = false
      const markClientDisconnected = () => {
        isClientDisconnected = true
      }
      const isCancelled = () => caseGenerationKeys.some((key) => cancelledCaseGenerationKeys.has(key))

      const caseAbortController = new AbortController()
      caseGenerationKeys.forEach((key) => caseGenerationAbortControllers.set(key, caseAbortController))

      req.raw.on('close', markClientDisconnected)
      req.raw.on('aborted', markClientDisconnected)

      // 3. 设置 SSE 响应头
      reply.raw.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      })

      // 4. 从数据库加载场景列表（通过 scenario_id 查询）
      const scenarios = []
      const notFoundIds = []
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

      // 存储所有生成的用例（用于保存到数据库）
      const allCases: any[] = []

      try {
        if (notFoundIds.length > 0) {
          await sendSSEEvent(
            reply,
            {
              type: SSE_EVENT_TYPES.ERROR,
              data: {
                message: `场景不存在: ${notFoundIds.join(', ')}`,
                code: 'SCENARIOS_NOT_FOUND',
              },
            },
            generationTaskRunId,
            isClientDisconnected,
          )
          endSSE(reply)
          return
        }

        if (scenarios.length === 0) {
          await sendSSEEvent(
            reply,
            {
              type: SSE_EVENT_TYPES.COMPLETE,
              data: {
                totalGenerated: 0,
                totalScenarios: 0,
                casesPerScenario,
              },
            },
            generationTaskRunId,
            isClientDisconnected,
          )
          endSSE(reply)
          return
        }

        // 5. 调用 generateAndRefineCases 生成并审核修复用例（流式）
        const client = createClient()

        // 使用流式生成，每当生成一个合格用例就立即推送
        await generateAndRefineCases(
          scenarios,
          casesPerScenario,
          tagTree,
          client,
          auditCases,
          fixCasesByAudit,
          datasetId,
          {
            maxIterations: maxIterations ?? 3,
            maxRefineRoundsPerBatch: maxRefineRoundsPerBatch ?? 1,
            auditConcurrency: auditConcurrency ?? 2,
            fixConcurrency: fixConcurrency ?? 2,
            signal: caseAbortController.signal,

            // 进度回调
            onProgress: async (info) => {
              await sendSSEEvent(
                reply,
                {
                  type: SSE_EVENT_TYPES.PROGRESS,
                  data: {
                  stage: info.stage,
                  current: info.current,
                  total: info.total,
                  progressPercentage: info.progressPercentage,
                  currentStep: info.currentStep,
                  currentScenarioName: info.currentScenarioName,
                },
                },
                generationTaskRunId,
                isClientDisconnected,
              )
            },

            // 流式用例回调：每生成一个合格用例就推送
            onCaseGenerated: async (caseItem, info) => {
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
              await sendSSEEvent(
                reply,
                {
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
                },
                generationTaskRunId,
                isClientDisconnected,
              )
            },
          },
        )

        // 6. 发送完成事件
        await sendSSEEvent(
          reply,
          {
            type: SSE_EVENT_TYPES.COMPLETE,
            data: {
              totalGenerated: allCases.length,
              totalScenarios: scenarios.length,
              casesPerScenario,
            },
          },
          generationTaskRunId,
          isClientDisconnected,
        )

        // 更新生成任务运行状态为完成
        if (generationTaskRunId) {
          await generationTaskRunRepository.updateById(generationTaskRunId, {
            status: GenerationTaskRunStatusEnum.completed,
          })
        }

        // 结束 SSE 连接
        endSSE(reply)
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : '未知错误'
        const isAbortError = error instanceof Error && error.name === 'AbortError'
        const cancelled = isAbortError || isCancelled()

        console.error('[Generate Cases Stream Error]', error)

        if (cancelled) {
          console.log(`[Generate Cases Stream] 已取消，已生成 ${allCases.length} 个用例`)
          // 更新生成任务运行状态为失败（取消视为一种终止）
          if (generationTaskRunId) {
            await generationTaskRunRepository.updateById(generationTaskRunId, {
              status: GenerationTaskRunStatusEnum.failed,
            })
          }
          await sendSSEEvent(
            reply,
            {
              type: SSE_EVENT_TYPES.ERROR,
              data: {
                message: '用例生成已取消',
                code: 'GENERATION_CANCELLED',
              },
            },
            generationTaskRunId,
            isClientDisconnected,
          )
        } else {
          // 发送错误事件
          await sendSSEEvent(
            reply,
            {
              type: SSE_EVENT_TYPES.ERROR,
              data: {
                message: `用例生成失败: ${errorMessage}`,
                code: 'GENERATION_ERROR',
              },
            },
            generationTaskRunId,
            isClientDisconnected,
          )
        }

        // 结束 SSE 连接
        endSSE(reply)
      } finally {
        // 清理取消标记和 AbortController
        caseGenerationKeys.forEach((key) => {
          cancelledCaseGenerationKeys.delete(key)
          caseGenerationAbortControllers.delete(key)
        })
        req.raw.off('close', markClientDisconnected)
        req.raw.off('aborted', markClientDisconnected)
      }
    },
  )
}

export default caseGenerationStreamRoutes
