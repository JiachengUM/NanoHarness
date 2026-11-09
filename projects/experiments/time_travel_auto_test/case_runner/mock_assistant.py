"""Mock 被测助手：不调 LLM，按预设规则回复。

从 test/test_case_runner_e2e.py 提取到生产位置——可视化服务器
（visualizer/run_server.py）的 demo mock 助手也要复用它。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from projects.experiments.time_travel_auto_test.case_runner.assistant_protocol import (
    ContextUpdateResult,
    StreamingReply,
)


class MockAssistant:
    """Mock 被测助手：不调 LLM，按预设规则回复。"""

    def __init__(self) -> None:
        self.virtual_car: Any = None
        self._session_id: str = ""
        self._history: list[dict[str, str]] = []
        self._reply_counter: int = 0
        # 每路投喂输入流首/末 chunk 的到达时刻（供流式投喂断言）
        self.first_chunk_walls: list[datetime] = []
        self.last_chunk_walls: list[datetime] = []

    def create(self, session_id: str, system_prompt: str = "") -> None:
        self._session_id = session_id
        self._history = []
        self._reply_counter = 0
        self.first_chunk_walls = []
        self.last_chunk_walls = []

    async def _collect_input(self, chunks: AsyncIterator[str]) -> str:
        """聚合输入流，记录首/末 chunk 到达时刻。

        首/末 chunk 相隔时间可区分投喂模型：
        - 流式投喂（第一个字即投）：chunk 按说话节奏逐个到达，相隔 ≈ 说话时长
        - 说完才投（旧模型）：所有 chunk 一次性到达，相隔 ≈ 0
        """
        first_wall: Optional[datetime] = None
        last_wall: Optional[datetime] = None
        parts: list[str] = []
        async for c in chunks:
            now = datetime.now()
            if first_wall is None:
                first_wall = now
            last_wall = now
            parts.append(c)
        if first_wall is not None:
            self.first_chunk_walls.append(first_wall)
            self.last_chunk_walls.append(last_wall)
        return "".join(parts)

    async def achat(self, user_text: str) -> str:
        self._reply_counter += 1
        # 简单规则回复
        if "开空调" in user_text or "有点热" in user_text:
            reply = "好的，已为您打开空调。"
            if self.virtual_car is not None:
                self.virtual_car.set_field("空调开启状态及模式", "制冷中")
        elif "开门" in user_text:
            reply = "好的，已为您开门。"
        elif "按摩" in user_text:
            reply = "好的，已为您开启座椅按摩。"
            if self.virtual_car is not None:
                self.virtual_car.set_field("主驾座椅按摩", "轻柔")
        elif "播放" in user_text or "听" in user_text and "歌" in user_text:
            reply = "好的，正在为您播放。"
            if self.virtual_car is not None:
                self.virtual_car.set_field("多媒体播放状态", "播放中")
                # 通用解析："播放XXX的YYY" → 歌手 XXX / 歌曲 YYY
                m = re.search(r'(?:播放|来一?首|听一?首)(?:点|一首|首)?(.+?)(?:吧|呗|。)?$', user_text)
                tail = (m.group(1) if m else "").strip()
                if tail and tail not in ("音乐", "歌", "歌曲", "首歌", "轻音乐"):
                    if "的" in tail:
                        artist, song = tail.rsplit("的", 1)
                        if artist.strip():
                            self.virtual_car.set_field("正在播放的歌手名", artist.strip())
                        if song.strip():
                            self.virtual_car.set_field("正在播放的歌曲名", song.strip())
                    else:
                        self.virtual_car.set_field("正在播放的歌曲名", tail)
        elif "暂停" in user_text:
            reply = "好的，已暂停播放。"
            if self.virtual_car is not None:
                self.virtual_car.set_field("多媒体播放状态", "暂停中")
        elif "导航" in user_text or "去机场" in user_text:
            reply = "好的，已为您规划路线。"
            if self.virtual_car is not None:
                self.virtual_car.set_field("导航目的地", "上海浦东国际机场T2航站楼")
        else:
            reply = f"收到您的请求：{user_text[:20]}"
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": reply})
        return reply

    async def achat_stream(self, chunks: AsyncIterator[str]) -> StreamingReply:
        user_text = await self._collect_input(chunks)
        reply_text = await self.achat(user_text)
        reply = StreamingReply()
        # 模拟流式：一次性放入
        await reply.put_chunk(reply_text)
        await reply.finish()
        return reply

    async def aupdate_context(
        self,
        car_info: dict[str, Any],
        current_time: Optional[datetime] = None,
    ) -> ContextUpdateResult:
        return ContextUpdateResult()

    async def adump_history(self) -> list[dict[str, str]]:
        return list(self._history)
