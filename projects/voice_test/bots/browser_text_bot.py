"""浏览器文本链路：包装任意 AnyBotToTest，只负责推浏览器事件。

registry 注册时传入 inner bot 类 + 可选 prepare_context 即可，不必每种 bot 各建一个文件。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from projects.mind.mem.auto_test_script.agent_v1_eval_context import (
    build_voice_test_agent_v1_context,
)
from projects.mind.test_backend.service.task.agent_v1_bot import AgentV1Bot
from projects.voice_test.schemas.browser_schemas import AsrFinalEvent, UserQueryEvent
from projects.voice_test.adapter.browser_text_adapter import BrowserTextAdapter

PrepareContextFn = Callable[[dict[str, Any] | None], dict[str, Any]]


def browser_text_bot_for_adapter(
    adapter: BrowserTextAdapter,
    inner_bot_cls: type[Any],
    prepare_context: PrepareContextFn | None = None,
) -> type[Any]:
    """为单个 WS 会话包装 inner_bot_cls，绑定 adapter，可选 merge case config。"""

    class SessionBrowserTextBot:
        _adapter: BrowserTextAdapter = adapter

        def __init__(self, inner: Any) -> None:
            self._inner = inner

        @classmethod
        def _prepare(cls, context_config: dict[str, Any] | None) -> dict[str, Any]:
            if prepare_context is None:
                base = dict(context_config or {})
            else:
                base = prepare_context(context_config)
            base["voice_test_adapter"] = cls._adapter
            base["auto_test_suppress_bot_console"] = True
            return base

        @classmethod
        def create(
            cls,
            context_config: dict[str, Any],
            *args: Any,
            **kwargs: Any,
        ) -> SessionBrowserTextBot:
            inner = inner_bot_cls.create(cls._prepare(context_config), *args, **kwargs)
            return cls(inner)

        async def aupdate_context(self, context_config: dict[str, Any]) -> None:
            await self._inner.aupdate_context(context_config)

        async def achat(self, query: str, session_id: str) -> str:
            await self._adapter.ensure_ready()
            await self._adapter.push_event(UserQueryEvent(text=query, mode="text", session_id=session_id))
            answer = await self._inner.achat(query, session_id)
            await self._adapter.push_event(AsrFinalEvent(text=answer))
            return answer

        def chat(self, query: str, session_id: str) -> str:
            return self._inner.chat(query, session_id)

        async def adump_history(self) -> list[dict[str, str]]:
            return await self._inner.adump_history()

        def dump_history(self) -> list[dict[str, str]]:
            return self._inner.dump_history()

        async def adump_state_trace(self) -> dict[str, Any]:
            return await self._inner.adump_state_trace()

        def dump_state_trace(self) -> dict[str, Any]:
            import asyncio

            return asyncio.run(self.adump_state_trace())

        @classmethod
        async def aclean_memory_for_users(
            cls,
            user_ids: list[str],
            *,
            context_config: dict[str, Any] | None = None,
            except_skills: bool = False,
        ) -> None:
            await inner_bot_cls.aclean_memory_for_users(
                user_ids,
                context_config=cls._prepare(context_config),
                except_skills=except_skills,
            )

    return SessionBrowserTextBot


def browser_text_agent_v1_for_adapter(adapter: BrowserTextAdapter) -> type[Any]:
    return browser_text_bot_for_adapter(
        adapter,
        AgentV1Bot,
        build_voice_test_agent_v1_context,
    )


def browser_text_old_complex_for_adapter(adapter: BrowserTextAdapter) -> type[Any]:
    """OldComplex：case.context_config 原样传入；voice-test 不调用远程 mock submit。"""
    from projects.mind.mem.auto_test_script.auto_test_demos.old_complex_reasoning_auto_test import (
        OldComplexReasoningServiceBot,
    )

    OldComplexReasoningServiceBot.is_submit_mock_info = False
    return browser_text_bot_for_adapter(adapter, OldComplexReasoningServiceBot)
