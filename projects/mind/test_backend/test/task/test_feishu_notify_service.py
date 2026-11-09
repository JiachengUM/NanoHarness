import json
from types import SimpleNamespace

import httpx
import pytest

from projects.mind.test_backend.service.task.feishu_notify_service import (
    FeishuNotifyError,
    FeishuNotifyRecipient,
    FeishuNotifier,
    build_task_run_text,
    extract_feishu_receive_id,
    lookup_feishu_user_ids,
    notify_task_run_finished,
    resolve_feishu_notify_config,
)


def test_resolve_feishu_notify_config_from_task_metadata_and_env():
    metadata = {
        "notify": {
            "feishu": {
                "receive_id": "ou_user",
                "receive_id_type": "open_id",
                "on_success": True,
                "on_failure": False,
            }
        }
    }
    env = {
        "FEISHU_APP_ID": "cli_xxx",
        "FEISHU_APP_SECRET": "secret_xxx",
    }

    config = resolve_feishu_notify_config(metadata, env=env)

    assert config is not None
    assert config.app_id == "cli_xxx"
    assert config.app_secret == "secret_xxx"
    assert config.receive_id == "ou_user"
    assert config.receive_id_type == "open_id"
    assert config.on_success is True
    assert config.on_failure is False


def test_resolve_feishu_notify_config_returns_none_without_credentials():
    metadata = {"notify": {"feishu": {"receive_id": "ou_user"}}}

    config = resolve_feishu_notify_config(metadata, env={})

    assert config is None


def test_build_task_run_text_includes_summary_metrics():
    task = SimpleNamespace(id="task_1", name="意图路由回归")
    task_run = SimpleNamespace(
        id="run_1",
        status="completed",
        progress=SimpleNamespace(total=10, completed=10, success=8, failed=2),
        metadata={
            "total_case_num": 10,
            "passed_case_num": 8,
            "pass_rate": 0.8,
            "time_avg": 123.45,
        },
    )

    text = build_task_run_text(task, task_run)

    assert "意图路由回归" in text
    assert "completed" in text
    assert "10/10" in text
    assert "8/10" in text
    assert "80.00%" in text
    assert "123.45 ms" in text


def test_extract_feishu_receive_id_skips_entries_without_id():
    data = {
        "user_list": [
            {"email": "someone@example.com"},
            {"user_id": "ou_user", "mobile": "13800138000"},
        ]
    }

    receive_id = extract_feishu_receive_id(data, receive_id_type="open_id")

    assert receive_id == "ou_user"


@pytest.mark.asyncio
async def test_feishu_notifier_sends_tenant_token_then_message():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/open-apis/auth/v3/tenant_access_token/internal":
            assert request.method == "POST"
            assert request.read() == (
                b'{"app_id":"cli_xxx","app_secret":"secret_xxx"}'
            )
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "tenant_access_token": "tenant-token",
                    "expire": 7200,
                },
            )

        if request.url.path == "/open-apis/im/v1/messages":
            assert request.method == "POST"
            assert request.url.params["receive_id_type"] == "open_id"
            assert request.headers["Authorization"] == "Bearer tenant-token"
            payload = json.loads(request.content)
            assert payload["receive_id"] == "ou_user"
            assert payload["msg_type"] == "text"
            assert payload["content"] == '{"text":"任务完成"}'
            return httpx.Response(
                200,
                json={"code": 0, "data": {"message_id": "om_message"}},
            )

        return httpx.Response(404)

    config = resolve_feishu_notify_config(
        {"notify": {"feishu": {"receive_id": "ou_user"}}},
        env={"FEISHU_APP_ID": "cli_xxx", "FEISHU_APP_SECRET": "secret_xxx"},
    )
    assert config is not None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await FeishuNotifier(config=config, client=client).send_text(
            "任务完成"
        )

    assert result.message_id == "om_message"
    assert [request.url.path for request in requests] == [
        "/open-apis/auth/v3/tenant_access_token/internal",
        "/open-apis/im/v1/messages",
    ]


@pytest.mark.asyncio
async def test_lookup_feishu_user_ids_posts_emails_and_mobiles():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/open-apis/auth/v3/tenant_access_token/internal":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "tenant_access_token": "tenant-token",
                    "expire": 7200,
                },
            )

        if request.url.path == "/open-apis/contact/v3/users/batch_get_id":
            assert request.method == "POST"
            assert request.url.params["user_id_type"] == "open_id"
            assert request.headers["Authorization"] == "Bearer tenant-token"
            assert json.loads(request.content) == {
                "emails": ["someone@example.com"],
                "mobiles": ["13800138000"],
            }
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "user_list": [
                            {
                                "open_id": "ou_user",
                                "user_id": "user_1",
                                "union_id": "on_user",
                                "email": "someone@example.com",
                                "mobile": "13800138000",
                            }
                        ]
                    },
                },
            )

        return httpx.Response(404)

    config = resolve_feishu_notify_config(
        {"notify": {"feishu": {"receive_id": "ou_user"}}},
        env={"FEISHU_APP_ID": "cli_xxx", "FEISHU_APP_SECRET": "secret_xxx"},
    )
    assert config is not None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        data = await lookup_feishu_user_ids(
            config,
            emails=["someone@example.com"],
            mobiles=["13800138000"],
            client=client,
        )

    assert data["user_list"][0]["open_id"] == "ou_user"
    assert [request.url.path for request in requests] == [
        "/open-apis/auth/v3/tenant_access_token/internal",
        "/open-apis/contact/v3/users/batch_get_id",
    ]


@pytest.mark.asyncio
async def test_lookup_feishu_user_ids_surfaces_http_error_body():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/open-apis/auth/v3/tenant_access_token/internal":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "tenant_access_token": "tenant-token",
                    "expire": 7200,
                },
            )

        return httpx.Response(
            400,
            json={
                "code": 41009,
                "msg": "no email or mobile error",
            },
        )

    config = resolve_feishu_notify_config(
        {"notify": {"feishu": {"receive_id": "ou_user"}}},
        env={"FEISHU_APP_ID": "cli_xxx", "FEISHU_APP_SECRET": "secret_xxx"},
    )
    assert config is not None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FeishuNotifyError, match="41009"):
            await lookup_feishu_user_ids(
                config,
                emails=["someone@example.com"],
                client=client,
            )


@pytest.mark.asyncio
async def test_notify_task_run_finished_resolves_mobile_and_sends_report(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "cli_xxx")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret_xxx")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/open-apis/auth/v3/tenant_access_token/internal":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "tenant_access_token": "tenant-token",
                    "expire": 7200,
                },
            )

        if request.url.path == "/open-apis/contact/v3/users/batch_get_id":
            assert request.url.params["user_id_type"] == "open_id"
            assert json.loads(request.content) == {"mobiles": ["13800138000"]}
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "user_list": [
                            {
                                "user_id": "ou_user",
                                "mobile": "13800138000",
                            }
                        ]
                    },
                },
            )

        if request.url.path == "/open-apis/im/v1/messages":
            payload = json.loads(request.content)
            assert request.url.params["receive_id_type"] == "open_id"
            assert payload["receive_id"] == "ou_user"
            assert "任务执行完成: 意图路由回归" in payload["content"]
            return httpx.Response(
                200,
                json={"code": 0, "data": {"message_id": "om_message"}},
            )

        return httpx.Response(404)

    task = SimpleNamespace(id="task_1", name="意图路由回归", metadata={})
    task_run = SimpleNamespace(
        id="run_1",
        status="completed",
        progress=SimpleNamespace(total=1, completed=1, success=1, failed=0),
        metadata={"pass_rate": 1.0},
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await notify_task_run_finished(
            task,
            task_run,
            recipient=FeishuNotifyRecipient(mobile="13800138000"),
            client=client,
        )

    assert result is not None
    assert result.message_id == "om_message"
    assert [request.url.path for request in requests] == [
        "/open-apis/auth/v3/tenant_access_token/internal",
        "/open-apis/contact/v3/users/batch_get_id",
        "/open-apis/auth/v3/tenant_access_token/internal",
        "/open-apis/im/v1/messages",
    ]
