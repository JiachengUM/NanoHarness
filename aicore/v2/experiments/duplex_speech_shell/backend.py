"""Narrow speech-shell port backed by the raw Duplex command client."""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import replace
from typing import Any, Protocol

from aicore.models.stream_model_api.duplex.config import DuplexConfig
from aicore.models.stream_model_api.duplex.duplex_client import DuplexClient
from aicore.models.stream_model_api.duplex.duplex_events import (
    TYPE_ERROR,
    TYPE_INPUT_AUDIO_BUFFER_COMMITTED,
    TYPE_RESPONSE_DONE,
    TYPE_RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE,
    TYPE_RESPONSE_OUTPUT_AUDIO_DELTA,
    TYPE_RESPONSE_OUTPUT_AUDIO_DONE,
    TYPE_RESPONSE_OUTPUT_AUDIO_STARTED,
    TYPE_RESPONSE_OUTPUT_TEXT_DELTA,
    TYPE_RESPONSE_OUTPUT_TEXT_DONE,
    TYPE_SESSION_CLOSED,
    TYPE_SESSION_CREATED,
    TYPE_SESSION_UPDATED,
    TYPE_TRANSCRIPTION_COMPLETED,
    TYPE_TRANSCRIPTION_DELTA,
    TYPE_TRANSCRIPTION_FAILED,
    TYPE_TRANSCRIPTION_STARTED,
)
from aicore.models.stream_model_api.duplex.websocket_transport import (
    AuthMode,
    DuplexWebSocketTransport,
)
from aicore.v2.experiments.duplex_speech_shell.events import (
    AsrCompleted,
    AsrDelta,
    AsrFailed,
    AsrStarted,
    SpeechShellClosed,
    SpeechShellError,
    SpeechShellEvent,
    TtsAudioDelta,
    TtsCompleted,
    TtsStarted,
)
from aicore.v2.experiments.duplex_speech_shell.profile import (
    build_browser_speech_shell_session_config,
)

logger = logging.getLogger(__name__)


class SpeechShellBackend(Protocol):
    """Application port for continuous ASR and externally supplied TTS text."""

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def append_audio(self, chunk: bytes) -> None: ...

    async def commit_audio(self) -> None: ...

    async def append_speech_text(self, speech_id: str, text: str) -> None: ...

    async def commit_speech_text(self, speech_id: str, text: str) -> None: ...

    async def receive_event(self) -> SpeechShellEvent: ...


class RawDuplexClient(Protocol):
    """Exact raw-client surface required by :class:`RawDuplexSpeechBackend`."""

    session_id: str

    async def connect(self) -> None: ...

    async def session_create(
        self,
        session: dict[str, Any],
        extension: dict[str, Any],
    ) -> None: ...

    async def recv_event(self) -> dict[str, Any]: ...

    async def input_audio_append(self, data: bytes) -> None: ...

    async def input_audio_commit(self) -> None: ...

    async def speech_text_append(self, speech_id: str, text: str) -> None: ...

    async def speech_text_commit(self, speech_id: str, text: str) -> None: ...

    async def close(self) -> None: ...


class RawDuplexSpeechBackend:
    """Adapt one raw ``DuplexClient`` session to the speech-shell port."""

    def __init__(
        self,
        client: RawDuplexClient,
        *,
        session: dict[str, Any],
        extension: dict[str, Any],
    ) -> None:
        self.client = client
        self.session = session
        self.extension = extension
        self._connected = False
        self._closed = False

    async def connect(self) -> None:
        if self._connected:
            return

        await self.client.connect()
        # session_create consumes session.created itself. The application
        # receive loop must start only after this handshake has completed.
        await self.client.session_create(self.session, self.extension)
        self._connected = True
        self._closed = False

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._connected = False
        await self.client.close()

    async def append_audio(self, chunk: bytes) -> None:
        await self.client.input_audio_append(chunk)

    async def commit_audio(self) -> None:
        await self.client.input_audio_commit()

    async def append_speech_text(self, speech_id: str, text: str) -> None:
        await self.client.speech_text_append(speech_id, text)

    async def commit_speech_text(self, speech_id: str, text: str) -> None:
        await self.client.speech_text_commit(speech_id, text)

    async def receive_event(self) -> SpeechShellEvent:
        while True:
            raw_event = await self.client.recv_event()
            event = _map_raw_event(raw_event)
            if event is not None:
                return event


def build_raw_duplex_speech_backend(
    client: RawDuplexClient,
    *,
    config: DuplexConfig | None = None,
) -> RawDuplexSpeechBackend:
    """Wrap an injected raw client with the fixed browser speech profile."""

    resolved_config = config or _load_default_config()
    session, extension = build_browser_speech_shell_session_config(
        resolved_config,
        session_id=client.session_id,
    )
    return RawDuplexSpeechBackend(
        client,
        session=session,
        extension=extension,
    )


def build_backend_for_client(client: RawDuplexClient) -> RawDuplexSpeechBackend:
    """Compatibility seam for callers that still inject a raw client factory."""

    config = getattr(client, "config", None) or getattr(client, "cfg", None)
    if hasattr(client, "session_id"):
        resolved_config = config if isinstance(config, DuplexConfig) else None
        return build_raw_duplex_speech_backend(client, config=resolved_config)

    build_config = getattr(client, "build_session_config", None)
    if callable(build_config):
        built = build_config()
        if isinstance(built, tuple) and len(built) == 2:
            session, extension = built
            return RawDuplexSpeechBackend(
                client,
                session=dict(session),
                extension=dict(extension),
            )
    raise TypeError(
        "Injected Duplex client must expose config/session_id or "
        "build_session_config()"
    )


def build_default_duplex_client(
    config: DuplexConfig | None = None,
) -> DuplexClient:
    """Build the silent raw client retained by the compatibility export."""

    resolved_config = config or _load_default_config()
    auth_mode = _load_auth_mode()
    transport = DuplexWebSocketTransport.from_config(
        resolved_config,
        auth_mode=auth_mode,
    )
    return DuplexClient(transport=transport)


def build_default_speech_backend() -> RawDuplexSpeechBackend:
    config = _load_default_config()
    return build_raw_duplex_speech_backend(
        build_default_duplex_client(config),
        config=config,
    )


def _load_default_config() -> DuplexConfig:
    config = DuplexConfig()
    if not config.api_key:
        raise RuntimeError("DuplexConfig.api_key is required")

    endpoint_override = os.environ.get("DUPLEX_ENDPOINT_URL")
    if endpoint_override:
        config = replace(config, endpoint_url=endpoint_override)
    return config


def _load_auth_mode() -> AuthMode:
    auth_mode = os.environ.get("DUPLEX_AUTH_MODE", "app-key")
    if auth_mode not in {"auto", "app-key", "x-api-key", "bearer"}:
        raise RuntimeError(f"Unsupported DUPLEX_AUTH_MODE: {auth_mode}")
    return auth_mode


def _map_raw_event(event: dict[str, Any]) -> SpeechShellEvent | None:
    event_type = str(event.get("type") or "")
    if event_type == TYPE_TRANSCRIPTION_STARTED:
        return AsrStarted()
    if event_type == TYPE_TRANSCRIPTION_DELTA:
        text = str(
            event.get("delta")
            or event.get("transcript")
            or event.get("text")
            or ""
        ).strip()
        return AsrDelta(text) if text else None
    if event_type == TYPE_TRANSCRIPTION_COMPLETED:
        text = str(event.get("transcript") or event.get("text") or "").strip()
        return AsrCompleted(text)
    if event_type == TYPE_TRANSCRIPTION_FAILED:
        return AsrFailed(_error_message(event.get("error")))
    if event_type == TYPE_RESPONSE_OUTPUT_AUDIO_STARTED:
        return TtsStarted(
            response_id=str(event.get("response_id") or event.get("event_id") or ""),
            tts_type=str(event.get("tts_type") or ""),
        )
    if event_type == TYPE_RESPONSE_OUTPUT_AUDIO_DELTA:
        encoded = event.get("delta")
        if not isinstance(encoded, str) or not encoded:
            return None
        try:
            pcm_s16le = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError):
            logger.warning("[DUPLEX] invalid output audio payload")
            return None
        response_id = str(event.get("response_id") or "") or None
        return TtsAudioDelta(response_id=response_id, pcm_s16le=pcm_s16le)
    if event_type == TYPE_RESPONSE_OUTPUT_AUDIO_DONE:
        response_id = str(event.get("response_id") or "") or None
        return TtsCompleted(response_id=response_id)
    if event_type == TYPE_SESSION_CLOSED:
        return SpeechShellClosed()
    if event_type == TYPE_ERROR:
        return SpeechShellError(_error_message(event.get("error")) or "Duplex error")

    if event_type == TYPE_RESPONSE_OUTPUT_TEXT_DONE:
        logger.warning(
            "[DUPLEX NATIVE] reply ignored response_id=%s text=%s",
            event.get("response_id") or "",
            event.get("text") or "",
        )
    elif event_type == TYPE_RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE:
        logger.warning(
            "[DUPLEX NATIVE] function call ignored name=%s arguments=%s",
            event.get("name") or "",
            event.get("arguments") or "",
        )
    elif event_type not in {
        TYPE_SESSION_CREATED,
        TYPE_SESSION_UPDATED,
        TYPE_INPUT_AUDIO_BUFFER_COMMITTED,
        TYPE_RESPONSE_OUTPUT_TEXT_DELTA,
        # response.done is only a provider summary. output_audio.done is the
        # sole event allowed to finish an accepted speech response.
        TYPE_RESPONSE_DONE,
    }:
        logger.debug("[DUPLEX] ignored provider event type=%s", event_type)
    return None


def _error_message(error: object) -> str:
    return "" if error is None else str(error)


__all__ = [
    "RawDuplexClient",
    "RawDuplexSpeechBackend",
    "SpeechShellBackend",
    "build_backend_for_client",
    "build_default_duplex_client",
    "build_default_speech_backend",
    "build_raw_duplex_speech_backend",
]
