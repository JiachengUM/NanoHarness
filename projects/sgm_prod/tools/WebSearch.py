import logging

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from aicore.tools import create_tool
from projects.mind.complex_reasoning.configs.config import get_app_config

__all__ = ["WebsearchInput", "WebsearchToolOutput", "WebsearchWorker", "create_websearch_tool"]

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


class WebsearchInput(BaseModel):
    # 联网检索关键词。
    query: str = Field(description="要在网络上搜索的信息描述，通用检索适用，不适用于电商、本地生活等垂直搜索")


class WebsearchReference(BaseModel):
    """单条联网检索参考。"""
    site_name: str = ""
    title: str = ""
    publish_time: str = ""
    summary: str = ""


class WebsearchToolOutput(BaseModel):
    """联网检索工具输出。"""
    query: str
    references: list[WebsearchReference] = Field(default_factory=list)
    message: str = ""


class WebsearchWorker:
    """联网搜索 worker，提供 async __call__ 接口。"""

    async def _run(self, query: str) -> WebsearchToolOutput:
        refs = await websearch(query)
        return WebsearchToolOutput(
            query=query,
            references=[WebsearchReference.model_validate(item) for item in refs],
            message=f"共 {len(refs)} 条参考" if refs else "未找到结果",
        )

    async def __call__(self, query: str) -> WebsearchToolOutput:
        return await self._run(query)


def create_websearch_tool():
    """联网信息查询工具工厂。"""
    return create_tool(
        name="websearch",
        description="通用联网搜索，获取网络上的基础信息",
        args_schema=WebsearchInput,
        worker=WebsearchWorker(),
    )
