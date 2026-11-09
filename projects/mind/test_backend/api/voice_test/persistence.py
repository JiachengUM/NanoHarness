"""DB 落库：task_run / task_run_item 持久化，供历史结果/详情页复用。

从 voice_test_api.py 拆分。包含：
- task / task_run 创建与状态流转（complete/failed/paused）
- case 结果保存（TaskRunItem + trace messages + eval）
- 进度更新
- 续跑时孤儿记录清理
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from beanie import PydanticObjectId

from projects.mind.complex_reasoning.task_mdb_models.case import (
    ComplexReasoningCaseDoc,
)
from projects.mind.complex_reasoning.task_mdb_models.dataset import (
    ComplexReasoningDatasetDoc,
)
from projects.mind.mem.auto_test_script.case_schema import TestCase
from projects.mind.test_backend.enums.task import TaskRunItemStatus, TaskRunStatus
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
from projects.voice_test.schemas.browser_schemas import JudgeStatus

if TYPE_CHECKING:
    from projects.mind.test_backend.api.voice_test.case_runner import VoiceCaseOutcome


# =============================================================================
# task / task_run 创建
# =============================================================================


def _build_voice_task_config() -> dict:
    """创建 Voice Test 专用 Task 时使用的最小 Agent 配置。

    浏览器语音测试实际执行不读取 Task.config；这里的 config 只是为了满足
    现有 TaskDoc schema，让 task_run 能复用历史结果、详情和导出接口。
    """
    return {
        "system_prompt": "Browser voice test placeholder task.",
        "run_params": {
            "model": "doubao-seed-1-8-251228",
            "max_turns": 5,
        },
        "tools_names": [],
        "history": [],
        "inherited_message_history": [],
    }


async def get_or_create_voice_task(
    dataset_id: PydanticObjectId,
    dataset_name: str,
) -> TaskDoc:
    """复用 task 体系时，为浏览器语音测试准备一个稳定的 Task 归属。"""
    task = await mdb_service.get_one(
        TaskDoc,
        query={
            "dataset_id": dataset_id,
            "metadata.voice_test_auto_task": True,
        },
    )
    if task:
        return task

    return await mdb_service.create(
        model=TaskDoc,
        data=TaskDoc(
            name=f"浏览器语音测试 - {dataset_name}",
            description="浏览器版本语音测试工具自动创建的任务，用于持久化 task_run 结果。",
            dataset_id=dataset_id,
            dataset_item_ids=[],
            config=_build_voice_task_config(),  # type: ignore[arg-type]
            metadata={
                "voice_test_auto_task": True,
                "source": "browser_voice_test",
            },
        ),
    )


async def create_voice_task_run(
    task: TaskDoc,
    *,
    total: int,
    enable_judge: bool,
    repeat_n: int = 1,
) -> TaskRunDoc:
    """每次批量语音测试创建一条独立 task_run。"""
    if task.id is None:
        raise ValueError("Voice Test Task 缺少 id，无法创建 task_run")
    return await mdb_service.create(
        model=TaskRunDoc,
        data=TaskRunDoc(
            task_id=task.id,
            status=TaskRunStatus.RUNNING,
            progress=TaskProgress(
                total=total,
                completed=0,
                success=0,
                failed=0,
                percent=0.0,
            ),
            metadata={
                "source": "browser_voice_test",
                "enable_judge": enable_judge,
                "repeat_n": repeat_n,
            },
        ),
    )


# =============================================================================
# case 结果保存
# =============================================================================


def _extract_system_prompt(case_traces: list[dict] | None) -> str | None:
    for case_trace in case_traces or []:
        for trace_data in case_trace.values():
            if isinstance(trace_data, dict) and trace_data.get("system_prompt"):
                return trace_data["system_prompt"]
    return None


async def _save_voice_trace_messages(
    task_run_item_id: PydanticObjectId,
    case_traces: list[dict] | None,
) -> None:
    """把 auto_test 产生的 trace 拆成 task_run_item_message，复用历史详情页。"""
    for case_trace in case_traces or []:
        for trace_data in case_trace.values():
            if not isinstance(trace_data, dict):
                continue
            session_id = trace_data.get("session_id", "")
            await mdb_service.create(
                model=TaskRunItemMessageDoc,
                data=TaskRunItemMessage(
                    task_run_item_id=task_run_item_id,
                    session_id=session_id,
                    role="user",
                    content=trace_data.get("query", ""),
                    metadata=trace_data.get("metadata", {}),
                ),
            )
            await mdb_service.create(
                model=TaskRunItemMessageDoc,
                data=TaskRunItemMessage(
                    task_run_item_id=task_run_item_id,
                    session_id=session_id,
                    role="assistant",
                    content=trace_data.get("answer", ""),
                    traces=trace_data.get("traces", []),
                    metadata=trace_data.get("metadata", {}),
                ),
            )


async def save_voice_case_result(
    task_run: TaskRunDoc,
    case: TestCase,
    outcome: VoiceCaseOutcome,
    *,
    repeat_index: int = 1,
    repeat_n: int = 1,
    slot: int = 0,
) -> PydanticObjectId | None:
    """保存一个浏览器语音 case 的执行结果、消息和可选 Judge 结果。返回 task_run_item id。

    slot：批跑中的全局序号（1-based），写入 metadata 供续跑时识别孤儿记录。
    """
    if task_run.id is None:
        raise ValueError("task_run 缺少 id，无法保存 case 结果")

    try:
        dataset_item_id = PydanticObjectId(str(case.id))
    except Exception as exc:
        raise ValueError(f"case {case.case_id!r} 缺少有效的数据库 id") from exc

    status = (
        TaskRunItemStatus.COMPLETED
        if outcome.execution_success
        else TaskRunItemStatus.FAILED
    )
    task_run_item = await mdb_service.create(
        model=TaskRunItemDoc,
        data=TaskRunItem(
            task_run_id=task_run.id,
            dataset_item_id=dataset_item_id,
            status=status,
            metadata={
                "source": "browser_voice_test",
                "history_for_judge": outcome.history_for_judge,
                "system_prompt": _extract_system_prompt(outcome.case_traces),
                "execution_error": outcome.execution_error,
                "judge_status": outcome.judge_status,
                "repeat_index": repeat_index,
                "repeat_n": repeat_n,
                "slot": slot,
                # 首轮响应耗时（ms）：仅首个 dialogue 的 SayHello 轮；None=超时/无ASR/文本链路
                "first_response_ms": outcome.first_response_ms,
            },
        ),
    )
    if task_run_item.id is None:
        raise ValueError("task_run_item 缺少 id，无法保存 trace")

    await _save_voice_trace_messages(task_run_item.id, outcome.case_traces)

    if outcome.judge_status in {JudgeStatus.COMPLETED, JudgeStatus.FAILED}:
        await mdb_service.create(
            model=TaskRunItemEvalDoc,
            data=TaskRunItemEval(
                task_run_item_id=task_run_item.id,
                llm_evaluation=Evaluation(
                    is_pass=outcome.is_passed,
                    comment=outcome.reason,
                ),
            ),
        )

    return task_run_item.id


# =============================================================================
# 进度更新
# =============================================================================


async def update_voice_task_run_progress(
    task_run: TaskRunDoc,
    *,
    total: int,
    outcome: VoiceCaseOutcome,
    enable_judge: bool,
    slot: int = 0,
    repeat_index: int = 1,
    case_id: str | None = None,
) -> None:
    """更新 task_run 进度；success 语义随是否评测而变化。"""
    if task_run.id is None:
        return
    if task_run.progress is None:
        task_run.progress = TaskProgress(
            total=total,
            completed=0,
            success=0,
            failed=0,
            percent=0.0,
        )

    task_run.progress.completed += 1
    is_success = outcome.counts_as_success(enable_judge=enable_judge)
    task_run.progress.success += 1 if is_success else 0
    task_run.progress.failed += 0 if is_success else 1
    task_run.progress.percent = task_run.progress.completed / total * 100
    await mdb_service.update(model=TaskRunDoc, doc_id=task_run.id, data=task_run)


# =============================================================================
# 状态流转：complete / failed / paused
# =============================================================================


def _compute_time_stats(times: list[float]) -> tuple[float, float, float, float]:
    """对首轮响应耗时列表算 avg/p50/p90/p99；空列表返回 4 个 0.0。"""
    if not times:
        return 0.0, 0.0, 0.0, 0.0
    sorted_times = sorted(times)
    avg = sum(sorted_times) / len(sorted_times)

    def _percentile(p: float) -> float:
        idx = int(p * (len(sorted_times) - 1))
        idx = max(0, min(idx, len(sorted_times) - 1))
        return sorted_times[idx]

    p50 = _percentile(0.50)
    p90 = _percentile(0.90)
    p99 = _percentile(0.99)
    return avg, p50, p90, p99


async def mark_voice_task_run_complete(
    task_run: TaskRunDoc,
    *,
    total: int,
    execution_success: int,
    enable_judge: bool,
    judged: int,
    passed: int,
    first_response_list: list[float] | None = None,
) -> None:
    if task_run.id is None:
        return
    times = first_response_list or []
    time_avg, time_p50, time_p90, time_p99 = _compute_time_stats(times)
    task_run.status = TaskRunStatus.COMPLETED
    task_run.metadata = {
        **(task_run.metadata or {}),
        "total_case_num": total,
        "execution_success_num": execution_success,
        "execution_success_rate": execution_success / total if total else 0.0,
        "enable_judge": enable_judge,
        "judged_case_num": judged,
        "passed_case_num": passed if enable_judge else None,
        "pass_rate": (passed / judged) if judged else None,
        # 首轮响应耗时统计（ms）：仅对非超时/有ASR的 case 计算
        "time_avg": time_avg,
        "time_p50": time_p50,
        "time_p90": time_p90,
        "time_p99": time_p99,
    }
    await mdb_service.update(model=TaskRunDoc, doc_id=task_run.id, data=task_run)


async def mark_voice_task_run_failed(task_run: TaskRunDoc, error: str) -> None:
    if task_run.id is None:
        return
    task_run.status = TaskRunStatus.FAILED
    task_run.metadata = {
        **(task_run.metadata or {}),
        "error": error,
    }
    await mdb_service.update(model=TaskRunDoc, doc_id=task_run.id, data=task_run)


async def mark_voice_task_run_paused(
    task_run: TaskRunDoc,
    reason: str,
    *,
    execution_success: int | None = None,
    judged: int | None = None,
    passed: int | None = None,
) -> None:
    """标记任务为暂停（可续跑）：用户暂停 / WS 断连。

    若传入统计值，则同步写入 metadata，供续跑时恢复累计统计。
    """
    if task_run.id is None:
        return
    task_run.status = TaskRunStatus.PAUSED
    new_meta = {
        **(task_run.metadata or {}),
        "paused_reason": reason,
    }
    # 续跑需要恢复累计统计：暂停时写入当前累计值
    if execution_success is not None:
        new_meta["execution_success_num"] = execution_success
    if judged is not None:
        new_meta["judged_case_num"] = judged
    if passed is not None:
        new_meta["passed_case_num"] = passed
    task_run.metadata = new_meta
    await mdb_service.update(model=TaskRunDoc, doc_id=task_run.id, data=task_run)


# =============================================================================
# 续跑：孤儿记录清理 + dataset 加载
# =============================================================================


async def cleanup_orphan_task_run_items(
    task_run_id: PydanticObjectId,
    resume_from: int = 0,
) -> int:
    """续跑前清理孤儿 TaskRunItemDoc：只删 slot > resume_from 的记录。

    场景：case 在 save_voice_case_result 之后、update_voice_task_run_progress 之前被打断，
    造成 TaskRunItemDoc 已写入但 progress 未更新。续跑时从 progress.completed 处继续，
    仅清理 slot > resume_from 的孤儿（未计入 progress 的），保留已正常完成的 item。
    返回删除的文档数。
    """
    result = await mdb_service.delete_by_query(
        model=TaskRunItemDoc,
        query={
            "task_run_id": task_run_id,
            "metadata.slot": {"$gt": resume_from},
        },
    )
    return result.deleted_count if result else 0


async def load_dataset_cases(
    dataset_id: str,
) -> tuple[PydanticObjectId, str, list[TestCase]]:
    """按数据集 ID 加载并冻结 case 快照，避免运行中受数据库修改影响。"""
    from pydantic import ValidationError

    try:
        dataset_oid = PydanticObjectId(dataset_id)
    except Exception as exc:
        raise ValueError("dataset_id 格式无效") from exc

    dataset = await mdb_service.get_by_id(
        ComplexReasoningDatasetDoc,
        doc_id=dataset_oid,
    )
    if dataset is None:
        raise ValueError("未找到指定数据集")

    docs = await mdb_service.get_list(
        ComplexReasoningCaseDoc,
        query={"dataset_id": dataset_oid},
        sort="_id",
    )
    if not docs:
        raise ValueError("该数据集没有可运行的测试用例")

    cases: list[TestCase] = []
    for doc in docs:
        payload = doc.model_dump()
        payload["id"] = str(doc.id)
        try:
            cases.append(TestCase.model_validate(payload))
        except ValidationError as exc:
            raise ValueError(f"数据集中的 case {doc.case_id!r} 无效: {exc}") from exc
    return dataset_oid, dataset.name, cases
