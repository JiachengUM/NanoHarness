from pydantic import Field

from projects.mind.advisor.mdb_models.doc_base import DomainEntityDocBase
from projects.mind.advisor.domain_data import WorldInfo


class WorldInfoDoc(DomainEntityDocBase):
    """世界信息模型"""
    entity: WorldInfo = Field(..., description="世界信息实体")

    class Settings:
        name = "world_info"  # MongoDB 集合名称
