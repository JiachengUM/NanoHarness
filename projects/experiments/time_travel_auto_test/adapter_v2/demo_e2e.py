"""新协议（事件源适配器模式）端到端 demo。

独立于现有代码运行（不动 case_runner），复用与协议无关的基础设施，
验证 AdapterRunner + TurnMuxer 能跑通完整链路：

Part A —— run(case) 完整脚本驱动（复用 EventScheduler）：
  1. 异步工具回灌：说话 → 调 set_reminder → 结果晚到 → 续接回复
  2. 车控写虚拟车：开空调（source="assistant" 三色区分的金色）
  3. 状态检查：state_check「空调开启状态及模式 == 制冷中」
  4. 打断：长故事说到中途，用户插话 → 助手自驱中断 → 半截话

Part B —— 方法级快进 + 主动话语：
  5. 设 30 分钟提醒 → 快进 1800s → 提醒到期 → 主动话语（无用户输入）

运行：
  D:\\apps\\miniconda\\envs\\dzy_env\\python.exe projects/experiments/time_travel_auto_test/adapter_v2/demo_e2e.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from projects.experiments.time_travel_auto_test.adapter_v2.mock_adapter import MockAdapter
from projects.experiments.time_travel_auto_test.adapter_v2.runner_v2 import AdapterRunner
from projects.experiments.time_travel_auto_test.case_runner.trace import RecordKind
from projects.experiments.time_travel_auto_test.case_schema import (
    FakePersonInfo,
    TestCase,
    VirtualCarInfo,
)
from projects.experiments.time_travel_auto_test.fake_person.models import (
    FakePersonSpeakArgs,
    FakePersonSpeakPerformAction,
)
from projects.experiments.time_travel_auto_test.script_events.script_event import (
    FakePersonScriptEvent,
    VirtualCarStateCheckAction,
    VirtualCarStateCheckArgs,
    VirtualCarStateCheckScriptEvent,
)


def _speak(delta_seconds: float, text: str) -> FakePersonScriptEvent:
    return FakePersonScriptEvent(
        event_t0_plus_timedelta=timedelta(seconds=delta_seconds),
        target="driver",
        action=FakePersonSpeakPerformAction(args=FakePersonSpeakArgs(content=text)),
    )


def build_case() -> TestCase:
    return TestCase(
        id="demo_e2e",
        case_name="新协议端到端演示",
        case_description="验证事件源适配器协议：异步工具回灌/车控/状态检查/打断",
        tags=["adapter_v2", "e2e"],
        fake_persons=[FakePersonInfo(role_id="driver", profile="一名车主，正在开车")],
        virtual_car=VirtualCarInfo(car_info={}),
        script_events=[
            _speak(1.0, "帮我设置一个30分钟后的提醒"),
            _speak(3.0, "开空调"),
            _speak(6.0, "给我讲个长故事"),
            _speak(6.8, "停一下，改去机场"),
        ],
        virtual_car_state_check_assertions=[
            VirtualCarStateCheckScriptEvent(
                event_t0_plus_timedelta=timedelta(seconds=4.0),
                target="car",
                action=VirtualCarStateCheckAction(
                    args=VirtualCarStateCheckArgs(
                        expected_fields={"空调开启状态及模式": "制冷中"}
                    )
                ),
            ),
        ],
        must_pass_assertions=["助手正确理解用户意图并执行车控/定时任务/打断"],
    )


def _dump_utterances(runner: AdapterRunner, title: str) -> None:
    print(f"\n── {title} · 发言记录 ──")
    for u in runner.trace.get_utterances():
        tag = ""
        if u.role == "assistant":
            if u.interrupted_by_barge_in:
                tag = "　[半截话·被插话打断]"
            elif u.is_partial:
                tag = "　[半截话]"
            elif u.is_proactive:
                tag = "　[主动话语]"
        print(f"  [{u.started_at.strftime('%H:%M:%S.%f')[:-3]}→{u.ended_at.strftime('%H:%M:%S.%f')[:-3]}] "
              f"{u.role}{tag}: {u.content!r}")


def _dump_state_checks(runner: AdapterRunner) -> None:
    print("\n── 状态检查 ──")
    for at, sc in runner.trace.get_state_checks():
        mark = "✓" if sc.passed else "✗"
        print(f"  [{at.strftime('%H:%M:%S.%f')[:-3]}] {mark} 期望 {sc.expected_fields}")
        if sc.mismatches:
            print(f"        实际不符: {sc.mismatches}")


async def part_a_run_case() -> None:
    print("════════════ Part A · run(case) 完整脚本驱动 ════════════")
    runner = AdapterRunner(MockAdapter(), chunk_delay=0.02)
    case = build_case()
    result = await runner.run(case)

    _dump_utterances(runner, "A")
    _dump_state_checks(runner)

    # 断言 1：异步工具回灌（set_reminder 的 tool_call + tool_result 被记录）
    tool_names = [
        r[2]["tool_name"] for r in runner.trace.records
        if r[1] in (RecordKind.TOOL_CALL, RecordKind.TOOL_RESULT)
    ]
    assert "set_reminder" in tool_names, f"未记录 set_reminder 工具事件: {tool_names}"
    print("  ✓ 1. 异步工具回灌（set_reminder 调用+返回）已记录")

    # 断言 2：车控写虚拟车（开空调 source="assistant"）
    car_sets = [
        r[2] for r in runner.trace.records if r[1] is RecordKind.VIRTUAL_CAR_SET_STATE
    ]
    ac_assistant = any(
        "空调开启状态及模式" in cs["updated_fields"] and cs["source"] == "assistant"
        for cs in car_sets
    )
    assert ac_assistant, "开空调应记 source=assistant 的车态变更"
    print("  ✓ 2. 车控写虚拟车（开空调，source=assistant）")

    # 断言 3：状态检查通过
    checks = runner.trace.get_state_checks()
    assert checks and all(sc.passed for _, sc in checks), "状态检查应全部通过"
    print("  ✓ 3. 状态检查通过（空调 == 制冷中）")

    # 断言 4：长故事被打断为半截话
    partials = [
        u for u in runner.trace.get_utterances()
        if u.role == "assistant" and u.interrupted_by_barge_in
    ]
    assert partials, "应有被插话打断的半截话"
    assert partials[0].content.startswith("从前有座山，"), "半截话内容不符"
    print(f"  ✓ 4. 打断：长故事半截话 = {partials[0].content!r}（助手自驱中断）")

    assert result.error is None, f"run(case) 报错: {result.error}"
    print("  ✓ Part A 全部通过（无调度错误）")


async def part_b_proactive() -> None:
    print("\n════════════ Part B · 快进 + 主动话语（方法级） ════════════")
    runner = AdapterRunner(MockAdapter(), chunk_delay=0.02)
    runner.setup(build_case())

    await runner.speak("帮我设置一个30分钟后的提醒")
    await runner.wait_idle()

    # 快进 1800s（30 分钟）→ 提醒到期
    await runner.accelerate_to(runner.mock_time + timedelta(seconds=1800))
    await runner.proactive("提醒到期")
    await runner.wait_idle()

    _dump_utterances(runner, "B")

    proactive_utterances = [
        u for u in runner.trace.get_utterances()
        if u.role == "assistant" and u.is_proactive
    ]
    assert proactive_utterances, "应有主动话语"
    assert proactive_utterances[0].content == "时间到了，该喝水啦。", \
        f"主动话语内容不符: {proactive_utterances[0].content!r}"
    print("  ✓ 5. 快进 30 分钟 → 提醒到期 → 主动话语（无用户输入）")
    print("  ✓ Part B 全部通过")


async def main() -> None:
    await part_a_run_case()
    await part_b_proactive()
    print("\n════════════ 端到端 demo 全部通过 ════════════")


if __name__ == "__main__":
    asyncio.run(main())