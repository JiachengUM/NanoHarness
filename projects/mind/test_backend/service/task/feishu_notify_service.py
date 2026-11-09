from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from typing import Mapping, Any

import httpx

from projects.mind.test_backend.config import get_feishu_config
from projects.mind.test_backend.enums.task import TaskRunStatus

FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
FEISHU_BATCH_GET_ID_URL = "https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id"


class FeishuNotifyError(RuntimeError):
    """Raised when Feishu returns a failed API response."""


@dataclass(frozen=True)
class FeishuNotifyConfig:
    app_id: str
    app_secret: str
    receive_id: str
    receive_id_type: str = "open_id"
    enabled: bool = True
    on_success: bool = True
    on_failure: bool = True


@dataclass(frozen=True)
class FeishuNotifyRecipient:
    email: str | None = None
    mobile: str | None = None
    receive_id: str | None = None
    receive_id_type: str = "open_id"


@dataclass(frozen=True)
class FeishuSendResult:
    message_id: str | None
    raw: dict[str, Any]


def resolve_feishu_notify_config(
    metadata: Mapping[str, Any] | None,
    *,
    env: Mapping[str, str] | None = None,
    receive_id: str | None = None,
    receive_id_type: str | None = None,
) -> FeishuNotifyConfig | None:
    env = env if env is not None else os.environ
    metadata = metadata or {}
    notify = metadata.get("notify") if isinstance(metadata.get("notify"), dict) else {}
    feishu = notify.get("feishu") if isinstance(notify.get("feishu"), dict) else {}

    if feishu.get("enabled") is False:
        return None

    feishu_config = get_feishu_config()
    app_id = feishu_config.app_id
    app_secret = feishu_config.app_secret
    resolved_receive_id = receive_id or (
        feishu.get("receive_id")
        or metadata.get("feishu_open_id")
        or env.get("FEISHU_RECEIVE_ID")
    )

    if not app_id or not app_secret or not resolved_receive_id:
        return None

    return FeishuNotifyConfig(
        app_id=str(app_id),
        app_secret=str(app_secret),
        receive_id=str(resolved_receive_id),
        receive_id_type=str(
            receive_id_type
            or feishu.get("receive_id_type")
            or env.get("FEISHU_RECEIVE_ID_TYPE")
            or "open_id"
        ),
        enabled=True,
        on_success=bool(feishu.get("on_success", True)),
        on_failure=bool(feishu.get("on_failure", True)),
    )


def build_task_run_text(task: Any, task_run: Any) -> str:
    task_name = getattr(task, "name", "")
    task_id = getattr(task, "id", "")
    run_id = getattr(task_run, "id", "")
    status = getattr(task_run, "status", "")
    progress = getattr(task_run, "progress", None)
    metadata = getattr(task_run, "metadata", None) or {}

    lines = [
        f"任务执行完成: {task_name}",
        f"状态: {status}",
        f"任务ID: {task_id}",
        f"运行ID: {run_id}",
    ]

    if progress:
        completed = getattr(progress, "completed", 0)
        total = getattr(progress, "total", 0)
        success = getattr(progress, "success", 0)
        failed = getattr(progress, "failed", 0)
        lines.append(f"进度: {completed}/{total}")
        lines.append(f"通过/总数: {success}/{total}")
        lines.append(f"失败: {failed}")

    if "passed_case_num" in metadata and "total_case_num" in metadata:
        lines.append(f"评测通过: {metadata['passed_case_num']}/{metadata['total_case_num']}")
    if "pass_rate" in metadata:
        lines.append(f"通过率: {metadata['pass_rate']:.2%}")
    if "time_avg" in metadata:
        lines.append(f"平均耗时: {metadata['time_avg']:.2f} ms")
    if "error" in metadata:
        lines.append(f"错误: {metadata['error']}")

    return "\n".join(lines)


def should_notify(config: FeishuNotifyConfig, status: str) -> bool:
    if not config.enabled:
        return False
    if status == TaskRunStatus.COMPLETED:
        return config.on_success
    if status == TaskRunStatus.FAILED:
        return config.on_failure
    return False


class FeishuNotifier:
    def __init__(
        self,
        config: FeishuNotifyConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ):
        self.config = config
        self._client = client

    async def send_text(self, text: str) -> FeishuSendResult:
        if self._client:
            return await self._send_text(self._client, text)

        async with httpx.AsyncClient(timeout=10.0) as client:
            return await self._send_text(client, text)

    async def _send_text(
        self, client: httpx.AsyncClient, text: str
    ) -> FeishuSendResult:
        token = await self._get_tenant_access_token(client)
        payload = {
            "receive_id": self.config.receive_id,
            "msg_type": "text",
            "content": json.dumps(
                {"text": text}, ensure_ascii=False, separators=(",", ":")
            ),
        }
        response = await client.post(
            FEISHU_MESSAGE_URL,
            params={"receive_id_type": self.config.receive_id_type},
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        data = _read_feishu_response(response)
        message_data = data.get("data") or {}
        return FeishuSendResult(message_id=message_data.get("message_id"), raw=data)

    async def _get_tenant_access_token(self, client: httpx.AsyncClient) -> str:
        response = await client.post(
            FEISHU_TOKEN_URL,
            json={"app_id": self.config.app_id, "app_secret": self.config.app_secret},
        )
        data = _read_feishu_response(response)
        token = data.get("tenant_access_token")
        if not token:
            raise FeishuNotifyError("Feishu response missing tenant_access_token")
        return str(token)


async def notify_task_run_finished(
    task: Any,
    task_run: Any,
    *,
    recipient: FeishuNotifyRecipient | None = None,
    client: httpx.AsyncClient | None = None,
) -> FeishuSendResult | None:
    config = await _resolve_notify_config(getattr(task, "metadata", None), recipient, client)
    if not config or not should_notify(config, str(getattr(task_run, "status", ""))):
        return None

    text = build_task_run_text(task, task_run)
    return await FeishuNotifier(config, client=client).send_text(text)


async def _resolve_notify_config(
    metadata: Mapping[str, Any] | None,
    recipient: FeishuNotifyRecipient | None,
    client: httpx.AsyncClient | None,
) -> FeishuNotifyConfig | None:
    if not recipient:
        return resolve_feishu_notify_config(metadata)

    if recipient.receive_id:
        return resolve_feishu_notify_config(
            metadata,
            receive_id=recipient.receive_id,
            receive_id_type=recipient.receive_id_type,
        )

    config = resolve_feishu_notify_config(
        metadata, receive_id="_lookup_only_", receive_id_type="open_id"
    )
    if not config:
        return None

    data = await lookup_feishu_user_ids(
        config,
        emails=[recipient.email] if recipient.email else None,
        mobiles=[recipient.mobile] if recipient.mobile else None,
        user_id_type="open_id",
        client=client,
    )
    receive_id = extract_feishu_receive_id(data, receive_id_type="open_id")
    if not receive_id:
        raise FeishuNotifyError(f"Feishu user lookup returned no open_id: {data}")
    return replace(config, receive_id=receive_id, receive_id_type="open_id")


async def lookup_feishu_user_ids(
    config: FeishuNotifyConfig,
    *,
    emails: list[str] | None = None,
    mobiles: list[str] | None = None,
    user_id_type: str = "open_id",
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    async def _lookup(active_client: httpx.AsyncClient) -> dict[str, Any]:
        token = await FeishuNotifier(config)._get_tenant_access_token(active_client)
        payload: dict[str, list[str]] = {}
        if emails:
            payload["emails"] = emails
        if mobiles:
            payload["mobiles"] = mobiles
        if not payload:
            raise ValueError("emails or mobiles must be provided")

        response = await active_client.post(
            FEISHU_BATCH_GET_ID_URL,
            params={"user_id_type": user_id_type},
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        data = _read_feishu_response(response)
        return data.get("data") or {}

    if client:
        return await _lookup(client)

    async with httpx.AsyncClient(timeout=10.0) as active_client:
        return await _lookup(active_client)


def extract_feishu_receive_id(
    data: Mapping[str, Any], *, receive_id_type: str = "open_id"
) -> str | None:
    user_list = data.get("user_list") or []
    if not isinstance(user_list, list):
        return None

    for user in user_list:
        if not isinstance(user, Mapping):
            continue
        if receive_id_type == "open_id":
            receive_id = user.get("open_id") or user.get("user_id")
        elif receive_id_type == "union_id":
            receive_id = user.get("union_id") or user.get("user_id")
        else:
            receive_id = user.get(receive_id_type)
        if receive_id:
            return str(receive_id)

    return None


def _read_feishu_response(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        if not response.is_success:
            raise FeishuNotifyError(
                f"Feishu HTTP error {response.status_code} {response.reason_phrase}: "
                f"{response.text}"
            ) from None
        raise FeishuNotifyError("Feishu response is not JSON") from None

    if not isinstance(data, dict):
        raise FeishuNotifyError(f"Feishu response is not an object: {data!r}")

    if not response.is_success:
        try:
            _raise_for_feishu_error(data)
        except FeishuNotifyError as e:
            raise FeishuNotifyError(
                f"Feishu HTTP error {response.status_code} {response.reason_phrase}: {e}"
            ) from None
        raise FeishuNotifyError(
            f"Feishu HTTP error {response.status_code} {response.reason_phrase}: {data}"
        )

    _raise_for_feishu_error(data)
    return data


def _raise_for_feishu_error(data: Mapping[str, Any]) -> None:
    code = data.get("code", 0)
    if code != 0:
        message = data.get("msg") or data.get("message") or "Feishu API error"
        raise FeishuNotifyError(f"{message} (code={code})")
