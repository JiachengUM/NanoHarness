from typing import Any, Optional

from pydantic import BaseModel
from projects.mind.advisor.domain_data import UserBase
from projects.mind.advisor.schemas.base import CreateMixin, DomainEntityOutMixin


class UserCreate(CreateMixin):
    """用户创建"""

    entity: UserBase


class UserOut(DomainEntityOutMixin):
    """用户输出"""

    entity: Optional[UserBase] = None


class UserFilter(BaseModel):
    """用户查询条件"""

    name: Optional[str] = None
    creator: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
