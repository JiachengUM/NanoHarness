from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from pydantic import BaseModel, Field

from aicore.tools import BaseTool
from aicore.agents.events import (
    DefaultReActEventTranslator,
    ReActEvent,
    ReActEventTranslator,
    ReActCompletedEvent,
    ReActFailedEvent,
    ReActTextDeltaEvent,
    ReActToolResultsDoneEvent,
)
from projects.mind.demo.sgm_processor.base import AgentBase, RunParams, SystemPrompt
from aicore.models.credentials import AsyncArk, ModelName, create_client
from aicore.models.responses import ResponseParams

from projects.mind.complex_reasoning.tools import get_default_tools


class HistoryItem(BaseModel):
    q: str = Field(description="历史问题")
    a: str = Field(description="历史回答")


class AgentDoStreamRequest(BaseModel):
    chat_id: str
    question_id: str
    query: str
    history: list[HistoryItem] = Field(default_factory=list)
    intent_type: str = Field(default="复杂推理")
    car_info: dict[str, Any] = Field(default_factory=dict)


class StreamChunk(BaseModel):
    error_code: int = Field(default=0)
    tts_text: str = Field(default="")
    content: str = Field(default="")
    rc: int = Field(default=1)
    observation: str | None = Field(default=None)
    plugin_name: str | None = Field(default=None)
    debug_info: dict[str, Any] | None = Field(default=None)
    log_id: str | None = Field(default=None)
    intent_type: str = Field(default="复杂推理")

    @classmethod
    def from_tool_results(
        cls,
        tool_results: list[dict[str, Any]],
        *,
        intent_type: str,
    ) -> "list[StreamChunk]":
        chunks = []
        for result in tool_results:
            raw = result.get("output")
            if not raw:
                continue
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(parsed, dict):
                continue
            chunk = cls._make_chunk(parsed, intent_type)
            if chunk:
                chunks.append(chunk)
        return chunks

    @classmethod
    def _make_chunk(cls, parsed: dict[str, Any], intent_type: str) -> "StreamChunk | None":
        if poi_list := parsed.get("list"):
            return cls(
                rc=1,
                observation=json.dumps({"list": poi_list}, ensure_ascii=False),
                plugin_name="poi_result",
                intent_type=intent_type,
            )

        if forecasts := parsed.get("forecasts"):
            return cls(
                rc=1,
                observation=json.dumps(forecasts, ensure_ascii=False),
                plugin_name="weather_result",
                intent_type=intent_type,
            )

        # 车控 / 媒体 / 导航：含 observation 字段才展示
        observation = parsed.get("observation")
        if observation is None:
            return None
        return cls(
            rc=1,
            observation=json.dumps(observation, ensure_ascii=False) if isinstance(observation, dict) else str(observation),
            plugin_name="function_call",
            intent_type=intent_type,
        )


class SGMChunkTranslator:
    """将 ReActEvent 映射为 SGM StreamChunk。"""

    def __init__(self, req: AgentDoStreamRequest) -> None:
        self.req = req
        self.terminal_chunk: StreamChunk | None = None

    def __call__(self, event: ReActEvent) -> list[StreamChunk]:
        if isinstance(event, ReActTextDeltaEvent):
            if not event.delta:
                return []
            return [
                StreamChunk(
                    tts_text=event.delta,
                    content=event.delta,
                    rc=1,
                    intent_type=self.req.intent_type,
                )
            ]

        if isinstance(event, ReActToolResultsDoneEvent):
            return StreamChunk.from_tool_results(
                event.tool_results,
                intent_type=self.req.intent_type,
            )

        if isinstance(event, ReActFailedEvent):
            self.terminal_chunk = StreamChunk(
                error_code=1,
                rc=2,
                debug_info={},
                log_id=self.req.question_id,
                intent_type=self.req.intent_type,
            )
            return []

        if isinstance(event, ReActCompletedEvent):
            self.terminal_chunk = StreamChunk(
                rc=2,
                debug_info={},
                log_id=self.req.question_id,
                intent_type=self.req.intent_type,
            )
            return []

        return []


_SYSTEM_PROMPT = SystemPrompt(
    role="你是一个智能车载助手，可以帮助用户查询天气、搜索地点、控制车辆、播放媒体、导航等。",
    guidelines=[
        "在调用工具之前，先用一句话简要告知用户你将要做什么，例如: 好的，我来帮您查一下天气",
        "根据用户需求，选择合适的工具完成任务，不要重复调用同一工具。",
    ],
)


class SGMAgent(AgentBase):
    """
    在 AgentBase 的 ReAct 事件流之上，映射成 SGM 的 StreamChunk 输出。
    """
    def __init__(
        self,
        run_params: RunParams,
        tools: list[BaseTool],
        *,
        event_translator: ReActEventTranslator | None = None,
    ) -> None:
        super().__init__(_SYSTEM_PROMPT, run_params=run_params, tools=tools)
        self.event_translator = event_translator or DefaultReActEventTranslator()

    @classmethod
    def create(
        cls,
        chat_id: str,
        *,
        model_name: ModelName = ModelName.SEED_1_8_251228,
        max_turns: int = 5,
        thinking_disabled: bool = True,
        event_translator: ReActEventTranslator | None = None,
    ) -> "SGMAgent":
        client, model = create_client(model_name, AsyncArk)
        params = ResponseParams(thinking={"type": "disabled"}) if thinking_disabled else None
        run_params = RunParams(
            model=model,
            client=client,
            params=params,
            max_turns=max_turns,
        )
        return cls(
            run_params=run_params,
            tools=get_default_tools(chat_id),
            event_translator=event_translator,
        )

    async def astream(self, req: AgentDoStreamRequest) -> AsyncGenerator[StreamChunk, None]:
        # 首包：对齐现有接口，先发一个 rc=0 的初始化事件。
        yield StreamChunk(rc=0, intent_type=req.intent_type)

        chunk_translator = SGMChunkTranslator(req)

        async for event in super().astream(
            req.query,
            event_listeners=[],
            event_translator=self.event_translator,
        ):
            for chunk in chunk_translator(event):
                yield chunk

        if chunk_translator.terminal_chunk is not None:
            yield chunk_translator.terminal_chunk
        else:
            # 走完循环但没收到 Completed/Failed，说明中途出问题
            yield StreamChunk(
                error_code=1,
                rc=2,
                debug_info={},
                log_id=req.question_id,
                intent_type=req.intent_type,
            )


__all__ = [
    "HistoryItem",
    "AgentDoStreamRequest",
    "StreamChunk",
    "SGMAgent",
]
