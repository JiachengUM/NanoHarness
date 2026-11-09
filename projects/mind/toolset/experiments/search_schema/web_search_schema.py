"""Web search domain schema.

这里只定义 Web 检索领域的字段和请求结构，不负责把请求翻译成搜索引擎语法。
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import Field

from projects.mind.toolset.experiments.search_schema.search_schema import (
    BoolQuery,
    DomainSchema,
    Predicate,
    SearchFieldSpec,
    SearchSchemaModel,
    SearchValue,
    SortSpec,
)


FileType = Literal[
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "txt",
    "rtf",
    "csv",
    "xml",
    "html",
    "htm",
    "zip",
    "rar",
    "tar",
    "gz",
    "jpg",
    "jpeg",
    "png",
    "gif",
    "bmp",
    "svg",
    "mp3",
    "mp4",
    "avi",
    "mov",
    "wmv",
    "flv",
]

WebSearchField = Literal[
    "text",
    "title",
    "body",
    "anchor",
    "url",
    "site",
    "related_site",
    "file_type",
    "published_at",
    "number",
    "price",
    "social_handle",
    "source",
]

WebSearchQuery = Union["WebSearchPredicate", "WebSearchBoolQuery"]


class WebSearchPredicate(Predicate):
    """Web 搜索领域原子条件。"""

    field: WebSearchField = Field(..., description="Web 搜索字段")
    value: SearchValue | list[FileType] | None = Field(default=None, description="Web 字段条件值")


class WebSearchBoolQuery(BoolQuery):
    """Web 搜索领域布尔查询。"""

    must: list[WebSearchQuery] = Field(default_factory=list, description="必须满足")
    should: list[WebSearchQuery] = Field(default_factory=list, description="最好满足，可作为偏好")
    must_not: list[WebSearchQuery] = Field(default_factory=list, description="必须排除")


class WebSearchRequest(SearchSchemaModel):
    """Web 搜索领域请求结构。"""

    domain: Literal["web"] = Field(default="web", description="搜索领域")
    query: WebSearchQuery = Field(..., description="Web 查找表达式")
    sort: list[SortSpec] = Field(default_factory=list, description="排序偏好")
    limit: int | None = Field(default=None, ge=1, description="期望返回数量")


WEB_SEARCH_DOMAIN_SCHEMA = DomainSchema(
    domain="web",
    description="网页、文档、新闻、公开站点等通用联网检索领域",
    default_query_fields=["text", "title", "body"],
    fields={
        "text": SearchFieldSpec(
            name="text",
            value_type="text",
            operators=["match", "match_phrase", "contains", "contains_all", "wildcard"],
            description="网页综合文本召回字段",
            examples=["大语言模型 对齐 综述"],
        ),
        "title": SearchFieldSpec(
            name="title",
            value_type="text",
            operators=["match", "match_phrase", "contains", "contains_all", "wildcard"],
            description="网页标题",
            examples=["综述", "官方公告"],
        ),
        "body": SearchFieldSpec(
            name="body",
            value_type="text",
            operators=["match", "match_phrase", "contains", "contains_all", "wildcard"],
            description="网页正文",
            examples=["CVE", "性能对比"],
        ),
        "anchor": SearchFieldSpec(
            name="anchor",
            value_type="text",
            operators=["match", "match_phrase", "contains", "contains_all"],
            description="链接锚文本",
            examples=["下载", "官方文档"],
        ),
        "url": SearchFieldSpec(
            name="url",
            value_type="text",
            operators=["contains", "contains_all", "prefix", "wildcard", "regex"],
            description="网页 URL 或路径",
            examples=["opinion", "zhuanlan"],
        ),
        "site": SearchFieldSpec(
            name="site",
            value_type="keyword",
            operators=["eq", "in", "not_in"],
            description="站点或域名",
            examples=["react.dev", "reuters.com"],
        ),
        "related_site": SearchFieldSpec(
            name="related_site",
            value_type="keyword",
            operators=["eq"],
            description="查找同类或相关网站",
            examples=["openai.com"],
        ),
        "file_type": SearchFieldSpec(
            name="file_type",
            value_type="enum",
            operators=["eq", "in", "not_in"],
            description="资源文件类型",
            values=list(FileType.__args__),
            examples=["pdf"],
        ),
        "published_at": SearchFieldSpec(
            name="published_at",
            value_type="date",
            operators=["gt", "gte", "lt", "lte", "between"],
            sortable=True,
            description="网页发布时间",
            examples=["2026-01-01", {"start": "2025-01-01", "end": "2025-12-31"}],
        ),
        "number": SearchFieldSpec(
            name="number",
            value_type="number",
            operators=["eq", "gt", "gte", "lt", "lte", "between"],
            sortable=True,
            description="页面中出现的可比较数值",
            examples=[{"start": 100, "end": 200}],
        ),
        "price": SearchFieldSpec(
            name="price",
            value_type="number",
            operators=["eq", "gt", "gte", "lt", "lte", "between"],
            sortable=True,
            description="价格或预算相关数值",
            examples=[{"start": 2000, "end": 3000}],
        ),
        "social_handle": SearchFieldSpec(
            name="social_handle",
            value_type="keyword",
            operators=["eq", "in"],
            description="社交媒体账号或提及对象",
            examples=["openai"],
        ),
        "source": SearchFieldSpec(
            name="source",
            value_type="keyword",
            operators=["eq", "in", "not_in"],
            description="新闻或内容来源名称",
            examples=["BBC", "Reuters"],
        ),
    },
)

WebSearchRequest.domain_schema = WEB_SEARCH_DOMAIN_SCHEMA


__all__ = [
    "FileType",
    "WebSearchField",
    "WebSearchQuery",
    "WebSearchPredicate",
    "WebSearchBoolQuery",
    "WebSearchRequest",
    "WEB_SEARCH_DOMAIN_SCHEMA",
]
