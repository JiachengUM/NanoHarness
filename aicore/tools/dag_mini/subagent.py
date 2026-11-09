"""DAG Mini — Subagent 执行逻辑（精简版，砍掉所有 evaluator/agent_loop/refine）。

模块自下而上：
- Subagent: 拓扑分层 + anyio TaskGroup 并行调度 + 派发 per-step Agent.run 一次
- create_taskagent: Subagent → TaskAgent tool 包装

每 step 只跑一次 Agent.run()：拿 assistant 最终回复 + tool_calls，写 StepRecord，
sign done_event。失败不外抛，写 record.error 后继续，让 chat_agent 自己看结果。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

import anyio
from pydantic import BaseModel, ConfigDict, Field

from aicore.tools.dag_mini.agent import Agent, AgentStreamError
from aicore.tools.dag_mini.dag import DAG
from aicore.tools.dag_mini.models import (
    StepCallback,
    StepGoal,
    StepRecord,
    SubagentOutput,
)
from aicore.tools.dag_mini.prompt import (
    SUBAGENT_SYSTEM_PROMPT_SUFFIX,
    TASK_AGENT_DESCRIPTION,
    build_dep_answers_block,
    build_runtime_context_block,
    render_taskagent_description,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Subagent — 拓扑 + anyio TaskGroup 调度（单跑版，无 evaluator）
# ============================================================================


class Subagent(BaseModel):
    """拆解外置；本类只负责执行（拓扑 + anyio TaskGroup + 派发 per-step Agent.run）。

    字段：
        model: LLM 模型名
        max_concurrent_steps: 全局并发上限（anyio.CapacityLimiter）
        max_react_turns: 单 step 内 Agent ReAct 轮数
        system_prompt / tools / runtime_context: 透传给 per-step Agent
    """

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)
    model: str
    max_concurrent_steps: int = Field(default=4, ge=1)
    max_react_turns: int = Field(default=2, ge=1)
    system_prompt: str
    tools: list[Any]
    runtime_context: dict[str, str]

    async def run(
        self,
        step_goals: list[StepGoal],
        *,
        on_step: StepCallback | None = None,
    ) -> SubagentOutput:
        """调度：所有 step 并发 spawn 进 anyio TaskGroup；CapacityLimiter 约束 LLM 并发。
        依赖通过 per-step anyio.Event 解锁。单步失败隔离 → 写 record.error，不级联取消。
        """
        start = time.monotonic()
        dag = DAG(nodes=step_goals)
        layers = dag.to_layers()
        layer_idx = {s.step_id: i for i, layer in enumerate(layers) for s in layer}

        records: dict[str, StepRecord] = {}
        done_events = {s.step_id: anyio.Event() for s in step_goals}
        run_limiter = anyio.CapacityLimiter(self.max_concurrent_steps)

        _CANCEL = anyio.get_cancelled_exc_class()

        async def _runner(step: StepGoal) -> None:
            """try/finally 包裹：finally shield cleanup 永远完成，try 内 CancelledError 静默。
            每 step 只跑一次 Agent.run；失败写 record.error，不外抛。
            """
            record: StepRecord | None = None
            t0 = time.monotonic()
            try:
                # 1. 等所有依赖 + 读 dep answers
                for dep in step.depends_on:
                    await done_events[dep].wait()
                dep_answers = {dep: records[dep].final_answer for dep in step.depends_on if dep in records}

                # 2. 构造 record
                record = StepRecord(
                    step=step,
                    dep_records=[records[d] for d in step.depends_on if d in records],
                    layer_index=layer_idx[step.step_id],
                    runtime_context=dict(self.runtime_context),
                    dep_answers=dep_answers,
                )

                # 3. 跑 step
                try:
                    async with run_limiter:
                        sys_prompt = (self.system_prompt or "") + SUBAGENT_SYSTEM_PROMPT_SUFFIX
                        sys_prompt += build_dep_answers_block(dep_answers)
                        sys_prompt += build_runtime_context_block(self.runtime_context)
                        agent = Agent(
                            model=self.model,
                            system_prompt=sys_prompt,
                            max_turns=self.max_react_turns,
                            tools=list(self.tools),
                        )
                        out = await agent.run(step.goal)
                        record.assistant_msg = out.get("assistant", "")
                        record.tool_calls = out.get("tool_calls", [])
                except AgentStreamError as e:
                    record.error = str(e)
                    logger.warning("step=%s AgentStreamError: %s", step.step_id, e)
                except BaseException as e:
                    if not isinstance(e, _CANCEL):
                        record.error = f"{type(e).__name__}: {e}"
                        logger.exception("step=%s runner 异常", step.step_id)
                finally:
                    # 记录本 step 耗时（含等依赖 + agent 跑 + 异常处理）
                    record.execution_time_seconds = round(time.monotonic() - t0, 3)
            except BaseException as e:
                # 兜底：Phase 1（await done_events）被取消或任何漏网异常
                if not isinstance(e, _CANCEL):
                    logger.exception("runner 异常 step=%s", step.step_id)
            finally:
                # shield cleanup：即使被取消也完成（不被父级 cancel scope 打断）
                if record is not None:
                    with anyio.CancelScope(shield=True):
                        records[step.step_id] = record
                        done_events[step.step_id].set()
                        if on_step is not None:
                            try:
                                await on_step(record)
                            except Exception:
                                logger.exception("on_step 异常 step=%s", record.step.step_id)

        async with anyio.create_task_group() as tg:
            for step in step_goals:
                tg.start_soon(_runner, step)

        success_count = sum(1 for r in records.values() if r.success)
        elapsed = round(time.monotonic() - start, 3)
        logger.info(
            "Subagent.run 完成: %d/%d success, 耗时=%.2fs",
            success_count, len(records), elapsed,
        )
        return SubagentOutput(
            step_records=list(records.values()),
            nodes=step_goals,
            total_execution_time_seconds=elapsed,
        )


# ============================================================================
# create_taskagent — Subagent → TaskAgent tool 包装
# ============================================================================


def create_taskagent(
    subagent: Subagent,
    available_tools: list[Any],
    *,
    timeout: float = 60,
    on_subagent_output: Callable[[SubagentOutput], Awaitable[None]] | None = None
):
    """把 Subagent 包装成 TaskAgent tool。chat_agent 看到 description 自主拆解 + 调本 tool。

    worker 接 ``steps`` 直接（框架用 ``worker(**plan.model_dump())`` 形式调用，把
    TaskPlan 字段展平成 kwargs），不在签名里包 TaskPlan。

    on_subagent_output: 每次 worker 跑完 Subagent 后回调（拿结构化 SubagentOutput）。
    tool 框架对返回值跑 nl_repr 字符串化后会丢结构，所以这里 side-channel 一下。
    """
    from aicore.tools.dag_mini.models import TaskPlan
    from aicore.tools.factory import create_tool

    description = TASK_AGENT_DESCRIPTION.format(
        available_tools=render_taskagent_description(available_tools),
    )

    async def worker(steps: list) -> dict:
        output: SubagentOutput = await subagent.run(steps)
        # side-channel：把结构化 SubagentOutput 抛给上层（demo 展示 / 监控 / 持久化用）
        if on_subagent_output is not None:
            try:
                await on_subagent_output(output)
            except Exception:
                logger.exception("on_subagent_output 回调异常，不影响主流程")
        # tool 框架对 Pydantic BaseModel 默认走 repr 字符串化，对 dict 走 nl_repr 同样字符串化，
        # chat_agent LLM 看到的都是结构化文本。返 model_dump 后的 dict 让 LLM 拿到 JSON 风格字段。
        return [output.final_answer for output in output.step_records]

    return create_tool(
        name="TaskAgent",
        description=description,
        args_schema=TaskPlan,
        worker=worker,
        timeout=timeout,
    )
