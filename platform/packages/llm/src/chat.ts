import OpenAI from 'openai'
import { Message } from './types'
import { invoke, stream } from './responses'
import { createClient } from './client'

export interface ChatOptions {
  systemPrompt?: string
  client?: OpenAI
}

/**
 * Chat类封装了与LLM进行多轮对话的逻辑，支持发送消息、获取响应、处理流式响应以及维护对话历史。
 * 通过使用Chat类，用户可以更方便地与LLM进行交互，并且能够保持对话的上下文连续性。
 */
export class Chat {
  private client: OpenAI
  private systemPrompt: string
  private messages: Message[] = []
  private previousResponseId?: string

  constructor({ systemPrompt = '你是一个智能助手', client = createClient() }: ChatOptions = {}) {
    this.systemPrompt = systemPrompt
    this.client = client || createClient()
  }

  // 发送消息并获取响应
  async invoke(query: string): Promise<string> {
    this.addMessage({ role: 'user', content: query })

    // 如果是对话的第一轮，发送systemPrompt；否则不发送，以保持上下文连续
    const systemPrompt = this.previousResponseId ? undefined : this.systemPrompt

    const response = await invoke(this.client, {
      instructions: systemPrompt,
      input: query,
      previous_response_id: this.previousResponseId,
    })

    return this.handleResponse(response)
  }

  // 发送消息并获取流式响应
  async *stream(query: string): AsyncIterable<string> {
    this.addMessage({ role: 'user', content: query })

    const systemPrompt = this.previousResponseId ? undefined : this.systemPrompt

    const events = await stream(this.client, {
      instructions: systemPrompt,
      input: query,
      previous_response_id: this.previousResponseId,
    })

    yield* this.handleResponseStream(events)
  }

  // 处理响应
  private async handleResponse(response: OpenAI.Responses.Response): Promise<string> {
    const outputText = response.output_text || ''
    this.previousResponseId = response.id

    this.addMessage({ role: 'assistant', content: outputText })

    return outputText
  }

  // 处理流式响应
  private async *handleResponseStream(
    events: AsyncIterable<OpenAI.Responses.ResponseStreamEvent>,
  ): AsyncIterable<string> {
    let content = ''

    for await (const event of events) {
      switch (event.type) {
        case 'response.output_text.delta':
          // 处理文本增量更新
          yield event.delta
          break
        case 'response.output_text.done':
          // 处理文本完成事件
          content = event.text
          break
        case 'response.completed':
          // 处理响应完成事件
          this.previousResponseId = event.response.id
          break
        default:
          // 其他类型的事件可以根据需要处理
          break
      }
    }

    this.addMessage({ role: 'assistant', content })
  }

  // 添加消息
  private addMessage(message: Message) {
    this.messages.push(message)
  }

  // 获取对话历史
  getHistory(): readonly Message[] {
    return [...this.messages]
  }

  // 开始新一轮对话，清空历史和previousResponseId
  newSession() {
    this.messages = []
    this.previousResponseId = undefined
  }
}
