"""FakePersonEvent：假人演员在时间轴上输出的事件流。

对标 AssistantEvent（assistant_protocol.py），假人侧也产出结构化事件流。
Runner 统一消费双侧事件，在 Test Trace 中交织记录。

分层（L0-L3 命名体系，见 ARCHITECTURE.md §8）：
- L0: 假人剧本（script_events）    → 平台内部定义
- L1: FakePersonEvent             → 假人模块产出，Runner 消费
- L2: Test Trace（TraceRecorder） → Runner 交织记录
- L3: Judge View（字符串）        → 裁判看到的高可读文本
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Literal


@dataclass
class FakePersonEvent:
    """假人演员产生的事件。

    Attributes:
        type: 事件类型（speak_start / text_delta / speak_done）
        wall_time: 真实时间戳，用于计算时序
        delta: text_delta 事件的文本增量
        role_id: 哪个假人在说话（对应 script_events 的 target）
    """
    type: Literal["speak_start", "text_delta", "speak_done"]
    wall_time: datetime
    delta: str = ""
    role_id: str = ""


async def deliver_fake_person_speech_stream(
    text: str,
    role_id: str,
    chunk_delay: float = 0.05,
) -> AsyncIterator[FakePersonEvent]:
    """以流式方式交付假人说话，产出 FakePersonEvent 序列。

    模拟真实说话节奏：先产出 speak_start，然后逐字产出 text_delta，
    最后产出 speak_done。每字之间间隔 chunk_delay 秒。

    用法：
        async for event in deliver_fake_person_speech_stream("开空调", "driver"):
            if event.type == "text_delta":
                print(event.delta, end="")
    """
    # speak_start
    yield FakePersonEvent(
        type="speak_start",
        wall_time=datetime.now(),
        role_id=role_id,
    )

    # 逐字交付（模拟真实说话节奏）
    for ch in text:
        await asyncio.sleep(chunk_delay)
        yield FakePersonEvent(
            type="text_delta",
            wall_time=datetime.now(),
            delta=ch,
            role_id=role_id,
        )

    # speak_done
    yield FakePersonEvent(
        type="speak_done",
        wall_time=datetime.now(),
        role_id=role_id,
    )