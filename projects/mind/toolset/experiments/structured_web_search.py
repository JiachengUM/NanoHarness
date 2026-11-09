"""联网检索工具 v3：基于通用 search schema 的 Web 搜索实现。"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from aicore.tools import create_tool
from aicore.utils.nl_repr import nl_repr
from projects.mind.complex_reasoning.configs.config import get_app_config
from projects.mind.toolset.experiments.search_schema.search_schema import RangeValue, SearchValue
from projects.mind.toolset.experiments.search_schema.web_search_schema import (
    WebSearchBoolQuery,
    WebSearchPredicate,
    WebSearchQuery,
    WebSearchRequest,
)

__all__ = ["WebSearchRequest", "structured_web_search_tool", "generate_complete_search"]

logger = logging.getLogger(__name__)


def _compact(value: Any) -> str:
    return str(value).replace(" ", "")


def _as_list(value: SearchValue | None) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _format_range(value: SearchValue | None) -> str:
    if isinstance(value, RangeValue):
        return f"{value.start}..{value.end}"
    return _compact(value)


class SearchBuilder:
    """把 WebSearchRequest 编译成 Google 风格搜索字符串。"""

    def build(self, input_data: WebSearchRequest) -> str:
        return self._build_expression(input_data.query)

    def _build_expression(self, expr: WebSearchQuery) -> str:
        if isinstance(expr, WebSearchPredicate):
            return self._build_predicate(expr)
        if isinstance(expr, WebSearchBoolQuery):
            return self._build_bool(expr)
        raise ValueError(f"未知表达式类型: {type(expr)}")

    def _build_predicate(self, expr: WebSearchPredicate) -> str:
        if expr.op == "exists":
            return self._build_exists(expr)
        if expr.op in ("ne", "not_in"):
            return self._build_negative_predicate(expr)

        if expr.field == "text":
            return self._build_text(expr)
        if expr.field == "title":
            return self._build_text_position(expr, "intitle", "allintitle")
        if expr.field == "body":
            return self._build_text_position(expr, "intext", "allintext")
        if expr.field == "anchor":
            return self._build_text_position(expr, "inanchor", "allinanchor")
        if expr.field == "url":
            return self._build_prefixed_values("inurl", expr.value)
        if expr.field == "site":
            return self._build_prefixed_values("site", expr.value)
        if expr.field == "related_site":
            return f"related:{_compact(expr.value)}"
        if expr.field == "file_type":
            return self._build_prefixed_values("filetype", expr.value)
        if expr.field == "published_at":
            return self._build_published_at(expr)
        if expr.field == "number":
            return _format_range(expr.value)
        if expr.field == "price":
            return f"price:{_format_range(expr.value)}"
        if expr.field == "social_handle":
            return " ".join(f"@{_compact(item)}" for item in _as_list(expr.value))
        if expr.field == "source":
            return self._build_prefixed_values("source", expr.value)
        raise ValueError(f"未支持的 Web 搜索字段: {expr.field}")

    def _build_bool(self, expr: WebSearchBoolQuery) -> str:
        parts: list[str] = []

        for item in expr.must:
            parts.append(self._build_must_part(item))

        if expr.should:
            subq = self._build_should(expr.should)
            if subq:
                parts.append(subq)

        for item in expr.must_not:
            parts.append(self._build_must_not_part(item))

        return " ".join(filter(None, parts)).strip()

    def _build_must_part(self, item: WebSearchQuery) -> str:
        subq = self._build_expression(item)
        if isinstance(item, WebSearchBoolQuery) and item.must_not and not item.must and not item.should:
            return f"({subq})"
        if any(op in subq for op in [" OR ", " AND "]):
            return f"({subq})"
        return subq

    def _build_must_not_part(self, item: WebSearchQuery) -> str:
        subq = self._build_expression(item)
        if " " in subq:
            negative = f"-({subq})"
        else:
            negative = f"-{subq}"
        if any(op in negative for op in [" OR ", " AND "]):
            return f"({negative})"
        return negative

    def _build_should(self, items: list[WebSearchQuery]) -> str:
        subqueries: list[str] = []
        for item in items:
            subq = self._build_expression(item)
            if " " in subq:
                subqueries.append(f"({subq})")
            else:
                subqueries.append(subq)
        return " OR ".join(subqueries)

    def _build_text(self, expr: WebSearchPredicate) -> str:
        if expr.op == "match_phrase":
            return " ".join(f'"{_compact(item)}"' for item in _as_list(expr.value))
        if expr.op == "wildcard":
            return _compact(expr.value)
        return " ".join(_compact(item) for item in _as_list(expr.value))

    def _build_text_position(self, expr: WebSearchPredicate, any_prefix: str, all_prefix: str) -> str:
        values = _as_list(expr.value)
        if expr.op == "contains_all":
            return f"{all_prefix}:{' '.join(_compact(item) for item in values)}"
        if expr.op == "match_phrase":
            return " ".join(f'{any_prefix}:"{_compact(item)}"' for item in values)
        return " ".join(f"{any_prefix}:{_compact(item)}" for item in values)

    def _build_prefixed_values(self, prefix: str, value: SearchValue | None) -> str:
        return " ".join(f"{prefix}:{_compact(item)}" for item in _as_list(value))

    def _build_published_at(self, expr: WebSearchPredicate) -> str:
        if expr.op in ("gt", "gte"):
            return f"after:{_compact(expr.value)}"
        if expr.op in ("lt", "lte"):
            return f"before:{_compact(expr.value)}"
        if expr.op == "between" and isinstance(expr.value, RangeValue):
            parts = []
            if expr.value.start is not None:
                parts.append(f"after:{_compact(expr.value.start)}")
            if expr.value.end is not None:
                parts.append(f"before:{_compact(expr.value.end)}")
            return " ".join(parts)
        return _compact(expr.value)

    def _build_exists(self, expr: WebSearchPredicate) -> str:
        if expr.field == "site":
            return "site:*"
        if expr.field == "file_type":
            return "filetype:*"
        return _compact(expr.field)

    def _build_negative_predicate(self, expr: WebSearchPredicate) -> str:
        positive = expr.model_copy(update={"op": "in" if expr.op == "not_in" else "eq"})
        subq = self._build_predicate(positive)
        if " " in subq:
            return f"-({subq})"
        return f"-{subq}"


def generate_complete_search(input_data: WebSearchRequest) -> str:
    builder = SearchBuilder()
    return builder.build(input_data)


async def websearch(kwargs) -> list[dict]:
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
        expression = WebSearchRequest.model_validate(kwargs)
        query = generate_complete_search(expression)
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


class WebsearchReference(BaseModel):
    """单条联网检索参考。"""

    site_name: str = ""
    title: str = ""
    publish_time: str = ""
    summary: str = ""


class WebsearchToolOutput(BaseModel):
    """联网检索工具输出（强类型）。"""

    query: str
    references: list[WebsearchReference] = Field(default_factory=list)
    message: str = ""


async def _websearch_worker(**kwargs) -> WebsearchToolOutput:
    try:
        refs = await websearch(kwargs)
        return WebsearchToolOutput(
            query=nl_repr(kwargs),
            references=[WebsearchReference.model_validate(item) for item in refs],
            message=f"共 {len(refs)} 条参考" if refs else "未找到结果",
        )
    except Exception as e:
        logger.exception("websearch error: %s", e)
        return WebsearchToolOutput(query=nl_repr(kwargs), message=f"检索异常: {e}")


WebsearchWorker = Callable[..., Awaitable[WebsearchToolOutput]]


def structured_web_search_tool(worker: WebsearchWorker = _websearch_worker, *, timeout: float | None = None):
    """联网信息查询工具。"""
    return create_tool(
        name="structured_web_search",
        description="通用联网搜索，使用 Predicate/BoolQuery 结构化表达 Web 搜索需求",
        args_schema=WebSearchRequest,
        worker=worker,
        timeout=timeout,
    )
