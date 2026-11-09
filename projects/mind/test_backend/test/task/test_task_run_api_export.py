from types import SimpleNamespace

import pytest

pytest.importorskip("beanie")
from beanie import PydanticObjectId  # noqa: E402

from projects.mind.test_backend.api.task import task_run_api
from projects.mind.test_backend.mdb_models.task import (
    TaskDoc,
    TaskRunDoc,
    TaskRunItemDoc,
    TaskRunItemEvalDoc,
    TaskRunItemMessageDoc,
)
from projects.mind.complex_reasoning.task_mdb_models.case import (  # noqa: E402
    ComplexReasoningCaseDoc,
)


@pytest.mark.asyncio
async def test_export_task_run_returns_excel_response(monkeypatch):
    task_id = PydanticObjectId("69ea000f799385d1bc6f2603")
    run_id = PydanticObjectId("69ea000f799385d1bc6f2604")
    item_id = PydanticObjectId("69ea000f799385d1bc6f2605")
    case_id = PydanticObjectId("69ea000f799385d1bc6f2606")

    task = SimpleNamespace(id=task_id, name="意图路由回归")
    task_run = SimpleNamespace(id=run_id, task_id=task_id)
    run_item = SimpleNamespace(id=item_id, dataset_item_id=case_id)
    case = SimpleNamespace(id=case_id)
    eval_doc = SimpleNamespace(task_run_item_id=item_id)
    message_doc = SimpleNamespace(task_run_item_id=item_id)
    captured = {}

    async def fake_get_by_id(model, doc_id):
        if model is TaskRunDoc and doc_id == run_id:
            return task_run
        if model is TaskDoc and doc_id == task_id:
            return task
        raise AssertionError((model, doc_id))

    async def fake_get_list(model, query=None, sort=None, exclude_fields=None):
        captured.setdefault("queries", []).append((model, query, sort, exclude_fields))
        if model is TaskRunItemDoc:
            return [run_item]
        if model is ComplexReasoningCaseDoc:
            return [case]
        if model is TaskRunItemEvalDoc:
            return [eval_doc]
        if model is TaskRunItemMessageDoc:
            return [message_doc]
        return []

    def fake_build_task_run_export_workbook(**kwargs):
        captured["builder_kwargs"] = kwargs
        return b"xlsx-bytes"

    monkeypatch.setattr(task_run_api.mdb_service, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(task_run_api.mdb_service, "get_list", fake_get_list)
    monkeypatch.setattr(
        task_run_api.task_run_export_service,
        "build_task_run_export_workbook",
        fake_build_task_run_export_workbook,
    )

    response = await task_run_api.export(run_id)

    assert response.media_type.endswith("spreadsheetml.sheet")
    assert response.headers["content-disposition"] == (
        "attachment; filename=task_run_69ea000f799385d1bc6f2604.xlsx"
    )
    assert captured["builder_kwargs"] == {
        "task": task,
        "task_run": task_run,
        "run_items": [run_item],
        "case_map": {str(case_id): case},
        "eval_map": {str(item_id): eval_doc},
        "message_map": {str(item_id): [message_doc]},
    }
