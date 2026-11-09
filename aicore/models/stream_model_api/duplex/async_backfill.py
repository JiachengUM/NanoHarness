"""Duplex 占位回灌兼容层（async continuation policy）。

async 工具调用先返回占位回执，真实结果在 session 级 ``TaskManager`` 中执行。
任务完成后，Duplex 需要把结果写入原问题，再用音频信号启动下一轮回复。
``DuplexAsyncBackfillScheduler`` 负责维护每个 question 的最小文本投影，
并串行化合成激活轮：

    TaskSuccessEvent(result)
      -> 将结果累积到来源 question 的本地投影
      -> conversation.item.update 整段替换该 question
      -> 记录一个尚未激活的结果 revision
      -> 等待当前 Duplex 回复进入终态
      -> 暂停麦克风并上传本地 PCM 触发音频
      -> PCM 上传和 commit 完成后记录该 result revision 已发送
      -> 触发音频自身的 transcription.done 仅被识别并丢弃
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from aicore.models.stream_model_api.duplex.duplex_agent_session import (
        DuplexAgentSession,
    )

logger = logging.getLogger(__name__)

_ASSET_DIR = Path(__file__).resolve().parent / "assets"
DEFAULT_ASYNC_TRIGGER_AUDIO_PATH = _ASSET_DIR / "async_results_ready.pcm"
DEFAULT_TOOL_TRIGGER_AUDIO_PATHS: Mapping[str, Path] = {
    "car_control": _ASSET_DIR / "car_control_ready.pcm",
    "media": _ASSET_DIR / "media_ready.pcm",
    "navigation": _ASSET_DIR / "navigation_ready.pcm",
    "QQ音乐单曲搜索": _ASSET_DIR / "music_song_ready.pcm",
    "QQ音乐歌单搜索": _ASSET_DIR / "music_playlist_ready.pcm",
    "QQ音乐专辑搜索": _ASSET_DIR / "music_album_ready.pcm",
    "地点搜索工具": _ASSET_DIR / "poi_search_ready.pcm",
    "websearch": _ASSET_DIR / "websearch_ready.pcm",
    "weather_agent": _ASSET_DIR / "weather_ready.pcm",
}

@dataclass(frozen=True, slots=True)
class DuplexAsyncCompatConfig:
    """Duplex 专用 async continuation 占位/回灌模拟配置。

    Canary 实验证明 ``conversation.item.create(role=user, input_text)`` 不会让
    文本进入后续音频轮次的推理上下文。因此兼容层用
    ``conversation.item.update`` 改写原 question，并通过
    ``tool_trigger_audio_paths`` 选择一段 16 kHz mono PCM16 激活语音；未知工具
    或一次激活覆盖多个工具时，回退到 ``trigger_audio_path`` 的通用提示。
    """

    trigger_audio_path: Path = DEFAULT_ASYNC_TRIGGER_AUDIO_PATH
    tool_trigger_audio_paths: Mapping[str, Path] = field(
        default_factory=lambda: dict(DEFAULT_TOOL_TRIGGER_AUDIO_PATHS)
    )

    def audio_path_for(self, tool_names: Collection[str]) -> Path:
        unique_names = {name for name in tool_names if name}
        if len(unique_names) == 1:
            tool_name = next(iter(unique_names))
            return self.tool_trigger_audio_paths.get(
                tool_name,
                self.trigger_audio_path,
            )
        return self.trigger_audio_path


def validate_trigger_audio(path: Path) -> None:
    """在会话启动前拒绝不可用的本地激活语音。"""

    if not path.is_file():
        raise FileNotFoundError(f"Duplex async trigger PCM not found: {path}")
    size = path.stat().st_size
    if size == 0 or size % 2:
        raise ValueError(
            "Duplex async trigger must be non-empty signed PCM16 audio: "
            f"{path}"
        )


@dataclass(frozen=True, slots=True)
class QuestionBackfill:
    """One terminal async result retained in a question's update projection."""

    task_id: str
    tool_name: str
    text: str


@dataclass(frozen=True, slots=True)
class BackfillActivation:
    """Exact async results covered by one synthetic provider activation."""

    activation_id: str
    question_ids: tuple[str, ...]
    task_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _BackfillRevision:
    question_id: str
    task_id: str
    tool_name: str


def render_backfill_context(
    transcript: str,
    backfills: Collection[QuestionBackfill],
) -> str:
    """Render the full replacement text for one original question item.

    Duplex update is replace, not append. Every write therefore carries the
    original transcript plus all terminal results already attached to the same
    question. Otherwise a later task would silently erase an earlier result.
    """

    rendered_results = "\n\n".join(
        "\n".join(
            (
                f"[异步工具结果 task_id={item.task_id}]",
                f"已完成工具：{item.tool_name.strip() or '未知工具'}",
                item.text,
            )
        )
        for item in backfills
    )
    original = transcript.strip()
    if not rendered_results:
        return original
    return (
        f"{original}\n\n" if original else ""
    ) + "[与本问题关联的异步工具结果]\n" + rendered_results


class DuplexAsyncBackfillScheduler:
    """串行化合成激活轮，不打断 Duplex 音频回复。

    每个任务完成后立即更新它所来源的 question。本地按 question 保存完整结果投影，
    因为 provider 的 update 是整段替换而不是 append；当前回复结束后，一帧 PCM 可以
    合并激活此前已更新的多个结果。
    """

    def __init__(
        self,
        *,
        session: DuplexAgentSession,
        config: DuplexAsyncCompatConfig,
        activation_observer: Callable[[BackfillActivation], None] | None = None,
        runtime_event_observer: Callable[[str], None] | None = None,
    ) -> None:
        for path in {
            config.trigger_audio_path,
            *config.tool_trigger_audio_paths.values(),
        }:
            validate_trigger_audio(path)
        self._session = session
        self._config = config
        self._activation_observer = activation_observer
        self._runtime_event_observer = runtime_event_observer
        self._result_revision = 0
        self._activated_result_revision = 0
        self._activation_requested = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._synthetic_pending = False
        # 每次更新都必须携带该 question 的全部历史结果，否则 replace 会覆盖前值。
        self._backfills_by_question: dict[str, list[QuestionBackfill]] = {}
        # 激活时按 revision 冻结精确的 question/task/tool 集合。
        self._backfill_revisions: dict[int, _BackfillRevision] = {}

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(
                self.run(),
                name="duplex-async-backfill-compat",
            )

    @property
    def task(self) -> asyncio.Task[None] | None:
        """Session-owned scheduler task exposed for lifecycle supervision."""

        return self._task

    @property
    def synthetic_pending(self) -> bool:
        """True while the synthetic activation audio owns the ASR lane.

        The flag is set before the trigger PCM upload and cleared by the first
        transcription.done afterwards. Observers may use it to distinguish
        synthetic ASR events from real user utterances.
        """

        return self._synthetic_pending

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self._synthetic_pending = False
        self._result_revision = 0
        self._activated_result_revision = 0
        self._activation_requested.clear()
        self._backfills_by_question.clear()
        self._backfill_revisions.clear()

    async def publish_backfill(
        self,
        *,
        question_id: str,
        task_id: str,
        tool_name: str,
        text: str,
    ) -> None:
        """Immediately update the origin question, then request activation."""

        transcript = self._session.question_transcript(question_id) or ""
        backfills = self._backfills_by_question.setdefault(question_id, [])
        backfills.append(
            QuestionBackfill(
                task_id=task_id,
                tool_name=tool_name,
                text=text,
            )
        )
        try:
            await self._session.submit_context_update(
                question_id,
                render_backfill_context(transcript, backfills),
            )
        except BaseException:
            # Do not let local projection get ahead of the provider. The
            # TaskManager listener propagates this write failure to the main
            # session instead of silently stopping all later backfills.
            backfills.pop()
            if not backfills:
                del self._backfills_by_question[question_id]
            raise
        self._result_revision += 1
        self._backfill_revisions[self._result_revision] = _BackfillRevision(
            question_id=question_id,
            task_id=task_id,
            tool_name=tool_name,
        )
        self._activation_requested.set()
        logger.info(
            "Duplex async question updated: task_id=%s question_id=%s revision=%s",
            task_id,
            question_id,
            self._result_revision,
        )

    def note_transcription_done(self) -> bool:
        """返回 True 表示该转写属于合成触发音频。

        Session 不得把触发音频自身的语音记为真实用户问题。该事件仅用于
        识别合成输入，不参与异步结果的发送状态或调度控制。
        """

        if not self._synthetic_pending:
            return False
        self._synthetic_pending = False
        return True

    async def run(self) -> None:
        while True:
            await self._activation_requested.wait()
            self._notify_runtime_event(
                "async_activation.waiting_idle "
                f"current_revision={self._activated_result_revision} "
                f"target_revision={self._result_revision}"
            )
            await self._session.wait_idle()
            if self._activated_result_revision >= self._result_revision:
                self._activation_requested.clear()
                continue

            target_revision = self._result_revision
            revisions = tuple(
                backfill
                for revision, backfill in self._backfill_revisions.items()
                if self._activated_result_revision < revision <= target_revision
            )
            self._session.mark_busy()
            logger.info(
                "Duplex async results activating: through_revision=%s",
                target_revision,
            )
            try:
                await self._activate(revisions)
            except BaseException:
                self._session.mark_idle()
                raise
            # Duplex 没有“模型已消费异步结果”的确认事件。PCM 与 commit 成功
            # 写入后只记录本次激活动作已发送；上传期间新增的 revision 留给下一轮。
            self._activated_result_revision = max(
                self._activated_result_revision,
                target_revision,
            )
            self._discard_revisions_through(self._activated_result_revision)
            if self._activated_result_revision >= self._result_revision:
                self._activation_requested.clear()
            logger.info(
                "Duplex async activation sent: through_revision=%s",
                self._activated_result_revision,
            )

    async def _activate(self, revisions: Collection[_BackfillRevision]) -> None:
        """用合成语音激活已经更新到服务端 question 的异步结果。"""

        self._synthetic_pending = True
        self._session.begin_synthetic_turn()
        try:
            tool_names = {revision.tool_name for revision in revisions}
            audio_path = self._config.audio_path_for(tool_names)
            activation = BackfillActivation(
                activation_id=f"backfill-{uuid4()}",
                question_ids=tuple(dict.fromkeys(
                    revision.question_id for revision in revisions
                )),
                task_ids=tuple(dict.fromkeys(
                    revision.task_id for revision in revisions
                )),
            )
            if self._activation_observer is not None:
                try:
                    self._activation_observer(activation)
                except Exception:
                    logger.exception(
                        "Duplex backfill activation observer failed; "
                        "continuing PCM activation"
                    )
            self._notify_runtime_event(
                "async_activation.started "
                f"activation_id={activation.activation_id} "
                f"questions={list(activation.question_ids)!r} "
                f"tasks={list(activation.task_ids)!r} "
                f"tools={sorted(tool_names)!r} "
                f"pcm={audio_path.name} bytes={audio_path.stat().st_size}"
            )
            await self._session.submit_audio_path(audio_path)
            self._notify_runtime_event(
                "async_activation.committed "
                f"activation_id={activation.activation_id} "
                f"tasks={list(activation.task_ids)!r}"
            )
        finally:
            # 麦克风只在合成 PCM 上传及 commit 期间暂停。服务端是否随后回传
            # transcription.done 不参与发送状态或调度控制。
            self._session.end_synthetic_turn()

    def _notify_runtime_event(self, message: str) -> None:
        if self._runtime_event_observer is None:
            return
        try:
            self._runtime_event_observer(message)
        except Exception:
            logger.exception(
                "Duplex runtime observer failed; continuing PCM activation"
            )

    def _discard_revisions_through(self, revision: int) -> None:
        for current in tuple(self._backfill_revisions):
            if current <= revision:
                del self._backfill_revisions[current]


__all__ = [
    "DEFAULT_ASYNC_TRIGGER_AUDIO_PATH",
    "DEFAULT_TOOL_TRIGGER_AUDIO_PATHS",
    "BackfillActivation",
    "DuplexAsyncCompatConfig",
    "DuplexAsyncBackfillScheduler",
    "QuestionBackfill",
    "render_backfill_context",
    "validate_trigger_audio",
]
