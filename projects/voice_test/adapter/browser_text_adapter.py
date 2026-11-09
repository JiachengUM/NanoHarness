"""浏览器文本链路：仅推送 JSON 事件，无音频。"""

from __future__ import annotations

import asyncio

from projects.voice_test.schemas.browser_schemas import (
    BrowserJsonEvent,
    OutMessage,
    ReadyTextEvent,
)


class BrowserTextAdapter:
    """与 BrowserVoiceAdapter 共用 out_queue 协议。"""

    def __init__(self, out_queue: asyncio.Queue[OutMessage] | None = None) -> None:
        self.out_queue: asyncio.Queue[OutMessage] = out_queue or asyncio.Queue()
        self._ready_sent = False

    def reset_session_events(self) -> None:
        self._ready_sent = False

    async def push_event(self, event: BrowserJsonEvent) -> None:
        await self.out_queue.put(event)

    async def ensure_ready(self) -> None:
        if self._ready_sent:
            return
        self._ready_sent = True
        await self.push_event(ReadyTextEvent())

    async def close(self) -> None:
        # 文本链路无持有资源；与 BrowserVoiceAdapter.close 对称，供 WS finally 统一调用。
        return
