from __future__ import annotations

from typing import Any, AsyncGenerator, Literal

from jinja2 import Template
from pydantic import BaseModel, ConfigDict, Field

from aicore.events.react import (
    ReActFinishEvent,
    ReActErrorEvent,
    ReActTextDeltaEvent,
    TaskToolDoneEvent,
    ToolCallStartEvent,
    ToolCallsDoneEvent,
)
from aicore.agents.experiments.base import AgentBase, AgentDumpPayload, AgentEvent, AgentState, RunParams
from aicore.agents.experiments.memory import MemoryConsumer, MemoryProducer
from aicore.agents.experiments.user_profile import UserProfile
from aicore.models.credentials import AsyncArk, ModelName, create_client
from aicore.models.responses import ResponseParams
from aicore.tools.task import TaskTool
from aicore.utils.nl_repr import nl_repr

from projects.sgm_prod.tools import build_tools


class HistoryItem(BaseModel):
    q: str = Field(description="历史问题")
    a: str = Field(description="历史回答")


class LngLat(BaseModel):
    """经纬度信息。"""

    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        multiple_of=0.000001,
        description="经度，单位度，取值范围[-180, 180]，精度到小数点后6位",
    )
    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        multiple_of=0.000001,
        description="纬度，单位度，取值范围[-90, 90]，精度到小数点后6位",
    )


class CarInfo(BaseModel):
    """车辆上下文信息。"""

    model_config = ConfigDict(extra="forbid")

    mainEngine: Literal["sgm"] = Field(..., description="主引擎标识，固定为'sgm'")
    vehicleId: str = Field(..., min_length=1, max_length=64, description="车辆唯一标识")
    vehicleType: Literal["NDBEV_MY27", "C1UL_MY27", "NCUB_MY26"] = Field(
        ...,
        description="车型代码枚举值",
    )
    vehicle_name: str = Field(..., description="车辆市售名称")
    sound_zone: Literal["主驾", "副驾", "左后", "右后", "前排", "后排"] = Field(
        ...,
        description="音区，即说话人当前位置",
    )

    province: str = Field(default="", description="当前位置省份，可为空字符串")
    city: str = Field(..., description="当前位置城市")
    district: str = Field(..., description="当前位置区/县")
    town: str = Field(default="", description="当前位置镇/街道，可为空字符串")
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        multiple_of=0.000001,
        description="当前位置经度，单位度，精度到小数点后6位",
    )
    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        multiple_of=0.000001,
        description="当前位置纬度，单位度，精度到小数点后6位",
    )

    audio_name: str = Field(..., description="音频名称（音乐、相声、有声读物等）")
    audio_producer: str = Field(..., description="音频制作人/歌手")
    video_name: str = Field(..., description="视频名称（电影、剧集、综艺等）")
    video_episodes: int = Field(..., ge=0, le=100000, description="视频集数，0表示未知或未指定")
    tts_language: Literal["mandarin", "cantonese", "english", "sichuan"] = Field(
        ...,
        description="TTS播报语言枚举",
    )

    current_location: str = Field(default="", description="用户当前位置描述，可为空字符串")
    target_location: str = Field(default="", description="用户询问目标地点，可为空字符串")
    home_location: str = Field(default="", description="用户家的位置描述，可为空字符串")
    home_lng_lat: LngLat | None = Field(default=None, description="用户家的经纬度信息")
    company_location: str = Field(default="", description="用户公司的位置描述，可为空字符串")
    company_lng_lat: LngLat | None = Field(default=None, description="用户公司的经纬度信息")

    nav_dest_name: str = Field(..., description="导航目的地名称")
    nav_dest_address: str = Field(..., description="导航目的地地址")
    nav_dest_lng_lat: LngLat | None = Field(default=None, description="导航目的地经纬度信息")
    nav_waypoint: str = Field(default="", description="导航途经点名称，可为空字符串")
    nav_remain_distance: str = Field(..., description="导航剩余距离描述，例如'160公里'")
    nav_remain_cost: str = Field(..., description="导航剩余时长描述，例如'150分钟'")
    nav_road_congestion: str = Field(..., description="道路拥堵情况描述，例如'畅通'")

    fatigue: Literal[0, 1] = Field(..., description="疲劳驾驶状态：0-不疲劳，1-疲劳")
    battery: int = Field(..., ge=0, le=100, description="电量百分比，范围0-100")
    rain_sensor: int = Field(..., ge=0, le=4, description="雨量传感器等级：0无雨、1小雨、2中雨、3大雨、4暴雨")
    car_heading: int = Field(
        ...,
        ge=0,
        le=360,
        description="车头朝向，0表示正北，顺时针取值，单位度，精度1度，取值范围0-360的整数",
    )


class AgentDoStreamRequest(BaseModel):
    """SGM Agent 流式请求参数"""
    chat_id: str = Field(description="会话ID")
    question_id: str | None = Field(default=None, description="问题ID")
    query: str = Field(description="用户输入的自然语言查询")
    history: list[HistoryItem] = Field(default_factory=list, description="历史对话记录")
    intent_type: str = Field(default="复杂推理", description="意图类型，如复杂推理、车控、媒体、导航")
    car_info: CarInfo | str | None = Field(default=None, description="车辆信息上下文")


class StreamChunk(BaseModel):
    """SSE 流式输出的单个数据块"""
    error_code: int = Field(default=0, description="错误码，0表示成功")
    tts_text: str = Field(default="", description="TTS语音合成文本")
    content: str = Field(default="", description="显示内容")
    rc: int = Field(default=1, description="返回码，0=开始、1=进行中、2=结束")
    observation: str | None = Field(default=None, description="工具调用结果")
    plugin_name: str | None = Field(default=None, description="工具名称，如function_call、websearch")
    debug_info: dict[str, Any] | None = Field(default=None, description="调试信息")
    log_id: str | None = Field(default=None, description="日志ID")
    intent_type: str = Field(default="复杂推理", description="意图类型")


class SGMChunkTranslator:
    """把 ReAct 事件映射成 SGM 的输出 chunk。"""

    def __init__(self, req: AgentDoStreamRequest) -> None:
        self.req = req
        self.terminal_chunk: StreamChunk | None = None
        # 按触发顺序记录工具调用信息，最终写入结束包 debug_info
        self.tool_calls: list[dict[str, str]] = []
        # 按轮次记录工具结果（顺序与 tool_calls 一致），便于排查
        self.tool_results: list[str] = []

    def __call__(self, event: AgentEvent) -> list[StreamChunk]:
        # 文本增量事件：输出 TTS 文本和显示内容
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

        # 工具调用开始事件：记录工具名和参数（保持调用顺序）
        if isinstance(event, ToolCallStartEvent):
            self.tool_calls.append(
                {
                    "name": event.name,
                    "arguments": event.arguments,
                }
            )
            return []

        # 工具调用完成事件：输出 observation
        if isinstance(event, TaskToolDoneEvent):
            obs = event.output.nl_repr()
            if not obs:
                return []
            return [StreamChunk(rc=1, observation=obs, plugin_name="function_call", intent_type=self.req.intent_type)]

        # 本轮全部工具完成事件：记录按工具调用顺序排列的结果
        if isinstance(event, ToolCallsDoneEvent):
            self.tool_results.extend(event.tool_results)
            return []

        debug_info = {
            "tool_calls": self.tool_calls,
            "tool_results": self.tool_results,
        }

        # Agent 失败事件：记录终止 chunk，稍后输出
        if isinstance(event, ReActErrorEvent):
            self.terminal_chunk = StreamChunk(
                error_code=1,
                rc=2,
                debug_info=debug_info,
                log_id=self.req.question_id,
                intent_type=self.req.intent_type,
            )
            return []

        # Agent 完成事件：记录终止 chunk，稍后输出
        if isinstance(event, ReActFinishEvent):
            self.terminal_chunk = StreamChunk(
                rc=2,
                debug_info=debug_info,
                log_id=self.req.question_id,
                intent_type=self.req.intent_type,
            )
            return []

        # 其他事件类型忽略
        return []


class DebugTranslator:
    """调试版 translator：可独立替换 SGMChunkTranslator 使用。"""

    def __init__(self, req: AgentDoStreamRequest) -> None:
        self.req = req
        self.terminal_chunk: StreamChunk | None = None
        self.tool_calls: list[dict[str, str]] = []
        self.tool_results: list[str] = []

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

        # 与基础 translator 的差异点：
        # tool start 不仅记录信息，还立即向外发一条 debug chunk。
        if isinstance(event, ToolCallStartEvent):
            tool_call = {
                "name": event.name,
                "arguments": event.arguments,
            }
            self.tool_calls.append(tool_call)
            return [
                StreamChunk(
                    rc=1,
                    plugin_name="function_call",
                    debug_info={
                        "event": "tool_call_start",
                        "tool_call": tool_call,
                    },
                    intent_type=self.req.intent_type,
                )
            ]

        if isinstance(event, TaskToolDoneEvent):
            obs = event.output.nl_repr()
            if not obs:
                return []
            return [StreamChunk(rc=1, observation=obs, plugin_name="function_call", intent_type=self.req.intent_type)]

        if isinstance(event, ToolCallsDoneEvent):
            self.tool_results.extend(event.tool_results)
            return []

        debug_info = {
            "tool_calls": self.tool_calls,
            "tool_results": self.tool_results,
        }
        if isinstance(event, ReActErrorEvent):
            self.terminal_chunk = StreamChunk(
                error_code=1,
                rc=2,
                debug_info=debug_info,
                log_id=self.req.question_id,
                intent_type=self.req.intent_type,
            )
            return []

        if isinstance(event, ReActFinishEvent):
            self.terminal_chunk = StreamChunk(
                rc=2,
                debug_info=debug_info,
                log_id=self.req.question_id,
                intent_type=self.req.intent_type,
            )
            return []

        return []


_SYSTEM_PROMPT_TEMPLATE = """\
你是一个智能车载助手，可以帮助用户控制车辆、播放媒体、导航和联网查询。

{% if user_profile %}
你服务的车主基本信息如下：
{{ user_profile }}
{% endif %}

{% if car_info %}
此外，当前车辆信息如下，请结合这些信息辅助车主完成任务：
{{ car_info }}
{% endif %}

请严格遵循以下指令：
- 在调用工具之前，先用一句话简要告知用户你将要做什么。
- 只调用与用户请求直接相关的工具，不要重复调用同一工具。
- 当用户当前指令包含省略表达或指代词时，应优先结合最近一轮对话中的明确对象进行补全理解。
- 如果上一轮已经明确操作对象，而当前轮是同一任务链上的省略表达，则默认沿用上一轮对象，不要重复追问。
- 对于连续车控指令，默认用户在延续上一个车控目标，除非用户明确切换到新的设备或功能。
- 只有在存在多个同等合理对象且无法根据最近上下文判断时，才向用户发起澄清。\
"""

_SYSTEM_PROMPT_RENDERER = Template(_SYSTEM_PROMPT_TEMPLATE)


class SGMAgent(AgentBase):
    """基于 AgentBase 的 SGM Agent，对外输出 StreamChunk。"""

    def __init__(
        self,
        system_prompt: str | None,
        run_params: RunParams,
        tools: list[TaskTool],
        *,
        state: AgentState | None = None,
        user_profile: UserProfile | None = None,
        memory_producer: MemoryProducer | None = None,
        memory_consumer: MemoryConsumer | None = None
    ) -> None:
        # 不传时使用动态渲染；传入时直接使用完整 system prompt
        super().__init__(system_prompt or "", run_params=run_params, tools=tools,
                         state=state, user_profile=user_profile, memory_producer=memory_producer, memory_consumer=memory_consumer)
        self._custom_system_prompt = system_prompt
        self._car_info: CarInfo | str | None = None

    @property
    async def system_prompt(self) -> str:
        system_to_return = ""
        if self._custom_system_prompt:
            system_to_return = self._custom_system_prompt
        else:
            user_profile_str = nl_repr(self.user_profile) if self.user_profile else ""
            car_info_str = nl_repr(self._car_info) if self._car_info else ""
            system_to_return = _SYSTEM_PROMPT_RENDERER.render(
                user_profile=user_profile_str,
                car_info=car_info_str,
            )

        if self.memory_consumer:
            # 记忆注入
            memory_rsp = await self.memory_consumer.retrieve_profiles()
            # TODO:缺少一个转化函数，把memory_rsp转化为字符串，先临时使用nl_repr
            memory_str = nl_repr(memory_rsp.data.result_list)
            if memory_str:
                system_to_return = f"{system_to_return}\n\n{memory_str}"
        return system_to_return
        
    @classmethod
    def build(
        cls,
        chat_id: str,
        *,
        system_prompt: str | None = None,
        model_name: ModelName = ModelName.SEED_1_8_251228,
        max_turns: int = 5,
        thinking_disabled: bool = True,
        user_profile: UserProfile | None = None,
        memory_producer: MemoryProducer | None = None,
        memory_consumer: MemoryConsumer | None = None,
    ) -> "SGMAgent":
        """工厂方法：简化 Agent 创建，自动配置模型客户端和工具"""
        params = ResponseParams(thinking={"type": "disabled"}) if thinking_disabled else None
        run_params = RunParams(
            model=model_name.value,
            params=params,
            max_turns=max_turns,
        )
        return cls(
            system_prompt=system_prompt,
            run_params=run_params,
            tools=build_tools(chat_id),
            state=None,
            user_profile=user_profile,
            memory_producer=memory_producer,
            memory_consumer=memory_consumer,
        )

    @classmethod
    def restore(
        cls,
        chat_id: str,
        payload: dict[str, Any],
    ) -> "SGMAgent":
        """从 dump payload 恢复 SGMAgent，对应base的create方法"""
        # 先把持久化结构反序列化成强类型对象，后续字段访问更安全。
        payload_obj = AgentDumpPayload.model_validate(payload)
        model_name = ModelName(payload_obj.run_params.model)
        client, model = create_client(model_name, AsyncArk)
        # dump 中 run_params 不包含运行期 client/model，这里补回可执行态依赖。
        run_params = payload_obj.run_params.model_copy(update={"client": client, "model": model})
        state = AgentState(history=payload_obj.history)

        restored_memory_producer = None
        restored_memory_consumer = None
        # restore 只做“按快照恢复”，记忆配置统一从 dump 重建。
        if payload_obj.memory:
            mem = payload_obj.memory
            user_info = mem.user_info
            if mem.producer:
                restored_memory_producer = MemoryProducer(
                    mem.producer.config,
                    user_info,
                    session_size=mem.producer.session_size,
                )
            if mem.consumer:
                restored_memory_consumer = MemoryConsumer(
                    mem.consumer.config,
                    user_info,
                )

        payload_prompt = str(payload_obj.system_prompt)
        restored_prompt = payload_prompt or None
        restored_user_profile = payload_obj.user_profile if isinstance(payload_obj.user_profile, UserProfile) else None

        return cls(
            system_prompt=restored_prompt,
            run_params=run_params,
            tools=build_tools(chat_id),
            state=state,
            user_profile=restored_user_profile,
            memory_producer=restored_memory_producer,
            memory_consumer=restored_memory_consumer,
        )

    async def astream_chunks(self, req: AgentDoStreamRequest) -> AsyncGenerator[StreamChunk, None]:
        """流式处理请求，逐步输出 StreamChunk"""
        # 每次请求前更新车辆上下文，供 system_prompt 动态渲染模式使用
        self._car_info = req.car_info

        # 发送开始信号
        yield StreamChunk(rc=0, intent_type=req.intent_type)

        # 创建 chunk 转换器，将 ReAct 事件转换为 StreamChunk
        chunk_translator = DebugTranslator(req)

        # 遍历父类事件流，转换并输出
        async for event in super().astream(
            req.query,
            event_listeners=[],
        ):
            for chunk in chunk_translator(event):
                yield chunk

        # 输出终止信号（正常结束）
        if chunk_translator.terminal_chunk is not None:
            yield chunk_translator.terminal_chunk
            return

        # 无终止信号则输出异常结束
        yield StreamChunk(
            error_code=1,
            rc=2,
            debug_info={},
            log_id=req.question_id,
            intent_type=req.intent_type,
        )


__all__ = [
    "HistoryItem",
    "LngLat",
    "CarInfo",
    "AgentDoStreamRequest",
    "StreamChunk",
    "SGMAgent",
    "SGMChunkTranslator",
    "DebugTranslator",
]
