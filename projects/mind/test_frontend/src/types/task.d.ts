interface Task extends Common {
  name?: string
  description?: string
  dataset_id?: string
  config?: AgentInstanceDump
  metadata?: Record<string, unknown>
}

interface TaskProgress {
  total?: number
  completed?: number
  success?: number
  failed?: number
  percent?: number
}

interface TaskRun extends Common {
  task_id?: string
  task?: Task
  status?: string
  progress?: TaskProgress
  metadata?: Record<string, unknown> & { ai_report?: string }
}

interface Metric {
  name?: string
  value?: number
  comment?: string
}

interface Evaluation {
  is_pass?: boolean
  score?: number | null
  comment?: string
  metrics?: Metric[] | null
}

interface TaskRunItemEval extends Common {
  task_run_item_id?: string
  llm_evaluation?: Evaluation | null
  human_evaluation?: Evaluation | null
}

interface RunEvent {
  type?: string
  event_id?: string
  round?: number
  timestamp?: string
  [key: string]: unknown
}

interface TaskRunMessage extends Common {
  task_run_item_id?: string
  session_id?: string
  role?: 'user' | 'assistant' | string
  content?: string
  traces?: RunEvent[] | null
  metadata?: Record<string, unknown>
}

interface TaskRunItem extends Common {
  task_run_id?: string
  dataset_item_id?: string
  status?: string
  metadata?: Record<string, unknown>
  eval?: TaskRunItemEval | null
  messages?: TaskRunMessage[]
}
