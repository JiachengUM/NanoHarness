import asyncio
import sys
import uuid

import uvicorn
import sys
print("Python模块搜索路径：")
for i, path in enumerate(sys.path, 1):
    print(f"{i}. {path}")
from projects.uiagent.server.app_factory import create_app
from projects.uiagent.server.configs.log_init import init_logging
from projects.uiagent.server.configs.nacos_util import init_nacos
from projects.uiagent.server.configs.trace_id_filter import trace_id_context

DEFAULT_BIND_HOST = "0.0.0.0" if sys.platform != "win32" else "127.0.0.1"

API_SERVER = {
    "host": DEFAULT_BIND_HOST,
    "port": 9001,
}


async def run_api_server():
    app = await create_app()
    host = API_SERVER["host"]
    port = API_SERVER["port"]
    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    # 设置启动时的 trace_id
    startup_trace_id = f"startup-{uuid.uuid4().hex}"
    trace_id_context.set(startup_trace_id)
    init_logging("volc-llm-nanoai-agent.log")
    init_nacos()
    await run_api_server()


if __name__ == "__main__":
    asyncio.run(main())
