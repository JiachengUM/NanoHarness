"""
复杂推理 ReAct Agent。仿照 aicore.agents.react 实现方式，
将原 agents_pre1 的「LLM → 解析 task_list → 执行 subagent」改为「LLM → tool_calls → 执行 tools → 再 LLM」。
Subagent 以 Tool 形式注册，由 ReActAgent 统一调度。
"""
from typing import Sequence

from aicore.agents.react import ReActAgentBase
from aicore.models.credentials import AsyncArk, ModelName, create_client
from aicore.models.responses import ResponseParams
from aicore.tools import BaseTool


def create_agent(
    tools: Sequence[BaseTool],
    model_name: ModelName = ModelName.SEED_1_8_251228,
    max_turns: int = 5,
    *,
    thinking_disabled: bool = True,
) -> ReActAgentBase:
    """
    创建复杂推理 ReAct Agent。
    默认带车控工具；可传入额外或替换的 tools。
    """
    client, model = create_client(model_name, AsyncArk)
    params = ResponseParams(thinking={"type": "disabled"}) if thinking_disabled else None
    return ReActAgentBase(
        tools=list(tools),
        model=model,
        client=client,
        params=params,
        max_turns=max_turns,
    )


__all__ = ["create_agent", "ReActAgent"]
