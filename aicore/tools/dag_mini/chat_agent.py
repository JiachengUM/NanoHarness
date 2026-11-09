"""DAG Mini — 最外层 chat_agent。

```
create_chat_agent(model, available_tools, ...) → chat_agent (v1 AgentBase)
  └─ tools = [TaskAgent]                              # 拆解后调本 tool
       └─ worker = subagent.run(plan.steps)           # DAG + 并行 + per-step Agent
              └─ 收集 step_records[*].final_answer     # → 回流到 chat_agent 的 v1 state
                                                          → chat_agent 看到结果，汇总回复
```

chat_agent 本身只跑一次 react（react_max_turns=1）：拆解后调 TaskAgent，然后
根据 tool 返回的 SubagentOutput 给用户最终回复。
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from aicore.tools.dag_mini.models import SubagentOutput
from aicore.tools.dag_mini.prompt import CHAT_SYSTEM_PROMPT
from aicore.tools.dag_mini.subagent import Subagent, create_taskagent

logger = logging.getLogger(__name__)


class ChatAgent(BaseModel):
    """最外层 chat_agent：v1 create_agent 的薄壳。

    字段：
        model: chat_agent 用的 LLM 模型（拆解 + 汇总回复）
        task_agent_timeout: TaskAgent tool 的超时（秒）
        react_max_turns: chat_agent ReAct 轮数（默认 1：拆解 + 调一次 tool + 汇总）
        on_subagent_output: 每次 Subagent 跑完后回调（拿结构化 SubagentOutput，不是 tool 框架的 nl_repr 字符串）
    """

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)

    model: str
    available_tools: list[Any] = Field(default_factory=list)
    runtime_context: dict[str, str] = Field(default_factory=dict)
    subagent_system_prompt: str = ""
    task_agent_timeout: float = 60.0
    chat_system_prompt: str = CHAT_SYSTEM_PROMPT
    chat_react_max_turns: int = 1
    subagent_max_concurrent_steps: int = 4
    subagent_max_react_turns: int = 2
    on_subagent_output: Callable[[SubagentOutput], Awaitable[None]] | None = None

    _v1_agent: Any = None

    async def _ensure_v1_agent(self) -> None:
        """懒构造：build Subagent → TaskAgent tool → v1 create_agent with [TaskAgent]。"""
        if self._v1_agent is not None:
            return
        import asyncio

        from aicore.v1.experiments.base import create_agent

        subagent = Subagent(
            model=self.model,
            max_concurrent_steps=self.subagent_max_concurrent_steps,
            max_react_turns=self.subagent_max_react_turns,
            system_prompt=self.subagent_system_prompt,
            tools=self.available_tools,
            runtime_context=self.runtime_context,
        )
        task_agent = create_taskagent(
            subagent,
            available_tools=self.available_tools,
            timeout=self.task_agent_timeout,
            on_subagent_output=self.on_subagent_output,
        )
        self._v1_agent = await asyncio.to_thread(
            create_agent,
            model=self.model,
            tools=[task_agent],
            react_max_turns=self.chat_react_max_turns,
            system_prompt=self.chat_system_prompt,
        )

    async def run(self, query: str) -> dict:
        """跑一次 chat_agent：拆解 → 调 TaskAgent → 汇总回复。

        Returns:
            v1 state 解析后的 4 键 dict：``system / user / assistant / tool_calls``。
            chat_agent 的 final assistant 即对用户的最终回复。
        """
        from aicore.tools.dag_mini.models import Trace

        await self._ensure_v1_agent()
        await self._v1_agent.run_astream(query, event_listeners=[])
        _, state = await self._v1_agent.dump()
        return Trace(state=state).dump_all()


def create_chat_agent(
    *,
    model: str,
    available_tools: list[Any],
    runtime_context: dict[str, str] | None = None,
    subagent_system_prompt: str = "",
    chat_system_prompt: str = CHAT_SYSTEM_PROMPT,
    task_agent_timeout: float = 60.0,
    chat_react_max_turns: int = 1,
    subagent_max_concurrent_steps: int = 4,
    subagent_max_react_turns: int = 2,
    on_subagent_output: Callable[[SubagentOutput], Awaitable[None]] | None = None
) -> ChatAgent:
    """工厂：构造 ChatAgent（未启动 v1 agent，第一次 run 时懒初始化）。

    on_subagent_output: 每次 TaskAgent 跑完 Subagent 后调用（拿结构化 SubagentOutput，
    不是 tool 框架的 nl_repr 字符串）。demo 用来收集 per-step 结果展示用。
    """
    return ChatAgent(
        model=model,
        available_tools=list(available_tools),
        runtime_context=dict(runtime_context or {}),
        subagent_system_prompt=subagent_system_prompt,
        chat_system_prompt=chat_system_prompt,
        task_agent_timeout=task_agent_timeout,
        chat_react_max_turns=chat_react_max_turns,
        subagent_max_concurrent_steps=subagent_max_concurrent_steps,
        subagent_max_react_turns=subagent_max_react_turns,
        on_subagent_output=on_subagent_output,
    )
