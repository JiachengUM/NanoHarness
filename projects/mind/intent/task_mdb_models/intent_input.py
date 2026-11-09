from beanie import PydanticObjectId
from pydantic import Field
from projects.mind.intent.intent_mdb_models.doc_base import IntentDataDocBase
from projects.mind.intent.task_data import IntentClsInput


class IntentInputDoc(IntentClsInput, IntentDataDocBase):
    """意图输入模型。"""
    dataset_id: PydanticObjectId | None = Field(default=None, title="数据集Id", description="所属数据集Id")

    class Settings:
        name = "intent_input"  # MongoDB 集合名称
