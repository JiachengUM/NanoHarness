// 消息类型
export interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
}
