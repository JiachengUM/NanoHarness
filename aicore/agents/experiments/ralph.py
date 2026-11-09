from __future__ import annotations

from typing import TypeAlias, Protocol, final, AsyncGenerator, Any, Literal, override

from pydantic import BaseModel, Field

from aicore.utils.nl_repr import nl_repr

from aicore.core.event import EventBase

from aicore.models.responses import ModelParams, Response, ainvoke_output_by_json

from aicore.tools.factory import TaskToolType


from aicore.events.react import ReActEventPrinter as _EventPrinterRaw, is_react_event
from aicore.events.task import TaskEventPrinter, is_task_event

from aicore.agents.react import (
    ReActFinishEvent,
    TaskToolDoneEvent,
    ToolCallStartEvent,
    ToolCallsDoneEvent,
    ReActEvent,
    TaskEvent,
    react_with_stream_tools,    
)
from aicore.agents.experiments.user_profile import UserProfile

__all__ = [
    # 核心架构
    "StructuredGoal",
    "CriterionCheck",
    "EvalResult",
    "ExecutorBase",
    "RalphExecuteEvent",
    "RalphEvalEvent",
    "RalphEvalFailEvent",
    "RalphFinishedEvent",
    "RalphEvent",
    "ralph_loop",

    # 缺省的具体实现
    "LMEvaluator",
    "ReActExecutor",
    "RalphReActEventPrinter",
]

class StructuredGoal(BaseModel):
    """结构化描述的目标"""
    description: str = Field(default=..., title="目标描述", description="用户的目标任务描述")

    criteria: list[str] = Field(default_factory=list, title="完成标准", description="用户的目标完成的标准")


class CriterionCheck(BaseModel):
    """单条 criterion 的核查结果。"""
    criterion: str = Field(default=..., title="条件", description="需要核查的条件")
    status: Literal["met", "missing", "unmet"] = Field(default=..., title="状态", description="条件核查状态")
    reason: str = Field(default=..., title="原因", description="判断依据或缺口说明")


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _split_goal_text(goal: str) -> list[str]:
    normalized = goal
    for punctuation in ("，", "。", "；", "、", "\n", "\r"):
        normalized = normalized.replace(punctuation, ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def _compile_goal_criteria(goal: GoalLike) -> list[str]:
    if isinstance(goal, StructuredGoal):
        base_criteria = [goal.description, *goal.criteria] if goal.criteria else [goal.description]
    else:
        base_criteria = _split_goal_text(goal)

    return _dedupe_preserve_order(base_criteria)


def _compute_eval_success(checks: list[CriterionCheck]) -> bool:
    return all(check.status == "met" for check in checks)


def _normalize_eval_result(
    result: EvalResult,
    *,
    expected_criteria: list[str] | None = None,
) -> EvalResult:
    if expected_criteria is not None:
        observed_criteria = [check.criterion for check in result.checks]
        if observed_criteria != expected_criteria:
            result.success = False
            result.reason = (
                "评估结果不完整或不匹配: "
                f"期望criteria={expected_criteria}, 实际criteria={observed_criteria}"
            )
            result.suggestion = "请为每条criteria按相同顺序输出一条checks，不要遗漏、重复或改写criteria。"
            return result

    if expected_criteria is None and len(result.checks) == 0:
        result.success = False
        result.reason = "评估结果不完整: 未返回任何checks"
        result.suggestion = "请为每条criteria输出一条checks，不要遗漏任何criteria。"
        return result

    result.success = _compute_eval_success(result.checks)
    if result.success:
        result.suggestion = None
    return result


# 同时支持结构化和非结构化的goal
GoalLike: TypeAlias = StructuredGoal | str

class EvalResult(BaseModel):
    """评估结果。"""
    success: bool = Field(default=..., description="是否成功")
    checks: list[CriterionCheck] = Field(default_factory=list, description="逐条条件核查结果")

    reason: str = Field(default=..., description="评估原因")
    """TODO: 这个字段将来会被结构化，跟goal.criteria相对应"""

    suggestion: str | None = Field(default=None, description="若评估失败，给执行器的下一步改进建议。要具体到缺失信息和建议的查询方向。")

    def __nl_repr__(self) -> str:
        lines = [f"success={self.success}"]
        if self.checks:
            lines.extend(
                f"{check.criterion}: {check.status} ({check.reason})"
                for check in self.checks
            )
        else:
            lines.append(f"reason: {self.reason}")

        if self.suggestion:
            lines.append(f"建议: {self.suggestion}")
        return "\n".join(lines)

class EvaluatorProtocol[R](Protocol):
    """
    评估器协议。
    TODO: 增加Trajectory作为输入，这样才能更精确的指出错误原因，提出改进建议。
    """
    async def __call__(self, goal: GoalLike, result: R, context: Any, traj: Any | None = None) -> EvalResult:...


class NotePad[R, T](BaseModel):
    """
    记事本。不同于Agent的State。
    TODO: 本质区别是什么？持久化？不是。
    """

    result: R | None = Field(default=None, description="运行结果")
    """任务执行结果可以为None，如果执行失败"""

    traj: T | None = Field(default=None, description="运行轨迹")
    
    eval_result: EvalResult | None = Field(default=None, description="当前运行结果的评估结果。")
    """任务结果的评估结果可以为None，如果评估失败或者未进行"""



class ExecutorBase[R, C, E, T]:
    """
    Ralph loop executor的基类。
    R: 任务执行结果(result)的类型。
    C: 上下文环境(context)信息的类型，只读不写。例如: 当前时间，用户信息等。
    E: 流式输出事件(event)的类型。
    T: 执行轨迹(Trajectory)的类型。
    """

    def __init__(
        self, 
        params: ModelParams, 
        context: C | None = None,
        guideline: str | None = None,
        ):
        self.params = params
        self.context = context
        self.guideline = guideline


    async def _build_context(self, goal: GoalLike, notepad: NotePad[R, T]) -> str:
        """构建上下文提示词。"""
        executor_goal = goal.description if isinstance(goal, StructuredGoal) else goal
        prompt = f"""你需要帮用户完成任务，描述如下:
{executor_goal}

你必须基于真实可验证的信息完成任务，不能把未查询到的属性当作已满足。
如果当前查询结果缺少某个关键条件对应的字段或证据，不能直接下结论，而是要继续查询补证。
当发现当前地点类型无法直接返回目标属性时，应主动切换查询维度或查询对象。例如：
- 找餐厅时缺少“是否有停车场”，应改查 `poi_type=停车场` 或与停车相关的地点/证据，再回到候选餐厅做交叉验证。
"""

        if self.context:
            prompt += f"\n当前上下文信息: \n{nl_repr(self.context)}\n"

        if notepad.result:
            prompt += f"\n上一轮的结果输出: \n{nl_repr(notepad.result)}\n"
            if notepad.traj:
                prompt += f"\n上一轮的执行轨迹: \n{nl_repr(notepad.traj)}\n"
            assert notepad.eval_result, "任务执行结果的评估结果不能为空"
            assert not notepad.eval_result.success, "上一轮结果评估必须是失败"
            prompt += f"\n对于上一轮结果的评估: \n{nl_repr(notepad.eval_result)}"
            prompt += "\n请下一轮务必修复所有 missing 和 unmet 的条件：missing 表示补证 / gather evidence，unmet 表示换候选或调整搜索方向，并按这些要求调整下一次工具调用。"

        if self.guideline:
            prompt += f"\n完成任务的过程中, 请遵守以下规则: \n{self.guideline}"
        return prompt

    async def _astream(self, prompt: str) -> AsyncGenerator[E, None]:
        """必须是无状态的。迭代结束后，能自动构建Trajectory对象。"""
        raise NotImplementedError


    @final
    async def __call__(self, goal: GoalLike, state: NotePad[R, T]) -> AsyncGenerator[E, None]:
        """单轮运行。"""
        prompt = await self._build_context(goal, state)

        async for event in self._astream(prompt):  # type: ignore   应该没问题，报错看起来像是个type checker的bug
            yield event

    def finish(self) -> tuple[R, T]:
        """其实现需要和_astream配合。"""
        raise NotImplementedError


class RalphExecuteEvent[R](EventBase):
    type: Literal["ralph.execute"] = Field(default="ralph.execute", init=False)  # type: ignore
    round: int = Field(default=..., description="轮次")
    result: R = Field(default=..., description="运行结果")

class RalphEvalEvent[R](EventBase):
    type: Literal["ralph.eval"] = Field(default="ralph.eval", init=False)  # type: ignore
    round: int = Field(default=..., description="轮次")
    result: EvalResult = Field(default=..., description="评估结果")

class RalphEvalFailEvent[R](EventBase):
    type: Literal["ralph.fail"] = Field(default="ralph.fail", init=False)  # type: ignore
    round: int = Field(default=..., description="轮次")
    result: R = Field(default=..., description="运行结果")
    reason: str = Field(default=..., description="失败原因")

class RalphFinishedEvent[R](EventBase):
    type: Literal["ralph.finished"] = Field(default="ralph.finished", init=False)  # type: ignore
    round: int = Field(default=..., description="轮次")
    result: R = Field(default=..., description="运行结果")
    eval_result: EvalResult = Field(default=..., description="评估结果")


type RalphEvent[R] = RalphExecuteEvent[R] | RalphEvalEvent[R] | RalphEvalFailEvent[R] | RalphFinishedEvent[R]


async def ralph_loop[R, C, E, T](
    goal: GoalLike, 
    executor: ExecutorBase[R, C, E, T], 
    evaluator: EvaluatorProtocol[R],
    notepad: NotePad[R, T] | None = None,
    *,
    max_turns: int,
) -> AsyncGenerator[E | RalphEvent[R], None]:
    assert max_turns > 1, "max_turns must be greater than 1"

    notepad = notepad or NotePad[R, T]()

    for n_round in range(max_turns):
        # 执行任务
        try:
            async for e in executor(goal, notepad):
                yield e

            notepad.result, notepad.traj = executor.finish()
            yield RalphExecuteEvent[R](round=n_round, result=notepad.result)
        except Exception as e:
            notepad.result = None
            notepad.eval_result = EvalResult(success=False, reason=f"任务执行失败: {str(e)}")
            yield RalphEvalEvent(round=n_round, result=notepad.eval_result)
            continue

        # 评测结果
        try:
            notepad.eval_result = await evaluator(goal, notepad.result, executor.context, notepad.traj)
            yield RalphEvalEvent(round=n_round, result=notepad.eval_result)
        except Exception as e:
            yield RalphEvalFailEvent[R](round=n_round, result=notepad.result, reason=f"任务评估失败: {str(e)}")
            # 致命错误，直接返回
            return
        
        if notepad.eval_result.success:
            break

    assert notepad.result, "任务执行结果不能为空"
    assert notepad.eval_result, "任务执行结果的评估结果不能为空"
    yield RalphFinishedEvent[R](round=n_round, result=notepad.result, eval_result=notepad.eval_result)


class LMEvaluator[R]:
    def __init__(self, params: ModelParams):
        self.params = params

    async def __call__(self, goal: GoalLike, result: R, context: Any, traj: Any | None = None) -> EvalResult:
        criteria = _compile_goal_criteria(goal)
        criteria_text = "\n".join(f"{idx}. {criterion}" for idx, criterion in enumerate(criteria, start=1))

        prompt = f"""你是一个裁判，判断AI助手是否成功完成了用户要求的任务。你不能进行任何没有数据依据的推测，必须严格遵守用户的任务要求完成条件。
如果任务失败，你必须给出足够具体、可执行的改进建议，帮助下一轮执行器调整查询策略，而不是只给抽象评价。

编译后的评估标准 criteria 如下，必须逐条输出对应的 checks 条目：
{criteria_text}

要求：
1. `checks` 必须与上面的 criteria 一一对应，顺序保持一致。
2. 每个 `check.status` 只能是 `met`、`missing` 或 `unmet`。
3. `met` 表示有直接证据满足该条件。
4. `missing` 表示当前没有足够证据判断。
5. `unmet` 表示当前已有明确反证。
6. `success` 由 checks 决定，不要只根据整体印象判断。

用户原始任务如下:
{nl_repr(goal)}"""

        if context is not None:
            prompt += f"\n当前上下文信息: \n{nl_repr(context)}\n"

        if traj is not None:
            prompt += f"\nAI助手上一轮的执行轨迹如下: \n{nl_repr(traj)}\n"

        prompt += f"""AI助手的回答如下: 
{nl_repr(result)}

请输出结构化评估结果：
1. `success` 只有在所有要求都被明确满足且有数据依据时才为 true。
2. `reason` 需要明确指出哪些条件已满足、哪些条件未被验证或未满足。
3. `suggestion` 在失败时必须可执行，最好直接指出下一轮应如何调整查询方向、补查什么字段、是否要切换 `poi_type` 或搜索对象；成功时可留空。
"""

        eval_res, _ = await ainvoke_output_by_json(
            prompt, 
            client=self.params.client, 
            model=self.params.model, 
            output_type=EvalResult
            )

        return _normalize_eval_result(eval_res, expected_criteria=criteria)


class ReActTrajectory(BaseModel):
    """通用的react执行轨迹"""
    response: Response

    prompt: str = Field(default=..., description="提示词")
    """注意没有系统和用户提示词之分。"""

    events: list[ReActEvent]

    def __nl_repr__(self) -> str:
        lines: list[str] = [f"本轮提示词:\n{self.prompt}"]

        tool_steps: list[str] = []
        for event in self.events:
            if isinstance(event, ToolCallStartEvent):
                tool_steps.append(f"调用工具 {event.name}，参数: {event.arguments}")
            elif isinstance(event, TaskToolDoneEvent):  # 对齐主线react TaskToolDone语义
                tool_steps.append(f"工具结果: {event.output.nl_repr()}")
            elif isinstance(event, ToolCallsDoneEvent): # 单轮全量工具执行结果列表
                tool_steps.append(f"工具结果: {nl_repr(event.tool_results)}")
            elif isinstance(event, ReActFinishEvent):
                tool_steps.append(f"最终回答: {event.response.raw_text}")   # type: ignore

        if tool_steps:
            lines.append("关键执行轨迹:\n" + "\n".join(tool_steps))

        return "\n\n".join(lines)

class ReActExecutor(ExecutorBase[str, UserProfile, ReActEvent | TaskEvent, ReActTrajectory]):
    """通用的react执行器"""
    def __init__(
        self, 
        params: ModelParams,
        user_profile: UserProfile | None = None,
        guideline: str | None = None,
        *,
        tools: list[TaskToolType] | None = None,
        max_turns: int = 3
    ) -> None:
        super().__init__(params, user_profile, guideline)
        
        self.tools = tools or []
        self.max_turns = max_turns
        self.events: list[ReActEvent] = []

        self.response: Response | None = None
        self.prompt: str | None = None
        
    @override
    async def _astream(self, prompt: str) -> AsyncGenerator[ReActEvent | TaskEvent, None]:  # type: ignore 应该没问题，报错看起来像是个type checker的bug
        self.events = []
        self.prompt = prompt
        async for event in react_with_stream_tools(
            prompt,
            None,
            client=self.params.client,
            model=self.params.model,
            tools=self.tools,
            max_turns=self.max_turns,
            params=self.params.params,
        ):
            if isinstance(event, ReActFinishEvent):
                self.response = event.response  # type: ignore

            if is_react_event(event):
                self.events.append(event)
            
            yield event

        assert self.response, "任务执行结果不能为空"

    def finish(self) -> tuple[str, ReActTrajectory]:
        assert self.response, "任务执行结果不能为空"
        assert self.prompt, "提示词不能为空"

        traj = ReActTrajectory(response=self.response, prompt=self.prompt, events=self.events)

        return self.response.raw_text, traj


class RalphReActEventPrinter[R](_EventPrinterRaw):
    def __init__(self) -> None:
        super().__init__()
        self.task_event_printer = TaskEventPrinter()

        self.clr_execute = "yellow"
        self.clr_eval_true = "green"
        self.clr_eval_false = "red"

    def __call__(self, event: RalphEvent[R] | ReActEvent | TaskEvent) -> None:
        match event:
            case RalphExecuteEvent():
                self.print(f"\n[{self.clr_execute}]Ralph.Execute R{event.round}[/]: {nl_repr(event.result)}")

            case RalphEvalEvent():
                self.print(f"\n[{self.clr_eval_true if event.result.success else self.clr_eval_false}]Ralph.Eval R{event.round}: {event.result.__nl_repr__()}[/]")
                
            case RalphEvalFailEvent():
                self.print(f"\n[{self.clr_eval_false}]❌ Ralph.EvalFail R{event.round}: {nl_repr(event.reason)}[/]")
                self.print(f"result: {nl_repr(event.result)}")

            case RalphFinishedEvent():
                clr = self.clr_eval_true if event.eval_result.success else self.clr_eval_false 
                self.print(f"\n[{clr}]✅ Ralph.Finished R{event.round}[/]: {nl_repr(event.result)}")
                self.print(f"[{clr}]eval:[/]{event.eval_result.__nl_repr__()}")
            
            case _:
                if is_react_event(event):
                    super().__call__(event)
                    return
                assert is_task_event(event), f"预期是ReActEvent/TaskEvent，实际是{type(event)}"
                self.task_event_printer(event)
