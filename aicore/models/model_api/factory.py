"""Factory helpers for constructing ModelAPI adapters at application edges."""

from __future__ import annotations

from typing import Any, Literal, assert_never

from volcenginesdkarkruntime import AsyncArk  # type: ignore

from aicore.models.credentials import get_client

from .chat_adapter import ChatModelAPI
from .protocol import ModelAPI
from .responses_adapter import ResponsesModelAPI

type ModelAPIBackend = Literal["chat", "responses"]


def create_chat_model_api(
    *,
    client: AsyncArk,
    model: str,
) -> ChatModelAPI:
    """Create a Chat-backed ModelAPI from provider client identity only."""

    return ChatModelAPI(
        client=client,
        model=model,
    )


def create_responses_model_api(
    *,
    client: AsyncArk,
    model: str,
) -> ResponsesModelAPI:
    """Create a Responses-backed ModelAPI from provider client identity only."""

    return ResponsesModelAPI(
        client=client,
        model=model,
    )


def create_model_api(
    *,
    backend: ModelAPIBackend,
    model: str,
    client: AsyncArk = get_client(AsyncArk),
) -> ModelAPI[Any]:
    """Create a ModelAPI adapter for the selected provider API surface."""

    match backend:
        case "chat":
            return create_chat_model_api(
                client=client,
                model=model,
            )
        case "responses":
            return create_responses_model_api(
                client=client,
                model=model,
            )
        case _:
            assert_never(backend)
