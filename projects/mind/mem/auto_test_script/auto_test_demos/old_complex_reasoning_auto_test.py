"""
复杂推理服务自动化测试脚本（旧链路版）
=====================================

目标：
1) 封装已部署复杂推理服务为 AnyBotToTest 协议；
2) 从 Mongo 拉取数据集或本地 mock case，执行自动评测并写报告；
3) 不启用火山记忆（不上传 history、不 reset 记忆库）。

数据集：
  - 默认从 Mongo 拉取 DATASET_NAMES（如「奔驰项目多轮对话测试集」）
  - USE_LOCAL_MOCK_CASES=True 时使用 build_cases() 本地用例
  - 环境变量 AUTO_TEST_DATASET_NAMES="A||B" 可覆盖数据集名

运行前请配置：
  COMPLEX_REASONING_URL
  COMPLEX_REASONING_HEADERS_JSON（可选，JSON字符串）
"""

import asyncio
import argparse
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import httpx

from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
    RunAllCasesResult,
    RunCaseResult,
)
from projects.mind.mem.auto_test_script.auto_test_demos.get_datasets import (
    get_dataset_list,
)
from projects.mind.mem.auto_test_script.case_schema import TestCase
from projects.mind.mem.volc_api import Message


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

# Mongo 数据集名（与 test_backend 后台「数据集名称」一致）；False 时从库拉取
DATASET_NAMES = ["奔驰项目多轮对话测试集"]
USE_LOCAL_MOCK_CASES = False
ENABLE_REMOTE_MOCK_SUBMIT = False
REPORT_DIR = str(Path(__file__).resolve().parent.parent / "auto_test_report")
JUDGE_LOG_PATH = os.path.join(REPORT_DIR, "old_complex_reasoning_judge_log.txt")
REPORT_MD_PATH = os.path.join(REPORT_DIR, "old_complex_reasoning_test_report.md")

DATASET_ALIAS_MAP = {
    "奔驰项目多轮对话测试集": "benz_multiturn",
}

# 从 case.context_config 移除，避免框架初始化火山记忆客户端
_VOLC_MEMORY_CONTEXT_KEYS = (
    "collection_name",
    "assistant_id",
    "profile_types",
    "event_types",
    "memory_limit",
    "event_limit",
)


def _parse_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_dataset_names_from_env(default: list[str]) -> list[str]:
    raw = os.getenv("AUTO_TEST_DATASET_NAMES", "").strip()
    if not raw:
        return default
    names = [x.strip() for x in raw.split("||") if x.strip()]
    return names or default


def _build_output_paths(
    dataset_names: list[str],
    default_log_path: str,
    default_report_path: str,
) -> tuple[str, str]:
    custom_log_path = os.getenv("AUTO_TEST_JUDGE_LOG_PATH", "").strip()
    custom_report_path = os.getenv("AUTO_TEST_REPORT_MD_PATH", "").strip()
    if custom_log_path and custom_report_path:
        return custom_log_path, custom_report_path
    if len(dataset_names) == 1:
        dataset_name = dataset_names[0]
        alias = DATASET_ALIAS_MAP.get(dataset_name, dataset_name)
        alias = re.sub(r"[^\w\-]+", "_", alias).strip("_").lower() or "dataset"
        log_path = os.path.join(REPORT_DIR, f"old_complex_reasoning_{alias}_judge_log.txt")
        report_path = os.path.join(REPORT_DIR, f"old_complex_reasoning_{alias}_report.md")
        return custom_log_path or log_path, custom_report_path or report_path
    return custom_log_path or default_log_path, custom_report_path or default_report_path


def patch_cases_default_context(cases: list[TestCase]) -> None:
    """为 Mongo 数据集 case 补全复杂推理服务默认 context_config（不含火山记忆字段）。"""
    for case in cases:
        case.context_config.setdefault("intent_type", DEFAULT_INTENT_TYPE)
        case.context_config.setdefault("main_engine", DEFAULT_MAIN_ENGINE)
        case.context_config.setdefault("mem_mode", DEFAULT_MEM_MODE)
        case.context_config.setdefault("is_test", DEFAULT_IS_TEST)
        case.context_config.setdefault("test_mock_id", DEFAULT_TEST_MOCK_ID)
        case.context_config.setdefault("profile_type", DEFAULT_PROFILE_TYPE)
        case.context_config.setdefault("event_type", DEFAULT_EVENT_TYPE)
        case.context_config.setdefault("is_submit_mock_info", DEFAULT_IS_SUBMIT_MOCK_INFO)
        case.context_config.setdefault("has_observation", DEFAULT_HAS_OBSERVATION)
        case.context_config.setdefault("sleep_interval", DEFAULT_SLEEP_INTERVAL)
        case.context_config.setdefault("mem_day_summary_url", DEFAULT_MEM_DAY_SUMMARY_URL)
        case.context_config.setdefault("mem_week_summary_url", DEFAULT_MEM_WEEK_SUMMARY_URL)
        case.context_config.setdefault("mem_summary_query_url", DEFAULT_MEM_SUMMARY_QUERY_URL)


def strip_volc_memory_fields(cases: list[TestCase]) -> None:
    for case in cases:
        for key in _VOLC_MEMORY_CONTEXT_KEYS:
            case.context_config.pop(key, None)


def isolate_case_user_ids_per_run(cases: list[TestCase]) -> str:
    run_id = uuid.uuid4().hex[:8]
    for case in cases:
        raw_user_id = str(
            case.context_config.get("user_id") or case.case_id or "old_complex_user"
        )
        safe_user_id = re.sub(r"[^\w\-]+", "_", raw_user_id).strip("_") or "old_complex_user"
        case.context_config["user_id"] = f"{safe_user_id}_run_{run_id}"
    return run_id


def _load_headers_from_env() -> dict[str, str]:
    """
    读取请求头环境变量，便于按环境注入鉴权头。
    """
    raw = os.getenv("COMPLEX_REASONING_HEADERS_JSON", "").strip()
    if not raw:
        return {"Content-Type": "application/json"}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("COMPLEX_REASONING_HEADERS_JSON 必须是 JSON object")
        parsed.setdefault("Content-Type", "application/json")
        return {str(k): str(v) for k, v in parsed.items()}
    except Exception as exc:
        raise ValueError(
            "COMPLEX_REASONING_HEADERS_JSON 解析失败，请传入合法JSON对象字符串"
        ) from exc


class OldComplexReasoningServiceBot:
    """
    将已部署复杂推理服务封装为 AnyBotToTest 协议。

    设计说明（和 case 的对接方式）：
    1) case.context_config["car_info"]
       - 支持 dict（结构化端状态）；
       - 支持 str（一整段端状态描述文本）。
    2) case.context_config["user_profile"]
       - 支持 dict（结构化画像）；
       - 支持 str（一整段画像文本）。
    3) create() 时会优先把 car_info/user_profile 注入 mock 链路；
       对话阶段再把 car_info 注入 agent 请求体，保证“mock + 实时上下文”都可用。
    """

    # 注意：agent_url 需要在运行时通过 --agent-url 显式指定。
    agent_url: str = os.getenv("COMPLEX_REASONING_URL", DEFAULT_AGENT_URL).strip()
    # 以下是你给出的默认配置，除非显式覆盖，否则直接使用这些值。
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
        moniqi_mock_url_template: str = "",
        mem_profile_url: str = "",
        mem_event_url: str = "",
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
        cls.agent_url = agent_url
        cls.is_submit_mock_info = is_submit_mock_info
        cls.moniqi_mock_url_template = (
            moniqi_mock_url_template or DEFAULT_MONIQI_MOCK_URL
        )
        cls.mem_profile_url = mem_profile_url or DEFAULT_MEM_PROFILE_MOCK_URL
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

    def __init__(
        self,
        *,
        user_id: str,
        context_config: dict[str, Any],
    ):
        # 每个 bot 实例对应一个 case（更准确地说是一个 case 的一次运行配置）。
        self.user_id = user_id
        self.context_config = context_config
        # session_id/chat_id 用于维持被测服务的多轮上下文。
        self.session_id: str | None = None
        self.chat_id: str | None = None
        # history_qa 是发给服务端的历史格式：[{q:..., a:...}, ...]
        self.history_qa: list[dict[str, str]] = []
        # turn_records 是给 judge 用的精简互动记录：[{role, content}, ...]
        self.turn_records: list[dict[str, str]] = []
        # state_trace 用于调试追踪请求/响应原始数据。
        self.state_trace: list[dict[str, Any]] = []
        # 用户可在 case 里覆盖 test_mock_id；否则使用默认值 mock_wd_m。
        self.test_mock_id: str = (
            context_config.get("test_mock_id")
            or context_config.get("mock_id")
            or DEFAULT_TEST_MOCK_ID
        )
        # 这组字段用于构建复杂推理接口请求体，默认值和你提供的参数保持一致。
        self.intent_type: str = str(
            context_config.get("intent_type") or DEFAULT_INTENT_TYPE
        )
        self.main_engine: str = str(
            context_config.get("main_engine") or DEFAULT_MAIN_ENGINE
        )
        self.mem_mode: str = str(context_config.get("mem_mode") or DEFAULT_MEM_MODE)
        self.is_test: bool = bool(
            context_config.get("is_test", DEFAULT_IS_TEST)
        )
        self.service_user_id: str = str(
            context_config.get("service_user_id")
            or context_config.get("user_id")
            or DEFAULT_SERVICE_USER_ID
        )
        # 统一把 case 中可能是 str/dict 的 car_info 归一化，后续复用。
        self.normalized_car_info: dict[str, Any] = self._normalize_car_info(
            context_config.get("car_info")
        )
        # 保留 user_profile 原始值（str 或 dict），记忆注入时直接使用。
        self.normalized_user_profile: str | dict[str, Any] | None = (
            self._normalize_user_profile(context_config.get("user_profile"))
        )

    async def aupdate_context(self, context_config: dict[str, Any]) -> None:
        """更新本次多轮对话生效的上下文配置。"""
        self.context_config = dict(context_config)
        self.service_user_id = str(
            self.context_config.get("service_user_id")
            or self.context_config.get("user_id")
            or DEFAULT_SERVICE_USER_ID
        )
        self.test_mock_id = (
            self.context_config.get("test_mock_id")
            or self.context_config.get("mock_id")
            or DEFAULT_TEST_MOCK_ID
        )
        self.intent_type = str(
            self.context_config.get("intent_type") or DEFAULT_INTENT_TYPE
        )
        self.main_engine = str(
            self.context_config.get("main_engine") or DEFAULT_MAIN_ENGINE
        )
        self.mem_mode = str(self.context_config.get("mem_mode") or DEFAULT_MEM_MODE)
        self.is_test = bool(self.context_config.get("is_test", DEFAULT_IS_TEST))
        self.normalized_car_info = self._normalize_car_info(
            self.context_config.get("car_info")
        )
        self.normalized_user_profile = self._normalize_user_profile(
            self.context_config.get("user_profile")
        )

    @staticmethod
    def _normalize_car_info(car_info: Any) -> dict[str, Any]:
        """
        将 case.context_config["car_info"] 归一化为 dict。

        兼容输入：
        - dict: 直接使用；
        - str: 包装为 {"车辆状态描述": "<原始字符串>"}，便于 mock 感知注入；
        - 其他: 视为无端状态。
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
        将 case.context_config["user_profile"] 做最小归一化。

        支持 str/dict；空字符串和其他类型视为未提供。
        """
        if isinstance(profile, dict):
            return profile
        if isinstance(profile, str):
            text = profile.strip()
            return text if text else None
        return None

    def _build_car_info_for_request(self) -> dict[str, Any]:
        """
        构建发给复杂推理服务的 request_body["car_info"]。

        规则：
        - 必带 vehicle_id（与旧适配器保持一致）；
        - 如果 case 给了 car_info，则一并放入请求体；
        - car_info 为字符串时，放入 "vehicle_state_text" 字段，保持语义清晰。
        """
        request_car_info: dict[str, Any] = {
            "vehicle_id": self.service_user_id,
            "main_engine": self.main_engine,
        }
        if not self.normalized_car_info:
            return request_car_info
        # 字符串 car_info 归一化后会是 {"车辆状态描述": "..."}，请求体里转成统一文本字段。
        if (
            len(self.normalized_car_info) == 1
            and "车辆状态描述" in self.normalized_car_info
        ):
            request_car_info["vehicle_state_text"] = self.normalized_car_info[
                "车辆状态描述"
            ]
            return request_car_info
        # dict 形式 car_info：整体并入请求体，让服务端按既有字段解析。
        request_car_info.update(self.normalized_car_info)
        return request_car_info

    @staticmethod
    def _build_moniqi_mock_full_input(
        test_mock_id: str,
        perception: dict[str, Any],
        memory: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
                nested_text = OldComplexReasoningServiceBot._extract_answer_text(nested)
                if nested_text:
                    return nested_text
        if isinstance(result, list):
            for item in reversed(result):
                text = OldComplexReasoningServiceBot._extract_answer_text(item)
                if text:
                    return text
        return ""

    @staticmethod
    def _parse_sse_events(raw_text: str) -> list[dict[str, Any]]:
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        events: list[dict[str, Any]] = []
        for line in lines:
            payload = line[5:].strip() if line.startswith("data:") else line
            if not payload or payload == "[DONE]":
                continue
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    @staticmethod
    def _extract_text_from_sse_body(raw_text: str) -> str:
        events = OldComplexReasoningServiceBot._parse_sse_events(raw_text)
        if not events:
            return ""
        for event in reversed(events):
            debug_info = event.get("debug_info")
            if isinstance(debug_info, dict):
                talk_output = debug_info.get("talk_output")
                if isinstance(talk_output, str) and talk_output.strip():
                    return talk_output.strip()
        tts_chunks: list[str] = []
        for event in events:
            tts = event.get("tts_text")
            if isinstance(tts, str) and tts:
                tts_chunks.append(tts)
        tts_text = "".join(tts_chunks).strip()
        if tts_text:
            return tts_text
        content_chunks: list[str] = []
        for event in events:
            content = event.get("content")
            if isinstance(content, str) and content:
                content_chunks.append(content)
        return "".join(content_chunks).strip()

    @staticmethod
    def _looks_like_sse(raw_text: str) -> bool:
        text = raw_text.lstrip()
        return text.startswith("data:") or "\ndata:" in text

    @staticmethod
    def _resolve_answer(response_text: str, data: Any) -> str:
        if response_text and OldComplexReasoningServiceBot._looks_like_sse(response_text):
            answer = OldComplexReasoningServiceBot._extract_text_from_sse_body(response_text)
            if answer:
                return answer
        return OldComplexReasoningServiceBot._extract_answer_text(data)

    def _submit_mock_perception_if_needed(self) -> None:
        """
        如配置了模拟器 mock url，则把 case 中 car_info 注入模拟器端状态。

        这里 car_info 支持字符串：
        - 字符串会先归一化为 {"车辆状态描述": "..."}；
        - 最终会被转换为模拟器的 dataN 字段结构。
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
        如配置了记忆 mock 接口，则把 case 中 user_profile 注入画像记忆。

        支持：
        - user_profile 为字符串：直接作为 user_profile 文本；
        - user_profile 为 dict：转为 JSON 字符串后写入 user_profile 字段。
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
            "unique_id": self.user_id,
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
        单轮异步对话入口（旧链路版）。

        兼容 JSON 与 text/event-stream（SSE）两类响应。
        """
        is_first_session = self.session_id is None
        is_session_switch = self.session_id is not None and self.session_id != session_id
        if is_first_session or is_session_switch:
            self.session_id = session_id
            self.chat_id = uuid.uuid4().hex
            self.history_qa = []
            self.turn_records = []

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
                    except json.JSONDecodeError:
                        data = {}
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
                response_text = exc.response.text if exc.response else ""
                data = {
                    "error": "http status error",
                    "status_code": exc.response.status_code if exc.response else None,
                    "raw_text": response_text,
                }
                break

        answer = self._resolve_answer(response_text, data)
        if not answer and stream_error is not None:
            answer = f"（复杂推理服务响应异常：{type(stream_error).__name__}）"
        if not answer:
            answer = "（助手返回为空或不可解析）"

        self.history_qa.append({"q": query, "a": answer})
        self.turn_records.append({"role": "user", "content": query})
        self.turn_records.append({"role": "assistant", "content": answer})
        trace_response: Any = data
        if response_text and self._looks_like_sse(response_text):
            events = self._parse_sse_events(response_text)
            if events:
                trace_response = {"sse_events": events, "parsed_answer": answer}
        self.state_trace.append(
            {"request": request_body, "response": trace_response, "parsed_answer": answer}
        )
        return answer

    def chat(self, query: str, session_id: str) -> str:
        return asyncio.run(self.achat(query, session_id))

    def dump_history(self) -> list[dict[str, str]]:
        return asyncio.run(self.adump_history())

    async def adump_history(self) -> list[dict[str, str]]:
        return list(self.turn_records)

    async def adump_state_trace(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "session_id": self.session_id,
            "test_mock_id": self.test_mock_id,
            "trace": self.state_trace,
        }

    async def dump_state_trace(self) -> dict[str, Any]:
        return await self.adump_state_trace()

    @classmethod
    async def aclean_memory_for_users(
        cls,
        user_ids: list[str],
        *,
        context_config: dict[str, Any] | None = None,
        except_skills: bool = False,
    ) -> None:
        """满足 AnyBotToTest 协议；本 bot 不在此清火山记忆。"""
        return

    @classmethod
    def create(
        cls,
        context_config: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> "OldComplexReasoningServiceBot":
        # 必须提供被测服务 URL，否则无法执行真实自动化测试。
        if not cls.agent_url:
            raise ValueError(
                "请先配置 COMPLEX_REASONING_URL 或调用 set_up_bot_to_test(agent_url=...)"
            )
        merged = {**context_config, **kwargs}
        # 优先使用 case 内 user_id；缺失时自动生成，避免 case 之间相互污染。
        user_id = merged.get("user_id") or f"auto_test_{uuid.uuid4().hex[:8]}"
        instance = cls(user_id=user_id, context_config=merged)
        instance._submit_mock_perception_if_needed()
        return instance


def build_cases() -> list[TestCase]:
    """本地 mock 用例（无火山记忆字段）。"""
    base_context = {
        "intent_type": DEFAULT_INTENT_TYPE,
        "main_engine": DEFAULT_MAIN_ENGINE,
        "mem_mode": DEFAULT_MEM_MODE,
        "is_test": DEFAULT_IS_TEST,
        "user_id": DEFAULT_SERVICE_USER_ID,
        "test_mock_id": DEFAULT_TEST_MOCK_ID,
        "is_submit_mock_info": DEFAULT_IS_SUBMIT_MOCK_INFO,
        "has_observation": DEFAULT_HAS_OBSERVATION,
        "sleep_interval": DEFAULT_SLEEP_INTERVAL,
        "car_info": "当前位置上海浦东前滩，车内温度24摄氏度，当前P档静止。",
    }

    case_profile_direct = TestCase(
        id="old_complex_1",
        case_id="old_complex_profile_memory_direct",
        context_config={
            **base_context,
            "profile_type": DEFAULT_PROFILE_TYPE,
            # 这里示例用字符串，匹配你希望的 case 输入方式。
            "user_profile": "王先生，偏好周杰伦，下班回家前喜欢先听歌。", 
        },
        max_round=6,
        user_query_lists=[
            [Message(role="user", content="我想听点歌，结合我的偏好推荐一下。")],
        ],
        expected_script="""
用户：我想听点歌，结合我的偏好推荐一下。
助手：结合用户画像里的音乐偏好给出推荐，并做简洁解释。
        """,
        nl_assertion=[
            "助手应基于用户问题给出明确可执行的回复，且语义连贯，不应答非所问。"
        ],
        case_description="验证 context_config 中直接注入的画像记忆是否能参与回复。",
        tags=["复杂推理", "画像记忆", "自动化测试"],
    )

    case_memory_produce_consume = TestCase(
        id="old_complex_2",
        case_id="old_complex_history_memory_produce_consume",
        context_config={
            **base_context,
        },
        max_round=8,
        user_query_lists=[
            [Message(role="user", content="记一下，我家在浦东前滩。")],
            [Message(role="user", content="我搬家了，现在住在嘉定新城。")],
            [Message(role="user", content="回家。")],
        ],
        expected_script="""
用户：记一下，我家在浦东前滩。
助手：确认记录。
（下一次独立会话）
用户：我搬家了，现在住在嘉定新城。
助手：确认更新。
（下一次独立会话）
用户：回家。
助手：应体现使用最新住址信息来理解“回家”的目标。
        """,
        nl_assertion=[
            "在最后一轮“回家”场景中，助手应体现出对前序多次对话所形成记忆的消费能力，并优先采用最新信息。"
        ],
        case_description="同一case内多次会话：先通过历史上传生产记忆，再在后续会话消费并验证。",
        tags=["复杂推理", "记忆生产", "记忆消费", "自动化测试"],
    )
    return [case_profile_direct, case_memory_produce_consume]


def parse_args() -> argparse.Namespace:
    """
    命令行参数入口：
    - --agent-url: 待测服务地址
    - --tenant-id: mock 画像写入需要的租户标识
    """
    parser = argparse.ArgumentParser(
        description="运行旧复杂推理服务自动化测试（mock配置已内置默认值）"
    )
    parser.add_argument(
        "--agent-url",
        default=DEFAULT_AGENT_URL,
        help="待测复杂推理服务URL，例如 https://xxx/api/complex_reasoning",
    )
    parser.add_argument(
        "--tenant-id",
        default=os.getenv("COMPLEX_REASONING_TENANT_ID", ""),
        help="可选，mock画像写入需要的 tenant_id；也可通过环境变量 COMPLEX_REASONING_TENANT_ID 提供",
    )
    return parser.parse_args()


async def main(agent_url: str, tenant_id: str = "") -> None:
    """
    主流程：
    1) 初始化 bot 运行配置
    2) 加载 Mongo 数据集或本地 mock case
    3) 执行自动评测并写报告
    """
    use_local_mock_cases = _parse_bool_env(
        "AUTO_TEST_USE_LOCAL_MOCK_CASES", USE_LOCAL_MOCK_CASES
    )
    enable_remote_mock_submit = _parse_bool_env(
        "AUTO_TEST_ENABLE_REMOTE_MOCK_SUBMIT", ENABLE_REMOTE_MOCK_SUBMIT
    )
    dataset_names = _parse_dataset_names_from_env(DATASET_NAMES)
    judge_log_path, report_md_path = _build_output_paths(
        dataset_names, JUDGE_LOG_PATH, REPORT_MD_PATH
    )
    concurrency_mode = _parse_bool_env("AUTO_TEST_CONCURRENCY_MODE", False)
    concurrency_num = int(os.getenv("AUTO_TEST_CONCURRENCY_NUM", "10"))
    case_limit = int(os.getenv("AUTO_TEST_CASE_LIMIT", "0"))

    OldComplexReasoningServiceBot.set_up_bot_to_test(
        agent_url=agent_url,
        moniqi_mock_url_template=DEFAULT_MONIQI_MOCK_URL,
        mem_profile_url=DEFAULT_MEM_PROFILE_MOCK_URL,
        mem_event_url=DEFAULT_MEM_EVENT_MOCK_URL,
        tenant_id=tenant_id,
        is_submit_mock_info=enable_remote_mock_submit,
        profile_type=DEFAULT_PROFILE_TYPE,
        event_type=DEFAULT_EVENT_TYPE,
        has_observation=DEFAULT_HAS_OBSERVATION,
        sleep_interval=DEFAULT_SLEEP_INTERVAL,
        mem_day_summary_url=DEFAULT_MEM_DAY_SUMMARY_URL,
        mem_week_summary_url=DEFAULT_MEM_WEEK_SUMMARY_URL,
        mem_summary_query_url=DEFAULT_MEM_SUMMARY_QUERY_URL,
    )

    if use_local_mock_cases:
        all_cases = build_cases()
        log_dataset_names = ["old_complex_reasoning_local_cases"]
    else:
        all_cases = await get_dataset_list(dataset_names)
        log_dataset_names = dataset_names
    if case_limit > 0:
        all_cases = all_cases[:case_limit]
    patch_cases_default_context(all_cases)
    strip_volc_memory_fields(all_cases)
    run_id = isolate_case_user_ids_per_run(all_cases)

    auto_test = AutoTestAndRLDataGenerator(
        bot_to_test=OldComplexReasoningServiceBot,
        memory_test_cases=all_cases,
        show_progress=False,
        log_dialogue=True,
        verbose=True,
    )

    run_result: RunAllCasesResult | None = None
    async for item in auto_test.arun_full_auto_judge_test(
        concurrency_mode=concurrency_mode,
        concurrency_num=concurrency_num,
        pause_mode=False,
        memory_reset_mode=False,
        upload_history_to_volc_memory=False,
    ):
        if isinstance(item, RunCaseResult):
            print(
                f"[STREAM] case已完成: case_id={item.case_id}, "
                f"id={item.id}, is_passed={item.is_passed}"
            )
        elif isinstance(item, RunAllCasesResult):
            run_result = item
    assert run_result is not None, "未收到最终 RunAllCasesResult"
    auto_test.write_test_task_judge_log(
        dataset_names=log_dataset_names,
        total_case_num=run_result.total_case_num,
        passed_case_num=run_result.passed_case_num,
        pass_rate=run_result.pass_rate,
        execution_success_num=run_result.execution_success_num,
        execution_success_rate=run_result.execution_success_rate,
        tags_correct_number_and_rate=run_result.tags_correct_number_and_rate,
        judge_result=run_result.result,
        log_file_path=judge_log_path,
    )
    auto_test.write_test_task_report(
        dataset_names=log_dataset_names,
        result_str=run_result.result,
        total_case_num=run_result.total_case_num,
        passed_case_num=run_result.passed_case_num,
        pass_rate=run_result.pass_rate,
        execution_success_num=run_result.execution_success_num,
        execution_success_rate=run_result.execution_success_rate,
        tags_correct_number_and_rate=run_result.tags_correct_number_and_rate,
        report_file_path=report_md_path,
    )

    print(f"数据集: {log_dataset_names}")
    print(f"本地 mock: {use_local_mock_cases}")
    print(f"总用例数: {run_result.total_case_num}")
    print(f"通过用例数: {run_result.passed_case_num}")
    print(f"通过率: {run_result.pass_rate:.2%}")
    print(f"case_limit: {case_limit}")
    print(f"run_id: {run_id}")
    print(f"judge_log: {judge_log_path}")
    print(f"report_md: {report_md_path}")
    if run_result.passed_case_num != run_result.total_case_num:
        raise AssertionError(
            f"存在未通过用例: {run_result.passed_case_num}/{run_result.total_case_num}"
        )
    print("全部用例通过。")


if __name__ == "__main__":
    cli_args = parse_args()
    asyncio.run(main(agent_url=cli_args.agent_url, tenant_id=cli_args.tenant_id))