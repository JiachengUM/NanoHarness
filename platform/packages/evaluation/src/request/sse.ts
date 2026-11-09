import { createParser, type EventSourceMessage } from 'eventsource-parser'

export type SSERES<T> = {
  code: number
  msg: string
  result: T
}

/**
 * SSE接口请求，返回一个Promise，在请求完成或发生错误时resolve或reject
 * @param url 接口URL
 * @param method HTTP方法，如'POST'
 * @param data 请求参数
 * @param onMessage 接收到消息时的回调
 * @param onClose 请求关闭时的回调
 * @param signal 可选的AbortSignal，用于取消请求
 */
export async function sseRequest<P, T>(
  url: string,
  method: string,
  data: P,
  onMessage: (data: T) => void,
  onClose: () => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    throw new Error(`SSE request failed with status ${response.status}`)
  }

  if (!response.body) {
    throw new Error('SSE response body is empty')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()

  const parser = createParser({
    onEvent(event: EventSourceMessage) {
      if (!event.data) {
        return
      }

      try {
        const parsed = JSON.parse(event.data) as T
        onMessage?.(parsed)
      } catch (e) {
        console.log(e)
      }
    },
  })

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }

      parser.feed(decoder.decode(value, { stream: true }))
    }

    parser.feed(decoder.decode())
  } catch (err) {
    if (!signal?.aborted) {
      console.log('SSE error:', err)
      throw err
    }
  } finally {
    reader.releaseLock()
    onClose?.()
  }
}

/**
 * 流式SSE接口请求，返回一个异步生成器，逐条yield接口发送的消息
 * @param url 接口URL
 * @param method HTTP方法，如'POST'
 * @param data 请求参数
 * @param signal 可选的AbortSignal，用于取消请求
 * @returns AsyncGenerator，逐条yield接口发送的消息
 */
export async function* sseStream<P, T>(
  url: string,
  method: string,
  data: P,
  signal?: AbortSignal,
): AsyncGenerator<T, void, unknown> {
  const controller = new AbortController()
  let wakeUp: (() => void) | undefined

  const queue: T[] = []
  let done = false
  let error: unknown = null

  const notify = () => {
    wakeUp?.()
    wakeUp = undefined
  }

  const waitNext = () =>
    new Promise<void>((resolve) => {
      wakeUp = resolve
    })

  if (signal) {
    if (signal.aborted) {
      controller.abort()
    } else {
      signal.addEventListener('abort', () => controller.abort(), { once: true })
    }
  }

  const requestTask = (async () => {
    const response = await fetch(url, {
      method,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    })

    if (!response.ok) {
      throw new Error(`SSE request failed with status ${response.status}`)
    }

    if (!response.body) {
      throw new Error('SSE response body is empty')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    const parser = createParser({
      onEvent(event: EventSourceMessage) {
        if (!event.data) {
          return
        }

        try {
          const parsed = JSON.parse(event.data) as T
          queue.push(parsed)
          notify()
        } catch (e) {
          console.log(e)
        }
      },
    })

    try {
      while (true) {
        const { done: readDone, value } = await reader.read()
        if (readDone) {
          break
        }

        parser.feed(decoder.decode(value, { stream: true }))
      }

      parser.feed(decoder.decode())
      done = true
      notify()
    } finally {
      reader.releaseLock()
    }
  })().catch((err) => {
    if (!controller.signal.aborted) {
      error = err
      done = true
      notify()
    }
  })

  try {
    while (!done || queue.length > 0) {
      if (queue.length === 0) {
        await waitNext()
      }

      if (error) {
        throw error
      }

      const next = queue.shift()
      if (next) {
        yield next
      }
    }
  } finally {
    controller.abort()
    await requestTask
  }
}
