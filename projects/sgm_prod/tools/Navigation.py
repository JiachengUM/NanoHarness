import json
import logging

from pydantic import BaseModel, Field

from aicore.tools import create_tool
from projects.sgm_prod.function_call import IntentType, call_fc

__all__ = ["NavigationInput", "NavigationOutput", "NavigationWorker", "create_navigation_tool"]

logger = logging.getLogger(__name__)


class NavigationInput(BaseModel):
    # 导航控制指令。
    command: str = Field(description="导航任务的自然语言描述，如：导航到虹桥火车站、添加途经点加油站、取消导航")


class NavigationOutput(BaseModel):
    status: str
    message: str = ""
    observation: dict[str, object] | None = None


class NavigationWorker:
    """导航 worker，封装 chat_id 并提供 async __call__。"""

    def __init__(self, chat_id: str):
        self.chat_id = chat_id

    async def _run(self, command: str) -> NavigationOutput:
        fc_result = await call_fc(command, self.chat_id, intent_type=IntentType.NAVIGATION)
        if fc_result.strip().startswith("{"):
            return NavigationOutput(
                status="success",
                message="已执行导航",
                observation=json.loads(fc_result),
            )
        return NavigationOutput(status="error", message="未获取到导航结果")

    async def __call__(self, command: str) -> NavigationOutput:
        return await self._run(command)


def create_navigation_tool(chat_id: str):
    """导航工具工厂：目的地导航、取消导航、路线调整等。"""
    return create_tool(
        name="navigation",
        description="执行导航相关任务，如开始导航、取消导航、添加途经点、调整路线偏好。",
        args_schema=NavigationInput,
        worker=NavigationWorker(chat_id),
    )
