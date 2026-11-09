interface AgentRequest {
  query?: string
  config?: AgentConfig
}

interface AgentConfig extends AnyObject {
  model?: string
  params?: AgentResponseParams
  tools?: string[]
  max_turns?: number
  system_prompt?: string | SystemPrompt
  memory_config_type?: 'user_profile' | 'memory_config'
  memory_config?: MemoryConfig
  user_profile?: UserProfile
}

interface MemoryConfig {
  user_info?: UserInfoMeta
  producer_config?: ProducerConfig
  consumer_config?: ConsumerConfig
  session_size?: number
}

interface ProducerConfig {
  collection_id: CollectionId
  memory_type: string[]
}

interface ConsumerConfig {
  collection_id: CollectionId
  profile_types?: string[] // 已失效，删除
  system_prompt_profile_types?: string[]
  search_profile_types?: string[]
  event_types?: string[]
  event_limit?: number
  profile_limit?: number
}

interface CollectionId {
  collection_name?: string
  project_name?: string
  resource_id?: string
}

interface UserInfoMeta {
  user_id: string
  user_name?: string
  assistant_id: string
  assistant_name?: string
  group_id?: string
}

interface UserProfile {
  user_type: string
  personal_status?: string[]
  residence?: string
  career_identity?: string[]
  daily_behavior?: string[]
  personality_traits?: string[]
  interests_hobbies?: string[]
  travel_pattern?: string[]
  vehicle_usage?: string[]
  media_preference?: string[]
}

interface SystemPrompt extends AnyObject {
  role: string // 角色提示词
  guidelines: string[] // 提示词指令
}

interface AgentResponseParams {
  temperature?: number
  top_p?: number
  thinking?: string // "enabled", "disabled", "auto"
  extra?: Record<string, unknown> // 额外参数
}

interface Thinking {
  type: string // "enabled", "disabled", "auto"
}

interface Caching {
  type: string // "enabled", "disabled"
  prefix?: boolean
}

interface AgentResponse {
  type: string
  content: AgentResult
}

interface AgentResult {
  event_id: string
  round: number
  type: string
  timestamp: string

  name?: string
  arguments?: object

  output?: object
  tool_results?: string[]

  delta?: string
  text?: string
  content?: string

  forced?: boolean
  response?: object
  reason?: string
}

interface AgentMemoryResponse extends Common {
  profiles?: ProfileMemory
  events?: EventMemory
}

interface ProfileMemory {
  data: ProfileMemoryData
}

interface ProfileMemoryData {
  collection_name: string
  count: number
  result_list: ProfileMemoryResult[]
  token_usage: number
}

interface ProfileMemoryResult {
  id: string
  score?: number
  memory_type: string
  user_id: string[]
  assistant_id: string[]
  group_id?: string
  time: number
  status?: string
  labels?: string
  memory_info: Record<string, MemoryContentType>
}

interface EventMemory {
  data: EventMemoryData
}

interface EventMemoryData {
  collection_name: string
  count: number
  result_list: EventMemoryResult[]
  token_usage: number
}

interface EventMemoryResult {
  id: string
  score?: number
  memory_type: string
  user_id: string[]
  assistant_id: string[]
  group_id?: string
  time: number
  status?: string
  labels?: string
  memory_info: Record<string, MemoryContentType>
  session_id: string
  origin_score?: number
  time_score?: number
  custom_weight_score?: number
}

type MemoryContentType = string | string[] | number | number[] | boolean | null
