from beanie import PydanticObjectId
from pydantic import Field
from projects.mind.intent.intent_mdb_models.doc_base import TaskDataDocBase
from projects.mind.intent.task_data.task import IntentTask


class IntentTaskDoc(IntentTask, TaskDataDocBase):
    """Intent task模型"""
    pass

    class Settings:
        name = "intent_task"  # MongoDB 集合名称
