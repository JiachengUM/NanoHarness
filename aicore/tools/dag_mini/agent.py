"""DAG Mini — Agent：v1 create_agent 薄壳。

``run(full_prompt)`` fire-and-forget 跑完 astream，再 dump state 解析出
4 键 dict：``system / user / assistant / tool_calls``。
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from aicore.tools.dag_mini.models import Trace


class AgentStreamError(Exception):
    """v1 astream / dump 失败统一包装。"""

    def __init__(self, original: BaseException):
        super().__init__(f"[{type(original).__name__}] {original}")


class Agent(BaseModel):
    """v1 create_agent 包装。run() 一次性返回 Trace 4 要素。"""

    model_config = {"arbitrary_types_allowed": True}

    model: str
    system_prompt: str = ""
    max_turns: int = Field(default=5, ge=1)
    tools: list[Any] = Field(default_factory=list)

    _v1_agent: Any = PrivateAttr(default=None)

    async def _ensure_v1_agent(self) -> None:
        """懒初始化 v1 agent：``asyncio.to_thread`` 跑同步 ``create_agent``。"""
        if self._v1_agent is not None:
            return
        from aicore.v1.experiments.base import create_agent
        self._v1_agent = await asyncio.to_thread(
            create_agent,
            model=self.model,
            tools=self.tools,
            react_max_turns=self.max_turns,
            system_prompt=self.system_prompt,
        )

    async def run(self, full_prompt: str) -> dict:
        """fire-and-forget astream → dump → 解析 Trace（system / user / assistant / tcin / tcout）。

        Raises:
            AgentStreamError: v1 astream / dump 失败时包装抛出。
        """
        await self._ensure_v1_agent()
        try:
            await self._v1_agent.run_astream(full_prompt, event_listeners=[])
            _, state = await self._v1_agent.dump()
        except Exception as e:
            raise AgentStreamError(e) from e
        return Trace(state=state).dump_all()
