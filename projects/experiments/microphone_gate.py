from __future__ import annotations

from dataclasses import dataclass


def is_microphone_trigger_key(key: str) -> bool:
    return key == " "


@dataclass
class MicrophoneInputGate:
    is_open: bool = False

    def open_for_user_input(self) -> bool:
        if self.is_open:
            return False
        self.is_open = True
        return True

    def close_after_user_input(self) -> None:
        self.is_open = False
