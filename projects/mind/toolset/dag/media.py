"""
媒体工具：对应原 complex_reasoning_agent subagent MediaAgent。
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

__all__ = ["MediaInput", "MediaTool","MediaOutput"]

logger = logging.getLogger(__name__)


class MediaInput(BaseModel):
    # 媒体控制指令。
    
    # command: str = Field(description="多媒体控制任务的自然语言描述，如：播放周杰伦的稻香、暂停播放、下一首")
    command: str = Field(description="媒体控制播放指令，播放内容：歌曲名称（song_name）/歌单名称（dissname）/专辑名称（album_name）等音频内容")


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


def MediaTool(chat_id: str, worker: MediaWorker | None = None, *, timeout: float | None = None):
    # """媒体工具：音乐播放与控制。调用火山 function_call 插件。"""
    return create_tool(
        name="AudioPlay",
        description=(
            "媒体控制播放器，播放内容：歌曲名称（song_name）/歌单名称（dissname）/专辑名称（album_name）等音频内容。"
            "输出：执行状态"
        ),
        args_schema=MediaInput,
        worker=worker if worker is not None else VolcMediaWorker(chat_id),
        timeout=timeout,
    )
