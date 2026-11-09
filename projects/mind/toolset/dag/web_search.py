"""
联网检索工具：对应原 complex_reasoning_agent WebsearchAgent / QueryTools.websearch。
调用火山 Ark Bot 流式接口，取首包 references。
"""
import logging
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
            messages=[
                {"role": "system", "content": "summary必须包含用户问题的答案"},
                {"role": "user", "content": query}],
            stream=True
        )
        async for chunk in stream:
            if hasattr(chunk, "references") and chunk.references:
                return [item for item in chunk.references]
        return []
    except Exception as e:
        logger.warning("websearch bot error: %s", e)
        return []

class WebsearchInput(BaseModel):
    query: str = Field(description="中心词和搜索条件")


class WebsearchToolOutput(BaseModel):
    """联网检索工具输出（强类型，仅 error 路径使用；success 路径直接返回 list[dict]）。"""
    query: str
    references: list[dict] = Field(default_factory=list)
    message: str = ""


async def _websearch_worker(query: str) -> WebsearchToolOutput | list[dict]:
    try:
        return await websearch(query)
    except Exception as e:
        logger.exception("websearch error: %s", e)
        return WebsearchToolOutput(query=query, message=f"检索异常: {e}")


WebsearchWorker = Callable[..., Awaitable[WebsearchToolOutput | list[dict]]]


def WebsearchTool(worker: WebsearchWorker = _websearch_worker, *, timeout: float | None = None):
    """联网信息查询工具。"""
    tool = create_tool(
        name="WebSearch",
        description=(
            "网页搜索输出，支持多种搜索类型，可作为general search工具，当用户查询意图/信息无法通过其它search类工具获取时启用。"
            "输出：通用搜索结果列表"
        ),
        args_schema=WebsearchInput,
        worker=worker,
        timeout=timeout,
    )
    return tool
