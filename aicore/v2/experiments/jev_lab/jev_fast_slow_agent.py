"""
Jev 快慢分工完整链路：Jev 路由分流 + 快路径直接执行工具 + ReAct 慢思考。

    用户输入 ──> JevRoutingAgent.astream(str)
                    │
                    ├─ Jev system_one（一次调用，~0.5s）
                    │   route(Choice) + needs_reasoning(Noul) + risk(Score)
                    │
                    ├─ ⚡ 快路径：简单意图且工具可直接执行
                    │   → 直接调工具 worker（跳过 ReAct 多轮 + LLM 生成）
                    │
                    └─ 🐢 慢路径：复杂/模糊/多工具意图
                        → 透传给内部 ReactAgentWithTaskRunner

要点：
- JevRoutingAgent 与 ReactAgentWithTaskRunner 实现 same AgentBase 协议，
  可直接替换进现有 AgentRunner（runner/printer/工具零改动）。
- TaskSuccessEvent（异步工具结果回灌）无条件走慢路径续接 ReAct 上下文。
- 快路径可直接执行的条件：工具 worker 接受自然语言 command（如车控/媒体，
  由火山 FC 端做提槽）。需要结构化参数的工具（天气/POI）Jev 提不了槽，走慢路径。

运行：
  PYTHONPATH=. .venv/bin/python aicore/v2/experiments/jev_lab/jev_fast_slow_agent.py
"""
from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, AsyncGenerator

from dotenv import load_dotenv
from typesafe_sdk import AsyncTypeSafeClient, Choice, Score, Noul

from aicore.models.credentials import ModelName
from aicore.events.agent import (
    AgentOutEvent,
    AgentOutTextDeltaEvent,
    AgentOutTextDoneEvent,
    AgentOutTextStartEvent,
)
from aicore.events.task import TaskEvent
from aicore.runtime.task import TaskManager
from aicore.simulation.user_env.data_source import UserDataMocked
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.agent_model import AgentBase, AgentInputEvent
from aicore.v2.agent_runner import AgentRunner
from aicore.v2.experiments.async_react_prompt import ASYNC_REACT_SYSTEM_PROMPT
from aicore.v2.experiments.react_agent_with_task_runner import (
    AgentTaskEventPrinter,
    ReactAgentWithTaskRunner,
    create_react_agent_with_task_runner,
)
from aicore.v2.experiments.task_cancel_tool import create_task_cancel_tool
from aicore.v2.experiments.weather_v2 import weather_search_v2_tool
from aicore.v2.experiments.poi_search_v2 import poi_search_v2_tool
from aicore.v2.experiments.music_search_v2 import qq_music_song_search_v2_tool
from projects.mind.toolset.car_control import CarControlTool
from projects.mind.toolset.media import MediaTool
from projects.mind.toolset.navigate import NavigateTool

load_dotenv(Path(__file__).parent / ".env")  # TYPESAFE_API_KEY

# ── 路由候选：对齐 v2 已有工具（name 与工具对象一致）+ 两个非工具选项 ──
ROUTES: dict[str, str] = {
    "car_control": "车载设备控制（空调、座椅、车窗、灯光等）",
    "media": "车载多媒体（播放/暂停/切歌、播放歌曲）",
    "navigation": "导航任务（开始/取消导航、路线调整）",
    "weather": "查询指定城市/时间的天气",
    "poi_search": "搜索地点（酒店、餐厅、停车场等）",
    "music_search": "搜索/推荐歌曲（QQ音乐单曲）",
    "reasoning_llm": "需要 substantial 推理、解释或长文本生成",
    "chitchat": "闲聊或简单问答，无需工具",
}

# 快路径可直接执行的 route：worker 接受自然语言 command，由 FC 端提槽。
# 其余工具（天气/POI/音乐）需要结构化参数，Jev 提不了开放槽位，走慢路径。
FAST_EXECUTABLE = {"car_control", "media"}

# 快路径判据阈值（实验值，可调）
REASONING_MAX = 0.4   # needs_reasoning 低于此值视为"无需慢思考"
CONFIDENCE_MIN = 0.8   # 路由置信度低于此值视为"路由模糊"
RISK_MAX = 0.7         # 风险高于此值视为"需要谨慎"


class JevRoutingAgent(AgentBase):
    """Jev 前置路由 + ReAct 兜底的快慢分工 agent（协议兼容，可直接替换进 AgentRunner）。"""

    def __init__(self, react_agent: ReactAgentWithTaskRunner) -> None:
        self._react_agent = react_agent
        self._jev = AsyncTypeSafeClient()  # 异步客户端：await 直接调用，无需 to_thread
        # route name -> 工具对象（快路径直接执行用）
        self._fast_tools = {t.name: t for t in react_agent.tools if t.name in FAST_EXECUTABLE}

    # ---------- AgentBase 协议：全部透传给内部 React agent ----------

    @property
    def context(self):
        return self._react_agent.context

    @property
    def state(self):
        return self._react_agent.state

    @property
    def tools(self) -> list[TaskToolProtocolGeneral]:
        return self._react_agent.tools

    async def new_session(self) -> None:
        await self._react_agent.new_session()

    async def dump(self):
        return await self._react_agent.dump()

    # ---------- 主流程 ----------

    async def astream(
        self, input: AgentInputEvent, /, **kwargs: Any
    ) -> AsyncGenerator[AgentOutEvent | TaskEvent, None]:
        # 异步工具结果回灌：必须走慢路径续接 ReAct 上下文
        if not isinstance(input, str):
            async for event in self._react_agent.astream(input, **kwargs):
                yield event
            return

        # Jev 快判断：一次调用同时拿到 路由/复杂度/风险
        t0 = perf_counter()
        d = await self._ask_jev(input)
        jev_ms = (perf_counter() - t0) * 1000

        # 分流决策：无需推理 + 路由收敛 + 低风险 + 工具可直接执行
        take_fast = (
            d["needs_reasoning"] < REASONING_MAX
            and d["confidence"] >= CONFIDENCE_MIN
            and d["risk"] <= RISK_MAX
            and d["route"] in FAST_EXECUTABLE
        )
        print(
            f"\n🔀 [Jev] {input!r}\n"
            f"   route={d['route']} (conf={d['confidence']:.2f}) "
            f"reasoning={d['needs_reasoning']} risk={d['risk']} 耗时={jev_ms:.0f}ms\n"
            f"   → {'⚡ 快路径(直接执行)' if take_fast else '🐢 慢路径(ReAct)'}"
        )

        if take_fast:
            # 快路径：直接调工具 worker（自然语言 command，FC 端提槽）
            result = await self._fast_tools[d["route"]].simple_worker(command=input)()
            status = getattr(getattr(result, "status", None), "value", None)
            if status == "error":
                reply = "抱歉，该服务暂时不可用，请稍后再试。"
            else:
                reply = getattr(result, "message", "") or "已执行。"
            async for event in _text_stream(reply):
                yield event
            return

        # 慢路径：透传给 ReAct agent
        async for event in self._react_agent.astream(input, **kwargs):
            yield event

    # ---------- Jev 快判断 ----------

    async def _ask_jev(self, user_message: str) -> dict[str, Any]:
        """一次 Jev 调用拿到路由/复杂度/风险三个维度的判断。"""
        response = await self._jev.system_one(
            state={"user_message": user_message, "available_tools": ROUTES},
            questions={
                "route": Choice(
                    instructions="Which tool or execution path is most appropriate?",
                    criteria=ROUTES,
                ),
                "needs_reasoning": Noul(
                    instructions="Does this request require substantial multi-step reasoning?"
                ),
                "risk": Score(
                    instructions="How consequential would an incorrect automated action be?",
                    criteria=["低风险且容易撤销", "中等后果", "高风险或难以撤销"],
                ),
            },
        )
        a = response.answers
        return {
            "route": a["route"].choice,
            "confidence": a["route"].confidence,
            "needs_reasoning": a["needs_reasoning"].noul,
            "risk": a["risk"].score,
        }


async def _text_stream(reply: str) -> AsyncGenerator[AgentOutEvent, None]:
    """把确定性文本包装成流式 AgentOut 事件（复用现有 printer 的流式渲染）。"""
    yield AgentOutTextStartEvent()
    for i in range(0, len(reply), 24):
        yield AgentOutTextDeltaEvent(delta=reply[i : i + 24])
    yield AgentOutTextDoneEvent()


def create_jev_fast_slow_agent(
    model: str,
    tools: list[TaskToolProtocolGeneral] | None = None,
    max_turns: int = 5,
    system_prompt: str = ASYNC_REACT_SYSTEM_PROMPT,
) -> JevRoutingAgent:
    """组装快慢分工 agent：内部创建 ReactAgentWithTaskRunner 作为慢路径。"""
    return JevRoutingAgent(
        create_react_agent_with_task_runner(
            model=model, tools=tools, max_turns=max_turns, system_prompt=system_prompt
        )
    )


# ============================================================
# 端到端验证
# ============================================================

CHAT_ID = "jev-fast-slow-test"

DEMO_INPUTS = [
    "打开车窗",                                          # ⚡ 快路径：car_control 直接执行
    "暂停播放",                                          # ⚡ 快路径：media 直接执行
    "播放周杰伦的晴天",                                   # 🐢 慢路径：music_search 职责与 media 重叠，路由模糊
    "请查香港今天的天气，找一家酒店，再推荐一首张学友的歌",  # 🐢 慢路径：多工具组合
    "你叫什么名字，介绍一下你能做什么",                     # 🐢 慢路径：chitchat 需 LLM 生成
]


def build_tools(task_manager: TaskManager) -> list[TaskToolProtocolGeneral]:
    """组装工具集（全部真实工具）。"""
    return [
        weather_search_v2_tool(chat_id=CHAT_ID, task_manager=task_manager),
        poi_search_v2_tool(task_manager=task_manager),
        qq_music_song_search_v2_tool(task_manager=task_manager),
        CarControlTool(chat_id=CHAT_ID),
        MediaTool(chat_id=CHAT_ID, task_manager=task_manager),
        NavigateTool(chat_id=CHAT_ID, task_manager=task_manager),
        create_task_cancel_tool(task_manager=task_manager),
    ]


async def main() -> None:
    task_manager = TaskManager()
    tools = build_tools(task_manager)

    agent = create_jev_fast_slow_agent(
        # SEED_1_8_251228 端点 RPM 配额紧张时持续 429，默认用 2.0 mini
        model=ModelName.SEED_2_0_MINI_260428,
        tools=tools,
    )

    await AgentRunner(
        user_data=UserDataMocked(DEMO_INPUTS),
        agent=agent,
        task_manager=task_manager,
        client=AgentTaskEventPrinter(),
    ).run()


if __name__ == "__main__":
    import anyio

    anyio.run(main)
