"""
导航工具：对应原 complex_reasoning_agent subagent NavigateAgent。
通过 call_fc(query, chat_id) 请求火山 FC 插件。
"""

import json
import logging
from enum import Enum
from typing import Callable, Awaitable

from pydantic import BaseModel, Field

from aicore.tools import create_tool

from projects.mind.complex_reasoning.utils.exception import FcException
from projects.mind.complex_reasoning.utils.plugins import IntentType, call_fc

__all__ = ["NavigateInput", "NavigateTool", "NavigateOutput"]

logger = logging.getLogger(__name__)


class NavigateInput(BaseModel):
    # 导航指令。

    # command: str = Field(description="导航任务的自然语言描述，如：导航到北京故宫、添加途径点加油站、避开拥堵")
    command: str = Field(description="导航任务指令")


class NavigateStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class NavigateOutput(BaseModel):
    status: NavigateStatus
    message: str = ""
    observation: dict[str, object] | None = None
    error_msg: str = ""


async def _navigate_worker(command: str, *, chat_id: str) -> NavigateOutput:
    try:
        fc_result = await call_fc(command, chat_id, intent_type=IntentType.NAVIGATION)
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


class VolcNavigateWorker:
    def __init__(self, chat_id: str):
        self.chat_id = chat_id

    async def __call__(self, command: str) -> NavigateOutput:
        return await _navigate_worker(command, chat_id=self.chat_id)


NavigateWorker = Callable[..., Awaitable[NavigateOutput]]


def NavigateTool(
    chat_id: str, worker: NavigateWorker | None = None, *, timeout: float | None = None
):
    """导航工具：目的地导航、途径点等。调用火山 function_call 插件。"""
    return create_tool(
        name="navigation",
        description="通过导航指令执行导航任务，指定目的地导航、添加途径点、路线偏好. 导航不依赖 navi_point 坐标, 提供明确的目的地即可: 可以是具体地址(如'朝阳区建国路88号')或地标名称(如'北京故宫'), 无需经纬度等严谨坐标参数. 但目的地必须明确, 不能是'最近的加油站''附近的停车场'这类模糊/相对描述. 导航工具只返回成功与否, 不会返回路线详细信息",
        args_schema=NavigateInput,
        worker=worker if worker is not None else VolcNavigateWorker(chat_id),
        timeout=timeout,
    )
