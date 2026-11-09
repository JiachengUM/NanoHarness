from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol

import websockets

from aicore.models.stream_model_api.duplex.duplex_events import (
    decode_server_event,
    encode_client_event,
)

DEFAULT_API_APP_ID = "7620217375"
DEFAULT_API_RESOURCE_ID = "volc.speech.dialog"
DEFAULT_API_APP_KEY = "PlgvMymc7f3tQnJ6"

AuthMode = Literal["auto", "app-key", "x-api-key", "bearer"]
ConnectFunction = Callable[..., Awaitable[Any]]
DuplexEventObserver = Callable[
    [Literal["upstream", "downstream"], dict[str, Any], str],
    None,
]
logger = logging.getLogger(__name__)


class DuplexTransportConfig(Protocol):
    """Structural config accepted by :meth:`from_config`."""

    endpoint_url: str
    api_key: str


def build_app_auth_headers(
    *,
    access_key: str,
    app_id: str = DEFAULT_API_APP_ID,
    app_key: str = DEFAULT_API_APP_KEY,
    resource_id: str = DEFAULT_API_RESOURCE_ID,
    connect_id_factory: Callable[[], str] | None = None,
) -> dict[str, str]:
    connect_id = (
        connect_id_factory() if connect_id_factory is not None else str(uuid.uuid4())
    )
    return {
        "X-Api-App-ID": app_id,
        "X-Api-Access-Key": access_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-App-Key": app_key,
        "X-Api-Connect-Id": connect_id,
    }


def get_websocket_response_header(websocket: Any, name: str) -> str | None:
    response_headers = getattr(websocket, "response_headers", None)
    if response_headers is not None:
        return response_headers.get(name)

    response = getattr(websocket, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        return headers.get(name)
    return None


def _is_http_401(error: Exception) -> bool:
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if status is None:
        status = getattr(response, "status", None)
    return status == 401 or "HTTP 401" in str(error)


class DuplexWebSocketTransport:
    def __init__(
        self,
        *,
        endpoint_url: str,
        api_key: str,
        auth_mode: AuthMode = "app-key",
        connect_func: ConnectFunction = websockets.connect,
        app_id: str = DEFAULT_API_APP_ID,
        app_key: str = DEFAULT_API_APP_KEY,
        resource_id: str = DEFAULT_API_RESOURCE_ID,
        connect_id_factory: Callable[[], str] | None = None,
        websocket: Any | None = None,
        event_observer: DuplexEventObserver | None = None,
    ) -> None:
        if auth_mode not in {"auto", "app-key", "x-api-key", "bearer"}:
            raise ValueError(f"Unsupported Duplex auth mode: {auth_mode}")
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.auth_mode = auth_mode
        self.connect_func = connect_func
        self.app_id = app_id
        self.app_key = app_key
        self.resource_id = resource_id
        self.connect_id_factory = connect_id_factory
        self.websocket = websocket
        self.event_observer = event_observer
        self._write_lock = asyncio.Lock()

    @classmethod
    def from_config(
        cls,
        config: DuplexTransportConfig,
        *,
        auth_mode: AuthMode = "app-key",
        connect_func: ConnectFunction = websockets.connect,
        event_observer: DuplexEventObserver | None = None,
    ) -> DuplexWebSocketTransport:
        return cls(
            endpoint_url=config.endpoint_url,
            api_key=config.api_key,
            auth_mode=auth_mode,
            connect_func=connect_func,
            event_observer=event_observer,
        )

    async def _connect_once(self, headers: dict[str, str]) -> Any:
        return await self.connect_func(
            self.endpoint_url,
            additional_headers=headers,
            ping_interval=None,
            proxy=None,
        )

    def _app_headers(self) -> dict[str, str]:
        return build_app_auth_headers(
            access_key=self.api_key,
            app_id=self.app_id,
            app_key=self.app_key,
            resource_id=self.resource_id,
            connect_id_factory=self.connect_id_factory,
        )

    def _remember_connection(self, websocket: Any) -> Any:
        self.websocket = websocket
        log_id = get_websocket_response_header(websocket, "X-Tt-Logid")
        if log_id:
            logger.info("Duplex connected log_id=%s", log_id)
        return websocket

    async def connect(self) -> Any:
        if self.websocket is not None:
            return self.websocket

        if self.auth_mode == "app-key":
            return self._remember_connection(
                await self._connect_once(self._app_headers())
            )
        if self.auth_mode == "x-api-key":
            return self._remember_connection(
                await self._connect_once({"X-Api-Key": self.api_key})
            )
        if self.auth_mode == "bearer":
            return self._remember_connection(
                await self._connect_once({"Authorization": f"Bearer {self.api_key}"})
            )

        attempts = [
            self._app_headers(),
            {"X-Api-Key": self.api_key},
            {"Authorization": f"Bearer {self.api_key}"},
        ]
        for index, headers in enumerate(attempts):
            try:
                return self._remember_connection(await self._connect_once(headers))
            except Exception as error:
                if not _is_http_401(error) or index == len(attempts) - 1:
                    raise
        raise AssertionError("unreachable")

    def _require_websocket(self) -> Any:
        if self.websocket is None:
            raise RuntimeError("Duplex WebSocket is not connected")
        return self.websocket

    async def send_event(self, event: dict[str, Any]) -> None:
        payload = encode_client_event(event)
        async with self._write_lock:
            await self._require_websocket().send(payload)
        if self.event_observer is not None:
            self.event_observer("upstream", event, payload)

    async def receive_event(self) -> dict[str, Any]:
        frame = await self._require_websocket().recv()
        event = decode_server_event(frame)
        if self.event_observer is not None:
            payload = frame.decode("utf-8") if isinstance(frame, bytes) else frame
            self.event_observer("downstream", event, payload)
        return event

    async def close(self) -> None:
        websocket = self.websocket
        self.websocket = None
        if websocket is not None:
            await websocket.close()


__all__ = [
    "AuthMode",
    "DuplexTransportConfig",
    "DuplexWebSocketTransport",
    "DuplexEventObserver",
    "build_app_auth_headers",
    "get_websocket_response_header",
]
