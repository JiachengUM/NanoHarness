from beanie import PydanticObjectId
from pydantic import Field
from projects.mind.intent.intent_mdb_models.doc_base import TaskDataDocBase
from projects.mind.intent.task_data.result import IntentResult


class IntentResultDoc(IntentResult, TaskDataDocBase):
    """Intent result模型"""
    pass

    class Settings:
        name = "intent_result"  # MongoDB 集合名称
