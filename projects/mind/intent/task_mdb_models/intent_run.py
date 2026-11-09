from projects.mind.intent.intent_mdb_models.doc_base import TaskDataDocBase
from projects.mind.intent.task_data.intent_run import IntentRun


class IntentRunDoc(IntentRun, TaskDataDocBase):
    """意图分类运行模型"""
    pass

    class Settings:
        name = "intent_run"  # MongoDB 集合名称
