from projects.mind.intent.intent_mdb_models.doc_base import TaskDataDocBase
from projects.mind.complex_reasoning.task_data.dataset import (
    ComplexReasoningDatasetMeta,
)


class ComplexReasoningDatasetDoc(ComplexReasoningDatasetMeta, TaskDataDocBase):
    """复杂推理数据集模型"""

    class Settings:
        name = "complex_reasoning_dataset"  # MongoDB 集合名称
