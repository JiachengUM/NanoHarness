"""测试过程可视化服务器（M1：实时模式）。

FastAPI + 单条 WebSocket（对齐 v2_frontend 的命令-ACK 模式，为语音测试预留多路复用）：
- GET /            → 前端静态文件（frontend/dist 存在时挂载；dev 模式走 vite 代理）
- GET /api/health  → 健康检查
- WS  /ws          → 双向通道

协议：
- 上行命令: {kind:"command", command_id, command, payload}
  - list_cases {}                          → case 列表
  - run_case {case_id, assistant_kind?, chunk_delay?, fast_mode?, use_streaming?, nav_tool_delay?, auto_judge?}
  - stop_case {}
  - judge_case {}                          → 重新终局评判（run 结束后已自动评判过一次，可手动重评）
- 下行:
  - {kind:"hello", server_time}
  - {kind:"event", event: 信封}             → 双时间戳事件流（event_bus）
    - case 自然完成后服务器自动发起终局评判，judge_verdict 事件经事件泵推送
    - 手动 judge_case 的 judge_verdict 由命令处理层直接发到发起连接（不经事件泵）
  - {kind:"ack", command_id, ok, status, payload}
  - {kind:"error", message}

用法：
  D:\\apps\\miniconda\\envs\\dzy_env\\python.exe projects/experiments/time_travel_auto_test/visualizer/run_server.py
  前端 dev 模式: cd visualizer/frontend && npm run dev → http://localhost:5173
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from projects.experiments.time_travel_auto_test.case_runner.assistant_protocol import (
    AssistantEvent,
    AssistantEventType,
    StreamingReply,
)
from projects.experiments.time_travel_auto_test.case_runner.mock_assistant import (
    MockAssistant,
)
from projects.experiments.time_travel_auto_test.case_runner.runner import (
    CaseRunner,
    RunnerConfig,
)
from projects.experiments.time_travel_auto_test.case_schema import (
    FakePersonInfo,
    TestCase,
    VirtualCarInfo,
)
from projects.experiments.time_travel_auto_test.demos.run_e2e_demo import (
    build_builtin_case,
    build_builtin_case_with_acceleration,
    build_builtin_complex_case,
    build_builtin_god_view_case,
    build_builtin_interrupt_case,
    build_builtin_llm_speak_case,
    build_builtin_multi_search_case,
    build_builtin_navigation_case,
    build_builtin_parallel_tools_case,
    build_builtin_scheduled_task_case,
    build_builtin_time_awareness_case,
)
from projects.experiments.time_travel_auto_test.adapter_v2.mock_adapter import MockAdapter
from projects.experiments.time_travel_auto_test.adapter_v2.runner_v2 import AdapterRunner
from projects.experiments.time_travel_auto_test.fake_person.models import (
    FakePersonSpeakArgs,
    FakePersonSpeakPerformAction,
)
from projects.experiments.time_travel_auto_test.script_events.script_event import (
    FakePersonScriptEvent,
    VirtualCarPerformScriptEvent,
    VirtualCarSetStateArgs,
    VirtualCarSetStatePerformAction,
    VirtualCarStateCheckAction,
    VirtualCarStateCheckArgs,
    VirtualCarStateCheckScriptEvent,
)
from projects.experiments.time_travel_auto_test.visualizer.event_bus import EventBus

FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"

app = FastAPI(title="time_travel_auto_test visualizer")


# ---------------- case 仓库 ----------------

# 内置 case 工厂（demos/run_e2e_demo.py 的演示 case，覆盖全部机制）
_CASE_FACTORIES = [
    build_builtin_case,                       # 简单开空调
    build_builtin_god_view_case,              # 上帝视角改车态（剧本/助手混合来源）
    build_builtin_case_with_acceleration,     # 时间加速
    build_builtin_time_awareness_case,        # 时间感知
    build_builtin_llm_speak_case,             # LLM 自主对话（需 LLM）
    build_builtin_interrupt_case,             # 插话重叠
    build_builtin_scheduled_task_case,        # 定时任务 + 主动提醒
    build_builtin_complex_case,               # 综合：插话+定时+快进+记忆+恢复轮
    build_builtin_navigation_case,            # 多条件导航：长耗时工具区间
    build_builtin_multi_search_case,          # 多轮信息查询：网页+POI+音乐搜索（需 v2 助手）
    build_builtin_parallel_tools_case,        # 单轮四工具并行：网页+POI+音乐+导航（需 v2 助手）
]


def load_all_cases() -> list[TestCase]:
    return [factory() for factory in _CASE_FACTORIES]


# ---------------- demo mock 助手（多条件导航工具模拟） ----------------


class DemoToolMockAssistant(MockAssistant):  # noqa: D101 —— 见类 docstring
    """可视化 demo mock 助手：多条件导航指令模拟真实 ReAct 节奏。

    导航类指令（含"导航"或"机场"）的流式事件序列：
        TEXT_DELTA（承接语）→ TOOL_CALL（多条件参数）→（nav_tool_delay 执行）
        → TOOL_RESULT（路线摘要）→ TEXT_DELTA（总结语）

    工具执行期间的静默是 agent 正常节奏：不算流式停顿，工具区间在
    时间线/对话流单独可见（这正是要演示的效果）。非导航指令走基类
    纯文本行为，其余 case 的 mock 表现不变。
    """

    def __init__(self, nav_tool_delay: float = 6.0) -> None:
        super().__init__()
        self.nav_tool_delay = nav_tool_delay

    async def achat_stream(self, chunks: AsyncIterator[str]) -> StreamingReply:
        user_text = await self._collect_input(chunks)
        if "导航" not in user_text and "机场" not in user_text:
            # 非导航指令：基类行为（规则回复 + 一次性流式）
            reply = StreamingReply()
            await reply.put_chunk(await self.achat(user_text))
            await reply.finish()
            return reply
        reply = StreamingReply()
        asyncio.create_task(self._produce_navigation(reply, user_text))
        return reply

    async def _produce_navigation(self, reply: StreamingReply, user_text: str) -> None:
        try:
            dest = (
                "上海浦东国际机场T2航站楼"
                if "浦东" in user_text
                else "上海虹桥国际机场T2航站楼"
            )
            await reply.put_chunk("好的，条件不少，我逐项按您的要求筛选路线，稍等——")
            await reply.put_event(AssistantEvent(
                type=AssistantEventType.TOOL_CALL,
                wall_time=datetime.now(),
                tool_name="navigation_route_planning",
                tool_args={
                    "destination": dest,
                    "avoid_tolls": "收费" in user_text,
                    "avoid_congestion": "拥堵" in user_text,
                    "via": "星巴克" if "星巴克" in user_text else None,
                    "need_charging": "充电" in user_text or "电量" in user_text,
                    "arrive_before": "17:30",
                },
            ))
            await asyncio.sleep(self.nav_tool_delay)
            await reply.put_event(AssistantEvent(
                type=AssistantEventType.TOOL_RESULT,
                wall_time=datetime.now(),
                tool_name="navigation_route_planning",
                tool_result={
                    "status": "ok",
                    "route": (
                        f"{dest}｜全程 41.6km｜预计 48 分钟｜"
                        "避开收费与拥堵路段｜途经星巴克（含充电桩）"
                    ),
                },
                tool_duration_ms=self.nav_tool_delay * 1000,
            ))
            await reply.put_chunk(
                "规划好了：全程 41.6 公里，避开了收费和拥堵路段，中途会经过一家"
                "带充电桩的星巴克，预计 48 分钟到，赶五点半的飞机没问题。"
            )
            # 车态副作用：state_check 验证最终目的地
            if self.virtual_car is not None:
                self.virtual_car.set_field("导航目的地", dest)
        finally:
            await reply.finish()


async def make_assistant(assistant_kind: str, nav_tool_delay: float = 6.0):
    """构造被测助手。M1 默认 mock（无 LLM 依赖，联调快）；v2 走真实接入层（旧协议）；adapter_v2 走新协议 mock；v2_adapter 走真实 v2_agent + 新协议。"""
    if assistant_kind == "v2":
        from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test import (
            TestedAssistant,
        )

        return TestedAssistant()
    if assistant_kind == "adapter_v2":
        # 新协议（事件源适配器模式）：被验证对象是 MockAdapter，框架只通过
        # AssistantAdapter 接口驱动，彻底中立。
        return MockAdapter()
    if assistant_kind == "v2_adapter":
        # 新协议 + 真实 v2_agent：V2AgentAdapter 复用现有工具，框架只通过
        # AssistantAdapter 接口驱动（延迟 import，避免启动时加载 LLM 依赖）。
        from projects.experiments.time_travel_auto_test.demos.v2_agent_adapter.adapter import (
            V2AgentAdapter,
        )

        return V2AgentAdapter()
    # 默认 mock：导航类指令带长耗时工具模拟（nav_tool_delay 可由 run_case 选项覆盖）
    return DemoToolMockAssistant(nav_tool_delay=nav_tool_delay)


# ---------------- 运行上下文（全局互斥：同一时刻只允许一个 run） ----------------


class RunContext:
    """一次 run_case 的执行上下文：事件总线 → 队列 → WS 推送泵。

    case 跑完后保留 run 产物（case / runner.trace / run_result /
    assistant_history），供 judge_case 命令构造 JudgeInput 做终局评判。
    """

    def __init__(self) -> None:
        self.bus = EventBus()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.runner_task: Optional[asyncio.Task] = None
        self.pump_task: Optional[asyncio.Task] = None
        self.judge_task: Optional[asyncio.Task] = None
        self.case_id: str = ""
        # run 产物（judge_case 输入；_run 完成后填充）
        self.case: Optional[TestCase] = None
        # 旧协议为 CaseRunner、新协议为 AdapterRunner（二者都暴露 .trace 给裁判）
        self.runner: Any = None
        self.run_result: Any = None
        self.assistant_history: Optional[list[dict[str, str]]] = None

    def start(self, ws: WebSocket, case: TestCase, options: dict[str, Any]) -> None:
        self.case_id = case.id
        self.case = case
        self.bus.subscribe(self.queue.put_nowait)
        self.runner_task = asyncio.create_task(self._run(case, options))
        self.pump_task = asyncio.create_task(self._pump(ws))

    async def _run(self, case: TestCase, options: dict[str, Any]) -> None:
        assistant_kind = options.get("assistant_kind", "mock")
        config = RunnerConfig(
            use_streaming=options.get("use_streaming", True),
            fast_mode=options.get("fast_mode", False),
            chunk_delay=options.get("chunk_delay", 0.05),
        )
        assistant = None
        try:
            assistant = await make_assistant(
                assistant_kind,
                nav_tool_delay=float(options.get("nav_tool_delay", 6.0)),
            )
            if assistant_kind in ("adapter_v2", "v2_adapter"):
                # 新协议：使用 AdapterRunner（薄调度器，复用 TimelineEngine/TraceRecorder/虚拟车）
                runner = AdapterRunner(
                    assistant,
                    chunk_delay=config.chunk_delay,
                    fast_mode=config.fast_mode,
                    event_bus=self.bus,
                )
                self.runner = runner
                self.run_result = await runner.run(case)
            else:
                # 旧协议：使用 CaseRunner
                runner = CaseRunner(assistant=assistant, config=config, event_bus=self.bus)
                self.runner = runner
                self.run_result = await runner.run(case)
            # 导出助手视角对话历史（Judge 输入的一部分）
            try:
                if assistant_kind in ("adapter_v2", "v2_adapter"):
                    # 新协议只约定同步 dump_history（无 adump_history）
                    self.assistant_history = assistant.dump_history()
                else:
                    self.assistant_history = await assistant.adump_history()
            except Exception:  # noqa: BLE001 —— 历史导出失败不阻断 case 完成
                self.assistant_history = None
            # 自动终局评判：case 自然完成即触发（无需前端手动点）。
            # 结果经事件总线推送（与泵串行），评判结束后由 _auto_judge 停泵。
            if options.get("auto_judge", True):
                self.judge_task = asyncio.create_task(self._auto_judge())
        except asyncio.CancelledError:
            self.bus.emit(
                "case_cancelled", {"case_id": case.id, "reason": "用户停止"}, None
            )
            raise
        except Exception as e:  # noqa: BLE001 —— 服务器兜底，错误也必须推给前端
            self.bus.emit("run_error", {"case_id": case.id, "message": f"{e!r}"}, None)
        finally:
            # case 自然结束/出错也清全局运行状态——否则 _current_run 残留，
            # 后续 run_case 会被"已有 case 正在运行"永久拒绝（僵尸 run）
            global _current_run
            if _current_run is self:
                _current_run = None
            # 评判任务存在时泵由 _auto_judge 收尾（结果先入队再停泵），
            # 否则这里直接停泵
            if self.judge_task is None:
                await self.queue.put(None)  # 泵停止信号

    async def _auto_judge(self) -> None:
        """case 完成后自动评判：结果经事件总线推送（与泵串行，避免与泵
        并发 ws.send_json 的竞态），推送完毕停泵。"""
        assert self.case is not None and self.runner is not None
        try:
            payload = await _execute_judge(
                case=self.case,
                recorder=self.runner.trace,
                run_result=self.run_result,
                assistant_history=self.assistant_history,
            )
        except asyncio.CancelledError:
            raise  # shutdown 场景：泵由 shutdown() 收尾
        except Exception as e:  # noqa: BLE001 —— 评判失败也要告知前端
            payload = {"error": f"{e!r}"}
        self.bus.emit("judge_verdict", payload, None)
        await self.queue.put(None)  # 评判结果已入队，现在停泵

    async def _pump(self, ws: WebSocket) -> None:
        """事件泵：队列 → WS（json 推送）。"""
        try:
            while True:
                ev = await self.queue.get()
                if ev is None:
                    break
                await ws.send_json({"kind": "event", "event": ev})
        except Exception:
            pass  # 连接断开等场景由外层清理

    async def shutdown(self) -> None:
        """停止运行：取消 runner 和 judge 任务，停泵收尾。"""
        if self.runner_task is not None and not self.runner_task.done():
            self.runner_task.cancel()
            try:
                await self.runner_task
            except (asyncio.CancelledError, Exception):
                pass
        if self.judge_task is not None and not self.judge_task.done():
            self.judge_task.cancel()
            try:
                await self.judge_task
            except (asyncio.CancelledError, Exception):
                pass
        if self.pump_task is not None and not self.pump_task.done():
            await self.queue.put(None)  # 泵停止信号
            try:
                await asyncio.wait_for(self.pump_task, timeout=2.0)
            except Exception:
                self.pump_task.cancel()

    # ---------------- 终局评判（judge_case 命令） ----------------

    @property
    def judge_ready(self) -> bool:
        """是否具备评判条件：有已完成的 run 产物。"""
        return (
            self.run_result is not None
            and self.runner is not None
            and self.case is not None
        )


async def _execute_judge(
    case: TestCase,
    recorder: Any,
    run_result: Any,
    assistant_history: Optional[list[dict[str, str]]],
) -> dict[str, Any]:
    """构造 JudgeInput 并跑 Judge，返回 verdict 的 JSON dict。

    独立模块级函数——pytest 通过 monkeypatch 本函数注入假裁判，
    避免 judge_case 命令测试依赖真实 LLM。
    """
    from projects.experiments.time_travel_auto_test.judge.judge import (
        Judge,
        build_judge_input_from_run_result,
    )

    judge = Judge()
    judge_input = build_judge_input_from_run_result(
        case, recorder, run_result, assistant_history
    )
    verdict = await judge.ajudge(judge_input)
    return verdict.model_dump(mode="json")


# 全局运行状态（服务器内互斥：M1 单 run 模型）
_current_run: Optional[RunContext] = None
# 最近一次 run（含已完成的产物，供 judge_case 用；新 run / 断连时替换释放）
_last_run: Optional[RunContext] = None


async def _stop_current_run() -> None:
    """停止正在运行的 case（不清理 _last_run 的产物——stop 后仍可评判半程轨迹）。"""
    global _current_run
    if _current_run is not None:
        await _current_run.shutdown()
        _current_run = None


async def _judge_and_send(ws: WebSocket, ctx: RunContext) -> None:
    """后台评判并把 judge_verdict 事件直接发到发起命令的 WS。

    不走 RunContext 事件泵——case 自然结束后泵已停止，
    且重连/stop 后发起评判时泵绑定的连接可能已不是当前连接。
    """
    assert ctx.case is not None and ctx.runner is not None
    try:
        payload = await _execute_judge(
            case=ctx.case,
            recorder=ctx.runner.trace,
            run_result=ctx.run_result,
            assistant_history=ctx.assistant_history,
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 —— 评判失败也要告知前端
        payload = {"error": f"{e!r}"}
    try:
        await ws.send_json({"kind": "event", "event": {
            "seq": 0,
            "wall_time": _now_iso(),
            "mock_time": None,
            "kind": "judge_verdict",
            "payload": payload,
        }})
    except Exception:
        pass  # 连接已断开——评判结果丢弃


# ---------------- HTTP ----------------


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True, "running": _current_run is not None})


# ---------------- WebSocket ----------------


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    global _current_run, _last_run
    await ws.accept()
    await ws.send_json({"kind": "hello", "server_time": _now_iso()})
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("kind") != "command":
                await ws.send_json({"kind": "error", "message": "未知消息类型"})
                continue
            command_id = msg.get("command_id", "")
            command = msg.get("command", "")
            payload = msg.get("payload") or {}
            try:
                await _handle_command(ws, command_id, command, payload)
            except Exception as e:  # noqa: BLE001
                await ws.send_json(
                    {"kind": "ack", "command_id": command_id, "ok": False,
                     "status": "error", "payload": {"message": f"{e!r}"}}
                )
    except WebSocketDisconnect:
        pass
    finally:
        # 连接断开即停止后台执行（含评判任务），并释放 run 产物
        await _stop_current_run()
        if _last_run is not None:
            await _last_run.shutdown()
            _last_run = None


async def _handle_command(
    ws: WebSocket, command_id: str, command: str, payload: dict[str, Any]
) -> None:
    global _current_run, _last_run

    async def ack(ok: bool, status: str, data: Optional[dict] = None) -> None:
        await ws.send_json({
            "kind": "ack", "command_id": command_id, "ok": ok,
            "status": status, "payload": data or {},
        })

    if command == "list_cases":
        cases = load_all_cases()
        await ack(True, "completed", {
            "cases": [
                {"id": c.id, "case_name": c.case_name, "case_description": c.case_description}
                for c in cases
            ],
        })

    elif command == "run_case":
        if _current_run is not None:
            await ack(False, "rejected", {"message": "已有 case 正在运行，请先停止"})
            return
        case_id = str(payload.get("case_id", ""))
        case = next((c for c in load_all_cases() if c.id == case_id), None)
        if case is None:
            await ack(False, "not_found", {"message": f"case 不存在: {case_id}"})
            return
        # 替换旧 run（shutdown 停旧泵/旧评判任务，释放产物）
        if _last_run is not None and _last_run is not _current_run:
            await _last_run.shutdown()
        ctx = RunContext()
        ctx.start(ws, case, payload)
        _current_run = ctx
        _last_run = ctx
        await ack(True, "accepted", {"case_id": case_id})

    elif command == "stop_case":
        was_running = _current_run is not None
        await _stop_current_run()
        await ack(True, "completed", {"was_running": was_running})

    elif command == "judge_case":
        ctx = _current_run if _current_run is not None else _last_run
        if ctx is None or not ctx.judge_ready:
            await ack(False, "rejected", {"message": "没有已完成的 case 运行，请先运行 case"})
            return
        if ctx.judge_task is not None and not ctx.judge_task.done():
            await ack(False, "rejected", {"message": "评判正在进行中，请稍候"})
            return
        ctx.judge_task = asyncio.create_task(_judge_and_send(ws, ctx))
        await ack(True, "accepted", {})

    else:
        await ack(False, "unknown_command", {"message": f"未知命令: {command}"})


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat()


# ---------------- 静态文件（生产模式：vite build 产物） ----------------

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


def main() -> None:
    """命令行入口：uvicorn 启动。"""
    import uvicorn

    port = int(os.environ.get("VISUALIZER_PORT", "8800"))
    print(f"可视化服务器启动: http://127.0.0.1:{port}")
    if not FRONTEND_DIST.exists():
        print("（未发现 frontend/dist —— dev 模式请用 vite dev server 代理）")
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
