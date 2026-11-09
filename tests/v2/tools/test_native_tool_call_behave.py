import anyio
import builtins
import json
import os
import re
from typing import Awaitable, Callable, cast

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "manual/model experiment requiring LangChain and real model invocation; "
        "focused tool contract is covered by test_task_cancel_tool.py"
    )
)

pytest.importorskip("langchain", reason="manual/model experiment requires LangChain")
from langchain.messages import AIMessage, HumanMessage, SystemMessage

from aicore.runtime.task import TaskManager
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.experiments.task_cancel_tool import create_task_cancel_tool

from aicore.models.responses import astream, ainvoke, ModelParams, EasyInputMessageParam, system_msg, user_msg, assistant_msg
from aicore.models.credentials import ModelName

from aicore.agents._react_core import _response_to_react_event
from aicore.events.react import ToolCallStartEvent, ReActEventPrinter, ReActTextDoneEvent

from aicore.tools import base_tool_to_param
from projects.mind.mem.auto_test_script.langchain_models import doubao_model

print = builtins.print

model_params = ModelParams(model=ModelName.SEED_1_8_251228)


def _create_demo_cancel_tool() -> TaskToolProtocolGeneral:
    return create_task_cancel_tool(
        task_manager=TaskManager(),
    )

DZY_SYSTEM_PROMPT = """你是一个非常资深的管家兼司机，特别擅长在旅途中通过和车主对话，贴心地协助车主完成各种任务并让车主满意。

作为优秀的管家，你已经很优秀，但是在工作方式上我还是要再次提醒你切记遵循一下几点：
  - 你是个非常厉害的管家，所以能同时干多个事情，同时满足车主多个要求。
  - 之后你看到的任何工具，都是可以长期运行的，它们可以支持你同时干多个事情，所以你不需要担心执行某个工具会占用太久时间而无法及时响应车主的其他要求。
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

现在，仔细阅读至今你和用户的对话记录以及下面你笔记本上记录着的和车主相关的点点滴滴。最后作为资深管家，体面而恰当地回复车主。"""

DZY_MANUAL_TOOL_CALL_PROMPT_APPEND = """

为了方便系统稳定执行工具，请严格遵循下面的临时动作协议：
  - 仅当你确定需要调用某个工具时，才允许触发工具动作。
  - 一旦要触发动作，你必须只输出下面格式，且不输出任何额外文字：
    <tool_call>{"name":"<工具名>","arguments":{"<参数名>":"<参数值>"}}</tool_call>
  - name 必须填写你要调用的工具名，且要与可用工具名称严格一致。
  - arguments 必须是合法 JSON 对象，字段与取值需严格符合目标工具的参数定义。
  - 如果不需要触发工具动作，则正常回复，不要输出 <tool_call> 标签。"""

TOOL_CALL_PATTERN = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
COMPARE_REPEAT_TIMES = int(os.getenv("TASK_CANCEL_COMPARE_REPEAT_TIMES", "10"))
ALIGN_LANGCHAIN_WITH_MODEL_PARAMS = os.getenv("ALIGN_LANGCHAIN_WITH_MODEL_PARAMS", "0") == "1"
CONSISTENCY_SNAPSHOTS: dict[str, dict] = {}


def _extract_json_object(payload: str) -> dict | None:
    """尽量从 payload 中提取首个可解析的 JSON 对象，容忍尾部噪声。"""
    start = payload.find("{")
    if start < 0:
        return None

    # 逐步截断，兼容模型偶发多输出一个 } 或 >
    for end in range(len(payload), start + 1, -1):
        candidate = payload[start:end].strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _parse_tool_call_action(text: str) -> dict | None:
    """从模型文本输出中解析临时 tool call 协议。"""
    payload = ""
    match = TOOL_CALL_PATTERN.search(text)
    if match:
        payload = match.group(1).strip()
    else:
        # 兜底：如果闭合标签附近有异常字符，尝试按标签边界截取
        start_tag = "<tool_call>"
        end_tag = "</tool_call>"
        start_idx = text.find(start_tag)
        end_idx = text.find(end_tag, start_idx + len(start_tag)) if start_idx >= 0 else -1
        if start_idx < 0 or end_idx < 0:
            return None
        payload = text[start_idx + len(start_tag):end_idx].strip()

    payload = payload.strip("`")
    if payload.startswith("json"):
        payload = payload[4:].strip()

    obj = _extract_json_object(payload)
    if obj is None:
        return None

    if not isinstance(obj, dict):
        return None
    if not isinstance(obj.get("name"), str) or not obj["name"].strip():
        return None
    if not isinstance(obj.get("arguments"), dict):
        return None
    return obj


def _to_langchain_messages(messages: list[EasyInputMessageParam], query: str):
    lc_messages = []

    def _normalize_content(raw_content: object) -> str:
        if isinstance(raw_content, str):
            return raw_content
        return json.dumps(raw_content, ensure_ascii=False)

    for msg in messages:
        role = msg.get("role")
        content = _normalize_content(msg.get("content", ""))
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))

    lc_messages.append(HumanMessage(content=query))
    return lc_messages


def _snapshot_message_brief(messages: list[EasyInputMessageParam], query: str) -> dict:
    """构建统一的输入快照，方便对比不同调用路径的输入是否一致。"""
    return {
        "history_len": len(messages),
        "history_roles": [str(m.get("role", "")) for m in messages],
        "query": query,
        "query_len": len(query),
    }


def _build_langchain_invoke_kwargs() -> dict:
    """将 model_params 中可对齐的参数映射到 LangChain 调用参数。"""
    params = model_params.params
    invoke_kwargs: dict = {}
    if params.temperature is not None:
        invoke_kwargs["temperature"] = params.temperature
    if params.top_p is not None:
        invoke_kwargs["top_p"] = params.top_p
    if params.max_output_tokens is not None:
        # 大部分 LangChain chat model 适配层使用 max_tokens
        invoke_kwargs["max_tokens"] = params.max_output_tokens
    return invoke_kwargs


def _get_langchain_model_defaults() -> dict:
    """读取 LangChain 模型对象上的常见默认参数，便于和 Ark 默认行为对比。"""
    defaults: dict = {}
    for key in ("model_name", "temperature", "top_p", "max_tokens", "model_kwargs"):
        if hasattr(doubao_model, key):
            defaults[key] = getattr(doubao_model, key)
    return defaults


def _print_call_consistency_snapshot(
    mode: str,
    case_name: str,
    messages: list[EasyInputMessageParam],
    query: str,
    *,
    effective_invoke_kwargs: dict | None = None,
    provider_defaults: dict | None = None,
) -> None:
    """记录关键请求参数与输入摘要，供汇总阶段统一输出。"""
    params_dump = model_params.params.model_dump(exclude_none=True)
    CONSISTENCY_SNAPSHOTS[f"{mode}/{case_name}"] = {
        "mode": mode,
        "case": case_name,
        "model": model_params.model,
        "params": params_dump,
        "effective_invoke_kwargs": effective_invoke_kwargs or {},
        "provider_defaults": provider_defaults or {},
        "tools_enabled": False,
        "input_brief": _snapshot_message_brief(messages, query),
    }


def _print_consistency_snapshots_summary() -> None:
    if not CONSISTENCY_SNAPSHOTS:
        return
    print("\n================ 调用一致性快照（汇总） ================\n")
    for key in sorted(CONSISTENCY_SNAPSHOTS.keys()):
        print({"consistency_snapshot": CONSISTENCY_SNAPSHOTS[key]})


def _build_manual_tool_context(tool: TaskToolProtocolGeneral) -> str:
    """把可用工具定义注入到文本上下文，供 manual 模式决策。"""
    tool_name = tool.name
    tool_desc = tool.description
    tool_params: dict = {}
    schema_cls = getattr(tool, "args_schema", None)
    if schema_cls and hasattr(schema_cls, "model_json_schema"):
        tool_params = schema_cls.model_json_schema()
    tool_params_text = json.dumps(tool_params, ensure_ascii=False)
    return (
        "\n\n可用工具定义（仅可使用下列工具）：\n"
        f"- 工具名: {tool_name}\n"
        f"- 描述: {tool_desc}\n"
        f"- 参数Schema(JSON): {tool_params_text}\n"
    )

CASES_DZY: list[tuple[str, list[EasyInputMessageParam], str]] = [
    (
        "start_task_context",
        [
            system_msg(content=DZY_SYSTEM_PROMPT),
        ],
        "北京天气如何",
    ),
    (
        "cancel_task",
        [
            system_msg(content=DZY_SYSTEM_PROMPT),
            user_msg(content="北京天气如何"),
            assistant_msg(content="好的。正在为您查询北京的天气，请稍候。任务运行详情如下： task_id=123, name=`天气查询`。"),
        ],
        "算了别查了",
    ),
    (
        "joke_with_running_task_context",
        [
            system_msg(content=DZY_SYSTEM_PROMPT),
            user_msg(content="北京天气如何"),
            assistant_msg(content="好的。正在为您查询北京的天气，请稍候。任务运行详情如下： task_id=123, name=`天气查询`。"),
        ],
        "讲个笑话。",
    ),
]

async def _run_single_manual_langchain_chat_model_tool_call(case_index: int) -> bool:
    tool = _create_demo_cancel_tool()

    case_name, raw_messages, query = CASES_DZY[case_index]
    system_prompt_text = (
        DZY_SYSTEM_PROMPT
        + _build_manual_tool_context(tool)
        + DZY_MANUAL_TOOL_CALL_PROMPT_APPEND
    )
    messages = [system_msg(content=system_prompt_text), *raw_messages[1:]]

    print("消息历史")
    print(messages)
    print(f"Case: {case_name}, 用户查询: {query}")
    
    print("当前工具调用模式: manual_langchain_chat_model")
    print("是否启用手搓tool call提示词: True")
    aligned_kwargs = _build_langchain_invoke_kwargs()
    langchain_invoke_kwargs = aligned_kwargs if ALIGN_LANGCHAIN_WITH_MODEL_PARAMS else {}
    _print_call_consistency_snapshot(
        "manual_langchain_chat_model",
        case_name,
        messages,
        query,
        effective_invoke_kwargs=langchain_invoke_kwargs,
        provider_defaults={
            "align_with_model_params": ALIGN_LANGCHAIN_WITH_MODEL_PARAMS,
            "langchain_model_defaults": _get_langchain_model_defaults(),
            "candidate_aligned_kwargs_from_model_params": aligned_kwargs,
        },
    )
    manual_tool_called = False

    # manual_langchain_chat_model 模式：走 langchain chat model，不传官方 tools 参数
    lc_messages = _to_langchain_messages(messages, query)
    model_response = await doubao_model.ainvoke(lc_messages, **langchain_invoke_kwargs)
    manual_text = str(model_response.content)
    print(f"manual_langchain_chat_model 模式模型原始输出: {manual_text}")

    parsed_action = _parse_tool_call_action(manual_text)
    if parsed_action is not None:
        if parsed_action["name"] != tool.name:
            print(f"检测到动作但工具名不匹配，跳过执行: {parsed_action['name']}")
        else:
            args_dict = parsed_action["arguments"]
            result = await tool.simple_worker(**args_dict)()
            manual_tool_called = True
            print(f"文本协议工具调用结果: {result}")
    else:
        print("未检测到可执行的文本工具动作")

    print(f"manual_langchain_chat_model 模式是否触发工具: {manual_tool_called}")
    return manual_tool_called


async def _run_single_manual_ark_tool_call(case_index: int) -> bool:
    tool = _create_demo_cancel_tool()

    case_name, raw_messages, query = CASES_DZY[case_index]
    system_prompt_text = (
        DZY_SYSTEM_PROMPT
        + _build_manual_tool_context(tool)
        + DZY_MANUAL_TOOL_CALL_PROMPT_APPEND
    )
    messages = [system_msg(content=system_prompt_text), *raw_messages[1:]]

    print("消息历史")
    print(messages)
    print(f"Case: {case_name}, 用户查询: {query}")
    print("当前工具调用模式: manual_ark")
    print("是否启用手搓tool call提示词: True")
    _print_call_consistency_snapshot(
        "manual_ark",
        case_name,
        messages,
        query,
        effective_invoke_kwargs=model_params.params.model_dump(exclude_none=True),
        provider_defaults={
            "ark_model_params_defaults": model_params.params.model_dump(),
            "ark_model_params_non_none": model_params.params.model_dump(exclude_none=True),
        },
    )

    manual_tool_called = False
    # manual_ark 模式：走 aicore.models.responses 的 ark ainvoke，不传官方 tools 参数
    model_response = await ainvoke(
        query,
        cast(list, messages),
        client=model_params.client,
        model=model_params.model,
        params=model_params.params,
    )
    manual_text = model_response.raw_text
    print(f"manual_ark 模式模型原始输出: {manual_text}")

    parsed_action = _parse_tool_call_action(manual_text)
    if parsed_action is not None:
        if parsed_action["name"] != tool.name:
            print(f"检测到动作但工具名不匹配，跳过执行: {parsed_action['name']}")
        else:
            args_dict = parsed_action["arguments"]
            result = await tool.simple_worker(**args_dict)()
            manual_tool_called = True
            print(f"文本协议工具调用结果: {result}")
    else:
        print("未检测到可执行的文本工具动作")

    print(f"manual_ark 模式是否触发工具: {manual_tool_called}")
    return manual_tool_called


async def _run_single_native_tool_call(case_index: int) -> bool:
    tool = _create_demo_cancel_tool()
    case_name, raw_messages, query = CASES_DZY[case_index]
    system_prompt_text = DZY_SYSTEM_PROMPT
    messages = [system_msg(content=system_prompt_text), *raw_messages[1:]]

    print("消息历史")
    print(messages)
    print(f"Case: {case_name}, 用户查询: {query}")
    print("当前工具调用模式: native")
    print("是否启用手搓tool call提示词: False")

    native_tool_called = False
    final_stream_result = await astream(
        query,
        cast(list, messages),
        client=model_params.client,
        model=model_params.model,
        tools=[base_tool_to_param(tool)],
        params=model_params.params,
    )

    printer = ReActEventPrinter()
    async for raw_event in final_stream_result:
        event = _response_to_react_event(raw_event, 1)
        if event is None:
            continue

        match event:
            case ToolCallStartEvent():
                native_tool_called = True
                args_dict = json.loads(event.arguments)
                result = await tool.simple_worker(**args_dict)()
                print(f"原生工具调用结果: {result}")
            case ReActTextDoneEvent():
                pass

        try:
            printer(event)
        except UnicodeEncodeError:
            # Windows 终端在 gbk 编码下打印 emoji 可能失败，不影响统计逻辑
            builtins.print("[native] skip rich printer due to console encoding limitation")

    final_response = final_stream_result.response
    _ = final_response
    print(f"native 模式是否触发工具: {native_tool_called}")
    return native_tool_called


async def _run_repeated_compare(
    label: str,
    single_runner: Callable[[], Awaitable[bool]],
    repeat_times: int = COMPARE_REPEAT_TIMES,
) -> tuple[int, float]:
    results: list[bool] = [False] * repeat_times

    async def _worker(idx: int) -> None:
        print(f"\n---- 并发任务 {idx + 1}/{repeat_times}: mode={label} ----")
        results[idx] = bool(await single_runner())

    async with anyio.create_task_group() as tg:
        for i in range(repeat_times):
            tg.start_soon(_worker, i)

    trigger_count = sum(int(v) for v in results)

    ratio = trigger_count / repeat_times if repeat_times > 0 else 0.0
    print(
        f"\n[{label}] 并发工具触发统计: {trigger_count}/{repeat_times}, "
        f"触发占比={ratio:.2%}"
    )
    return trigger_count, ratio


async def test_task_cancel_tool():
    repeat_times = COMPARE_REPEAT_TIMES
    print(f"\n================ 连续对比测试开始，重复次数: {repeat_times} ================\n")

    print("\n================ 第一阶段：统计“算了别查了”触发任务取消工具占比 ================\n")
    manual_langchain_cancel_count, _ = await _run_repeated_compare(
        label="manual_langchain_chat_model/cancel_task",
        single_runner=lambda: _run_single_manual_langchain_chat_model_tool_call(1),
        repeat_times=repeat_times,
    )
    manual_ark_cancel_count, _ = await _run_repeated_compare(
        label="manual_ark/cancel_task",
        single_runner=lambda: _run_single_manual_ark_tool_call(1),
        repeat_times=repeat_times,
    )
    native_cancel_count, _ = await _run_repeated_compare(
        label="native/cancel_task",
        single_runner=lambda: _run_single_native_tool_call(1),
        repeat_times=repeat_times,
    )

    print("\n================ 第二阶段：在相同上下文下统计“讲个笑话”误触发占比 ================\n")
    manual_langchain_joke_count, manual_langchain_joke_ratio = await _run_repeated_compare(
        label="manual_langchain_chat_model/joke_with_running_task_context",
        single_runner=lambda: _run_single_manual_langchain_chat_model_tool_call(2),
        repeat_times=repeat_times,
    )
    manual_ark_joke_count, manual_ark_joke_ratio = await _run_repeated_compare(
        label="manual_ark/joke_with_running_task_context",
        single_runner=lambda: _run_single_manual_ark_tool_call(2),
        repeat_times=repeat_times,
    )
    native_joke_count, native_joke_ratio = await _run_repeated_compare(
        label="native/joke_with_running_task_context",
        single_runner=lambda: _run_single_native_tool_call(2),
        repeat_times=repeat_times,
    )

    print("\n================ 汇总对比结果 ================\n")
    print(
        f"[取消场景] manual_langchain_chat_model={manual_langchain_cancel_count}/{repeat_times} ({manual_langchain_cancel_count / repeat_times:.2%}), "
        f"manual_ark={manual_ark_cancel_count}/{repeat_times} ({manual_ark_cancel_count / repeat_times:.2%}), "
        f"native={native_cancel_count}/{repeat_times} ({native_cancel_count / repeat_times:.2%})"
    )
    print(
        f"[讲笑话场景] manual_langchain_chat_model={manual_langchain_joke_count}/{repeat_times} ({manual_langchain_joke_ratio:.2%}), "
        f"manual_ark={manual_ark_joke_count}/{repeat_times} ({manual_ark_joke_ratio:.2%}), "
        f"native={native_joke_count}/{repeat_times} ({native_joke_ratio:.2%})"
    )
    print(
        "[结论] 对比 manual_langchain_chat_model、manual_ark、native 三种模式下的触发与误触发占比。"
    )
    _print_consistency_snapshots_summary()


if __name__ == "__main__":
    anyio.run(test_task_cancel_tool)
