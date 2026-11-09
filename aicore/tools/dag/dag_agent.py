"""DAG Agent — 批量评测入口

本模块是 DAG 系统的主入口之一，职责：
1. 创建 LLM Agent（绑定 PlanTool）
2. 批量读取查询，逐条调用 Agent 执行
3. 从 Agent 对话历史中提取 system_msg / assistant_msg / tool_input / tool_output
4. 将 tool_output 还原为 PlanExecutionOutput 强类型对象
5. 将结果展开为扁平 dict 写入 CSV（trace / execution_result / safety_issue 按节点/序号展开为独立列）

典型用法：asyncio.run(run())
"""
import asyncio
import csv
import json
import logging
import os
from pathlib import Path
from datetime import datetime
from rich import print
from rich.pretty import pprint
from aicore.models.credentials import ModelName
from aicore.v1.experiments.agent import create_agent, Agent
from typing import Any, Dict, List, Tuple
from projects.mind.toolset.dag import get_prompt
from aicore.tools.dag.plan_execution_tool import PlanTool
from aicore.tools.dag.base_classes import PlanExecutionOutput
from aicore.tools.dag.operator_executors import setup_executors

logger = logging.getLogger(__name__)


def read_txt(path: str) -> str:
    """读取文本文件"""
    with open(path, "r", encoding='utf-8') as file:
        return file.read()


async def dump_agent_data(query: str, agent: Agent) -> Tuple[str, str, List[Dict[str, Any]], List[PlanExecutionOutput]]:
    """运行 Agent 并从对话历史中提取结构化数据

    Args:
        query: 用户查询文本
        agent: 已创建的 Agent 实例

    Returns:
        (system_msg, assistant_msg, tool_call_input, tool_call_output) 四元组
        - system_msg: 系统提示词
        - assistant_msg: 助手最终回复
        - tool_call_input: 工具调用入参列表 [{tool_name: arguments}, ...]
        - tool_call_output: 工具调用输出列表（尽量还原为 PlanExecutionOutput）
    """
    await agent.run_astream(query, event_listeners=[])
    _, state = await agent.dump()
    state_json = state.model_dump()

    system_msg = []
    assistant_msg = []
    tool_call_input: List[Dict[str, Any]] = []
    tool_call_output: List[Dict[str, Any]] = []

    for row in json.loads(state_json["model_api_state_dump"]["serialized"]):
        role = row.get("type", "")
        if role in ["system", "user"]:
            system_msg.append(row["text"])
        elif role == "assistant":
            tool_calls = row.get("tool_calls", [])
            if tool_calls:
                tool_call_input.append(tool_calls[0]["arguments"])
            elif row.get("text", ""):
                assistant_msg.append(row["text"])
        elif role == "tool_result":
            tool_call_output.append(row["results"][0]["output"])
    return "\n\n".join(system_msg), "\n\n".join(assistant_msg), tool_call_input, tool_call_output


def write_csv(results: List[Dict[str, Any]], output_path: str) -> str:
    """将每个 task 的执行结果展开写入 CSV，每 task 一行。

    列包含：基础信息 + 展开后的 trace 各列 + 展开后的 execution_result 各列
           + 展开后的 issue_report 各列。

    注：safety_issues 列保留作为输出列名，取值应从 issue_report.by_category(
    IssueCategory.SAFETY) 派生计数（在 _plan_execution_worker → dict 展开阶段填充）。
    """
    # 收集所有出现过的列，保持稳定顺序：基础列在前，其余按首次出现顺序追加
    base_cols = [
        "query", "system_msg", "assistant_msg", "tool_input_json",
        "success", "stage", "message", "goal", "steps", "dag_nodes", "safety_issues",
    ]
    seen = set(base_cols)
    extra_cols: List[str] = []
    for row in results:
        for k in row.keys():
            if k not in seen:
                seen.add(k)
                extra_cols.append(k)
    fieldnames = base_cols + extra_cols

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return output_path


async def process_query(data_item: Dict[str, Any], agent: Agent, max_retries: int = 2):
    """处理单个查询，解析失败时自动重试。

    Args:
        data_item: 包含 "query" 键的字典
        agent: Agent 实例
        max_retries: 最大重试次数（默认 2）

    Returns:
        更新后的 data_item，追加 system_msg / assistant_msg / tool_input / tool_output 字段
    """
    for attempt in range(max_retries + 1):
        try:
            system_msg, assistant_msg, tool_input, tool_output = await dump_agent_data(data_item["query"], agent)
            data_item["system_msg"] = system_msg
            data_item["assistant_msg"] = assistant_msg
            data_item["tool_input"] = tool_input
            data_item["tool_output"] = tool_output
            return data_item
        except AssertionError as e:
            # M15：保留重试逻辑，但用 logger.exception 记录完整堆栈
            if attempt < max_retries and "参数解析失败" in str(e):
                logger.exception("查询解析失败，第 %d 次重试: %s", attempt + 1, data_item["query"][:80])
                continue
            data_item["system_msg"] = ""
            data_item["assistant_msg"] = f"参数解析失败: {e}"
            data_item["tool_input"] = []
            data_item["tool_output"] = []
            return data_item
        except Exception:
            # M15：保留重试逻辑，但用 logger.exception 记录完整堆栈（含 traceback）
            if attempt < max_retries:
                logger.exception("执行异常，第 %d 次重试: %s", attempt + 1, data_item["query"][:80])
                continue
            raise


async def run() -> None:
    """批量评测主流程

    1. 初始化执行器（setup_executors）
    2. 读取 multi_step_query.txt 中的查询列表
    3. 创建 Agent（绑定 PlanTool，使用 SEED_2_0_PRO 模型）
    4. 并发执行所有查询（asyncio.gather）
    5. 打印结果摘要
    6. 写入 CSV 文件
    """
    setup_executors()
    plan_tool = PlanTool()
    base_dir = Path(__file__).resolve().parent
    input_file = base_dir / "multi_step_query.txt"
    data = read_txt(path=str(input_file)).split("\n")
    data = [{"query": row} for row in data if row.strip()][:1]
    agent = create_agent(model=ModelName.SEED_2_0_PRO_260215, tools=[plan_tool], system_prompt=get_prompt(), react_max_turns=3)
    tasks = [process_query(data_item, agent) for data_item in data]
    results = await asyncio.gather(*tasks)

    pprint(results, expand_all=True)

    # 写入 CSV：每个 task 一行，trace / execution_result 字段展开为独立列
    # ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    # csv_path = str(base_dir / f"dag_agent_output_{ts}.csv")
    # written = write_csv(results, csv_path)
    # print(f"\n=== CSV 已写入: {written} ===")


if __name__ == "__main__":
    asyncio.run(run())