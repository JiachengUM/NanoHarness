"""请求上下文管理"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional


_current_trace_id: ContextVar[Optional[str]] = ContextVar(
    "current_trace_id", default=None
)


def set_current_trace_id(trace_id: Optional[str]) -> None:
    _current_trace_id.set(trace_id)


def get_current_trace_id() -> Optional[str]:
    return _current_trace_id.get()


__all__ = [
    "set_current_trace_id",
    "get_current_trace_id",
]
