"""终端可视化（Textual TUI）：运行 case 后展示双列时间轴（剧本 vs 实际）。

用法（在仓库根目录 d:\\yitu_projects\\nanoai 下执行）：
    D:\\apps\\miniconda\\python.exe -m projects.experiments.time_travel_auto_test.visualizer.tui_viewer --case interrupt
    D:\\apps\\miniconda\\python.exe -m projects.experiments.time_travel_auto_test.visualizer.tui_viewer --list
    D:\\apps\\miniconda\\python.exe -m projects.experiments.time_travel_auto_test.visualizer.tui_viewer --case builtin --no-judge
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, RichLog, Static
from rich.text import Text

# ---------------------------------------------------------------------------
# 时间格式化
# ---------------------------------------------------------------------------
def format_offset(s: float | None) -> str:
    if s is None:
        return "边界"
    if s == 0:
        return "T0"
    if s < 1:
        return f"T+{int(s * 1000)}ms"
    if s < 60:
        return f"T+{s:.1f}s"
    m, r = divmod(s, 60)
    if m < 60:
        return f"T+{int(m)}m{int(r)}s" if r else f"T+{int(m)}m"
    h, m2 = divmod(m, 60)
    return f"T+{int(h)}h{int(m2)}m" if m2 else f"T+{int(h)}h"


# ---------------------------------------------------------------------------
# 事件渲染
# ---------------------------------------------------------------------------
EVENT_LABELS = {
    "script_fake_person_speak": "假人说话",
    "script_car_set_state": "车态变更",
    "script_state_check": "状态检查",
    "fake_person_speak": "假人说话",
    "assistant_reply": "助手回复",
    "interrupt": "打断",
    "car_state_change": "车态变更",
    "state_check": "状态检查",
    "acceleration": "时间快进",
}

EVENT_ICONS = {
    "script_fake_person_speak": "👤",
    "script_car_set_state": "🔧",
    "script_state_check": "✓",
    "fake_person_speak": "👤",
    "assistant_reply": "🤖",
    "interrupt": "⚡",
    "car_state_change": "🔧",
    "state_check": "✓",
    "acceleration": "⏱",
}


def _render_event_line(ev: dict[str, Any], side: str) -> Text:
    """将单个事件渲染为一行 Rich Text。"""
    ev_type = ev.get("type", "?")
    ts = ev.get("offset_seconds")
    time_label = "边界" if ts is None else format_offset(ts)
    icon = EVENT_ICONS.get(ev_type, "?")
    label = EVENT_LABELS.get(ev_type, ev_type)

    text = Text()
    text.append(f"{time_label} ", style="dim")

    content = ""
    is_partial = False
    extra = ""

    if ev_type == "script_fake_person_speak":
        target = ev.get("target", "?")
        content = ev.get("content") or "[LLM 自主生成]"
        text.append(f"{icon} ", style="bold cyan")
        text.append(f"{label}", style="bold cyan")
        text.append(f" ({target})", style="dim")
    elif ev_type == "fake_person_speak":
        role = ev.get("role", "?")
        content = ev.get("content", "")
        is_partial = ev.get("is_partial", False)
        text.append(f"{icon} ", style="bold cyan")
        text.append(f"{label}", style="bold cyan")
        text.append(f" ({role})", style="dim")
        if is_partial:
            extra = " [半截]"
    elif ev_type == "script_car_set_state":
        fields = ev.get("fields", {})
        content = ", ".join(f"{k}={v}" for k, v in fields.items())
        text.append(f"{icon} ", style="yellow")
        text.append(f"{label}", style="yellow")
    elif ev_type == "car_state_change":
        fields = ev.get("updated_fields", {})
        content = ", ".join(f"{k}={v}" for k, v in fields.items())
        text.append(f"{icon} ", style="yellow")
        text.append(f"{label}", style="yellow")
    elif ev_type == "script_state_check":
        fields = ev.get("expected_fields", {})
        content = ", ".join(f"{k}={v}" for k, v in fields.items())
        text.append(f"{icon} ", style="green")
        text.append(f"{label}", style="green")
    elif ev_type == "state_check":
        passed = ev.get("passed", False)
        expected = ev.get("expected", {})
        actual = ev.get("actual", {})
        mismatches = ev.get("mismatches", {})
        icon2 = "✓" if passed else "✗"
        style2 = "bold green" if passed else "bold red"
        status = "通过" if passed else "失败"
        text.append(f"{icon2} ", style=style2)
        text.append(f"{label} {status}", style=style2)
        kvs = []
        for k in expected:
            act = actual.get(k, "--")
            m = " ❌" if k in mismatches else ""
            kvs.append(f"{k}={act}{m}")
        content = ", ".join(kvs)
    elif ev_type == "assistant_reply":
        content = ev.get("content", "")
        is_partial = ev.get("is_partial", False)
        text.append(f"{icon} ", style="bold green")
        text.append(f"{label}", style="bold green")
        if is_partial:
            extra = " [半截]"
    elif ev_type == "acceleration":
        content = ev.get("description", "")
        text.append(f"{icon} ", style="magenta")
        text.append(f"{label}", style="magenta")
    else:
        text.append(f"{icon} {label}")

    if extra:
        text.append(extra, style="bold red")
    if content:
        text.append(f"\n  {content}", style="italic dim")

    return text


# ---------------------------------------------------------------------------
# Textual App
# ---------------------------------------------------------------------------
class TimeTravelTUI(App[None]):
    """TimeTravel 测试可视化 TUI。"""

    CSS = """
    #main-container {
        layout: vertical;
        height: 1fr;
    }

    #info-bar {
        height: auto;
        padding: 1 2;
        border-bottom: solid $primary;
        background: $surface;
    }

    #info-bar Static {
        width: 1fr;
    }

    #timeline-container {
        layout: horizontal;
        height: 1fr;
    }

    #timeline-container > Vertical {
        width: 1fr;
    }

    RichLog {
        height: 1fr;
        border: round $primary;
        padding: 0 1;
    }

    .window-title {
        color: $primary;
        border-bottom: solid $primary;
        margin-bottom: 1;
        padding: 0 1;
    }

    .score-pass {
        color: $success;
    }

    .score-fail {
        color: $error;
    }

    .status-text {
        padding: 0 2;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("q,escape", "quit", "退出"),
        Binding("r", "rerun", "重新运行"),
    ]

    def __init__(self, case_id: str = "", enable_judge: bool = True) -> None:
        super().__init__()
        self._case_id = case_id
        self._enable_judge = enable_judge
        self._data: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            yield Static("⏳ 正在运行测试...", id="info-bar")
            with Horizontal(id="timeline-container"):
                with Vertical():
                    yield Static("📋 剧本事件（预期）", classes="window-title")
                    yield RichLog(id="script-timeline", auto_scroll=False, highlight=True, markup=True)
                with Vertical():
                    yield Static("🎬 实际事件（Trace）", classes="window-title")
                    yield RichLog(id="trace-timeline", auto_scroll=False, highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._run_case(), name="case-runner")

    async def _run_case(self) -> None:
        """后台运行 case。"""
        info = self.query_one("#info-bar", Static)
        info.update(f"⏳ 正在运行 case: {self._case_id} ...")

        try:
            data = await _run_case_async(self._case_id, self._enable_judge)
            self._data = data
            self._populate()
        except Exception as e:
            import traceback
            info.update(f"❌ 运行失败: {e}\n{traceback.format_exc()}")

    def _populate(self) -> None:
        """填充 UI 数据。"""
        data = self._data
        if data is None:
            return

        ci = data.get("case_info", {})
        judge = data.get("judge")

        # 信息栏
        info = self.query_one("#info-bar", Static)
        info.update(self._build_info_bar(ci, judge))

        # 剧本时间轴
        script_log = self.query_one("#script-timeline", RichLog)
        script_log.clear()
        for ev in data.get("script_events", []):
            script_log.write(_render_event_line(ev, "script"))

        # 实际时间轴
        trace_log = self.query_one("#trace-timeline", RichLog)
        trace_log.clear()
        for ev in data.get("trace", {}).get("events", []):
            trace_log.write(_render_event_line(ev, "trace"))

    def _build_info_bar(self, ci: dict, judge: dict | None) -> str:
        """构建顶部信息栏。"""
        name = ci.get("name", "?")
        case_id = ci.get("id", "?")
        desc = ci.get("description", "")

        lines = [
            f"[bold white]{name}[/]  [dim]({case_id})[/]",
            f"[dim italic]{desc}[/]",
        ]

        if judge:
            sc = judge.get("score", 0)
            passed = judge.get("overall_passed", False)
            color = "green" if passed else "red"
            status = "PASS" if passed else "FAIL"
            must = judge.get("must_pass", {})
            bonus = judge.get("bonus", {})
            scs = judge.get("state_checks", {})

            lines.append(
                f"[bold {color}]Score: {sc:.0f}/100 {status}[/]  "
                f"[dim]必过: {must.get('passed',0)}/{must.get('total',0)}  "
                f"加分: {bonus.get('passed',0)}/{bonus.get('total',0)}  "
                f"状态检查: {scs.get('passed',0)}/{scs.get('total',0)}[/]"
            )

            if judge.get("summary"):
                lines.append(f"[dim italic]{judge['summary']}[/]")

        return "\n".join(lines)

    def action_rerun(self) -> None:
        """重新运行 case。"""
        self._data = None
        script_log = self.query_one("#script-timeline", RichLog)
        trace_log = self.query_one("#trace-timeline", RichLog)
        script_log.clear()
        trace_log.clear()
        self.run_worker(self._run_case(), name="case-runner")


# ---------------------------------------------------------------------------
# 异步运行 case（直接 await，不创建独立 event loop）
# ---------------------------------------------------------------------------
async def _run_case_async(case_id: str, enable_judge: bool) -> dict[str, Any]:
    """异步运行 case，返回可视化数据。"""
    from projects.experiments.time_travel_auto_test.visualizer.export_trace import export_trace_json
    from projects.experiments.time_travel_auto_test.case_runner.runner import CaseRunner, RunnerConfig
    from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tested_assistant import TestedAssistant

    case = _build_case(case_id)
    assistant = TestedAssistant()
    config = RunnerConfig(
        use_streaming=True,
        fast_mode=False,
        assistant_timeout=120.0,
        fake_person_timeout=60.0,
        enable_acceleration=True,
    )
    runner = CaseRunner(assistant=assistant, config=config)
    t0 = datetime.now().replace(microsecond=0)

    run_result = await runner.run(case, t0=t0)

    verdict = None
    if enable_judge and not run_result.error:
        from projects.experiments.time_travel_auto_test.judge.judge import Judge, build_judge_input_from_run_result
        try:
            assistant_history = await assistant.adump_history()
        except Exception:
            assistant_history = []
        judge_input = build_judge_input_from_run_result(
            case=case, recorder=runner.trace, run_result=run_result,
            assistant_history=assistant_history,
        )
        j = Judge()
        try:
            verdict = await j.ajudge(judge_input)
        except Exception:
            pass

    return export_trace_json(case, runner.trace, verdict)


def _build_case(case_id: str):
    from projects.experiments.time_travel_auto_test.demos.run_e2e_demo import (
        build_builtin_case,
        build_builtin_case_with_acceleration,
        build_builtin_llm_speak_case,
        build_builtin_interrupt_case,
        load_fixture_case,
    )
    builders = {
        "builtin": build_builtin_case,
        "builtin-accel": build_builtin_case_with_acceleration,
        "llm-speak": build_builtin_llm_speak_case,
        "interrupt": build_builtin_interrupt_case,
    }
    if case_id in builders:
        return builders[case_id]()
    return load_fixture_case(case_id)


AVAILABLE_CASES = {
    "builtin": "简单开空调",
    "builtin-accel": "时间加速 + 提醒追问",
    "llm-speak": "LLM 自主对话",
    "interrupt": "全双工打断",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TimeTravel 终端可视化（Textual TUI）")
    parser.add_argument("--case", type=str, help="要运行的 case ID")
    parser.add_argument("--list", action="store_true", help="列出可用 case")
    parser.add_argument("--no-judge", action="store_true", help="跳过 Judge")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.list:
        print("\n可用 case:")
        for cid, name in AVAILABLE_CASES.items():
            print(f"  {cid:<20} {name}")
        print()
        return

    if not args.case:
        print("请指定 --case <case_id>，或使用 --list 查看可用 case")
        return

    case_id = args.case
    if case_id not in AVAILABLE_CASES:
        print(f"⚠ 未知 case: {case_id}，将尝试作为 fixture case 加载")

    enable_judge = not args.no_judge
    app = TimeTravelTUI(case_id=case_id, enable_judge=enable_judge)
    app.run()


if __name__ == "__main__":
    main()