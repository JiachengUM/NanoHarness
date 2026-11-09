"""DAG Mini — 公开 API。

精简自 dag_v3：砍掉 EvaluatorAgent / EvaluationResult / agent_loop / refine / skip_validation /
compute_cpl / events 流。

核心概念：
- ``ChatAgent`` — 最外层：v1 create_agent + TaskAgent tool
- ``Subagent`` — DAG 拓扑 + 同层 anyio 并行 + 派发 per-step Agent
- ``Agent`` — v1 create_agent 的薄壳（4 元组返回）
- ``DAG`` — Kahn 拓扑分层

调用链：
    user query → ChatAgent.run → LLM 拆解 → TaskAgent tool
                                            → Subagent.run(steps)
                                                → DAG.to_layers
                                                → anyio TaskGroup 并行 per-step Agent.run
                                                → 收集 step_records[*].final_answer
                                            → SubagentOutput → 回流 chat_agent v1 state
                                  → chat_agent LLM 看结果，汇总 → user
"""

from aicore.tools.dag_mini.agent import Agent, AgentStreamError
from aicore.tools.dag_mini.chat_agent import ChatAgent, create_chat_agent
from aicore.tools.dag_mini.dag import DAG
from aicore.tools.dag_mini.models import (
    StepCallback,
    StepGoal,
    StepRecord,
    SubagentOutput,
    TaskPlan,
    Trace,
)
from aicore.tools.dag_mini.prompt import (
    CHAT_SYSTEM_PROMPT,
    SUBAGENT_SYSTEM_PROMPT_SUFFIX,
    TASK_AGENT_DESCRIPTION,
    build_dep_answers_block,
    build_runtime_context_block,
    render_taskagent_description,
)
from aicore.tools.dag_mini.subagent import Subagent, create_taskagent


__all__ = [
    "Agent",
    "AgentStreamError",
    "CHAT_SYSTEM_PROMPT",
    "ChatAgent",
    "DAG",
    "SUBAGENT_SYSTEM_PROMPT_SUFFIX",
    "StepCallback",
    "StepGoal",
    "StepRecord",
    "Subagent",
    "SubagentOutput",
    "TASK_AGENT_DESCRIPTION",
    "TaskPlan",
    "Trace",
    "build_dep_answers_block",
    "build_runtime_context_block",
    "create_chat_agent",
    "create_taskagent",
    "render_taskagent_description",
]
