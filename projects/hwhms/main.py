import asyncio
import logging
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI

# 将项目根目录添加到 Python 路径
# 即使安装了包，直接运行脚本时仍需要此行代码
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
from projects.hwhms.common.config.config import AppConfig
from projects.hwhms.common.config.nacos_configs import NacosConfigs
from projects.hwhms.common.config.nacos_util import init_nacos

from projects.hwhms import api
from projects.hwhms.common.config.logging_config import init_logging

logger = logging.getLogger(__name__)

DEFAULT_BIND_HOST = "0.0.0.0" if sys.platform != "win32" else "127.0.0.1"

API_SERVER = {
    "host": DEFAULT_BIND_HOST,
    "port": 18992,
}

async def create_app() -> FastAPI:
    # 创建FastAPI应用
    app = FastAPI(
        title="HWHMS API",
        description="华为智能中枢的API",
        version="0.1.0"
    )

    # 包含路由
    app.include_router(api.router, prefix="/v1/exturing", tags=["exturing"])
    app.include_router(api.router, prefix="/health", tags=["health"])
    app.include_router(api.router, prefix="/test", tags=["test"])

    return app


async def run_server():
    app = await create_app()
    # 初始化日志
    init_logging("logs/nanoai-hms/hwhms.log")
    init_nacos() 
    # 初始化 Nacos 和 AppConfig（确保控制器初始化之前执行）
    await NacosConfigs.init()
    await AppConfig.init()
    host = API_SERVER["host"]
    port = API_SERVER["port"]
    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config)
    await server.serve()



if __name__ == "__main__":
    asyncio.run(run_server())