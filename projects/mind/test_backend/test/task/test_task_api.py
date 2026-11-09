import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("beanie")
from beanie import PydanticObjectId  # noqa: E402

from projects.mind.test_backend.api.task import task_api
from projects.mind.test_backend.schemas.task.task import TaskRunRequest


@pytest.mark.asyncio
async def test_run_task_passes_notify_contact_to_background_task(monkeypatch):
    captured = {}
    original_create_task = asyncio.create_task

    async def fake_run_task_by_step(task_id, notify_recipient=None):
        captured["task_id"] = task_id
        captured["notify_recipient"] = notify_recipient

    def capture_task(coro):
        task = original_create_task(coro)
        captured["task"] = task
        return task

    monkeypatch.setattr(
        task_api,
        "_get_task_auto_run_service",
        lambda: SimpleNamespace(run_task_by_step=fake_run_task_by_step),
    )
    monkeypatch.setattr(task_api.asyncio, "create_task", capture_task)

    task_id = PydanticObjectId("69ea000f799385d1bc6f2603")
    response = await task_api.run_task(
        task_id,
        TaskRunRequest(email="qihang.yu@extour-inc.com", phone="13800138000"),
        current_user=None,
    )
    await captured["task"]

    assert response.code == 200
    assert captured["task_id"] == task_id
    assert captured["notify_recipient"].email == "qihang.yu@extour-inc.com"
    assert captured["notify_recipient"].mobile == "13800138000"


@pytest.mark.asyncio
async def test_run_task_uses_logged_in_feishu_user_as_notify_recipient(monkeypatch):
    captured = {}
    original_create_task = asyncio.create_task

    async def fake_run_task_by_step(task_id, notify_recipient=None):
        captured["task_id"] = task_id
        captured["notify_recipient"] = notify_recipient

    def capture_task(coro):
        task = original_create_task(coro)
        captured["task"] = task
        return task

    monkeypatch.setattr(
        task_api,
        "_get_task_auto_run_service",
        lambda: SimpleNamespace(run_task_by_step=fake_run_task_by_step),
    )
    monkeypatch.setattr(task_api.asyncio, "create_task", capture_task)

    task_id = PydanticObjectId("69ea000f799385d1bc6f2603")
    current_user = SimpleNamespace(open_id="ou_user", name="Wayne")

    response = await task_api.run_task(
        task_id,
        None,
        current_user=current_user,
    )
    await captured["task"]

    assert response.code == 200
    assert captured["task_id"] == task_id
    assert captured["notify_recipient"].receive_id == "ou_user"
    assert captured["notify_recipient"].receive_id_type == "open_id"
