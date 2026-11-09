"""Duplex provider event names, codecs and request builders."""

from __future__ import annotations

import base64
import json
from typing import Any

TYPE_SESSION_CREATE = "session.create"
TYPE_SESSION_CLOSE = "session.close"
TYPE_INPUT_AUDIO_BUFFER_APPEND = "input_audio_buffer.append"
TYPE_INPUT_AUDIO_BUFFER_COMMIT = "input_audio_buffer.commit"
TYPE_RESPONSE_CANCEL = "response.cancel"
# Provider commands used by the v2 external-Agent speech shell for Duplex TTS.
# DuplexStreamModelAPI itself does not emit them.
TYPE_SPEECH_TEXT_BUFFER_APPEND = "speech_text_buffer.append"
TYPE_SPEECH_TEXT_BUFFER_COMMIT = "speech_text_buffer.commit"
TYPE_SPEECH_TEXT_BUFFER_REPLACEMENT_APPEND = "speech_text_buffer.replacement.append"
TYPE_SPEECH_TEXT_BUFFER_REPLACEMENT_COMMIT = "speech_text_buffer.replacement.commit"
TYPE_CONVERSATION_ITEM_CREATE = "conversation.item.create"
TYPE_CONVERSATION_ITEM_UPDATE = "conversation.item.update"
TYPE_CONVERSATION_ITEM_RETRIEVE = "conversation.item.retrieve"

TYPE_SESSION_CREATED = "session.created"
TYPE_SESSION_UPDATED = "session.updated"
TYPE_SESSION_CLOSED = "session.closed"
TYPE_INPUT_AUDIO_BUFFER_COMMITTED = "input_audio_buffer.committed"
TYPE_TRANSCRIPTION_STARTED = "conversation.item.input_audio_transcription.started"
TYPE_TRANSCRIPTION_DELTA = "conversation.item.input_audio_transcription.delta"
TYPE_TRANSCRIPTION_COMPLETED = "conversation.item.input_audio_transcription.completed"
TYPE_TRANSCRIPTION_FAILED = "conversation.item.input_audio_transcription.failed"
TYPE_RESPONSE_OUTPUT_TEXT_DELTA = "response.output_text.delta"
TYPE_RESPONSE_OUTPUT_TEXT_DONE = "response.output_text.done"
TYPE_RESPONSE_OUTPUT_AUDIO_STARTED = "response.output_audio.started"
TYPE_RESPONSE_OUTPUT_AUDIO_DELTA = "response.output_audio.delta"
TYPE_RESPONSE_OUTPUT_AUDIO_DONE = "response.output_audio.done"
TYPE_CONVERSATION_ITEM_ADDED = "conversation.item.added"
TYPE_CONVERSATION_ITEM_RETRIEVED = "conversation.item.retrieved"
TYPE_CONVERSATION_ITEM_UPDATED = "conversation.item.updated"
TYPE_CONVERSATION_ITEM_DELETED = "conversation.item.deleted"
TYPE_RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE = "response.function_call_arguments.done"
TYPE_RESPONSE_DONE = "response.done"
TYPE_RESPONSE_CANCELED = "response.canceled"
TYPE_ERROR = "error"


def encode_client_event(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False, separators=(",", ":"))


def decode_server_event(frame: str | bytes) -> dict[str, Any]:
    if isinstance(frame, bytes):
        frame = frame.decode("utf-8")
    event = json.loads(frame)
    if not isinstance(event, dict):
        raise ValueError("Duplex server event must be a JSON object")
    return event


def build_session_create_event(
    *,
    event_id: str,
    session: dict[str, Any],
    extension: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": TYPE_SESSION_CREATE,
        "event_id": event_id,
        "session": session,
        "extension": extension,
    }


def build_session_close_event(*, event_id: str) -> dict[str, Any]:
    return {"type": TYPE_SESSION_CLOSE, "event_id": event_id}


def build_input_audio_append_event(data: bytes) -> dict[str, Any]:
    return {
        "type": TYPE_INPUT_AUDIO_BUFFER_APPEND,
        "audio": base64.b64encode(data).decode("ascii"),
    }


def build_input_audio_commit_event(*, event_id: str) -> dict[str, Any]:
    return {"type": TYPE_INPUT_AUDIO_BUFFER_COMMIT, "event_id": event_id}


def build_response_cancel_event() -> dict[str, Any]:
    return {"type": TYPE_RESPONSE_CANCEL}


def build_speech_text_event(
    *,
    event_type: str,
    event_id: str,
    speech_id: str,
    text: str,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "event_id": event_id,
        "speech_id": speech_id,
        "text": text,
    }


def build_conversation_item_event(
    *,
    event_type: str,
    event_id: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "type": event_type,
        "event_id": event_id,
        "items": items,
    }
