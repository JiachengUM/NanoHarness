from pydantic import Field

from projects.mind.advisor.mdb_models.doc_base import DomainEntityDocBase
from projects.mind.advisor.domain_data import VisualInterior


class VisualIntDoc(DomainEntityDocBase):
    """内部视觉信息模型"""
    entity: VisualInterior = Field(..., description="内部视觉信息实体")

    class Settings:
        name = "visual_int"  # MongoDB 集合名称
