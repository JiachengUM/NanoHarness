import json
import logging

from pydantic import BaseModel, Field

from aicore.tools import create_tool
from projects.sgm_prod.function_call import IntentType, call_fc

__all__ = ["CarControlInput", "CarControlOutput", "CarControlWorker", "create_car_control_tool"]

logger = logging.getLogger(__name__)


class CarControlInput(BaseModel):
    # 车控指令参数。
    command: str = Field(description="车控指令的自然语言描述，如：空调调到18度凉爽模式、打开座椅按摩、关闭所有车窗")


class CarControlOutput(BaseModel):
    status: str
    message: str = ""
    observation: dict[str, object] | None = None


class CarControlWorker:
    """车控 worker，封装 chat_id 并提供 async __call__。"""

    def __init__(self, chat_id: str):
        self.chat_id = chat_id

    async def _run(self, command: str) -> CarControlOutput:
        fc_result = await call_fc(command, self.chat_id, intent_type=IntentType.VEHICLE_CONTROL)
        if fc_result.strip().startswith("{"):
            return CarControlOutput(
                status="success",
                message="已执行车控",
                observation=json.loads(fc_result),
            )
        return CarControlOutput(status="error", message="未获取到车控结果")

    async def __call__(self, command: str) -> CarControlOutput:
        return await self._run(command)


def create_car_control_tool(chat_id: str):
    """车控工具工厂：空调、座椅、车窗、灯光等。"""
    return create_tool(
        name="car_control",
        description="执行车载设备控制，包括：空调（温度、风量、模式）、座椅（位置、按摩、加热、通风）、车窗/天窗/车门、灯光（氛围灯、阅读灯、远近光）等。输入为自然语言车控指令。",
        args_schema=CarControlInput,
        worker=CarControlWorker(chat_id),
    )
