"""
导航工具：对应原 complex_reasoning_agent subagent NavigateAgent。
通过 call_fc(command, chat_id) 请求火山 FC 插件。

入参：从单一 command 字符串改为结构化 NavigationParams（destination / origin / departure_time / route_preference），
LLM 拆解后由 worker 拼成自然语言 command 给 call_fc。
"""
import json
import logging
from enum import Enum
from typing import Callable, Awaitable, Literal, Optional

from pydantic import BaseModel, Field

from aicore.tools import create_tool
from aicore.tools.dag.operator_models import BaseSchema

from projects.mind.complex_reasoning.utils.exception import FcException
from projects.mind.complex_reasoning.utils.plugins import IntentType, call_fc

__all__ = ["NavigateTool", "NavigateOutput", "NavigateInput"]

logger = logging.getLogger(__name__)


# 路线偏好英文 → 中文（拼接 command 时用，FC 插件偏自然语言）
_ROUTE_PREF_ZH: dict[str, str] = {
    "fastest": "最快",
    "shortest": "最短",
    "economical": "经济",
    "scenic": "风景",
}


class NavigateInput(BaseSchema):
    """导航参数 - 原子能力：路线规划与导航"""

    destination: str = Field(description="目的地")

    # 可选字段
    origin: Optional[str] = Field(
        default=None,
        description="出发地，默认使用当前位置"
    )

    departure_time: Optional[str] = Field(
        default=None,
        description="期望出发时间，格式: HH:MM"
    )

    # 路线偏好
    route_preference: Optional[Literal["fastest", "shortest", "economical", "scenic"]] = Field(
        default=None,
        description="路线偏好: fastest(最快), shortest(最短)"
    )


class NavigateStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class NavigateOutput(BaseModel):
    status: NavigateStatus
    message: str = ""
    observation: dict[str, object] | None = None
    error_msg: str = ""


def _build_navigation_command(
    *,
    destination: str = "",
    origin: Optional[str] = None,
    departure_time: Optional[str] = None,
    route_preference: Optional[str] = None,
) -> str:
    """把结构化导航参数拼成自然语言 command，给 call_fc 使用。

    拼接顺序：目的地 → 出发地 → 期望出发时间 → 路线偏好；空字段自动跳过。
    全空时兜底返回 "导航"（FC 插件仍能识别为导航意图）。
    """
    parts: list[str] = []
    if destination:
        parts.append(f"导航到{destination}")
    if origin:
        parts.append(f"从{origin}出发")
    if departure_time:
        parts.append(f"期望{departure_time}出发")
    if route_preference:
        pref_zh = _ROUTE_PREF_ZH.get(route_preference, route_preference)
        parts.append(f"走{pref_zh}路线")
    if not parts:
        return "导航"
    return "，".join(parts) + "。"


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

    async def __call__(
        self,
        *,
        destination: str = "",
        origin: Optional[str] = None,
        departure_time: Optional[str] = None,
        route_preference: Optional[str] = None,
    ) -> NavigateOutput:
        command = _build_navigation_command(
            destination=destination,
            origin=origin,
            departure_time=departure_time,
            route_preference=route_preference,
        )
        return await _navigate_worker(command, chat_id=self.chat_id)


NavigateWorker = Callable[..., Awaitable[NavigateOutput]]


def NavigateTool(chat_id: str, worker: NavigateWorker | None = None, *, timeout: float | None = None):
    """导航工具：路线规划与导航执行（目的地、出发地、出发时间、路线偏好）。"""
    return create_tool(
        name="Navigation",
        description=(
            "导航工具：路线规划与导航执行（目的地、出发地、出发时间、路线偏好）。"
            "输出：导航执行状态"
        ),
        args_schema=NavigateInput,
        worker=worker if worker is not None else VolcNavigateWorker(chat_id),
        timeout=timeout,
    )
