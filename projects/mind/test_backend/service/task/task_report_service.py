from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from typing import Any

from beanie import PydanticObjectId

from projects.mind.test_backend.db.init_beanie import init_db
from projects.mind.test_backend.mdb_models.task import (
    TaskRunDoc,
    TaskRunItemDoc,
    TaskRunItemEvalDoc,
    TaskDoc,
)
from projects.mind.complex_reasoning.task_mdb_models.case import ComplexReasoningCaseDoc
from aicore.models.credentials import create_client, AsyncArk, ModelName
from aicore.models.chat.streaming import astream


REPORT_WRITER_PROMPT = """
你是一个资深且专业的测试工程师，你需要根据本次任务运行中$total_case_num个测试用例的执行结果与模型评测结果，写一份markdown格式的综合测试报告。

总的测试结果如下：

$result

本次任务一共测试了$total_case_num个用例，其中通过了$passed_case_num个用例，通过率为$pass_rate。

请根据以上信息，写一份详细的测试报告。
测试报告的格式如下：
- 测试用例总数：$total_case_num
- 通过用例数：$passed_case_num
- 通过率：$pass_rate（但是换成保留2位小数的百分比）
- 测试用例标签通过率：
$tags_correct_number_and_rate
- 着重对所有未通过的用例的演绎结果进行聚类分析，一条条罗列出共性问题（由出现次数最多的问题到最少的问题，并且把问题对应的【用例编号】也对应着列出来，注意是用例编号，不是其他ID），并尝试对每个问题给出针对性的改进意见，以便协助被测助手改进问题。
- 同时还从工具调用准确度维度，上下文理解能力维度，推理能力维度分别给出分析结论

编写时你需要注意的事项：
- 测试报告的格式必须符合markdown格式。
- 测试报告的内容必须详细、准确、专业。
- 测试报告的语言必须采用中文。
- 仔细设计格式，字体，一定要保证容易易读性。
- 引用用例时请使用【用例编号：xxx】中的xxx作为用例标识，不要使用其他任何ID或编号。
- 一定要确保阅读这个报告的人觉得你的报告是非常全面，专业，详细，准确，易读的！

开始编写吧！
"""


async def fetch_task_run_data(task_run_id: PydanticObjectId) -> dict[str, Any]:
    """
    根据 task_run_id 拉取所有相关数据
    """
    task_run = await TaskRunDoc.get(task_run_id)
    if not task_run:
        raise ValueError(f"未找到 task_run: {task_run_id}")

    task = await TaskDoc.get(task_run.task_id)
    if not task:
        raise ValueError(f"未找到 task: {task_run.task_id}")

    items = await TaskRunItemDoc.find({"task_run_id": task_run_id}).to_list()

    item_ids = [item.id for item in items if item.id is not None]

    eval_docs = []
    if item_ids:
        eval_docs = await TaskRunItemEvalDoc.find(
            {"task_run_item_id": {"$in": item_ids}}
        ).to_list()
    eval_map = {str(doc.task_run_item_id): doc for doc in eval_docs}

    case_ids = [
        item.dataset_item_id for item in items if item.dataset_item_id is not None
    ]
    case_docs = []
    if case_ids:
        case_docs = await ComplexReasoningCaseDoc.find(
            {"_id": {"$in": case_ids}}
        ).to_list()
    case_map = {str(doc.id): doc for doc in case_docs}

    return {
        "task_run_id": str(task_run_id),
        "task_run": task_run,
        "task": task,
        "items": items,
        "eval_map": eval_map,
        "case_map": case_map,
    }


def calculate_statistics(data: dict[str, Any]) -> dict[str, Any]:
    """
    计算统计指标
    """
    items = data["items"]
    eval_map = data["eval_map"]
    case_map = data["case_map"]

    total = len(items)
    passed = 0
    failed_items = []

    tag_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "passed": 0}
    )

    result_lines = []

    for item in items:
        item_id = str(item.id)
        case_id_obj = str(item.dataset_item_id)
        case = case_map.get(case_id_obj)
        case_id = (
            case.case_id
            if case and hasattr(case, "case_id") and case.case_id
            else case_id_obj[-8:]
        )
        case_title = (
            case.title if case and hasattr(case, "title") and case.title else case_id
        )
        case_tags = case.tags if case and hasattr(case, "tags") else []

        eval_doc = eval_map.get(item_id)
        llm_eval = None
        is_pass = None
        eval_comment = ""
        eval_score = None

        if eval_doc and eval_doc.llm_evaluation:
            llm_eval = eval_doc.llm_evaluation
            is_pass = llm_eval.is_pass
            eval_comment = llm_eval.comment or ""
            eval_score = llm_eval.score

        if is_pass:
            passed += 1

        for tag in case_tags:
            tag_stats[tag]["total"] += 1
            if is_pass:
                tag_stats[tag]["passed"] += 1

        status_icon = "✅" if is_pass else ("❌" if is_pass is False else "⏳")
        status_text = (
            "通过" if is_pass else ("未通过" if is_pass is False else "未评测")
        )
        result_lines.append(
            f"【用例编号：{case_id}】\n"
            f"用例标题：{case_title}\n"
            f"执行状态：{item.status}\n"
            f"评测状态：{status_icon} {status_text}\n"
            f"标签：{', '.join(case_tags) if case_tags else '无'}\n"
            f"模型评分：{eval_score if eval_score is not None else 'N/A'}\n"
            f"评测意见：{eval_comment if eval_comment else '无'}\n"
        )

        if is_pass is False:
            failed_items.append(
                {
                    "case_id": case_id,
                    "case_id_obj": case_id_obj,
                    "case_title": case_title,
                    "tags": case_tags,
                    "comment": eval_comment,
                    "score": eval_score,
                }
            )

    pass_rate = passed / total if total > 0 else 0.0

    tag_result_lines = []
    for tag, stats in tag_stats.items():
        tag_total = stats["total"]
        tag_passed = stats["passed"]
        tag_rate = tag_passed / tag_total if tag_total > 0 else 0.0
        tag_result_lines.append(
            f"{tag}: 总数:{tag_total}，通过数:{tag_passed}，准确率:{tag_rate:.2%}"
        )

    return {
        "total": total,
        "passed": passed,
        "pass_rate": pass_rate,
        "failed_items": failed_items,
        "tag_stats": tag_stats,
        "tag_result_str": "\n".join(tag_result_lines),
        "result_str": "\n".join(result_lines),
    }


async def generate_report_with_llm(
    result_str: str,
    total_case_num: int,
    passed_case_num: int,
    pass_rate: float,
    tags_correct_number_and_rate: str,
) -> str:
    """
    调用大模型生成测试报告
    """
    client, model = create_client(ModelName.SEED_1_8_251228, AsyncArk)

    from string import Template

    system_prompt = Template(REPORT_WRITER_PROMPT).substitute(
        result=result_str,
        total_case_num=total_case_num,
        passed_case_num=passed_case_num,
        pass_rate=f"{pass_rate:.2%}",
        tags_correct_number_and_rate=tags_correct_number_and_rate,
    )

    print("正在调用大模型生成报告（流式）...", end="", flush=True)
    stream_res = await astream(
        "请生成测试报告",
        system_prompt,
        show_reasoning=False,
        client=client,
        model=model,
    )
    async for chunk in stream_res:
        print(".", end="", flush=True)
    print()

    report_content = stream_res.output
    assert report_content, "报告生成失败，返回内容为空"
    return report_content


def build_full_report(
    *,
    task: Any,
    task_run: Any,
    stats: dict[str, Any],
    ai_report_body: str,
) -> str:
    """
    组装完整的报告（头部元信息 + AI生成的正文）
    """
    lines = []
    lines.append("# 测试任务运行报告\n")
    lines.append(f"- **任务名称**: {task.name}")
    lines.append(f"- **任务描述**: {task.description or '无'}")
    lines.append(f"- **运行ID**: {task_run.id}")
    lines.append(f"- **运行状态**: {task_run.status}")
    lines.append(f"- **总用例数**: {stats['total']}")
    lines.append(f"- **通过用例数**: {stats['passed']}")
    lines.append(f"- **通过率**: {stats['pass_rate']:.2%}")
    lines.append("\n---\n")
    lines.append(ai_report_body)
    return "\n".join(lines)


async def generate_task_run_report(task_run_id: str | PydanticObjectId) -> str:
    """
    生成单个 task_run 的完整 Markdown 报告

    Args:
        task_run_id: 任务运行ID

    Returns:
        完整的 Markdown 报告内容
    """
    if isinstance(task_run_id, str):
        task_run_id = PydanticObjectId(task_run_id)

    data = await fetch_task_run_data(task_run_id)
    task = data["task"]
    task_run = data["task_run"]

    print(f"任务名称: {task.name}")
    print(f"运行状态: {task_run.status}")

    print("正在计算统计指标...")
    stats = calculate_statistics(data)

    print(f"总用例数: {stats['total']}")
    print(f"通过用例数: {stats['passed']}")
    print(f"通过率: {stats['pass_rate']:.2%}")

    print("正在调用大模型生成报告...")
    report_body = await generate_report_with_llm(
        result_str=stats["result_str"],
        total_case_num=stats["total"],
        passed_case_num=stats["passed"],
        pass_rate=stats["pass_rate"],
        tags_correct_number_and_rate=stats["tag_result_str"],
    )

    full_report = build_full_report(
        task=task,
        task_run=task_run,
        stats=stats,
        ai_report_body=report_body,
    )

    return full_report


async def generate_and_save_task_run_report(task_run_id: str | PydanticObjectId) -> str:
    """
    生成报告并保存到 task_run 的 metadata.ai_report 字段
    生成期间状态改为 reporting，生成成功改为 completed，失败恢复原状态

    Args:
        task_run_id: 任务运行ID

    Returns:
        完整的 Markdown 报告内容
    """
    if isinstance(task_run_id, str):
        task_run_id = PydanticObjectId(task_run_id)

    task_run = await TaskRunDoc.get(task_run_id)
    if not task_run:
        raise ValueError(f"未找到 task_run: {task_run_id}")

    from projects.mind.test_backend.enums.task import TaskRunStatus

    if task_run.status == TaskRunStatus.REPORTING:
        print(f"[generate_report] 报告正在生成中，跳过: {task_run_id}")
        return "报告正在生成中"

    original_status = task_run.status

    task_run.status = TaskRunStatus.REPORTING
    await task_run.save()

    try:
        report = await generate_task_run_report(str(task_run_id))

        if not task_run.metadata:
            task_run.metadata = {}
        task_run.metadata["ai_report"] = report
        task_run.status = TaskRunStatus.COMPLETED
        await task_run.save()
        print(f"报告已保存到 task_run.metadata.ai_report: {task_run_id}")

        return report
    except Exception as e:
        task_run.status = original_status
        await task_run.save()
        print(f"报告生成失败，恢复状态为 {original_status}: {task_run_id}")
        raise e


def _ensure_db_initialized():
    """
    确保数据库已初始化（脚本模式下用）
    """
    try:
        import asyncio

        asyncio.get_running_loop()
    except RuntimeError:
        pass
