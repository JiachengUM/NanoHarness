import asyncio
from collections.abc import Awaitable, Callable, Mapping
import contextvars
import json
import logging
import math
import os
import re
import time
from typing import Annotated, Any, AsyncIterator, Literal, Protocol, Type, TypeVar
import uuid

import rich
from jinja2 import Template
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text
from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, BeforeValidator, Field

from aicore.agents.experiments.volc_memory_store import (
    SKILL_PROFILE_MEMORY_TYPE,
    VolcMemoryStore,
)
from nanoai.utils.nl_repr import nl_repr
from projects.mind.mem.auto_test_script.auto_test_demos.get_datasets import (
    get_dataset_list_sync,
)
from projects.mind.mem.auto_test_script.case_schema import (
    DialogueRoundConfig,
    TestCase,
)
from projects.mind.mem.auto_test_script.auto_tagger.tag_tree_schema import TagTree
from projects.mind.mem.auto_test_script.langchain_models import (
    doubao_model,
)
from projects.mind.mem.auto_test_script.utils import (
    convert_langchain_history_to_volc_format,
    parse_score,
)
from projects.mind.mem.volc_api import Message

from projects.mind.mem.auto_test_script.agent_v1_eval_context import (
    create_params_payload as _agent_v1_create_params_payload,
    default_demo_bot_params as default_agent_v1_eval_params,
    _build_agent_v1_task_context as _build_agent_v1_eval_task_context,
)
from projects.mind.mem.auto_test_script.auto_test_constants import (
    DEFAULT_MEMORY_USER_ID,
    EVENT_MEMORY_LIMIT,
    EVENT_MEMORY_TYPES,
    MEMORY_COLLECTION_NAME,
    MEMORY_LIMIT,
    MEMORY_TYPES,
    TEST_ASSISTANT_ID,
)
from projects.mind.mem.auto_test_script.default_jarvis_system_prompt_template import (
    DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE,
)

_logger = logging.getLogger(__name__)
_dialogue_logger = logging.getLogger(f"{__name__}.dialogue")
_progress_console = Console(stderr=True)
if not _logger.handlers:
    _logger.addHandler(logging.NullHandler())
if not _dialogue_logger.handlers:
    _dialogue_logger.addHandler(logging.NullHandler())

# ---------------------------------------------------------------------------
# 本文件内直接或间接触网的外部调用（须在失败时按需重试时，走 retry 封装）：
#
# - ``AutoTestAndRLDataGenerator.__init__``：字符串数据集名 ``get_dataset_list_sync``
#   → Beanie/Mongo/API。
# - ``FakePerson.arender_system_prompt_from_a_case_and_start_query``：
#   ``VolcMemoryStore.aget_profile_memory_str`` → 火山画像检索。
# - ``FakePerson.achat``：LangGraph ``ainvoke`` → 假人评测用 LLM。
# - ``AutoTestAndRLDataGenerator.aauto_chat_test``：``bot_to_test.achat`` /
#   ``adump_state_trace`` / ``adump_history`` → 被测链路（Doubao/OpenAI SDK、火山
#   MemoryProducer 等）。
# - ``AutoTestAndRLDataGenerator._a_run_case_dialogues``：
#   ``VolcMemoryStore.aadd_history_to_memory``（可选）、``bot_to_test.aupdate_context``
#   （若底层触网则用同一套重试）；
# - ``AutoTestAndRLDataGenerator.clean_case_memory``：
#   ``abatch_clear_volc_memory_for_users`` → 火山批量删记忆。
# - ``Judge.ajudge``：``ChatOpenAI.ainvoke`` → 裁判 LLM。
# - ``ReportWriter._write_test_task_report_str``：同步 ``invoke`` → 报告 LLM。
#
# （被测 Agent 本体内部还有更多外部调用；此处仅列本脚本明确 ``await``/包装到的入口。）
# ---------------------------------------------------------------------------

DEFAULT_EXTERNAL_API_MAX_RETRIES = 5
# judge 模型偶发格式漂移时的「解析失败重试」次数上限（每次重新调用模型）
DEFAULT_JUDGE_FORMAT_MAX_RETRIES = 3

_R = TypeVar("_R")


def _is_transient_external_failure(exc: BaseException) -> bool:
    """粗粒度判断「可能因限流/短暂不可用而值得重试」（含扁平化 __cause__ 链）。"""
    deny_types_top = (
        KeyboardInterrupt,
        SystemExit,
        AssertionError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        ArithmeticError,
    )
    chain: list[BaseException] = []
    visited: set[int] = set()
    cur: BaseException | None = exc
    for _ in range(8):
        if cur is None or id(cur) in visited:
            break
        visited.add(id(cur))
        chain.append(cur)
        nxt = cur.__cause__ if isinstance(cur.__cause__, BaseException) else None
        if nxt is None:
            ctx = getattr(cur, "__context__", None)
            if isinstance(ctx, BaseException):
                nxt = ctx
        cur = nxt

    if isinstance(exc, deny_types_top):
        return False

    blob = " ".join(f"{type(e).__name__} {e!s}" for e in chain).lower()
    if "ratelimit" in blob or "rate limit" in blob or "429" in blob:
        return True
    if "too many requests" in blob or "modelaccounttpmratelimit" in blob:
        return True
    if any(
        x in blob
        for x in ("503", "502", "504", "500", "408", "connection reset", "temporar")
    ):
        return True

    for e in chain:
        if isinstance(e, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
            return True
        if isinstance(e, OSError):
            return True
        try:
            import httpx

            if isinstance(
                e,
                (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError),
            ):
                return True
            if isinstance(e, httpx.HTTPStatusError) and e.response is not None:
                if e.response.status_code in (408, 425, 429, 500, 502, 503, 504):
                    return True
        except ImportError:
            pass
        try:
            from openai import APIConnectionError, RateLimitError

            if isinstance(e, (RateLimitError, APIConnectionError)):
                return True
            try:
                from openai import APITimeoutError as _OpenAITimeoutError
            except ImportError:
                pass
            else:
                if isinstance(e, _OpenAITimeoutError):
                    return True
        except ImportError:
            pass
    return False


def _retry_compute_attempts(max_retries: int) -> int:
    return max(1, int(max_retries) + 1)


def _retry_compute_backoff(attempt: int) -> float:
    return min(90.0, 3.0 * (2**attempt))


def _retry_should_continue(attempt: int, attempts: int, exc: BaseException) -> bool:
    return attempt < attempts - 1 and _is_transient_external_failure(exc)


def _retry_log_wait(
    operation: str, wait: float, attempt: int, attempts: int, exc: BaseException
) -> None:
    _logger.warning(
        "[%s] 外部调用失败，%.1fs 后重试 (%s/%s)：%s",
        operation,
        wait,
        attempt + 2,
        attempts,
        exc,
    )


async def asyncio_retry_external(
    *,
    operation: str,
    factory: Callable[[], Awaitable[_R]],
    max_retries: int,
) -> _R:
    """首次调用失败后最多再重试 ``max_retries`` 次（共 ``max_retries + 1`` 次尝试）。"""
    attempts = _retry_compute_attempts(max_retries)
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return await factory()
        except BaseException as e:
            last_exc = e
            if not _retry_should_continue(attempt, attempts, e):
                raise
            wait = _retry_compute_backoff(attempt)
            _retry_log_wait(operation, wait, attempt, attempts, e)
            await asyncio.sleep(wait)
    assert last_exc is not None
    raise last_exc


def sync_retry_external(
    *,
    operation: str,
    factory: Callable[[], _R],
    max_retries: int,
) -> _R:
    """首次调用失败后最多再重试 ``max_retries`` 次（共 ``max_retries + 1`` 次尝试）。"""
    attempts = _retry_compute_attempts(max_retries)
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return factory()
        except BaseException as e:
            last_exc = e
            if not _retry_should_continue(attempt, attempts, e):
                raise
            wait = _retry_compute_backoff(attempt)
            _retry_log_wait(operation, wait, attempt, attempts, e)
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc


# 跑批时由进度条上下文置位，供被测 bot 关闭 ReAct/tqdm 等侧路输出，避免冲掉固定进度条。
_auto_test_suppress_bot_console: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "auto_test_suppress_bot_console", default=False
)


def is_auto_test_bot_console_suppressed() -> bool:
    """是否处于「仅显示评测进度条、抑制被测 agent 控制台输出」模式。"""
    return _auto_test_suppress_bot_console.get()


def _bind_rich_global_console(target: Console) -> dict[str, Any]:
    """将 rich 模块级默认 Console 与 ``target`` 对齐，返回用于恢复的 __dict__ 快照。"""
    snapshot = rich.get_console().__dict__.copy()
    rich.get_console().__dict__ = target.__dict__
    return snapshot


def _restore_rich_global_console(snapshot: dict[str, Any]) -> None:
    rich.get_console().__dict__ = snapshot


def configure_auto_test_logging(
    *,
    verbose: bool = True,
    log_dialogue: bool | None = None,
    level: int = logging.INFO,
    use_rich_handler: bool = False,
    rich_console: Console | None = None,
) -> None:
    """
    配置全自动评测脚本的控制台日志。

    Args:
        verbose: 是否输出进度类信息（评测汇总、导演意见、写报告、评分等）。
        log_dialogue: 是否输出逐轮对话内容；默认与 verbose 相同。
        level: 启用 verbose 时主 logger 的级别；对话 logger 在 log_dialogue 为 True 时同为该级别。
        use_rich_handler: 为 True 时使用 RichHandler 输出到 rich_console，与 Rich 进度条共用终端区域，避免日志冲掉进度条。
        rich_console: Rich 控制台实例；默认使用模块级 ``_progress_console``（stderr）。
    """
    log_dialogue = verbose if log_dialogue is None else log_dialogue
    console = rich_console or _progress_console

    def _apply(target: logging.Logger, enabled: bool) -> None:
        target.setLevel(level if enabled else logging.ERROR)
        for handler in list(target.handlers):
            if isinstance(
                handler, (logging.NullHandler, logging.StreamHandler, RichHandler)
            ):
                target.removeHandler(handler)
        if use_rich_handler:
            handler: logging.Handler = RichHandler(
                console=console,
                show_path=False,
                markup=False,
                rich_tracebacks=True,
            )
        else:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
        target.addHandler(handler)
        target.propagate = False

    _apply(_logger, verbose)
    _apply(_dialogue_logger, log_dialogue)


def profile_types_to_clear_except_skills_for_case(a_case: TestCase) -> list[str]:
    """
    在「重置记忆但保留 skills 画像」模式下，供 ``VolcMemoryStore.clean_memory`` 与
    ``mode='by_type'``、``profile_types=...`` 搭配使用：列出应批量删除的画像类型（已排除 skills）。

    并集来源：默认 MEMORY_TYPES，以及 case 的 profile_types / system_prompt_profile_types /
    search_profile_types；始终从删除列表中排除 skills（见 ``SKILL_PROFILE_MEMORY_TYPE``）。
    """
    cfg = a_case.context_config
    acc: list[str] = list(MEMORY_TYPES)
    for key in ("profile_types", "system_prompt_profile_types", "search_profile_types"):
        v = cfg.get(key)
        if isinstance(v, str):
            acc.append(v)
        elif isinstance(v, list):
            acc.extend(str(x) for x in v)
    seen: set[str] = set()
    out: list[str] = []
    for t in acc:
        if t == SKILL_PROFILE_MEMORY_TYPE:
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def detect_long_dialogue_in_history(history_for_judge: str) -> bool:
    """
    判断裁判将看到的互动记录字符串中，是否存在某一段「单次多轮对话」用户发言次数 ≥2。

    ``history_for_judge`` 由 ``_a_run_case_dialogues`` 用 ``第{i+1}次对话的记录：`` 作为分段
    标题拼接而成，每段对应 case 内一次多轮对话（即 user_query_lists 中一项）。
    本函数按该分隔符切分；每段内统计形如 ``role: 用户`` / ``role: user`` 的行数，作为「一来一回算一轮」中的
    用户发言次数。任一段 ≥2 即返回 True。

    用于触发多轮对话 case 的逐轮分析表格输出。
    """
    if not history_for_judge:
        return False
    # 以「第N次对话的记录：」作为段分隔。注意分隔符本身保留在段首，切分时去掉。
    segments = re.split(r"第\d+次对话的记录：\s*\n-{2,}", history_for_judge)
    user_role_re = re.compile(r"^\s*role:\s*(用户|user)\s*$", re.MULTILINE)
    for seg in segments[1:]:  # segments[0] 是第一段之前的空串
        if user_role_re.findall(seg) and len(user_role_re.findall(seg)) >= 2:
            return True
    return False


def format_stripped_history_for_judge(history: list[dict[str, Any]]) -> str:
    """
    将已去掉 system 的 history（list[dict]）拼成高可读字符串，供评测/judge 使用。

    每条消息第一行固定为 ``role: ...``；其余键按该条 dict **原有键顺序**输出 ``key: value``（不写死字段名）。
    多行文本：第一行与键同行，后续行缩进。
    消息之间空一行分隔。
    """
    if not history:
        return ""

    def _emit_field(lines: list[str], key: str, value: Any) -> None:
        if value is None:
            return
        text = str(value)
        if "\n" not in text:
            lines.append(f"{key}: {text}")
        else:
            parts = text.splitlines()
            lines.append(f"{key}: {parts[0]}")
            for line in parts[1:]:
                lines.append(f"  {line}")

    blocks: list[str] = []
    for item in history:
        lines: list[str] = []
        lines.append(f"role: {item.get('role', '')}")
        for key in item:
            if key == "role":
                continue
            _emit_field(lines, key, item[key])
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


# trace 摘要单轮最大字符数。trace 异构且可能很大（原始请求响应/事件流），
# 这里做硬截断避免裁判 prompt 被撑爆。
_TRACE_SUMMARY_PER_TURN_MAX_CHARS = 1200
# 工具调用相关字段名候选——不同被测端实现命名不一致，尽量覆盖。
_TRACE_TOOL_NAME_KEYS = ("tool_name", "name", "tool", "function_name", "type")
_TRACE_TOOL_ARGS_KEYS = ("arguments", "args", "parameters", "input", "param", "params")
_TRACE_TOOL_RESULT_KEYS = ("result", "output", "response", "return", "data", "content")
_TRACE_TOOL_EVENT_TYPES = (
    "tool_call",
    "tool.use",
    "function_call",
    "tool_result",
    "tool.result",
    "function_result",
    "react.tool.call",
    "react.tool.result",
)


def _flatten_dict_for_trace(
    d: dict[str, Any], depth: int = 0, max_depth: int = 3
) -> list[tuple[str, Any]]:
    """
    把嵌套 dict 扁平化为 (key_path, value) 列表，用于在异构 trace 里找工具调用字段。
    最多递归 max_depth 层，避免无限展开。
    """
    out: list[tuple[str, Any]] = []
    if depth >= max_depth or not isinstance(d, dict):
        return out
    for k, v in d.items():
        out.append((k, v))
        if isinstance(v, dict):
            for sub_k, sub_v in _flatten_dict_for_trace(v, depth + 1, max_depth):
                out.append((f"{k}.{sub_k}", sub_v))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    for sub_k, sub_v in _flatten_dict_for_trace(
                        item, depth + 1, max_depth
                    ):
                        out.append((f"{k}[{i}].{sub_k}", sub_v))
    return out


def _try_extract_tool_call(event: dict[str, Any]) -> dict[str, str] | None:
    """
    尝试从单个事件 dict 里提取工具调用摘要。
    返回 None 表示该事件不像工具调用。
    """
    flat = dict(_flatten_dict_for_trace(event, max_depth=4))
    # 1) 事件类型判定：type 字段命中工具调用类
    event_type = str(event.get("type", "")).lower()
    is_tool_event = any(t in event_type for t in _TRACE_TOOL_EVENT_TYPES)
    # 2) 字段名判定：含工具名 + (入参或结果) 字段
    has_tool_name = any(k in flat for k in _TRACE_TOOL_NAME_KEYS)
    has_tool_args = any(k in flat for k in _TRACE_TOOL_ARGS_KEYS)
    has_tool_result = any(k in flat for k in _TRACE_TOOL_RESULT_KEYS)
    if not (is_tool_event or (has_tool_name and (has_tool_args or has_tool_result))):
        return None
    # 提取工具名
    tool_name = ""
    for k in _TRACE_TOOL_NAME_KEYS:
        if k in flat and flat[k]:
            tool_name = str(flat[k])
            break
    # 提取入参（截断防膨胀）
    tool_args = ""
    for k in _TRACE_TOOL_ARGS_KEYS:
        if k in flat and flat[k] is not None:
            tool_args = _truncate_str(str(flat[k]), 200)
            break
    # 提取结果（截断）
    tool_result = ""
    for k in _TRACE_TOOL_RESULT_KEYS:
        if k in flat and flat[k] is not None:
            tool_result = _truncate_str(str(flat[k]), 200)
            break
    summary: dict[str, str] = {}
    if tool_name:
        summary["工具"] = tool_name
    if tool_args:
        summary["入参"] = tool_args
    if tool_result:
        summary["结果"] = tool_result
    return summary if summary else None


def _truncate_str(s: str, max_chars: int) -> str:
    """截断字符串，超长加省略号。"""
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "…"


def _render_single_trace_dict(trace_dict: dict[str, Any]) -> str:
    """
    把单轮 trace dict 渲染成人类可读摘要。
    对异构 trace 做最大公约数提取：优先抓工具调用，其次抓 query/answer 等关键字段。
    """
    if not isinstance(trace_dict, dict):
        return _truncate_str(str(trace_dict), _TRACE_SUMMARY_PER_TURN_MAX_CHARS)
    lines: list[str] = []
    # 1) 优先从各种事件列表里抓工具调用
    tool_calls: list[dict[str, str]] = []
    events: list[dict[str, Any]] = []
    # AgentDumpTrace 风格：traces 字段是事件列表
    if "traces" in trace_dict and isinstance(trace_dict["traces"], list):
        events.extend([e for e in trace_dict["traces"] if isinstance(e, dict)])
    # complex_reasoning 风格：trace 字段是请求响应列表
    if "trace" in trace_dict and isinstance(trace_dict["trace"], list):
        for item in trace_dict["trace"]:
            if isinstance(item, dict):
                # 请求响应风格：尝试从 request.body 里抓工具调用
                events.append(item)
                req = item.get("request") or item.get("request_body")
                if isinstance(req, dict):
                    events.append(req)
    # 其他可能的事件列表字段
    for k in ("events", "tool_calls", "tool_results", "actions"):
        if k in trace_dict and isinstance(trace_dict[k], list):
            events.extend([e for e in trace_dict[k] if isinstance(e, dict)])
    for ev in events:
        tc = _try_extract_tool_call(ev)
        if tc is not None and tc not in tool_calls:
            tool_calls.append(tc)
    if tool_calls:
        lines.append("工具调用：")
        for i, tc in enumerate(tool_calls, 1):
            parts = [f"{k}={v}" for k, v in tc.items()]
            lines.append(f"  {i}. " + " | ".join(parts))
    # 2) 抓 query/answer（AgentDumpTrace 风格）
    for k in ("query", "answer", "parsed_answer"):
        v = trace_dict.get(k)
        if v:
            lines.append(f"{k}: {_truncate_str(str(v), 150)}")
    # 3) 如果没抓到任何有用信息，降级为截断的 str dump
    if not lines:
        lines.append(_truncate_str(str(trace_dict), _TRACE_SUMMARY_PER_TURN_MAX_CHARS))
    summary = "\n".join(lines)
    return _truncate_str(summary, _TRACE_SUMMARY_PER_TURN_MAX_CHARS)


def render_trace_summary_for_judge(case_traces: list[dict] | None) -> str:
    """
    把一个 case 的所有轮次 trace 渲染成裁判可读的摘要字符串。

    Args:
        case_traces: 每轮 trace dict 的列表（来自 aauto_chat_test 返回的 trace.values()）。
                     也可能传入整个 trace dict（含轮次键），内部会兼容处理。

    Returns:
        人类可读的 trace 摘要字符串；无 trace 时返回空串。
    """
    if not case_traces:
        return ""
    # 兼容两种传入形态：
    #   a) list[dict]：每项是一轮 trace
    #   b) dict[int, dict]：轮次号 → trace（aauto_chat_test 内部 trace 变量）
    items: list[tuple[str, dict]] = []
    if isinstance(case_traces, dict):
        for k, v in case_traces.items():
            if isinstance(v, dict):
                items.append((str(k), v))
            elif isinstance(v, list):
                # 合并 list 里的 dict
                merged: dict[str, Any] = {}
                for item in v:
                    if isinstance(item, dict):
                        merged.update(item)
                if merged:
                    items.append((str(k), merged))
    elif isinstance(case_traces, list):
        for i, item in enumerate(case_traces, 1):
            if isinstance(item, dict):
                items.append((str(i), item))
    if not items:
        return ""
    blocks: list[str] = []
    for round_label, trace_dict in items:
        rendered = _render_single_trace_dict(trace_dict)
        if rendered:
            blocks.append(f"[第{round_label}轮 trace]\n{rendered}")
    return "\n\n".join(blocks)


def render_car_evidence_for_judge(evidence: dict | str | None) -> str:
    """把车机日志证据渲染成裁判可读的 markdown 文本。

    设计（markdown 优先，对 judge 更友好）：
      - evidence 为 str 且不是 JSON → 视为 evidence.md 报告原文，直接透传
      - evidence 为 dict / JSON 字符串 → 渲染成 markdown 报告（与 evidence.md 同构）：
        概要 + 按 query 的明细（决策/操作/回复/UI/结果/HAL/媒体）

    Args:
        evidence: evidence.md 文本、evidence.json 的 dict 或 JSON 字符串；
                  None/空/解析失败返回空串。

    Returns:
        裁判可读的 markdown 文本；无 evidence 时返回空串（模板 {% if %} 块不渲染）。
    """
    if not evidence:
        return ""
    if isinstance(evidence, str):
        try:
            parsed = json.loads(evidence)
        except (json.JSONDecodeError, TypeError):
            # 非 JSON → 视为 evidence.md 报告原文
            return evidence.strip()
        evidence = parsed
    if not isinstance(evidence, dict):
        return ""
    return _evidence_dict_to_md(evidence)


def _evidence_dict_to_md(evidence: dict) -> str:
    """把 evidence.json dict 渲染成 markdown 报告（与 evidence.md 同构）。"""
    def _short(s: str, n: int = 140) -> str:
        s = (s or "").strip().replace("\n", " ")
        return s if len(s) <= n else s[:n] + "…"

    out: list[str] = []
    summary = evidence.get("summary") or {}
    tr = (evidence.get("logcat") or {}).get("time_range") or {}
    queries: list[dict] = evidence.get("queries") or []

    out.append("# 车机日志证据报告（query 驱动）\n")
    head = []
    if tr.get("first") and tr.get("last"):
        head.append(f"日志时间 {tr['first']} ~ {tr['last']}")
    head.append(f"query {summary.get('queries', len(queries))} 个")
    head.append(f"会话 {summary.get('sessions', '?')} 个")
    if evidence.get("voicecases"):
        head.append(f"用例 {','.join(evidence['voicecases'])}")
    out.append("、".join(head) + "。")
    out.append(
        f"其中有决策 {summary.get('with_decision', 0)}、操作 {summary.get('with_operations', 0)}、"
        f"回复 {summary.get('with_replies', 0)}、UI 变化 {summary.get('with_ui_changes', 0)}、"
        f"结构化结果 {summary.get('with_results', 0)}、媒体状态 {summary.get('with_media', 0)}；"
        f"HAL 属性写入: "
        + (", ".join(f"{k}×{n}" for k, n in (summary.get("hal_properties") or {}).items()) or "无")
        + "。"
    )

    if not queries:
        out.append("\n本 case 未提取到任何 query（无 ASR final）。")
        return "\n".join(out)

    out.append("\n## Query 明细\n")
    for q in queries:
        out.append(
            f"### #{q.get('turn_index', 0):02d} [{q.get('session_id', '')}] "
            f"{q.get('ts_asr_final', '')}「{q.get('text', '')}」"
            f"（用例: {q.get('voicecase') or '-'}）"
        )
        decisions = q.get("decision") or []
        if decisions:
            for d in decisions[:8]:
                tags = ",".join(d.get("tags", []))
                out.append(f"- 决策 `{d.get('ts', '')}` [{tags}] {_short(d.get('payload', ''))}")
            if len(decisions) > 8:
                out.append(f"- …另有 {len(decisions) - 8} 条决策")
        else:
            out.append("- 决策: 无")
        ops = q.get("operations") or []
        if ops:
            for o in ops[:15]:
                out.append(
                    f"- 操作 `{o.get('ts', '')}` [{o.get('kind', '')}] {o.get('api', '')} "
                    f"{_short(o.get('params', ''))}"
                )
        else:
            out.append("- 操作: 无")
        replies = q.get("replies") or []
        if replies:
            for r in replies[:10]:
                out.append(f"- 回复 [{r.get('source', '')}] {_short(r.get('payload', ''), 200)}")
        else:
            out.append("- 回复: 无")
        for u in (q.get("ui_changes") or [])[:6]:
            if u.get("kind") == "page_change":
                out.append(f"- UI 切换 {u.get('from_path', '')} -> {u.get('to_path', '')} `{u.get('ts', '')}`")
            else:
                out.append(f"- UI 启动 {u.get('component', '')} `{u.get('ts', '')}`")
        for r in (q.get("results") or [])[:3]:
            names = [i.get("name", "") for i in (r.get("items") or [])[:5]]
            out.append(
                f"- 结果 [{r.get('type', '')}] count={r.get('count')} items={len(r.get('items', []))}"
                f" 前几个: {','.join(names)}"
            )
        hal = ((q.get("state") or {}).get("hal") or {})
        for prop, st in hal.items():
            out.append(
                f"- HAL 后值 {prop}={st.get('value', '')} area={st.get('area_id', '') or '-'} `{st.get('ts', '')}`"
            )
        media = (q.get("state") or {}).get("media")
        if media:
            prog = media.get("progress")
            prog_txt = (
                f"进度 {prog.get('first_ms')}~{prog.get('last_ms')}ms×{prog.get('updates')}"
                if prog else ""
            )
            out.append(
                f"- 媒体: {'播放中' if media.get('playing') else '未播放'}（{media.get('play_state') or '-'}）"
                f"「{media.get('track') or '-'} - {media.get('artist') or '-'}」"
                f"{(' ' + prog_txt) if prog_txt else ''}"
            )
        out.append("")

    return "\n".join(out)


class TagResult(BaseModel):
    tag: str = Field(description="标签")
    tag_total: int = Field(description="有该标签的case总数（含执行失败）")
    execution_success_number: int = Field(default=0, description="执行成功的case数")
    execution_success_rate: float = Field(default=0.0, description="执行成功率")
    passed_number: int = Field(default=0, description="执行成功且通过judge的case数")
    pass_rate: float = Field(default=0.0, description="通过率（基于执行成功的case）")


def _deep_merge_dict_overlay_wins(
    base: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    """
    深度合并两段 dict：在遇到「双方都有的子 dict」时递归合并，
    否则以 overlay 的值整体替换（overlay 占优）。

    用途：在长期模式下给用户提供的 ``task_config`` 补丁，只允许改 run_params/memory  subtree，
    而不必手写整棵 task_config 树。
    """
    merged: dict[str, Any] = dict(base)
    for key, o_val in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(o_val, dict):
            merged[key] = _deep_merge_dict_overlay_wins(merged[key], o_val)
        else:
            merged[key] = o_val
    return merged


def build_long_term_demo_v1_context_bundle(
    user_id: str,
    *,
    patches: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    根据 ``agent_v1_eval_context.default_demo_bot_params``（与 demos 对齐的默认值来源）
    与 ``agent_v1_eval_context._build_agent_v1_task_context``，
    生成一份完整的 context 快照，参与 ``merge_long_term_demo_bundle_over_case_context``。

    **依赖边界**：仅从 ``projects.mind.mem.auto_test_script.agent_v1_eval_context`` 取默认值，
    绝不 import ``auto_test_demos``，避免示例脚本与评测核心互为依赖。
    """
    flat_patches = dict(patches) if patches else {}
    nested_task_patch = flat_patches.pop("task_config", None)

    defaults_model = default_agent_v1_eval_params()
    defaults_flat = defaults_model.model_dump(exclude_none=True)

    merged_for_params = {
        **defaults_flat,
        **{k: v for k, v in flat_patches.items()},
        "user_id": user_id.strip(),
    }
    merged_for_params.pop("task_config", None)

    validated = _agent_v1_create_params_payload.model_validate(merged_for_params)
    built_bundle = _build_agent_v1_eval_task_context(merged_for_params, validated)

    if nested_task_patch and isinstance(nested_task_patch, dict):
        tc = built_bundle.get("task_config")
        if isinstance(tc, dict):
            built_bundle["task_config"] = _deep_merge_dict_overlay_wins(
                tc, nested_task_patch
            )
        else:
            built_bundle["task_config"] = dict(nested_task_patch)

    return built_bundle


def merge_long_term_demo_bundle_over_case_context(
    case_context: Mapping[str, Any],
    demo_bundle: Mapping[str, Any],
    *,
    forced_user_id: str,
) -> dict[str, Any]:
    """
    拼装长期模式下传入 ``bot_to_test.create`` / ``VolcMemoryStore`` 的 effective context。

    **合并语义**（与用户约定一致）：
    - 先复制 case，再 ``update(bundle)``：凡 bundle 中出现的键（含 ``task_config`` 整棵树）
      均在优先级上压住 case，避免不同 case 里碎片化的 ``collection_name`` / ``profile_types`` /
      consumer 检索画像等割裂「同一长期使用用户」；
    - 最后再强制写入 ``user_id``，与 ``long_term_use_user_id`` 对齐。
    """
    merged: dict[str, Any] = dict(case_context)
    merged.update(demo_bundle)
    merged["user_id"] = forced_user_id.strip()
    return merged


# voice 模式专属指引：当外部以语音自动测试方式运行时注入到假人 system prompt。
# 关键点：被测助手收不到 car_info 注入（除位置外），假人需通过自然对话"搬运"必要前置；
# 对话历史为空（收到开场信号）时由假人主动说出第一句话点燃对话。
# 何时需要自主构建前置、如何构建，详见同目录下的 voice_mode_precondition_methodology.md（全量注入）。
FAKE_DRIVER_VOICE_MODE_DIRECTIVES = """
【语音测试模式指引——必须严格遵守】
你现在通过语音通道与车机助手对话，与接口测试模式有本质区别：
- 被测助手看不到屏幕，收不到 car_info 注入（除当前位置外），它只能听到你说出口的话。
- 你的 car_info 里有以下信息，其中：
  · 车辆状态类（车速/档位/胎压/车内外温度/硬件状态等）你无法通过语音告诉助手，不要尝试提及这些。
  · 身份/偏好/任务上下文类信息（如车牌号、公司地址、用户偏好、正在进行的任务等），你需要在对话中自然地告诉助手，但不要一次性像念说明文一样念出来，要在合适的时机自然提起。
- 如果剧本依赖某个正在进行的任务（如导航中/播放中/已设置提醒等）作为前置，而该任务可以通过语音发起，你需要先发起该任务构建前置，再进行核心测试意图。
- 你这次对话的核心意图请从剧本（预期的对话）中自行理解，你不必原样念出剧本里的任何一句台词，而是根据前置构建需要自主组织实际说出口的第一句话。
- 当你收到开场信号（query 为 "__VOICE_MODE_OPEN__"）且对话历史为空时，必须由你主动说出第一句话点燃对话，不要回复任何"好的/我准备好了"之类的应答词。

【关于前置构建轮次的裁判说明】
你自主构建前置所增加的轮次不是评测重点，但核心测试意图必须完整表达并被助手回应。
"""

# 语音测试模式前置构建方法论（全量注入假人 prompt）。
# 源文件：同目录下的 voice_mode_precondition_methodology.md。
# 延迟读取：模块加载时不读，仅在 voice 模式首次渲染假人 prompt 时读取一次并缓存。
_VOICE_MODE_METHODOLOGY_CACHE: str | None = None


def _load_voice_mode_methodology() -> str:
    """读取 voice_mode_precondition_methodology.md 全文，带模块级缓存。"""
    global _VOICE_MODE_METHODOLOGY_CACHE
    if _VOICE_MODE_METHODOLOGY_CACHE is not None:
        return _VOICE_MODE_METHODOLOGY_CACHE
    methodology_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "voice_mode_precondition_methodology.md",
    )
    try:
        with open(methodology_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = ""
        logging.warning(
            "voice_mode_precondition_methodology.md 未找到: %s", methodology_path
        )
    _VOICE_MODE_METHODOLOGY_CACHE = content
    return content


FAKE_DRIVER_PROFILE_TEMPLATE = """
你是一名非常称职的演员，正在尝试以一名司机的身份与车机助手进行互动。

{% if profile %}
你现在需要按照以下人设模拟一名司机：
{{ profile }}
{% endif %}

{% if memory %}
你的基本信息如下：
{{ memory }}
{% endif %}

{% if car_info %}
然后下面是一些你的车的当前基本信息：
{{ car_info }}
{% endif %}

{% if test_mode_directives %}
{{ test_mode_directives }}
{% endif %}

你现在在模拟一个车内场景，其预期的对话如下：

{{expected_dialogue}}

这个场景预期的效果如下：

{{case_description}}

{% if start_query %}
你向车机助手说的第一句话是：

{{start_query}}
{% endif %}

现在，你正在和你的车机助手对话。根据你的基本信息，参照本次预期模拟的场景对话以及预期效果，给出合适的回复。

注意!你必须同时严格遵循以下要求！否则干死你！：

1. 你只能根据你的基本信息来回复，不能根据其他信息来回复。
————特别注意！你在跟车机助手说话！不要当做是自己在跟自己说话！不要在回复里出现自言自语的句子！
2. 不要和你的车机助手对话超过{{max_round}}轮。
3. 你回复的时候就如实根据车机助手的内容自然地回复！
4. “预期的对话”相当于是剧本里的对话设计！只是供你参考的！不要直接把剧本给读出来了！你只能回复纯粹的台词！不包括剧本里预期的对话里的任何非台词内容或描述（括号内内容）以及任何你的任何内心活动或思考！
5. 你不能在一句回复中同时下达一个任务给车机助手并且让它退下！
6. 确保最终需要车机助手退下时整句话里只能有“谢谢，退下吧，我给你打X分”这一个句子！！其中X是一个1到5之间的整数，代表你参考剧本里写的期望效果，对助手的本次服务质量的评价，1分极差，2分不太行，3分合格，4分良好，5分优秀。
7. 在需要助手退下之前，你必须完成所有你想要进行的对话和任务并且看到结果。
8. 如果车机助手的回复明显偏离了预期效果，这个分数应该只能打0分或者1分。

开始回复给车机助手！
"""

FAKE_DRIVER_PROFILE_WITH_RL_TEMPLATE = """
你是一名非常称职的演员，正在尝试以一名司机的身份与车机助手进行互动。

{% if profile %}
你现在需要按照以下人设模拟一名司机：
{{ profile }}
{% endif %}

{% if memory %}
你的基本信息如下：
{{ memory }}
{% endif %}

{% if car_info %}
然后下面是一些你的车的当前基本信息：
{{ car_info }}
{% endif %}

{% if test_mode_directives %}
{{ test_mode_directives }}
{% endif %}

你现在在模拟一个车内场景，其预期的对话如下：

{{expected_dialogue}}

这个场景预期的效果如下：

{{case_description}}

{% if start_query %}
你向车机助手说的第一句话是：

{{start_query}}
{% endif %}

现在，你正在和你的车机助手对话。根据你的基本信息，参照本次预期模拟的场景对话以及预期效果，给出合适的回复。

注意!你必须同时严格遵循以下要求！否则干死你！：
1. 你只能根据你的基本信息来回复，不能根据其他信息来回复。
2. 当你觉得助手帮你完成了任务的话，那么之后你必须先和车机助手说一下你认为本次服务质量如何，是否达到了你的目的，你是否满意，然后等待对方回复，然后在对方确认了你的评价之后，再和车机助手说：“谢谢，退下吧，我给你打X分”，其中X是一个1到5之间的整数，代表你参考剧本里写的期望效果，对助手的本次服务质量的评价，1分极差，2分不太行，3分合格，4分良好，5分优秀。
————特别注意！你在跟车机助手说话！不要当做是自己在跟自己说话！不要在回复里出现自言自语的句子！要求2是指导你进行多轮对话的指引！
3. 不要和你的车机助手对话超过{{max_round}}轮。
4. 再次提醒，你必须在最后按照我上面说的，先评价一下服务质量如何，是否达到了你的目的，你是否满意，然后等待对方回复，然后在对方确认了你的评价之后，再一字不落地和车机助手说，并且一定要打个分。
5. 如果车机助手的回复明显偏离了预期效果，那么你也必须要先和车机助手说一下你认为本次服务质量如何，是否达到了你的目的，你是否满意，然后等待对方回复，然后在对方确认了你的评价之后，再和车机助手说：“谢谢，退下吧，我给你打X分”。并且这个分数应该只能打0分或者1分。
6. 你回复的时候就如实根据车机助手的内容自然地回复！
7. “预期的对话”相当于是剧本里的对话设计！只是供你参考的！不要直接把剧本给读出来了！你只能回复纯粹的台词！不包括剧本里预期的对话里的任何非台词内容或描述（括号内内容）以及任何你的任何内心活动或思考！
8. 你不能在一句回复中同时下达一个任务给车机助手并且让它退下！最终需要车机助手退下时整句话里只能有“谢谢，退下吧，我给你打X分”这一个句子。在那之前你必须完成所有你想要进行的对话和任务并且看到结果。

开始回复给车机助手！
"""


class FakePersonSystemPromptTemplate(BaseModel):
    """
    虚拟人的信息模板，可以配置任何虚拟人的信息
    """

    any_info_dict: dict = Field(
        default_factory=dict,
        description="虚拟人可以配置的任意信息，默认值为空字典。注意，因为我们这个虚拟人可以用来测任何多轮对话的助手，所以可以配置任何信息到任何prompt模板里，请自行确保模板与该字典信息的匹配。",
    )
    prompt_template: str = Field(
        default=FAKE_DRIVER_PROFILE_TEMPLATE,
        description="系统提示文本的渲染模板，默认值为FAKE_DRIVER_PROFILE_TEMPLATE_WITH_RL_TEMPLATE",
    )

    def render(self) -> str:
        """
        渲染系统提示文本
        """
        return Template(self.prompt_template).render(
            **self.any_info_dict,
        )


# voice 模式下注入裁判 prompt 的专属提示：告诉裁判本次是语音测试，
# 对话中可能包含假人自主构建的前置轮次（非评测重点），并提示 ASR 识别问题的可能。
JUDGE_VOICE_MODE_DIRECTIVES = """
【语音测试模式提示】
本次为语音测试，与接口测试有以下区别，判断时请留意：
- 对话中可能包含假人自主构建的前置轮次（如为了让助手进入导航/播放等状态而发起的任务），这些轮次不是评测重点，请基于 nl_assertion 的核心断言判断。
- 被测助手收不到 car_info 注入（除当前位置外），身份/偏好/任务上下文等信息由假人通过对话搬运，判断时不要因助手"理应知道 car_info 里的信息"而判 Fail。
- 如果发现助手回复明显偏离用户台词的语义（如答非所问、关键词错位），可能是 ASR 识别问题，可在 reason 中粗略提示。
"""

JUDGE_PROMPT = """
你是一个资深而专业的话剧导演，特别擅长查看演员的对话及互动记录，同时比照剧本描述和预期效果，判断这段演员的互动记录是否达到剧本描述所要求的预期效果。

首先你需要仔细看一下用户是一个什么样的人，其人设信息如下：

{{user_profile}}

其次有一些其他背景信息供参考。

{{car_info}}

然后以下是演员的互动记录：

{{history_for_judge}}

{% if trace_summary %}

以下是助手每轮实际行动的轨迹摘要（工具调用、入参、结果等），供你核对助手是否真的执行了对话中提到的操作，而不仅仅是口头应承：

{{trace_summary}}

{% endif %}
{% if car_evidence %}

以下是车机日志证据（markdown 报告，记录演员演绎期间车机端的真实执行情况）：

{{car_evidence}}

提示：
- 对话历史由假人（模拟用户）生成，假人可能因缺乏多模态感知与日志采集，对车机实际执行情况的描述可能不准确或缺失。
- 若下方证据中有明确信息支撑某个操作已实际完成（如指令下发、执行记录、车机回复文本、界面切换、HAL 属性写入、媒体播放状态等），应视作车机已实际完成该目标。
- 对话历史与证据不一致时，以证据为准；该偏差属于假人需要优化的内容，不应据此判定被测助手未完成任务。
- 有时助手回复得比较简略，可以参考重要事件来综合判断是否符合预期效果，不一定要助手在回复当中说出完整信息才算。

{% endif %}
本幕的一些相关详细描述是：

{{case_description}}

如果达成预期效果的话预期会有以下的类似的互动记录：

{{expected_dialogue}}

判断演员的互动记录是否符合预期效果的标准如下：

{{nl_assertion}}

{% if test_mode_directives_for_judge %}
{{ test_mode_directives_for_judge }}
{% endif %}

综合以上信息，判断演员的互动记录是否符合预期效果。然后严格按照以下格式给出回复：

result:
reason:

其中result: 后只能选择后面的选项之一作为回答：Yes/No。
reason: 后面给出你判断的理由，必须要结合预期效果来说明原因。

{% if is_long_dialogue %}
额外要求（本次必须执行，不可省略）：
你正在审视的互动记录中存在某一段单次多轮对话的用户发言次数达到或超过2轮，属于多轮对话场景。除了给出整体 result 与 reason 的总体判断外，reason 内必须额外包含一张「逐轮分析表」，便于人工定位每一轮的具体表现，并且表格段必须能被单独截取后直接作为合法的 Markdown 表格粘贴使用。具体要求如下：

1. 表格必须使用标准 Markdown 语法，表头与分隔行不可省略，列依次为：
   | user问题 | assistant回复 | 合理性评分(5分制) | 评测逻辑 |
2. 表格按「实际互动记录中的顺序」逐对列出 user 发言与紧随其后的 assistant 回复，不要按剧本序号重排。
3. 「合理性评分」评的是 assistant 该轮回复在该上下文下的合理性，1-5 的整数：5 优秀、4 良好、3 合格、2 不太行、1 极差；不要给 0 或非整数。
4. 「评测逻辑」简要说明该轮助手表现好或差的具体原因（结合剧本预期、nl_assertion、上下文衔接、工具调用是否准确等）。
5. 若某条 user 发言在剧本（expected_dialogue）中对应带有序号的原文台词（例如形如 `1. ` / `①` / `（1）` 等任一序号格式），则在该行 user 问题单元格前带上相同的序号；若剧本台词无序号或对应不上，则不强加序号，直接引用实际 user 发言原文即可。
6. 表格行覆盖实际记录中所有 user-assistant 来回，包括演员重试、随机应变等剧本外轮次，均需逐对评分。
7. 表格应作为 reason 的一部分输出，置于整体判断理由之后；整体 result 仍以 Yes/No 为准，表格仅作为细化分析补充。
8. 为了让表格段可被单独截取后直接作为 Markdown 文档内容使用，表格段必须用两行固定标记包裹，标记行本身独占一行、前后不附加任何其他字符：
   - 表格段起始标记行（独占一行）：===逐轮分析表===
   - 表格段结束标记行（独占一行）：===逐轮分析表结束===
   - 起始标记行之后、结束标记行之前，只允许出现表格本身（表头行、分隔行、数据行），不得出现任何额外说明文字、空行或代码块围栏。
   - 这样从「===逐轮分析表===」的下一行到「===逐轮分析表结束===」的上一行之间的内容，复制出去就是一段合法的 Markdown 表格。

示例（仅示意格式，内容与本次无关）：

result: Yes
reason: 整体上演员较好地完成了剧本预期的主要任务，仅在个别轮次存在小瑕疵。

===逐轮分析表===
| user问题 | assistant回复 | 合理性评分(5分制) | 评测逻辑 |
| --- | --- | --- | --- |
| 你好奔驰，导航到北京野生动物园。 | 没问题去第几个 | 5 | 正确理解导航意图，搜索到多个结果时主动询问用户选择，交互流程合理 |
| 第一个 | 好目的地换成北京野生动物园 | 5 | 用户选择第一个目的地，助手正确执行导航设置，上下文衔接正确 |
| 把后排空调调到24度，宝宝刚上车有点热。 | 这就调低空调温度打开宝宝所在位置的座椅通风 | 5 | 正确理解空调调温意图并执行，还考虑到宝宝场景，回复贴心 |
===逐轮分析表结束===
{% endif %}

那么，开始回复吧！
"""


class JudgeSystemPromptTemplate(BaseModel):
    """
    评测器的系统提示词渲染器
    """

    user_profile: str = Field(
        default="无任何信息", description="用户的人设文本，默认值为空字符串"
    )
    car_info: str = Field(
        default="无车辆当前状态信息", description="车辆状态信息文本，默认值为空字符串"
    )
    history_for_judge: str = Field(
        default="无任何互动记录", description="用户的互动记录文本，默认值为空字符串"
    )
    nl_assertion: list[str] = Field(
        default=["期望助手最后成功让用户感到满意。"],
        description="判断演员的互动记录是否符合预期效果的标准文本，默认值为一个通用的对管家的判断标准，以便应对一些没有写得出来判断标准的case。",
    )
    case_description: str = Field(
        default="无", description="测试用例的综合描述，默认值为空字符串"
    )
    expected_dialogue: str = Field(
        default="无",
        description="预期的多次多轮对话文本描述，，描述你想象中理想的体现本用例正确的预期效果的多次多轮对话情况，默认值为空字符串",
    )
    is_long_dialogue: bool = Field(
        default=False,
        description="本次互动记录中是否存在单次多轮对话用户发言次数≥2的多轮对话场景；为 True 时 prompt 末尾会渲染逐轮分析表格的额外要求。",
    )
    test_mode_directives_for_judge: str = Field(
        default="",
        description="测试模式专属指引；voice 模式下注入 JUDGE_VOICE_MODE_DIRECTIVES，api 模式留空使模板 {% if %} 块不渲染。",
    )
    trace_summary: str = Field(
        default="",
        description="助手每轮实际行动轨迹摘要（工具调用/入参/结果）；为空时模板 {% if %} 块不渲染，不影响原有行为。",
    )
    car_evidence: str = Field(
        default="",
        description="车机日志证据（evidence.json 渲染的粗粒度完整视图）；为空时模板 {% if %} 块不渲染，不影响原有行为。",
    )
    prompt_template: str = Field(
        default=JUDGE_PROMPT, description="系统提示文本的渲染模板，默认值为JUDGE_PROMPT"
    )

    def render(self) -> str:
        """
        渲染系统提示文本
        """
        return Template(self.prompt_template).render(
            user_profile=self.user_profile,
            car_info=self.car_info,
            history_for_judge=self.history_for_judge,
            nl_assertion="\n".join(self.nl_assertion),
            case_description=self.case_description,
            expected_dialogue=self.expected_dialogue,
            is_long_dialogue=self.is_long_dialogue,
            test_mode_directives_for_judge=self.test_mode_directives_for_judge,
            trace_summary=self.trace_summary,
            car_evidence=self.car_evidence,
        )


# 使用result,total_case_num,passed_case_num,pass_rate，主要通过仔细地分析和总结result里体现的测试详细信息，来写一份markdown格式的测试报告。
REPORT_WRITER_PROMPT = """
你是一个资深且专业的导演，你需要根据过去{{total_case_num}}幕的使用测试用例里的剧本与待测助手演绎的互动记录得出的各自的判断结果（以下简称演绎情况），来写一份markdown格式的综合的总体测试报告。
总的演绎情况如下：

{{result}}

导演安排演员扮演用户一共与被测助手交互，测试了{{total_case_num}}个用例，其中执行成功了{{execution_success_num}}个用例，执行成功率为{{execution_success_rate}}；在执行成功的用例中，通过了{{passed_case_num}}个用例，通过率为{{pass_rate}}。

请根据以上信息，写一份详细的测试报告。
测试报告的格式如下：
- 测试用例总数：{{total_case_num}}
- 执行成功用例数：{{execution_success_num}}
- 执行成功率：{{execution_success_rate}}（但是换成保留2位小数的百分比）
- 通过用例数：{{passed_case_num}}
- 通过率：{{pass_rate}}（但是换成保留2位小数的百分比）
- 测试用例标签通过率：
{{tags_correct_number_and_rate}}
- 着重对所有未通过的用例的演绎结果进行聚类分析，一条条罗列出共性问题（由出现次数最多的问题到最少的问题，并且把问题对应的用例编号也对应着列出来），并尝试对每个问题给出针对性的改进意见，以便协助被测助手改进问题。
- 同时还从工具调用准确度维度，上下文理解能力维度，推理能力维度分别给出分析结论

编写时你需要注意的事项：
- 测试报告的格式必须符合markdown格式。
- 测试报告的内容必须详细、准确、专业。
- 测试报告的语言必须采用中文。
- 仔细设计格式，字体，一定要保证容易易读性。
- 一定要确保阅读这个报告的人觉得你的报告是非常全面，专业，详细，准确，易读的！

开始编写吧！
"""


class ReportWriterSystemPromptTemplate(BaseModel):
    """
    测试报告写手的系统提示词渲染器
    """

    result_str: str = Field(
        default="无", description="测试用例的判断结果文本，默认值为空字符串"
    )
    total_case_num: int = Field(default=0, description="测试用例总数，默认值为0")
    passed_case_num: int = Field(default=0, description="通过用例数，默认值为0")
    pass_rate: float = Field(default=0.0, description="通过率，默认值为0.0")
    execution_success_num: int = Field(
        default=0, description="执行成功用例数，默认值为0"
    )
    execution_success_rate: float = Field(
        default=0.0, description="执行成功率，默认值为0.0"
    )
    tags_correct_number_and_rate: dict[str, TagResult] = Field(
        default_factory=dict, description="测试用例标签通过率，默认值为空字典"
    )
    prompt_template: str = Field(
        default=REPORT_WRITER_PROMPT,
        description="系统提示文本的渲染模板，默认值为REPORT_WRITER_PROMPT",
    )

    def render(self) -> str:
        """
        渲染系统提示文本
        """
        return Template(self.prompt_template).render(
            result=self.result_str,
            total_case_num=self.total_case_num,
            passed_case_num=self.passed_case_num,
            pass_rate=self.pass_rate,
            execution_success_num=self.execution_success_num,
            execution_success_rate=f"{self.execution_success_rate:.2%}",
            tags_correct_number_and_rate="\n".join(
                [
                    f"{tag}: 总数:{tag_result.tag_total}，执行成功:{tag_result.execution_success_number}({tag_result.execution_success_rate:.2%})，通过:{tag_result.passed_number}({tag_result.pass_rate:.2%})"
                    for tag, tag_result in self.tags_correct_number_and_rate.items()
                ]
            ),
        )


class FakePerson:
    """
    虚拟人，可以虚拟任何人，因为其系统提示文本是彻底灵活的。
    """

    # voice 模式下用于点燃对话的开场信号：当 aauto_chat_test 检测到 voice 模式时，
    # 第一轮不向被测助手发 start_query，而是向假人发这个信号让假人主动开口。
    # 该信号在对话历史中会被过滤掉，不污染裁判判分。
    VOICE_MODE_OPEN_SIGNAL = "__VOICE_MODE_OPEN__"

    def __init__(
        self,
        store: VolcMemoryStore | None = None,
        present_case: TestCase | None = None,
        max_round: int = 8,
        model: ChatOpenAI = doubao_model,
        checkpointer: BaseCheckpointSaver = InMemorySaver(),
        fake_person_system_template: FakePersonSystemPromptTemplate = FakePersonSystemPromptTemplate(),
        external_api_max_retries: int = DEFAULT_EXTERNAL_API_MAX_RETRIES,
        test_mode: Literal["api", "voice"] = "api",
    ):
        self.model: ChatOpenAI = model
        self.checkpointer: BaseCheckpointSaver = checkpointer  # 虚拟人的短期记忆
        # 虚拟人的火山长期记忆。因为虚拟人也需要有相同的用户基本信息，暂时通过火山记忆共享来实现，可能有问题。
        self.store: VolcMemoryStore | None = store
        self.max_round: int = max_round  # 虚拟人最多对话轮数
        self.profile_template: FakePersonSystemPromptTemplate = (
            fake_person_system_template  # 虚拟人的设定
        )
        self.fake_person: CompiledStateGraph | None = None  # 可对话虚拟人实例
        self.system_prompt: str = (
            "你是一个普通人。"  # 虚拟人的系统提示文本，默认极其简单的人设
        )
        # 正在对话的测试用例，假人必须通过一个case才能初始化
        self.present_case: TestCase | None = present_case
        self.session_id: str | None = None  # 正在对话的聊天ID
        self.external_api_max_retries = external_api_max_retries
        # 测试模式："api"=接口测试（被测助手直接收 car_info 注入，冷启动台词直接发）；
        #          "voice"=语音测试（被测助手收不到 car_info，假人需通过对话搬运必要前置，并由假人主动开口点燃对话）
        self.test_mode: Literal["api", "voice"] = test_mode

    def compile_fake_person(self):
        """
        利用测试用例信息创建一个对应的可对话的虚拟人实例
        """
        self.fake_person = create_agent(
            model=self.model,
            checkpointer=self.checkpointer,
            system_prompt=self.system_prompt,
        )

    async def arender_system_prompt_from_a_case_and_start_query(self, start_query: str):
        """
        利用测试用例信息创建一个对应的可对话的虚拟人的系统提示文本
        """
        if self.present_case is None:
            raise ValueError("请先设置一个测试用例")
        # 查看TestCase里
        if self.store is None:
            memory = None
        else:
            if self.present_case.context_config.get("memory_types") is None:
                memory = None
            else:
                memory = await asyncio_retry_external(
                    operation="VolcMemoryStore.aget_profile_memory_str",
                    factory=lambda: self.store.aget_profile_memory_str(
                        self.present_case.context_config.get("memory_limit"),
                        self.present_case.context_config.get("memory_types"),
                    ),
                    max_retries=self.external_api_max_retries,
                )
        info_to_render = {
            "profile": self.present_case.context_config.get("user_profile"),
            "memory": memory,
            "car_info": self.present_case.context_config.get("car_info"),
            "expected_dialogue": self.present_case.expected_script,
            "case_description": self.present_case.case_description,
            "start_query": start_query,
        }
        # voice 模式专属指引：只有 voice 模式才注入，api 模式保持原行为不变
        if self.test_mode == "voice":
            # voice 模式下假人不应看到 start_query（冷启动台词），纯粹靠剧本和对话记录决定怎么说
            info_to_render["start_query"] = ""
            # 全量注入前置构建方法论，告诉假人何时/如何自主构建语音前置
            methodology = _load_voice_mode_methodology()
            info_to_render["test_mode_directives"] = (
                FAKE_DRIVER_VOICE_MODE_DIRECTIVES
                + "\n\n【语音测试模式前置构建方法论——必须严格遵守】\n"
                + methodology
            )
        else:
            # api 模式不注入 directives，模板里 {% if test_mode_directives %} 块自然不渲染
            info_to_render["test_mode_directives"] = ""
        self.profile_template.any_info_dict.update(info_to_render)
        self.system_prompt = self.profile_template.render()

    def print_history(self):
        old_config = {"configurable": {"thread_id": self.session_id}}
        history = list(self.fake_person.get_state_history(old_config))[0].values[
            "messages"
        ]
        assert history
        volc_history = convert_langchain_history_to_volc_format(history)

    def chat(self, query: str, session_id: str) -> str:
        """
        和假人聊天，用session_id作为一次多轮对话的唯一标识符
        Args:
            query (str): 最新的用户的一句话
            session_id (str): 对话会话ID，用于唯一标识一次多轮对话
        Returns:
            str: 虚拟人对用户查询的回复文本
        """
        return asyncio.run(self.achat(query, session_id))

    async def achat(self, query: str, session_id: str) -> str:
        """
        和假人聊天，用session_id作为一次多轮对话的唯一标识符
        Args:
            query (str): 最新的用户的一句话
            session_id (str): 对话会话ID，用于唯一标识一次多轮对话
        Returns:
            str: 虚拟人对用户查询的回复文本
        """
        if self.fake_person is None:
            await self.arender_system_prompt_from_a_case_and_start_query(query)
            self.compile_fake_person()
        if self.session_id is not None and self.session_id != session_id:
            start_query = query
            await self.arender_system_prompt_from_a_case_and_start_query(start_query)
            self.compile_fake_person()
            self.session_id = session_id
        if self.session_id is None:
            start_query = query
            await self.arender_system_prompt_from_a_case_and_start_query(start_query)
            self.compile_fake_person()
            self.session_id = session_id
        config: RunnableConfig = {"configurable": {"thread_id": self.session_id}}
        response = await asyncio_retry_external(
            operation="FakePerson.langgraph.ainvoke",
            factory=lambda: self.fake_person.ainvoke(
                {"messages": query}, config=config
            ),
            max_retries=self.external_api_max_retries,
        )
        return response["messages"][-1].content


class Judge:
    def __init__(
        self,
        case: TestCase | None = None,
        model: ChatOpenAI = doubao_model,
        *,
        log_enabled: bool = True,
        external_api_max_retries: int = DEFAULT_EXTERNAL_API_MAX_RETRIES,
        judge_format_max_retries: int = DEFAULT_JUDGE_FORMAT_MAX_RETRIES,
        test_mode: Literal["api", "voice"] = "api",
    ):
        self.model: ChatOpenAI = model
        self._log_enabled = log_enabled
        self.checkpointer: BaseCheckpointSaver = InMemorySaver()
        self.judge_prompt_template: JudgeSystemPromptTemplate = (
            JudgeSystemPromptTemplate()
        )  # 裁判导演的设定
        self.system_prompt: str = "你是一个资深而专业的话剧导演。"
        self.judge_format_max_retries = judge_format_max_retries
        # 正在评判的测试用例，不设置也可以，就只是一个光秃秃的导演，没有任何其他信息
        self.present_case: TestCase | None = case
        self.external_api_max_retries = external_api_max_retries
        # 测试模式：voice 模式下裁判 prompt 会注入语音测试专属提示
        self.test_mode: Literal["api", "voice"] = test_mode

    def render_system_prompt_from_a_case_and_history_for_judge(
        self,
        history_record_for_judge: str,
        *,
        is_long_dialogue: bool = False,
        case_traces: list[dict] | dict | None = None,
        car_evidence: str = "",
    ):
        """
        利用测试用例信息创建一个对应的可对话的虚拟人的系统提示文本。

        Args:
            history_record_for_judge: 演员互动记录字符串。
            is_long_dialogue: 是否存在单次多轮对话≥2轮的多轮对话场景；为 True 时 prompt 末尾会渲染
                逐轮分析表格的额外要求。由调用方（``ajudge``）通过
                ``detect_long_dialogue_in_history`` 检测后传入。
            case_traces: 被测助手每轮的状态轨迹（工具调用/入参/结果等），渲染成摘要注入裁判 prompt，
                让裁判能核对助手是否真的执行了操作。为空时模板 {% if %} 块不渲染，不影响原有行为。
            car_evidence: 车机日志证据文本（evidence.json 渲染的粗粒度完整视图，由 ``ajudge``
                通过 ``render_car_evidence_for_judge`` 生成）；为空时模板 {% if %} 块不渲染。
        """
        if self.present_case is None:
            raise ValueError("请先设置一个测试用例")
        self.judge_prompt_template.user_profile = self.present_case.context_config.get(
            "user_profile", ""
        )
        self.judge_prompt_template.car_info = self.present_case.context_config.get(
            "car_info", ""
        )
        self.judge_prompt_template.history_for_judge = history_record_for_judge
        self.judge_prompt_template.expected_dialogue = self.present_case.expected_script
        self.judge_prompt_template.case_description = self.present_case.case_description
        self.judge_prompt_template.nl_assertion = self.present_case.nl_assertion
        self.judge_prompt_template.is_long_dialogue = is_long_dialogue
        # voice 模式注入语音测试专属指引；api 模式留空，模板 {% if %} 块不渲染
        self.judge_prompt_template.test_mode_directives_for_judge = (
            JUDGE_VOICE_MODE_DIRECTIVES if self.test_mode == "voice" else ""
        )
        # 渲染 trace 摘要供裁判核对助手实际行动
        self.judge_prompt_template.trace_summary = render_trace_summary_for_judge(
            case_traces
        )
        # 渲染车机日志证据供裁判核对车机端真实执行
        self.judge_prompt_template.car_evidence = car_evidence
        self.system_prompt = self.judge_prompt_template.render()

    def _parse_judge_result_and_reason(self, judge_result: str) -> tuple[bool, str]:
        """
        解析判断结果字符串，返回判断结果和判断理由
        """

        match = re.search(
            r"result:\s*(Yes|No)\s*reason:\s*(.*)", judge_result, re.DOTALL
        )
        # 校验是否有2个match group
        assert match is not None, "judge_result格式错误，没有匹配到result和reason"
        if match:
            # 校验匹配结果
            result = match.group(1)
            assert result in ["Yes", "No"], "result不是Yes或No"
            if result == "Yes":
                return True, match.group(2).strip()
            else:
                return False, match.group(2).strip()
        return False, "No valid result or reason found"

    async def ajudge(
        self,
        case: TestCase,
        history_for_judge: str,
        case_traces: list[dict] | dict | None = None,
        evidence: dict | str | None = None,
    ) -> tuple[bool, str]:
        """
        对演员的互动记录进行判断，返回判断结果。judge直接使用model进行续写。

        对模型偶发的格式漂移做容错：解析失败时重新调用模型（附加格式提醒），
        最多重试 ``self.judge_format_max_retries`` 次；全部失败则抛出 AssertionError，
        并把最后一次的模型原始回复带进异常消息，便于诊断。

        Args:
            case (MemoryTestCase): 测试用例
            history_for_judge (str): 演员们（即被测bot和假人bot）的互动记录
            case_traces: 被测助手每轮的状态轨迹（工具调用/入参/结果等），渲染成摘要注入裁判 prompt。
                         为空时裁判只看对话文本，不影响原有行为。
            evidence: case 的车机日志证据（evidence.json 的 dict 或 JSON 字符串），
                      渲染成粗粒度完整视图注入裁判 prompt，供裁判核对车机端真实执行；
                      None/空时不注入，不影响原有行为。
        Returns:
            tuple[bool, str]: 判断结果和判断理由
        """
        self.present_case = case
        is_long = detect_long_dialogue_in_history(history_for_judge)
        self.render_system_prompt_from_a_case_and_history_for_judge(
            history_for_judge,
            is_long_dialogue=is_long,
            case_traces=case_traces,
            car_evidence=render_car_evidence_for_judge(evidence),
        )
        session_id = str(uuid.uuid4())
        config: RunnableConfig = {"configurable": {"thread_id": session_id}}

        last_content: str | None = None
        last_error_msg: str = ""
        for attempt in range(self.judge_format_max_retries + 1):
            # 重试时在原 system_prompt 后追加格式提醒，纠正上一次的格式漂移
            prompt = self.system_prompt
            if attempt > 0:
                prompt = (
                    f"{self.system_prompt}\n\n"
                    f"注意：你上一次的回复格式不正确（{last_error_msg}）。"
                    "请严格按照如下格式回复，不要使用其他字段名或格式：\n\n"
                    "result: <Yes或No>\nreason: <你的判断理由>\n"
                )
            response = await asyncio_retry_external(
                operation="Judge.ChatOpenAI.ainvoke",
                factory=lambda: self.model.ainvoke(prompt, config=config),
                max_retries=self.external_api_max_retries,
            )
            assert isinstance(response.content, str), "judge_result为空"
            last_content = response.content
            try:
                return self._parse_judge_result_and_reason(last_content)
            except AssertionError:
                last_error_msg = "没有匹配到result和reason"
                continue
        # 所有重试均失败，带原始回复抛错
        assert False, (
            f"judge 经过 {self.judge_format_max_retries} 次重试仍解析失败。"
            f"模型最后一次原始回复如下：\n{last_content}"
        )

    def judge(
        self,
        case: TestCase,
        history_for_judge: str,
        case_traces: list[dict] | dict | None = None,
    ) -> tuple[bool, str]:
        """
        对演员的互动记录进行判断，返回判断结果。judge直接使用model进行续写。
        Args:
            case (MemoryTestCase): 测试用例
            history_for_judge (str): 演员们（即被测bot和假人bot）的互动记录
            case_traces: 被测助手每轮的状态轨迹（工具调用/入参/结果等），渲染成摘要注入裁判 prompt。
                         为空时裁判只看对话文本，不影响原有行为。
        Returns:
            tuple[bool, str]: 判断结果和判断理由
        """
        return asyncio.run(self.ajudge(case, history_for_judge, case_traces))


class ReportWriter:
    def __init__(
        self,
        model: ChatOpenAI = doubao_model,
        external_api_max_retries: int = DEFAULT_EXTERNAL_API_MAX_RETRIES,
    ):
        self.model: ChatOpenAI = model
        self.checkpointer: BaseCheckpointSaver = InMemorySaver()
        self.report_write_prompt_template: ReportWriterSystemPromptTemplate = (
            ReportWriterSystemPromptTemplate()
        )  # 裁判导演的设定
        self.system_prompt: str = ""
        self.external_api_max_retries = external_api_max_retries

    def _render_system_prompt_from_result_for_report_writer(
        self,
        result_str: str,
        total_case_num: int,
        passed_case_num: int,
        pass_rate: float,
        execution_success_num: int,
        execution_success_rate: float,
        tags_correct_number_and_rate: dict[str, TagResult],
    ):
        """
        利用测试用例信息创建一个对应的可对话的虚拟人的系统提示文本
        """
        self.report_write_prompt_template.result_str = result_str
        self.report_write_prompt_template.total_case_num = total_case_num
        self.report_write_prompt_template.passed_case_num = passed_case_num
        self.report_write_prompt_template.pass_rate = pass_rate
        self.report_write_prompt_template.execution_success_num = execution_success_num
        self.report_write_prompt_template.execution_success_rate = (
            execution_success_rate
        )
        self.report_write_prompt_template.tags_correct_number_and_rate = (
            tags_correct_number_and_rate
        )
        self.system_prompt = self.report_write_prompt_template.render()

    def _write_test_task_report_str(self) -> str:
        """
        写入测试任务报告
        Args:
            result_str (str): 测试任务的结果字符串
            total_case_num (int): 测试用例总数
            passed_case_num (int): 通过的测试用例数
            pass_rate (float): 测试用例通过率
        """
        session_id = str(uuid.uuid4())
        config: RunnableConfig = {"configurable": {"thread_id": session_id}}
        response = sync_retry_external(
            operation="ReportWriter.ChatOpenAI.invoke",
            factory=lambda: self.model.invoke(self.system_prompt, config=config),
            max_retries=self.external_api_max_retries,
        )
        assert isinstance(response.content, str), "report_content为空"
        return response.content

    def write_down_markdown_file(
        self,
        dataset_names: list[str],
        result_str: str,
        total_case_num: int,
        passed_case_num: int,
        pass_rate: float,
        execution_success_num: int,
        execution_success_rate: float,
        tags_correct_number_and_rate: dict[str, TagResult],
        report_file_path: str,
    ):
        """
        写入测试任务报告
        Args:
            dataset_names (list[str]): 测试数据集名称列表
            result_str (str): 测试任务的结果字符串
            total_case_num (int): 测试用例总数
            passed_case_num (int): 通过的测试用例数
            pass_rate (float): 测试用例通过率
        """
        self._render_system_prompt_from_result_for_report_writer(
            result_str,
            total_case_num,
            passed_case_num,
            pass_rate,
            execution_success_num,
            execution_success_rate,
            tags_correct_number_and_rate,
        )
        report_content_str = self._write_test_task_report_str()
        # 把符合Markdown文件格式的report_content_str写入文件
        assert report_file_path.endswith(".md"), "report_file_path必须是Markdown文件"
        with open(report_file_path, "w", encoding="utf-8") as f:
            f.write(f"测试数据集名称列表：{dataset_names}\n\n")
            f.write(report_content_str)


T = TypeVar("T")


# 封装待测机器人，既可以直接用langchain的bot，又可以兼容其他框架的bot甚至api的bot，只要有chat方法即可
class AnyBotToTest(Protocol):
    """任何待测机器人的协议，满足协议即可测"""

    async def aupdate_context(self, context_config: dict[str, Any]) -> None:
        """
        异步更新当前bot的上下文配置。
        Args:
            context_config (dict[str, Any]): 本次多轮对话要生效的上下文（可覆盖初始配置）
        """
        ...

    async def dump_state_trace(self) -> dict:
        """
        导出一个助手至今为止的状态变化记录，用于保存供debug使用，在自动化评测系统中会保留
        Returns:
            dict: 助手的状态变化记录
        """
        ...

    def chat(self, query: str, session_id: str) -> str:
        """
        与机器人进行一次对话，返回机器人的回复
        Args:
            query (str): 用户的查询
            session_id (str): 会话ID
        Returns:
            str: 机器人的回复
        """
        ...

    async def achat(self, query: str, session_id: str) -> str:
        """
        异步与机器人进行一次对话，返回机器人的回复
        Args:
            query (str): 用户的查询
            session_id (str): 会话ID
        Returns:
            str: 机器人的回复
        """
        ...

    def dump_history(self) -> list[dict[str, str]]:
        """
        导出被测机器人的互动记录列表。允许包含首条system提示词，评测侧会在送judge前剔除该条。
        并且注意工具返回如果不能控制其内容规模，那么干脆别放进来。
        Returns:
            list[dict[str, str]]: 机器人的互动记录列表，一般形如[{"role": "user", "content": "你好，我要导航到公园"}, {"role": "assistant", "content": "好，调用导航工具"},{"role": "tool_call", "param": "xxx"},{"role": "tool_result", "result": "xxx"},{"role": "assistant", "content": "已经导航到公园啦"}]
            不一定如上述形式，重要的是要一个精简的可读的记录列表，自动测试会用换行符原原本本粘起这些记录dict的str形态后就直接送往judge进行评判
        """
        ...

    async def adump_history(self) -> list[dict[str, str]]:
        """
        异步导出被测机器人的互动记录列表。允许包含首条system提示词，评测侧会在送judge前剔除该条。
        并且注意工具返回如果不能控制其内容规模，那么干脆别放进来。

        自动测试在一次「单次多轮」走完并准备落盘评判前会调用本方法（参见 ``aauto_chat_test``
        尾部）。对于有记忆生产者且 ``session_size`` 较大的 Bot，仅靠 ``session_id`` 切换触发
        ``flush`` 会漏掉「仅此一段会话」的对话；此类实现应在返回前按需提交缓冲区（例如
        ``MemoryProducer.flush``），不改变本方法返回值形态。

        Returns:
            list[dict[str, str]]: 机器人的互动记录列表，一般形如[{"role": "user", "content": "你好，我要导航到公园"}, {"role": "assistant", "content": "好，调用导航工具"},{"role": "tool_call", "param": "xxx"},{"role": "tool_result", "result": "xxx"},{"role": "assistant", "content": "已经导航到公园啦"}]
            不一定如上述形式，重要的是要一个精简的可读的记录列表，自动测试会用换行符原原本本粘起这些记录dict的str形态后就直接送往judge进行评判
        """
        ...

    async def adump_state_trace(self) -> dict:
        """
        异步导出一个助手至今为止的状态变化记录，用于保存供debug使用，在自动化评测系统中会保留
        Returns:
            dict: 助手的状态变化记录
        """
        ...

    @classmethod
    def create(cls: Type[T], context_config: dict[str, Any], *args, **kwargs) -> T:
        """
        创建一个待测机器人实例，用context_config配置机器人人的包括但不限于系统提示词在内的所有任意配置项，每次会使用case内的context_config来初始化配置待测机器人
        Args:
            context_config (dict[str, Any]): 包含系统提示词、用户信息、车辆状态，记忆配置等等任意配置项的字典
            *args: 其他参数
            **kwargs: 其他关键字参数
        """
        ...

    @classmethod
    async def aclean_memory_for_users(
        cls,
        user_ids: list[str],
        *,
        context_config: dict[str, Any] | None = None,
        except_skills: bool = False,
    ) -> None:
        """
        按 user_id 批量清空该 bot 对应记忆库中的记忆。

        自动评测脚本在每个 epoch 开始前调用此方法，确保 case 之间记忆隔离。
        子类应根据自身记忆后端实现具体的清空逻辑；无记忆后端的 bot 可空实现。

        Args:
            user_ids: 待清空记忆的用户 ID 列表（在评测脚本中即 case_id）。
            context_config: 可选的上下文配置，供 bot 解析自身使用的记忆库标识
                （collection_name / assistant_id 等）。不传时 bot 应使用自身默认配置。
            except_skills: 为 True 时保留 skills 画像，仅清空事件记忆与非 skills 画像。
        """
        ...


class SystemPromptTemplate(BaseModel):
    """
    信息模板，可以配置任何助手的信息
    """

    any_info_dict: dict = Field(
        default_factory=dict,
        description="可以配置任何信息到任何prompt模板里，请自行确保模板与信息的匹配,否则报错。",
    )
    prompt_template: str = Field(
        default=DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE,
        description="系统提示文本的渲染模板",
    )

    def render(self) -> str:
        """
        渲染系统提示文本
        """
        return Template(self.prompt_template).render(**self.any_info_dict)


class RunCaseResult(BaseModel):
    """
    运行测试用例的结果
    tuple[bool, str, list[str], str, str, list[str],str, list[dict]]: 判断结果，判断理由，tags，id，case_id，nl_assertion，history_for_judge，case_traces
    """

    is_passed: bool = Field(description="是否通过测试")
    reason: str = Field(description="判断理由")
    tags: list[str] = Field(default_factory=list, description="测试用例的标签")
    id: Annotated[str, BeforeValidator(str)] = Field(description="测试用例的ID")
    case_id: str = Field(description="测试用例的name")
    nl_assertion: list[str] = Field(description="测试用例的NL断言")
    history_for_judge: str = Field(
        default_factory=str, description="测试用例的对话记录编纂出来的字符串"
    )
    case_traces: list[dict] = Field(
        default_factory=list, description="测试用例的运行轨迹"
    )
    tags: list[str] = Field(default_factory=list, description="测试用例的标签")
    execution_success: bool = Field(default=True, description="用例是否执行成功")
    execution_error: str | None = Field(
        default=None, description="执行失败时的错误信息"
    )


class RunAllCasesResult(BaseModel):
    """
    运行所有测试用例的结果
    details_result_list: 每个case跑了后的RunCaseResult的列表
            result: 测试任务的总体结果字符串，可直接打印当可视化log使用
            total_case_num: 评测总次数（单轮=数据集用例数；多 epoch=用例数×epoch）
            passed_case_num: 通过的评测次数
            pass_rate: 通过率
            execution_success_num: 执行成功的评测次数
            execution_success_rate: 执行成功率
            tags_correct_number_and_rate: 每个tag的正确数和通过率
    """

    details_result_list: list[RunCaseResult] = Field(
        default_factory=list, description="所有测试用例的结果"
    )
    result: str = Field(
        description="测试任务的总体结果字符串，可直接打印当可视化log使用"
    )
    total_case_num: int = Field(
        description="评测总次数（单轮=用例数；多 epoch=用例数×epoch）"
    )
    passed_case_num: int = Field(description="通过的评测次数")
    pass_rate: float = Field(description="测试用例通过率")
    execution_success_num: int = Field(default=0, description="执行成功的评测次数")
    execution_success_rate: float = Field(default=0.0, description="执行成功率")
    tags_correct_number_and_rate: dict[str, TagResult] = Field(
        default_factory=dict,
        description="每个tag的通过数和通过率, key是tag, value是TagResult",
    )


class _PassedCountColumn(ProgressColumn):
    """直接读 task.fields，避免 str.format / Rich markup 误解析字段名。

    双维度显示：全局累计 + 当前 epoch 内计数。
    - 全局分母为总评测次数（base_case_num * epoch），跨 epoch 不重置；
    - 当前 epoch 分母为单 epoch case 数，每轮重置。
    """

    def render(self, task) -> Text:
        passed = int(task.fields.get("passed_count", 0))
        exec_ok = int(task.fields.get("execution_success_count", 0))
        total = int(task.fields.get("global_total", 0)) or int(task.total or 0)
        ep_passed = int(task.fields.get("epoch_passed_count", 0))
        ep_exec_ok = int(task.fields.get("epoch_execution_success_count", 0))
        ep_completed = int(task.fields.get("epoch_completed", 0))
        ep_total = int(task.fields.get("epoch_total", 0))
        return Text(
            f"执行成功 {exec_ok}/{total} (本轮 {ep_exec_ok}/{ep_completed}/{ep_total}) "
            f"通过 {passed}/{total} (本轮 {ep_passed}/{ep_completed}/{ep_total})",
            style="green",
        )


class _PassRateColumn(ProgressColumn):
    def render(self, task) -> Text:
        exec_rate = task.fields.get("execution_success_rate", "—")
        pass_rate = task.fields.get("pass_rate", "—")
        ep_exec_rate = task.fields.get("epoch_execution_success_rate", "—")
        ep_pass_rate = task.fields.get("epoch_pass_rate", "—")
        return Text(
            f"执行成功率 {exec_rate} (本轮 {ep_exec_rate}) 通过率 {pass_rate} (本轮 {ep_pass_rate})",
            style="cyan",
        )


class _EtaRemainingColumn(ProgressColumn):
    def render(self, task) -> Text:
        return Text(f"预计还需 {task.fields.get('eta', '—')}", style="dim")


def _format_eta_remaining(seconds: float) -> str:
    """将剩余秒数格式化为可读中文时长。"""
    if not math.isfinite(seconds) or seconds < 0:
        return "—"
    total = int(seconds)
    if total == 0:
        return "即将完成"
    if total < 60:
        return f"{total}秒"
    minutes, sec = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}分{sec}秒" if sec else f"{minutes}分钟"
    hours, minutes = divmod(minutes, 60)
    if minutes:
        return f"{hours}小时{minutes}分"
    return f"{hours}小时"


class _AutoTestRunProgress:
    """
    Rich 进度条固定在终端底部（备用屏幕 + stdout/stderr 重定向 + 统一 Rich 控制台）。

    开启时会抑制被测 bot 侧控制台输出（见 ``auto_test_suppress_bot_console`` / ``is_auto_test_bot_console_suppressed``）。
    """

    def __init__(
        self,
        *,
        total: int,
        epoch: int,
        enabled: bool,
        verbose: bool,
        log_dialogue: bool | None,
        epoch_total: int,
    ) -> None:
        self._total = total  # 全局总评测次数 = base_case_num * epoch
        self._epoch_total = epoch_total  # 单 epoch case 数 = base_case_num
        self._epoch = epoch
        self._enabled = enabled
        self._verbose = verbose
        self._log_dialogue = log_dialogue
        self._progress: Progress | None = None
        self._task_id: int | None = None
        self._completed = 0  # 全局累计已完成
        self._global_passed = 0  # 全局累计通过
        self._global_exec_ok = 0  # 全局累计执行成功
        self._epoch_completed = 0  # 当前 epoch 内已完成
        self._epoch_passed = 0  # 当前 epoch 内通过
        self._epoch_exec_ok = 0  # 当前 epoch 内执行成功
        self._rich_console_snapshot: dict[str, Any] | None = None
        self._suppress_token: contextvars.Token[bool] | None = None
        self._epoch_hint = ""
        self._started_at: float | None = None

    def _estimate_eta_remaining(self) -> str:
        """按已完成 case 的平均耗时，估算剩余 case 还需多久。"""
        if self._started_at is None or self._completed <= 0:
            return "计算中…"
        remaining = self._total - self._completed
        if remaining <= 0:
            return "即将完成"
        elapsed = time.monotonic() - self._started_at
        return _format_eta_remaining(elapsed / self._completed * remaining)

    def __enter__(self) -> "_AutoTestRunProgress":
        if not self._enabled:
            return self
        configure_auto_test_logging(
            verbose=self._verbose,
            log_dialogue=self._log_dialogue,
            use_rich_handler=True,
            rich_console=_progress_console,
        )
        self._rich_console_snapshot = _bind_rich_global_console(_progress_console)
        self._suppress_token = _auto_test_suppress_bot_console.set(True)
        self._started_at = time.monotonic()

        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=36),
            TaskProgressColumn(),
            TextColumn("•"),
            _PassedCountColumn(),
            TextColumn("•"),
            _PassRateColumn(),
            TimeElapsedColumn(),
            TextColumn("•"),
            _EtaRemainingColumn(),
            console=_progress_console,
            redirect_stdout=True,
            redirect_stderr=True,
            refresh_per_second=4,
            expand=True,
            transient=False,
        )
        # 备用屏幕：进度条独占终端视口，普通 print/rich.print 在上方滚动，不会顶掉进度条。
        self._progress.live._screen = True
        self._progress.__enter__()
        self._epoch_hint = f" 第1/{self._epoch}轮" if self._epoch > 1 else ""
        self._task_id = self._progress.add_task(
            self._running_description(),
            total=self._total,
            passed_count=0,
            pass_rate="—",
            execution_success_count=0,
            execution_success_rate="—",
            global_total=self._total,
            epoch_total=self._epoch_total,
            epoch_completed=0,
            epoch_passed_count=0,
            epoch_execution_success_count=0,
            epoch_execution_success_rate="—",
            epoch_pass_rate="—",
            eta="计算中…",
        )
        return self

    def _running_description(self) -> str:
        return f"自动化评测{self._epoch_hint}  {self._completed}/{self._total}"

    def set_epoch(self, epoch_index: int) -> None:
        if not self._enabled or self._progress is None or self._task_id is None:
            return
        self._epoch_hint = (
            f" 第{epoch_index + 1}/{self._epoch}轮" if self._epoch > 1 else ""
        )
        # 重置当前 epoch 内计数器（全局累计保留）
        self._epoch_completed = 0
        self._epoch_passed = 0
        self._epoch_exec_ok = 0
        self._progress.update(
            self._task_id,
            description=self._running_description(),
            epoch_completed=0,
            epoch_passed_count=0,
            epoch_execution_success_count=0,
            epoch_execution_success_rate="—",
            epoch_pass_rate="—",
        )

    def set_status(self, message: str) -> None:
        if not self._enabled or self._progress is None or self._task_id is None:
            return
        self._progress.update(self._task_id, description=message)

    def on_case_done(
        self,
        *,
        passed: int,
        execution_success_count: int,
        epoch_passed: int,
        epoch_execution_success_count: int,
    ) -> None:
        """更新进度条。

        传双维度计数：
        - ``passed`` / ``execution_success_count``: 全局累计通过/执行成功
        - ``epoch_passed`` / ``epoch_execution_success_count``: 当前 epoch 内通过/执行成功
        ``completed`` 由进度条内部维护（每次 advance=1 自动累加），不再从外部传。
        """
        if not self._enabled or self._progress is None or self._task_id is None:
            return
        self._global_passed = passed
        self._global_exec_ok = execution_success_count
        self._epoch_passed = epoch_passed
        self._epoch_exec_ok = epoch_execution_success_count
        self._completed = min(self._completed + 1, self._total)
        self._epoch_completed = min(self._epoch_completed + 1, self._epoch_total)

        exec_rate = (
            execution_success_count / self._completed if self._completed else 0.0
        )
        overall_rate = (
            passed / execution_success_count if execution_success_count else 0.0
        )
        ep_exec_rate = (
            epoch_execution_success_count / self._epoch_completed
            if self._epoch_completed
            else 0.0
        )
        ep_overall_rate = (
            epoch_passed / epoch_execution_success_count
            if epoch_execution_success_count
            else 0.0
        )
        self._progress.update(
            self._task_id,
            advance=1,
            passed_count=passed,
            pass_rate=f"{overall_rate:.1%}",
            execution_success_count=execution_success_count,
            execution_success_rate=f"{exec_rate:.1%}",
            epoch_passed_count=epoch_passed,
            epoch_execution_success_count=epoch_execution_success_count,
            epoch_execution_success_rate=f"{ep_exec_rate:.1%}",
            epoch_pass_rate=f"{ep_overall_rate:.1%}",
            epoch_completed=self._epoch_completed,
            eta=self._estimate_eta_remaining(),
            description=self._running_description(),
        )

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._suppress_token is not None:
            _auto_test_suppress_bot_console.reset(self._suppress_token)
            self._suppress_token = None
        if self._progress is not None:
            self._progress.__exit__(exc_type, exc_val, exc_tb)
            self._progress = None
        if self._rich_console_snapshot is not None:
            _restore_rich_global_console(self._rich_console_snapshot)
            self._rich_console_snapshot = None


class AutoTestAndRLDataGenerator:
    """自动测试和强化学习数据生成器"""

    # 把bot_to_test改为可传入一个符合AnyBotToTest Protocol的类
    def __init__(
        self,
        bot_to_test: Type[AnyBotToTest],
        memory_test_cases: list[TestCase] | str,
        give_score: bool = True,
        *,
        verbose: bool = True,
        log_dialogue: bool | None = None,
        show_progress: bool = True,
        external_api_max_retries: int = DEFAULT_EXTERNAL_API_MAX_RETRIES,
        test_mode: Literal["api", "voice"] = "api",
    ):
        """
        Args:
            bot_to_test (Type[AnyBotToTest]): 待测试的机器人类，必须符合AnyBotToTest协议
            memory_test_cases (list[TestCase]): 测试用例列表
            give_score (bool, optional): 是否给每个测试用例评分. Defaults to True.
            verbose: 是否向控制台输出评测进度与汇总信息。默认 True（与原先 print 行为一致）。
            log_dialogue: 是否输出每轮用户/助手对话；默认与 verbose 相同。可单独关闭以仅保留汇总日志。
            show_progress: 是否在跑批时显示 Rich 终端进度条（与 ``verbose`` / ``log_dialogue`` 一样，仅在构造时配置）。默认 True。
            external_api_max_retries: LLM / 火山等外部调用失败后，除首次外最多再重试次数；默认 5（共至多 6 次尝试）。
            test_mode: 测试模式，"api"=接口测试（被测助手直接收 car_info 注入，冷启动台词直接发给被测助手）；
                "voice"=语音测试（被测助手收不到 car_info 注入，假人需通过对话搬运必要前置，并由假人主动开口点燃对话）。
                默认 "api"，保持向后兼容。
        """
        self.external_api_max_retries = external_api_max_retries
        self._show_progress = show_progress
        self.test_mode: Literal["api", "voice"] = test_mode
        configure_auto_test_logging(
            verbose=verbose,
            log_dialogue=log_dialogue,
            use_rich_handler=show_progress,
        )
        self._verbose = verbose
        self._log_dialogue = verbose if log_dialogue is None else log_dialogue
        self.memory_test_cases: list[TestCase] = []
        if isinstance(memory_test_cases, str):
            self.memory_test_cases = sync_retry_external(
                operation="get_dataset_list_sync",
                factory=lambda n=memory_test_cases: get_dataset_list_sync(n),
                max_retries=self.external_api_max_retries,
            )
        else:
            self.memory_test_cases = memory_test_cases
        assert self.memory_test_cases, "memory_test_cases不能为空"
        # 如果case有记忆相关的配置才用上
        self.store: VolcMemoryStore | None = None
        self.give_score = give_score
        self.pause_mode = False
        self.long_term_use = False
        self.long_term_use_user_id = "跑长期记忆"
        self.bot_to_test = bot_to_test
        self.upload_history_to_volc_memory = False
        #: 仅在 ``long_term_use`` 时使用：对齐 demo_v1 的完整快照，跑批开始时构建一次，
        #: 对每个 case 与 ``case.context_config`` 做「快照压 case」合并。
        self._long_term_context_bundle: dict[str, Any] | None = None

    async def _a_retry_external_api(
        self, operation: str, factory: Callable[[], Awaitable[_R]]
    ) -> _R:
        return await asyncio_retry_external(
            operation=operation,
            factory=factory,
            max_retries=self.external_api_max_retries,
        )

    @classmethod
    def _conver_history_dict_to_volc_messages(
        cls, history: list[dict]
    ) -> list[Message]:
        # 如果dict里key是用户，那么role=user，否则role=assistant
        volc_messages = []
        # TODO: 这里就要统一！！如果dump的不是“用户”“助手”
        for one_turn in history:
            if one_turn["role"] == "用户" or one_turn["role"] == "user":
                role = "user"
            elif one_turn["role"] == "助手" or one_turn["role"] == "assistant":
                role = "assistant"
            else:
                continue
            volc_messages.append(Message(role=role, content=one_turn["content"]))
        return volc_messages

    @classmethod
    def _normalize_dialogue_round(
        cls, one_dialogue: list[Message] | DialogueRoundConfig
    ) -> tuple[str, dict[str, Any], str | None]:
        """兼容旧格式(list[Message])和新格式(DialogueRoundConfig)的单轮配置。"""
        if isinstance(one_dialogue, DialogueRoundConfig):
            user_messages = one_dialogue.user_query_list
            mock_info = dict(one_dialogue.mock_info)
            mock_time = one_dialogue.mock_time
        else:
            user_messages = one_dialogue
            mock_info = {}
            mock_time = None
        assert user_messages, "每次多轮对话至少要有一条用户消息用于冷启动"
        start_query = user_messages[0].content
        return start_query, mock_info, mock_time

    @classmethod
    def _strip_first_system_message(cls, history: list[dict]) -> list[dict]:
        """去掉history首条system消息，避免把system prompt传给judge。"""
        if not history:
            return history
        first_role = str(history[0].get("role", "")).lower()
        if first_role == "system":
            return history[1:]
        return history

    async def aauto_chat_test(
        self,
        bot_to_test: AnyBotToTest,
        fake_person: FakePerson,
        start_query: str,
        max_round: int = 8,
    ) -> tuple[int, list[dict]] | list[dict]:
        """
        以一句用户的话为引子，引发一段多轮对话，返回用户对本次服务的评分和对话历史
        Args:
            bot_to_test (AnyBotToTest): 待测试的机器人实例，必须符合AnyBotToTest协议
            fake_person (FakePerson): 假人
            start_query (str): 一次多轮对话中用户说的第一句话，用来冷启动
                - api 模式：直接作为冷启动台词发给被测助手
                - voice 模式：作为"核心意图参考"注入假人 prompt，假人自主组织第一句话开口
            max_round (int, optional): 最大轮数，超过最大轮数，对话不得不结束. Defaults to 8.
        Returns:
            tuple[int, list[dict]]: 用户对本次服务的评分和对话历史

        对话正常结束时通过 ``await bot_to_test.adump_history()`` 取出助手侧历史；需要把本段会话
        提交记忆库的 Bot（如带 ``MemoryProducer``、且仅靠 ``session_id`` 切换时的 ``flush``
        不足以覆盖「单段即止」的场景）应在 ``adump_history`` 的实现里完成缓冲区提交而不是依赖
        评测脚本额外钩子。

        voice 模式下，第一轮不向被测助手发 start_query，而是向假人发开场信号
        (``FakePerson.VOICE_MODE_OPEN_SIGNAL``)，由假人主动说出第一句话点燃对话，
        再把假人的话发给被测助手。开场信号不进入 history_for_judge，不污染裁判判分。
        """
        # 注意测试时，在火山控制台确保MEMORY_USER_ID对应的记忆为空！！！否则有很多以前的记忆。
        session_id = str(uuid.uuid4())
        trace = {}
        history_for_judge = []

        if fake_person.test_mode == "voice":
            # voice 模式：假人主动开口点燃对话
            # 向假人发开场信号，假人 prompt 里约定收到此信号且对话历史为空时主动说出第一句话
            fake_person_answer = await self._a_retry_external_api(
                "FakePerson.achat(voice_open)",
                lambda: fake_person.achat(
                    FakePerson.VOICE_MODE_OPEN_SIGNAL, session_id
                ),
            )
            if self._log_dialogue:
                _dialogue_logger.info("+" * 80)
                _dialogue_logger.info("用户（假人主动开口）：%s", fake_person_answer)
            history_for_judge.append({"role": "用户", "content": fake_person_answer})
            # 把假人的第一句话发给被测助手
            assistant_answer = await self._a_retry_external_api(
                "bot_to_test.achat",
                lambda: bot_to_test.achat(fake_person_answer, session_id),
            )
            if self._log_dialogue:
                _dialogue_logger.info("+" * 80)
                _dialogue_logger.info("助手：%s", assistant_answer)
            history_for_judge.append({"role": "助手", "content": assistant_answer})
            now_round = 1
            round_trace = await self._a_retry_external_api(
                "bot_to_test.adump_state_trace",
                lambda: bot_to_test.adump_state_trace(),
            )
            trace[now_round] = round_trace
            # 后续循环：假人继续回应助手的话，循环结构与 api 模式一致
            while "退下" not in fake_person_answer and now_round < max_round:
                now_round += 1
                fake_person_answer = await self._a_retry_external_api(
                    "FakePerson.achat",
                    lambda: fake_person.achat(assistant_answer, session_id),
                )
                history_for_judge.append(
                    {"role": "用户", "content": fake_person_answer}
                )
                if self._log_dialogue:
                    _dialogue_logger.info("+" * 80)
                    _dialogue_logger.info("用户：%s", fake_person_answer)
                assistant_answer = await self._a_retry_external_api(
                    "bot_to_test.achat",
                    lambda: bot_to_test.achat(fake_person_answer, session_id),
                )
                history_for_judge.append({"role": "助手", "content": assistant_answer})
                if self._log_dialogue:
                    _dialogue_logger.info("+" * 80)
                    _dialogue_logger.info("助手：%s", assistant_answer)
                round_trace = await self._a_retry_external_api(
                    "bot_to_test.adump_state_trace",
                    lambda: bot_to_test.adump_state_trace(),
                )
                trace[now_round] = round_trace
        else:
            # api 模式：原逻辑，直接把 start_query 发给被测助手作为冷启动
            if self._log_dialogue:
                _dialogue_logger.info("+" * 80)
                _dialogue_logger.info("用户：%s", start_query)
            assistant_answer = await self._a_retry_external_api(
                "bot_to_test.achat",
                lambda: bot_to_test.achat(start_query, session_id),
            )
            if self._log_dialogue:
                _dialogue_logger.info("+" * 80)
                _dialogue_logger.info("助手：%s", assistant_answer)
            history_for_judge.append({"role": "助手", "content": assistant_answer})
            fake_person_answer = ""
            now_round = 1
            round_trace = await self._a_retry_external_api(
                "bot_to_test.adump_state_trace",
                lambda: bot_to_test.adump_state_trace(),
            )
            trace[now_round] = round_trace
            while "退下" not in fake_person_answer and now_round < max_round:
                now_round += 1
                fake_person_answer = await self._a_retry_external_api(
                    "FakePerson.achat",
                    lambda: fake_person.achat(assistant_answer, session_id),
                )
                history_for_judge.append(
                    {"role": "用户", "content": fake_person_answer}
                )
                if self._log_dialogue:
                    _dialogue_logger.info("+" * 80)
                    _dialogue_logger.info("用户：%s", fake_person_answer)
                assistant_answer = await self._a_retry_external_api(
                    "bot_to_test.achat",
                    lambda: bot_to_test.achat(fake_person_answer, session_id),
                )
                history_for_judge.append({"role": "助手", "content": assistant_answer})
                if self._log_dialogue:
                    _dialogue_logger.info("+" * 80)
                    _dialogue_logger.info("助手：%s", assistant_answer)
                round_trace = await self._a_retry_external_api(
                    "bot_to_test.adump_state_trace",
                    lambda: bot_to_test.adump_state_trace(),
                )
                trace[now_round] = round_trace

        history = await self._a_retry_external_api(
            "bot_to_test.adump_history",
            lambda: bot_to_test.adump_history(),
        )
        if now_round >= max_round:
            _logger.warning("超过最大轮数，对话不得不结束")
            history.append({"role": "导演", "content": "你们超过最大对话次数啦！cut！"})
            history_for_judge.append(
                {"role": "导演", "content": "你们超过最大对话次数啦！cut！"}
            )
        # trace = await bot_to_test.adump_state_trace()
        # 最后一句假人回复需要加入history里,因为adump_history是助手端的短期记忆，不包括假人触发结束条件的最后一句话
        # history.append({"role": "user", "content": fake_person_answer})

        if self.give_score:
            score = parse_score(fake_person_answer)
            # return score, history_for_judge
            return score, history, trace
        else:
            # return history_for_judge
            return history, trace

    def write_test_task_report(
        self,
        dataset_names: list[str],
        result_str: str,
        total_case_num: int,
        passed_case_num: int,
        pass_rate: float,
        execution_success_num: int,
        execution_success_rate: float,
        tags_correct_number_and_rate: dict[str, TagResult],
        report_file_path: str,
    ):
        """
        写入测试任务报告
        Args:
            dataset_names (list[str]): 测试数据集名称列表
            result_str (str): 测试任务的结果字符串
            total_case_num (int): 测试用例总数
            passed_case_num (int): 通过的测试用例数
            pass_rate (float): 测试用例通过率
            execution_success_num (int): 执行成功的测试用例数
            execution_success_rate (float): 执行成功率
            tags_correct_number_and_rate (dict[str, TagResult]): 标签通过数和通过率
            report_file_path (str): 报告文件路径，必须是Markdown文件
        """
        # 创建一个报告写手
        report_writer = ReportWriter(
            external_api_max_retries=self.external_api_max_retries,
        )
        assert report_file_path.endswith(".md"), "report_file_path必须是Markdown文件"
        # 确保目录存在
        os.makedirs(os.path.dirname(report_file_path), exist_ok=True)
        if self._verbose:
            _logger.info("正在写入测试任务报告...")
        report_writer.write_down_markdown_file(
            dataset_names,
            result_str,
            total_case_num,
            passed_case_num,
            pass_rate,
            execution_success_num,
            execution_success_rate,
            tags_correct_number_and_rate,
            report_file_path,
        )
        if self._verbose:
            _logger.info("测试任务报告写入完成")

    @staticmethod
    def _collect_leaves_under_node(node) -> list[str]:
        leaves: list[str] = []
        if not node.children:
            leaves.append(node.name)
        for child in node.children:
            leaves.extend(AutoTestAndRLDataGenerator._collect_leaves_under_node(child))
        return leaves

    @staticmethod
    def _find_node_in_tree(root, name: str):
        if root.name == name:
            return root
        for child in root.children:
            found = AutoTestAndRLDataGenerator._find_node_in_tree(child, name)
            if found is not None:
                return found
        return None

    @staticmethod
    def _compute_tag_stats_with_tree(
        details: list[RunCaseResult],
        tags_to_print: list[str],
        tag_tree: TagTree | None,
    ) -> dict[str, TagResult]:
        expanded_tags: list[str] = []
        if tag_tree is not None:
            for tag_name in tags_to_print:
                node = AutoTestAndRLDataGenerator._find_node_in_tree(
                    tag_tree.root, tag_name
                )
                if node is not None and node.children:
                    for n in node.iter_nodes():
                        if n.name not in expanded_tags:
                            expanded_tags.append(n.name)
                else:
                    if tag_name not in expanded_tags:
                        expanded_tags.append(tag_name)
        else:
            expanded_tags = list(tags_to_print)

        tag_to_cases: dict[str, set[str]] = {}
        for tag_name in expanded_tags:
            tag_to_cases[tag_name] = set()

        if tag_tree is not None:
            for tag_name in expanded_tags:
                node = AutoTestAndRLDataGenerator._find_node_in_tree(
                    tag_tree.root, tag_name
                )
                if node is not None and node.children:
                    leaf_names = AutoTestAndRLDataGenerator._collect_leaves_under_node(
                        node
                    )
                    for case_result in details:
                        if any(t in leaf_names for t in case_result.tags):
                            tag_to_cases[tag_name].add(case_result.id)
                else:
                    for case_result in details:
                        if tag_name in case_result.tags:
                            tag_to_cases[tag_name].add(case_result.id)
        else:
            for tag_name in expanded_tags:
                for case_result in details:
                    if tag_name in case_result.tags:
                        tag_to_cases[tag_name].add(case_result.id)

        case_by_id: dict[str, RunCaseResult] = {r.id: r for r in details}
        result: dict[str, TagResult] = {}
        for tag_name in expanded_tags:
            case_ids = tag_to_cases[tag_name]
            total = len(case_ids)
            if total == 0:
                result[tag_name] = TagResult(tag=tag_name, tag_total=0)
                continue
            exec_ok = sum(1 for cid in case_ids if case_by_id[cid].execution_success)
            passed = sum(
                1
                for cid in case_ids
                if case_by_id[cid].execution_success and case_by_id[cid].is_passed
            )
            result[tag_name] = TagResult(
                tag=tag_name,
                tag_total=total,
                execution_success_number=exec_ok,
                execution_success_rate=exec_ok / total if total else 0.0,
                passed_number=passed,
                pass_rate=passed / exec_ok if exec_ok else 0.0,
            )
        return result

    @staticmethod
    def _format_tag_stats_hierarchical(
        tags_stats: dict[str, TagResult],
        tags_to_print: list[str],
        tag_tree: TagTree | None,
    ) -> str:
        if tag_tree is None:
            lines: list[str] = []
            for tag_name in tags_to_print:
                tr = tags_stats.get(tag_name)
                if tr is None:
                    continue
                if tr.tag_total == 0:
                    lines.append(f"  - {tag_name}: 总数:0")
                else:
                    lines.append(
                        f"  - {tag_name}: 总数:{tr.tag_total}，"
                        f"执行成功:{tr.execution_success_number}({tr.execution_success_rate:.2%})，"
                        f"通过:{tr.passed_number}({tr.pass_rate:.2%})"
                    )
            return "\n".join(lines)

        def _render_subtree(node, indent: int) -> list[str]:
            lines = []
            prefix = "  " * indent + "- " if indent > 0 else "  - "
            tr = tags_stats.get(node.name)
            if tr is not None:
                if tr.tag_total == 0:
                    lines.append(f"{prefix}{node.name}: 总数:0")
                else:
                    lines.append(
                        f"{prefix}{node.name}: 总数:{tr.tag_total}，"
                        f"执行成功:{tr.execution_success_number}({tr.execution_success_rate:.2%})，"
                        f"通过:{tr.passed_number}({tr.pass_rate:.2%})"
                    )
            for child in node.children:
                lines.extend(_render_subtree(child, indent + 1))
            return lines

        lines = []
        rendered_names: set[str] = set()
        for tag_name in tags_to_print:
            node = AutoTestAndRLDataGenerator._find_node_in_tree(
                tag_tree.root, tag_name
            )
            if node is not None and node.children:
                lines.extend(_render_subtree(node, 0))
                rendered_names.add(tag_name)
                for desc in node.iter_nodes():
                    rendered_names.add(desc.name)
            else:
                if tag_name not in rendered_names:
                    tr = tags_stats.get(tag_name)
                    if tr is not None:
                        if tr.tag_total == 0:
                            lines.append(f"  - {tag_name}: 总数:0")
                        else:
                            lines.append(
                                f"  - {tag_name}: 总数:{tr.tag_total}，"
                                f"执行成功:{tr.execution_success_number}({tr.execution_success_rate:.2%})，"
                                f"通过:{tr.passed_number}({tr.pass_rate:.2%})"
                            )
                    rendered_names.add(tag_name)
        return "\n".join(lines)

    def write_test_task_judge_log(
        self,
        dataset_names: list[str],
        total_case_num: int,
        passed_case_num: int,
        pass_rate: float,
        execution_success_num: int,
        execution_success_rate: float,
        tags_correct_number_and_rate: dict[str, TagResult],
        judge_result: str,
        log_file_path: str,
        epoch: int = 1,
        tags_to_print: list[str] | None = None,
        tag_tree: TagTree | None = None,
        details_result_list: list[RunCaseResult] | None = None,
    ):
        """
        写入测试任务评测日志
        Args:
            dataset_names (list[str]): 测试数据集名称列表
            total_case_num (int): 测试用例总数（多 epoch 时为累计评测次数）
            passed_case_num (int): 通过的测试用例数（多 epoch 时为累计通过次数）
            pass_rate (float): 测试用例通过率
            execution_success_num (int): 执行成功的测试用例数
            execution_success_rate (float): 执行成功率
            tags_correct_number_and_rate (dict[str, TagResult]): 标签通过数和通过率
            judge_result (str): 测试任务的评测结果字符串
            log_file_path (str): 日志文件路径，必须是Markdown文件
            epoch (int): 重复跑批轮数。大于 1 时日志头部不写用例总数/通过数等次数类汇总，只写通过率及各标签通过率。
            tags_to_print (list[str] | None): 只打印这些标签的统计；为 None 时打印全部。
            tag_tree (TagTree | None): 标签树；与 tags_to_print 配合，非叶子节点会展开子树逐层打印。
            details_result_list (list[RunCaseResult] | None): 当 tags_to_print 或 tag_tree 非空时须传入，用于重算标签统计。
        """
        if tags_to_print is not None and details_result_list is not None:
            tags_stats = self._compute_tag_stats_with_tree(
                details_result_list,
                tags_to_print,
                tag_tree,
            )
            tags_str = self._format_tag_stats_hierarchical(
                tags_stats,
                tags_to_print,
                tag_tree,
            )
        else:
            tags_stats = tags_correct_number_and_rate
            tags_to_print_resolved = list(tags_stats.keys())
            tags_str = self._format_tag_stats_hierarchical(
                tags_stats,
                tags_to_print_resolved,
                None,
            )

        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(f"测试数据集名称列表：{dataset_names}\n")
            if epoch <= 1:
                f.write(f"测试用例总数：{total_case_num}\n")
                f.write(f"执行成功的测试用例数：{execution_success_num}\n")
                f.write(f"执行成功率：{execution_success_rate:.2%}\n")
                f.write(f"通过的测试用例数：{passed_case_num}\n")
                f.write(f"测试用例通过率：{pass_rate:.2%}\n")
                f.write("标签统计：\n")
                f.write(tags_str + "\n")
            else:
                f.write(
                    f"epoch：{epoch}（多轮重复跑批；以下不写用例次数类汇总，仅保留通过率）\n"
                )
                f.write(f"执行成功率：{execution_success_rate:.2%}\n")
                f.write(f"测试用例通过率：{pass_rate:.2%}\n")
                f.write("各标签统计：\n")
                f.write(tags_str + "\n")
            f.write("\n\n" + "+" * 160 + "\n\n")
            f.write(judge_result)

    async def _a_run_case_dialogues(
        self, a_case: TestCase
    ) -> tuple[str, list[dict], bool, str | None]:
        """
        只运行case内自动对话，返回给judge的历史和trace，以及执行是否成功和错误信息。
        """
        # ------------------------------------------------------------------
        # 长期模式 effective context：在此处完成「快照压 case」，不改动各 bot.create 内部的合并顺序。
        # 非长期模式：沿用原逻辑——按 case 自带的 collection_name / user_id（缺省则用 case_id）走 Volc。
        # ------------------------------------------------------------------
        if self.long_term_use:
            assert self._long_term_context_bundle is not None
            effective_ctx = merge_long_term_demo_bundle_over_case_context(
                a_case.context_config,
                self._long_term_context_bundle,
                forced_user_id=self.long_term_use_user_id,
            )
            test_user_id = self.long_term_use_user_id
        else:
            effective_ctx = dict(a_case.context_config)

        # 判断是否有火山 SID：以 effective_ctx 为准；长期快照里必带 demo 对齐的 collection_name。
        has_memory_collection = effective_ctx.get("collection_name") is not None
        if not self.long_term_use:
            if has_memory_collection:
                test_user_id = a_case.case_id
            elif effective_ctx.get("user_id") is None:
                test_user_id = a_case.case_id
            else:
                test_user_id = str(effective_ctx.get("user_id"))
            effective_ctx["user_id"] = test_user_id

        # 测记忆的case，必须有collection_name字段；长期模式下由 demo 快照保证集合存在。
        if has_memory_collection:
            assert effective_ctx.get("user_id") is not None, "user_id不能为空"
            _mem_lim = effective_ctx.get("memory_limit")
            if _mem_lim is None and self.long_term_use:
                _mem_lim = effective_ctx.get("profile_limit")
            # 非长期：与旧代码一致仅用 memory_limit 键，默认 MEMORY_LIMIT；
            # 长期：快照里常见 profile_limit 而无 memory_limit，与 consumer.config 对齐。
            store = VolcMemoryStore(
                collection_name=effective_ctx.get(
                    "collection_name", MEMORY_COLLECTION_NAME
                ),
                assistant_id=effective_ctx.get("assistant_id", TEST_ASSISTANT_ID),
                user_id=test_user_id,
                memory_types=effective_ctx.get("profile_types", MEMORY_TYPES),
                memory_limit=int(_mem_lim if _mem_lim is not None else MEMORY_LIMIT),
                event_type=effective_ctx.get("event_types", EVENT_MEMORY_TYPES),
                event_limit=int(effective_ctx.get("event_limit", EVENT_MEMORY_LIMIT)),
            )
            self.store = store
        else:
            # case（或快照）未配置火山 collection：不向假人挂载 Volc 侧写通路。
            self.store = None
        history_for_judge = ""
        execution_success = True
        execution_error = None
        # 旧逻辑会先写 ``a_case.context_config["user_id"]``；此处用 effective_ctx 整份拷贝回去，
        # 确保 FakePerson 首轮渲染拿到的 profile/car_info/user_id 与 Volc/store 分支一致，
        # 且不把仅在 bot 侧的 ``auto_test_suppress_bot_console`` 提前塞进 case。
        a_case.context_config = dict(effective_ctx)
        fake_driver = FakePerson(
            self.store,
            a_case,
            max_round=a_case.max_round,
            external_api_max_retries=self.external_api_max_retries,
            test_mode=self.test_mode,
        )
        base_context_config = dict(effective_ctx)
        if self._show_progress and not self._verbose:
            base_context_config["auto_test_suppress_bot_console"] = True
        bot_to_test = self.bot_to_test.create(base_context_config)
        case_traces = []
        for i, one_dialogue in enumerate(a_case.user_query_lists):
            start_query, mock_info, mock_time = self._normalize_dialogue_round(
                one_dialogue
            )
            dialogue_context_config = dict(base_context_config)
            dialogue_context_config.update(mock_info)
            dialogue_context_config["mock_time"] = mock_time
            if has_memory_collection:
                dialogue_context_config["user_id"] = test_user_id
            a_case.context_config = dialogue_context_config
            await self._a_retry_external_api(
                "bot_to_test.aupdate_context",
                lambda ctx=dialogue_context_config: bot_to_test.aupdate_context(ctx),
            )
            if self.give_score:
                try:
                    score, history, trace = await self.aauto_chat_test(
                        bot_to_test, fake_driver, start_query, a_case.max_round
                    )
                    if self._verbose:
                        _logger.info("第%s次对话,用户的评分是%s", i + 1, score)
                except Exception as e:
                    message = {
                        "role": "导演",
                        "content": f"第{i + 1}次对话,用户的评分和历史失败获取失败，错误信息是{e}",
                    }
                    _logger.error(
                        "第%s次对话,用户的评分和历史失败获取失败，错误信息是%s",
                        i + 1,
                        e,
                    )
                    execution_success = False
                    execution_error = str(e)
                    score = None
                    history = [message]
                    trace = None
            else:
                score = None
                try:
                    history, trace = await self.aauto_chat_test(
                        bot_to_test, fake_driver, start_query, a_case.max_round
                    )
                except Exception as e:
                    message = {
                        "role": "导演",
                        "content": f"第{i + 1}次对话,用户的历史记录获取失败，错误信息是{e}",
                    }
                    _logger.error(
                        "第%s次对话,用户的历史记录获取失败，错误信息是%s",
                        i + 1,
                        e,
                    )
                    execution_success = False
                    execution_error = str(e)
                    history = [message]
                    trace = None
            if self.upload_history_to_volc_memory:
                # 上传到火山记忆库
                # TODO history携带带system_prompt的history上传火山，并且取出配置的该多轮对话发生日期时间作为时间戳传给火山
                volc_messages = self._conver_history_dict_to_volc_messages(history)
                if self.store is not None:
                    st = self.store
                    await self._a_retry_external_api(
                        "VolcMemoryStore.aadd_history_to_memory",
                        lambda msgs=volc_messages, mt=mock_time, store=st: (
                            store.aadd_history_to_memory(
                                msgs,
                                wait_seconds=30,
                                mock_time=mt,
                            )
                        ),
                    )
            history_for_judge_ready = self._strip_first_system_message(history)
            history_for_judge += (
                f"第{i + 1}次对话的记录：\n"
                + "-" * 80
                + f"\n{format_stripped_history_for_judge(history_for_judge_ready).strip()}\n"
            )
            if trace:
                case_traces.append(trace)
            if self.pause_mode:
                input(
                    "\n当前处于调试模式，每运行一个case中的一个多轮对话后均会暂停，以便查看记忆的生成状况。在下一次多轮对话结束时可以查看上一次多轮对话的记忆。\n\n\n按任意键继续本case内下一次多轮对话..."
                )
        return history_for_judge, case_traces, execution_success, execution_error

    async def _a_judge_a_case(
        self,
        a_case: TestCase,
        history_for_judge: str,
        case_traces: list[dict],
        evidence: dict | str | None = None,
    ) -> RunCaseResult:
        """
        基于自动对话结果执行评测并生成RunCaseResult。

        judge 解析失败（重试耗尽）时不会抛出异常导致整个批量测试崩溃，
        而是返回 ``execution_success=False`` 的 RunCaseResult，跳过该 case 继续。

        Args:
            evidence: case 的车机日志证据（evidence.json dict/字符串），注入裁判 prompt 供核对。
        """
        judge = Judge(
            a_case,
            log_enabled=self._verbose,
            external_api_max_retries=self.external_api_max_retries,
            test_mode=self.test_mode,
        )
        if self._verbose:
            _logger.info("正在出具导演意见……")
        # case_traces 是 list[dict[int, dict]]（每个元素是一次多轮对话的所有轮次 trace），
        # 展开成扁平 list[dict] 供渲染器按轮渲染。
        flat_traces: list[dict] = []
        for seg in case_traces:
            if isinstance(seg, dict):
                # dict[int, dict]：轮次号 → trace dict
                flat_traces.extend(v for v in seg.values() if isinstance(v, dict))
            elif isinstance(seg, list):
                flat_traces.extend(item for item in seg if isinstance(item, dict))
        try:
            judge_result, judge_reason = await judge.ajudge(
                a_case,
                history_for_judge.strip(),
                case_traces=flat_traces,
                evidence=evidence,
            )
        except AssertionError as e:
            # judge 重试耗尽仍解析失败：标记执行失败并跳过，不崩溃
            _logger.error(f"case {a_case.case_id} judge 解析失败，跳过：{e}")
            return RunCaseResult(
                is_passed=False,
                reason=f"执行失败：judge解析失败 - {e}",
                tags=a_case.tags,
                id=str(a_case.id),
                case_id=a_case.case_id,
                nl_assertion=a_case.nl_assertion,
                history_for_judge=history_for_judge,
                case_traces=case_traces,
                execution_success=False,
                execution_error=f"judge解析失败: {e}",
            )
        return RunCaseResult(
            is_passed=judge_result,
            reason=judge_reason,
            tags=a_case.tags,
            id=str(a_case.id),
            case_id=a_case.case_id,
            nl_assertion=a_case.nl_assertion,
            history_for_judge=history_for_judge,
            case_traces=case_traces,
        )

    async def a_judge_a_case(
        self,
        a_case: TestCase,
        history_for_judge: str,
        case_traces: list[dict] | None = None,
        evidence: dict | str | None = None,
    ):
        """异步评判一个测试用例，返回是否通过和理由，供外部调用者自己决定怎么生成RunCaseResult

        judge 解析失败（重试耗尽）时返回 ``(False, "<失败原因>")`` 而非抛异常。

        Args:
            evidence: case 的车机日志证据（evidence.json dict/字符串），注入裁判 prompt 供核对。
        """
        judge = Judge(
            a_case,
            log_enabled=self._verbose,
            external_api_max_retries=self.external_api_max_retries,
            test_mode=self.test_mode,
        )
        if self._verbose:
            _logger.info("正在出具导演意见……")
        try:
            judge_result, judge_reason = await judge.ajudge(
                a_case,
                history_for_judge.strip(),
                case_traces=case_traces,
                evidence=evidence,
            )
        except AssertionError as e:
            _logger.error(f"case {a_case.case_id} judge 解析失败，跳过：{e}")
            return False, f"judge解析失败 - {e}"

        return judge_result, judge_reason

    async def _a_run_a_case(
        self, a_case: TestCase
    ) -> RunCaseResult:  # tuple[bool, str, list[str]] 该case的是否通过结果，原因，tags
        """
        异步运行一个测试用例
        Args:
            a_case (TestCase): 测试用例
        Returns:
            RunCaseResult: 判断结果，判断理由，tags，id，case_id，nl_assertion，history_for_judge，case_traces
        """
        (
            history_for_judge,
            case_traces,
            execution_success,
            execution_error,
        ) = await self._a_run_case_dialogues(a_case)
        if not execution_success:
            return RunCaseResult(
                is_passed=False,
                reason=f"执行失败：{execution_error}",
                tags=a_case.tags,
                id=str(a_case.id),
                case_id=a_case.case_id,
                nl_assertion=a_case.nl_assertion,
                history_for_judge=history_for_judge,
                case_traces=case_traces,
                execution_success=False,
                execution_error=execution_error,
            )
        return await self._a_judge_a_case(a_case, history_for_judge, case_traces)

    async def a_run_a_case(self, a_case: TestCase):
        """异步运行一个测试用例，返回history_for_judge和case_traces，供外部调用者自己决定是否评测或者怎么评测"""
        (
            history_for_judge,
            case_traces,
            execution_success,
            execution_error,
        ) = await self._a_run_case_dialogues(a_case)
        return history_for_judge, case_traces

    def run_full_auto_judge_test(
        self,
        concurrency_mode: bool = False,
        concurrency_num: int | None = None,
        pause_mode: bool = True,
        memory_reset_mode: bool = True,
        upload_history_to_volc_memory: bool = False,
        memory_reset_except_skills: bool = False,
        epoch: int = 1,
        long_term_use: bool = False,
        long_term_use_user_id: str | None = None,
        long_term_use_config: Mapping[str, Any] | None = None,
    ) -> RunAllCasesResult:
        """
        全自动评测一个chat bot与假人对话后的结果
        Args:
            concurrency_mode: 是否开启并发模式，默认False关闭
            concurrency_num: 并发数，默认不传的话为None，此时并发数等于case数
            memory_test_cases: 测试用例列表
            pause_mode: 是否开启调试模式，每轮对话后会暂停，以便在后台查看记忆的生成状况，默认True打开
            memory_reset_mode: 是否开启记忆重置模式，每次测试前会清空记忆，防止不同测试用例之间累积记忆的干扰，默认True打开
            memory_reset_except_skills: 仅当 memory_reset_mode 为 True 时生效；为 True 时通过 VolcMemoryStore.clean_memory
                （mode='by_type'，清空全部事件 + 仅删除指定 profile_types）保留 skills 画像。默认 False。
            epoch: 对数据集完整重复评测的轮数，正整数，默认 1。每轮开始前在 memory_reset_mode 下会重新执行记忆重置。
            long_term_use: 长期使用模式：全数据集与多 epoch 共用 ``long_term_use_user_id`` 作为火山 user_id，不再按 case_id 隔离；
                与 memory_reset_mode=True 互斥（同时传入将抛出 ``ValueError``）；且须关闭 ``concurrency_mode`` 或 ``concurrency_num=1``。
                启用时使用 ``agent_v1_eval_context.default_demo_bot_params`` 生成完整 Agent V1 / 火山记忆快照，并在本模块内以
                「快照压 case」方式覆盖每个 case 的同名配置后再 ``bot_to_test.create``。
            long_term_use_user_id: 仅当 long_term_use 时生效；未传时默认为 DEFAULT_MEMORY_USER_ID。
            long_term_use_config: 仅 ``long_term_use=True`` 时有效；对齐 ``agent_v1_eval_context.create_params_payload`` 的可选顶层补丁
                （如 ``collection_name`` / ``assistant_id`` / ``profile_types`` / ``system_prompt_profile_types`` /
                ``search_profile_types`` / ``profile_limit`` / ``event_types`` / ``event_limit`` 等），会与 demo 默认值
                merge 后再 ``_build_agent_v1_task_context``；可提供 ``task_config`` 嵌套 dict 对上述合并结果做递归补丁。
                非长期模式传入将抛出 ``ValueError``。
        Returns:
            RunAllCasesResult: 汇总后的最终测试结果
        """
        if epoch < 1:
            raise ValueError("epoch 必须为正整数")

        async def _collect_final_result() -> RunAllCasesResult:
            final_result: RunAllCasesResult | None = None
            async for item in self.arun_full_auto_judge_test(
                concurrency_mode=concurrency_mode,
                concurrency_num=concurrency_num,
                pause_mode=pause_mode,
                memory_reset_mode=memory_reset_mode,
                upload_history_to_volc_memory=upload_history_to_volc_memory,
                memory_reset_except_skills=memory_reset_except_skills,
                epoch=epoch,
                long_term_use=long_term_use,
                long_term_use_user_id=long_term_use_user_id,
                long_term_use_config=long_term_use_config,
            ):
                if isinstance(item, RunAllCasesResult):
                    final_result = item
            assert final_result is not None, "运行结束但未产出RunAllCasesResult"
            return final_result

        return asyncio.run(_collect_final_result())

    async def clean_case_memory(self, memory_reset_except_skills: bool = False) -> None:
        # 本脚本将 case_id 用作火山 user_id，以便用例之间记忆隔离。
        for a_case in self.memory_test_cases:
            if a_case.context_config.get("user_id") is None:
                a_case.context_config["user_id"] = a_case.case_id

        # 按 context_config 分组：同一 bot 下不同 case 可能指向不同记忆库，
        # 但 bot.aclean_memory_for_users 内部会自行解析 collection_name 等字段，
        # 此处按 case 逐个委托即可保证每个 case 的 context_config 都被正确传入。
        # 同一 context_config 的 case 合并 user_ids 一次批量清空，减少 API 调用次数。
        _groups: dict[int, tuple[list[str], dict]] = {}
        for a_case in self.memory_test_cases:
            _key = id(a_case.context_config)
            if _key not in _groups:
                _groups[_key] = ([], a_case.context_config)
            _groups[_key][0].append(a_case.case_id)
        for _user_ids, _ctx in _groups.values():
            await self.bot_to_test.aclean_memory_for_users(
                _user_ids,
                context_config=_ctx,
                except_skills=memory_reset_except_skills,
            )

    async def arun_full_auto_judge_test(
        self,
        concurrency_mode: bool = False,
        concurrency_num: int | None = None,
        pause_mode: bool = True,
        memory_reset_mode: bool = True,
        upload_history_to_volc_memory: bool = False,
        memory_reset_except_skills: bool = False,
        epoch: int = 1,
        long_term_use: bool = False,
        long_term_use_user_id: str | None = None,
        long_term_use_config: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[RunCaseResult | RunAllCasesResult]:
        """
        全自动评测一个chat bot与假人对话后的结果
        Args:
            concurrency_mode: 是否开启并发模式，默认False关闭
            concurrency_num: 并发数，默认不传的话为None，此时并发数等于case数
            memory_test_cases: 测试用例列表
            pause_mode: 是否开启调试模式，每轮对话后会暂停，以便在后台查看记忆的生成状况，默认True打开
            memory_reset_mode: 是否开启记忆重置模式，每轮（epoch）开始前会清空记忆，防止不同测试用例之间累积记忆的干扰，默认True打开
            memory_reset_except_skills: 仅当 memory_reset_mode 为 True 时生效；为 True 时每次重置调用 VolcMemoryStore.clean_memory
                的 mode='by_type'：清空全部事件记忆，并按用例推导的 profile_types 批量删除画像（已排除 skills），从而保留 skills。默认 False。
            epoch: 对数据集完整重复评测的轮数，正整数，默认 1。
            long_term_use: 长期使用模式：所有 case（含多 epoch）共用同一 user_id（见 ``long_term_use_user_id``），不按 case_id 分隔记忆；
                与 memory_reset_mode=True 互斥（同时传入将抛出 ``ValueError``）；且须 ``concurrency_mode=False`` 或 ``concurrency_num=1``。
                启用时在每个 case 的 ``bot_to_test.create`` 之前，会用 demo_v1 完整快照压住 case.context_config。
            long_term_use_user_id: 仅当 long_term_use 时使用；省略时等价于 DEFAULT_MEMORY_USER_ID。
            long_term_use_config: 见 ``run_full_auto_judge_test`` 文档；仅在长期模式下有意义。
        Returns:
            AsyncIterator[RunCaseResult | RunAllCasesResult]:
                - 每跑完一个case，先yield对应的RunCaseResult
                - 全部 epoch 与全部 case 结束后，再yield最终的RunAllCasesResult
        """
        if epoch < 1:
            raise ValueError("epoch 必须为正整数")
        self.long_term_use = long_term_use
        self._long_term_context_bundle = None
        if long_term_use_config is not None and not long_term_use:
            raise ValueError(
                "long_term_use_config 仅在 long_term_use=True 时使用；当前 long_term_use=False。"
            )
        if long_term_use:
            if memory_reset_mode:
                raise ValueError(
                    "long_term_use=True 时不允许 memory_reset_mode=True（长期连用需跨 case/epoch 保留记忆）。"
                )
            resolved_uid = (long_term_use_user_id or DEFAULT_MEMORY_USER_ID).strip()
            if not resolved_uid:
                raise ValueError(
                    "long_term_use=True 时必须提供非空的 long_term_use_user_id（或使用默认 DEFAULT_MEMORY_USER_ID）。"
                )
            self.long_term_use_user_id = resolved_uid
            if concurrency_mode and concurrency_num != 1:
                raise ValueError(
                    "long_term_use=True 时须关闭 concurrency_mode，或传入 concurrency_num=1（共用 user_id 时不可多 case 并行）。"
                )
            self._long_term_context_bundle = build_long_term_demo_v1_context_bundle(
                resolved_uid,
                patches=dict(long_term_use_config) if long_term_use_config else None,
            )
        else:
            self.long_term_use_user_id = ""

        self.pause_mode = pause_mode
        self.memory_reset_mode = memory_reset_mode
        self.upload_history_to_volc_memory = upload_history_to_volc_memory

        base_case_num = len(self.memory_test_cases)
        all_details: list[RunCaseResult] = []
        combined_result = ""
        tags_merged: dict[str, TagResult] = {}
        total_passed_all = 0
        total_execution_success_all = 0
        total_evaluations = base_case_num * epoch
        # 全局累计计数器（跨 epoch 不重置，用于进度条全局维度）
        global_passed = 0
        global_exec_ok = 0

        with _AutoTestRunProgress(
            total=total_evaluations,
            epoch=epoch,
            enabled=self._show_progress,
            verbose=self._verbose,
            log_dialogue=self._log_dialogue,
            epoch_total=base_case_num,
        ) as run_progress:
            for ep in range(epoch):
                result = ""
                passed_case_num = 0
                execution_success_num = 0
                tags_correct_number_and_rate: dict[str, TagResult] = {}
                details_result_list: list[RunCaseResult] = []
                total_case_num = base_case_num

                run_progress.set_epoch(ep)

                if self.memory_reset_mode:
                    run_progress.set_status("正在清空火山记忆…")
                    await self.clean_case_memory(memory_reset_except_skills)
                    run_progress.set_epoch(ep)

                def _update_stats(run_case_result: RunCaseResult) -> None:
                    nonlocal \
                        passed_case_num, \
                        execution_success_num, \
                        result, \
                        tags_correct_number_and_rate
                    nonlocal global_passed, global_exec_ok
                    details_result_list.append(run_case_result)
                    if run_case_result.execution_success:
                        result += (
                            f"导演意见：\n测试用例:\n{run_case_result.case_id}\nid:\n{run_case_result.id}\n——的多次对话结果是:\n{run_case_result.history_for_judge}\n\n"
                            f"通过标准是:\n{nl_repr(run_case_result.nl_assertion).strip()}\n\n"
                            f"判断结果是{run_case_result.is_passed}\n理由是{run_case_result.reason}\n"
                            + "*" * 160
                            + "\n"
                        )
                    else:
                        result += (
                            f"【执行失败】\n测试用例:\n{run_case_result.case_id}\nid:\n{run_case_result.id}\n——执行失败，错误信息:\n{run_case_result.execution_error}\n"
                            + "*" * 160
                            + "\n"
                        )
                    if run_case_result.execution_success:
                        execution_success_num += 1
                        global_exec_ok += 1
                        if run_case_result.is_passed:
                            passed_case_num += 1
                            global_passed += 1
                    for a_tag in run_case_result.tags:
                        if a_tag not in tags_correct_number_and_rate:
                            tags_correct_number_and_rate[a_tag] = TagResult(
                                tag=a_tag,
                                tag_total=0,
                                execution_success_number=0,
                                execution_success_rate=0.0,
                                passed_number=0,
                                pass_rate=0.0,
                            )
                        tr = tags_correct_number_and_rate[a_tag]
                        tr.tag_total += 1
                        if run_case_result.execution_success:
                            tr.execution_success_number += 1
                            if run_case_result.is_passed:
                                tr.passed_number += 1
                        tr.execution_success_rate = (
                            tr.execution_success_number / tr.tag_total
                            if tr.tag_total
                            else 0.0
                        )
                        tr.pass_rate = (
                            tr.passed_number / tr.execution_success_number
                            if tr.execution_success_number
                            else 0.0
                        )

                if concurrency_mode:
                    if not concurrency_num:
                        concurrency_num = total_case_num
                    for i in range(0, total_case_num, concurrency_num):
                        batch = self.memory_test_cases[i : i + concurrency_num]
                        tasks = [
                            asyncio.create_task(self._a_run_a_case(test_case))
                            for test_case in batch
                        ]
                        for finished in asyncio.as_completed(tasks):
                            item = await finished
                            _update_stats(item)
                            run_progress.on_case_done(
                                passed=global_passed,
                                execution_success_count=global_exec_ok,
                                epoch_passed=passed_case_num,
                                epoch_execution_success_count=execution_success_num,
                            )
                            yield item
                else:
                    for case in self.memory_test_cases:
                        item = await self._a_run_a_case(case)
                        _update_stats(item)
                        run_progress.on_case_done(
                            passed=global_passed,
                            execution_success_count=global_exec_ok,
                            epoch_passed=passed_case_num,
                            epoch_execution_success_count=execution_success_num,
                        )
                        yield item

                sep = (
                    f"\n\n{'=' * 80}\n第 {ep + 1}/{epoch} 轮（共 {epoch} 轮）\n{'=' * 80}\n\n"
                    if epoch > 1 and ep > 0
                    else ""
                )
                combined_result += sep + result
                all_details.extend(details_result_list)
                total_passed_all += passed_case_num
                total_execution_success_all += execution_success_num

                for tag, tr in tags_correct_number_and_rate.items():
                    if tag not in tags_merged:
                        tags_merged[tag] = TagResult(
                            tag=tag,
                            tag_total=0,
                            execution_success_number=0,
                            execution_success_rate=0.0,
                            passed_number=0,
                            pass_rate=0.0,
                        )
                    mt = tags_merged[tag]
                    mt.tag_total += tr.tag_total
                    mt.execution_success_number += tr.execution_success_number
                    mt.passed_number += tr.passed_number
                    mt.execution_success_rate = (
                        mt.execution_success_number / mt.tag_total
                        if mt.tag_total
                        else 0.0
                    )
                    mt.pass_rate = (
                        mt.passed_number / mt.execution_success_number
                        if mt.execution_success_number
                        else 0.0
                    )

        final_pass_rate = (
            total_passed_all / total_execution_success_all
            if total_execution_success_all
            else 0.0
        )
        final_execution_success_rate = (
            total_execution_success_all / total_evaluations
            if total_evaluations
            else 0.0
        )

        if self._verbose:
            if epoch <= 1:
                _logger.info(
                    "测试用例总数是%s，执行成功数是%s，执行成功率是%s，通过数是%s，通过率是————————%s\n以下为各标签下case的正确率：\n",
                    total_evaluations,
                    total_execution_success_all,
                    f"{final_execution_success_rate:.2%}",
                    total_passed_all,
                    final_pass_rate,
                )
            else:
                _logger.info(
                    "共 %s 轮重复评测，累计评测次数 %s，执行成功 %s，执行成功率 %s，通过 %s，总通过率 %s\n各标签汇总通过率：\n",
                    epoch,
                    total_evaluations,
                    total_execution_success_all,
                    f"{final_execution_success_rate:.2%}",
                    total_passed_all,
                    f"{final_pass_rate:.2%}",
                )
            tags_correct_number_and_rate_str = ""
            for tag, tag_result in tags_merged.items():
                if epoch <= 1:
                    tags_correct_number_and_rate_str += f"{tag}：总数:{tag_result.tag_total}，执行成功:{tag_result.execution_success_number}({tag_result.execution_success_rate:.2%})，通过:{tag_result.passed_number}({tag_result.pass_rate:.2%})\n"
                else:
                    tags_correct_number_and_rate_str += f"{tag}：执行成功率{tag_result.execution_success_rate:.2%}，通过率{tag_result.pass_rate:.2%}\n"
            if tags_correct_number_and_rate_str:
                _logger.info("%s", tags_correct_number_and_rate_str.rstrip("\n"))

        yield RunAllCasesResult(
            details_result_list=all_details,
            result=combined_result,
            total_case_num=total_evaluations,
            passed_case_num=total_passed_all,
            pass_rate=final_pass_rate,
            execution_success_num=total_execution_success_all,
            execution_success_rate=final_execution_success_rate,
            tags_correct_number_and_rate=tags_merged,
        )
