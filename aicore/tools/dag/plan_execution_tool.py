"""Plan执行工具 - 封装完整的Plan处理流程

将 _plan_generator_worker 和 PlanProcessor.process 合并为一个worker，
提供从结构化Plan到最终执行结果的完整流程。

异常处理遵循 AGENTS.md 第 3 条"无捕获·全记录·直抛出"：
- 本层不再 try-except，异常自然向上抛出由调用方处理
- 各阶段 Issue 通过 IssueReport 汇聚，
  从 PlanExecutionOutput.issue_report 单一出口抛出

策略提示词：PlanTool description 从 issue_strategy_prompt.md 读取，
指导 LLM 据 issue_report 反馈制定优化策略。

C1：_plan_execution_worker 已迁至 plan_worker.py（消除循环依赖），
本文件仅保留 PlanTool 工厂和类型定义。
max_node_retries 透传到 create_harness_worker 控制 harness 内部重试上限。
"""

import logging
from typing import Any, Optional

from aicore.tools import create_tool

from aicore.tools.dag.harness import create_harness_worker
from aicore.tools.dag.plan_generator import PlanGeneratorInput
from aicore.tools.dag.plan_worker import PlanExecutionWorker

logger = logging.getLogger(__name__)


def PlanTool(
    worker: Optional[PlanExecutionWorker] = None,
    *,
    timeout: float | None = None,
    max_node_retries: int = 1,
) -> Any:
    """PlanTool 工厂 — 组装 worker / timeout / max_node_retries

    max_node_retries 透传到 create_harness_worker，
    控制 harness 内部节点级 LLM 优化重试上限。
    默认 1（harness 内最多重试 1 次，耗尽后返回结果
    + retry_summary 交外层 React 处理）。
    默认 worker 由 create_harness_worker(max_node_retries) 产出。
    """
    if worker is None:
        worker = create_harness_worker(max_node_retries)

    # 占位符的路径表示中不显示索引；
    description = """
        将用户输入转换成结构化Plan，基于Plan获取任务目标所需的信息；
        Plan生成策略：一步一步将目标分解成最小可执行单元；
        """
    return create_tool(
        name="PlanTool",
        description=description,
        args_schema=PlanGeneratorInput,
        worker=worker,
        timeout=timeout,
    )
