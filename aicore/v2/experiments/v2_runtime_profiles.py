"""Runtime profile and capability declarations for the unified v2 gateway."""

from __future__ import annotations

from typing import Literal

type RuntimeProfile = Literal[
    "react_s2s",
    "plact_s2s",
    "react_duplex_shell",
    "plact_duplex_shell",
    "duplex_native",
]


def capabilities_for(profile: RuntimeProfile) -> dict[str, bool]:
    native = profile == "duplex_native"
    return {
        "text_input": not native,
        "realtime_audio": True,
        "native_audio_output": native,
        "voice_text_query": not native,
        "turn_cancel": False,
        "task_cancel": True,
        "restore": False,
    }


def agent_mode_for(profile: RuntimeProfile) -> Literal["react", "plact"]:
    return "plact" if profile.startswith("plact_") else "react"


def profile_for_agent_mode(
    mode: Literal["react", "plact"],
    *,
    voice_family: Literal["s2s", "duplex_shell"],
) -> RuntimeProfile:
    return f"{mode}_{voice_family}"  # type: ignore[return-value]


__all__ = [
    "RuntimeProfile",
    "agent_mode_for",
    "capabilities_for",
    "profile_for_agent_mode",
]
