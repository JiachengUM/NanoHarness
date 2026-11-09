from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from aicore.models.stream_model_api.duplex.async_backfill import (
    BackfillActivation,
    DuplexAsyncBackfillScheduler,
    DuplexAsyncCompatConfig,
)


class FakeBackfillSession:
    def __init__(self) -> None:
        self.transcripts: dict[str, str] = {}
        self.updates: list[tuple[str, str]] = []
        self.audio_paths: list[Path] = []
        self.reject_next_update = False
        self.idle = asyncio.Event()
        self.synthetic_turns = 0

    def question_transcript(self, question_id: str) -> str | None:
        return self.transcripts.get(question_id)

    async def submit_context_update(self, item_id: str, text: str) -> None:
        if self.reject_next_update:
            self.reject_next_update = False
            raise RuntimeError("update rejected")
        self.updates.append((item_id, text))

    async def wait_idle(self) -> None:
        await self.idle.wait()

    def mark_busy(self) -> None:
        self.idle.clear()

    def mark_idle(self) -> None:
        self.idle.set()

    def begin_synthetic_turn(self) -> None:
        self.synthetic_turns += 1

    def end_synthetic_turn(self) -> None:
        self.synthetic_turns -= 1

    async def submit_audio_path(self, path: Path) -> None:
        self.audio_paths.append(path)


def make_config(tmp_path: Path) -> tuple[DuplexAsyncCompatConfig, Path, Path]:
    generic = tmp_path / "generic.pcm"
    websearch = tmp_path / "websearch.pcm"
    generic.write_bytes(b"\x01\x00")
    websearch.write_bytes(b"\x02\x00")
    return (
        DuplexAsyncCompatConfig(
            trigger_audio_path=generic,
            tool_trigger_audio_paths={"websearch": websearch},
        ),
        generic,
        websearch,
    )


async def wait_until(predicate) -> None:
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(0)


def test_async_compat_selects_specific_audio_only_for_one_known_tool(
    tmp_path: Path,
) -> None:
    config, generic, websearch = make_config(tmp_path)

    assert config.audio_path_for({"websearch"}) == websearch
    assert config.audio_path_for({"unknown"}) == generic
    assert config.audio_path_for({"websearch", "unknown"}) == generic


@pytest.mark.asyncio
async def test_backfills_accumulate_per_question_without_cross_contamination(
    tmp_path: Path,
) -> None:
    config, _, _ = make_config(tmp_path)
    session = FakeBackfillSession()
    session.transcripts.update({"q1": "查天气", "q2": "打开空调"})
    scheduler = DuplexAsyncBackfillScheduler(
        session=session,  # type: ignore[arg-type]
        config=config,
    )

    await scheduler.publish_backfill(
        question_id="q1",
        task_id="task-a",
        tool_name="websearch",
        text="晴天",
    )
    await scheduler.publish_backfill(
        question_id="q1",
        task_id="task-b",
        tool_name="websearch",
        text="最高 30 度",
    )
    await scheduler.publish_backfill(
        question_id="q2",
        task_id="task-c",
        tool_name="car_control",
        text="空调已打开",
    )

    assert [item_id for item_id, _ in session.updates] == ["q1", "q1", "q2"]
    q1 = session.updates[1][1]
    q2 = session.updates[2][1]
    assert "查天气" in q1 and "晴天" in q1 and "最高 30 度" in q1
    assert "空调已打开" not in q1
    assert "打开空调" in q2 and "空调已打开" in q2
    assert "晴天" not in q2


@pytest.mark.asyncio
async def test_failed_update_does_not_advance_local_question_projection(
    tmp_path: Path,
) -> None:
    config, _, _ = make_config(tmp_path)
    session = FakeBackfillSession()
    session.transcripts["q1"] = "查天气"
    scheduler = DuplexAsyncBackfillScheduler(
        session=session,  # type: ignore[arg-type]
        config=config,
    )

    session.reject_next_update = True
    with pytest.raises(RuntimeError, match="update rejected"):
        await scheduler.publish_backfill(
            question_id="q1",
            task_id="task-a",
            tool_name="websearch",
            text="不应保留",
        )
    await scheduler.publish_backfill(
        question_id="q1",
        task_id="task-b",
        tool_name="websearch",
        text="应当保留",
    )

    assert len(session.updates) == 1
    assert "应当保留" in session.updates[0][1]
    assert "不应保留" not in session.updates[0][1]


@pytest.mark.asyncio
async def test_result_arriving_during_activation_receives_a_second_activation(
    tmp_path: Path,
) -> None:
    config, generic, websearch = make_config(tmp_path)
    session = FakeBackfillSession()
    session.transcripts["q1"] = "查两个任务"
    scheduler = DuplexAsyncBackfillScheduler(
        session=session,  # type: ignore[arg-type]
        config=config,
    )
    session.idle.set()
    scheduler.start()
    try:
        await scheduler.publish_backfill(
            question_id="q1",
            task_id="task-a",
            tool_name="websearch",
            text="结果 A",
        )
        await wait_until(lambda: session.audio_paths == [websearch])
        # The local microphone is released as soon as PCM upload + commit
        # returns; downstream provider events do not control this lifecycle.
        assert session.synthetic_turns == 0

        await scheduler.publish_backfill(
            question_id="q1",
            task_id="task-b",
            tool_name="car_control",
            text="结果 B",
        )
        assert scheduler.note_transcription_done() is True
        session.mark_idle()
        await wait_until(lambda: len(session.audio_paths) == 2)

        assert session.audio_paths == [websearch, generic]
        assert scheduler.note_transcription_done() is True
        assert session.synthetic_turns == 0
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_activation_submission_does_not_wait_for_provider_ack(
    tmp_path: Path,
) -> None:
    config, _, _ = make_config(tmp_path)
    session = FakeBackfillSession()
    session.transcripts["q1"] = "查天气"
    session.idle.set()
    scheduler = DuplexAsyncBackfillScheduler(
        session=session,  # type: ignore[arg-type]
        config=config,
    )
    scheduler.start()
    await scheduler.publish_backfill(
        question_id="q1",
        task_id="task-a",
        tool_name="websearch",
        text="晴天",
    )

    await wait_until(lambda: len(session.audio_paths) == 1)

    task = scheduler.task
    assert task is not None and not task.done()
    assert scheduler._activated_result_revision == 1
    assert session.synthetic_turns == 0
    await scheduler.stop()


@pytest.mark.asyncio
async def test_activation_observer_receives_exact_frozen_task_batch(
    tmp_path: Path,
) -> None:
    config, _, _ = make_config(tmp_path)
    session = FakeBackfillSession()
    session.transcripts.update({"q1": "问题一", "q2": "问题二"})
    activations: list[BackfillActivation] = []
    runtime_events: list[str] = []
    scheduler = DuplexAsyncBackfillScheduler(
        session=session,  # type: ignore[arg-type]
        config=config,
        activation_observer=activations.append,
        runtime_event_observer=runtime_events.append,
    )

    await scheduler.publish_backfill(
        question_id="q1", task_id="task-a", tool_name="websearch", text="A"
    )
    await scheduler.publish_backfill(
        question_id="q2", task_id="task-b", tool_name="weather", text="B"
    )
    session.idle.set()
    scheduler.start()
    try:
        await wait_until(lambda: len(activations) == 1)
        assert activations[0].activation_id.startswith("backfill-")
        assert activations[0].question_ids == ("q1", "q2")
        assert activations[0].task_ids == ("task-a", "task-b")
        assert len(session.audio_paths) == 1
        assert runtime_events[0].startswith("async_activation.waiting_idle ")
        assert runtime_events[1].startswith("async_activation.started ")
        assert "tasks=['task-a', 'task-b']" in runtime_events[1]
        assert "pcm=generic.pcm bytes=2" in runtime_events[1]
        assert runtime_events[2].startswith("async_activation.committed ")
    finally:
        await scheduler.stop()
