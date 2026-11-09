"""Public protocol for session-scoped stream model implementations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal, Protocol

from aicore.models.stream_model_api.events import StreamModelEvent
from aicore.models.stream_model_api.inputs import StreamModelInput

type ToolCallMode = Literal["sync", "async"]


class StreamModelAPI(Protocol):
    """Session-scoped stream model boundary.

    Implementations own exactly one provider session and one upstream input
    lane / downstream event lane.  The input lane is not a queue: every
    ``submit()`` is pushed straight to the provider in call order.  The event
    lane is single-consumer: ``events()`` must be called by at most one task.
    """

    @property
    def session_id(self) -> str:
        """Stable identifier for the underlying provider session."""

    async def start(self) -> None:
        """Connect to the provider and create the session.  Idempotent."""

    async def submit(self, input: StreamModelInput) -> str | None:
        """Submit one input to the provider lane.

        Returns a correlation id only when the backend can assign one
        synchronously (e.g. Responses query roots).  Backends whose ids arrive
        asynchronously on the event lane (e.g. Duplex ``item_id`` /
        ``response_id``) return ``None``.
        """

    def events(self) -> AsyncIterator[StreamModelEvent]:
        """Yield provider events for exactly one consumer.

        The stream ends when the provider session closes; calling ``events()``
        or ``submit()`` afterwards raises.
        """

    async def aclose(self) -> None:
        """Close the provider session and release the event lane.  Idempotent."""


__all__ = ["StreamModelAPI", "ToolCallMode"]
