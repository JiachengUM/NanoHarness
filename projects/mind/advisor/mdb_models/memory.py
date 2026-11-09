from pydantic import Field

from projects.mind.advisor.mdb_models.doc_base import DomainEntityDocBase
from projects.mind.advisor.domain_data import EpisodicMemory


class EpisodicMemoryDoc(DomainEntityDocBase):
    """用户记忆模型"""
    entity: EpisodicMemory = Field(..., description="记忆实体")

    class Settings:
        name = "memory"  # MongoDB 集合名称
