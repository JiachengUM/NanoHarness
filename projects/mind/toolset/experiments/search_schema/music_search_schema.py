"""Music search domain schema.

这里只定义音乐检索领域的字段和请求结构，不负责调用 QQ 音乐或做后处理筛选。
TODO: 这里的术语和 qq music 接口不完全一致, 需要在 tool 内做一层翻译
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


MusicEntityType = Literal["track", "album", "playlist", "artist"]
MusicVersionType = Literal["original", "live", "cover", "remix", "acoustic", "demo", "instrumental"]

MusicSearchField = Literal[
    "text",
    "entity_type",
    "track_title",
    "artist",
    "album",
    "playlist_title",
    "lyrics",
    "genre",
    "mood",
    "language",
    "scene",
    "bpm",
    "release_date",
    "release_year",
    "duration_seconds",
    "version_type",
    "is_cover",
    "is_live",
    "popularity",
]

MusicSearchQuery = Union["MusicSearchPredicate", "MusicSearchBoolQuery"]


class MusicSearchPredicate(Predicate):
    """音乐搜索领域原子条件。"""

    field: MusicSearchField = Field(..., description="音乐搜索字段")
    value: SearchValue | list[MusicEntityType] | list[MusicVersionType] | None = Field(
        default=None,
        description="音乐字段条件值",
    )


class MusicSearchBoolQuery(BoolQuery):
    """音乐搜索领域布尔查询。"""

    must: list[MusicSearchQuery] = Field(default_factory=list, description="必须满足")
    should: list[MusicSearchQuery] = Field(default_factory=list, description="最好满足，可作为偏好")
    must_not: list[MusicSearchQuery] = Field(default_factory=list, description="必须排除")


class MusicSearchRequest(SearchSchemaModel):
    """音乐搜索领域请求结构。"""

    domain: Literal["music"] = Field(default="music", description="搜索领域")
    target: MusicEntityType = Field(default="track", description="期望召回的音乐实体类型")
    query: MusicSearchQuery = Field(..., description="音乐查找表达式")
    sort: list[SortSpec] = Field(default_factory=list, description="排序偏好")
    limit: int | None = Field(default=None, ge=1, description="期望返回数量")


MUSIC_SEARCH_DOMAIN_SCHEMA = DomainSchema(
    domain="music",
    description="歌曲、歌手、专辑、歌单等音乐内容检索领域",
    default_query_fields=["text", "track_title", "artist", "album", "lyrics"],
    default_sort=[SortSpec(field="popularity", order="desc")],
    fields={
        "text": SearchFieldSpec(
            name="text",
            value_type="text",
            operators=["match", "match_phrase", "contains", "contains_all"],
            description="音乐综合文本召回字段，可包含歌名、歌手、专辑、风格等",
            examples=["周杰伦 晴天", "跑步 英文 电子"],
        ),
        "entity_type": SearchFieldSpec(
            name="entity_type",
            value_type="enum",
            operators=["eq", "in"],
            description="音乐实体类型",
            values=list(MusicEntityType.__args__),
            examples=["track", "playlist"],
        ),
        "track_title": SearchFieldSpec(
            name="track_title",
            value_type="text",
            operators=["eq", "match", "match_phrase", "contains", "contains_all"],
            description="歌曲名",
            examples=["晴天", "告白气球"],
        ),
        "artist": SearchFieldSpec(
            name="artist",
            value_type="text",
            operators=["eq", "in", "match", "contains"],
            description="歌手、乐队或作曲家",
            examples=["周杰伦", "Taylor Swift"],
        ),
        "album": SearchFieldSpec(
            name="album",
            value_type="text",
            operators=["eq", "match", "contains"],
            description="专辑名",
            examples=["叶惠美"],
        ),
        "playlist_title": SearchFieldSpec(
            name="playlist_title",
            value_type="text",
            operators=["eq", "match", "contains"],
            description="歌单名",
            examples=["华语流行", "跑步歌单"],
        ),
        "lyrics": SearchFieldSpec(
            name="lyrics",
            value_type="text",
            operators=["match", "match_phrase", "contains", "contains_all"],
            description="歌词内容",
            examples=["雨", "一路向北"],
        ),
        "genre": SearchFieldSpec(
            name="genre",
            value_type="keyword",
            operators=["eq", "in", "match"],
            description="曲风或流派",
            examples=["民谣", "R&B", "electronic"],
        ),
        "mood": SearchFieldSpec(
            name="mood",
            value_type="keyword",
            operators=["eq", "in", "match"],
            description="情绪氛围",
            examples=["sad", "chill", "energetic"],
            notes="可能是语义标签或派生字段，例如由用户说的心情不好、想放松、想提神转换得到。",
        ),
        "language": SearchFieldSpec(
            name="language",
            value_type="keyword",
            operators=["eq", "in", "not_in"],
            description="歌曲语言",
            examples=["zh", "en", "粤语"],
        ),
        "scene": SearchFieldSpec(
            name="scene",
            value_type="keyword",
            operators=["eq", "in", "match"],
            description="使用场景",
            examples=["running", "driving", "sleep"],
            notes="通常不是后端原始字段，可能需要映射到 genre、mood、bpm 等字段。",
        ),
        "bpm": SearchFieldSpec(
            name="bpm",
            value_type="number",
            operators=["eq", "gt", "gte", "lt", "lte", "between"],
            sortable=True,
            description="歌曲速度",
            examples=[{"start": 120, "end": 140}],
        ),
        "release_date": SearchFieldSpec(
            name="release_date",
            value_type="date",
            operators=["eq", "gt", "gte", "lt", "lte", "between"],
            sortable=True,
            description="发行日期",
            examples=["2026-01-01"],
        ),
        "release_year": SearchFieldSpec(
            name="release_year",
            value_type="number",
            operators=["eq", "gt", "gte", "lt", "lte", "between"],
            sortable=True,
            description="发行年份",
            derived_from=["release_date"],
            examples=[2010],
        ),
        "duration_seconds": SearchFieldSpec(
            name="duration_seconds",
            value_type="duration",
            operators=["eq", "gt", "gte", "lt", "lte", "between"],
            sortable=True,
            description="歌曲时长，单位秒",
            examples=[240],
        ),
        "version_type": SearchFieldSpec(
            name="version_type",
            value_type="enum",
            operators=["eq", "in", "not_in"],
            description="歌曲版本类型",
            values=list(MusicVersionType.__args__),
            examples=["original", "live"],
        ),
        "is_cover": SearchFieldSpec(
            name="is_cover",
            value_type="bool",
            operators=["eq", "exists"],
            description="是否翻唱",
            examples=[False],
        ),
        "is_live": SearchFieldSpec(
            name="is_live",
            value_type="bool",
            operators=["eq", "exists"],
            description="是否现场版",
            examples=[False],
        ),
        "popularity": SearchFieldSpec(
            name="popularity",
            value_type="number",
            operators=["eq", "gt", "gte", "lt", "lte", "between"],
            sortable=True,
            description="热度、流行度或播放量归一化指标",
            examples=[80],
        ),
    },
)

MusicSearchRequest.domain_schema = MUSIC_SEARCH_DOMAIN_SCHEMA


__all__ = [
    "MusicEntityType",
    "MusicVersionType",
    "MusicSearchField",
    "MusicSearchQuery",
    "MusicSearchPredicate",
    "MusicSearchBoolQuery",
    "MusicSearchRequest",
    "MUSIC_SEARCH_DOMAIN_SCHEMA",
]
