"""
QQ 音乐开放 API 检索工具（单曲 / 歌单 / 专辑）。

单文件实现：
1. 通用 music_search 数据结构
2. 通用 SGMMusicWorker
3. QQ 原始数据模型、检索函数
4. 三个不带 planning + 三个带 planning，共 6 个工具
"""

from collections.abc import Awaitable, Callable
import hashlib
import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from aicore.models.credentials import AsyncArk, ModelName, create_client
from aicore.models.responses import ResponseParams, ainvoke
from aicore.tools import create_tool
from aicore.tools.experiments.goal_planner import StructuredGoal
from aicore.utils.nl_repr import nl_repr
from aicore.utils.volc_client.httpx_client import HttpClient, HttpxTransport
from projects.mind.complex_reasoning.configs.config import get_app_config

logger = logging.getLogger(__name__)

_http_client: HttpClient | None = None


def _get_client() -> HttpClient:
    global _http_client
    if _http_client is None:
        _http_client = HttpClient(
            HttpxTransport(httpx.AsyncClient(timeout=httpx.Timeout(5.0)))
        )
    return _http_client


def _qq_sign(params: dict[str, object], app_key: str) -> str:
    sorted_keys = sorted(k for k in params.keys() if k != "sign")
    sign_str = "&".join(f"{k}={params[k]}" for k in sorted_keys) + f"_{app_key}"
    return hashlib.md5(sign_str.encode()).hexdigest()


async def _qq_request(opi_cmd: str, additional: dict[str, object]) -> dict | None:
    cfg = get_app_config()
    params: dict[str, object] = {
        "opi_cmd": opi_cmd,
        "app_id": cfg.QQ_MUSIC_APP_ID,
        "timestamp": int(time.time()),
        "device_id": cfg.QQ_MUSIC_DEVICE_ID,
        "sign_version": "v2",
        **additional,
    }
    params["sign"] = _qq_sign(params, cfg.QQ_MUSIC_APP_KEY)
    try:
        resp = await _get_client().get(cfg.QQ_MUSIC_BASE_URL, params=params)
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        logger.warning("QQ 音乐请求异常: %s", e)
        return None
    if not isinstance(resp.json, dict):
        return None
    if resp.json.get("ret") == 0:
        return resp.json
    return None


# --- 通用 music_search 数据结构 ---


class MusicSearchInput(BaseModel):
    # 音乐搜索输入参数（单曲/歌单/专辑）。

    query: str = Field(..., description="支持搜索单曲名、歌手名、专辑名")
    criteria: list[str] | None = Field(
        default=None, description="音乐搜索条件列表，每条是一个自然语言约束"
    )


class MusicSearchGoal(StructuredGoal, MusicSearchInput):
    # 音乐搜索目标（planning 输入）。

    criteria: list[str] | None = Field(
        default=None, description="音乐搜索条件列表，每条是一个自然语言约束"
    )


class MusicSearchParams(BaseModel):
    """音乐搜索算法参数。"""

    model: str = Field(default=ModelName.SEED_1_6_FLASH_250828)

    @property
    def client(self) -> AsyncArk:
        m = ModelName(self.model)
        client, _ = create_client(m, AsyncArk)
        return client


class SGMMusicWorker:
    """
    通用音乐搜索 worker：
    - search_func：异步搜索函数，接受 query 返回原始 item 列表
    - output_cls：对应的输出类（SongSearchOutput/PlaylistSearchOutput/AlbumSearchOutput）
    - criteria 非空时叠加 LLM 筛选（使用 to_dict() 过滤展示字段）
    """

    def __init__(
        self,
        search_func: Callable[[str], Awaitable[list[Any]]],
        output_cls: type,
        params: MusicSearchParams | None = None,
    ):
        self.search_func = search_func
        self.output_cls = output_cls
        self.params = params or MusicSearchParams()

    def _to_output(self, items: list[Any]) -> Any:
        return self.output_cls(items=items)

    async def _filter_by_criteria(self, items: list[Any], criteria: list[str]) -> str:
        prompt = f"""你需要从下述给出的音乐中筛选出符合条件的。
{nl_repr([item.to_dict() for item in items])}

筛选条件和规则如下:
{nl_repr(criteria)}

请返回通过筛选的音乐的详细信息。如果筛选不出来，请说明原因。
"""
        rsp = await ainvoke(
            prompt,
            client=self.params.client,
            model=self.params.model,
            params=ResponseParams(thinking={"type": "disabled"}),
        )
        return rsp.raw_text

    async def __call__(self, query: str, criteria: list[str] | None = None) -> Any:
        items = await self.search_func(query)
        criteria = criteria or []
        if not criteria:
            return self._to_output(items)
        return await self._filter_by_criteria(items, criteria)


# --- QQ API 原始数据模型 ---


class SongItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # song_id: int = 0
    # song_mid: str = ""
    song_name: str = ""
    song_title: str = ""
    # singer_id: int = 0
    # singer_mid: str = ""
    singer_name: str = ""
    singer_title: str = ""
    # singer_pic: str = ""
    # album_id: int = 0
    # album_mid: str = ""
    album_name: str = ""
    # album_pic: str = ""
    # album_pic_150x150: str = ""
    # album_pic_300x300: str = ""
    # album_pic_500x500: str = ""
    # song_play_url: str = ""
    # song_play_url_standard: str = ""
    # song_play_url_hq: str = ""
    # song_play_url_sq: str = ""
    # song_play_time: int = 0
    # song_h5_url: str = ""
    # playable: int = 0
    # vip: int = 0
    # try_30s_url: str = ""
    # try_begin: int = 0
    # try_end: int = 0
    language: str = ""
    genre: str = ""
    author: str = ""
    public_time: str = ""
    # mv_id: int = 0
    # k_song_id: int = 0
    # k_song_mid: str = ""
    # isdigital_album: int = 0
    # origin: int = 0
    match_lyric: str = ""
    # unplayable_code: int = 0
    # unplayable_msg: str = ""

    # song_name: str = ""
    # song_title: str = ""
    # singer_name: str = ""
    # album_name: str = ""
    # genre: str = ""
    # public_time: str = ""
    # author: str = ""
    # match_lyric: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class PlaylistItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # dissid: str = ""
    dissname: str = ""
    creator_name: str = ""
    creator_uin: str = ""
    imgurl: str = ""
    song_count: int = 0
    # listen_count: int = 0
    createtime: int = 0
    diss_cover: str = ""
    diss_tags: str = ""
    intro: str = ""

    # dissname: str = ""
    # creator_name: str = ""
    # intro: str = ""
    # diss_tags: str = ""
    # song_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class AlbumItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # album_id: int = 0
    # album_mid: str = ""
    album_name: str = ""
    # album_pic: str = ""
    # album_pic_150x150: str = ""
    # album_pic_300x300: str = ""
    # album_pic_500x500: str = ""
    # singer_id: int = 0
    # singer_mid: str = ""
    singer_name: str = ""
    # singer_pic: str = ""
    public_time: str = ""
    company: str = ""
    genre: str = ""
    language: str = ""
    # aalbum_id: int = 0
    intro: str = ""
    song_count: int = 0
    # isdigital_album: int = 0

    # album_name: str = ""
    # singer_name: str = ""
    # genre: str = ""
    # language: str = ""
    # public_time: str = ""
    # company: str = ""
    # intro: str = ""
    # song_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


# --- 三种输出类型 ---


class SongSearchOutput(BaseModel):
    items: list[SongItem] = Field(
        default_factory=list, description="符合条件的单曲列表"
    )


class PlaylistSearchOutput(BaseModel):
    items: list[PlaylistItem] = Field(
        default_factory=list, description="符合条件的歌单列表"
    )


class AlbumSearchOutput(BaseModel):
    items: list[AlbumItem] = Field(
        default_factory=list, description="符合条件的专辑列表"
    )


SongSearchOutputLike = SongSearchOutput | str
PlaylistSearchOutputLike = PlaylistSearchOutput | str
AlbumSearchOutputLike = AlbumSearchOutput | str


# --- QQ API 搜索函数（返回原始 item 列表）---


async def search_song(query: str, num: int = 5) -> list[SongItem]:
    res = await _qq_request(
        "fcg_music_custom_search.fcg", {"w": query, "p": 1, "num": num, "t": 0}
    )
    if not res:
        return []
    return [SongItem.model_validate(item) for item in res.get("list", [])]


async def search_playlist(query: str, num: int = 5) -> list[PlaylistItem]:
    res = await _qq_request(
        "fcg_music_custom_search.fcg", {"w": query, "p": 1, "num": num, "t": 3}
    )
    if not res:
        return []
    return [PlaylistItem.model_validate(item) for item in res.get("list", [])]


async def search_album(query: str, num: int = 5) -> list[AlbumItem]:
    res = await _qq_request(
        "fcg_music_custom_search.fcg", {"w": query, "p": 1, "num": num, "t": 8}
    )
    if not res:
        return []
    return [AlbumItem.model_validate(item) for item in res.get("list", [])]


# --- 3 个不带 planning 版本（工厂函数）---


def qq_music_song_search_tool(
    worker: SGMMusicWorker | None = None,
    *,
    timeout: float | None = None,
):
    return create_tool(
        name="QQ音乐单曲搜索",
        description="""单曲搜索工具，支持按歌曲名搜索歌曲信息；
        必须按criteria筛选，criteria是除了query之外的包括个人偏好等任何其它信息。""",
        args_schema=MusicSearchInput,
        worker=worker
        or SGMMusicWorker(search_func=search_song, output_cls=SongSearchOutput),
        timeout=timeout,
    )


def qq_music_playlist_search_tool(
    worker: SGMMusicWorker | None = None,
    *,
    timeout: float | None = None,
):
    return create_tool(
        name="QQ音乐歌单搜索",
        description="""歌单搜索工具，支持按主题、歌单名搜索歌单信息；
        必须按criteria筛选，criteria是除了query之外的包括个人偏好等任何其它信息。""",
        args_schema=MusicSearchInput,
        worker=worker
        or SGMMusicWorker(search_func=search_playlist, output_cls=PlaylistSearchOutput),
        timeout=timeout,
    )


def qq_music_album_search_tool(
    worker: SGMMusicWorker | None = None,
    *,
    timeout: float | None = None,
):
    return create_tool(
        name="QQ音乐专辑搜索",
        description="""专辑搜索工具，支持按专辑名、歌手名搜索专辑信息；
        必须按criteria筛选，criteria是除了query之外的包括个人偏好等任何其它信息。""",
        args_schema=MusicSearchInput,
        worker=worker
        or SGMMusicWorker(search_func=search_album, output_cls=AlbumSearchOutput),
        timeout=timeout,
    )


# --- 3 个带 planning 版本（工厂函数）---


def qq_music_song_search_tool_with_planning(
    worker: SGMMusicWorker | None = None,
    *,
    timeout: float | None = None,
):
    return create_tool(
        name="QQ音乐单曲搜索",
        description="基于用户需求搜索QQ音乐单曲，支持按criteria筛选。缺少关键信息时返回澄清问题。",
        args_schema=MusicSearchGoal,
        worker=worker
        or SGMMusicWorker(search_func=search_song, output_cls=SongSearchOutput),
        timeout=timeout,
        with_clarify=True,
    )


def qq_music_playlist_search_tool_with_planning(
    worker: SGMMusicWorker | None = None,
    *,
    timeout: float | None = None,
):
    return create_tool(
        name="QQ音乐歌单搜索",
        description="基于用户需求搜索QQ音乐歌单，支持按criteria筛选。缺少关键信息时返回澄清问题。",
        args_schema=MusicSearchGoal,
        worker=worker
        or SGMMusicWorker(search_func=search_playlist, output_cls=PlaylistSearchOutput),
        timeout=timeout,
        with_clarify=True,
    )


def qq_music_album_search_tool_with_planning(
    worker: SGMMusicWorker | None = None,
    *,
    timeout: float | None = None,
):
    return create_tool(
        name="QQ音乐专辑搜索",
        description="基于用户需求搜索QQ音乐专辑，支持按criteria筛选。缺少关键信息时返回澄清问题。",
        args_schema=MusicSearchGoal,
        worker=worker
        or SGMMusicWorker(search_func=search_album, output_cls=AlbumSearchOutput),
        timeout=timeout,
        with_clarify=True,
    )


__all__ = [
    "MusicSearchInput",
    "MusicSearchGoal",
    "MusicSearchParams",
    "SGMMusicWorker",
    "SongItem",
    "PlaylistItem",
    "AlbumItem",
    "SongSearchOutput",
    "PlaylistSearchOutput",
    "AlbumSearchOutput",
    "SongSearchOutputLike",
    "PlaylistSearchOutputLike",
    "AlbumSearchOutputLike",
    "search_song",
    "search_playlist",
    "search_album",
    "qq_music_song_search_tool",
    "qq_music_playlist_search_tool",
    "qq_music_album_search_tool",
    "qq_music_song_search_tool_with_planning",
    "qq_music_playlist_search_tool_with_planning",
    "qq_music_album_search_tool_with_planning",
]
