
import uuid

from fastapi import FastAPI, Request

from projects.uiagent.server.configs.trace_id_filter import trace_id_context

def register_routes(app: FastAPI):
    @app.middleware("http")
    async def trace_id_middleware(request: Request, call_next):
        """
        http请求日志Id管理中间件，用于生成和管理请求的trace_id
        """
        trace_id = str(uuid.uuid4())
        # 设置 trace_id 到上下文变量
        token = trace_id_context.set(trace_id)

        # 可选：将 trace_id 放入 request.state，供后续使用
        request.state.trace_id = trace_id

        response = await call_next(request)

        trace_id_context.reset(token)
        return response