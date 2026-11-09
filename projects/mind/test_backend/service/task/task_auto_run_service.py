import asyncio
from enum import StrEnum
import time
from typing import Any
import uuid

import httpx

from beanie import PydanticObjectId
from pydantic import BaseModel

from projects.mind.complex_reasoning.task_data.input import DialogueRoundConfig
from projects.mind.complex_reasoning.task_mdb_models.case import ComplexReasoningCaseDoc
from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
    RunAllCasesResult,
    RunCaseResult,
    TagResult,
)
from projects.mind.test_backend.core.errors import ErrorCode, raise_app_error
from projects.mind.test_backend.enums.task import (
    AgentType,
    TaskRunItemStatus,
    TaskRunStatus,
)
from projects.mind.test_backend.mdb_models.task import (
    Evaluation,
    TaskDoc,
    TaskProgress,
    TaskRunDoc,
    TaskRunItem,
    TaskRunItemDoc,
    TaskRunItemEval,
    TaskRunItemEvalDoc,
    TaskRunItemMessage,
    TaskRunItemMessageDoc,
)
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.service.task.feishu_notify_service import (
    FeishuNotifyRecipient,
    notify_task_run_finished,
)

# from projects.mind.test_backend.service.task.base_agent_bot import BaseAgentBot
from projects.mind.test_backend.service.task.sgm_agen_bot import SGMAgentBot
from projects.mind.test_backend.service.task.agent_v1_bot import AgentV1Bot

TestAgentBotMap = {
    # AgentType.BASE_AGENT: BaseAgentBot,
    AgentType.SGM_AGENT: SGMAgentBot,
    AgentType.AGENT_V1: AgentV1Bot,
}

CONCURRENCY = 50  # 默认并发数，可以根据实际情况调整，或者通过任务的metadata进行配置
INTENT_URL = (
    "http://sgm-complex-dev.extour-inc.com/sgm-complex/v1/simple_complex_arbitration"
)


class ROLE(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class JudgeResultItem(BaseModel):
    dataset_item: ComplexReasoningCaseDoc
    judge_result: bool | None
    time: float | None = None


class RunAllResult(RunAllCasesResult):
    time_p50: float = 0.0
    time_avg: float = 0.0
    time_p90: float = 0.0
    time_p99: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_dataset_items(task: TaskDoc) -> list[ComplexReasoningCaseDoc]:
    print(f"获取数据集项，数据集ID: {task.dataset_id}")
    query: dict[str, Any] = {"dataset_id": task.dataset_id}
    if task.dataset_item_ids:
        query["_id"] = {"$in": task.dataset_item_ids}

    items = await mdb_service.get_list(ComplexReasoningCaseDoc, query=query, sort="_id")
    for item in items:
        item.context_config = item.context_config or {}
        item.context_config["task_config"] = task.config.model_dump()

    print(f"获取到 {len(items)} 个数据集项")
    return items


def _get_agent_type(task: TaskDoc) -> AgentType:
    meta = task.metadata if isinstance(task.metadata, dict) else {}
    agent_type = meta.get("agent_type", AgentType.AGENT_V1)
    return agent_type


def _build_auto_test(
    task: TaskDoc, dataset_items: list[ComplexReasoningCaseDoc]
) -> AutoTestAndRLDataGenerator:
    agent_type = _get_agent_type(task)
    bot_to_test = TestAgentBotMap.get(agent_type, AgentV1Bot)
    return AutoTestAndRLDataGenerator(bot_to_test=bot_to_test, memory_test_cases=dataset_items)  # type: ignore


def _get_concurrency(task: TaskDoc) -> int:
    meta = task.metadata if isinstance(task.metadata, dict) else {}
    return meta.get("concurrency", CONCURRENCY)


async def _save_trace_messages(
    task_run_item_id: PydanticObjectId, trace_data: dict
) -> None:
    session_id = trace_data.get("session_id", "")
    # 用户输入消息
    await mdb_service.create(
        model=TaskRunItemMessageDoc,
        data=TaskRunItemMessage(
            task_run_item_id=task_run_item_id,
            session_id=session_id,
            role=ROLE.USER,
            content=trace_data.get("query", ""),
            metadata=trace_data.get("metadata", {}),
        ),
    )
    # agent回复消息
    await mdb_service.create(
        model=TaskRunItemMessageDoc,
        data=TaskRunItemMessage(
            task_run_item_id=task_run_item_id,
            session_id=session_id,
            role=ROLE.ASSISTANT,
            content=trace_data.get("answer", ""),
            traces=trace_data.get("traces", []),
            metadata=trace_data.get("metadata", {}),
        ),
    )


async def _save_case_result(task_run: TaskRunDoc, item: RunCaseResult) -> None:
    system_prompt = None
    for case_trace in item.case_traces:
        for trace_data in case_trace.values():
            if trace_data.get("system_prompt"):
                system_prompt = trace_data["system_prompt"]
                break

    # 创建测试用例结果
    task_run_item = await mdb_service.create(
        model=TaskRunItemDoc,
        data=TaskRunItem(
            task_run_id=task_run.id,  # type: ignore
            dataset_item_id=PydanticObjectId(item.id),
            status=TaskRunItemStatus.COMPLETED,
            metadata={
                "history_for_judge": item.history_for_judge,
                "system_prompt": system_prompt,
            },
        ),
    )

    # 保存测试用例的对话消息记录及trace信息
    for case_trace in item.case_traces:
        for trace_data in case_trace.values():
            await _save_trace_messages(task_run_item.id, trace_data)  # type: ignore

    # 保存评估结果
    await mdb_service.create(
        model=TaskRunItemEvalDoc,
        data=TaskRunItemEval(
            task_run_item_id=task_run_item.id,  # type: ignore
            llm_evaluation=Evaluation(is_pass=item.is_passed, comment=item.reason),
        ),
    )
    print(f"完成[{item.case_id}]的测试，是否通过: {item.is_passed}")

    # TODO: 这里更新task_run的状态和进度信息


async def _update_task_run_progress(
    task_run: TaskRunDoc, total: int, judge_result: bool | None
) -> None:
    if not task_run.progress:
        task_run.progress = TaskProgress(
            total=total,
            completed=0,
            success=0,
            failed=0,
            percent=0.0,
        )
    task_run.progress.completed += 1
    task_run.progress.success += 1 if judge_result else 0
    task_run.progress.failed += 0 if judge_result else 1
    task_run.progress.percent = (
        task_run.progress.completed / task_run.progress.total * 100
    )
    await mdb_service.update(model=TaskRunDoc, doc_id=task_run.id, data=task_run)  # type: ignore


def _mark_task_run_complete(task_run: TaskRunDoc, item: RunAllResult) -> None:
    task_run.status = TaskRunStatus.COMPLETED
    metadata = item.model_dump()
    # 删除可能过大的字段，避免超过 MongoDB 文档大小限制
    del metadata["details_result_list"]
    del metadata["result"]
    task_run.metadata = metadata
    print("所有数据集项测试完成")


def _mark_task_run_failed(task_run: TaskRunDoc, error: str) -> None:
    task_run.status = TaskRunStatus.FAILED
    metadata = task_run.metadata if isinstance(task_run.metadata, dict) else {}
    metadata["error"] = error
    task_run.metadata = metadata


def _mark_task_run_item_failed(task_run_item: TaskRunItem, error: str) -> None:
    task_run_item.status = TaskRunItemStatus.FAILED
    metadata = (
        task_run_item.metadata if isinstance(task_run_item.metadata, dict) else {}
    )
    metadata["error"] = error
    task_run_item.metadata = metadata


async def _save_task_run_and_notify(
    task: TaskDoc,
    task_run: TaskRunDoc,
    notify_recipient: FeishuNotifyRecipient | None = None,
) -> TaskRunDoc | None:
    if not task_run.id:
        return task_run

    updated_task_run = await mdb_service.update(
        model=TaskRunDoc, doc_id=task_run.id, data=task_run
    )
    if updated_task_run:
        try:
            await notify_task_run_finished(
                task, updated_task_run, recipient=notify_recipient
            )
        except Exception as e:
            print(f"飞书通知发送失败: {e}")
    return updated_task_run


def _get_percentile_from_sorted(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0

    idx = int(percentile * (len(values) - 1))
    idx = max(0, min(idx, len(values) - 1))
    return values[idx]


def _get_all_case_results(statistics_items: list[JudgeResultItem]) -> RunAllResult:
    total_case_num = len(statistics_items)
    passed_case_num = 0
    tags_correct_number_and_rate: dict[str, TagResult] = {}

    for item in statistics_items:
        dataset_item = item.dataset_item
        judge_result = item.judge_result
        if judge_result:
            passed_case_num += 1
        for a_tag in dataset_item.tags or []:
            if a_tag not in tags_correct_number_and_rate:
                tags_correct_number_and_rate[a_tag] = TagResult(
                    tag=a_tag, tag_total=0, passed_number=0, pass_rate=0.0
                )
            if judge_result:
                tags_correct_number_and_rate[a_tag].passed_number += 1
            tags_correct_number_and_rate[a_tag].tag_total += 1
            tags_correct_number_and_rate[a_tag].pass_rate = (
                tags_correct_number_and_rate[a_tag].passed_number
                / tags_correct_number_and_rate[a_tag].tag_total
            )

    pass_rate = passed_case_num / total_case_num if total_case_num else 0.0

    valid_times = [item.time for item in statistics_items if item.time is not None]
    sorted_times = sorted(valid_times)
    if sorted_times:
        time_avg = sum(sorted_times) / len(sorted_times)
        time_p50 = _get_percentile_from_sorted(sorted_times, 0.50)
        time_p90 = _get_percentile_from_sorted(sorted_times, 0.90)
        time_p99 = _get_percentile_from_sorted(sorted_times, 0.99)
    else:
        time_avg = 0.0
        time_p50 = 0.0
        time_p90 = 0.0
        time_p99 = 0.0

    return RunAllResult(
        details_result_list=[],
        result="",
        total_case_num=total_case_num,
        passed_case_num=passed_case_num,
        pass_rate=pass_rate,
        tags_correct_number_and_rate=tags_correct_number_and_rate,
        time_avg=time_avg,
        time_p50=time_p50,
        time_p90=time_p90,
        time_p99=time_p99,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_task(
    task_id: PydanticObjectId,
    notify_recipient: FeishuNotifyRecipient | None = None,
):
    """执行任务的对外接口"""
    task = await mdb_service.get_by_id(TaskDoc, task_id)
    if not task or not task.id:
        return raise_app_error(ErrorCode.NOT_FOUND, 404, f"未找到任务: {task_id}")

    task_run = await mdb_service.create(
        model=TaskRunDoc,
        data=TaskRunDoc(task_id=task.id, status=TaskRunStatus.RUNNING),
    )

    dataset_items = await _get_dataset_items(task)
    if not dataset_items:
        _mark_task_run_failed(task_run, "数据集测试用例列表为空，无法执行测试")
        return await _save_task_run_and_notify(task, task_run, notify_recipient)

    try:
        auto_test = _build_auto_test(task, dataset_items)
        async for item in auto_test.arun_full_auto_judge_test(
            concurrency_mode=True,
            concurrency_num=_get_concurrency(task),
            pause_mode=False,
            memory_reset_mode=True,
            upload_history_to_volc_memory=False,
        ):
            if isinstance(item, RunCaseResult):
                await _save_case_result(task_run, item)
            elif isinstance(item, RunAllResult):
                _mark_task_run_complete(task_run, item)

    except Exception as e:
        print(f"执行任务 {task_id} 失败，错误信息: {str(e)}")
        _mark_task_run_failed(task_run, f"执行任务 {task_id} 失败，错误信息: {str(e)}")

    return await _save_task_run_and_notify(task, task_run, notify_recipient)


async def run_task_by_step(
    task_id: PydanticObjectId,
    notify_recipient: FeishuNotifyRecipient | None = None,
):
    task = await mdb_service.get_by_id(TaskDoc, task_id)
    if not task or not task.id:
        return raise_app_error(ErrorCode.NOT_FOUND, 404, f"未找到任务: {task_id}")

    dataset_items = await _get_dataset_items(task)
    total = len(dataset_items)
    agent_type = _get_agent_type(task)

    task_run = await mdb_service.create(
        model=TaskRunDoc,
        data=TaskRunDoc(
            task_id=task.id,
            status=TaskRunStatus.RUNNING,
            progress=TaskProgress(
                total=len(dataset_items), completed=0, success=0, failed=0, percent=0.0
            ),
        ),
    )

    if not dataset_items:
        _mark_task_run_failed(task_run, "数据集测试用例列表为空，无法执行测试")
        return await _save_task_run_and_notify(task, task_run, notify_recipient)

    auto_test = _build_auto_test(task, dataset_items)
    concurrency = _get_concurrency(task)

    try:
        safe_concurrency = max(1, int(concurrency))
        semaphore = asyncio.Semaphore(safe_concurrency)

        async def _run_one_case(item: ComplexReasoningCaseDoc) -> JudgeResultItem:
            async with semaphore:
                print(f"开始执行数据集项 {item.case_id} 的测试")
                judge_result = None
                time_used = None
                if agent_type == AgentType.INTENT_AGENT:
                    judge_result, _, time_used = await run_intent_case(task, task_run, item)
                else:
                    task_run_item, time_used = await run_a_case(auto_test, task_run.id, item)
                    print(f"数据集项 {item.case_id} 的测试执行完成，开始评判")
                    judge_result, _ = await judge_a_case(auto_test, task_run_item, item)

                # 更新task_run的状态和进度信息
                await _update_task_run_progress(
                    task_run, total=total, judge_result=judge_result
                )

                return JudgeResultItem(
                    dataset_item=item, judge_result=judge_result, time=time_used
                )

        statistics_items = await asyncio.gather(
            *(_run_one_case(item) for item in dataset_items)
        )

        all_case_results = _get_all_case_results(statistics_items)
        task_run.metadata = all_case_results.model_dump()
        task_run.status = TaskRunStatus.COMPLETED
        print("所有数据集项测试完成")
    except Exception as e:
        print(f"执行任务 {task_id} 失败，错误信息: {str(e)}")
        _mark_task_run_failed(task_run, f"执行任务 {task_id} 失败，错误信息: {str(e)}")

    return await _save_task_run_and_notify(task, task_run, notify_recipient)


async def run_a_case(
    auto_test: AutoTestAndRLDataGenerator,
    task_run_id: PydanticObjectId,
    item: ComplexReasoningCaseDoc,
) -> tuple[TaskRunItemDoc, float | None]:
    task_run_item_data = TaskRunItem(
        task_run_id=task_run_id,
        dataset_item_id=PydanticObjectId(item.id),
    )

    try:
        # TODO:根据配置决定是否清除记忆
        await auto_test.clean_case_memory(item)
        start = time.perf_counter()
        history_for_judge, case_traces, _, _ = await auto_test._a_run_case_dialogues(item)
        time_used = (time.perf_counter() - start) * 1000

        system_prompt = None
        for case_trace in case_traces:
            for trace_data in case_trace.values():
                if trace_data.get("system_prompt"):
                    system_prompt = trace_data["system_prompt"]
                    break

        # 创建测试用例结果
        task_run_item_data.status = TaskRunItemStatus.COMPLETED
        task_run_item_data.metadata = {
            "history_for_judge": history_for_judge,
            "system_prompt": system_prompt,
        }

        task_run_item = await mdb_service.create(
            model=TaskRunItemDoc,
            data=task_run_item_data,
        )

        # 保存测试用例的对话消息记录及trace信息
        for case_trace in case_traces:
            for trace_data in case_trace.values():
                await _save_trace_messages(task_run_item.id, trace_data)  # type: ignore

        return task_run_item, time_used

    except Exception as e:
        print(f"执行数据集项 {item.case_id} 失败，错误信息: {str(e)}")
        _mark_task_run_item_failed(
            task_run_item_data, f"执行数据集项 {item.case_id} 失败，错误信息: {str(e)}"
        )

        task_run_item = await mdb_service.create(
            model=TaskRunItemDoc,
            data=task_run_item_data,
        )
        return task_run_item, None


async def judge_a_case(
    auto_test: AutoTestAndRLDataGenerator,
    task_run_item: TaskRunItemDoc,
    item: ComplexReasoningCaseDoc,
):
    if (
        not task_run_item
        or not task_run_item.id
        or task_run_item.status != TaskRunItemStatus.COMPLETED
    ):
        return None, "测试用例未完成，无法评判"

    history_for_judge = (
        task_run_item.metadata.get("history_for_judge", "")
        if task_run_item.metadata
        else ""
    )
    judge_result, judge_reason = await auto_test.a_judge_a_case(item, history_for_judge)

    # 保存评估结果
    await mdb_service.create(
        model=TaskRunItemEvalDoc,
        data=TaskRunItemEval(
            task_run_item_id=task_run_item.id,
            llm_evaluation=Evaluation(is_pass=judge_result, comment=judge_reason),
        ),
    )
    print(f"完成[{item.case_id}]的测试，是否通过: {judge_result}")
    return judge_result, judge_reason


async def run_intent_case(
    task: TaskDoc, task_run: TaskRunDoc, item: ComplexReasoningCaseDoc
) -> tuple[bool, str, float]:
    url = task.metadata.get("url", INTENT_URL) if task.metadata else INTENT_URL
    simple = task.metadata.get("simple", []) if task.metadata else []
    complex = task.metadata.get("complex", []) if task.metadata else []
    prompt = task.metadata.get("prompt", "") if task.metadata else ""
    project = task.metadata.get("project", "") if task.metadata else ""

    if not task_run.id:
        raise ValueError("task_run.id 不能为空")

    if not item.user_query_lists:
        raise ValueError(f"测试用例 {item.case_id} 缺少有效的 user_query_lists")

    round_config = item.user_query_lists[0]
    messages = (
        round_config.user_query_list
        if isinstance(round_config, DialogueRoundConfig)
        else round_config
    )
    if not messages:
        raise ValueError(f"测试用例 {item.case_id} 缺少有效的 user_query_lists")

    # 取最后一条消息作为 query，前面的用户消息整理为 history。
    last_message = messages[-1]
    query = last_message.content or ""
    history = [{"q": msg.content, "a": ""} for msg in messages[:-1]]

    payload = {
        "query": query,
        "chat_id": uuid.uuid4().hex,
        "question_id": uuid.uuid4().hex,
        "history": history,
        "simple": simple,
        "complex": complex,
        "prompt": prompt,
        "project": project,
    }

    result, elapsed = await run_intent_api(url, payload)

    print(
        f"数据集项 {item.case_id} 的测试执行完成，开始评判，结果: {result}, 耗时: {elapsed:.2f} ms"
    )

    # 创建测试用例结果
    task_run_item_data = TaskRunItem(
        task_run_id=task_run.id,
        dataset_item_id=PydanticObjectId(item.id),
        status=TaskRunItemStatus.COMPLETED,
        metadata={
            "time": elapsed,
            "query": query,
            "history": history,
            "result": result,
        },
    )
    task_run_item = await mdb_service.create(
        model=TaskRunItemDoc,
        data=task_run_item_data,
    )

    if not task_run_item.id:
        raise ValueError("task_run_item.id 不能为空")

    is_pass = False
    comment = ""

    if item.code_assertion:
        is_pass = True if result == item.code_assertion.get("intent_type") else False
        comment = f"期望意图类型为{item.code_assertion.get('intent_type')}，实际意图类型为{result}"
    else:
        comment = "测试用例缺乏 code_assertion，无法判断是否通过"

    await mdb_service.create(
        model=TaskRunItemEvalDoc,
        data=TaskRunItemEval(
            task_run_item_id=task_run_item.id,
            llm_evaluation=Evaluation(is_pass=is_pass, comment=comment),
        ),
    )

    return is_pass, comment, elapsed


async def run_intent_api(url, payload):
    async with httpx.AsyncClient() as client:
        start = time.perf_counter()
        response = await client.post(url, json=payload)
        response.raise_for_status()
        result = response.json().get("data", "")
        elapsed = (time.perf_counter() - start) * 1000
        print(f"Result: {result}, Elapsed time: {elapsed:.2f} ms")

        return result, elapsed
