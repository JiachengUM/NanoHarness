"""
导航工具：对应原 complex_reasoning_agent subagent NavigateAgent。
通过 call_fc(query, chat_id) 请求火山 FC 插件。
"""
import json
import logging
from enum import Enum
from typing import Callable, Awaitable

from pydantic import BaseModel, Field

from aicore.runtime.task import TaskManager
from aicore.tools import create_tool

from projects.mind.complex_reasoning.utils.exception import FcException
from projects.mind.complex_reasoning.utils.plugins import IntentType, call_fc

__all__ = ["NavigateInput", "NavigateTool", "NavigateOutput"]

logger = logging.getLogger(__name__)

_NAVIGATION_START_FUNCTION_CODES = {
    "单目的地导航",
    "多目的地导航",
}
_NAVIGATION_GENERIC_FUNCTION_CODES = {
    "导航操作",
}

_NAVIGATION_START_FALLBACK_KEYWORDS = (
    "导航到",
    "导航去",
    "前往",
    "带我去",
    "开车去",
)
_NAVIGATION_CONTROL_FALLBACK_KEYWORDS = (
    "取消",
    "停止",
    "退出",
    "关闭",
    "暂停",
    "添加",
    "新增",
    "途经",
    "途径",
    "避开",
    "路线偏好",
    "路线刷新",
    "切换",
    "查询",
    "还有多久",
    "剩余",
    "播报",
)


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


def _extract_function_codes(observation: dict[str, object] | None) -> list[str]:
    if not observation:
        return []

    functions = observation.get("functions")
    if not isinstance(functions, list):
        return []

    codes: list[str] = []
    for function_item in functions:
        if not isinstance(function_item, dict):
            continue

        function_code = function_item.get("function_code")
        if isinstance(function_code, str):
            codes.append(function_code)

    return codes


def _looks_like_navigation_start(command: str) -> bool:
    normalized = command.strip()
    if any(keyword in normalized for keyword in _NAVIGATION_CONTROL_FALLBACK_KEYWORDS):
        return False
    return any(keyword in normalized for keyword in _NAVIGATION_START_FALLBACK_KEYWORDS)


def _should_track_navigation_task(command: str, output: NavigateOutput) -> bool:
    if output.status != NavigateStatus.SUCCESS:
        return False

    function_codes = _extract_function_codes(output.observation)
    if any(code in _NAVIGATION_START_FUNCTION_CODES for code in function_codes):
        return True

    if any(code in _NAVIGATION_GENERIC_FUNCTION_CODES for code in function_codes):
        return _looks_like_navigation_start(command)

    if function_codes:
        return False

    return _looks_like_navigation_start(command)


def _build_navigation_task_arguments(command: str, output: NavigateOutput) -> dict[str, object]:
    arguments: dict[str, object] = {"command": command}
    function_codes = _extract_function_codes(output.observation)
    if function_codes:
        arguments["function_codes"] = ",".join(function_codes)
    return arguments


async def _cancel_navigation(*, chat_id: str) -> None:
    await call_fc("取消导航", chat_id, intent_type=IntentType.NAVIGATION)


class TaskManagedNavigateWorker:
    def __init__(self, worker: NavigateWorker, *, chat_id: str, task_manager: TaskManager):
        self.worker = worker
        self.chat_id = chat_id
        self.task_manager = task_manager

    async def __call__(self, command: str) -> NavigateOutput:
        output = await self.worker(command=command)
        if _should_track_navigation_task(command, output):
            try:
                self.task_manager.submit_external_task(
                    name="navigation",
                    arguments=_build_navigation_task_arguments(command, output),
                    cancel=lambda: _cancel_navigation(chat_id=self.chat_id),
                    metadata={"external_task_type": "navigation"},
                    replace_existing=True,
                )
            except Exception:
                logger.exception("Failed to register navigation external task")
        return output


def NavigateTool(
    chat_id: str,
    worker: NavigateWorker | None = None,
    *,
    timeout: float | None = None,
    task_manager: TaskManager | None = None,
):
    """导航工具：目的地导航、途径点等。调用火山 function_call 插件。"""
    actual_worker = worker if worker is not None else VolcNavigateWorker(chat_id)
    if task_manager is not None:
        actual_worker = TaskManagedNavigateWorker(
            actual_worker,
            chat_id=chat_id,
            task_manager=task_manager,
        )

    return create_tool(
        name="navigation",
        description="通过导航指令执行导航任务，指定目的地导航、添加途径点、路线偏好",
        args_schema=NavigateInput,
        worker=actual_worker,
        timeout=timeout,
    )
