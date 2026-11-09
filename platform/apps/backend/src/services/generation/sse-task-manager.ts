import { EventEmitter } from 'events'
import { generationTaskRunRepository } from '@eval-platform/database'

/**
 * SSE 事件结构（通用，事件 type 由各业务路由自定义）
 */
export interface SSEEvent {
  type: string
  data: Record<string, unknown>
}

/**
 * 任务状态
 */
export type TaskStatus = 'running' | 'completed' | 'cancelled' | 'failed'

/**
 * 单实例进程内任务管理器（通用，不绑定具体业务）
 *
 * 职责：
 * 1. 将任务执行与 HTTP/SSE 连接解耦 —— 任务在后台 setImmediate 中执行，连接断了也继续跑
 * 2. 通过 EventEmitter 向在线订阅者广播事件，连接断开只解订阅
 * 3. 事件写入 MongoDB events 数组，便于后续审计/扩展
 *
 * 不支持多实例部署（需要 Redis pub/sub 才能跨实例广播）。
 *
 * 适用场景：scenario 生成、case 生成 等耗时 SSE 任务。
 */
class SseTaskManager {
  /** taskRunId → emitter，仅 running 中任务存在 */
  private emitters = new Map<string, EventEmitter>()

  /** taskRunId → 当前状态 */
  private statuses = new Map<string, TaskStatus>()

  /**
   * 注册一个任务，标记为 running 并创建 emitter
   *
   * @throws 若 taskRunId 已在运行
   */
  register(taskRunId: string): void {
    if (this.emitters.has(taskRunId)) {
      throw new Error(`Task ${taskRunId} already running`)
    }
    this.emitters.set(taskRunId, new EventEmitter())
    this.statuses.set(taskRunId, 'running')
  }

  /**
   * 启动后台任务（与请求上下文解耦）
   *
   * 任务在 setImmediate 中执行，调用方立即返回。
   * 任务结束后自动标记状态并清理 emitter（保留 status 供后续查询）。
   *
   * @param taskRunId 任务 ID
   * @param runFn 任务函数，必须自己处理取消逻辑（通过 shouldStop/isCancelled）
   *   - 抛出 'GENERATION_CANCELLED' 会被识别为 cancelled
   *   - 其他异常会被识别为 failed
   *   - 正常返回且未显式 markDone，会被识别为 completed
   */
  startTask(taskRunId: string, runFn: () => Promise<void>): void {
    setImmediate(async () => {
      try {
        await runFn()
        // 如果任务函数内部没有显式标记状态，默认标记为 completed
        if (this.statuses.get(taskRunId) === 'running') {
          this.markDone(taskRunId, 'completed')
        }
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error)
        if (msg === 'GENERATION_CANCELLED') {
          this.markDone(taskRunId, 'cancelled')
        } else {
          console.error(`[SseTaskManager] Task ${taskRunId} failed:`, error)
          this.markDone(taskRunId, 'failed')
        }
      }
    })
  }

  /**
   * 推送事件：写 MongoDB + 广播给在线订阅者
   *
   * 即使没有订阅者也会写入 DB，保证断线期间产生的事件不丢。
   */
  async emit(taskRunId: string, event: SSEEvent): Promise<void> {
    // 1. 写入 MongoDB events 数组
    try {
      const taskRun = await generationTaskRunRepository.findById(taskRunId)
      if (taskRun) {
        taskRun.events.push(event as unknown as Record<string, unknown>)
        await generationTaskRunRepository.updateById(taskRunId, taskRun)
      }
    } catch (err) {
      console.warn(`[SseTaskManager] emit: failed to persist event for ${taskRunId}:`, err)
    }

    // 2. 广播给在线订阅者（没有订阅者时事件被丢弃，不影响任务执行）
    this.emitters.get(taskRunId)?.emit('event', event)
  }

  /**
   * 订阅实时事件流
   *
   * @returns unsubscribe 函数，SSE 连接断开时必须调用
   */
  subscribe(taskRunId: string, onEvent: (event: SSEEvent) => void): () => void {
    const emitter = this.emitters.get(taskRunId)
    if (!emitter) {
      // 任务已不在 running，返回 no-op
      return () => {}
    }
    emitter.on('event', onEvent)
    return () => {
      emitter.off('event', onEvent)
    }
  }

  /**
   * 订阅任务结束事件（任务转为终态时触发一次）
   *
   * 若任务已结束（emitter 已被清理），立即用 setImmediate 触发回调。
   *
   * @returns unsubscribe 函数
   */
  onDone(taskRunId: string, onDone: (status: TaskStatus) => void): () => void {
    const emitter = this.emitters.get(taskRunId)
    if (!emitter) {
      // emitter 已被清理，说明任务已结束，查 status 立即回调
      const status = this.statuses.get(taskRunId)
      if (status) setImmediate(() => onDone(status))
      return () => {}
    }
    emitter.once('done', (status: TaskStatus) => onDone(status))
    return () => {
      emitter.off('done', onDone)
    }
  }

  /**
   * 查询任务当前状态
   *
   * 优先用内存中的状态（running 中），否则回查 MongoDB
   */
  async getStatus(taskRunId: string): Promise<TaskStatus | null> {
    const cached = this.statuses.get(taskRunId)
    if (cached) return cached

    const taskRun = await generationTaskRunRepository.findById(taskRunId)
    if (!taskRun) return null
    return (taskRun.status as TaskStatus) || null
  }

  /**
   * 标记任务完成/取消/失败
   *
   * 不立即删除 emitter，而是发完终态事件后再清理。
   * emitter 在内存中保留一段时间也无伤大雅，由 markDone 内部的 cleanup 处理。
   */
  markDone(taskRunId: string, status: TaskStatus): void {
    this.statuses.set(taskRunId, status)

    // 通知所有在线订阅者：任务结束（订阅方需自己关闭 SSE）
    // 通过 emit('done') 而不是 event，避免与业务事件混淆
    this.emitters.get(taskRunId)?.emit('done', status)

    // 清理 emitter（订阅者已在 done 事件中收到通知）
    // 用 setImmediate 让订阅者的 done 回调先执行完再清理
    setImmediate(() => {
      this.emitters.delete(taskRunId)
    })
  }

  /**
   * 判断任务是否还在运行
   */
  isRunning(taskRunId: string): boolean {
    return this.statuses.get(taskRunId) === 'running'
  }

  /**
   * 取消任务（由 /cancel 路由调用）
   *
   * 只标记状态，实际中断由 runFn 内部检查 isCancelled() 实现。
   */
  requestCancel(taskRunId: string): void {
    // 不直接 markDone，让 runFn 自己感知到取消后退出
    // runFn 退出后由 startTask 的 catch 捕获 GENERATION_CANCELLED 并 markDone
    // 这里只做标记，由调用方在 runFn 中轮询检查
    this.emitters.get(taskRunId)?.emit('cancel-requested')
  }
}

/**
 * 通用 SSE 任务管理器单例
 *
 * 所有 SSE 流式生成任务（scenario、case 等）共享同一个实例。
 */
export const sseTaskManager = new SseTaskManager()
