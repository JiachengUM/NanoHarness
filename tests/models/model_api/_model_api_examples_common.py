from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from collections.abc import Coroutine, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypeVar

from pydantic import BaseModel, Field
from rich import print

from aicore.models.doubao_models import ModelName
from aicore.models.model_api import (
    ModelAPIBackend,
    ModelCallParams,
    ModelEvent,
    ModelResponse,
    ModelStream,
    ModelTextDeltaEvent,
    ModelTextDoneEvent,
    ModelTextStartEvent,
    ModelToolCallEvent,
    UserMessage,
    ToolResultsMessage,
    ToolRunRequest,
    ToolRunResult,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


T = TypeVar("T")

DEFAULT_MODEL_NAME: Final = ModelName.SEED_1_8_251228
MODEL_NAMES: Final[list[ModelName]] = [
    DEFAULT_MODEL_NAME,
]
BACKENDS: Final[list[ModelAPIBackend]] = [
    "chat",
    "responses",
]


class WeatherArgs(BaseModel):
    location: str = Field(..., description="城市名称，例如上海、北京")


class SendMessageArgs(BaseModel):
    receiver: str = Field(..., description="消息接收人")
    content: str = Field(..., description="消息内容")


class DummyWeatherTool:
    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "根据城市名称查询该城市当日天气。"

    @property
    def args_schema(self) -> type[WeatherArgs]:
        return WeatherArgs


class DummySendMessageTool:
    @property
    def name(self) -> str:
        return "send_message"

    @property
    def description(self) -> str:
        return "向指定接收人发送一条文本消息。"

    @property
    def args_schema(self) -> type[SendMessageArgs]:
        return SendMessageArgs


@dataclass(frozen=True)
class ModelExampleCase:
    backend: ModelAPIBackend
    model_name: ModelName = DEFAULT_MODEL_NAME

    @property
    def label(self) -> str:
        return f"{self.backend}:{self.model_name.value}"


def iter_model_cases(
    *,
    backends: Iterable[ModelAPIBackend] = BACKENDS,
    model_names: Iterable[ModelName] = MODEL_NAMES,
) -> list[ModelExampleCase]:
    return [
        ModelExampleCase(backend=backend, model_name=model_name)
        for model_name in model_names
        for backend in backends
    ]


def short_params(
    *,
    max_output_tokens: int = 1024,
) -> ModelCallParams:
    return ModelCallParams(
        temperature=0,
        max_output_tokens=max_output_tokens,
        thinking="disabled",
    )


def run_async(awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def print_case_header(title: str, case: ModelExampleCase) -> None:
    print("\n" + "=" * 80)
    print(f"{title} | backend={case.backend}, model={case.model_name}")


def print_step(title: str) -> None:
    print("\n" + "-" * 80)
    print(f"[bold cyan]{title}[/bold cyan]")


def print_exception(context: str, exc: BaseException) -> None:
    print(f"[bold red]{context}[/bold red]")
    print(f"{type(exc).__name__}: {exc}")


def preview(value: object, *, limit: int = 600) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


async def collect_stream_events(
    stream: ModelStream[Any],
) -> list[ModelEvent]:
    return [event async for event in stream]


def text_input(text: str) -> UserMessage:
    return UserMessage(text=text)


def weather_result_input(
    run_id: str,
    *,
    city: str = "上海",
) -> ToolResultsMessage:
    output = {
        "city": city,
        "temperature": "20 到 26 摄氏度",
        "condition": "晴",
        "wind": "东北风 2 级",
    }
    return ToolResultsMessage(
        results=[
            ToolRunResult(
                run_id=run_id,
                output=json.dumps(output, ensure_ascii=False),
            )
        ],
    )


def tool_results_input(
    outputs: Mapping[str, str | Mapping[str, object]],
) -> ToolResultsMessage:
    results: list[ToolRunResult] = []
    for run_id, output in outputs.items():
        if isinstance(output, str):
            serialized = output
        else:
            serialized = json.dumps(output, ensure_ascii=False)
        results.append(ToolRunResult(run_id=run_id, output=serialized))
    return ToolResultsMessage(results=results)


def simulated_tool_output(tool_call: ToolRunRequest) -> Mapping[str, object]:
    if tool_call.tool_name == "get_weather":
        location = tool_call.arguments.get("location", "上海")
        return {
            "city": location,
            "temperature": "20 到 26 摄氏度",
            "condition": "晴",
            "wind": "东北风 2 级",
        }

    if tool_call.tool_name == "send_message":
        return {
            "status": "success",
            "receiver": tool_call.arguments.get("receiver", "张三"),
            "content": tool_call.arguments.get("content", ""),
        }

    return {
        "status": "success",
        "tool": tool_call.tool_name,
        "arguments": tool_call.arguments,
    }


def simulated_tool_results_input(
    tool_calls: Iterable[ToolRunRequest],
) -> ToolResultsMessage:
    return tool_results_input(
        {
            tool_call.run_id: simulated_tool_output(tool_call)
            for tool_call in tool_calls
        }
    )


def print_tool_calls(tool_calls: Iterable[ToolRunRequest]) -> None:
    tool_calls = list(tool_calls)
    if not tool_calls:
        print("tool_calls: []")
        return

    print(f"tool_calls: {len(tool_calls)}")
    for index, tool_call in enumerate(tool_calls, start=1):
        print(f"  [{index}] run_id: {tool_call.run_id}")
        print(f"      name: {tool_call.tool_name}")
        print(f"      arguments: {tool_call.arguments}")
        print(f"      raw_arguments: {tool_call.raw_arguments}")


def print_model_response(
    title: str,
    response: ModelResponse[Any] | None,
) -> None:
    print(f"\n[bold]{title}[/bold]")
    if response is None:
        print("response: None")
        return

    print(f"text: {preview(response.text)}")
    print(f"state: {type(response.state).__name__}")
    print_tool_calls(response.tool_calls)

    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        print(f"parsed: {parsed}")

    if response.metadata:
        print(f"metadata keys: {list(response.metadata.keys())}")


def print_state_dump(title: str, dump: object) -> None:
    print(f"\n[bold]{title}[/bold]")
    for attr in ("object", "format", "format_version", "metadata"):
        print(f"{attr}: {getattr(dump, attr, None)}")
    print(f"serialized: {preview(getattr(dump, 'serialized', None))}")


def print_model_event(event: ModelEvent) -> None:
    if isinstance(event, ModelTextStartEvent):
        print("event: model.text.start")
    elif isinstance(event, ModelTextDeltaEvent):
        print(f"event: model.text.delta | delta={preview(event.delta, limit=80)}")
    elif isinstance(event, ModelTextDoneEvent):
        print(f"event: model.text.done | text={preview(event.text, limit=160)}")
    elif isinstance(event, ModelToolCallEvent):
        print(
            "event: model.tool_call | "
            f"name={event.tool_call.tool_name}, "
            f"run_id={event.tool_call.run_id}, "
            f"arguments={event.tool_call.arguments}"
        )
    else:
        print(f"event: {event}")


def print_event_summary(events: Iterable[ModelEvent]) -> None:
    counts = Counter(event.type for event in events)
    print("\n[bold]event summary[/bold]")
    if not counts:
        print("events: []")
        return

    for event_type, count in counts.items():
        print(f"{event_type}: {count}")
