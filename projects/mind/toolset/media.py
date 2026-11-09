"""
媒体工具：对应原 complex_reasoning_agent subagent MediaAgent。
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

__all__ = ["MediaInput", "MediaTool","MediaOutput"]

logger = logging.getLogger(__name__)

_MEDIA_PLAY_FUNCTION_CODES = {
    "音乐歌曲播放",
    "音乐歌单播放",
    "有声音频播放",
    "网络电台播放",
    "本地电台播放",
    "影视剧视频播放",
    "新闻播放",
    "媒体列表播放",
    "K 歌歌曲点播",
}

_MEDIA_START_FALLBACK_KEYWORDS = ("播放", "放一首", "来一首", "听")
_MEDIA_CONTROL_FALLBACK_KEYWORDS = (
    "暂停",
    "停止",
    "取消",
    "关闭",
    "下一首",
    "上一首",
    "切歌",
    "音量",
    "静音",
    "继续播放",
    "恢复播放",
)


class MediaInput(BaseModel):
    # 媒体控制指令。
    
    # command: str = Field(description="多媒体控制任务的自然语言描述，如：播放周杰伦的稻香、暂停播放、下一首")
    command: str = Field(description="结合用户意图和QQMusic返回信息的执行描述")


class MediaStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class MediaOutput(BaseModel):
    status: MediaStatus
    message: str = ""
    observation: dict[str, object] | None = None
    error_msg: str = ""


async def _media_worker(command: str, *, chat_id: str) -> MediaOutput:
    try:
        fc_result = await call_fc(command, chat_id, intent_type=IntentType.MEDIA_CONTROL)
        if isinstance(fc_result, str) and fc_result.strip().startswith("{"):
            return MediaOutput(
                status=MediaStatus.SUCCESS,
                message="已执行媒体控制",
                observation=json.loads(fc_result),
            )
        # 如果有媒体fc_result，正常来说是json格式，如果不是，说明失败
        return MediaOutput(
            status=MediaStatus.ERROR,
            observation=None,
            message="未获取到媒体结果",
        )
    except FcException as e:
        logger.warning("call_fc FcException: %s", e)
        return MediaOutput(status=MediaStatus.ERROR, error_msg=str(e))
    except Exception as e:
        logger.exception("call_fc error: %s", e)
        return MediaOutput(status=MediaStatus.ERROR, error_msg=str(e))


class VolcMediaWorker:
    def __init__(self, chat_id: str):
        self.chat_id = chat_id

    async def __call__(self, command: str) -> MediaOutput:
        return await _media_worker(command, chat_id=self.chat_id)


MediaWorker = Callable[..., Awaitable[MediaOutput]]


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


def _looks_like_media_play_start(command: str) -> bool:
    normalized = command.strip()
    if any(keyword in normalized for keyword in _MEDIA_CONTROL_FALLBACK_KEYWORDS):
        return False
    return any(keyword in normalized for keyword in _MEDIA_START_FALLBACK_KEYWORDS)


def _should_track_media_task(command: str, output: MediaOutput) -> bool:
    if output.status != MediaStatus.SUCCESS:
        return False

    function_codes = _extract_function_codes(output.observation)
    if function_codes:
        return any(code in _MEDIA_PLAY_FUNCTION_CODES for code in function_codes)

    return _looks_like_media_play_start(command)


def _build_media_task_arguments(command: str, output: MediaOutput) -> dict[str, object]:
    arguments: dict[str, object] = {"command": command}
    function_codes = _extract_function_codes(output.observation)
    if function_codes:
        arguments["function_codes"] = ",".join(function_codes)
    return arguments


async def _cancel_media_playback(*, chat_id: str) -> None:
    await call_fc("暂停播放", chat_id, intent_type=IntentType.MEDIA_CONTROL)


class TaskManagedMediaWorker:
    def __init__(self, worker: MediaWorker, *, chat_id: str, task_manager: TaskManager):
        self.worker = worker
        self.chat_id = chat_id
        self.task_manager = task_manager

    async def __call__(self, command: str) -> MediaOutput:
        output = await self.worker(command=command)
        if _should_track_media_task(command, output):
            try:
                self.task_manager.submit_external_task(
                    name="media",
                    arguments=_build_media_task_arguments(command, output),
                    cancel=lambda: _cancel_media_playback(chat_id=self.chat_id),
                    metadata={"external_task_type": "media_playback"},
                    replace_existing=True,
                )
            except Exception:
                logger.exception("Failed to register media external task")
        return output


def MediaTool(
    chat_id: str,
    worker: MediaWorker | None = None,
    *,
    timeout: float | None = None,
    task_manager: TaskManager | None = None,
):
    """媒体工具：音乐播放与控制。调用火山 function_call 插件。"""
    actual_worker = worker if worker is not None else VolcMediaWorker(chat_id)
    if task_manager is not None:
        actual_worker = TaskManagedMediaWorker(
            actual_worker,
            chat_id=chat_id,
            task_manager=task_manager,
        )

    return create_tool(
        name="media",
        description="音乐控制和执行，**不需要具体的歌曲ID**，当搜出多首歌曲均满足筛选条件时，必须先通过媒体控制整理成歌单，然后执行歌单播放",
        args_schema=MediaInput,
        worker=actual_worker,
        timeout=timeout,
    )
