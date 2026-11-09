"""物理语音测试：扬声器/麦克风 + S2S 适配 AutoTest 评测框架。

运行入口：
    .venv/bin/python projects/voice_test/main.py
"""

from projects.voice_test.adapter.browser_voice_adapter import BrowserVoiceAdapter
from projects.voice_test.bots.browser_voice_bot import (
    BrowserVoiceBot,
    browser_voice_bot_for_adapter,
)

__all__ = [
    "BrowserVoiceAdapter",
    "BrowserVoiceBot",
    "browser_voice_bot_for_adapter",
]
