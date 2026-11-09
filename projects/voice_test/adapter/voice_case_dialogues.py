"""语音链路专用：在 case 内冷启动之间插入等待，不改动 AutoTestAndRLDataGenerator。"""

from __future__ import annotations

import asyncio
from typing import Any

from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
)
from projects.mind.mem.auto_test_script.case_schema import TestCase
from projects.voice_test.adapter._logger import get_vt_logger
from projects.voice_test.schemas.browser_schemas import (
    CountdownWaitEvent,
)
from projects.voice_test.adapter.browser_voice_adapter import BrowserVoiceAdapter
from projects.voice_test.config.adapter_config import VoiceAdapterConfig

_log = get_vt_logger("dialogues")


async def await_countdown_wait(
    adapter: BrowserVoiceAdapter | None,
    seconds: int,
    label: str,
) -> None:
    wait_sec = int(seconds or 0)
    if wait_sec <= 0:
        return
    if adapter is not None:
        await adapter.push_event(CountdownWaitEvent(label=label, seconds=wait_sec))
    for _ in range(wait_sec):
        await asyncio.sleep(1)
    if adapter is not None:
        await adapter.push_event(CountdownWaitEvent(label=label, seconds=0))


async def run_voice_case_dialogues(
    auto_test: AutoTestAndRLDataGenerator,
    case: TestCase,
    adapter: BrowserVoiceAdapter,
    cfg: VoiceAdapterConfig,
) -> tuple[str, list[dict], bool, str | None]:
    """包装 aauto_chat_test：每段冷启动对话结束后按语音配置等待。

    首轮响应时间：仅 case 内第一个 dialogue 采集，挂到 adapter.case_first_response_ms。
    """
    dialogue_total = len(case.user_query_lists)
    state = {"index": 0}
    orig_chat = auto_test.aauto_chat_test
    case_id = getattr(case, "case_id", "?")
    # 用 adapter 的带 sid/run 前缀 logger，让 dialogues 日志也带前缀
    dlog = getattr(adapter, "_log", _log)
    dlog.info("case enter case_id=%s dialogues=%d", case_id, dialogue_total)
    # case 级首轮响应时间（ms）；仅第一个 dialogue 采集，None=未采集或超时
    case_first_response_ms: float | None = None

    async def chat_with_waits(
        bot_to_test: Any,
        fake_person: Any,
        start_query: str,
        max_round: int = 8,
    ) -> Any:
        nonlocal case_first_response_ms
        i = state["index"]
        dlog.info("case=%s dialogue %d/%d start", case_id, i + 1, dialogue_total)
        result = await orig_chat(bot_to_test, fake_person, start_query, max_round)
        # 仅 case 内首个 dialogue 采集首轮响应时间
        if i == 0:
            case_first_response_ms = adapter.take_last_first_response_ms()
            dlog.info("case=%s first_response_ms=%s", case_id, case_first_response_ms)
        # 仅在下一段冷启动之前等待记忆落库；最后一轮播完直接结束或进入下个 case。
        if i < dialogue_total - 1:
            await await_countdown_wait(adapter, cfg.memory_extraction_wait_sec, "等待记忆提取")
        state["index"] = i + 1
        dlog.info("case=%s dialogue %d/%d done", case_id, i + 1, dialogue_total)
        return result

    auto_test.aauto_chat_test = chat_with_waits  # type: ignore[method-assign]
    try:
        result = await auto_test._a_run_case_dialogues(case)
        # 把首轮响应时间挂到 adapter，供 _run_test_session 取走
        adapter.case_first_response_ms = case_first_response_ms
        return result
    finally:
        auto_test.aauto_chat_test = orig_chat
        dlog.info("case exit case_id=%s", case_id)
