from typing import Any, Optional
from pydantic import BaseModel
from projects.mind.advisor.domain_data import VehicleState
from projects.mind.advisor.schemas.base import CreateMixin, DomainEntityOutMixin


class VehicleStateCreate(CreateMixin):
    """车端状态创建"""

    entity: VehicleState


class VehicleStateOut(DomainEntityOutMixin):
    """车端状态输出"""

    entity: Optional[VehicleState] = None


class VehicleStateFilter(BaseModel):
    """查询条件"""

    creator: Optional[str] = None

    def get_filters(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
