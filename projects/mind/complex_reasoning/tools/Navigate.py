"""
导航工具：对应原 complex_reasoning_agent subagent NavigateAgent。
通过 call_fc(query, chat_id) 请求火山 FC 插件。
"""
import json
import logging
from enum import Enum

from pydantic import BaseModel, Field

from aicore.tools import BaseTool

from projects.mind.complex_reasoning.utils.exception import FcException
from projects.mind.complex_reasoning.utils.plugins import IntentType, call_fc

__all__ = ["NavigateInput", "NavigateTool"]

logger = logging.getLogger(__name__)


class NavigateInput(BaseModel):
    """导航指令。"""
    command: str = Field(
        description="导航任务的自然语言描述，如：导航到北京故宫、添加途径点加油站、避开拥堵"
    )


class NavigateStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class NavigateOutput(BaseModel):
    status: NavigateStatus
    message: str = ""
    observation: dict[str, object] | None = None
    error_msg: str = ""


class NavigateTool(BaseTool):
    """导航工具：目的地导航、途径点等。调用火山 function_call 插件。"""
    name: str = "navigation"
    description: str = "执行导航相关任务：指定目的地导航、添加途径点、路线偏好等。输入为自然语言导航指令。"
    args_schema: type[BaseModel] = NavigateInput
    chat_id: str = Field(..., description="会话 ID，用于请求火山导航插件")

    def _run(self, command: str) -> dict:
        raise NotImplementedError("导航工具请使用异步调用 ainvoke/astream")

    async def _arun(self, command: str) -> NavigateOutput:
        try:
            fc_result = await call_fc(command, self.chat_id, intent_type=IntentType.NAVIGATION)
            if isinstance(fc_result, str) and fc_result.strip().startswith("{"):
                return NavigateOutput(
                    status=NavigateStatus.SUCCESS,
                    message="已执行导航",
                    observation=json.loads(fc_result),
                )
            # 如果有导航fc_result，正常来说是json格式，如果不是，说明失败
            return NavigateOutput(
                status=NavigateStatus.ERROR,
                observation=None,
                message="未获取到导航结果",
            )
        except FcException as e:
            logger.warning("call_fc FcException: %s", e)
            return NavigateOutput(status=NavigateStatus.ERROR, error_msg=str(e))
        except Exception as e:
            logger.exception("call_fc error: %s", e)
            return NavigateOutput(status=NavigateStatus.ERROR, error_msg=str(e))
