from pydantic import Field

from projects.mind.advisor.mdb_models.doc_base import DomainEntityDocBase
from projects.mind.advisor.domain_data import UserBase


class UserDoc(DomainEntityDocBase):
    """用户模型"""
    entity: UserBase = Field(..., description="用户实体")

    class Settings:
        name = "users"  # MongoDB 集合名称
