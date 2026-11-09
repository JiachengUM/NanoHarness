from projects.mind.advisor.task_data import AdvisorDatasetMeta
from projects.mind.advisor.mdb_models.doc_base import TaskDataDocBase


class AdvisorDatasetDoc(AdvisorDatasetMeta, TaskDataDocBase):
    """advisor数据集模型"""

    class Settings:
        name = "advisor_dataset"  # MongoDB 集合名称