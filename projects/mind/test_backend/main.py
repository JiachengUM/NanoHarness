import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse

from aicore.v2.experiments.v2_frontend_duplex_backend import (
    app as v2_agent_duplex_app,
)
from projects.mind.test_backend.api.routers import api_router
from projects.mind.advisor.utils.httpx_client import init_httpx_client
from projects.mind.test_backend.db.init_beanie import init_db
from projects.mind.test_backend.core.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from nanoai.utils import logger
from projects.mind.test_backend.service.context.context import poll_context_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting application: AI Mind Test Backend")
    await init_db()
    await init_httpx_client()

    task = None
    if os.getenv("ENV") == "production":
        # 仅部署环境启动后台轮询任务
        task = asyncio.create_task(poll_context_loop())

    yield

    if task:
        task.cancel()
    logger.info("Shutting down application")


app = FastAPI(
    title="AI Mind Test Backend",
    version="0.1.0",
    debug=True,
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
)

# CORS 中间件，允许所有来源和常用方法
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 统一异常处理
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.include_router(api_router)
app.mount("/api/v2-agent", v2_agent_duplex_app)


def run() -> None:  # Entry point for script definition in pyproject
    import uvicorn

    uvicorn.run(
        " projects.mind.advisor.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        factory=False,
    )


if __name__ == "__main__":  # pragma: no cover
    # 启动主服务
    run()
