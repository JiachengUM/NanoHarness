"""Tool run value objects shared by agent/model boundaries."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ToolRunType(BaseModel):
    """Base class for tool run value objects."""

    model_config = ConfigDict(extra="forbid")


class ToolRunRequest(ToolRunType):
    """A request to execute a tool once."""

    # 对应的抽象源于functioncall的call_id
    run_id: str
    tool_name: str
    arguments: dict[str, object]
    raw_arguments: str | None = Field(
        default=None,
        description="Provider raw arguments for debugging only.",
    )


class ToolRunResult(ToolRunType):
    """Result of one tool run."""

    run_id: str
    output: str
