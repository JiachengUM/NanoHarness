import contextvars
import logging
import uuid
import json
import asyncio
from datetime import datetime
from fastapi import Request, Response, FastAPI
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse
from typing import Optional, List, Set

from projects.uiagent.server.models.log import LogTable

logger = logging.getLogger(__name__)


class LoggingConfig:
    """日志记录配置类"""

    def __init__(
            self,
            enabled: bool = True,
            exclude_paths: Optional[Set[str]] = None,
            include_paths: Optional[Set[str]] = None,
            max_content_size: int = 10 * 1024 * 1024,  # 10MB默认限制
            log_request_body: bool = True,
            log_response_body: bool = True
    ):
        self.enabled = enabled
        self.exclude_paths = exclude_paths or set()
        self.include_paths = include_paths or set()
        self.max_content_size = max_content_size
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body

    def should_log_path(self, path: str) -> bool:
        """检查是否应该记录指定路径的日志"""
        if not self.enabled:
            return False

        # 如果设置了包含路径，只记录包含路径中的请求
        if self.include_paths and path not in self.include_paths:
            return False

        # 如果路径在排除列表中，不记录
        if path in self.exclude_paths:
            return False

        return True


def register_request_save(app: FastAPI, config: Optional[LoggingConfig] = None):
    """注册请求保存中间件"""
    if config is None:
        config = LoggingConfig(
            exclude_paths={
                "/docs",
                "/openapi.json",
                "/",
                "/health",
                "/log",
            }
        )

    @app.middleware("http")
    async def trace_id_middleware(request: Request, call_next):
        # 检查是否应该记录该路径的日志
        path = request.url.path

        if not config.should_log_path(path):
            # 不记录日志，直接传递请求
            return await call_next(request)

        chat_id = None
        req_json = {"raw_type": "non_json_request"}

        trace_id = getattr(request.state, 'trace_id', None)

        if trace_id is None:
            # 如果没有，才生成新的（理论上不应该发生）
            trace_id = str(uuid.uuid4())
            logger.warning(f'未找到 trace_id，使用新生成的: {trace_id}')

        # 记录请求开始时间
        start_time = datetime.now()

        try:
            # 读取请求体（如果是JSON）
            if (config.log_request_body and
                    request.method in ["POST", "PUT", "PATCH"] and
                    "application/json" in request.headers.get("content-type", "")):

                try:
                    # 读取并缓存请求体
                    body_bytes = await request.body()
                    if body_bytes:
                        req_json = json.loads(body_bytes)
                        chat_id = req_json.get("chat_id") if isinstance(req_json, dict) else None

                    # 重置请求体，以便后续使用
                    async def receive_reset():
                        return {"type": "http.request", "body": body_bytes, "more_body": False}

                    request._receive = receive_reset

                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"JSON解析错误: {e}")

        except Exception as e:
            logger.warning(f"请求体读取错误: {e}")

        # 处理请求并获取响应
        response = await call_next(request)

        # 记录请求结束时间
        end_time = datetime.now()
        process_time = (end_time - start_time).total_seconds()

        # 处理响应体，使用回调机制确保流式响应完整记录
        new_response = await _process_response_with_callback(
            response, path, trace_id, chat_id, req_json, start_time, process_time, config
        )

        return new_response


async def _process_response_with_callback(
        response: Response,
        path: str,
        trace_id: str,
        chat_id: Optional[str],
        req_json: dict,
        start_time: datetime,
        process_time: float,
        config: LoggingConfig
) -> Response:
    """使用回调机制处理响应，确保流式响应完整记录"""
    try:
        # 如果是StreamingResponse，使用回调机制
        if isinstance(response, StreamingResponse):
            return await _process_streaming_response_with_callback(
                response, path, trace_id, chat_id, req_json, start_time, process_time, config
            )
        else:
            # 常规响应直接处理
            return await _process_regular_response(
                response, path, trace_id, chat_id, req_json, start_time, process_time, config
            )
    except Exception as e:
        logger.error(f"处理响应时出错: {e}")
        error_response = JSONResponse(
            content={"error": "Internal server error"},
            status_code=500
        )
        error_response.headers["X-Trace-ID"] = trace_id
        return error_response


async def _process_streaming_response_with_callback(
        response: StreamingResponse,
        path: str,
        trace_id: str,
        chat_id: Optional[str],
        req_json: dict,
        start_time: datetime,
        process_time: float,
        config: LoggingConfig
) -> StreamingResponse:
    """使用回调机制处理流式响应"""
    collected_chunks = []

    async def content_generator():
        try:
            # 收集所有chunk
            async for chunk in response.body_iterator:
                collected_chunks.append(chunk)
                yield chunk
        except Exception as e:
            logger.error(f"流式响应生成错误: {e}")
            raise
        finally:
            # 无论成功还是失败，都在最后执行回调
            if config.log_response_body:
                # 使用copy避免后续修改影响
                chunks_copy = collected_chunks.copy()

                # 异步执行保存操作
                asyncio.create_task(
                    _save_streaming_content_callback(
                        chunks_copy, response.media_type, path,
                        trace_id, chat_id, req_json, start_time, process_time
                    )
                )

    # 创建新的StreamingResponse
    new_response = StreamingResponse(
        content=content_generator(),
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
        background=response.background
    )

    # 添加trace_id到响应头
    new_response.headers["X-Trace-ID"] = trace_id

    return new_response


async def _save_streaming_content_callback(
        collected_chunks: List[bytes],
        media_type: str,
        path: str,
        trace_id: str,
        chat_id: Optional[str],
        req_json: dict,
        start_time: datetime,
        process_time: float
):
    """流式响应完成后的回调函数"""
    try:
        if not collected_chunks:
            logger.warning(f"流式响应没有收集到任何chunk - 路径: {path}, TraceID: {trace_id}")
            return

        # 拼接所有chunk
        full_content = b"".join(collected_chunks)

        # 解析响应内容
        resp_json = await _parse_response_content(full_content, media_type)
        if isinstance(resp_json, dict):
            trace_id_resp = resp_json.get('trace_id', trace_id)
            resp_json["type"] = "streaming_response"
            resp_json["chunk_count"] = len(collected_chunks)
            resp_json["content_size"] = len(full_content)
        else:
            trace_id_resp = trace_id
        if trace_id_resp != trace_id:
            logger.warning(f"trace_id：[{trace_id}]异常，从请求中获取到的trace_id[{trace_id}]与响应信息中trace_id[{trace_id_resp}]的不一致")

        # 保存到数据库
        await save_log_async(
            trace_id_resp,
            chat_id,
            path,
            req_json,
            resp_json,
            start_time,
            process_time
        )

        logger.info(f"流式响应记录成功 - 路径: {path}, TraceID: {trace_id}, "
                    f"共{len(collected_chunks)}个chunk，总大小{len(full_content)}字节")

    except Exception as e:
        logger.error(f"流式响应回调处理出错: {e}")
        # 即使出错也尝试保存错误信息
        error_resp = {
            "type": "streaming_response",
            "error": f"Failed to process streaming content: {str(e)}",
            "chunk_count": len(collected_chunks)
        }

        try:
            await save_log_async(
                trace_id,
                chat_id,
                path,
                req_json,
                error_resp,
                start_time,
                process_time
            )
        except Exception as save_error:
            logger.error(f"保存错误信息到数据库失败: {save_error}")


async def _process_regular_response(
        response: Response,
        path: str,
        trace_id: str,
        chat_id: Optional[str],
        req_json: dict,
        start_time: datetime,
        process_time: float,
        config: LoggingConfig
) -> Response:
    """处理常规响应"""
    try:
        # 获取响应体
        if hasattr(response, "body"):
            body = response.body
        elif hasattr(response, "render"):
            body = await response.render()
        else:
            # 对于未知类型的响应，返回原始响应
            logger.warning(f"未知响应类型: {type(response)}")
            return response

        # 尝试解析内容
        resp_json = {}
        if config.log_response_body:
            resp_json = await _parse_response_content(body, getattr(response, "media_type", None))
        if isinstance(resp_json, dict):
            trace_id_resp = resp_json.get('trace_id', trace_id)
        else:
            trace_id_resp = trace_id
        if trace_id_resp == trace_id:
            logger.warning(f"trace_id：[{trace_id}]无效，未能从响应中获取")

        # 创建新的响应对象以确保响应体可再次读取
        new_response = Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=getattr(response, "media_type", None)
        )


        # 立即保存到数据库
        asyncio.create_task(
            save_log_async(
                trace_id_resp,
                chat_id,
                path,
                req_json,
                resp_json,
                start_time,
                process_time
            )
        )

        return new_response

    except Exception as e:
        logger.error(f"处理常规响应时出错: {e}")
        # 出错时返回原始响应
        response.headers["X-Trace-ID"] = trace_id
        return response


async def _parse_response_content(body: bytes, media_type: Optional[str]) -> dict:
    """解析响应内容"""
    if not body:
        return {"content": "empty"}

    try:
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning(f"JSON响应解析失败: {e}")
        try:
            return {"raw_content": body.decode("utf-8")}
        except UnicodeDecodeError:
            return {"raw_content_hex": body.hex()}



async def save_log_async(
        trace_id: str,
        chat_id: Optional[str],
        path: str,
        req_body: dict,
        resp_body: dict,
        start_time: datetime,
        process_time: float
):
    """异步保存日志到数据库"""
    try:
        await LogTable.save_data(
            trace_id=trace_id,
            chat_id=chat_id,
            path=path,  # 新增的path字段
            req=req_body,
            resp=resp_body,
            create_time=start_time,
            process_time=round(process_time, 3)
        )

        logger.info(f"请求记录成功 - 路径: {path}, TraceID: {trace_id}, "
                    f"ChatID: {chat_id}, 耗时: {process_time:.3f}s")

    except Exception as e:
        logger.error(f"保存日志到数据库失败: {str(e)}")