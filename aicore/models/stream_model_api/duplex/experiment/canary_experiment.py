"""Manual Duplex context-ingestion canary experiment.

This is deliberately separate from the DynamicTask production path. It tests
whether text written with ``conversation.item.create`` or
``conversation.item.update`` is visible to the inference turn started by the
same synthetic PCM. No tool, TaskManager, placeholder marker, or real search
result participates in the experiment.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from aicore.models.stream_model_api.duplex.config import (
    DuplexConfig,
    build_duplex_session_config,
)
from aicore.models.stream_model_api.duplex.diagnostics import DuplexDiagnostics
from aicore.models.stream_model_api.duplex.duplex_client import DuplexClient
from aicore.models.stream_model_api.duplex.duplex_agent_session import (
    DEFAULT_OUTPUT_AUDIO_PATH,
    DuplexAgentSession,
)
from aicore.models.stream_model_api.duplex.duplex_stream_model_api import (
    DuplexStreamModelAPI,
)
from aicore.models.stream_model_api.duplex.websocket_transport import (
    DuplexWebSocketTransport,
)
from aicore.models.stream_model_api.events import (
    StreamModelEvent,
    StreamTranscriptionDoneEvent,
)
from aicore.models.stream_model_api.inputs import (
    ContextItemRetrieveInput,
    ContextItemUpdateInput,
)
from aicore.runtime.task import TaskManager


type CanaryMode = Literal[
    "control",
    "create-short",
    "create-long",
    "update-short",
    "update-long",
]

CANARY_TRIGGER_AUDIO_PATH = (
    Path(__file__).resolve().parent.parent / "assets" / "async_results_ready.pcm"
)

SYSTEM_PROMPT = """
你是上下文可见性实验助手。

用户首先会说一句准备实验的话。此时只回复“准备好了”。
之后会听到一段固定的本地激活音频，内容大意是工具已经完成、请根据新增结果回答。
收到该激活音频后：

1. 检查当前会话上下文是否明确包含“验证标记”和“结果数值”两个字段。
2. 如果都能看到，只回复：“标记是 <原值>，数值是 <原值>”。必须逐字复述，不得猜测或改写。
3. 如果任一字段看不到，只回复：“没有看到验证数据”。
4. 不得调用工具，不得根据字段名猜测值，不得提及内部协议或实验实现。
""".strip()

_LONG_PADDING_BLOCK = (
    "背景材料：这段文本只用于制造上下文长度，不包含验证答案。"
    "请忽略其中的日期、地点、人物和数字描述。"
)


class _CanaryAgentSession(DuplexAgentSession):
    """Expose the first real ASR item only to this diagnostic coordinator."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.first_question: asyncio.Future[tuple[str, str]] = (
            asyncio.get_running_loop().create_future()
        )

    def _handle_audio_event(self, event: StreamModelEvent) -> None:
        super()._handle_audio_event(event)
        if (
            not self.first_question.done()
            and isinstance(event, StreamTranscriptionDoneEvent)
            and event.item_id
        ):
            # The canary controls exactly one real microphone turn. Suppress
            # ambient audio again before mutating context and uploading the
            # synthetic activation PCM.
            self.begin_synthetic_turn()
            self.first_question.set_result((event.item_id, event.transcript))


@dataclass(frozen=True, slots=True)
class CanaryCase:
    mode: CanaryMode
    marker: str
    value: str
    padding_chars: int = 6000

    @property
    def uses_update(self) -> bool:
        return self.mode.startswith("update-")

    @property
    def uses_create(self) -> bool:
        return self.mode.startswith("create-")

    @property
    def is_long(self) -> bool:
        return self.mode.endswith("-long")

    def diagnostic_text(self) -> str:
        facts = f"验证标记：{self.marker}\n结果数值：{self.value}"
        if not self.is_long:
            return facts
        repeats = (self.padding_chars // len(_LONG_PADDING_BLOCK)) + 1
        padding = (_LONG_PADDING_BLOCK * repeats)[: self.padding_chars]
        # Put the canary in the middle so the experiment does not accidentally
        # test only a provider's leading/trailing truncation behavior.
        midpoint = len(padding) // 2
        return f"{padding[:midpoint]}\n{facts}\n{padding[midpoint:]}"


def build_canary_case(
    mode: CanaryMode,
    *,
    marker: str | None = None,
    value: str | None = None,
    padding_chars: int = 6000,
) -> CanaryCase:
    return CanaryCase(
        mode=mode,
        marker=marker or f"ZEBRA-{secrets.token_hex(3).upper()}",
        value=value or f"{secrets.randbelow(9000) + 1000}.{secrets.randbelow(10)}",
        padding_chars=padding_chars,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test Duplex create/update context visibility with a canary.",
    )
    parser.add_argument(
        "--mode",
        choices=(
            "control",
            "create-short",
            "create-long",
            "update-short",
            "update-long",
        ),
        required=True,
    )
    parser.add_argument("--marker", default=None)
    parser.add_argument("--value", default=None)
    parser.add_argument("--padding-chars", type=int, default=6000)
    parser.add_argument("--activation-delay", type=float, default=1.0)
    parser.add_argument("--case-log", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--endpoint-url", default=None)
    parser.add_argument(
        "--auth-mode",
        choices=("auto", "app-key", "x-api-key", "bearer"),
        default="app-key",
    )
    parser.add_argument("--output-audio", default=str(DEFAULT_OUTPUT_AUDIO_PATH))
    return parser.parse_args(argv)


async def inject_canary_after_first_reply(
    session: DuplexAgentSession,
    case: CanaryCase,
    *,
    question_ready: asyncio.Future[tuple[str, str]],
    activation_delay: float,
    runtime_event: Callable[[str], None],
) -> None:
    """Wait for the first real question/reply, mutate context, then activate."""

    await asyncio.to_thread(input, "[CANARY] 按回车打开一轮麦克风：")
    session.end_synthetic_turn()
    question_id, original = await question_ready

    # ``_reply_idle`` becomes set only after provider audio completes and local
    # playback drains. This keeps the synthetic canary turn from interrupting
    # the baseline “准备好了” reply.
    await session.wait_idle()
    text = case.diagnostic_text()
    if case.uses_create:
        # Keep ``conversation.item.create`` inside this provider-specific
        # experiment. It is not a usable StreamModelAPI observation primitive.
        await session.model_api.client.conversation_item_create(
            [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                }
            ]
        )
    elif case.uses_update:
        # update replaces the original question. Preserve its transcript so
        # this experiment changes only the append-vs-update transport.
        updated = f"{original}\n\n{text}" if original else text
        await session.model_api.submit(
            ContextItemUpdateInput(item_id=question_id, text=updated)
        )

    runtime_event(
        "canary_injected "
        f"mode={case.mode} question_id={question_id} marker={case.marker} "
        f"value={case.value} text_chars={len(text)}"
    )

    # Retrieve is observational only. Update uses the exact mutated item;
    # create/control query recent context because create returns no item id.
    await session.model_api.submit(
        ContextItemRetrieveInput(
            item_id=question_id if case.uses_update else None,
        )
    )
    await asyncio.sleep(max(0.0, activation_delay))

    session.mark_busy()
    session.begin_synthetic_turn()
    try:
        await session.submit_audio_path(CANARY_TRIGGER_AUDIO_PATH)
    finally:
        # Keep the microphone suspended: this diagnostic needs no additional
        # real user turn after the synthetic activation.
        pass


async def async_main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.padding_chars < 0:
        raise ValueError("--padding-chars must be non-negative")
    if args.activation_delay < 0:
        raise ValueError("--activation-delay must be non-negative")

    case = build_canary_case(
        args.mode,
        marker=args.marker,
        value=args.value,
        padding_chars=args.padding_chars,
    )
    log_path = Path(args.case_log).expanduser() if args.case_log else None
    if log_path is not None and not log_path.parent.is_dir():
        raise ValueError(f"case log parent does not exist: {log_path.parent}")
    config = DuplexConfig(instructions=SYSTEM_PROMPT)
    if args.model:
        config.model = args.model
    if args.endpoint_url:
        config.endpoint_url = args.endpoint_url

    with DuplexDiagnostics(log_path) as diagnostics:
        diagnostics.record_session(
            model=config.model,
            tool_call_mode=f"canary:{case.mode}",
            tool_names=[],
        )
        diagnostics.runtime_event(
            "canary_expected "
            f"mode={case.mode} marker={case.marker} value={case.value}"
        )
        print(
            f"[CANARY] mode={case.mode} marker={case.marker} value={case.value}\n"
            "[CANARY] 接下来按回车打开麦克风，只说：准备开始上下文实验。"
        )

        transport = DuplexWebSocketTransport.from_config(
            config,
            auth_mode=args.auth_mode,
            event_observer=diagnostics.duplex_event,
        )
        client = DuplexClient(transport=transport)
        session_config, extension = build_duplex_session_config(
            config,
            session_id=client.session_id,
        )
        model_api = DuplexStreamModelAPI(
            client=client,
            session=session_config,
            extension=extension,
            tools=[],
        )
        session = _CanaryAgentSession(
            model_api=model_api,
            tools=[],
            task_manager=TaskManager(max_concurrency=10),
            tool_call_mode="sync",
            config=config,
            output_audio_path=Path(args.output_audio),
            context_diagnostics=False,
            mic_mode="continuous",
        )
        session.begin_synthetic_turn()

        session_task = asyncio.create_task(session.run(), name="duplex-canary-session")
        injection_task = asyncio.create_task(
            inject_canary_after_first_reply(
                session,
                case,
                question_ready=session.first_question,
                activation_delay=args.activation_delay,
                runtime_event=diagnostics.runtime_event,
            ),
            name="duplex-canary-injection",
        )
        try:
            done, _ = await asyncio.wait(
                {session_task, injection_task},
                return_when=asyncio.FIRST_EXCEPTION,
            )
            if injection_task in done:
                injection_error = injection_task.exception()
                if injection_error is not None:
                    session_task.cancel()
                    await asyncio.gather(session_task, return_exceptions=True)
                    raise RuntimeError("Duplex canary injection failed") from injection_error
            await session_task
        finally:
            if not injection_task.done():
                injection_task.cancel()
            await asyncio.gather(injection_task, return_exceptions=True)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()


__all__ = [
    "CanaryCase",
    "SYSTEM_PROMPT",
    "build_canary_case",
    "inject_canary_after_first_reply",
    "main",
    "parse_args",
]
