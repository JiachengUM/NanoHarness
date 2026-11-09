from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from projects.mind.complex_reasoning.task_mdb_models.case import (
    ComplexReasoningCaseDoc,
)
from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import Judge
from projects.mind.mem.auto_test_script.case_schema import TestCase
from projects.mind.test_backend.config import get_tos_config
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.mdb_models.task import (
    Evaluation,
    TaskRunItem,
    TaskRunItemDoc,
    TaskRunItemEvalDoc,
    TaskRunItemMessageDoc,
)
from projects.mind.test_backend.schemas.task.task import (
    TaskRunItemFilter,
    TaskRunItemOut,
)
from projects.mind.test_backend.utils.huoshan_tos import TosClient
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/task_run_item",
    tags=["Task Run Item Manager"],
)

logger = logging.getLogger(__name__)


@router.get("/list", response_model=ApiResponse[list[TaskRunItemOut]])
async def list(filters: TaskRunItemFilter = Depends()):
    docs = await mdb_service.get_list(
        model=TaskRunItemDoc,
        query=await filters.resolve_filters(),
        sort="created_time",
        exclude_fields=["answer", "answer_list", "metadata"],
    )
    out_list = to_out_list(docs, TaskRunItemOut)
    print(f"查询到 {len(out_list)} 个 TaskRunItem")

    if out_list:
        item_ids = [
            PydanticObjectId(item.id) for item in out_list if item.id is not None
        ]
        print("查询到的 item_ids:", item_ids)
        eval_docs = await mdb_service.get_list(
            model=TaskRunItemEvalDoc,
            query={"task_run_item_id": {"$in": item_ids}},
        )
        eval_map = {str(doc.task_run_item_id): doc for doc in eval_docs}

        for item in out_list:
            if item.id is not None:
                item.eval = eval_map.get(str(item.id))

    return ok(out_list)


@router.get("/page", response_model=ApiResponse[Page[TaskRunItemOut]])
async def page(
    filters: TaskRunItemFilter = Depends(),
    page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=TaskRunItemDoc,
        filters=await filters.resolve_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="created_time",
    )
    out_page = to_out_page(page_docs, TaskRunItemOut)

    if out_page.items:
        item_ids = [
            PydanticObjectId(item.id) for item in out_page.items if item.id is not None
        ]
        eval_docs = await mdb_service.get_list(
            model=TaskRunItemEvalDoc,
            query={"task_run_item_id": {"$in": item_ids}},
        )
        eval_map = {str(doc.task_run_item_id): doc for doc in eval_docs}

        for item in out_page.items:
            if item.id is not None:
                item.eval = eval_map.get(str(item.id))

    return ok(out_page)


@router.get("/{id}", response_model=ApiResponse[TaskRunItemOut])
async def get_by_id(id: PydanticObjectId):
    doc = await mdb_service.get_by_id(TaskRunItemDoc, id)
    if not doc:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    eval = await mdb_service.get_one(
        TaskRunItemEvalDoc, query={"task_run_item_id": doc.id}
    )
    messages = await mdb_service.get_list(
        TaskRunItemMessageDoc, query={"task_run_item_id": doc.id}, sort="created_time"
    )
    print(f"查询到评测结果: {eval}")
    print(f"查询到消息条数: {len(messages)}")

    out_doc = TaskRunItemOut.model_validate(doc)
    out_doc.eval = eval
    out_doc.messages = messages

    return ok(out_doc)


@router.post("", response_model=ApiResponse[TaskRunItemOut])
async def create(payload: TaskRunItem):
    doc = await mdb_service.create(model=TaskRunItemDoc, data=payload)
    return ok(to_out(doc, TaskRunItemOut), message="创建成功")


@router.put("/{id}", response_model=ApiResponse[TaskRunItemOut])
async def update(id: PydanticObjectId, payload: TaskRunItem):
    doc = await mdb_service.update(model=TaskRunItemDoc, doc_id=id, data=payload)
    return ok(to_out(doc, TaskRunItemOut), message="更新成功")


@router.delete("/{id}", response_model=ApiResponse)
async def delete(id: PydanticObjectId):
    result = await mdb_service.delete_by_id(model=TaskRunItemDoc, id=id)
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")


class UpdateTaskRunItemMetadataRequest(BaseModel):
    video_object_key: str | None = None
    log_object_key: str | None = None
    evidence_object_key: str | None = None
    evidence_md_object_key: str | None = None


@router.patch("/{id}/metadata", response_model=ApiResponse[dict])
async def update_metadata(
    id: PydanticObjectId,
    body: UpdateTaskRunItemMetadataRequest,
) -> ApiResponse[dict]:
    """追加更新 task_run_item 的 metadata（不覆盖已有字段）。

    evidence_object_key 落库时（本地 recorder 上传完成后回调），异步触发一次
    「带 evidence 的重新评判」，覆盖详情页的模型评价；不阻塞本接口响应。
    """
    logger.info(f"[task_run_item] 更新 metadata: id={id} body={body.model_dump()}")
    doc = await mdb_service.get_by_id(TaskRunItemDoc, doc_id=id)
    if doc is None:
        logger.warning(f"[task_run_item] 不存在: id={id}")
        raise HTTPException(status_code=404, detail="task_run_item 不存在")

    current_meta = doc.metadata or {}
    updates = body.model_dump(exclude_none=True)
    if updates:
        doc.metadata = {**current_meta, **updates}
        await doc.save()
        logger.info(
            f"[task_run_item] metadata 更新成功: id={id} "
            f"video_object_key={doc.metadata.get('video_object_key')}"
        )

    # evidence 落库后异步带 evidence 重判（覆盖 llm_evaluation，详情页模型评价以重判为准）
    if (
        body.evidence_object_key
        and not doc.metadata.get("re_judged_with_evidence")
        and not doc.metadata.get("re_judging")
    ):
        doc.metadata["re_judging"] = True
        await doc.save()
        asyncio.create_task(
            _rejudge_with_evidence(id, body.evidence_object_key, body.evidence_md_object_key)
        )

    return ok({"ok": True, "id": str(id), "metadata": doc.metadata})


async def _rejudge_with_evidence(
    item_id: PydanticObjectId,
    evidence_object_key: str | None,
    evidence_md_object_key: str | None,
) -> None:
    """下载证据（优先 markdown 报告，缺失/失败回退 evidence.json），带证据重新评判并覆盖 llm_evaluation。

    任一环节失败（下载/解析/评判）不重试：打 re_judge_failed 标记，保留原评价，
    不影响任何主流程（由 PATCH metadata 以 asyncio.create_task 异步触发）。
    """
    try:
        # 1. 下载证据（judge 直接消费 markdown 报告，对模型更友好）
        client = TosClient(get_tos_config())
        evidence: dict | str | None = None
        if evidence_md_object_key:
            try:
                evidence = client.download_bytes(evidence_md_object_key).decode("utf-8")
            except Exception as md_exc:
                logger.warning(f"[rejudge] evidence.md 下载失败，回退 json: {md_exc}")
        if not evidence and evidence_object_key:
            data = client.download_bytes(evidence_object_key)
            parsed = json.loads(data.decode("utf-8"))
            evidence = parsed if isinstance(parsed, dict) else None
        if not evidence:
            raise ValueError("evidence 下载为空")

        # 2. 反查 item + case，重建 TestCase（与 voice_test_api 加载逻辑一致）
        item = await mdb_service.get_by_id(TaskRunItemDoc, doc_id=item_id)
        if item is None:
            logger.warning(f"[rejudge] item 不存在，跳过: id={item_id}")
            return
        case_doc = await mdb_service.get_by_id(
            ComplexReasoningCaseDoc, doc_id=item.dataset_item_id
        )
        if case_doc is None:
            raise ValueError(f"未找到 case: dataset_item_id={item.dataset_item_id}")
        payload = case_doc.model_dump()
        payload["id"] = str(case_doc.id)
        case = TestCase.model_validate(payload)

        # 3. 带 evidence 重新评判
        history_for_judge = (item.metadata or {}).get("history_for_judge", "")
        judge = Judge(case, log_enabled=False, test_mode="voice")
        is_pass, reason = await judge.ajudge(case, history_for_judge, evidence=evidence)
        logger.info(
            f"[rejudge] 带 evidence 重判完成: item_id={item_id} is_pass={is_pass}"
        )

        # 4. 覆盖 llm_evaluation（详情页模型评价以重判为准）
        eval_doc = await mdb_service.get_one(
            TaskRunItemEvalDoc, query={"task_run_item_id": item_id}
        )
        if eval_doc is not None:
            eval_doc.llm_evaluation = Evaluation(is_pass=is_pass, comment=reason)
            await eval_doc.save()
        else:
            logger.warning(f"[rejudge] 未找到 eval 记录，跳过覆盖: item_id={item_id}")

        # 5. 打完成标记
        item.metadata = {
            **(item.metadata or {}),
            "re_judged_with_evidence": True,
            "re_judged_at": datetime.now().isoformat(timespec="seconds"),
            "re_judging": False,
        }
        await item.save()
    except Exception as exc:
        logger.warning(f"[rejudge] 带 evidence 重判失败: item_id={item_id} err={exc}")
        try:
            item = await mdb_service.get_by_id(TaskRunItemDoc, doc_id=item_id)
            if item is not None:
                item.metadata = {
                    **(item.metadata or {}),
                    "re_judge_failed": True,
                    "re_judge_failed_at": datetime.now().isoformat(timespec="seconds"),
                    "re_judge_error": str(exc)[:500],
                    "re_judging": False,
                }
                await item.save()
        except Exception as save_exc:
            logger.error(f"[rejudge] 失败标记写入异常: {save_exc}")


__all__ = ["router"]
