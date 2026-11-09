from __future__ import annotations

import json
from typing import Generic, Optional, TypeVar, Any, AsyncGenerator
from io import BytesIO
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from projects.mind.test_backend.core.errors import raise_app_error, ErrorCode
from projects.mind.test_backend.core.context import get_current_trace_id

T = TypeVar("T")

SUCCESS_CODE = 200


class ApiResponse(BaseModel, Generic[T]):
    """统一成功响应结构（仅用于成功）。"""

    code: int = Field(default=SUCCESS_CODE, description="业务状态码：成功固定 200")
    message: str = Field(default="success", description="响应提示信息")
    data: Optional[T] = Field(default=None, description="具体数据载荷")
    trace_id: Optional[str] = Field(default=None, description="链路追踪ID")

    @classmethod
    def build(cls, data: T | None = None, message: str = "success") -> ApiResponse[T]:
        return cls(data=data, message=message, trace_id=get_current_trace_id())


class ApiStreamChunk(BaseModel):
    """SSE流式响应结构，用于区分不同类型的流式数据块。"""

    type: str = Field(..., description="响应类型")
    content: Any = Field(..., description="具体内容，类型根据type字段变化")

    def to_str(self) -> str:
        return f"data: {json.dumps(self.model_dump(), ensure_ascii=False)}\n\n"


def ok(data: T | None = None, message: str = "success") -> ApiResponse[T]:
    return ApiResponse[T].build(data=data, message=message)


def fail(
    code: ErrorCode,
    message: str | None = None,
    *,
    status: int = 400,
    detail: Any = None,
) -> None:
    """业务失败辅助：内部仍使用异常流程，保持 HTTP 状态码语义。"""
    raise_app_error(code=code, status_code=status, message=message, detail=detail)


def sse_ok(generator: AsyncGenerator[str, None]) -> StreamingResponse:
    """SSE流式响应封装。

    Args:
        generator: 异步生成器，yield SSE格式的字符串 (data: {...}\\n\\n)

    Returns:
        StreamingResponse: 配置好的SSE流式响应
    """
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用nginx缓冲
        },
    )


def excel_export_ok(
    excel_bytes: bytes,
    filename: str = "export.xlsx",
) -> StreamingResponse:
    """导出 Excel 成功响应。"""
    return StreamingResponse(
        content=BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


__all__ = [
    "ApiResponse",
    "ApiStreamChunk",
    "ok",
    "fail",
    "sse_ok",
    "SUCCESS_CODE",
    "excel_export_ok",
]
