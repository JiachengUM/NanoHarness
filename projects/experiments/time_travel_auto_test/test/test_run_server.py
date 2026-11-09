"""可视化 WS 服务器测试（真实 uvicorn 线程 + websockets 客户端）。

不用 FastAPI TestClient：环境里 httpx 0.28 与 starlette 0.27 的
TestClient 不兼容（app= 参数已移除），且真实 TCP + WS 协议栈更接近
生产。全部用 MockAssistant（无 LLM 依赖）。
"""

from __future__ import annotations

import json
import threading
import time

import pytest
import uvicorn

try:
    from websockets.asyncio.client import connect  # websockets >= 14
except ImportError:  # pragma: no cover
    from websockets import connect  # type: ignore

from projects.experiments.time_travel_auto_test.visualizer import run_server


@pytest.fixture()
def ws_url():
    """起真实 uvicorn 服务器（随机端口），返回 /ws 地址。"""
    run_server._current_run = None  # 每个测试独立运行状态
    run_server._last_run = None  # 评判产物（run 上下文）也重置，避免跨测试泄漏
    config = uvicorn.Config(run_server.app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10.0
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn 服务器启动超时"
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"ws://127.0.0.1:{port}/ws"
    server.should_exit = True
    thread.join(timeout=5)


async def _send_cmd(ws, command_id: str, command: str, payload: dict | None = None) -> None:
    await ws.send(json.dumps({
        "kind": "command",
        "command_id": command_id,
        "command": command,
        "payload": payload or {},
    }, ensure_ascii=False))


async def _recv_until(ws, predicate, max_messages: int = 500) -> dict:
    """循环接收消息直到谓词命中（跳过其他消息），返回命中消息。"""
    for _ in range(max_messages):
        raw = await ws.recv()
        msg = json.loads(raw)
        if predicate(msg):
            return msg
    raise AssertionError(f"{max_messages} 条消息内未命中谓词")


async def _recv_ack(ws, command_id: str) -> dict:
    return await _recv_until(
        ws, lambda m: m.get("kind") == "ack" and m.get("command_id") == command_id
    )


@pytest.mark.anyio
async def test_ws_hello_and_list_cases(ws_url: str) -> None:
    async with connect(ws_url) as ws:
        hello = json.loads(await ws.recv())
        assert hello["kind"] == "hello"
        assert "server_time" in hello

        await _send_cmd(ws, "c1", "list_cases")
        ack = await _recv_ack(ws, "c1")
        assert ack["ok"] is True
        assert ack["status"] == "completed"
        cases = ack["payload"]["cases"]
        assert len(cases) >= 1
        assert all("id" in c and "case_name" in c for c in cases)


@pytest.mark.anyio
async def test_ws_run_case_unknown_rejected(ws_url: str) -> None:
    async with connect(ws_url) as ws:
        await ws.recv()  # hello

        await _send_cmd(ws, "c1", "run_case", {"case_id": "no-such-case"})
        ack = await _recv_ack(ws, "c1")
        assert ack["ok"] is False
        assert ack["status"] == "not_found"


@pytest.mark.anyio
async def test_ws_run_case_streams_events(ws_url: str) -> None:
    """run_case → ack accepted → 事件流（case_started ... case_finished）。"""
    async with connect(ws_url) as ws:
        await ws.recv()  # hello

        await _send_cmd(ws, "c1", "run_case", {
            "case_id": "builtin-simple-ac",
            "fast_mode": True,
            "use_streaming": False,
        })
        ack = await _recv_ack(ws, "c1")
        assert ack["ok"] is True
        assert ack["status"] == "accepted"

        # 事件流：第一个事件应为 case_started（层2）
        first_event = await _recv_until(ws, lambda m: m.get("kind") == "event")
        assert first_event["event"]["kind"] == "case_started"
        assert first_event["event"]["payload"]["case_id"] == "builtin-simple-ac"
        # 双时间戳信封
        assert first_event["event"]["mock_time"] is not None
        assert first_event["event"]["wall_time"]

        # 收到 utterance 事件（层1）
        utt = await _recv_until(
            ws,
            lambda m: m.get("kind") == "event" and m["event"]["kind"] == "utterance",
        )
        assert utt["event"]["payload"]["content"]

        # 终点：case_finished
        fin = await _recv_until(
            ws,
            lambda m: m.get("kind") == "event" and m["event"]["kind"] == "case_finished",
        )
        assert fin["event"]["payload"]["error"] is None
        assert fin["event"]["payload"]["total_utterances"] == 2

        # 跑完后可再次运行（运行上下文已清理）
        await _send_cmd(ws, "c2", "stop_case")
        await _send_cmd(ws, "c3", "run_case", {
            "case_id": "builtin-simple-ac",
            "fast_mode": True,
            "use_streaming": False,
        })
        ack2 = await _recv_ack(ws, "c3")
        assert ack2["ok"] is True
        await _send_cmd(ws, "c4", "stop_case")


@pytest.mark.anyio
async def test_ws_stop_case_idle(ws_url: str) -> None:
    async with connect(ws_url) as ws:
        await ws.recv()  # hello

        # 空闲时 stop 也应成功
        await _send_cmd(ws, "c1", "stop_case")
        ack = await _recv_ack(ws, "c1")
        assert ack["ok"] is True
        assert ack["payload"]["was_running"] is False


# ---------------- judge_case 命令（裁判终局评判） ----------------


def _fake_verdict(case_id: str) -> dict:
    """与 JudgeVerdict.model_dump(mode="json") 同构的假裁判结果。"""
    return {
        "case_id": case_id,
        "overall_passed": True,
        "score": 100.0,
        "score_breakdown": {
            "must_pass_total": 1,
            "must_pass_passed": 1,
            "bonus_total": 0,
            "bonus_passed": 0,
            "state_check_total": 1,
            "state_check_passed": 1,
            "score": 100.0,
            "passed": True,
        },
        "assertion_results": [
            {
                "assertion": "空调被打开",
                "assertion_type": "must_pass",
                "passed": True,
                "reasoning": "轨迹显示空调已开启",
                "evidence": ["car_set_state 空调开启状态及模式=制冷中"],
            }
        ],
        "summary": "假裁判：全部通过",
    }


async def _run_case_until_finished(ws, command_id: str, case_id: str) -> None:
    """跑一个快速 mock case 并等到 case_finished 事件。"""
    await _send_cmd(ws, command_id, "run_case", {
        "case_id": case_id,
        "fast_mode": True,
        "use_streaming": False,
    })
    ack = await _recv_ack(ws, command_id)
    assert ack["ok"] is True, f"run_case 未受理: {ack}"
    await _recv_until(
        ws,
        lambda m: m.get("kind") == "event" and m["event"]["kind"] == "case_finished",
    )


@pytest.mark.anyio
async def test_ws_judge_case_rejected_without_run(ws_url: str) -> None:
    """judge_case：没有已完成的 run → rejected。"""
    async with connect(ws_url) as ws:
        await ws.recv()  # hello

        await _send_cmd(ws, "c1", "judge_case")
        ack = await _recv_ack(ws, "c1")
        assert ack["ok"] is False
        assert ack["status"] == "rejected"
        assert "没有已完成的 case 运行" in ack["payload"]["message"]


@pytest.mark.anyio
async def test_ws_judge_case_returns_verdict(ws_url: str, monkeypatch) -> None:
    """run 完成 → judge_case → ack accepted + judge_verdict 事件直达本连接。"""
    async def fake_execute_judge(case, recorder, run_result, assistant_history):
        return _fake_verdict(case.id)

    monkeypatch.setattr(run_server, "_execute_judge", fake_execute_judge)

    async with connect(ws_url) as ws:
        await ws.recv()  # hello

        await _run_case_until_finished(ws, "c1", "builtin-simple-ac")

        await _send_cmd(ws, "c2", "judge_case")
        ack = await _recv_ack(ws, "c2")
        assert ack["ok"] is True
        assert ack["status"] == "accepted"

        verdict = await _recv_until(
            ws,
            lambda m: m.get("kind") == "event" and m["event"]["kind"] == "judge_verdict",
        )
        payload = verdict["event"]["payload"]
        assert payload["case_id"] == "builtin-simple-ac"
        assert payload["overall_passed"] is True
        assert payload["score"] == 100.0
        assert payload["assertion_results"][0]["passed"] is True
        assert payload["summary"] == "假裁判：全部通过"

        # 可重新评判（上一评判任务已完成）
        await _send_cmd(ws, "c3", "judge_case")
        ack3 = await _recv_ack(ws, "c3")
        assert ack3["ok"] is True
        verdict2 = await _recv_until(
            ws,
            lambda m: m.get("kind") == "event" and m["event"]["kind"] == "judge_verdict",
        )
        assert verdict2["event"]["payload"]["case_id"] == "builtin-simple-ac"


@pytest.mark.anyio
async def test_ws_judge_case_error_payload(ws_url: str, monkeypatch) -> None:
    """评判抛异常 → judge_verdict payload 含 error（前端显示错误态）。"""
    async def boom(case, recorder, run_result, assistant_history):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(run_server, "_execute_judge", boom)

    async with connect(ws_url) as ws:
        await ws.recv()  # hello

        await _run_case_until_finished(ws, "c1", "builtin-simple-ac")

        await _send_cmd(ws, "c2", "judge_case")
        ack = await _recv_ack(ws, "c2")
        assert ack["ok"] is True

        verdict = await _recv_until(
            ws,
            lambda m: m.get("kind") == "event" and m["event"]["kind"] == "judge_verdict",
        )
        payload = verdict["event"]["payload"]
        assert "error" in payload
        assert "LLM down" in payload["error"]


@pytest.mark.anyio
async def test_ws_auto_judge_after_case_finished(ws_url: str, monkeypatch) -> None:
    """case 自然完成后自动终局评判：不发 judge_case，judge_verdict 自动经事件泵到达。"""
    async def fake_execute_judge(case, recorder, run_result, assistant_history):
        return _fake_verdict(case.id)

    monkeypatch.setattr(run_server, "_execute_judge", fake_execute_judge)

    async with connect(ws_url) as ws:
        await ws.recv()  # hello

        # 只发 run_case，不手动 judge_case
        await _send_cmd(ws, "c1", "run_case", {
            "case_id": "builtin-simple-ac",
            "fast_mode": True,
            "use_streaming": False,
        })
        ack = await _recv_ack(ws, "c1")
        assert ack["ok"] is True

        # case_finished 之后自动评判结果经事件泵推送
        verdict = await _recv_until(
            ws,
            lambda m: m.get("kind") == "event" and m["event"]["kind"] == "judge_verdict",
        )
        payload = verdict["event"]["payload"]
        assert payload["case_id"] == "builtin-simple-ac"
        assert payload["overall_passed"] is True
        assert payload["summary"] == "假裁判：全部通过"
