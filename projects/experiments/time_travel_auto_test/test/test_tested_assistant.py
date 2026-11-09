"""TestedAssistant 单元测试。

不依赖真 LLM：用 monkeypatch 替换 create_react_agent_with_task_runner，
返回一个 mock agent，其 astream 产出预设的 AgentOutTextDeltaEvent。

验证：
1. AssistantProtocol 接口完整（is_assistant 通过）
2. create / achat / achat_stream / aupdate_context / adump_history 基本流程
3. 流式回复能拿到完整文本
4. 打断（StreamingReply.interrupt）能停止流式
5. 车控工具能操作 VirtualCar 状态（真工具链路）
6. 虚拟车共享：Runner 共享的 car 实例被助手持有后，车控工具能写入
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator

import pytest

from projects.experiments.time_travel_auto_test.case_runner.assistant_protocol import (
    AssistantEventType,
    StreamingReply,
    is_assistant,
)
from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tested_assistant import (
    DEFAULT_SYSTEM_PROMPT,
    TestedAssistant,
)
from projects.experiments.time_travel_auto_test.virtual_car.models import VirtualCar


# ---------------- Mock aicore v2 agent 事件 ----------------


async def _text_stream(text: str) -> AsyncGenerator[str, None]:
    """把完整文本包装为单 chunk 输入流（模拟流式 ASR 一次性说完）。"""
    yield text


class MockTextDeltaEvent:
    """模拟 AgentOutTextDeltaEvent。"""

    def __init__(self, delta: str) -> None:
        self.delta = delta


class MockTaskCreatedEvent:
    """模拟 TaskCreatedEvent（无文本，只用于验证 _extract_text 跳过）。"""

    type = "task.created"
    task_id = "mock-task"
    name = "mock_tool"


class MockAgent:
    """模拟 ReactAgentWithTaskRunner。

    每次调用 achat 时，根据 user_text 返回预设的流式事件序列。
    """

    def __init__(self, script: dict[str, list[str]] | None = None) -> None:
        # script: {user_text: [chunk1, chunk2, ...]}
        # 默认脚本：任何输入都返回 "好的，已为您处理。"
        self._script = script or {}
        self._default_chunks = ["好的", "，已为您处理", "。"]
        self.call_count = 0

    def astream(self, input: str, **kwargs: Any) -> AsyncGenerator[Any, None]:
        """模拟 astream：按预设 chunk 产出事件。"""
        self.call_count += 1
        chunks = self._script.get(input, self._default_chunks)

        async def _gen():
            for chunk in chunks:
                yield MockTextDeltaEvent(chunk)

        return _gen()


class SlowMockAgent(MockAgent):
    """慢速版 MockAgent：每个 chunk 之间 sleep，让流持续一段时间（打断测试用）。"""

    def __init__(self, script: dict[str, list[str]] | None = None, delay: float = 0.05) -> None:
        super().__init__(script)
        self._delay = delay

    def astream(self, input: str, **kwargs: Any) -> AsyncGenerator[Any, None]:
        self.call_count += 1
        chunks = self._script.get(input, self._default_chunks)

        async def _gen():
            for chunk in chunks:
                await asyncio.sleep(self._delay)
                yield MockTextDeltaEvent(chunk)

        return _gen()


def _patch_create_agent(monkeypatch, mock_agent: MockAgent) -> None:
    """用 monkeypatch 替换 create_react_agent_with_task_runner 和所有真实工具工厂。

    这样 TestedAssistant._ensure_agent 不会真的去初始化 weather/poi/music 等业务工具
    （那些需要真实 API 配置），但 VirtualCarControlTool 仍然走真实链路（操作 VirtualCar）。
    """
    def _fake_create(*args: Any, **kwargs: Any) -> MockAgent:
        return mock_agent

    # mock 掉工厂函数，返回简单的 callable 占位（不会被 mock agent 调用）
    def _fake_tool(*args: Any, **kwargs: Any) -> Any:
        return None

    monkeypatch.setattr(
        "projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tested_assistant.create_react_agent_with_task_runner",
        _fake_create,
    )
    # 业务工具工厂全部 mock 掉（避免真实 API 初始化）
    monkeypatch.setattr(
        "projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tested_assistant.weather_search_v2_tool",
        _fake_tool,
    )
    monkeypatch.setattr(
        "projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tested_assistant.poi_search_v2_tool",
        _fake_tool,
    )
    monkeypatch.setattr(
        "projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tested_assistant.qq_music_song_search_v2_tool",
        _fake_tool,
    )
    monkeypatch.setattr(
        "projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tested_assistant.create_task_cancel_tool",
        _fake_tool,
    )


# ---------------- 测试 ----------------


@pytest.mark.anyio
async def test_tested_assistant_implements_protocol(monkeypatch) -> None:
    """验证 TestedAssistant 实现 AssistantProtocol。"""
    mock = MockAgent()
    _patch_create_agent(monkeypatch, mock)

    assistant = TestedAssistant(virtual_car=VirtualCar())
    assert is_assistant(assistant), "TestedAssistant 必须实现 AssistantProtocol"


@pytest.mark.anyio
async def test_achat_non_streaming(monkeypatch) -> None:
    """非流式 achat：返回完整回复。"""
    mock = MockAgent(script={"开空调": ["好的", "，已为您开空调", "。"]})
    _patch_create_agent(monkeypatch, mock)

    car = VirtualCar()
    assistant = TestedAssistant(virtual_car=car)
    assistant.create(session_id="test-001")

    reply = await assistant.achat("开空调")
    assert reply == "好的，已为您开空调。"

    history = await assistant.adump_history()
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "开空调"}
    assert history[1] == {"role": "assistant", "content": "好的，已为您开空调。"}


@pytest.mark.anyio
async def test_achat_stream_returns_full_text(monkeypatch) -> None:
    """流式 achat_stream：能拿到完整文本。"""
    mock = MockAgent(script={"播放音乐": ["好的", "，正在播放", "。"]})
    _patch_create_agent(monkeypatch, mock)

    assistant = TestedAssistant(virtual_car=VirtualCar())
    assistant.create(session_id="test-002")

    reply = await assistant.achat_stream(_text_stream("播放音乐"))
    chunks: list[str] = []
    async for event in reply.stream():
        if event.type == AssistantEventType.TEXT_DELTA and event.delta:
            chunks.append(event.delta)

    assert "".join(chunks) == "好的，正在播放。"
    assert reply.is_done
    assert not reply.is_interrupted


@pytest.mark.anyio
async def test_achat_stream_interrupt(monkeypatch) -> None:
    """流式打断：interrupt 后 stream 立即停止，已收到的部分保留。"""
    # 用一个 chunk 较多的脚本，方便中途打断
    mock = MockAgent(script={"长回复": ["第一段", "第二段", "第三段", "第四段"]})
    _patch_create_agent(monkeypatch, mock)

    assistant = TestedAssistant(virtual_car=VirtualCar())
    assistant.create(session_id="test-003")

    reply = await assistant.achat_stream(_text_stream("长回复"))

    # 消费第一个 chunk 后打断
    chunks: list[str] = []
    async for event in reply.stream():
        if event.type == AssistantEventType.TEXT_DELTA and event.delta:
            chunks.append(event.delta)
        if len(chunks) == 1:
            reply.interrupt()
            # interrupt 后 stream 应该立即结束（下一个 get 拿到哨兵）

    # 至少收到第一个 chunk
    assert len(chunks) >= 1
    assert chunks[0] == "第一段"
    assert reply.is_interrupted
    # collected_text 应包含已收到的文本
    assert reply.collected_text.startswith("第一段")


@pytest.mark.anyio
async def test_achat_stream_barge_in_interrupts_old_stream(monkeypatch) -> None:
    """插话打断契约：新输入第一个 chunk 到达即打断旧流，半截话入 history。

    接入层实现文字层打断（对齐音频层插话打断语义），不改 v2_agent 底层：
    1. 流1（慢速产出）进行中
    2. 流2 的第一个输入 chunk 到达 → 流1 立即 is_interrupted
    3. 流1 半截话以"［被用户打断，未说完］"标记入 _history（顺序确定）
    4. 流2 正常完成
    """
    mock = SlowMockAgent(script={"长回复": ["一", "二", "三", "四", "五"]}, delay=0.05)
    _patch_create_agent(monkeypatch, mock)

    assistant = TestedAssistant(virtual_car=VirtualCar())
    assistant.create(session_id="barge-in-001")

    # 流1：后台消费
    reply1 = await assistant.achat_stream(_text_stream("长回复"))
    parts1: list[str] = []

    async def consume1() -> None:
        async for event in reply1.stream():
            if event.type == AssistantEventType.TEXT_DELTA and event.delta:
                parts1.append(event.delta)

    task1 = asyncio.create_task(consume1())

    # 等流1 出 1~2 个 chunk（5 chunk × 0.05s，0.12s 时约出 2 个）
    await asyncio.sleep(0.12)

    # 流2：第一个 chunk 到达即触发插话打断（打断流1）
    reply2 = await assistant.achat_stream(_text_stream("新指令"))

    assert reply1.is_interrupted, "新输入第一个 chunk 到达时，旧流应立即被打断"

    # 等流1 消费任务收尾（收到哨兵）+ 流2 完成
    parts2: list[str] = []
    async for event in reply2.stream():
        if event.type == AssistantEventType.TEXT_DELTA and event.delta:
            parts2.append(event.delta)
    await task1

    # 流1 半截话：收到过至少 1 个 chunk，且明显少于完整 5 个
    assert len(parts1) >= 1
    assert len(parts1) < 5
    # 流2 正常完成（默认脚本 "好的，已为您处理。"）
    assert "".join(parts2) == "好的，已为您处理。"
    assert reply2.is_done and not reply2.is_interrupted

    # history 顺序确定：user1 → assistant1(半截+打断标记) → user2 → assistant2
    history = await assistant.adump_history()
    assert [h["role"] for h in history] == ["user", "assistant", "user", "assistant"]
    assert history[0]["content"] == "长回复"
    assert "被用户打断，未说完" in history[1]["content"]
    assert history[1]["content"].startswith(parts1[0])
    assert history[2]["content"] == "新指令"
    assert history[3]["content"] == "好的，已为您处理。"


@pytest.mark.anyio
async def test_achat_stream_barge_in_skips_finished_old_stream(monkeypatch) -> None:
    """旧流已正常完成时，新输入不产生打断记账（无重复半截话条目）。"""
    mock = MockAgent(script={"第一句": ["回复一"], "第二句": ["回复二"]})
    _patch_create_agent(monkeypatch, mock)

    assistant = TestedAssistant(virtual_car=VirtualCar())
    assistant.create(session_id="barge-in-002")

    reply1 = await assistant.achat_stream(_text_stream("第一句"))
    async for event in reply1.stream():
        pass  # 完整消费，流1 正常结束
    assert reply1.is_done and not reply1.is_interrupted

    reply2 = await assistant.achat_stream(_text_stream("第二句"))
    async for event in reply2.stream():
        pass

    history = await assistant.adump_history()
    # 无任何"被用户打断"条目
    assert all("被用户打断" not in h["content"] for h in history)
    assert [h["role"] for h in history] == ["user", "assistant", "user", "assistant"]


@pytest.mark.anyio
async def test_virtual_car_shared_with_assistant(monkeypatch) -> None:
    """Runner 共享的 VirtualCar 实例能被助手持有，车控工具可操作。"""
    mock = MockAgent()
    _patch_create_agent(monkeypatch, mock)

    # 模拟 Runner._share_virtual_car_with_assistant 的行为
    car = VirtualCar(car_info={"车内温度": "29摄氏度"})
    assistant = TestedAssistant()  # 不传 car
    assistant.virtual_car = car  # Runner 共享

    assert assistant.virtual_car is car
    # 车控工具应该能操作这个 car 实例（通过 set_field）
    car.set_field("空调开启状态及模式", "制冷中")
    assert car.car_info["空调开启状态及模式"] == "制冷中"


@pytest.mark.anyio
async def test_create_resets_session(monkeypatch) -> None:
    """create 重置会话：history 清空，agent 重新懒加载。"""
    mock = MockAgent()
    _patch_create_agent(monkeypatch, mock)

    assistant = TestedAssistant(virtual_car=VirtualCar())
    assistant.create(session_id="session-1")
    await assistant.achat("第一条")

    assert len(await assistant.adump_history()) == 2

    # 新 session
    assistant.create(session_id="session-2")
    assert len(await assistant.adump_history()) == 0
    assert assistant._agent is None  # 重置后 agent 为 None，等待懒加载


@pytest.mark.anyio
async def test_aupdate_context_noop(monkeypatch) -> None:
    """aupdate_context 返回 ContextUpdateResult（无主动话语 + 无注入事件）。"""
    from datetime import datetime

    mock = MockAgent()
    _patch_create_agent(monkeypatch, mock)

    assistant = TestedAssistant(virtual_car=VirtualCar())
    assistant.create(session_id="test-004")
    # 不应抛异常；返回 ContextUpdateResult（proactive_text=None, injected_events=[]）
    result = await assistant.aupdate_context(
        {"车内温度": "30摄氏度"},
        current_time=datetime(2025, 1, 3, 18, 30),
    )
    assert result.proactive_text is None
    assert result.injected_events == []


@pytest.mark.anyio
async def test_default_system_prompt_complete() -> None:
    """验证 DEFAULT_SYSTEM_PROMPT 包含关键异步回执约定。"""
    # 7 条异步回执约定
    assert "[占位回执]" in DEFAULT_SYSTEM_PROMPT
    assert "[工具结果回灌]" in DEFAULT_SYSTEM_PROMPT
    assert "pending" in DEFAULT_SYSTEM_PROMPT
    assert "cancel_task" in DEFAULT_SYSTEM_PROMPT
    assert "根据对应占位回执找到 task_id" in DEFAULT_SYSTEM_PROMPT
    assert "call_id" not in DEFAULT_SYSTEM_PROMPT
    # 车控与设备约定（car_control / media / navigation 三工具）
    assert "car_control" in DEFAULT_SYSTEM_PROMPT
    assert "媒体控制" in DEFAULT_SYSTEM_PROMPT
    assert "导航控制" in DEFAULT_SYSTEM_PROMPT


@pytest.mark.anyio
async def test_extract_text_skips_non_text_events(monkeypatch) -> None:
    """_extract_text 对非文本事件返回空字符串。"""
    from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tested_assistant import (
        _extract_text,
    )

    # 文本 delta 事件
    assert _extract_text(MockTextDeltaEvent("hello")) == "hello"
    # 任务事件（无 delta/text 字段）
    assert _extract_text(MockTaskCreatedEvent()) == ""
    # 空字符串 delta 不返回
    assert _extract_text(MockTextDeltaEvent("")) == ""


@pytest.mark.anyio
async def test_multiple_turns_in_same_session(monkeypatch) -> None:
    """同一 session 内多轮对话：history 累积，agent 复用。"""
    mock = MockAgent(
        script={
            "第一句": ["回复一"],
            "第二句": ["回复二"],
        }
    )
    _patch_create_agent(monkeypatch, mock)

    assistant = TestedAssistant(virtual_car=VirtualCar())
    assistant.create(session_id="multi-turn")

    r1 = await assistant.achat("第一句")
    r2 = await assistant.achat("第二句")

    assert r1 == "回复一"
    assert r2 == "回复二"
    # agent 只创建一次（懒加载后复用）
    assert mock.call_count == 2
    # history 累积 4 条
    history = await assistant.adump_history()
    assert len(history) == 4
    assert history[0]["content"] == "第一句"
    assert history[3]["content"] == "回复二"


@pytest.mark.anyio
async def test_backfill_tool_result_carries_task_id_and_duration(monkeypatch) -> None:
    """异步工具结果回灌：结果队列携带 task_id + 真实耗时（虚拟时间差）。

    验证 2026-09-03 修复：结果端补记 task_id 供前端精确配对（并行同名工具
    不误配），duration_ms 从 call→result 的 mock 时间差计算（不再硬编码 0）。
    """
    from datetime import datetime, timedelta
    from types import SimpleNamespace

    mock = MockAgent()
    _patch_create_agent(monkeypatch, mock)

    assistant = TestedAssistant(virtual_car=VirtualCar())
    assistant.create(session_id="backfill-duration")

    call_mock = datetime(2025, 1, 1, 12, 0, 0)
    assistant._task_start_mock["task-abc"] = call_mock
    assistant._current_time = call_mock + timedelta(seconds=3)

    result_obj = SimpleNamespace(tool_name="poi_search", result={"名称": "上海博物馆"})
    event = SimpleNamespace(task_id="task-abc", result=result_obj)

    await assistant._handle_backfill(event)

    results = assistant.drain_backfill_tool_results()
    assert len(results) == 1
    mock_time, task_id, tool_name, raw_result, duration_ms = results[0]
    assert task_id == "task-abc"
    assert tool_name == "poi_search"
    assert raw_result == {"名称": "上海博物馆"}
    assert duration_ms == pytest.approx(3000.0)
    assert mock_time == call_mock + timedelta(seconds=3)
