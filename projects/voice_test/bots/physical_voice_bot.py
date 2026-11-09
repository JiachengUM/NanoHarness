"""AutoTest 评测框架的物理语音 Bot。"""

from __future__ import annotations

from typing import Any

from projects.voice_test.adapter.voice_adapter import PhysicalVoiceAdapter


class PhysicalVoiceBot:
    """AutoTestAndRLDataGenerator 使用的 Bot。"""

    _adapter: PhysicalVoiceAdapter | None = None

    def __init__(self, context_config: dict[str, Any]) -> None:
        self.context_config = dict(context_config)
        self.session_id = ""
        self.query = ""
        self.answer = ""
        self.turn_records: list[dict[str, str]] = []

    @classmethod
    def _get_adapter(cls) -> PhysicalVoiceAdapter:
        if cls._adapter is None:
            cls._adapter = PhysicalVoiceAdapter()
        return cls._adapter

    async def aupdate_context(self, context_config: dict[str, Any]) -> None:
        self.context_config.update(context_config)

    async def achat(self, query: str, session_id: str) -> str:
        if self.session_id and self.session_id != session_id:
            self.turn_records = []
        self.session_id = session_id
        self.query = query
        self.answer = await self._get_adapter().speak_and_listen(query, session_id)
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
                {"type": "physical_voice.user_query", "text": self.query},
                {"type": "physical_voice.assistant_reply", "text": self.answer},
            ],
            "metadata": {"mode": "physical_voice_adapter"},
        }

    @classmethod
    def create(
        cls,
        context_config: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> "PhysicalVoiceBot":
        del args, kwargs
        return cls(context_config)

    @classmethod
    async def aclean_memory_for_users(
        cls,
        user_ids: list[str],
        *,
        context_config: dict[str, Any] | None = None,
        except_skills: bool = False,
    ) -> None:
        del user_ids, context_config, except_skills
        await cls.close_adapter()

    @classmethod
    async def close_adapter(cls) -> None:
        if cls._adapter is not None:
            await cls._adapter.close()
            cls._adapter = None
