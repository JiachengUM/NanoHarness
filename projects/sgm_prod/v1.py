from __future__ import annotations

import json
from datetime import datetime
from typing import Any, AsyncGenerator

from jinja2 import Template
from pydantic import BaseModel, Field

from aicore.agents.experiments.memory import (
    MemoryConsumerConfig,
    MemoryProducerConfig,
    UserInfoMetadata,
)
from aicore.agents.experiments.user_profile import UserProfile
from aicore.utils.nl_repr import nl_repr
from aicore.events.react import (
    ReActFinishEvent,
    ReActErrorEvent,
    ReActTextDeltaEvent,
    TaskToolDoneEvent,
)
from aicore.models.credentials import ModelName
from aicore.models.responses import ModelParams
from aicore.v1.experiments.agent import Agent, AgentContext, AgentEvent

from projects.mind.mem.volc_api import CollectionID

# from projects.mind.toolset import get_default_tools
from projects.experiments.s2s.s2s_agent_config import (
    build_v1_tools_with_timeout as get_default_tools,
)  # 如果v1要演示超时失败，请取消注释

# 与 auto_test_and_rl_data_generator.DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE 一致（内联，避免 import 拉入 langchain）
_DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE = """你是一个非常资深的管家兼司机，特别擅长在旅途中通过和车主对话，贴心地协助车主完成各种任务并让车主满意。

{% if user_profile %}
你服务的车主的基本信息如下：

{{user_profile}}
{% endif %}

此外，你们现在在车里，虽然你不是司机但是你是整辆车的管家。所以你还需要根据下述车辆状态信息来辅助车主完成任务：

{{car_info}}

作为优秀的管家，你已经很优秀，但是在工作方式上我还是要再次提醒你切记遵循一下几点：
  - 如果你通过笔记本很了解车主了，那么直接一些，不要让车主做很多选择的决策。
  - 不要再犯笔记本里出现过的以往你犯过的一些被车主纠正过的问题！！！
  - 你是非常聪明的，不要犯一些常识性的错误做一些不必要的动作或者明知不太可行却调用不必要的工具。
  - 除非车主直接下达了一个有精确目标的任务（包括但不限于一个精确的地点或者歌曲，打开空调，明确提到自己冷等等不需要推理或者从候选中选择的任务），否则你都需要在执行最终的任务前让用户确认一下任务的目标（如导航的地址，播放的歌曲）。
  - 还有，你的另外一个名字是：语音助手。
  - 你回复的内容是要用你的说出来的，所以注意不要回复出需要听众听超过1分钟的内容，也就是任何时候都别超过200个字，而且不要回复一些你无法，难以用嘴发音的生僻字符（包括但不限于任何表情符号，非常规的符号）。
  - 任何回复给车主的列表类的内容，你都要按照一般常识进行排序（如有评分的按照评分降序，有距离的按照从近到远排序，如果都有那么结合实际情况你自己做出合理的判断，这只是个例子，其他情况按照什么排序你可以自主判断。）
  - 对于任何你回复给车主的列表类内容，任何时候你都需要给出推荐理由并且让用户选择或者确认。比如“帮我导航到最近的xxx”这样的任务，你在搜索出几个结果并且知道列表信息里哪个是最符合条件的你也要和给出理由并且让用户确认一下。
  - 你很聪明，有时候一个用一个工具虽然暂时无法解决问题，但是可以尝试尝试用另一个工具来解决。比如任何时候你都可以尝试尝试网页搜索工具，什么信息都能搜到，不要太早放弃。
  - 
现在，仔细阅读至今你和用户的对话记录以及下面你笔记本上记录着的和车主相关的点点滴滴，，{% if thinking %}然后结合上面的工作方式回顾下面你与车主至今的互动情况，进行200字以内的思考，{% endif %}最后作为资深管家，体面而恰当地回复车主。"""

# 与 demo 默认值对齐（本文件内联，避免跨模块引用）
MEMORY_COLLECTION_NAME = "test_prompt"
DEFAULT_MEMORY_USER_ID = "记忆演示员"
DEFAULT_MEMORY_USER_NAME = "张"
TEST_ASSISTANT_ID = "Jarvis"
TEST_ASSISTANT_NAME = "贾维斯"
EVENT_MEMORY_TYPES = "event_v1"
MEMORY_LIMIT = 10
EVENT_MEMORY_LIMIT = 10
MEMORY_TYPES: list[str] = ["steward_note_book"]
_MEMORY_PRODUCER_SESSION_SIZE = 100

# 展车状态默认文案（时间与内容写死）
DEFAULT_VEHICLE_STATE_STR = """
        '当前系统时间': '{current_time}',
        '当前位置': '上海徐汇区徐汇滨江城开中心T2',
        '车辆当前档位': 'P档（驻车档）',
        '车辆当前行驶速度': '0 km/h（静止状态）',
        '车内温度': '24摄氏度（舒适模式）',
        '车外温度': '20摄氏度',
        '车辆动力模式（新能源车/混动车专用）': '纯电模式',
        '动力电池电量百分比（新能源车必需）': '70%',
        '剩余续航里程（新能源车）': '510 km',
        '天窗状态': '已打开',
        '遮阳帘状态': '关闭',
        '空调开启状态及模式': '关闭中',
        '车内空气质量（智能车功能）': 'PM2.5 15μg/m³（优）',
        '中控屏幕状态（智能车重点）': '演示模式 - 智能座舱功能展示页面',
        '语音助手唤醒词': '唤醒词"你好小涂"',
        '四轮胎压监测': '左前2.3bar，右前2.3bar，左后2.2bar，右后2.2bar（正常）',
        '总里程数': '15 km（展车测试里程）',
        '车辆告警/故障信息': '无告警',
        '车辆展示模式（车展专用）': '演示模式已开启'"""


def get_default_vehicle_state_str() -> str:
    """获取默认车辆状态文案，系统时间使用当前本地时间。"""
    return _DEFAULT_VEHICLE_STATE_TEMPLATE.format(
        current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


# 兼容旧代码直接 import 该常量；create_agent 未传 car_info 时会调用 get_default_vehicle_state_str 动态生成。
DEFAULT_VEHICLE_STATE_STR = get_default_vehicle_state_str()


def default_memory_user_info() -> UserInfoMetadata:
    """与 auto_test_demos 中 create_params_payload 默认 user/assistant 一致。"""
    return UserInfoMetadata(
        user_id=DEFAULT_MEMORY_USER_ID,
        user_name=DEFAULT_MEMORY_USER_NAME,
        assistant_id=TEST_ASSISTANT_ID,
        assistant_name=TEST_ASSISTANT_NAME,
    )


def default_memory_consumer_config() -> MemoryConsumerConfig:
    """与 demo_auto_test.create_params_payload 中 memory 相关字段默认值一致。"""
    return MemoryConsumerConfig(
        collection_id=CollectionID(
            collection_name=MEMORY_COLLECTION_NAME, project_name="default"
        ),
        system_prompt_profile_types=list(MEMORY_TYPES),
        search_profile_types=None,
        event_types=[EVENT_MEMORY_TYPES],
        event_limit=EVENT_MEMORY_LIMIT,
        profile_limit=MEMORY_LIMIT,
    )


def default_memory_producer_config() -> MemoryProducerConfig:
    """与 demo_auto_test.AgentWithMemoryToTest 中 producer 一致：memory_type = event_types + system_prompt_profile_types。"""
    event_types_list = [EVENT_MEMORY_TYPES]
    profile_types = list(MEMORY_TYPES)
    return MemoryProducerConfig(
        collection_id=CollectionID(
            collection_name=MEMORY_COLLECTION_NAME, project_name="default"
        ),
        memory_type=event_types_list + profile_types,
    )


class HistoryItem(BaseModel):
    q: str = Field(description="历史问题")
    a: str = Field(description="历史回答")


class AgentDoStreamRequest(BaseModel):
    """SGM Agent 流式请求参数"""

    chat_id: str = Field(description="会话ID")
    question_id: str | None = Field(default=None, description="问题ID")
    query: str = Field(description="用户输入的自然语言查询")
    history: list[HistoryItem] = Field(default_factory=list, description="历史对话记录")
    intent_type: str = Field(
        default="复杂推理", description="意图类型，如复杂推理、车控、媒体、导航"
    )
    car_info: dict[str, Any] = Field(default_factory=dict, description="车辆信息上下文")


class StreamChunk(BaseModel):
    """SSE 流式输出的单个数据块"""

    error_code: int = Field(default=0, description="错误码，0表示成功")
    tts_text: str = Field(default="", description="TTS语音合成文本")
    content: str = Field(default="", description="显示内容")
    rc: int = Field(default=1, description="返回码，0=开始、1=进行中、2=结束")
    observation: str | None = Field(default=None, description="工具调用结果")
    plugin_name: str | None = Field(
        default=None, description="工具名称，如function_call、websearch"
    )
    debug_info: dict[str, Any] | None = Field(default=None, description="调试信息")
    log_id: str | None = Field(default=None, description="日志ID")
    intent_type: str = Field(default="复杂推理", description="意图类型")


class SGMChunkTranslator:
    """将 ReActEvent 映射为 SGM StreamChunk。"""

    def __init__(self, req: AgentDoStreamRequest) -> None:
        self.req = req
        self.terminal_chunk: StreamChunk | None = None

    # 这一段纯粹是为了兼容旧的工具输出格式，未来可以删除
    def _chunk_from_tool_output(self, output: Any) -> StreamChunk | None:
        data = getattr(output, "data", None)
        if data is None:
            return None
        parsed = data.model_dump() if isinstance(data, BaseModel) else data
        if not isinstance(parsed, dict):
            return None

        if poi_list := parsed.get("pois") or parsed.get("list"):
            return StreamChunk(
                rc=1,
                observation=json.dumps({"list": poi_list}, ensure_ascii=False),
                plugin_name="poi_result",
                intent_type=self.req.intent_type,
            )

        if forecasts := parsed.get("forecasts"):
            return StreamChunk(
                rc=1,
                observation=json.dumps(forecasts, ensure_ascii=False),
                plugin_name="weather_result",
                intent_type=self.req.intent_type,
            )

        observation = parsed.get("observation")
        if observation is None:
            return None
        return StreamChunk(
            rc=1,
            observation=json.dumps(observation, ensure_ascii=False)
            if isinstance(observation, (dict, list))
            else str(observation),
            plugin_name="function_call",
            intent_type=self.req.intent_type,
        )

    def __call__(self, event: AgentEvent) -> list[StreamChunk]:
        if isinstance(event, ReActTextDeltaEvent):
            if not event.delta:
                return []
            return [
                StreamChunk(
                    tts_text=event.delta,
                    content=event.delta,
                    rc=1,
                    intent_type=self.req.intent_type,
                )
            ]

        if isinstance(event, TaskToolDoneEvent):
            chunk = self._chunk_from_tool_output(event.output)
            if chunk is not None:
                return [chunk]
            obs = event.output.nl_repr()
            if not obs:
                return []
            return [
                StreamChunk(
                    rc=1,
                    observation=obs,
                    plugin_name="function_call",
                    intent_type=self.req.intent_type,
                )
            ]

        if isinstance(event, ReActErrorEvent):
            self.terminal_chunk = StreamChunk(
                error_code=1,
                rc=2,
                debug_info={},
                log_id=self.req.question_id,
                intent_type=self.req.intent_type,
            )
            return []

        if isinstance(event, ReActFinishEvent):
            self.terminal_chunk = StreamChunk(
                rc=2,
                debug_info={},
                log_id=self.req.question_id,
                intent_type=self.req.intent_type,
            )
            return []

        return []


_SYSTEM_PROMPT_RENDERER = Template(_DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE)


def build_jarvis_system_prompt(
    *,
    user_profile: UserProfile | BaseModel | None = None,
    car_info: str | dict[str, Any] | None = None,
) -> str:
    car_source = car_info if car_info is not None else DEFAULT_VEHICLE_STATE_STR
    car_info_str = (
        nl_repr(car_source) if not isinstance(car_source, str) else car_source
    )
    profile_str = nl_repr(user_profile) if user_profile else ""
    return _SYSTEM_PROMPT_RENDERER.render(
        user_profile=profile_str,
        car_info=car_info_str,
    )


class SGMAgent(Agent):
    """
    在 aicore.v1.experiments.agent.Agent 的事件流之上，映射成 SGM 的 StreamChunk 输出。
    """

    def __init__(self, context: AgentContext, /) -> None:
        super().__init__(context)

    async def astream_chunks(
        self, req: AgentDoStreamRequest
    ) -> AsyncGenerator[StreamChunk, None]:
        # 首包：对齐现有接口，先发一个 rc=0 的初始化事件。
        yield StreamChunk(rc=0, intent_type=req.intent_type)

        chunk_translator = SGMChunkTranslator(req)

        async for event in super().astream(req.query):
            for chunk in chunk_translator(event):
                yield chunk

        if chunk_translator.terminal_chunk is not None:
            yield chunk_translator.terminal_chunk
        else:
            # 走完循环但没收到 Completed/Failed，说明中途出问题
            yield StreamChunk(
                error_code=1,
                rc=2,
                debug_info={},
                log_id=req.question_id,
                intent_type=req.intent_type,
            )


def create_agent(
    chat_id: str,
    *,
    model_name: ModelName = ModelName.SEED_1_8_251228,
    max_turns: int = 5,
    user_profile: UserProfile | BaseModel | None = None,
    car_info: str | dict[str, Any] | None = None,
    memory_user_info: UserInfoMetadata | None = None,
    memory_consumer_config: MemoryConsumerConfig | None = None,
    memory_producer_config: MemoryProducerConfig | None = None,
) -> SGMAgent:
    """
    memory 相关参数未传时使用本文件内与 demo 一致的默认工厂；producer 会话缓冲固定为 100。

    画像写入 Jinja 模板；AgentContext.user_profile 恒为 None，避免 Agent.system_prompt 再拼一段画像。
    car_info 未传时使用 get_default_vehicle_state_str() 动态生成默认车辆状态。

    S2S 多轮语音：结束一轮会话时需清空 ReAct 状态并把缓冲对话 flush 到火山，
    请使用 ``aicore.v1.experiments.agent.Agent.new_session``。
    TUI 演示侧用 ``projects.experiments.s2s.session_runner.SessionResetInterceptAgent``
    包裹 Agent，消费队列中的 ``SESSION_RESET_INPUT`` 哨兵并在 ``astream`` 入口调用 ``new_session``
    （见 ``S2STUIAgentApp`` / ``s2s_tui_agent_app_main.build_v1_runner_bundle``）。
    """
    model_params = ModelParams(model=model_name.value)
    resolved_user_info = memory_user_info or default_memory_user_info()
    resolved_consumer_config = (
        memory_consumer_config or default_memory_consumer_config()
    )
    resolved_producer_config = (
        memory_producer_config or default_memory_producer_config()
    )

    system_prompt_rendered = build_jarvis_system_prompt(
        user_profile=user_profile,
        car_info=car_info,
    )

    context = AgentContext(
        system_prompt=system_prompt_rendered,
        model_params=model_params,
        react_max_turns=max_turns,
        tools=get_default_tools(chat_id),
        user_profile=None,
        memory_user_info=resolved_user_info,
        memory_producer_config=resolved_producer_config,
        memory_producer_session_size=_MEMORY_PRODUCER_SESSION_SIZE,
        memory_consumer_config=resolved_consumer_config,
    )
    return SGMAgent(context)


__all__ = [
    "HistoryItem",
    "AgentDoStreamRequest",
    "StreamChunk",
    "SGMAgent",
    "build_jarvis_system_prompt",
    "create_agent",
    "default_memory_user_info",
    "default_memory_consumer_config",
    "default_memory_producer_config",
    "get_default_vehicle_state_str",
    "DEFAULT_VEHICLE_STATE_STR",
]
