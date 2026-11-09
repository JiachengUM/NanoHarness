from pydantic import Field

from projects.mind.advisor.mdb_models.doc_base import DomainEntityDocBase
from projects.mind.advisor.domain_data import VisualExterior


class VisualExtDoc(DomainEntityDocBase):
    """外部视觉信息模型"""
    entity: VisualExterior = Field(..., description="外部视觉信息实体")

    class Settings:
        name = "visual_ext"  # MongoDB 集合名称
