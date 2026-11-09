from pydantic import Field

from projects.mind.advisor.domain_data import VehicleState
from projects.mind.advisor.mdb_models.doc_base import DomainEntityDocBase


class VehicleStateDoc(DomainEntityDocBase):
    """车端状态"""

    entity: VehicleState = Field(..., description="车端状态实体")

    class Settings:
        name = "vehicle_state"  # MongoDB 集合名称
