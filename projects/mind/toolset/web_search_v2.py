"""
联网检索工具：对应原 complex_reasoning_agent WebsearchAgent / QueryTools.websearch。
调用火山 Ark Bot 流式接口，取首包 references。
"""
import logging
from typing import Callable, Awaitable, List, Optional, Literal, Annotated, Union

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from aicore.tools import create_tool
from aicore.utils.nl_repr import nl_repr

from projects.mind.complex_reasoning.configs.config import get_app_config

__all__ = ["WebsearchInput", "WebsearchTool"]

logger = logging.getLogger(__name__)

FileType = Literal[
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "txt", "rtf", "csv", "xml", "html", "htm",
    "zip", "rar", "tar", "gz",
    "jpg", "jpeg", "png", "gif", "bmp", "svg",
    "mp3", "mp4", "avi", "mov", "wmv", "flv"
]

LogicalExpression = Union["AtomicQuery", "AndGroup", "OrGroup", "NotGroup"]

class AtomicQuery(BaseModel):
    # 基础文本
    text: Optional[str] = Field(None, description="基础搜索文本")

    # 基础逻辑与模糊匹配算子
    exact_match: Optional[List[str]] = Field(None, description="精确匹配词组列表（强制完整顺序）")
    wildcard: Optional[str] = Field(None, description="通配符（替代未知字词）")
    exclude: Optional[List[str]] = Field(None, description="排除词列表")

    # 站内与网站级算子
    site: Optional[List[str]] = Field(None, description="限定网站/域名列表")
    related: Optional[str] = Field(None, description="查找同类/相关网站")

    # 内容位置定位算子
    intitle: Optional[List[str]] = Field(None, description="标题包含关键词列表（OR关系）")
    allintitle: Optional[List[str]] = Field(None, description="标题全包含关键词列表（AND关系）")
    intext: Optional[List[str]] = Field(None, description="正文包含关键词列表（OR关系）")
    allintext: Optional[List[str]] = Field(None, description="正文全包含关键词列表（AND关系）")
    inanchor: Optional[List[str]] = Field(None, description="锚文本包含关键词列表（OR关系）")
    allinanchor: Optional[List[str]] = Field(None, description="锚文本全包含关键词列表（AND关系）")

    # 文件与资源筛选算子
    filetype: Optional[List[FileType]] = Field(None, description="文件类型列表")

    # 时间与数值范围算子
    range_num: Optional[str] = Field(None, description="数值范围（如 100..200）")
    after: Optional[str] = Field(None, description="时间筛选（指定日期后）")
    before: Optional[str] = Field(None, description="时间筛选（指定日期前）")

    # 即时信息与工具类算子
    # define: Optional[str] = Field(None, description="词典定义")
    # weather: Optional[str] = Field(None, description="天气查询")
    # stocks: Optional[str] = Field(None, description="股票行情")
    # map: Optional[str] = Field(None, description="强制地图")
    # movie: Optional[str] = Field(None, description="电影信息")
    # unit_convert: Optional[str] = Field(None, description="单位换算")
    # news_source: Optional[str] = Field(None, description="新闻来源筛选")

    # 社交与电商算子
    social_mention: Optional[str] = Field(None, description="社交媒体提及")
    price_filter: Optional[str] = Field(None, description="价格筛选")


# ========== 逻辑组合器 ==========
class AndGroup(BaseModel):
    # AND 逻辑组：所有条件必须同时满足
    and_: List[LogicalExpression] = Field(..., alias="and", description="AND组合的子条件列表")


class OrGroup(BaseModel):
    # OR 逻辑组：满足任一条件即可
    or_: List[LogicalExpression] = Field(..., alias="or", description="OR组合的子条件列表")


class NotGroup(BaseModel):
    # NOT 逻辑组：排除指定条件
    not_: LogicalExpression = Field(..., alias="not", description="要排除的条件")


class WebsearchInput(BaseModel):
    query: LogicalExpression = Field(..., description="搜索表达式，支持嵌套组合")

    # 特殊即时功能（这些通常不参与逻辑组合）
    # define: Optional[str] = Field(None, description="词典定义（独立功能）")
    # weather: Optional[str] = Field(None, description="天气查询（独立功能）")
    # stocks: Optional[str] = Field(None, description="股票行情（独立功能）")
    # map: Optional[str] = Field(None, description="强制地图（独立功能）")
    # movie: Optional[str] = Field(None, description="电影信息（独立功能）")


class SearchBuilder:
    def build(self, input_data: WebsearchInput) -> str:
        """生成完整的Google搜索字符串"""

        # 处理独立即时功能（优先级最高）
        # special_queries = []
        # if input_data.define:
        #     special_queries.append(f"define:{input_data.define}")
        # if input_data.weather:
        #     special_queries.append(f"weather:{input_data.weather}")
        # if input_data.stocks:
        #     special_queries.append(f"stocks:{input_data.stocks}")
        # if input_data.map:
        #     special_queries.append(f"map:{input_data.map}")
        # if input_data.movie:
        #     special_queries.append(f"movie:{input_data.movie}")
        #
        # if special_queries:
        #     return " ".join(special_queries)

        # 处理逻辑查询
        return self._build_expression(input_data.query)

    def _build_expression(self, expr: LogicalExpression) -> str:
        """递归构建表达式"""
        if isinstance(expr, AtomicQuery):
            return self._build_atomic(expr)
        elif isinstance(expr, AndGroup):
            return self._build_and(expr)
        elif isinstance(expr, OrGroup):
            return self._build_or(expr)
        elif isinstance(expr, NotGroup):
            return self._build_not(expr)
        else:
            raise ValueError(f"未知表达式类型: {type(expr)}")

    def _build_atomic(self, atomic: AtomicQuery) -> str:
        # 构建原子查询
        parts = []

        # 1. 基础文本
        if atomic.text:
            parts.append(atomic.text.replace(" ", ""))

        # 2. 精确匹配（引号包裹）
        if atomic.exact_match:
            for phrase in atomic.exact_match:
                parts.append(f'"{phrase.replace(" ", "")}"')

        # 3. 通配符
        if atomic.wildcard:
            parts.append(atomic.wildcard.replace(" ", ""))

        # 4. 排除词
        if atomic.exclude:
            for word in atomic.exclude:
                parts.append(f"-{word.replace(" ", "")}")

        # 5. 站点限制
        if atomic.site:
            for site in atomic.site:
                parts.append(f"site:{site.replace(" ", "")}")

        # 6. 相关网站
        if atomic.related:
            parts.append(f"related:{atomic.related.replace(" ", "")}")

        # 7. 标题相关
        if atomic.intitle:
            for word in atomic.intitle:
                parts.append(f"intitle:{word.replace(" ", "")}")
        if atomic.allintitle:
            parts.append(f"allintitle:{' '.join([word.replace(" ", "") for word in atomic.allintitle])}")

        # 8. 正文相关
        if atomic.intext:
            for word in atomic.intext:
                parts.append(f"intext:{word.replace(" ", "")}")
        if atomic.allintext:
            parts.append(f"allintext:{' '.join([word.replace(" ", "") for word in atomic.allintext])}")

        # 9. 锚文本相关
        if atomic.inanchor:
            for word in atomic.inanchor:
                parts.append(f"inanchor:{word.replace(" ", "")}")
        if atomic.allinanchor:
            parts.append(f"allinanchor:{' '.join([word.replace(" ", "") for word in atomic.allinanchor])}")

        # 10. 文件类型
        if atomic.filetype:
            for ft in atomic.filetype:
                parts.append(f"filetype:{ft.replace(" ", "")}")

        # 11. 数值范围
        if atomic.range_num:
            parts.append(f"{atomic.range_num.replace(" ", "")}")

        # 12. 时间范围
        if atomic.after:
            parts.append(f"after:{atomic.after.replace(" ", "")}")
        if atomic.before:
            parts.append(f"before:{atomic.before.replace(" ", "")}")

        # 13. 其他即时功能（在原子查询中）
        # if atomic.define:
        #     parts.append(f"define:{atomic.define}")
        # if atomic.weather:
        #     parts.append(f"weather:{atomic.weather}")
        # if atomic.stocks:
        #     parts.append(f"stocks:{atomic.stocks}")
        # if atomic.map:
        #     parts.append(f"map:{atomic.map}")
        # if atomic.movie:
        #     parts.append(f"movie:{atomic.movie}")

        # 14. 单位换算
        # if atomic.unit_convert:
        #     parts.append(f"{atomic.unit_convert}")

        # 15. 新闻来源
        # if atomic.news_source:
        #     parts.append(f"source:{atomic.news_source}")

        # 16. 社交媒体提及
        if atomic.social_mention:
            parts.append(f"@{atomic.social_mention.replace(" ", "")}")

        # 17. 价格筛选
        if atomic.price_filter:
            parts.append(f"price:{atomic.price_filter.replace(" ", "")}")

        return " ".join(filter(None, parts)).strip()

    def _build_and(self, group: AndGroup) -> str:
        # 构建AND组
        subqueries = []
        for expr in group.and_:
            subq = self._build_expression(expr)
            # 判断是否需要括号
            if any(op in subq for op in [" OR ", " AND "]):
                subqueries.append(f"({subq})")
            else:
                subqueries.append(subq)
        return " ".join(subqueries)

    def _build_or(self, group: OrGroup) -> str:
        # 构建OR组
        subqueries = []
        for expr in group.or_:
            subq = self._build_expression(expr)
            if " " in subq:
                subqueries.append(f"({subq})")
            else:
                subqueries.append(subq)
        return " OR ".join(subqueries)

    def _build_not(self, group: NotGroup) -> str:
        # 构建NOT组
        subq = self._build_expression(group.not_)
        if " " in subq:
            return f"-({subq})"
        return f"-{subq}"

def generate_complete_search(input_data: WebsearchInput) -> str:
    # 生成完整的搜索结果
    builder = SearchBuilder()
    query_str = builder.build(input_data)
    return query_str

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
        expression = WebsearchInput.model_validate(kwargs)
        query = generate_complete_search(expression)
        stream = await client.chat.completions.create(
            model=cfg.WEBSEARCH_BOT_MODEL,
            messages=[{"role": "user", "content": query}],
            stream=True
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
    references: List[WebsearchReference] = Field(default_factory=list)
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


def WebsearchTool(worker: WebsearchWorker = _websearch_worker, *, timeout: float | None = None):
    """联网信息查询工具。"""
    return create_tool(
        name="websearch",
        description="""通用联网搜索，运用逻辑运算符和算子结构化表达用户搜索需求，每个关键词不能有空格""",
        args_schema=WebsearchInput,
        worker=worker,
        timeout=timeout,
    )