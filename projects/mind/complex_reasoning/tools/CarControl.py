"""
车控工具：对应原 complex_reasoning_agent 中 subagent CarControlAgent。
通过 call_fc(query, chat_id) 请求火山 FC 插件，chat_id 必填。
"""
import json
import logging
from enum import Enum

from pydantic import BaseModel, Field

from aicore.tools import BaseTool

from projects.mind.complex_reasoning.utils.exception import FcException
from projects.mind.complex_reasoning.utils.plugins import IntentType, call_fc

__all__ = ["CarControlInput", "CarControlTool"]

logger = logging.getLogger(__name__)


class CarControlInput(BaseModel):
    """车控指令参数。与原 car_control_agent 的 param（自然语言指令）一致。"""
    command: str = Field(description="车控指令的自然语言描述，如：空调调到18度凉爽模式、打开座椅按摩、关闭所有车窗")


class CarControlStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class CarControlOutput(BaseModel):
    status: CarControlStatus
    message: str = ""
    observation: dict[str, object] | None = None
    error_msg: str = ""


class CarControlTool(BaseTool):
    """
    车控工具：空调、座椅、车窗、灯光等。调用火山 function_call 插件。
    """
    name: str = "car_control"

    description: str = ("执行车载设备控制，包括：空调（温度、风量、模式）、座椅（位置、按摩、加热、通风）、车窗/天窗/车门、灯光（氛围灯、阅读灯、远近光）等。输入为自然语言车控指令。")
    
    args_schema: type[BaseModel] = CarControlInput
    
    chat_id: str = Field(..., description="会话 ID，用于请求火山车控服务")

    def _run(self, command: str) -> dict:
        """同步路径不支持，请使用 ainvoke/astream。"""
        raise NotImplementedError("车控请使用异步调用 ainvoke/astream")

    async def _arun(self, command: str) -> CarControlOutput:
        try:
            fc_result = await call_fc(command, self.chat_id, intent_type=IntentType.VEHICLE_CONTROL)
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
