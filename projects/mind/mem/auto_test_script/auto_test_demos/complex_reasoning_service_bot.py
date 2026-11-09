"""
复杂推理服务适配器（AnyBotToTest 实现）。

这个文件的核心目标是把“线上复杂推理 HTTP 服务”包装成自动化评测框架可调用的 bot：
1) 统一构造请求体（query/chat_id/history/user_id/car_info 等）；
2) 兼容普通 JSON 与 SSE 流式响应；
3) 把流式字符拼接为完整 assistant 文本，保证 adump_history 可读；
4) 从 debug_info 抽取工具调用轨迹，补充 function_call/function_call_output；
5) 可选写入 mock 端状态与 mock 用户画像，复刻线上评测链路。
"""

import asyncio
import json
import os
import uuid
import datetime
from json import JSONDecodeError
from typing import Any

import httpx


DEFAULT_TEST_MOCK_ID = "mock_wd_m"
DEFAULT_AGENT_URL = (
    "https://complex-test.extour-inc.com/complex-reasoning-agent-lite/v1/agent/do/stream"
)
DEFAULT_INTENT_TYPE = "复杂推理"
DEFAULT_MAIN_ENGINE = "exturing_1.0_plus"
DEFAULT_MEM_MODE = "real"
DEFAULT_IS_TEST = True
DEFAULT_SERVICE_USER_ID = "dzy_test_complex"

DEFAULT_IS_SUBMIT_MOCK_INFO = True
DEFAULT_MONIQI_MOCK_URL = (
    "https://llm-test.extour-inc.com:18888/api/v1/clients/mock_wd_m/submit"
)
DEFAULT_MEM_PROFILE_MOCK_URL = (
    "https://context-inner-test.extour-inc.com/et-context/profile/add"
)
DEFAULT_MEM_EVENT_MOCK_URL = ""
DEFAULT_PROFILE_TYPE = "user_profile_v2"
DEFAULT_EVENT_TYPE = "user_event_v1"
DEFAULT_HAS_OBSERVATION = False
DEFAULT_SLEEP_INTERVAL = 0
DEFAULT_MEM_DAY_SUMMARY_URL = (
    "https://context-inner-test.extour-inc.com/et-context/summary/trigger/day"
)
DEFAULT_MEM_WEEK_SUMMARY_URL = (
    "https://context-inner-test.extour-inc.com/et-context/summary/trigger/recent"
)
DEFAULT_MEM_SUMMARY_QUERY_URL = (
    "https://context-inner-test.extour-inc.com/et-context/summary/query"
)


def _load_headers_from_env() -> dict[str, str]:
    """
    读取自定义请求头配置。

    环境变量 COMPLEX_REASONING_HEADERS_JSON 允许注入鉴权头等信息，
    默认只带 Content-Type，避免本地调试时因缺头导致请求失败。
    """
    raw = os.getenv("COMPLEX_REASONING_HEADERS_JSON", "").strip()
    if not raw:
        return {"Content-Type": "application/json"}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("COMPLEX_REASONING_HEADERS_JSON must be a JSON object")
    parsed.setdefault("Content-Type", "application/json")
    return {str(k): str(v) for k, v in parsed.items()}


class ComplexReasoningServiceBot:
    """
    被测复杂推理服务封装（AnyBotToTest 协议实现）。
    """

    agent_url: str = os.getenv("COMPLEX_REASONING_URL", DEFAULT_AGENT_URL).strip()
    is_submit_mock_info: bool = DEFAULT_IS_SUBMIT_MOCK_INFO
    moniqi_mock_url_template: str = os.getenv(
        "COMPLEX_REASONING_MOCK_URL_TEMPLATE", DEFAULT_MONIQI_MOCK_URL
    ).strip()
    mem_profile_url: str = os.getenv(
        "COMPLEX_REASONING_MEM_PROFILE_URL", DEFAULT_MEM_PROFILE_MOCK_URL
    ).strip()
    mem_event_url: str = os.getenv(
        "COMPLEX_REASONING_MEM_EVENT_URL", DEFAULT_MEM_EVENT_MOCK_URL
    ).strip()
    tenant_id: str = os.getenv("COMPLEX_REASONING_TENANT_ID", "").strip()
    default_profile_type: str = DEFAULT_PROFILE_TYPE
    default_event_type: str = DEFAULT_EVENT_TYPE
    has_observation: bool = DEFAULT_HAS_OBSERVATION
    sleep_interval: int = DEFAULT_SLEEP_INTERVAL
    mem_day_summary_url: str = DEFAULT_MEM_DAY_SUMMARY_URL
    mem_week_summary_url: str = DEFAULT_MEM_WEEK_SUMMARY_URL
    mem_summary_query_url: str = DEFAULT_MEM_SUMMARY_QUERY_URL
    default_headers: dict[str, str] = _load_headers_from_env()

    @classmethod
    def set_up_bot_to_test(
        cls,
        *,
        agent_url: str,
        moniqi_mock_url_template: str = DEFAULT_MONIQI_MOCK_URL,
        mem_profile_url: str = DEFAULT_MEM_PROFILE_MOCK_URL,
        mem_event_url: str = DEFAULT_MEM_EVENT_MOCK_URL,
        tenant_id: str = "",
        is_submit_mock_info: bool = DEFAULT_IS_SUBMIT_MOCK_INFO,
        profile_type: str = DEFAULT_PROFILE_TYPE,
        event_type: str = DEFAULT_EVENT_TYPE,
        has_observation: bool = DEFAULT_HAS_OBSERVATION,
        sleep_interval: int = DEFAULT_SLEEP_INTERVAL,
        mem_day_summary_url: str = DEFAULT_MEM_DAY_SUMMARY_URL,
        mem_week_summary_url: str = DEFAULT_MEM_WEEK_SUMMARY_URL,
        mem_summary_query_url: str = DEFAULT_MEM_SUMMARY_QUERY_URL,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        类级别配置入口。

        评测脚本在真正创建实例前，先调用这个方法把 URL、tenant、mock 开关等
        统一设好，这样每个 case 创建实例时会复用同一套运行参数。
        """
        cls.agent_url = agent_url
        cls.is_submit_mock_info = is_submit_mock_info
        cls.moniqi_mock_url_template = moniqi_mock_url_template
        cls.mem_profile_url = mem_profile_url
        cls.mem_event_url = mem_event_url
        cls.tenant_id = tenant_id
        cls.default_profile_type = profile_type
        cls.default_event_type = event_type
        cls.has_observation = has_observation
        cls.sleep_interval = sleep_interval
        cls.mem_day_summary_url = mem_day_summary_url
        cls.mem_week_summary_url = mem_week_summary_url
        cls.mem_summary_query_url = mem_summary_query_url
        if headers:
            merged = {"Content-Type": "application/json"}
            merged.update(headers)
            cls.default_headers = merged

    def __init__(self, context_config: dict[str, Any]):
        """
        每个 case 对应一个 bot 实例。

        说明：
        - session/chat 相关字段用于维持单次多轮上下文；
        - turn_records 是最终给 judge 的“可读对话历史”；
        - state_trace 保留原始请求/响应，便于回溯问题。
        """
        self.context_config = context_config
        self.session_id: str | None = None
        self.chat_id: str | None = None
        self.history_qa: list[dict[str, str]] = []
        self.turn_records: list[dict[str, str]] = []
        self.state_trace: list[dict[str, Any]] = []

        self.test_mock_id: str = (
            context_config.get("test_mock_id")
            or context_config.get("mock_id")
            or DEFAULT_TEST_MOCK_ID
        )
        self.intent_type: str = str(
            context_config.get("intent_type") or DEFAULT_INTENT_TYPE
        )
        self.main_engine: str = str(
            context_config.get("main_engine") or DEFAULT_MAIN_ENGINE
        )
        self.mem_mode: str = str(context_config.get("mem_mode") or DEFAULT_MEM_MODE)
        self.is_test: bool = bool(context_config.get("is_test", DEFAULT_IS_TEST))
        self.service_user_id: str = str(
            context_config.get("service_user_id")
            or context_config.get("user_id")
            or DEFAULT_SERVICE_USER_ID
        )
        # 不同“多次多轮对话”之间的等待秒数，用于给后端记忆抽取留生效时间。
        self.sleep_interval_seconds: int = int(
            context_config.get("sleep_interval", self.__class__.sleep_interval)
        )

        self.normalized_car_info: dict[str, Any] = self._normalize_car_info(
            context_config.get("car_info")
        )
        self.normalized_user_profile: str | dict[str, Any] | None = (
            self._normalize_user_profile(context_config.get("user_profile"))
        )
        # 显式初始化短期状态，避免实例复用时残留历史。
        self._reset_short_term_state()

    def _reset_short_term_state(self) -> None:
        """
        清空短期会话状态（对话记录/会话标识）。
        每次新 case 或新会话切换都应调用，防止短期记忆串场。
        """
        self.session_id = None
        self.chat_id = None
        self.history_qa = []
        self.turn_records = []

    async def aupdate_context(self, context_config: dict[str, Any]) -> None:
        """
        更新本次多轮对话上下文，使 mock_info 覆盖在原配置上生效。
        """
        self.context_config = dict(context_config)
        self.service_user_id = str(
            self.context_config.get("service_user_id")
            or self.context_config.get("user_id")
            or DEFAULT_SERVICE_USER_ID
        )
        self.intent_type = str(
            self.context_config.get("intent_type") or DEFAULT_INTENT_TYPE
        )
        self.main_engine = str(
            self.context_config.get("main_engine") or DEFAULT_MAIN_ENGINE
        )
        self.mem_mode = str(self.context_config.get("mem_mode") or DEFAULT_MEM_MODE)
        self.is_test = bool(self.context_config.get("is_test", DEFAULT_IS_TEST))
        self.test_mock_id = (
            self.context_config.get("test_mock_id")
            or self.context_config.get("mock_id")
            or DEFAULT_TEST_MOCK_ID
        )
        self.sleep_interval_seconds = int(
            self.context_config.get("sleep_interval", self.__class__.sleep_interval)
        )
        self.normalized_car_info = self._normalize_car_info(
            self.context_config.get("car_info")
        )
        self.normalized_user_profile = self._normalize_user_profile(
            self.context_config.get("user_profile")
        )
        self.current_mock_time: str | None = self.context_config.get("mock_time")

    async def _trigger_day_week_summary_if_needed(self) -> dict[str, Any] | None:
        """在会话切换时按 mock_time 触发日/周摘要，帮助长期记忆提取生效。"""
        mock_time = getattr(self, "current_mock_time", None)
        if not mock_time:
            return None
        tenant_id = self.__class__.tenant_id or self.main_engine
        if not tenant_id:
            return None
        day_url = self.context_config.get("mem_day_summary_url") or self.__class__.mem_day_summary_url
        week_url = self.context_config.get("mem_week_summary_url") or self.__class__.mem_week_summary_url
        query_url = self.context_config.get("mem_summary_query_url") or self.__class__.mem_summary_query_url
        if not day_url or not week_url or not query_url:
            return None
        try:
            dt = datetime.datetime.strptime(mock_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
        summary_day = dt.strftime("%Y-%m-%d")
        start_day = (dt - datetime.timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
        end_day = summary_day
        day_body = {
            "tenant_id": tenant_id,
            "unique_id": self.service_user_id,
            "summary_day": summary_day,
        }
        week_body = {
            "tenant_id": tenant_id,
            "unique_id": self.service_user_id,
            "start_day": start_day,
            "end_day": end_day,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            day_resp = await client.post(day_url, json=day_body, headers=self.__class__.default_headers)
            day_resp.raise_for_status()
            query_resp = await client.post(query_url, json=day_body, headers=self.__class__.default_headers)
            query_resp.raise_for_status()
            week_resp = await client.post(week_url, json=week_body, headers=self.__class__.default_headers)
            week_resp.raise_for_status()
        return {
            "mock_time": mock_time,
            "tenant_id": tenant_id,
            "summary_day": summary_day,
            "start_day": start_day,
            "end_day": end_day,
            "day_status": day_resp.status_code,
            "query_status": query_resp.status_code,
            "week_status": week_resp.status_code,
        }

    @staticmethod
    def _normalize_car_info(car_info: Any) -> dict[str, Any]:
        """
        将 case 中 car_info 归一化为 dict。

        支持两种输入：
        - dict：结构化车况，直接透传；
        - str：自然语言车况描述，封装到固定键下。
        """
        if isinstance(car_info, dict):
            return car_info
        if isinstance(car_info, str):
            text = car_info.strip()
            if text:
                return {"车辆状态描述": text}
        return {}

    @staticmethod
    def _normalize_user_profile(profile: Any) -> str | dict[str, Any] | None:
        """
        将 user_profile 归一化为 str/dict/None。
        """
        if isinstance(profile, dict):
            return profile
        if isinstance(profile, str):
            text = profile.strip()
            return text if text else None
        return None

    def _build_car_info_for_request(self) -> dict[str, Any]:
        """
        构造请求体 car_info 字段。

        关键点：
        - 强制注入 vehicle_id/main_engine，保证服务端路由逻辑稳定；
        - 若用户给的是车况字符串，放到 vehicle_state_text；
        - 若是结构化车况，整体并入。
        """
        request_car_info: dict[str, Any] = {
            "vehicle_id": self.service_user_id,
            "main_engine": self.main_engine,
        }
        if not self.normalized_car_info:
            return request_car_info
        if (
            len(self.normalized_car_info) == 1
            and "车辆状态描述" in self.normalized_car_info
        ):
            request_car_info["vehicle_state_text"] = self.normalized_car_info[
                "车辆状态描述"
            ]
            return request_car_info
        request_car_info.update(self.normalized_car_info)
        return request_car_info

    @staticmethod
    def _build_moniqi_mock_full_input(
        test_mock_id: str,
        perception: dict[str, Any],
        memory: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        生成模拟器 mock 接口所需 payload。

        该接口格式固定，端状态与记忆都放在 dataN 节点下，因此这里会把任意键值
        重新映射为 data1/data2/... 结构。
        """
        payload = {
            "event": {"name": "事件", "selection": {"selected": [], "multi_select": True}, "items": []},
            "vlm": {"name": "视觉信息", "selection": {"selected": [], "multi_select": True}, "items": []},
            "vehicle_state": {
                "name": "端状态",
                "selection": {"selected": ["test_for_perception"], "multi_select": True},
                "items": [{"item_id": "test_for_perception", "name": "临时测试端状态", "subtype": None, "data": {}}],
            },
            "memory": {
                "name": "记忆",
                "selection": {"selected": ["test_for_memory"], "multi_select": True},
                "items": [{"item_id": "test_for_memory", "name": "临时测试记忆", "subtype": None, "data": {}}],
            },
            "world_info": {"name": "世界信息", "selection": {"selected": [], "multi_select": True}, "items": []},
            "target_clients": [test_mock_id],
        }
        index = 0
        for k, v in perception.items():
            index += 1
            payload["vehicle_state"]["items"][0]["data"][f"data{index}"] = {
                "description": str(k),
                "example": v,
            }
        for k, v in (memory or {}).items():
            index += 1
            payload["memory"]["items"][0]["data"][f"data{index}"] = {
                "description": str(k),
                "example": v,
            }
        return payload

    @staticmethod
    def _extract_answer_text(result: Any) -> str:
        """
        从多种响应结构里提取“可展示文本”。
        """
        if isinstance(result, str):
            return result.strip()
        if isinstance(result, dict):
            for key in [
                "answer",
                "tts",
                "response",
                "reply",
                "content",
                "text",
                "final_answer",
                "talk_output",
            ]:
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for nested_key in ["data", "result", "output", "message"]:
                nested = result.get(nested_key)
                nested_text = ComplexReasoningServiceBot._extract_answer_text(nested)
                if nested_text:
                    return nested_text
        if isinstance(result, list):
            for item in reversed(result):
                text = ComplexReasoningServiceBot._extract_answer_text(item)
                if text:
                    return text
        return ""

    @staticmethod
    def _extract_text_from_sse_body(raw_text: str) -> str:
        """
        兼容流式接口返回的 text/event-stream 文本，尽量提取可读回复文本。
        """
        events = ComplexReasoningServiceBot._parse_sse_events(raw_text)
        if not events:
            return ""
        # 优先使用 debug_info 里的 talk_output，这通常是最终的完整助手话术。
        for event in reversed(events):
            debug_info = event.get("debug_info")
            if isinstance(debug_info, dict):
                talk_output = debug_info.get("talk_output")
                if isinstance(talk_output, str) and talk_output.strip():
                    return talk_output.strip()

        # 其次拼接流式 tts_text（字符流）
        tts_chunks: list[str] = []
        for event in events:
            tts = event.get("tts_text")
            if isinstance(tts, str) and tts:
                tts_chunks.append(tts)
        tts_text = "".join(tts_chunks).strip()
        if tts_text:
            return tts_text

        # 最后兜底拼接 content 字段
        content_chunks: list[str] = []
        for event in events:
            content = event.get("content")
            if isinstance(content, str) and content:
                content_chunks.append(content)
        return "".join(content_chunks).strip()

    @staticmethod
    def _parse_sse_events(raw_text: str) -> list[dict[str, Any]]:
        """
        解析 SSE body，返回结构化事件列表。
        """
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        events: list[dict[str, Any]] = []
        for line in lines:
            payload = line[5:].strip() if line.startswith("data:") else line
            if not payload or payload == "[DONE]":
                continue
            try:
                event = json.loads(payload)
            except JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    @staticmethod
    def _extract_tool_trace_from_debug_info(
        debug_info: dict[str, Any],
    ) -> list[dict[str, str]]:
        """
        从 debug_info 中提取精简可读的工具调用轨迹，便于 judge 理解行为链路。
        """
        traces: list[dict[str, str]] = []
        call_keys = [k for k in debug_info.keys() if "调用工具参数" in k]
        result_keys = [k for k in debug_info.keys() if "工具结果" in k]

        for key in sorted(call_keys):
            value = debug_info.get(key)
            if not isinstance(value, list):
                continue
            for item in value:
                if not isinstance(item, dict):
                    continue
                tool_name = str(item.get("task_name", "unknown_tool"))
                tool_param = item.get("param", "")
                traces.append(
                    {
                        "role": "function_call",
                        "name": tool_name,
                        "arguments": str(tool_param),
                    }
                )

        for key in sorted(result_keys):
            value = debug_info.get(key)
            if not isinstance(value, list):
                continue
            for item in value:
                if not isinstance(item, dict):
                    continue
                tool_name = str(item.get("tool_name", "unknown_tool"))
                tool_feedback = item.get("tool_feedback", "")
                traces.append(
                    {
                        "role": "function_call_output",
                        "name": tool_name,
                        "content": str(tool_feedback),
                    }
                )
        return traces

    @classmethod
    def _extract_tool_records_from_events(
        cls, events: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """
        优先从最终 debug_info 抽取工具轨迹；没有 debug_info 时回退到 observation 简要记录。
        """
        for event in reversed(events):
            debug_info = event.get("debug_info")
            if isinstance(debug_info, dict):
                traces = cls._extract_tool_trace_from_debug_info(debug_info)
                if traces:
                    return traces

        fallback: list[dict[str, str]] = []
        for event in events:
            plugin_name = event.get("plugin_name")
            observation = event.get("observation")
            if (
                isinstance(plugin_name, str)
                and plugin_name
                and isinstance(observation, str)
                and observation
                and observation != "{\"tasks\": [], \"status\": \"DONE\"}"
            ):
                fallback.append(
                    {
                        "role": "function_call_output",
                        "name": plugin_name,
                        "content": observation,
                    }
                )
        return fallback

    def _submit_mock_perception_if_needed(self) -> None:
        """
        可选：将 case 车况注入模拟器 mock。
        """
        if not self.normalized_car_info:
            return
        if not self.__class__.is_submit_mock_info:
            return
        if not self.__class__.moniqi_mock_url_template:
            return
        mock_url = self.__class__.moniqi_mock_url_template.format(self.test_mock_id)
        body = self._build_moniqi_mock_full_input(
            self.test_mock_id, self.normalized_car_info, {}
        )
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                mock_url,
                json=body,
                headers=self.__class__.default_headers,
            )
            resp.raise_for_status()

    def _submit_profile_memory_if_needed(self) -> None:
        """
        可选：将 case 用户画像注入 mock 记忆接口。
        """
        profile = self.normalized_user_profile
        if profile is None:
            return
        if not self.__class__.is_submit_mock_info:
            return
        if not self.__class__.mem_profile_url:
            return
        if not self.__class__.tenant_id:
            raise ValueError("提交 mock 画像记忆时必须提供 tenant_id")
        profile_type = (
            self.context_config.get("profile_type")
            or self.context_config.get("profile_types", [self.__class__.default_profile_type])[0]
        )
        if isinstance(profile, str):
            profile_payload = profile
        else:
            profile_payload = json.dumps(profile, ensure_ascii=False, indent=2)
        body = {
            "tenant_id": self.__class__.tenant_id,
            "unique_id": self.service_user_id,
            "profile_type": profile_type,
            "memory_info": {"user_profile": profile_payload},
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                self.__class__.mem_profile_url,
                json=body,
                headers=self.__class__.default_headers,
            )
            resp.raise_for_status()

    async def achat(self, query: str, session_id: str) -> str:
        """
        单轮异步对话。

        完整流程：
        1) 处理 session 切换；
        2) 发送请求到复杂推理服务；
        3) 兼容 JSON/SSE 两类响应并提取可读 answer；
        4) 抽取工具轨迹并写入 turn_records；
        5) 保存 state_trace 用于调试。
        """
        is_first_session = self.session_id is None
        is_session_switch = self.session_id is not None and self.session_id != session_id
        if is_first_session or is_session_switch:
            if is_session_switch and self.sleep_interval_seconds > 0:
                print(f"多次多轮对话之间间隔...{self.sleep_interval_seconds}秒")
                for _ in range(self.sleep_interval_seconds):
                    await asyncio.sleep(1)
                print("等待间隔时间到！")
            if is_session_switch:
                # 上一次会话结束后触发摘要提取，让画像/事件记忆可被后续会话消费。
                summary_trace = await self._trigger_day_week_summary_if_needed()
                if summary_trace is not None:
                    self.state_trace.append({"summary_trigger": summary_trace})
            # 每个 session（即 case 中的一次“多轮对话”）都先清短期状态，再开启新chat。
            self._reset_short_term_state()
            self.session_id = session_id
            self.chat_id = uuid.uuid4().hex

        request_body = {
            "intent_type": self.intent_type,
            "query": query,
            "chat_id": self.chat_id,
            "question_id": uuid.uuid4().hex,
            "history": self.history_qa,
            "mem_mode": self.mem_mode,
            "is_test": self.is_test,
            "test_mock_id": self.test_mock_id,
            "user_id": self.service_user_id,
            "car_info": self._build_car_info_for_request(),
        }
        response_text = ""
        data: Any = {}
        stream_error: Exception | None = None
        # 复杂推理服务是流式返回，偶发会出现 chunked body 提前断开。
        # 这里做有限重试，尽量把临时网络抖动/连接中断吸收在 bot 层，不让通用测试框架被异常打断。
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=90) as client:
                    response = await client.post(
                        self.__class__.agent_url,
                        json=request_body,
                        headers=self.__class__.default_headers,
                    )
                    response.raise_for_status()
                    response_text = response.text
                    try:
                        data = response.json()
                    except JSONDecodeError:
                        data = {"raw_text": response_text}
                stream_error = None
                break
            except (
                httpx.RemoteProtocolError,
                httpx.ReadError,
                httpx.ReadTimeout,
                httpx.WriteError,
                httpx.ConnectError,
                httpx.PoolTimeout,
            ) as exc:
                stream_error = exc
                if attempt < max_attempts:
                    await asyncio.sleep(attempt)
                    continue
                data = {
                    "error": f"stream read failed after {max_attempts} attempts",
                    "error_type": type(exc).__name__,
                    "error_detail": str(exc),
                }
            except httpx.HTTPStatusError as exc:
                stream_error = exc
                status_code = exc.response.status_code if exc.response else None
                response_text = exc.response.text if exc.response else ""
                data = {
                    "error": "http status error",
                    "status_code": status_code,
                    "raw_text": response_text,
                }
                break

        answer = self._extract_answer_text(data)
        if not answer and response_text:
            answer = self._extract_text_from_sse_body(response_text)
        if not answer and stream_error is not None:
            answer = f"（复杂推理服务响应异常：{type(stream_error).__name__}）"
        if not answer:
            # 兜底时避免把整段流式 body 灌进 history，保证可读性。
            answer = "（助手返回为空或不可解析）"
        events = self._parse_sse_events(response_text) if response_text else []
        tool_records = self._extract_tool_records_from_events(events)
        # history_qa 供下一轮请求拼装 history 使用（服务端消费格式）。
        self.history_qa.append({"q": query, "a": answer})
        # turn_records 供 judge 使用（人类可读格式）。
        self.turn_records.append({"role": "user", "content": query})
        self.turn_records.extend(tool_records)
        self.turn_records.append({"role": "assistant", "content": answer})
        self.state_trace.append(
            {"request": request_body, "response": data, "parsed_answer": answer}
        )
        return answer

    def chat(self, query: str, session_id: str) -> str:
        return asyncio.run(self.achat(query, session_id))

    async def adump_history(self) -> list[dict[str, str]]:
        """
        返回给自动评测框架的可读历史。
        """
        return list(self.turn_records)

    def dump_history(self) -> list[dict[str, str]]:
        return asyncio.run(self.adump_history())

    async def adump_state_trace(self) -> dict[str, Any]:
        """
        返回调试轨迹（请求与响应原文）。
        """
        return {
            "user_id": self.service_user_id,
            "chat_id": self.chat_id,
            "session_id": self.session_id,
            "test_mock_id": self.test_mock_id,
            "trace": self.state_trace,
        }

    async def dump_state_trace(self) -> dict[str, Any]:
        return await self.adump_state_trace()

    @classmethod
    def create(
        cls, context_config: dict[str, Any], *args: Any, **kwargs: Any
    ) -> "ComplexReasoningServiceBot":
        """
        框架工厂方法。

        框架会对每个 case 调用一次 create()，这里负责：
        - 合并 case 配置；
        - 初始化实例；
        - 按需提交 mock 端状态/画像。
        """
        if not cls.agent_url:
            raise ValueError(
                "请先配置 COMPLEX_REASONING_URL 或调用 set_up_bot_to_test(agent_url=...)"
            )
        merged = {**context_config, **kwargs}
        instance = cls(context_config=merged)
        # 每个case启动前显式清短期状态，确保不会带上上一个case的会话缓存。
        instance._reset_short_term_state()
        instance._submit_mock_perception_if_needed()
        instance._submit_profile_memory_if_needed()
        return instance
