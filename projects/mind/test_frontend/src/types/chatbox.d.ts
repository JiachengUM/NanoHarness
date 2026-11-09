interface AgentInstanceDump {
  tools_names?: string[]
  system_prompt?: string | SystemPrompt
  run_params?: {
    model?: string
    max_turns?: number
    params?: AgentResponseParams
  }
  memory?: {
    user_info?: UserInfoMeta
    producer?: {
      config?: ProducerConfig
      session_size?: number
    }
    consumer?: {
      config?: ConsumerConfig
    }
  }
  user_profile?: UserProfile
}

interface AgentContext {
  system_prompt?: string | SystemPrompt
  model_params?: {
    model?: string
    params?: AgentResponseParams
  }
  react_max_turns?: number
  tools_names?: string[]
  memory_user_info?: UserInfoMeta
  memory_producer_config?: ProducerConfig
  memory_producer_session_size?: number
  memory_consumer_config?: ConsumerConfig
  user_profile?: UserProfile
}

interface AgentState {
  trace?: any[]
}

interface AgentV1Dump {
  context: AgentContext
  state: AgentState
}

interface ChatSession extends Common {
  session_id?: string
  title?: string
  agent_instance_dump?: AgentV1Dump
  messages?: ChatMessage[]
}

interface ChatMessage extends Common {
  type?: string // 消息角色，humain-用户，ai-助手
  content?: string // 消息内容
  events?: AgentResult[] // 消息事件列表
  trace?: AgentResult[] // TODO: 弃用，后面删掉（使用events代替）
  status?: string // 消息状态，pending-等待中，answering-回答中，complete-完成，stop-已停止
  human_evaluation?: EvaluationResult // 消息人工评价
}

interface EvaluationResult extends Common {
  overall_score?: number
  overall_reason?: string
  metrics?: ChatMetric[]
}

interface ChatMetric {
  metric_name?: string
  score?: number
  reason?: string
}

interface ChatRequest {
  message: string // 消息内容
}

interface EvaluationForm {
  id?: string
  message_index?: number
  human_evaluation?: EvaluationResult
}

interface AutoChatConfig extends Common {
  query?: string
  chat_turns?: number
  user_profile?: string
  chat_scene?: string
}
