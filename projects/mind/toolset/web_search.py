"""
联网检索工具：对应原 complex_reasoning_agent WebsearchAgent / QueryTools.websearch。
调用火山 Ark Bot 流式接口，取首包 references。
"""
import logging
from typing import List
from typing import Callable, Awaitable

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from aicore.tools import create_tool

from projects.mind.complex_reasoning.configs.config import get_app_config

__all__ = ["WebsearchInput", "WebsearchTool"]

logger = logging.getLogger(__name__)


async def websearch(query: str) -> list[dict]:
    """联网检索：调用配置的 Bot，流式首包中的 references。"""
    cfg = get_app_config()
    if not getattr(cfg, "WEBSEARCH_BOT_API_KEY", None) or not getattr(cfg, "WEBSEARCH_BOT_MODEL", None):
        logger.warning("WEBSEARCH_BOT_API_KEY 或 WEBSEARCH_BOT_MODEL 未配置，联网检索不可用")
        return []

    client = AsyncOpenAI(
        base_url=cfg.WEBSEARCH_BOT_BASE_URL,
        api_key=cfg.WEBSEARCH_BOT_API_KEY,
    )
    try:
        stream = await client.chat.completions.create(
            model=cfg.WEBSEARCH_BOT_MODEL,
            messages=[{"role": "user", "content": query}],
            stream=True,
        )
        async for chunk in stream:
            if hasattr(chunk, "references") and chunk.references:
                return [
                    {
                        "site_name": item.get("site_name", ""),
                        "title": item.get("title", ""),
                        "publish_time": item.get("publish_time", ""),
                        "summary": item.get("summary", ""),
                    }
                    for item in chunk.references
                ]
        return []
    except Exception as e:
        logger.warning("websearch bot error: %s", e)
        return []


class WebsearchInput(BaseModel):
    # 联网检索关键词。
    
    # query: str = Field(description="要在网络上搜索的信息描述，通用检索适用，不适用于电商、本地生活等垂直搜索")
    query: str = Field(description="搜索关键词")


class WebsearchReference(BaseModel):
    """单条联网检索参考。"""
    site_name: str = ""
    title: str = ""
    publish_time: str = ""
    summary: str = ""


class WebsearchToolOutput(BaseModel):
    """联网检索工具输出（强类型）。"""
    query: str
    references: List[WebsearchReference] = Field(default_factory=list)
    message: str = ""


async def _websearch_worker(query: str) -> WebsearchToolOutput:
    try:
        refs = await websearch(query)
        return WebsearchToolOutput(
            query=query,
            references=[WebsearchReference.model_validate(item) for item in refs],
            message=f"共 {len(refs)} 条参考" if refs else "未找到结果",
        )
    except Exception as e:
        logger.exception("websearch error: %s", e)
        return WebsearchToolOutput(query=query, message=f"检索异常: {e}")


WebsearchWorker = Callable[..., Awaitable[WebsearchToolOutput]]


def WebsearchTool(worker: WebsearchWorker = _websearch_worker, *, timeout: float | None = None):
    """联网信息查询工具。"""
    return create_tool(
        name="websearch",
        description="通用联网搜索",
        args_schema=WebsearchInput,
        worker=worker,
        timeout=timeout,
    )
