"""对外公开所有的任务数据schema。"""

from projects.mind.intent.task_data.input import IntentClsInput
from projects.mind.intent.task_data.output import IntentClsOutput, IntentClsRunTrajectory
from projects.mind.intent.task_data.param import IntentClsPrompt, IntentClsParam, LLMParam


__all__ = [
    "IntentClsInput",
    "IntentClsPrompt",
    "LLMParam",
    "IntentClsParam",
    "IntentClsOutput",
    "IntentClsRunTrajectory",
]
