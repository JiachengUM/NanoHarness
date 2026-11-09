"""对比 SEED 2.0 模型在 Chat/Responses API 下的 tool_choice="none" 行为。

实验矩阵：
- 模型：SEED 2.0 Pro 260215、SEED 2.0 Mini 260428；
- 后端：Chat Completions、Responses；
- 输入：无工具意图、隐含工具意图、显式工具调用意图。

2026-08-26 单次联网实验结论：
1. 四组“模型 × 后端”组合都没有返回结构化 ``tool_calls``，说明
   ``tool_choice="none"`` 在协议输出层生效。
2. SEED 2.0 Pro 在两个后端遇到隐含或显式工具意图时，都会把
   ``<|FunctionCallBegin|>...<|FunctionCallEnd|>`` 作为普通 assistant 文本输出。
3. SEED 2.0 Mini 的 Chat 后端在隐含工具意图下直接编造实时天气，在显式
   工具意图下输出上述工具调用标记文本；Responses 后端在隐含工具意图下同样
   编造实时天气，在显式工具意图下改为普通文本追问。
4. 因此 ``tool_choice="none"`` 只能用于断言“没有协议级工具调用”，不能保证
   模型一定生成有用、忠实的自然语言回答。产品链路还应检查工具调用标记文本，
   并通过提示词或权威结果回灌约束模型不要编造外部实时信息。

以上是一次实测观察，不保证模型服务后续版本或重复采样得到完全相同的文本行为。
直接运行本文件可重新打印完整输入、输出及二维矩阵汇总，不依赖 pytest。
"""

from __future__ import annotations

from dataclasses import dataclass

from rich import print

from aicore.models.doubao_models import ModelName
from aicore.models.model_api import (
    ModelAPIBackend,
    ModelCallParams,
    create_model_api,
)

from tests.models.model_api._model_api_examples_common import (
    DummyWeatherTool,
    ModelExampleCase,
    iter_model_cases,
    print_case_header,
    print_exception,
    print_model_response,
    print_step,
    run_async,
    text_input,
)


SYSTEM_PROMPT = (
    "你是一个工具选择实验助手。普通知识问题直接回答；"
    "需要实时天气时必须调用 get_weather 工具，不能编造实时数据。"
)


@dataclass(frozen=True)
class ToolChoiceNoneCase:
    name: str
    query: str


CASES = [
    ToolChoiceNoneCase(
        name="用户输入没有工具请求意图",
        query="用一句话解释什么是全双工语音交互，控制在 30 字以内。",
    ),
    ToolChoiceNoneCase(
        name="用户输入隐含工具请求意图",
        query="上海现在的实时天气怎么样？请给出当前温度。",
    ),
    ToolChoiceNoneCase(
        name="用户输入显式要求调用工具",
        query="必须调用 get_weather 工具查询上海实时天气，不要直接回答天气内容。",
    ),
]

TOOL_CALL_TEXT_MARKERS = (
    "<|FunctionCallBegin|>",
    "<|FunctionCallEnd|>",
)

MODEL_NAMES = [
    ModelName.SEED_2_0_PRO_260215,
    ModelName.SEED_2_0_MINI_260428,
]

BACKENDS: list[ModelAPIBackend] = [
    "chat",
    "responses",
]


def tool_choice_none_params() -> ModelCallParams:
    """构造两个 backend 共用的逐轮参数。

    API 契约使用字符串 ``"none"`` 禁止本轮工具调用；Python ``None``
    表示不设置该参数，会保留后端默认的工具选择行为。
    """
    return ModelCallParams(
        temperature=0,
        max_output_tokens=256,
        thinking="disabled",
        extra={"tool_choice": "none"},
    )


def contains_tool_call_text(text: str | None) -> bool:
    return text is not None and any(
        marker in text for marker in TOOL_CALL_TEXT_MARKERS
    )


async def run_tool_choice_none_flow(
    case: ModelExampleCase,
) -> tuple[list[str], list[str]]:
    """打印一个 backend 下三种用户意图的完整输入输出轨迹。"""
    print_case_header('ModelAPI tool_choice="none"', case)

    api = create_model_api(backend=case.backend, model=case.model_name)
    weather_tool = DummyWeatherTool()
    params = tool_choice_none_params()
    failures: list[str] = []
    warnings: list[str] = []

    for index, scenario in enumerate(CASES, start=1):
        print_step(f"{index}. {scenario.name}")
        state = api.initial_state(system_prompt=SYSTEM_PROMPT)

        print("[bold]model input[/bold]")
        print(f"system: {SYSTEM_PROMPT}")
        print(f"user: {scenario.query}")
        print(
            "tools: "
            f"[{{'name': '{weather_tool.name}', "
            f"'description': '{weather_tool.description}', "
            f"'parameters': {weather_tool.args_schema.model_json_schema()}}}]"
        )
        print(f"params: {params.model_dump()}")

        response = await api.invoke(
            text_input(scenario.query),
            state=state,
            tools=[weather_tool],
            params=params,
        )

        print_model_response("model output", response)
        if response.tool_calls:
            message = (
                f"{case.label} / {scenario.name}: "
                f'tool_choice="none" 仍返回了 tool_calls'
            )
            failures.append(message)
            print(f"[bold red]FAIL[/bold red] {message}")
        elif contains_tool_call_text(response.text):
            message = (
                f"{case.label} / {scenario.name}: "
                "没有结构化 tool_calls，但 assistant text 包含工具调用标记"
            )
            warnings.append(message)
            print(f"[bold yellow]WARN[/bold yellow] {message}")
        else:
            print(
                '[bold green]PASS[/bold green] '
                '模型返回普通 assistant 输出，没有结构化 tool call。'
            )

    return failures, warnings


def main() -> None:
    """依次运行 Chat 和 Responses backend，不依赖 pytest。"""
    failures: list[str] = []
    warnings: list[str] = []

    for case in iter_model_cases(
        model_names=MODEL_NAMES,
        backends=BACKENDS,
    ):
        try:
            case_failures, case_warnings = run_async(
                run_tool_choice_none_flow(case)
            )
            failures.extend(case_failures)
            warnings.extend(case_warnings)
        except Exception as exc:
            message = f"tool_choice none script failed: {case.label}"
            failures.append(message)
            print_exception(message, exc)

    print("\n" + "=" * 80)
    if failures:
        print("[bold red]tool_choice=none verification failed[/bold red]")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    if warnings:
        print(
            '[bold yellow]tool_choice="none" protocol verification passed, '
            "but tool-call-like text was observed[/bold yellow]"
        )
        for warning in warnings:
            print(f"- {warning}")
        return

    print(
        '[bold green]tool_choice="none" verification passed for all backends '
        "and scenarios.[/bold green]"
    )


if __name__ == "__main__":
    main()
