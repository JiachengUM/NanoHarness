from enum import StrEnum


class TaskRunStatus(StrEnum):
  PENDING = 'pending'
  RUNNING = 'running'
  PAUSED = 'paused'  # 用户暂停 / WS 断连（可恢复）
  COMPLETED = 'completed'
  FAILED = 'failed'
  REPORTING = 'reporting'

class TaskRunItemStatus(StrEnum):
  PENDING = 'pending'
  RUNNING = 'running'
  EVALUATING = 'evaluating'
  COMPLETED = 'completed'
  FAILED = 'failed'
  SKIPPED = 'skipped'

class AgentType(StrEnum):
    BASE_AGENT = "BaseAgent"
    SGM_AGENT = "SGMAgent"
    AGENT_V1 = "AgentV1"
    INTENT_AGENT = "IntentAgent"
    S2S_AGENT = "S2SAgent"