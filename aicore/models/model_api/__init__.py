"""Provider-neutral Model API abstractions."""

from .events import (
    ModelEvent,
    ModelTextDeltaEvent,
    ModelTextDoneEvent,
    ModelTextStartEvent,
    ModelToolCallEvent,
    is_model_event,
)
from .protocol import ModelAPI, ModelStream
from .factory import (
    ModelAPIBackend,
    create_chat_model_api,
    create_model_api,
    create_responses_model_api,
)
from .types import (
    AssistantMessage,
    ModelCallParams,
    ModelParams,
    ModelInput,
    ModelInputMessage,
    ModelMessage,
    ModelResponse,
    ModelState,
    ModelStateDump,
    StructuredModelResponse,
    SystemMessage,
    ToolResultsMessage,
    UserMessage,
)
from aicore.tools.run import ToolRunRequest, ToolRunResult

__all__ = [
    "AssistantMessage",
    "ModelAPI",
    "ModelAPIBackend",
    "ModelCallParams",
    "ModelParams",
    "ModelEvent",
    "ModelInput",
    "ModelInputMessage",
    "ModelMessage",
    "ModelResponse",
    "ModelState",
    "ModelStateDump",
    "ModelStream",
    "ModelTextDeltaEvent",
    "ModelTextDoneEvent",
    "ModelTextStartEvent",
    "ModelToolCallEvent",
    "StructuredModelResponse",
    "SystemMessage",
    "ToolRunRequest",
    "ToolRunResult",
    "ToolResultsMessage",
    "UserMessage",
    "create_chat_model_api",
    "create_model_api",
    "create_responses_model_api",
    "is_model_event",
]
