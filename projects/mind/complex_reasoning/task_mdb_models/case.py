from beanie import PydanticObjectId
from pydantic import Field
from projects.mind.intent.intent_mdb_models.doc_base import IntentDataDocBase
from projects.mind.complex_reasoning.task_data import ComplexReasoningCase


class ComplexReasoningCaseDoc(ComplexReasoningCase, IntentDataDocBase):
    """复杂推理输入模型。"""

    dataset_id: PydanticObjectId | None = Field(
        default=None, title="数据集Id", description="所属数据集Id"
    )

    class Settings:
        name = "complex_reasoning_case"  # MongoDB 集合名称
