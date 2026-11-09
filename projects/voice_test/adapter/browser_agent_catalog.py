"""voice-test 被测 Agent 注册表。

新增 Agent 只需在 VOICE_TEST_AGENT_REGISTRY 加一条，例如：
  VoiceTestTarget.AGENT_V1: VoiceTestAgentSpec(..., bot_for_adapter=browser_text_agent_v1_for_adapter)
  VoiceTestTarget.OLD_COMPLEX: VoiceTestAgentSpec(..., bot_for_adapter=browser_text_old_complex_for_adapter)

需要 inject task_config 时用 browser_text_bot_for_adapter(adapter, XxxBot, prepare_fn)；
case 原样传入时用 browser_text_bot_for_adapter(adapter, XxxBot) 或对应快捷函数。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from projects.voice_test.schemas.browser_schemas import VoiceTestTarget
from projects.voice_test.adapter.browser_text_adapter import BrowserTextAdapter
from projects.voice_test.bots.browser_text_bot import (
    browser_text_agent_v1_for_adapter,
    browser_text_old_complex_for_adapter,
)
from projects.voice_test.adapter.browser_voice_adapter import BrowserVoiceAdapter
from projects.voice_test.bots.browser_voice_bot import browser_voice_bot_for_adapter

TestMode = Literal["voice", "text"]

BotFactory = Callable[[BrowserVoiceAdapter | BrowserTextAdapter], type[Any]]


@dataclass(frozen=True)
class VoiceTestAgentSpec:
    label: str
    description: str
    channel: TestMode
    bot_for_adapter: BotFactory


# ========== 新增 Agent 只改这里 ==========
VOICE_TEST_AGENT_REGISTRY: dict[VoiceTestTarget, VoiceTestAgentSpec] = {
    VoiceTestTarget.VOICE: VoiceTestAgentSpec(
        label="语音",
        description="浏览器麦克风收音 + TTS 播报",
        channel="voice",
        bot_for_adapter=lambda adapter: browser_voice_bot_for_adapter(adapter),  # type: ignore[arg-type]
    ),
    VoiceTestTarget.AGENT_V1: VoiceTestAgentSpec(
        label="Agent V1",
        description="文本直连 AgentV1",
        channel="text",
        bot_for_adapter=lambda adapter: browser_text_agent_v1_for_adapter(adapter),  # type: ignore[arg-type]
    ),
    # VoiceTestTarget.OLD_COMPLEX: VoiceTestAgentSpec(
    #     label="复杂推理",
    #     description="HTTP 复杂推理服务",
    #     channel="text",
    #     bot_for_adapter=lambda adapter: browser_text_old_complex_for_adapter(adapter),  # type: ignore[arg-type]
    # ),
}


def _require_spec(target: VoiceTestTarget) -> VoiceTestAgentSpec:
    # 枚举合法 ≠ 已启用：未注册进 REGISTRY 的仍拒绝（如暂未开放的 OLD_COMPLEX）。
    spec = VOICE_TEST_AGENT_REGISTRY.get(target)
    if spec is None:
        supported = ", ".join(sorted(k.value for k in VOICE_TEST_AGENT_REGISTRY))
        raise ValueError(f"agent_type 必须是 {supported} 之一")
    return spec


def voice_test_agent_options_payload() -> list[dict[str, str]]:
    return [
        {
            "value": key.value,
            "label": spec.label,
            "description": spec.description,
            "test_mode": spec.channel,
        }
        for key, spec in VOICE_TEST_AGENT_REGISTRY.items()
    ]


def is_voice_target(target: VoiceTestTarget) -> bool:
    return _require_spec(target).channel == "voice"


def resolve_test_mode(target: VoiceTestTarget) -> TestMode:
    return _require_spec(target).channel


def parse_voice_test_target(raw: object) -> VoiceTestTarget:
    if not isinstance(raw, str):
        raise ValueError("agent_type 必须是字符串")
    try:
        target = VoiceTestTarget(raw.strip())
    except ValueError as exc:
        known = ", ".join(t.value for t in VoiceTestTarget)
        raise ValueError(f"agent_type 必须是 {known} 之一") from exc
    _require_spec(target)
    return target


def bot_for_voice_test(
    adapter: BrowserVoiceAdapter | BrowserTextAdapter,
    *,
    target: VoiceTestTarget,
):
    spec = _require_spec(target)
    if spec.channel == "voice":
        if not isinstance(adapter, BrowserVoiceAdapter):
            raise TypeError("语音链路需要 BrowserVoiceAdapter")
    elif not isinstance(adapter, BrowserTextAdapter):
        raise TypeError("文本 Agent 需要 BrowserTextAdapter")
    return spec.bot_for_adapter(adapter)
