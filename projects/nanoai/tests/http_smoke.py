"""Executable HTTP smoke test for the NanoAI Session service.

Run from the repository root with:

    uv run python projects/nanoai/tests/http_smoke.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL = "doubao-seed-1-8-251228"
STARTUP_TIMEOUT_SECONDS = 30
TURN_TIMEOUT_SECONDS = 120


class SmokeCheckFailed(RuntimeError):
    """One smoke-test check did not pass."""


@dataclass
class CheckRecorder:
    console: Console
    records: list[tuple[str, bool, str]] = field(default_factory=list)

    def require(self, label: str, condition: bool, detail: str) -> None:
        self.records.append((label, condition, detail))
        state = "[green]PASS[/green]" if condition else "[red]FAIL[/red]"
        self.console.print(f"{state} {label}: {detail}")
        if not condition:
            raise SmokeCheckFailed(f"{label}: {detail}")

    def print_summary(self) -> None:
        table = Table(title="NanoAI HTTP Smoke Test")
        table.add_column("检查项")
        table.add_column("结果")
        table.add_column("详情", overflow="fold")
        for label, passed, detail in self.records:
            state = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
            table.add_row(label, state, detail)
        self.console.print(table)


def main() -> int:
    console = Console()
    checks = CheckRecorder(console)
    port = _find_available_port()
    base_url = f"http://127.0.0.1:{port}"
    model = os.environ.get("NANOAI_HTTP_SMOKE_MODEL", DEFAULT_MODEL)
    process: subprocess.Popen[str] | None = None
    session_id: str | None = None
    dump_payload: dict[str, Any] | None = None
    user_query = (
        "我刚下班，准备从国贸开回望京。车里有点热，出发前请告诉我现在车速、"
        "车内温度、电量和续航，并判断开空调回家是否合适。"
    )
    follow_up_query = "我刚才说准备开到哪里？只回答地点。"
    restored_query = "服务重启前，我说准备开到哪里？只回答地点。"

    console.rule("NanoAI HTTP Smoke Test")
    console.print(f"[cyan]模型:[/cyan] {model}")
    console.print(f"[cyan]临时服务:[/cyan] {base_url}")
    console.print(f"[cyan]第 1 轮用户提问:[/cyan] {user_query}")
    console.print(f"[cyan]第 2 轮用户提问:[/cyan] {follow_up_query}")
    console.print(f"[cyan]恢复后第 3 轮用户提问:[/cyan] {restored_query}")

    try:
        process = _start_server(port)
        with httpx.Client(base_url=base_url, timeout=TURN_TIMEOUT_SECONDS) as client:
            _wait_for_health(client, checks)

            created = client.post(
                "/v1/sessions",
                json={
                    "config": {
                        "model": model,
                        "system_prompt": (
                            "你是车载助手。每次回答前先读取会话静态上下文中的 car_info，"
                            "并且仅用其中数据回答车辆状态，不能编造。用一句话回答。"
                        ),
                        "params": {"max_output_tokens": 1024, "thinking": "disabled"},
                        "max_turns": 1,
                    },
                    "context": {
                        "car_info": {
                            "vehicle_model": "Nano S7",
                            "vehicle_status": {
                                "speed_kph": 0,
                                "gear": "P",
                                "drive_mode": "舒适",
                                "ready_to_drive": True,
                            },
                            "energy": {
                                "battery_percent": 18,
                                "remaining_range_km": 42,
                                "charging_status": "未充电",
                            },
                            "climate": {
                                "cabin_temperature_c": 26.5,
                                "outside_temperature_c": 32,
                                "air_conditioner": "关闭",
                                "target_temperature_c": 23,
                            },
                            "safety": {
                                "doors_locked": True,
                                "tire_pressure_kpa": {
                                    "front_left": 245,
                                    "front_right": 244,
                                    "rear_left": 242,
                                    "rear_right": 243,
                                },
                            },
                            "location": "北京市朝阳区国贸",
                        }
                    },
                },
            )
            checks.require(
                "创建 Session",
                created.status_code == 201,
                f"HTTP {created.status_code}",
            )
            session_id_value = created.json().get("session_id")
            checks.require(
                "返回 session_id",
                isinstance(session_id_value, str),
                str(session_id_value),
            )
            session_id = str(session_id_value)

            with client.stream(
                "POST",
                f"/v1/sessions/{session_id}/turns",
                json={"input": user_query},
            ) as streamed:
                checks.require(
                    "提交 turn",
                    streamed.status_code == 200,
                    f"HTTP {streamed.status_code}",
                )
                checks.require(
                    "返回 SSE 内容类型",
                    "text/event-stream" in streamed.headers.get("content-type", ""),
                    streamed.headers.get("content-type", ""),
                )
                sse_events = list(_read_sse(streamed))

            event_names = [name for name, _ in sse_events]
            event_summary = _event_summary(event_names)
            checks.require(
                "SSE 已提交事件", "session.submitted" in event_names, event_summary
            )
            checks.require(
                "SSE 已完成事件",
                "session.turn.finished" in event_names,
                event_summary,
            )
            finished = _find_event_data(sse_events, "session.turn.finished")
            checks.require(
                "turn 成功完成",
                finished.get("status") == "completed",
                str(finished.get("status")),
            )

            final_text = _final_text(sse_events)
            checks.require(
                "模型使用 car_info",
                all(value in final_text for value in ("18", "42", "26.5")),
                final_text or "<empty>",
            )

            with client.stream(
                "POST",
                f"/v1/sessions/{session_id}/turns",
                json={"input": follow_up_query},
            ) as streamed:
                checks.require(
                    "提交第二个 turn",
                    streamed.status_code == 200,
                    f"HTTP {streamed.status_code}",
                )
                follow_up_events = list(_read_sse(streamed))

            follow_up_names = [name for name, _ in follow_up_events]
            checks.require(
                "第二个 turn 已完成",
                "session.turn.finished" in follow_up_names,
                _event_summary(follow_up_names),
            )
            follow_up_finished = _find_event_data(
                follow_up_events, "session.turn.finished"
            )
            checks.require(
                "第二个 turn 成功完成",
                follow_up_finished.get("status") == "completed",
                str(follow_up_finished.get("status")),
            )
            checks.require(
                "多轮对话保留用户上下文",
                "望京" in _final_text(follow_up_events),
                _final_text(follow_up_events) or "<empty>",
            )

            dumped = client.get(f"/v1/sessions/{session_id}/dump")
            checks.require(
                "导出 Session dump",
                dumped.status_code == 200,
                f"HTTP {dumped.status_code}",
            )
            dump_payload = dumped.json()
            checks.require(
                "dump 保留两个 turn",
                len(dump_payload.get("state", {}).get("history", [])) == 2,
                str(len(dump_payload.get("state", {}).get("history", []))),
            )

        if dump_payload is None or session_id is None:
            raise ValueError("Session dump was not exported")

        _stop_server(process, console)
        process = _start_server(port)
        console.rule("模拟服务重启并恢复 Session")
        with httpx.Client(base_url=base_url, timeout=TURN_TIMEOUT_SECONDS) as client:
            _wait_for_health(client, checks, label="重启后服务健康检查")
            restored = client.post("/v1/sessions/restore", json=dump_payload)
            checks.require(
                "恢复 Session",
                restored.status_code == 201,
                f"HTTP {restored.status_code}",
            )
            checks.require(
                "恢复同一 session_id",
                restored.json().get("session_id") == session_id,
                str(restored.json().get("session_id")),
            )

            with client.stream(
                "POST",
                f"/v1/sessions/{session_id}/turns",
                json={"input": restored_query},
            ) as streamed:
                checks.require(
                    "恢复后提交第三个 turn",
                    streamed.status_code == 200,
                    f"HTTP {streamed.status_code}",
                )
                restored_events = list(_read_sse(streamed))

            restored_names = [name for name, _ in restored_events]
            checks.require(
                "恢复后第三个 turn 已完成",
                "session.turn.finished" in restored_names,
                _event_summary(restored_names),
            )
            checks.require(
                "恢复后保留模型对话历史",
                "望京" in _final_text(restored_events),
                _final_text(restored_events) or "<empty>",
            )

            final_session = client.get(f"/v1/sessions/{session_id}")
            checks.require(
                "查询恢复后的 Session",
                final_session.status_code == 200,
                f"HTTP {final_session.status_code}",
            )
            final_session_data = final_session.json()
            final_history = final_session_data.get("state", {}).get("history", [])
            checks.require(
                "恢复后 Session 保留三个 turn",
                len(final_history) == 3,
                str(len(final_history)),
            )
            closed = client.delete(f"/v1/sessions/{session_id}")
            checks.require(
                "关闭恢复后的 Session",
                closed.status_code == 204,
                f"HTTP {closed.status_code}",
            )
    except (httpx.HTTPError, SmokeCheckFailed, OSError, ValueError) as error:
        console.print(f"[red]Smoke test failed:[/red] {error}")
        return 1
    finally:
        _stop_server(process, console)
        checks.print_summary()

    return 0


def _find_available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(port: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "projects.nanoai.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _wait_for_health(
    client: httpx.Client,
    checks: CheckRecorder,
    *,
    label: str = "服务健康检查",
) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    last_detail = "server did not start"
    while time.monotonic() < deadline:
        try:
            response = client.get("/health", timeout=1)
            if response.status_code == 200:
                checks.require(
                    label,
                    response.json() == {"status": "ok"},
                    str(response.json()),
                )
                return
            last_detail = f"HTTP {response.status_code}"
        except httpx.HTTPError as error:
            last_detail = str(error)
        time.sleep(0.2)
    checks.require(label, False, last_detail)


def _read_sse(response: httpx.Response) -> Iterator[tuple[str, dict[str, Any]]]:
    event_name = "message"
    for line in response.iter_lines():
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            yield event_name, json.loads(line.removeprefix("data: "))
        elif not line:
            event_name = "message"


def _find_event_data(
    events: list[tuple[str, dict[str, Any]]], name: str
) -> dict[str, Any]:
    for event_name, data in reversed(events):
        if event_name == name:
            return data
    raise ValueError(f"SSE 中不存在事件 {name}")


def _event_summary(event_names: list[str]) -> str:
    return f"{len(event_names)} 个事件: {', '.join(dict.fromkeys(event_names))}"


def _final_text(events: list[tuple[str, dict[str, Any]]]) -> str:
    for event_name, data in reversed(events):
        if event_name != "session.output":
            continue
        payload = data.get("data")
        if isinstance(payload, dict) and payload.get("type") in {
            "react.text.done",
            "explicit.text.done",
        }:
            text = payload.get("text")
            return text if isinstance(text, str) else ""
    return ""


def _stop_server(process: subprocess.Popen[str] | None, console: Console) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if process.returncode not in {0, -15}:
        output = process.stdout.read() if process.stdout is not None else ""
        console.print(
            f"[yellow]服务进程退出码 {process.returncode}:[/yellow]\n{output}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
