from __future__ import annotations

import asyncio

import pytest

from aicore.models.stream_model_api.duplex.experiment.canary_experiment import (
    build_canary_case,
    inject_canary_after_first_reply,
    parse_args,
)
from aicore.models.stream_model_api.inputs import (
    ContextItemRetrieveInput,
    ContextItemUpdateInput,
)


def test_short_canary_contains_only_unknown_facts() -> None:
    case = build_canary_case(
        "create-short",
        marker="ZEBRA-7319",
        value="17.3",
    )

    assert case.diagnostic_text() == "验证标记：ZEBRA-7319\n结果数值：17.3"


def test_long_canary_places_same_facts_inside_padding() -> None:
    case = build_canary_case(
        "update-long",
        marker="ZEBRA-7319",
        value="17.3",
        padding_chars=6000,
    )

    text = case.diagnostic_text()
    assert len(text) > 6000
    assert text.count("ZEBRA-7319") == 1
    assert text.count("17.3") == 1
    assert 2500 < text.index("ZEBRA-7319") < 3500


def test_control_mode_writes_no_context_item() -> None:
    case = build_canary_case(
        "control",
        marker="ZEBRA-7319",
        value="17.3",
    )

    assert case.uses_create is False
    assert case.uses_update is False


def test_canary_cli_requires_explicit_mode() -> None:
    with pytest.raises(SystemExit):
        parse_args([])

    args = parse_args(["--mode", "create-short", "--activation-delay", "0"])
    assert args.mode == "create-short"
    assert args.activation_delay == 0


def test_context_update_rejects_empty_item_id() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ContextItemUpdateInput(item_id=" ", text="canary")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_create_count", "expects_update"),
    [
        ("control", 0, False),
        ("create-short", 1, False),
        ("update-short", 0, True),
    ],
)
async def test_canary_injection_preserves_provider_event_order_and_question_id(
    mode: str,
    expected_create_count: int,
    expects_update: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steps: list[tuple[str, object | None]] = []

    async def fake_to_thread(*_: object) -> None:
        steps.append(("user_ready", None))

    class Client:
        async def conversation_item_create(self, items: object) -> None:
            steps.append(("create", items))

    class ModelAPI:
        client = Client()

        async def submit(self, input: object) -> None:
            steps.append(("submit", input))

    class Session:
        model_api = ModelAPI()

        def end_synthetic_turn(self) -> None:
            steps.append(("microphone_open", None))

        async def wait_idle(self) -> None:
            steps.append(("reply_idle", None))

        def mark_busy(self) -> None:
            steps.append(("mark_busy", None))

        def begin_synthetic_turn(self) -> None:
            steps.append(("microphone_suspended", None))

        async def submit_audio_path(self, path: object) -> None:
            steps.append(("activation_pcm", path))

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    ready: asyncio.Future[tuple[str, str]] = (
        asyncio.get_running_loop().create_future()
    )
    ready.set_result(("question-1", "准备开始上下文实验"))
    case = build_canary_case(  # type: ignore[arg-type]
        mode,
        marker="ZEBRA-7319",
        value="17.3",
    )

    await inject_canary_after_first_reply(
        Session(),  # type: ignore[arg-type]
        case,
        question_ready=ready,
        activation_delay=0,
        runtime_event=lambda message: steps.append(("runtime", message)),
    )

    assert [name for name, _ in steps[:3]] == [
        "user_ready",
        "microphone_open",
        "reply_idle",
    ]
    submitted = [value for name, value in steps if name == "submit"]
    assert isinstance(submitted[-1], ContextItemRetrieveInput)
    creates = [value for name, value in steps if name == "create"]
    assert len(creates) == expected_create_count
    if expects_update:
        assert isinstance(submitted[0], ContextItemUpdateInput)
        assert submitted[0].item_id == "question-1"
        assert submitted[0].text.startswith("准备开始上下文实验\n\n")
    else:
        assert len(submitted) == 1
    if creates:
        assert creates[0][0]["content"][0]["text"] == case.diagnostic_text()
    assert [name for name, _ in steps[-3:]] == [
        "mark_busy",
        "microphone_suspended",
        "activation_pcm",
    ]
