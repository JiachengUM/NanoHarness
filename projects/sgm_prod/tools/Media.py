import json
import logging

from pydantic import BaseModel, Field

from aicore.tools import create_tool
from projects.sgm_prod.function_call import IntentType, call_fc

__all__ = ["MediaInput", "MediaOutput", "MediaWorker", "create_media_tool"]

logger = logging.getLogger(__name__)


class MediaInput(BaseModel):
    # 媒体控制指令。
    command: str = Field(description="多媒体控制任务的自然语言描述，如：播放周杰伦的稻香、暂停播放、下一首")


class MediaOutput(BaseModel):
    status: str
    message: str = ""
    observation: dict[str, object] | None = None


class MediaWorker:
    """媒体控制 worker，封装 chat_id 并提供 async __call__。"""

    def __init__(self, chat_id: str):
        self.chat_id = chat_id

    async def _run(self, command: str) -> MediaOutput:
        fc_result = await call_fc(command, self.chat_id, intent_type=IntentType.MEDIA_CONTROL)
        if fc_result.strip().startswith("{"):
            return MediaOutput(
                status="success",
                message="已执行媒体控制",
                observation=json.loads(fc_result),
            )
        return MediaOutput(status="error", message="未获取到媒体结果")

    async def __call__(self, command: str) -> MediaOutput:
        return await self._run(command)


def create_media_tool(chat_id: str):
    """媒体工具工厂：音乐播放与控制。"""
    return create_tool(
        name="media",
        description="控制车载多媒体，如播放/暂停/切歌、播放指定歌曲或歌单。输入为自然语言控制指令。",
        args_schema=MediaInput,
        worker=MediaWorker(chat_id),
    )
