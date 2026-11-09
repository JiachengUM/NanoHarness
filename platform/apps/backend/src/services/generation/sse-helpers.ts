import type { FastifyReply } from 'fastify'
import { Readable } from 'stream'
import { generationTaskRunRepository } from '@eval-platform/database'
import { sseTaskManager, type SSEEvent, type TaskStatus } from './sse-task-manager'

// ═══════════════════════════════════════════════════════════════════════════
// SSE 响应写入辅助
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 向客户端写入一个 SSE 事件
 */
export function writeSSEEvent(reply: FastifyReply, event: SSEEvent) {
  const data = JSON.stringify(event)
  reply.raw.write(`data: ${data}\n\n`)
}

/**
 * 结束 SSE 连接
 */
export function endSSE(reply: FastifyReply) {
  reply.raw.end()
}

/**
 * 设置 SSE 响应头
 */
export function setSSEHeaders(reply: FastifyReply) {
  reply.raw.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    Connection: 'keep-alive',
  })
}

// ═══════════════════════════════════════════════════════════════════════════
// 终态事件回放
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 根据任务状态发送对应的终态事件并关闭 SSE
 *
 * 用于：客户端重连时任务已结束，从 MongoDB events 数组中回放最后一个
 * complete/error 事件给客户端。
 *
 * @param reply Fastify reply
 * @param status 任务终态
 * @param taskRunId 任务运行 ID
 * @param terminalEventTypes 终态事件类型集合，例如 { COMPLETE: 'complete', ERROR: 'error' }
 */
export async function sendTerminalEventByStatus(
  reply: FastifyReply,
  status: TaskStatus,
  taskRunId: string,
  terminalEventTypes: { COMPLETE: string; ERROR: string },
) {
  if (status === 'completed' || status === 'failed') {
    const taskRun = await generationTaskRunRepository.findById(taskRunId)
    const events = taskRun?.events || []
    const lastTerminal = [...events]
      .reverse()
      .find((e: any) => e.type === terminalEventTypes.COMPLETE || e.type === terminalEventTypes.ERROR)
    if (lastTerminal) {
      writeSSEEvent(reply, lastTerminal as unknown as SSEEvent)
    } else if (status === 'completed') {
      writeSSEEvent(reply, {
        type: terminalEventTypes.COMPLETE,
        data: { message: '任务已完成（无汇总数据）' },
      })
    } else {
      writeSSEEvent(reply, {
        type: terminalEventTypes.ERROR,
        data: { message: '任务执行失败', code: 'GENERATION_ERROR' },
      })
    }
  }
  // cancelled：不写事件，直接关闭
  endSSE(reply)
}

// ═══════════════════════════════════════════════════════════════════════════
// SSE 订阅辅助
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 处理 SSE stream 路由的订阅逻辑（通用）
 *
 * 流程：
 * 1. 检查任务是否存在
 * 2. 设置 SSE 响应头
 * 3. 查询当前状态：
 *    - 已结束 → 发送终态事件并关闭
 *    - running → 订阅实时事件 + 订阅 done 事件
 * 4. 连接断开时清理订阅
 *
 * @param reply Fastify reply
 * @param taskRunId 任务运行 ID
 * @param req raw 请求对象（用于监听 close/aborted 事件）
 * @param terminalEventTypes 终态事件类型集合
 */
export async function handleSseStreamSubscription(
  reply: FastifyReply,
  taskRunId: string,
  req: {
    raw: Readable & { on: (ev: string, cb: () => void) => void; off: (ev: string, cb: () => void) => void }
  },
  terminalEventTypes: { COMPLETE: string; ERROR: string },
) {
  // 1. 检查任务是否存在
  const taskRun = await generationTaskRunRepository.findById(taskRunId)
  if (!taskRun) {
    reply.raw.statusCode = 404
    reply.raw.end(JSON.stringify({ message: '任务不存在' }))
    return
  }

  // 2. 设置 SSE 响应头
  setSSEHeaders(reply)

  // 3. 查询当前状态
  const status = await sseTaskManager.getStatus(taskRunId)
  console.log(`[StreamSubscribe] taskRunId=${taskRunId} status=${status}`)

  // 4. 任务已不在 running → 发送终态事件并关闭
  if (!status || status !== 'running') {
    await sendTerminalEventByStatus(reply, status || 'completed', taskRunId, terminalEventTypes)
    return
  }

  // 5. 任务正在运行 → 订阅实时事件
  let isClientDisconnected = false
  const markDisconnected = () => {
    isClientDisconnected = true
  }
  req.raw.on('close', markDisconnected)
  req.raw.on('aborted', markDisconnected)

  const unsubscribe = sseTaskManager.subscribe(taskRunId, (event) => {
    if (isClientDisconnected) return
    writeSSEEvent(reply, event)
  })

  // 订阅任务结束事件（事件驱动，无需轮询）
  // 任务结束时回放最后一个 complete/error 事件给客户端
  const unsubscribeDone = sseTaskManager.onDone(taskRunId, async () => {
    if (isClientDisconnected) return
    const freshTaskRun = await generationTaskRunRepository.findById(taskRunId)
    const events = freshTaskRun?.events || []
    const lastTerminal = [...events]
      .reverse()
      .find((e: any) => e.type === terminalEventTypes.COMPLETE || e.type === terminalEventTypes.ERROR)
    if (lastTerminal) {
      writeSSEEvent(reply, lastTerminal as unknown as SSEEvent)
    }
    endSSE(reply)
  })

  // 6. 清理（连接断开时解订阅，任务继续跑不受影响）
  const cleanup = () => {
    isClientDisconnected = true
    unsubscribe()
    unsubscribeDone()
    req.raw.off('close', markDisconnected)
    req.raw.off('aborted', markDisconnected)
  }
  req.raw.on('close', cleanup)
}

export { sseTaskManager }
export type { SSEEvent, TaskStatus }
