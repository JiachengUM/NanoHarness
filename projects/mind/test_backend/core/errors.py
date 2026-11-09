"""统一异常与响应结构 & 应用内错误码体系。

设计目标：
1. 所有对外错误响应结构保持一致：{ code, message, detail, trace_id }
2. 通过 ErrorCode 枚举集中管理业务语义，避免散落的字符串（便于前端 i18n / 监控聚合）。
3. 业务代码使用 raise_app_error/ErrorCode，而不是直接 raise HTTPException。
4. 未捕获异常与仍旧裸抛 HTTPException 的地方保持向后兼容。
"""

from __future__ import annotations

from typing import Any, Optional
from enum import IntEnum

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.exceptions import RequestValidationError
from nanoai.utils import logger


class ErrorCode(IntEnum):  # 数字业务码（约定 1000+ 为通用，2000+ 认证，3000+ 用户等）
    # 通用 1xxx
    INTERNAL_ERROR = 1000
    VALIDATION_ERROR = 1001
    PARAM_INVALID = 1002  # 参数语义/业务规则不满足（与格式校验区分）
    NOT_FOUND = 1004


class AppError(HTTPException):
    """应用内统一业务异常。"""

    def __init__(
        self,
        code: ErrorCode,
        status_code: int,
        message: Optional[str] = None,
        detail: Any = None,
    ) -> None:
        self.app_code = int(code)
        self.message_text = message or code.name.lower()
        self.detail_obj = detail
        super().__init__(status_code=status_code, detail=self.message_text)


def raise_app_error(
    code: ErrorCode,
    status_code: int,
    message: Optional[str] = None,
    detail: Any = None,
) -> None:
    """辅助函数：抛出 AppError。"""
    raise AppError(code=code, status_code=status_code, message=message, detail=detail)


class ErrorResponse(BaseModel):
    code: int
    message: str
    detail: Optional[Any] = None
    trace_id: Optional[str] = None


def http_exception_handler(request: Request, exc: HTTPException):  # noqa: D401
    trace_id = request.state.trace_id if hasattr(request.state, "trace_id") else None

    if isinstance(exc, AppError):  # 我们自定义的业务异常
        payload = ErrorResponse(
            code=exc.app_code,
            message=exc.message_text,
            detail=exc.detail_obj,
            trace_id=trace_id,
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    payload = ErrorResponse(
        code=exc.status_code,
        message=exc.detail if isinstance(exc.detail, str) else "HTTP Error",
        detail=None if isinstance(exc.detail, str) else exc.detail,
        trace_id=trace_id,
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


def unhandled_exception_handler(request: Request, exc: Exception):  # noqa: D401
    trace_id = request.state.trace_id if hasattr(request.state, "trace_id") else None
    logger.exception(f"Unhandled exception: {exc}")
    payload = ErrorResponse(
        code=int(ErrorCode.INTERNAL_ERROR),
        message="服务器内部错误",
        detail=None,  # 可在 debug 模式下附加: traceback.format_exc()
        trace_id=trace_id,
    )
    return JSONResponse(status_code=500, content=payload.model_dump())


def _sanitize_validation_errors(errors: Any):
    """防御性清洗: 确保 validation errors 可被 JSON 序列化。

    FastAPI/Pydantic v2 正常情况下 exc.errors() 返回 list[dict]，其中的
    'ctx' 值都应可序列化。但若第三方/自定义 validator 直接塞入了异常对象，
    这里做一次递归转换，避免 ValueError 等裸对象导致 JSON 序列化失败。
    """

    def convert(obj: Any):  # noqa: ANN401 - 广义处理
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        if isinstance(obj, list):
            return [convert(x) for x in obj]
        if isinstance(obj, tuple):
            return [convert(x) for x in obj]
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        # 其他不可直接序列化的对象，退化为字符串
        try:
            return str(obj)
        except Exception:  # pragma: no cover
            return repr(obj)

    return convert(errors)


def validation_exception_handler(
    request: Request, exc: RequestValidationError
):  # noqa: D401
    trace_id = request.state.trace_id if hasattr(request.state, "trace_id") else None
    raw_errors = exc.errors()
    safe_errors = _sanitize_validation_errors(raw_errors)
    payload = ErrorResponse(
        code=int(ErrorCode.VALIDATION_ERROR),
        message="参数校验失败",
        detail=safe_errors,
        trace_id=trace_id,
    )
    return JSONResponse(status_code=422, content=payload.model_dump())


__all__ = [
    "ErrorCode",
    "AppError",
    "raise_app_error",
    "ErrorResponse",
    "http_exception_handler",
    "unhandled_exception_handler",
    "validation_exception_handler",
]
