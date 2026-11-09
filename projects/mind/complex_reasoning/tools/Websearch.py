"""
联网检索工具：对应原 complex_reasoning_agent WebsearchAgent / QueryTools.websearch。
调用火山 Ark Bot 流式接口，取首包 references。
"""
import logging
from typing import List

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from aicore.tools import BaseTool

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
    """联网检索关键词。"""
    query: str = Field(
        description="要在网络上搜索的信息描述，通用检索适用，不适用于电商、本地生活等垂直搜索"
    )


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


class WebsearchTool(BaseTool):
    """联网信息查询工具。调用火山 Bot 获取 references。"""
    name: str = "websearch"
    description: str = "通用联网搜索，获取网络上的基础信息。不适用于垂直领域（如电商、本地生活攻略）。"
    args_schema: type[BaseModel] = WebsearchInput

    def _run(self, query: str) -> dict:
        raise NotImplementedError("联网检索请使用异步调用 ainvoke/astream")

    async def _arun(self, query: str) -> WebsearchToolOutput:
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
