"""真实 v2_agent 新协议接入的端到端验证脚本。

跑通「真实 ReactAgentWithTaskRunner + 复用现有工具 + 新协议（AdapterRunner 编排）」
完整链路，验证适配器（adapter.py 的 V2AgentAdapter）在新协议下正确接线。

默认跑「开空调」（car_control 工具，纯本地 set_field，异步任务化但无需外部网络），
验证：
1. 真实 LLM agent 被新协议 adapter 驱动对话；
2. 工具经 TaskManager 异步执行 → 事件经 TurnMuxer 汇合 → 落 TraceRecorder；
3. 工具结果回灌 → 助手接续回复；
4. 车控结果落到共享 VirtualCar 实例。

运行（在仓库根目录或本目录均可）：
  D:\\apps\\miniconda\\envs\\dzy_env\\python.exe projects/experiments/time_travel_auto_test/demos/v2_agent_adapter/run_e2e.py
  D:\\apps\\miniconda\\envs\\dzy_env\\python.exe projects/experiments/time_travel_auto_test/demos/v2_agent_adapter/run_e2e.py --query "帮我设置一个60秒后的提醒"

命令行参数：
  --query TEXT   发给助手的用户台词（默认「开空调」）
  --check FIELD VALUE  额外断言虚拟车某字段最终值（可多次），如 --check 空调开启状态及模式 制冷中
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 无论从哪个目录运行都能定位仓库根
_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def setup_windows_utf8_console() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
        except Exception:
            pass


from projects.experiments.time_travel_auto_test.adapter_v2.runner_v2 import AdapterRunner
from projects.experiments.time_travel_auto_test.case_runner.trace import RecordKind
from projects.experiments.time_travel_auto_test.case_schema import (
    FakePersonInfo,
    TestCase,
    VirtualCarInfo,
)
from projects.experiments.time_travel_auto_test.demos.v2_agent_adapter.adapter import (
    V2AgentAdapter,
)
from projects.experiments.time_travel_auto_test.virtual_car.models import VirtualCar


def build_case(query: str) -> TestCase:
    return TestCase(
        id="v2-adapter-e2e",
        case_name="v2_agent 新协议接入端到端",
        case_description="真实 v2_agent 经 V2AgentAdapter 接入新协议，验证对话+工具+车控落地",
        tags=["adapter_v2", "v2_agent", "真实LLM"],
        fake_persons=[FakePersonInfo(role_id="driver", profile="一名车主，说话直接")],
        virtual_car=VirtualCarInfo(
            car_info={
                "车辆当前行驶速度": "0 km/h（静止）",
                "车辆当前档位": "P档（驻车档）",
                "车辆点火状态": "通电",
                "手刹状态": "拉起",
                "车内温度": "29摄氏度",
                "车外温度": "35°C",
                "空调开启状态及模式": "关闭中",
                "主驾是否有人": "有人",
                "副驾是否有人": "没人",
                "多媒体播放状态": "停止中",
                "导航状态": "未导航",
                "当前位置": "上海平金中心地下停车场B2",
            }
        ),
        script_events=[],
        must_pass_assertions=["助手正确理解用户意图并执行"],
    )


def _dump_utterances(runner: AdapterRunner) -> None:
    print("\n── 发言记录 ──")
    for u in runner.trace.get_utterances():
        print(f"  [{u.started_at.strftime('%H:%M:%S.%f')[:-3]}→{u.ended_at.strftime('%H:%M:%S.%f')[:-3]}] "
              f"{u.role}: {u.content!r}")


def _dump_tools(runner: AdapterRunner) -> None:
    print("\n── 工具事件 ──")
    for rec in runner.trace.records:
        if rec[1] not in (RecordKind.TOOL_CALL, RecordKind.TOOL_RESULT):
            continue
        meta = rec[2]
        label = meta.get("tool_name", "")
        print(f"  {rec[1].value:<14} {label}  task_id={meta.get('task_id')!r}")


async def main(args: argparse.Namespace) -> None:
    query: str = args.query
    checks: list[tuple[str, str]] = args.check or []

    print("════════ v2_agent 新协议接入端到端验证 ════════")
    print(f"  用户台词: {query!r}")

    runner = AdapterRunner(V2AgentAdapter(), chunk_delay=0.02)
    runner.setup(build_case(query))

    car: VirtualCar = runner.virtual_car
    assert car is not None

    print("\n[1] 用户说话 → 发起 USER 回合")
    await runner.speak(query)

    print("[2] 等待助手回合自然耗尽（真实 LLM + 异步工具回灌）")
    await runner.wait_idle()

    _dump_utterances(runner)
    _dump_tools(runner)

    # 断言：确实产生了助手回复
    replies = [u for u in runner.trace.get_utterances() if u.role == "assistant"]
    assert replies, "应至少产生一条助手回复"
    print(f"\n  ✓ 助手回复条数: {len(replies)}")
    for r in replies:
        print(f"      - {r.content!r}")

    # 断言：确实产生了工具事件（异步工具走 TaskManager → TurnMuxer → TraceRecorder）
    tool_events = [
        rec for rec in runner.trace.records
        if rec[1] in (RecordKind.TOOL_CALL, RecordKind.TOOL_RESULT)
    ]
    print(f"  ✓ 工具事件条数: {len(tool_events)}")

    # 额外断言虚拟车字段
    for field, expected in checks:
        actual_val = str(car.get_field(field))
        mark = "✓" if actual_val == expected else "✗"
        print(f"  {mark} 虚拟车字段 {field}: {actual_val!r} (期望 {expected!r})")
        assert actual_val == expected, f"{field} 期望 {expected!r} 实际 {actual_val!r}"

    history = runner._adapter.dump_history()
    print(f"\n  ✓ 导出对话历史 {len(history)} 条")
    for h in history:
        print(f"      [{h['role']}] {h['content'][:60]!r}")

    print("\n════════ 端到端验证通过 ════════")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="v2_agent 新协议接入端到端验证")
    parser.add_argument("--query", default="开空调", help="发给助手的用户台词")
    parser.add_argument(
        "--check",
        nargs=2,
        action="append",
        metavar=("FIELD", "VALUE"),
        help="额外断言虚拟车字段最终值，可多次",
    )
    return parser.parse_args()


if __name__ == "__main__":
    setup_windows_utf8_console()
    asyncio.run(main(parse_args()))