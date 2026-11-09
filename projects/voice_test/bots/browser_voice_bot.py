"""浏览器音频链路的 AutoTest Bot。"""

from __future__ import annotations

from typing import Any

from projects.voice_test.adapter.browser_voice_adapter import BrowserVoiceAdapter


class BrowserVoiceBot:
    """AutoTest 协议实现；须通过 browser_voice_bot_for_adapter 绑定会话 adapter。"""

    def __init__(self, context_config: dict[str, Any]) -> None:
        self.context_config = dict(context_config)
        self.session_id = ""
        self.query = ""
        self.answer = ""
        self.turn_records: list[dict[str, str]] = []
        self._adapter: BrowserVoiceAdapter | None = None

    def _require_adapter(self) -> BrowserVoiceAdapter:
        if self._adapter is None:
            raise RuntimeError("BrowserVoiceBot 未绑定 adapter，请使用 browser_voice_bot_for_adapter")
        return self._adapter

    async def aupdate_context(self, context_config: dict[str, Any]) -> None:
        self.context_config.update(context_config)

    async def achat(self, query: str, session_id: str) -> str:
        if self.session_id and self.session_id != session_id:
            self.turn_records = []
        self.session_id = session_id
        self.query = query
        self.answer = await self._require_adapter().speak_and_listen(query, session_id)
        self.turn_records.extend(
            [
                {"role": "user", "content": query},
                {"role": "assistant", "content": self.answer},
            ]
        )
        return self.answer

    async def adump_history(self) -> list[dict[str, str]]:
        return list(self.turn_records)

    async def adump_state_trace(self) -> dict[str, Any]:
        return {
            "system_prompt": None,
            "session_id": self.session_id,
            "query": self.query,
            "answer": self.answer,
            "traces": [
                {"type": "browser_voice.user_query", "text": self.query},
                {"type": "browser_voice.assistant_reply", "text": self.answer},
            ],
            "metadata": {"mode": "browser_voice_adapter"},
        }

    @classmethod
    def create(
        cls,
        context_config: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> "BrowserVoiceBot":
        del args, kwargs
        raise TypeError("请使用 browser_voice_bot_for_adapter(adapter) 获取 Bot 类")

    @classmethod
    async def aclean_memory_for_users(
        cls,
        user_ids: list[str],
        *,
        context_config: dict[str, Any] | None = None,
        except_skills: bool = False,
    ) -> None:
        # 有意空实现：语音链路只跑浏览器 S2S 假人，不侧写火山记忆，也清不了。
        # 跑 case 前清记忆由 _run_test_session 在非 voice 分支调用；voice 分支已跳过。
        del user_ids, context_config, except_skills


def browser_voice_bot_for_adapter(adapter: BrowserVoiceAdapter) -> type[BrowserVoiceBot]:
    """为单个 WS 会话生成 Bot 类，adapter 绑在实例上，多用户互不干扰。"""

    class SessionBrowserVoiceBot(BrowserVoiceBot):
        @classmethod
        def create(
            cls,
            context_config: dict[str, Any],
            *args: Any,
            **kwargs: Any,
        ) -> SessionBrowserVoiceBot:
            del args, kwargs
            bot = cls(context_config)
            bot._adapter = adapter
            return bot

    return SessionBrowserVoiceBot
