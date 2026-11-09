import { generateId } from '@eval-platform/shared'

export interface HistoryItem {
  role: string
  content: string | Record<string, unknown>
  [key: string]: unknown
}

/**
 * AgentAdaptor 是一个抽象类，定义了智能Agent适配器的基本接口和功能。它包含以下主要成员：
- `sessionId`: 用于标识当前会话的唯一ID。
- `history`: 用于存储会话历史记录的数组，每条记录包含角色（如用户或助手）和内容。
- `chat(content: string | Record<string, unknown>, role?: string)`: 抽象方法，子类需要实现该方法来处理输入内容并更新历史记录。
- `newSession()`: 方法，用于开始一个新的会话，生成新的sessionId并清空历史记录。
- `getHistory()`: 方法，返回当前会话的历史记录。
- `getSessionId()`: 方法，返回当前会话的sessionId。
- `addHistory(role: string, content: string | Record<string, unknown>)`: 受保护的方法，用于向历史记录中添加一条新记录。

AgentAdaptor 的设计使得不同类型的智能Agent适配器可以继承该类，并实现具体的聊天逻辑
 */
abstract class AgentAdaptor {
  private sessionId: string
  protected history: HistoryItem[]

  constructor() {
    this.sessionId = generateId()
    this.history = []
  }

  abstract invoke(input: string): Promise<HistoryItem[]>

  newSession() {
    this.sessionId = generateId()
    this.history = []
  }

  getHistory() {
    return this.history
  }

  getMessages() {
    return this.history.filter((item) => item.role === 'user' || item.role === 'assistant')
  }

  getSessionId() {
    return this.sessionId
  }

  protected addHistory(role: string, content: HistoryItem['content']): void
  protected addHistory(item: HistoryItem): void
  protected addHistory(roleOrItem: string | HistoryItem, content?: HistoryItem['content']): void {
    if (typeof roleOrItem === 'string') {
      this.history.push({
        role: roleOrItem,
        content: content as HistoryItem['content'],
      })
    } else {
      this.history.push(roleOrItem)
    }
  }
}

export default AgentAdaptor
