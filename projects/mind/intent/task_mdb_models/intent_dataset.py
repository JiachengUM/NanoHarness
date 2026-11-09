from projects.mind.intent.intent_mdb_models.doc_base import TaskDataDocBase
from projects.mind.intent.task_data.intent_dataset import IntentDatasetMeta


class IntentDatasetDoc(IntentDatasetMeta, TaskDataDocBase):
    """Intent数据集模型"""

    class Settings:
        name = "intent_dataset"  # MongoDB 集合名称
