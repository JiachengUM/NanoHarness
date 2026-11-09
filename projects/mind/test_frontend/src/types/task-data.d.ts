// ==================== Advisor Context ====================
interface AdvisorContext {
  user?: string | User // 用户画像
  memory?: string | EpisodicMemory // 记忆信息
  vehicle_state?: string | VehicleState // 车辆状态
  visual_exterior?: string | VisualExterior // 外部视觉信息
  visual_interior?: string | VisualInterior // 内部视觉信息
  world_info?: string | WorldInfo // 世界信息
}

// ==================== Advisor Dataset ====================
interface Dataset extends Common {
  name?: string // 数据集名称
  description?: string // 数据集描述
}

// ==================== Advisor Input ====================
interface AdvisorInput extends Common {
  dataset_id?: string // 数据集ID
  brief?: string // 摘要信息
  event?: string // 事件
  context?: AdvisorContext // 工作环境上下文
}

// ==================== Advisor Run ====================
interface Metric {
  name?: string
  value?: number
  comment?: string
}

interface ManualEvaluation {
  score?: number
  comment?: string
  metrics?: Metric[]
}

interface AdvisorOutput {
  advice?: string //
  reason?: string
  think?: string
}

// advisor输出信息模型
interface AdvisorRun extends Common {
  brief?: string
  advise_type?: string
  input?: AdvisorInput
  output?: AdvisorOutput
  manual_evaluation?: ManualEvaluation
}

// ==================== Intent Params ====================
interface LLMParam {
  model?: string // 模型名称
  temperature?: number // 采样温度
  top_p?: number // nucleus采样
}

interface IntentClsPrompt {
  categories?: Category[] | string[] // 意图分类列表
  expert_role?: string // 专家角色
  output_hint?: string // 输出提示
}

interface IntentParams {
  prompt?: IntentClsPrompt
  llm_param: LLMParam
}

// ==================== Intent Input ====================
interface Message {
  role: string // 角色
  content: string // 内容
}

interface IntentInput extends Common {
  dataset_id?: string // 数据集ID
  query?: string // 意图分类查询
  messages?: Message[] // 历史对话
}

// ==================== Intent Run ====================
interface IntentOutput {
  intent_type?: string // 识别意图
  reason?: string // 识别原因
}

interface IntentClsRunTrajectory {
  sys_prompt?: string
  user_prompt?: string
}

interface IntentRun extends Common {
  input?: IntentInput
  output?: IntentOutput
  param?: IntentParams
  trajectory?: IntentClsRunTrajectory
  total_time?: number // 总耗时，单位毫秒
  manual_evaluation?: ManualEvaluation
}

// ==================== Complex Reasoning Dataset ====================
interface ComplexReasoningDataset extends Common {
  name?: string // 数据集名称
  description?: string // 数据集描述
  item_count?: number // 数据集包含的测试用例数量
}

// ==================== Complex Reasoning Input ====================

interface DialogueRoundConfig {
  user_query_list: Message[] // 每轮对话的消息列表，包含系统和用户的消息
  mock_info?: Record<string, unknown> // 每轮对话的mock信息，结构为json
  mock_time?: string // YYYY-MM-DD HH:mm:ss
}
interface ComplexReasoningCase extends Common {
  dataset_id?: string // 数据集ID
  case_id?: string // 用例ID
  context_config?: object // 上下文配置，结构不固定
  max_round?: number // 最大对话轮数
  user_query_lists?: (Message[] | DialogueRoundConfig)[] // 多轮对话列表，每个元素是一轮对话，包含系统和用户的消息列表
  expected_script?: string // 期望的推理脚本
  nl_assertion?: string[] // 自然语言断言，用于评估推理结果的正确性
  code_assertion?: Record<string, unknown> // 代码断言，用于评估推理结果的正确性
  case_description?: string // 测试用例描述
  tags?: string[] // 测试用例标签
}

interface DatasetBuildParams extends AnyObject {
  dataset?: Dataset
  dataset_id?: string
  dataset_item_ids?: string[] // 选择的数据集Item Id列表
  task_run_item_ids?: string[] // 选择的任务运行Item Id列表
  dataset_items?: ComplexReasoningCase[] // 选择的数据集Item列表
}
