"""
车控工具：对应原 complex_reasoning_agent 中 subagent CarControlAgent。
通过 call_fc(query, chat_id) 请求火山 FC 插件，chat_id 必填。
"""
import json
import logging
from enum import Enum
from typing import Callable, Awaitable

from pydantic import BaseModel, Field

from aicore.tools import create_tool

from projects.mind.complex_reasoning.utils.exception import FcException
from projects.mind.complex_reasoning.utils.plugins import IntentType, call_fc

__all__ = ["CarControlInput", "CarControlTool","CarControlOutput"]

logger = logging.getLogger(__name__)


class CarControlInput(BaseModel):
    # 车控指令参数。与原 car_control_agent 的 param（自然语言指令）一致。
    
    # command: str = Field(description="车控指令的自然语言描述，如：空调调到18度凉爽模式、打开座椅按摩、关闭所有车窗")
    command: str = Field(description="车控指令描述")


class CarControlStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class CarControlOutput(BaseModel):
    status: CarControlStatus
    message: str = ""
    observation: dict[str, object] | None = None
    error_msg: str = ""


async def _car_control_worker(command: str, *, chat_id: str) -> CarControlOutput:
    try:
        fc_result = await call_fc(command, chat_id, intent_type=IntentType.VEHICLE_CONTROL)
        if isinstance(fc_result, str) and fc_result.strip().startswith("{"):
            return CarControlOutput(
                status=CarControlStatus.SUCCESS,
                message="已执行车控",
                observation=json.loads(fc_result),
            )
        # 如果有车控fc_result，正常来说是json格式，如果不是，说明失败
        return CarControlOutput(
            status=CarControlStatus.ERROR,
            observation=None,
            message="未获取到车控结果",
        )
    except FcException as e:
        logger.warning("call_fc FcException: %s", e)
        return CarControlOutput(status=CarControlStatus.ERROR, error_msg=str(e))
    except Exception as e:
        logger.exception("call_fc error: %s", e)
        return CarControlOutput(status=CarControlStatus.ERROR, error_msg=str(e))


class VolcCarControlWorker:
    def __init__(self, chat_id: str):
        self.chat_id = chat_id

    async def __call__(self, command: str) -> CarControlOutput:
        return await _car_control_worker(command, chat_id=self.chat_id)


CarControlWorker = Callable[..., Awaitable[CarControlOutput]]


def CarControlTool(chat_id: str, worker: CarControlWorker | None = None, *, timeout: float | None = None):
    """车控工具：空调、座椅、车窗、灯光等。调用火山 function_call 插件。"""
    return create_tool(
        name="car_control",
        description="车控指令执行",
        args_schema=CarControlInput,
        worker=worker if worker is not None else VolcCarControlWorker(chat_id),
        timeout=timeout,
    )
