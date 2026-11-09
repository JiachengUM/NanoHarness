"""虚拟车媒体控制工具（独立工具，非车控）。

对齐 aicore/v2/experiments/sgm_tools_v2.py 的 media_v2_tool 接口
（name="media"），但操作虚拟车媒体状态而非真实车机媒体 API：
- 指令解析产出 {car_info key: 中文值} 写入集，统一走 VirtualCar.set_field 落盘
  （devices 是唯一真相源，on_field_change 钩子 → 可视化 car_set_state 事件）
- 支持：播放/暂停/继续/停止、点歌（歌曲/歌手/歌单）、音量调节、
  音源切换（蓝牙音乐/在线音乐/收音机/USB）、查询当前播放状态
- 切歌不支持：虚拟车无歌单队列数据（诚实返回错误而非编造歌曲）
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from aicore.runtime.task import TaskManager
from aicore.v2.tools.factory import create_tool

if TYPE_CHECKING:
    from projects.experiments.time_travel_auto_test.virtual_car.models import VirtualCar

__all__ = [
    "MediaControlInput",
    "MediaControlOutput",
    "MediaControlTool",
]

logger = logging.getLogger(__name__)

_GENERIC_MEDIA_WORDS = {"音乐", "歌", "歌曲", "首歌", "轻音乐", "流行音乐", "点歌"}

# 查询意图特征词（不含动作词时视为查询当前状态）
_QUERY_WORDS = ("什么歌", "什么状态", "啥状态", "放的什么", "在放什么", "在放啥", "哪首歌", "音量多少", "播放状态")

_SOURCES: dict[str, str] = {
    "蓝牙": "蓝牙音乐",
    "在线": "在线音乐",
    "收音机": "收音机",
    "电台": "收音机",
    "usb": "USB",
    "USB": "USB",
    "优盘": "USB",
    "U盘": "USB",
}


class MediaControlInput(BaseModel):
    """虚拟车媒体控制指令参数"""

    command: str = Field(
        description=(
            "媒体控制指令的自然语言描述。\n"
            "支持：\n"
            "- 播放控制：播放音乐 / 继续播放 / 暂停 / 停止播放\n"
            "- 点歌：播放XX的XX（歌手+歌曲，如「播放周杰伦的晴天」）、播放XX（歌曲名）、播放歌单XX\n"
            "- 音量：音量调到N% / 音量调大 / 音量调小\n"
            "- 音源：切换到蓝牙音乐 / 在线音乐 / 收音机 / USB\n"
            "- 查询：现在放的什么歌 / 播放状态 / 音量多少"
        )
    )


class MediaControlOutput(BaseModel):
    """虚拟车媒体控制执行结果"""

    status: str = Field(description="执行状态: success / error")
    message: str = Field(description="执行结果描述")
    observation: dict | None = Field(default=None, description="变更后/当前的媒体状态")


class MediaController:
    """虚拟车媒体控制器：解析自然语言媒体指令 → set_field 写入。"""

    def __init__(self, virtual_car: VirtualCar):
        self.car = virtual_car

    async def execute(self, command: str) -> MediaControlOutput:
        """执行媒体指令（顺序：切歌拒绝 → 查询 → 播放控制 → 音量 → 音源）。"""
        if not command or not command.strip():
            return MediaControlOutput(status="error", message="指令为空")

        cmd = command.strip()
        logger.info("执行虚拟车媒体指令: %s", cmd)

        # 切歌：虚拟车无歌单队列，诚实拒绝（不编造歌曲）
        if any(k in cmd for k in ("下一首", "上一首", "切歌", "换一首", "换首")):
            return MediaControlOutput(
                status="error",
                message="当前音源无歌单队列，无法切歌",
            )

        # 查询播放状态（疑问特征词且无动作词 → 纯查询，不改变状态）
        if any(k in cmd for k in _QUERY_WORDS) and not any(
            k in cmd for k in ("来", "听", "暂停", "继续", "停止", "切换", "调", "播放一", "放一")
        ):
            track = str(self.car.get_field("正在播放的歌曲名"))
            artist = str(self.car.get_field("正在播放的歌手名"))
            status = str(self.car.get_field("多媒体播放状态"))
            volume = str(self.car.get_field("音量"))
            parts = []
            if status == "播放中" and track != "无":
                parts.append(f"正在播放 {artist if artist != '无' else ''}的《{track}》".strip())
            else:
                parts.append(f"当前{status}")
            parts.append(f"音量 {volume}")
            return MediaControlOutput(
                status="success",
                message="，".join(parts),
                observation={
                    "多媒体播放状态": status,
                    "正在播放的歌曲名": track,
                    "正在播放的歌手名": artist,
                    "音量": volume,
                },
            )

        writes: dict[str, str] = {}

        # 播放控制
        if "暂停" in cmd:
            writes["多媒体播放状态"] = "暂停中"
        elif any(k in cmd for k in ("停止", "别放", "别播", "关掉")):
            writes["多媒体播放状态"] = "停止中"
        elif "继续" in cmd:
            writes["多媒体播放状态"] = "播放中"
        elif any(k in cmd for k in ("播放", "放", "来首", "来一首", "听首", "听一")):
            writes["多媒体播放状态"] = "播放中"
            self._parse_track(cmd, writes)

        # 音量
        if "音量" in cmd or "声音" in cmd:
            m = re.search(r'(\d{1,3})\s*%', cmd)
            if m:
                writes["音量"] = f"{min(100, int(m.group(1)))}%"
            elif any(k in cmd for k in ("调大", "大一点", "大声", "调高")):
                writes["音量"] = f"{min(100, self.car.media.volume + 10)}%"
            elif any(k in cmd for k in ("调小", "小一点", "小声", "调低")):
                writes["音量"] = f"{max(0, self.car.media.volume - 10)}%"

        # 音源切换
        if "切换" in cmd or ("换" in cmd and "歌" not in cmd):
            for kw, source in _SOURCES.items():
                if kw in cmd:
                    writes["音源"] = source
                    break

        if not writes:
            return MediaControlOutput(status="error", message=f"不支持的媒体指令: {cmd}")

        for key, value in writes.items():
            self.car.set_field(key, value)
        changes = {key: str(self.car.get_field(key)) for key in writes}
        return MediaControlOutput(
            status="success",
            message=f"媒体控制成功：{'；'.join(f'{k}={v}' for k, v in changes.items())}",
            observation=changes,
        )

    def _parse_track(self, cmd: str, writes: dict[str, str]) -> None:
        """解析歌曲/歌手/歌单："播放周杰伦的晴天" → 歌手=周杰伦 歌曲=晴天；"播放歌单XXX" → 歌单=XXX。"""
        m = re.search(r'(?:播放|放|来一首|来首|听一?首)(?:点|一首|首)?(.+?)(?:吧|呗|好吗|谢谢)?$', cmd)
        tail = (m.group(1) if m else "").strip()
        if not tail or tail in _GENERIC_MEDIA_WORDS:
            return
        if "歌单" in tail:
            playlist = tail.replace("歌单", "").strip()
            if playlist:
                writes["正在播放的歌单名"] = playlist
            return
        if "的" in tail:
            artist, song = tail.rsplit("的", 1)
            if artist.strip():
                writes["正在播放的歌手名"] = artist.strip()
            if song.strip():
                writes["正在播放的歌曲名"] = song.strip()
        else:
            writes["正在播放的歌曲名"] = tail


def MediaControlTool(
    virtual_car: VirtualCar | None = None,
    task_manager: TaskManager | None = None,
) -> callable:
    """虚拟车媒体控制工具工厂（name="media"，对齐 sgm media_v2_tool）。

    Args:
        virtual_car: 要控制的虚拟车实例。如果为None，需要从上下文获取。
        task_manager: 传入时走异步任务化执行（产生 TaskCreatedEvent 工具事件，
                      落到工具泳道/对话流）；不传时同步执行（兼容单测直接调用）。
    """
    controller = MediaController(virtual_car) if virtual_car else None

    async def worker(command: str) -> MediaControlOutput:
        if controller is None:
            return MediaControlOutput(status="error", message="虚拟车实例未设置")
        return await controller.execute(command)

    return create_tool(
        name="media",
        description=(
            "控制虚拟车媒体播放：播放/暂停/继续/停止、点歌（播放指定歌手的歌曲或歌曲名，"
            "如「播放周杰伦的晴天」）、播放歌单、音量调节（N%/调大/调小）、"
            "音源切换（蓝牙音乐/在线音乐/收音机/USB）、查询当前播放状态。"
            "输入为自然语言媒体控制指令。"
        ),
        args_schema=MediaControlInput,
        worker=worker,
        timeout=5.0,
        asyncable="async" if task_manager is not None else "sync",
        task_manager=task_manager,
    )
