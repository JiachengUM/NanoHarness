"""取消工具各版本的 Agent adapter 与统一测评入口。"""

from __future__ import annotations

from collections.abc import Sequence
import sys
from typing import Literal

from aicore.models.credentials import ModelName
from aicore.runtime.task import TaskManager
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.experiments.async_react_prompt import ASYNC_REACT_SYSTEM_PROMPT
from aicore.v2.experiments.react_agent_with_task_runner import (
    ReactAgentWithTaskRunner,
    create_react_agent_with_task_runner,
    render_active_task_context,
)
from aicore.v2.experiments.task_cancel_eval.cases import (
    CANCEL_TOOL_CASES,
    CancelToolCase,
    build_simulated_business_tools,
)
from aicore.v2.experiments.task_cancel_eval.runner import (
    EvaluationAgentBuilder,
    run_cancel_evaluation_cli,
)
from aicore.v2.experiments.task_cancel_tool import create_task_cancel_tool
from aicore.v2.experiments.task_cancel_tool_v1 import (
    create_task_cancel_tool as create_task_cancel_tool_v1,
)

__all__ = [
    "CancelToolVariant",
    "DEFAULT_MODEL",
    "V0_SYSTEM_PROMPT",
    "V1_SYSTEM_PROMPT",
    "build_task_cancel_agent",
    "build_task_cancel_tools",
    "build_v0_agent",
    "build_v0_system_prompt",
    "build_v0_tools",
    "build_v1_agent",
    "build_v1_system_prompt",
    "build_v1_tools",
    "create_cancel_agent_builder",
    "normalize_cancel_variant",
]

type CancelToolVariant = Literal["v0", "v1"]

DEFAULT_MODEL = ModelName.SEED_2_1_PRO_260628

_CANCEL_SECTION_START = "## 取消异步任务"
_CANCEL_SECTION_END = "## 语音回复风格"
_TASK_ID_MODIFY_TARGET_RULE = (
    "- 从历史业务工具调用及其占位回执中识别被修改的旧任务；"
    "无法唯一识别时先向用户澄清；"
)
_V1_MODIFY_TARGET_RULE = (
    "- 从当前活跃任务状态块中识别被修改的旧任务；无法唯一识别时先向用户澄清；"
)
_V1_CANCEL_SECTION = """## 取消异步任务

1. 每轮用户输入前可能注入以「当前活跃任务:」开头的状态块；未出现该状态块表示没有活跃异步任务。
   该状态块是判断能否取消任务的唯一实时依据，不要只根据历史占位回执判断。
2. 用户明确要求取消，或者正在修改同一个活跃异步任务时，可以调用 cancel_task。
   状态块中必须存在至少一个活跃异步任务；用户指定了目标时，该目标还必须能与状态块中的任务匹配。
   没有活跃异步任务时，不要调用 cancel_task。若对话中相关查询结果已经返回，直接回复
   「相关信息已经查到了，不需要取消」；若此前没有相关任务，回复「现在没有正在执行的任务，不需要取消」。
   这两种情况都不要回复「已取消」，也不要声称执行了取消操作。
3. 调用 cancel_task 时绝不要填写 task_id。target_hint 必须从状态块中原样摘取最能区分目标的
   tool_name 片段或参数值片段，不要翻译或改写；用户没有明确指向某一个任务时填 null。
4. 「取消导航」「停止播放」等也可能是导航、媒体或车控指令。若状态块中没有匹配的活跃异步任务，
   应使用对应业务工具，而不是 cancel_task。
5. 对用户明确发起的取消，根据 cancel_task 返回的「[已取消]」「[部分取消]」「[无需取消]」
   「[需要澄清]」「[无操作]」或「[取消失败]」简短回复；需要澄清时，询问用户要取消哪一个任务。
   「[无需取消]」或「[无操作]」绝不表示取消成功：若相关结果已经返回，说明信息已经查到、无需取消；
   否则说明当前没有正在执行的任务。不要回复「已取消」。
6. 对「修改任务」触发的取消，「[已取消]」「[部分取消]」「[无需取消]」或「[无操作]」只是中间步骤，
   不要把它作为最终回复；继续用合并后的完整参数提交新任务。收到新任务的占位回执后，再简短告知用户
   已按新条件重新查询。若返回「[需要澄清]」或「[取消失败]」，先澄清或说明失败，不要提交替代任务。
"""

_DEFAULT_CASE = CANCEL_TOOL_CASES["running_task_cancel"]


def build_v0_system_prompt() -> str:
    prompt = ASYNC_REACT_SYSTEM_PROMPT
    if "target_hint" in prompt or "绝不要填写 task_id" in prompt:
        raise ValueError("v0 prompt 仍包含旧取消工具参数约束")
    return prompt


def build_v1_system_prompt() -> str:
    before_cancel, start, after_start = ASYNC_REACT_SYSTEM_PROMPT.partition(
        _CANCEL_SECTION_START
    )
    _, end, after_cancel = after_start.partition(_CANCEL_SECTION_END)
    if not start or not end:
        raise ValueError("ASYNC_REACT_SYSTEM_PROMPT 缺少取消任务章节")

    before_cancel = before_cancel.replace(
        _TASK_ID_MODIFY_TARGET_RULE,
        _V1_MODIFY_TARGET_RULE,
    )
    prompt = (
        f"{before_cancel.rstrip()}\n\n"
        f"{_V1_CANCEL_SECTION.strip()}\n\n"
        f"{_CANCEL_SECTION_END}{after_cancel}"
    )
    if "target_hint" not in prompt or "当前活跃任务:" not in prompt:
        raise ValueError("v1 prompt 缺少 target_hint 取消约束")
    return prompt


V0_SYSTEM_PROMPT = build_v0_system_prompt()
V1_SYSTEM_PROMPT = build_v1_system_prompt()


def build_task_cancel_tools(
    task_manager: TaskManager | None = None,
    case: CancelToolCase = _DEFAULT_CASE,
) -> list[TaskToolProtocolGeneral]:
    task_manager = task_manager if task_manager is not None else TaskManager()
    return [
        *build_simulated_business_tools(
            task_manager=task_manager,
            case=case,
        ),
        create_task_cancel_tool(task_manager=task_manager),
    ]


def build_task_cancel_agent(
    task_manager: TaskManager,
    case: CancelToolCase,
    *,
    model: str = DEFAULT_MODEL,
) -> ReactAgentWithTaskRunner:
    return create_react_agent_with_task_runner(
        model=model,
        tools=build_task_cancel_tools(task_manager, case),
        system_prompt=ASYNC_REACT_SYSTEM_PROMPT,
        max_turns=5,
    )


def build_v1_tools(
    task_manager: TaskManager | None = None,
    case: CancelToolCase = _DEFAULT_CASE,
) -> list[TaskToolProtocolGeneral]:
    task_manager = task_manager if task_manager is not None else TaskManager()
    return [
        *build_simulated_business_tools(
            task_manager=task_manager,
            case=case,
        ),
        create_task_cancel_tool_v1(task_manager=task_manager),
    ]


def build_v1_agent(
    task_manager: TaskManager,
    case: CancelToolCase,
    *,
    model: str = DEFAULT_MODEL,
) -> ReactAgentWithTaskRunner:
    return create_react_agent_with_task_runner(
        model=model,
        tools=build_v1_tools(task_manager, case),
        system_prompt=V1_SYSTEM_PROMPT,
        max_turns=5,
        ambient_context_provider=lambda: render_active_task_context(
            task_manager
        ),
    )


def build_v0_tools(
    task_manager: TaskManager | None = None,
    case: CancelToolCase = _DEFAULT_CASE,
) -> list[TaskToolProtocolGeneral]:
    return build_task_cancel_tools(task_manager, case)


def build_v0_agent(
    task_manager: TaskManager,
    case: CancelToolCase,
    *,
    model: str = DEFAULT_MODEL,
) -> ReactAgentWithTaskRunner:
    return build_task_cancel_agent(
        task_manager,
        case,
        model=model,
    )


def normalize_cancel_variant(variant: str) -> CancelToolVariant:
    if variant in {"target_hint", "v1"}:
        return "v1"
    if variant == "v0":
        return "v0"
    raise ValueError(
        f"未知取消工具版本: {variant!r}. 可选: v0, v1"
    )


def create_cancel_agent_builder(
    variant: str,
    *,
    model: str = DEFAULT_MODEL,
) -> EvaluationAgentBuilder:
    normalized_variant = normalize_cancel_variant(variant)

    def build_agent(
        task_manager: TaskManager,
        case: CancelToolCase,
    ) -> ReactAgentWithTaskRunner:
        if normalized_variant == "v0":
            return build_v0_agent(
                task_manager,
                case,
                model=model,
            )
        return build_v1_agent(
            task_manager,
            case,
            model=model,
        )

    return build_agent


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print(
            "用法: python -m aicore.v2.experiments.task_cancel_eval.eval "
            "<v0|v1> [case_name|all]（target_hint 是 v1 的兼容别名）"
        )
        return 2

    raw_variant = arguments.pop(0)
    try:
        variant = normalize_cancel_variant(raw_variant)
    except ValueError as exc:
        print(exc)
        return 2

    agent_builder = create_cancel_agent_builder(variant)
    return run_cancel_evaluation_cli(
        agent_builder,
        program_name=(
            "-m aicore.v2.experiments.task_cancel_eval.eval "
            f"{raw_variant}"
        ),
        argv=arguments,
    )


if __name__ == "__main__":
    raise SystemExit(main())
