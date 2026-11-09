"""QQ 音乐搜索 v2：基于通用 search schema 的音乐检索工具。

QQ 音乐 custom search 当前只支持关键词 w、搜索类型 t、分页 p/num。
因此 v2 的策略是：
1. 从 MusicSearchRequest 中抽取可下推到 w 的召回关键词；
2. 调用 QQ 音乐接口召回候选；
3. 把完整结构化查询和候选结果交给 LLM 判断，不做程序后过滤。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from aicore.models.credentials import AsyncArk, ModelName, create_client
from aicore.models.responses import ainvoke
from aicore.tools import create_tool
from aicore.utils.nl_repr import nl_repr
from projects.mind.toolset.music_search import (
    AlbumItem,
    AlbumSearchOutput,
    PlaylistItem,
    PlaylistSearchOutput,
    SongItem,
    SongSearchOutput,
    search_album,
    search_playlist,
    search_song,
)
from projects.mind.toolset.experiments.search_schema.music_search_schema import (
    MusicSearchBoolQuery,
    MusicSearchPredicate,
    MusicSearchQuery,
    MusicSearchRequest,
)
from projects.mind.toolset.experiments.search_schema.search_schema import RangeValue, SearchValue


RECALL_FIELDS = {
    "text",
    "track_title",
    "artist",
    "album",
    "playlist_title",
    "lyrics",
    "genre",
}

NEGATIVE_OPERATORS = {"ne", "not_in"}

DEFAULT_RECALL_QUERY: dict[str, str] = {
    "track": "音乐",
    "album": "专辑",
    "playlist": "歌单",
    "artist": "歌手",
}


class MusicSearchV2Params(BaseModel):
    """音乐搜索 v2 算法参数。"""

    model: str = Field(default=ModelName.SEED_1_6_FLASH_250828)

    @property
    def client(self) -> AsyncArk:
        m = ModelName(self.model)
        client, _ = create_client(m, AsyncArk)
        return client


MusicSearchV2Output = SongSearchOutput | PlaylistSearchOutput | AlbumSearchOutput | str
MusicSearchV2Worker = Callable[..., Awaitable[MusicSearchV2Output]]
StructuredMusicEntityType = Literal["track", "playlist", "album"]


class StructuredMusicSearchRequest(MusicSearchRequest):
    """结构化音乐搜索请求。"""

    target: StructuredMusicEntityType = Field(
        default="track",
        description="搜索目标：track=单曲，playlist=歌单，album=专辑",
    )


def _value_to_recall_terms(value: SearchValue | None) -> list[str]:
    if value is None or isinstance(value, RangeValue):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def extract_recall_terms(query: MusicSearchQuery) -> list[str]:
    """抽取 QQ 音乐接口可下推到 w 的召回关键词。"""

    if isinstance(query, MusicSearchPredicate):
        if query.field not in RECALL_FIELDS or query.op in NEGATIVE_OPERATORS:
            return []
        return _value_to_recall_terms(query.value)

    if isinstance(query, MusicSearchBoolQuery):
        terms: list[str] = []
        for item in query.must:
            terms.extend(extract_recall_terms(item))
        for item in query.should:
            terms.extend(extract_recall_terms(item))
        return terms

    return []


def generate_recall_query(input_data: MusicSearchRequest) -> str:
    terms = _dedupe_keep_order(extract_recall_terms(input_data.query))
    if terms:
        return " ".join(terms)
    return DEFAULT_RECALL_QUERY.get(input_data.target, "音乐")


def _candidate_dicts(items: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        if hasattr(item, "to_dict"):
            result.append(item.to_dict())
        elif hasattr(item, "model_dump"):
            result.append(item.model_dump())
        else:
            result.append({"value": item})
    return result


class QQMusicSearchV2Worker:
    """使用 MusicSearchRequest 搜索 QQ 音乐，并由 LLM 判断结构化条件。"""

    def __init__(self, params: MusicSearchV2Params | None = None):
        self.params = params or MusicSearchV2Params()

    async def __call__(self, **kwargs: Any) -> MusicSearchV2Output:
        request = StructuredMusicSearchRequest.model_validate(kwargs)
        return await self.execute(request)

    async def execute(self, request: StructuredMusicSearchRequest) -> MusicSearchV2Output:
        recall_query = generate_recall_query(request)
        num = min(max(request.limit or 10, 1), 50)
        items: list[SongItem] | list[PlaylistItem] | list[AlbumItem] = await self._recall(request.target, recall_query, num)
        if not items:
            return f"未召回到候选音乐；QQ音乐召回关键词：{recall_query}"
        return await self._judge_by_llm(request, recall_query, items)

    async def _recall(
        self,
        target: StructuredMusicEntityType,
        recall_query: str,
        num: int,
    ) -> list[SongItem] | list[PlaylistItem] | list[AlbumItem]:
        if target == "playlist":
            return await search_playlist(recall_query, num=num)
        if target == "album":
            return await search_album(recall_query, num=num)
        return await search_song(recall_query, num=num)

    async def _judge_by_llm(
        self,
        request: MusicSearchRequest,
        recall_query: str,
        items: list[Any],
    ) -> str:
        prompt = f"""你需要从 QQ 音乐接口召回的候选结果中，筛选出符合结构化搜索需求的音乐内容。

重要背景：
1. QQ 音乐搜索接口当前只能通过关键词 w 召回候选，不能把歌手、风格、语言、发行时间、BPM、版本类型等条件作为接口参数精确过滤。
2. 本次实际下推到 QQ 音乐接口的召回关键词是：{recall_query}
3. 你必须根据完整结构化搜索需求判断候选结果，而不是只根据召回关键词判断。
4. must 表示必须满足；should 表示偏好或满足其一，minimum_should_match 表示 should 至少满足数量；must_not 表示必须排除。
5. 如果候选字段不足以判断某个条件，请明确说明“不确定/字段不足”，不要编造候选中没有的信息。
6. 如果没有完全满足的结果，可以返回部分满足的候选，并说明每个候选满足和未满足的条件。

完整结构化搜索需求：
{nl_repr(request.model_dump(mode="json"))}

候选结果：
{nl_repr(_candidate_dicts(items))}

请返回通过筛选的音乐详细信息，并说明筛选依据。如果筛选不出来，请说明原因。
"""
        rsp = await ainvoke(prompt, client=self.params.client, model=self.params.model)
        return rsp.raw_text


def structured_music_search_tool(
    worker: MusicSearchV2Worker | None = None,
    *,
    timeout: float | None = None,
    with_clarify: bool = True,
):
    """基于通用 search schema 的 QQ 音乐搜索工具。"""

    return create_tool(
        name="structured_music_search",
        description="搜索符合结构化条件的音乐内容，可召回单曲、歌单或专辑。",
        args_schema=StructuredMusicSearchRequest,
        worker=worker or QQMusicSearchV2Worker(),
        timeout=timeout,
        with_clarify=with_clarify,
    )


__all__ = [
    "MusicSearchV2Params",
    "MusicSearchV2Output",
    "MusicSearchV2Worker",
    "StructuredMusicEntityType",
    "StructuredMusicSearchRequest",
    "extract_recall_terms",
    "generate_recall_query",
    "structured_music_search_tool",
]
