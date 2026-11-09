import httpx
from typing import Optional
from nanoai.utils import logger

# 全局异步客户端
GLOBAL_HTTPX_CLIENT: Optional[httpx.AsyncClient] = None


async def init_httpx_client() -> None:
    """初始化全局httpx异步客户端，可在项目启动时调用"""
    global GLOBAL_HTTPX_CLIENT
    if GLOBAL_HTTPX_CLIENT is None:
        GLOBAL_HTTPX_CLIENT = httpx.AsyncClient(
            timeout=60,  # 全局默认超时时间
        )
        logger.info("全局httpx异步客户端初始化成功 | init_httpx_client")


# 销毁方法，优雅释放资源
async def close_httpx_client() -> None:
    """关闭全局httpx异步客户端，项目关闭时调用"""
    global GLOBAL_HTTPX_CLIENT
    if GLOBAL_HTTPX_CLIENT and not GLOBAL_HTTPX_CLIENT.is_closed:
        await GLOBAL_HTTPX_CLIENT.aclose()
        GLOBAL_HTTPX_CLIENT = None
        logger.info("全局httpx异步客户端已优雅关闭 | close_httpx_client")


def get_httpx_client() -> httpx.AsyncClient:
    if GLOBAL_HTTPX_CLIENT is None:
        raise RuntimeError("HTTPX client没被初始化")
    return GLOBAL_HTTPX_CLIENT
