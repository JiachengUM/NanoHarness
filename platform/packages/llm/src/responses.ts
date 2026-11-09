import OpenAI from 'openai'
import { MODELS } from './constants/models'

export async function invoke(client: OpenAI, params: OpenAI.Responses.ResponseCreateParamsNonStreaming, signal?: AbortSignal) {
  const response = await client.responses.create({
    model: MODELS.SEED_2_0_MINI_260428,
    ...params,
  }, signal ? { signal } : undefined)

  return response
}

export async function stream(
  client: OpenAI,
  params: Omit<OpenAI.Responses.ResponseCreateParamsNonStreaming, 'stream'>,
) {
  const stream = await client.responses.create({
    model: MODELS.SEED_2_0_MINI_260428,
    stream: true,
    ...params,
  })

  return stream
}

// ═══════════════════════════════════════════════════════════════════════════
// 带重试的 LLM 调用（处理 JSON 解析偶发错误）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 延迟函数
 */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

/**
 * 带重试的 LLM 调用（自动解析 JSON）
 *
 * 当 LLM 返回的 JSON 格式有误时自动重试调用，最多重试3次。
 * 使用指数退避策略：1s, 2s, 4s
 *
 * @param client OpenAI 客户端
 * @param params 调用参数
 * @param maxRetries 最大重试次数（默认3次）
 * @returns 解析后的对象
 */
export async function invokeWithRetry<T>(
  client: OpenAI,
  params: OpenAI.Responses.ResponseCreateParamsNonStreaming,
  maxRetries: number = 3,
  signal?: AbortSignal
): Promise<T> {
  let lastError: Error | null = null

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    try {
      const response = await invoke(client, params, signal)

      if (!response.output_text) {
        throw new Error('LLM 返回为空')
      }

      // 尝试解析 JSON
      return JSON.parse(response.output_text) as T
    } catch (error) {
      lastError = error as Error

      if (attempt < maxRetries) {
        console.warn(`[invokeWithRetry] LLM 调用失败 (尝试 ${attempt}/${maxRetries}): ${(error as Error).message}`)

        // 指数退避：1s, 2s, 4s
        const delay = Math.pow(2, attempt - 1) * 1000
        await sleep(delay)
      }
    }
  }

  throw new Error(`LLM 调用失败 (${maxRetries}次尝试): ${lastError?.message}`)
}

/**
 * 带重试的 LLM 调用（返回原始文本）
 *
 * @param client OpenAI 客户端
 * @param params 调用参数
 * @param maxRetries 最大重试次数（默认3次）
 * @returns LLM 返回的原始文本
 */
export async function invokeWithRetryRaw(
  client: OpenAI,
  params: OpenAI.Responses.ResponseCreateParamsNonStreaming,
  maxRetries: number = 3,
  signal?: AbortSignal
): Promise<string> {
  let lastError: Error | null = null

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    try {
      const response = await invoke(client, params, signal)

      if (!response.output_text) {
        throw new Error('LLM 返回为空')
      }

      return response.output_text
    } catch (error) {
      lastError = error as Error

      if (attempt < maxRetries) {
        console.warn(`[invokeWithRetryRaw] LLM 调用失败 (尝试 ${attempt}/${maxRetries}): ${(error as Error).message}`)

        // 指数退避：1s, 2s, 4s
        const delay = Math.pow(2, attempt - 1) * 1000
        await sleep(delay)
      }
    }
  }

  throw new Error(`LLM 调用失败 (${maxRetries}次尝试): ${lastError?.message}`)
}
