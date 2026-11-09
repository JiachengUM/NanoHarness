"""DAG Mini — 数据节点。

节点 = 状态，边 = 函数。Subagent.run 是 orchestrator。

精简：
- 没有 evaluator / refine / 事件流
- StepRecord 直接持有 assistant_msg / tool_calls / error
- SubagentOutput.step_records 透给 chat_agent
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field


StepCallback = Callable[["StepRecord"], Awaitable[None]]


class StepGoal(BaseModel):
    """DAG 节点：step_id / goal / depends_on。"""

    model_config = ConfigDict(extra="ignore")

    step_id: str = Field(description="唯一 ID（如 's1', 's2', ...）")
    goal: str = Field(description="该 step 要达成的目标")
    depends_on: list[str] = Field(
        default_factory=list,
        description="上游 step_id 列表",
    )


class Trace:
    """v1 state → 4 键 dict。dump() 不含 system；dump_all() 含 system。

    键 = ``system / user / assistant / tool_calls``；``tool_calls`` 是
    ``[{input: {name, arguments}, output}]`` 列表（input/output 对应 v1
    的 tool_call_input / tool_call_output 两要素）。
    """

    def __init__(self, state):
        self.state = state

    def _parse(self) -> dict:
        rows = json.loads(
            (self.state.model_dump().get("model_api_state_dump") or {}).get("serialized", "") or "[]"
        )
        sys, usr, asst, ins, outs = [], [], [], [], []
        for r in rows:
            t = r.get("type", "")
            if t == "system" and r.get("text"):
                sys.append(r["text"])
            elif t == "user" and r.get("text"):
                usr.append(r["text"])
            elif t == "assistant":
                for tc in r.get("tool_calls") or []:
                    ins.append({"name": tc.get("tool_name", ""), "arguments": tc.get("arguments") or {}})
                if not r.get("tool_calls") and r.get("text"):
                    asst.append(r["text"])
            elif t == "tool_result":
                for x in r.get("results") or []:
                    o = x.get("output", "")
                    if not isinstance(o, str):
                        outs.append(o)
                    else:
                        try:
                            outs.append(json.loads(o))
                        except (json.JSONDecodeError, TypeError):
                            outs.append(o)
        tcs = [{"input": i, **({"output": outs[k]} if k < len(outs) else {})} for k, i in enumerate(ins)]
        return {"system": "\n\n".join(sys), "user": "\n\n".join(usr), "assistant": "\n\n".join(asst), "tool_calls": tcs}

    def dump(self) -> dict:
        d = self._parse()
        d.pop("system", None)
        return d

    def dump_all(self) -> dict:
        return self._parse()


class TaskPlan(BaseModel):
    """taskagent tool 的入参：chat_agent 拆解后调 taskagent 时的入参 schema。"""

    model_config = ConfigDict(extra="ignore")

    steps: list[StepGoal] = Field(default_factory=list)


class StepRecord(BaseModel):
    """单 step 执行结果（无 evaluator 精简版）。

    字段：
        step: 原始 StepGoal
        layer_index: 在 DAG 拓扑分层中的层号
        runtime_context / dep_answers: 透传给 per-step Agent
        assistant_msg: agent 最终回复（final_answer 同义）
        tool_calls: 全部工具调用记录
        error: 失败信息（成功时为 None）
    """

    model_config = ConfigDict(extra="ignore")

    step: StepGoal
    dep_records: list["StepRecord"] = Field(default_factory=list)
    layer_index: int = 0
    runtime_context: dict[str, str] = Field(default_factory=dict)
    dep_answers: dict[str, str] = Field(default_factory=dict)
    assistant_msg: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    execution_time_seconds: float = 0.0

    @property
    def success(self) -> bool:
        return self.error is None

    @property
    def final_answer(self) -> str:
        """同 assistant_msg：chat_agent 收集时用。"""
        return self.assistant_msg


class SubagentOutput(BaseModel):
    """Subagent 输出：step_records + nodes。"""

    model_config = ConfigDict(extra="ignore")

    step_records: list[StepRecord] = Field(default_factory=list)
    nodes: list[StepGoal] = Field(default_factory=list)
    total_execution_time_seconds: float = 0.0

    @property
    def success(self) -> bool:
        return bool(self.nodes) and all(r.success for r in self.step_records)
