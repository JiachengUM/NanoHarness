"""
QQ 音乐开放 API 检索工具（单曲 / 歌单 / 专辑）。

入参：SongSearchParams / PlaylistSearchParams / AlbumSearchParams（仅 keyword 字段），
worker 直接用 keyword 作为 search query 给 search_func。
"""
from collections.abc import Awaitable, Callable
import hashlib
import logging
import time
from typing import Any, Optional

import httpx

from aicore.tools import create_tool
from aicore.tools.dag.operator_models import (
    SongItem,
    PlaylistItem,
    AlbumItem,
    SongSearchParams,
    PlaylistSearchParams,
    AlbumSearchParams,
    SongSearchOutput,
    PlaylistSearchOutput,
    AlbumSearchOutput,
)
from aicore.utils.volc_client.httpx_client import HttpClient, HttpxTransport
from projects.mind.complex_reasoning.configs.config import get_app_config

__all__ = [
    "qq_music_song_search_tool",
    "qq_music_playlist_search_tool",
    "qq_music_album_search_tool",
]

logger = logging.getLogger(__name__)

_http_client: HttpClient | None = None


def _get_client() -> HttpClient:
    global _http_client
    if _http_client is None:
        _http_client = HttpClient(HttpxTransport(httpx.AsyncClient(timeout=httpx.Timeout(5.0))))
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


# ---------- query 拼接（按 navigation 的 _build_navigation_command 模式） ----------

def _build_keyword_query(*, keyword: Optional[str] = None) -> str:
    """统一的 query 拼接：直接使用 keyword 作为 search query。"""
    return (keyword or "").strip()


# ---------- worker ----------

class SGMMusicWorker:
    """通用音乐搜索 worker。

    接受 SongSearchParams / PlaylistSearchParams / AlbumSearchParams 等的 keyword 字段，
    直接作为 search query 调 search_func。
    """

    def __init__(
        self,
        search_func: Callable[[str, int], Awaitable[list[Any]]],
        output_cls: type,
        field_name: str,
        build_query: Callable[..., str],
    ):
        self.search_func = search_func
        self.output_cls = output_cls
        self.field_name = field_name
        self.build_query = build_query

    def _to_output(self, items: list[Any]) -> Any:
        return self.output_cls(**{self.field_name: items})

    async def __call__(
        self,
        *,
        limit: int = 5,
        **fields: Any,
    ) -> Any:
        actual_query = self.build_query(**fields)
        if not actual_query:
            return self._to_output([])
        items = await self.search_func(actual_query, num=limit)
        return self._to_output(items)


# ---------- 底层 search API ----------

async def search_song(query: str, num: int = 5) -> list[SongItem]:
    res = await _qq_request("fcg_music_custom_search.fcg", {"w": query, "p": 1, "num": num, "t": 0})
    if not res:
        return []
    return [SongItem.model_validate(item) for item in res.get("list", [])]


async def search_playlist(query: str, num: int = 5) -> list[PlaylistItem]:
    res = await _qq_request("fcg_music_custom_search.fcg", {"w": query, "p": 1, "num": num, "t": 3})
    if not res:
        return []
    return [PlaylistItem.model_validate(item) for item in res.get("list", [])]


async def search_album(query: str, num: int = 5) -> list[AlbumItem]:
    res = await _qq_request("fcg_music_custom_search.fcg", {"w": query, "p": 1, "num": num, "t": 8})
    if not res:
        return []
    return [AlbumItem.model_validate(item) for item in res.get("list", [])]


# ---------- tool factory ----------

def qq_music_song_search_tool(
    worker: SGMMusicWorker | None = None,
    *,
    timeout: float | None = None,
):
    return create_tool(
        name="SongSearch",
        description=(
            "单曲搜索工具。"
            "输出：单曲结果列表"
        ),
        args_schema=SongSearchParams,
        worker=worker or SGMMusicWorker(
            search_func=search_song,
            output_cls=SongSearchOutput,
            field_name="songs",
            build_query=_build_keyword_query,
        ),
        timeout=timeout,
    )


def qq_music_playlist_search_tool(
    worker: SGMMusicWorker | None = None,
    *,
    timeout: float | None = None,
):
    return create_tool(
        name="PlaylistSearch",
        description=(
            "歌单搜索工具。"
            "输出：歌单结果列表"
        ),
        args_schema=PlaylistSearchParams,
        worker=worker or SGMMusicWorker(
            search_func=search_playlist,
            output_cls=PlaylistSearchOutput,
            field_name="playlists",
            build_query=_build_keyword_query,
        ),
        timeout=timeout,
    )


def qq_music_album_search_tool(
    worker: SGMMusicWorker | None = None,
    *,
    timeout: float | None = None,
):
    return create_tool(
        name="AlbumSearch",
        description=(
            "专辑搜索工具。"
            "输出：专辑结果列表"
        ),
        args_schema=AlbumSearchParams,
        worker=worker or SGMMusicWorker(
            search_func=search_album,
            output_cls=AlbumSearchOutput,
            field_name="albums",
            build_query=_build_keyword_query,
        ),
        timeout=timeout,
    )
