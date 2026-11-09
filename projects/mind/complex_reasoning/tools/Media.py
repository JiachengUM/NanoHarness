"""
媒体工具：对应原 complex_reasoning_agent subagent MediaAgent。
通过 call_fc(query, chat_id) 请求火山 FC 插件。
"""
import json
import logging
from enum import Enum

from pydantic import BaseModel, Field

from aicore.tools import BaseTool

from projects.mind.complex_reasoning.utils.exception import FcException
from projects.mind.complex_reasoning.utils.plugins import IntentType, call_fc

__all__ = ["MediaInput", "MediaTool"]

logger = logging.getLogger(__name__)


class MediaInput(BaseModel):
    """媒体控制指令。"""
    command: str = Field(description="多媒体控制任务的自然语言描述，如：播放周杰伦的稻香、暂停播放、下一首")


class MediaStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class MediaOutput(BaseModel):
    status: MediaStatus
    message: str = ""
    observation: dict[str, object] | None = None
    error_msg: str = ""


class MediaTool(BaseTool):
    """媒体工具：音乐播放与控制。调用火山 function_call 插件。"""
    name: str = "media"
    description: str = "控制车载多媒体，如播放/暂停/切歌、播放指定歌曲或歌单。输入为自然语言控制指令。"
    args_schema: type[BaseModel] = MediaInput
    chat_id: str = Field(..., description="会话 ID，用于请求火山媒体插件")

    def _run(self, command: str) -> dict:
        raise NotImplementedError("媒体工具请使用异步调用 ainvoke/astream")

    async def _arun(self, command: str) -> MediaOutput:
        try:
            fc_result = await call_fc(command, self.chat_id, intent_type=IntentType.MEDIA_CONTROL)
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
