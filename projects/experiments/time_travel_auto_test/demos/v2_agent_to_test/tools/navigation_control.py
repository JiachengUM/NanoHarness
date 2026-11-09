"""虚拟车导航工具（复用真实导航核心 + 结果落虚拟车）。

复用真实导航核心 VolcNavigateWorker（projects.mind.toolset.navigate，
生产端点 call_fc(intent_type=NAVIGATION)），
调用火山 FC 插件拿到结构化 function_code + params，再把结果映射到虚拟车导航状态：
- 开始导航（function_code ∈ {单目的地导航, 多目的地导航}）→ 提取 params 中 destination
  → VirtualCar.set_field("导航目的地" / "导航状态") 落盘
- 取消导航 → 清空虚拟车导航状态
- 查询 → 返回当前虚拟车导航状态（不改状态）

结果统一走 VirtualCar.set_field（devices 是唯一真相源，on_field_change → 可视化事件）。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from aicore.runtime.task import TaskManager
from aicore.v2.tools.factory import create_tool
from projects.mind.toolset.navigate import NavigateOutput, VolcNavigateWorker

if TYPE_CHECKING:
    from projects.experiments.time_travel_auto_test.virtual_car.models import VirtualCar

__all__ = [
    "NavigationControlInput",
    "NavigationControlOutput",
    "NavigationControlTool",
    "NavigationController",
]

logger = logging.getLogger(__name__)

# 开始导航的 function_code（复用 sgm_prod 导航能力边界）
_NAV_START_CODES = frozenset({"单目的地导航", "多目的地导航"})
# 取消导航的指令关键词（FC 无独立"取消导航"function_code，走"导航操作"，故按指令语义兜底）
_CANCEL_KEYWORDS = ("取消", "停止", "结束", "退出", "关闭", "别导", "不用导")
# FC params 中目的地字段候选键（不同 FC 版本 key 存在差异，做兜底）
_DEST_PARAM_KEYS = ("destination", "nav_dest_name", "dest_name", "目的地", "地点")


class NavigationControlInput(BaseModel):
    """虚拟车导航指令参数"""

    command: str = Field(
        description=(
            "导航指令的自然语言描述。\n"
            "支持：\n"
            "- 开始导航：导航到XX / 导航去XX / 带我去XX / 去XX（目的地为具体地点名称）\n"
            "- 取消导航：取消导航 / 停止导航 / 退出导航 / 关闭导航\n"
            "- 查询状态：现在导航到哪了 / 导航状态 / 还有多久到"
        )
    )


class NavigationControlOutput(BaseModel):
    """虚拟车导航执行结果"""

    status: str = Field(description="执行状态: success / error")
    message: str = Field(description="执行结果描述")
    observation: dict | None = Field(default=None, description="变更后/当前的导航状态")


_NavigationWorkerType = Callable[[str], Awaitable[NavigateOutput]]


def _extract_function_codes(observation: dict | None) -> list[str]:
    if not observation:
        return []
    codes: list[str] = []
    for item in observation.get("functions", []):
        if isinstance(item, dict) and isinstance(item.get("function_code"), str):
            codes.append(item["function_code"])
    return codes


def _extract_destination(observation: dict | None) -> str:
    """从 FC 返回的 functions 中提取导航目的地（仅开始导航的 function_code）。"""
    if not observation:
        return ""
    for item in observation.get("functions", []):
        if not isinstance(item, dict):
            continue
        if item.get("function_code") not in _NAV_START_CODES:
            continue
        for param in item.get("params", []):
            if not isinstance(param, dict):
                continue
            for key in _DEST_PARAM_KEYS:
                value = param.get(key)
                if isinstance(value, str) and value.strip() and value.strip() != "空":
                    return value.strip()
    return ""


class NavigationController:
    """虚拟车导航控制器：复用真实导航核心 → 解析结果 → set_field 落虚拟车。"""

    def __init__(
        self,
        virtual_car: VirtualCar,
        *,
        worker: _NavigationWorkerType | None = None,
        chat_id: str = "time-travel-demo",
    ) -> None:
        self.car = virtual_car
        self.worker = worker or VolcNavigateWorker(chat_id)

    async def execute(self, command: str) -> NavigationControlOutput:
        """执行导航指令：先走真实导航核心，再把结果映射到虚拟车状态。"""
        if not command or not command.strip():
            return NavigationControlOutput(status="error", message="指令为空")

        cmd = command.strip()
        logger.info("执行导航指令: %s", cmd)

        try:
            result = await self.worker(cmd)
        except Exception as e:  # 真实 FC 为外部网络调用，异常统一收敛为工具 error
            logger.exception("导航 worker 执行异常: %s", e)
            return NavigationControlOutput(status="error", message=f"导航服务异常: {e}")

        if getattr(result, "status", "") != "success" or not result.observation:
            return NavigationControlOutput(
                status="error",
                message=getattr(result, "message", "") or "导航服务未返回有效结果",
            )

        # 开始导航：FC 给出开始导航 function_code + 目的地
        dest = _extract_destination(result.observation)
        if dest:
            self.car.set_field("导航目的地", dest)
            self.car.set_field("导航状态", "导航中")
            return NavigationControlOutput(
                status="success",
                message=f"已开始导航：{dest}",
                observation={"导航目的地": dest, "导航状态": "导航中"},
            )

        # 取消导航：按指令语义清空状态
        if any(k in cmd for k in _CANCEL_KEYWORDS):
            self.car.set_field("导航目的地", "未设置")
            self.car.set_field("导航状态", "未导航")
            return NavigationControlOutput(
                status="success",
                message="已取消导航",
                observation={"导航目的地": "未设置", "导航状态": "未导航"},
            )

        # 查询：返回当前状态，不改状态
        cur_dest = str(self.car.get_field("导航目的地"))
        cur_status = str(self.car.get_field("导航状态"))
        if cur_status == "导航中" and cur_dest and cur_dest != "未设置":
            return NavigationControlOutput(
                status="success",
                message=f"当前正在导航，目的地：{cur_dest}",
                observation={"导航目的地": cur_dest, "导航状态": cur_status},
            )
        return NavigationControlOutput(
            status="success",
            message="当前未在导航",
            observation={"导航目的地": cur_dest, "导航状态": cur_status},
        )


def NavigationControlTool(
    virtual_car: VirtualCar | None = None,
    *,
    chat_id: str = "time-travel-demo",
    worker: _NavigationWorkerType | None = None,
    task_manager: TaskManager | None = None,
) -> callable:
    """虚拟车导航工具工厂（name="navigation"，对齐 sgm navigation_v2_tool）。

    长耗时导航通过 task_manager 走异步执行（asyncable="async"）：agent 调用后先收到
    占位回执，真实导航结果由 TaskManager 后台执行完成后回灌，工具泳道可见并行区间。
    不传 task_manager 时回退同步执行（asyncable="sync"，兼容直接单测调用）。
    """
    controller = NavigationController(virtual_car, worker=worker, chat_id=chat_id) if virtual_car else None

    async def inner_worker(command: str) -> NavigationControlOutput:
        if controller is None:
            return NavigationControlOutput(status="error", message="虚拟车实例未设置")
        return await controller.execute(command)

    return create_tool(
        name="navigation",
        description=(
            "控制虚拟车导航：设置目的地开始导航（如「导航到虹桥火车站」「带我去公司」）、"
            "取消导航、查询当前导航状态。输入为自然语言导航指令。"
        ),
        args_schema=NavigationControlInput,
        worker=inner_worker,
        timeout=10.0,
        asyncable="async" if task_manager is not None else "sync",
        task_manager=task_manager,
    )