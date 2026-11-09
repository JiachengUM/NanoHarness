from __future__ import annotations

import uuid
from typing import Any, Protocol

from aicore.models.stream_model_api.duplex.duplex_events import (
    TYPE_CONVERSATION_ITEM_CREATE,
    TYPE_CONVERSATION_ITEM_RETRIEVE,
    TYPE_CONVERSATION_ITEM_UPDATE,
    TYPE_ERROR,
    TYPE_SESSION_CREATED,
    TYPE_SPEECH_TEXT_BUFFER_APPEND,
    TYPE_SPEECH_TEXT_BUFFER_COMMIT,
    TYPE_SPEECH_TEXT_BUFFER_REPLACEMENT_APPEND,
    TYPE_SPEECH_TEXT_BUFFER_REPLACEMENT_COMMIT,
    build_conversation_item_event,
    build_input_audio_append_event,
    build_input_audio_commit_event,
    build_response_cancel_event,
    build_session_close_event,
    build_session_create_event,
    build_speech_text_event,
)


class DuplexEventTransport(Protocol):
    async def connect(self) -> Any: ...
    async def send_event(self, event: dict[str, Any]) -> None: ...
    async def receive_event(self) -> dict[str, Any]: ...
    async def close(self) -> None: ...


class DuplexClient:
    """Low-level Duplex command client over one injected transport.

    Session prompts, VAD profiles, business tools and function-call handlers
    belong to the composition root. This client only owns provider command
    encoding, ids and connection lifecycle.

    The ``speech_text_*`` commands below are provider capabilities used by the
    v2 external-Agent speech shell. The Duplex-native ``StreamModelAPI`` path
    does not use them: it consumes Duplex model audio directly. Keeping these
    commands here lets both application paths share one raw provider client.
    """

    def __init__(
        self,
        *,
        transport: DuplexEventTransport,
        session_id: str | None = None,
    ) -> None:
        self.transport = transport
        self.session_id = session_id or str(uuid.uuid4())
        self.dialog_id = ""
        self._event_id = 0
        self._connected = False
        self._closed = False

    def new_event_id(self) -> str:
        self._event_id += 1
        return f"event_{self._event_id}"

    async def connect(self) -> None:
        await self.transport.connect()
        self._connected = True
        self._closed = False

    async def send_event(self, event: dict[str, Any]) -> None:
        await self.transport.send_event(event)

    async def recv_event(self) -> dict[str, Any]:
        return await self.transport.receive_event()

    async def session_create(
        self,
        session: dict[str, Any],
        extension: dict[str, Any],
    ) -> None:
        await self.send_event(
            build_session_create_event(
                event_id=self.new_event_id(),
                session=session,
                extension=extension,
            )
        )
        while True:
            event = await self.recv_event()
            event_type = event.get("type")
            if event_type == TYPE_SESSION_CREATED:
                self.dialog_id = str(event.get("session", {}).get("id") or "")
                return
            if event_type == TYPE_ERROR:
                raise RuntimeError(f"Duplex session.create failed: {event}")

    async def session_close(self) -> None:
        await self.send_event(build_session_close_event(event_id=self.new_event_id()))

    async def input_audio_append(self, data: bytes) -> None:
        await self.send_event(build_input_audio_append_event(data))

    async def input_audio_commit(self) -> None:
        await self.send_event(
            build_input_audio_commit_event(event_id=self.new_event_id())
        )

    async def response_cancel(self) -> None:
        await self.send_event(build_response_cancel_event())

    async def speech_text_append(self, speech_id: str, text: str) -> None:
        await self._send_speech_text(
            TYPE_SPEECH_TEXT_BUFFER_APPEND,
            speech_id,
            text,
        )

    async def speech_text_commit(self, speech_id: str, text: str) -> None:
        await self._send_speech_text(
            TYPE_SPEECH_TEXT_BUFFER_COMMIT,
            speech_id,
            text,
        )

    async def speech_text_replacement_append(
        self,
        speech_id: str,
        text: str,
    ) -> None:
        await self._send_speech_text(
            TYPE_SPEECH_TEXT_BUFFER_REPLACEMENT_APPEND,
            speech_id,
            text,
        )

    async def speech_text_replacement_commit(
        self,
        speech_id: str,
        text: str,
    ) -> None:
        await self._send_speech_text(
            TYPE_SPEECH_TEXT_BUFFER_REPLACEMENT_COMMIT,
            speech_id,
            text,
        )

    async def _send_speech_text(
        self,
        event_type: str,
        speech_id: str,
        text: str,
    ) -> None:
        await self.send_event(
            build_speech_text_event(
                event_type=event_type,
                event_id=self.new_event_id(),
                speech_id=speech_id,
                text=text,
            )
        )

    async def conversation_item_create(
        self,
        items: list[dict[str, Any]],
    ) -> None:
        await self._send_conversation_items(TYPE_CONVERSATION_ITEM_CREATE, items)

    async def conversation_item_update(
        self,
        items: list[dict[str, Any]],
    ) -> None:
        await self._send_conversation_items(TYPE_CONVERSATION_ITEM_UPDATE, items)

    async def conversation_item_retrieve(
        self,
        items: list[dict[str, Any]] | None = None,
    ) -> None:
        await self._send_conversation_items(
            TYPE_CONVERSATION_ITEM_RETRIEVE,
            items or [],
        )

    async def _send_conversation_items(
        self,
        event_type: str,
        items: list[dict[str, Any]],
    ) -> None:
        await self.send_event(
            build_conversation_item_event(
                event_type=event_type,
                event_id=self.new_event_id(),
                items=items,
            )
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._connected:
            try:
                await self.session_close()
            finally:
                self._connected = False
                await self.transport.close()
        else:
            await self.transport.close()


__all__ = ["DuplexClient", "DuplexEventTransport"]
