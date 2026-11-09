"""
音乐检索工具：对应原 complex_reasoning_agent MusicSearchAgent。
使用 QQ 音乐开放 API。
"""
import hashlib
import json
import logging
import time
import asyncio
from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import List, Optional

import aiohttp
from pydantic import BaseModel, Field

from aicore.tools import BaseTool

from projects.mind.complex_reasoning.configs.config import get_app_config
from projects.mind.complex_reasoning.utils.http_client import HttpClient

__all__ = ["MusicSearchInput", "MusicSearchTool"]

logger = logging.getLogger(__name__)

def _qq_sign(params: dict[str, object], app_key: str) -> str:
    sorted_keys = sorted(k for k in params.keys() if k != "sign")
    sign_str = "&".join(f"{k}={params[k]}" for k in sorted_keys) + f"_{app_key}"
    return hashlib.md5(sign_str.encode()).hexdigest()


async def _qq_request(opi_cmd: str, additional: dict[str, object]) -> Optional[dict]:
    cfg = get_app_config()
    params = {
        "opi_cmd": opi_cmd,
        "app_id": cfg.QQ_MUSIC_APP_ID,
        "timestamp": int(time.time()),
        "device_id": cfg.QQ_MUSIC_DEVICE_ID,
        "sign_version": "v2",
        **additional,
    }
    params["sign"] = _qq_sign(params, cfg.QQ_MUSIC_APP_KEY)
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        client = await HttpClient.get_instance()
        resp = await client.get(cfg.QQ_MUSIC_BASE_URL, params=params, timeout=timeout)
        if not isinstance(resp.json, dict):
            return None
        if resp.json.get("ret") == 0:
            return resp.json
        return None
    except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
        logger.warning("QQ 音乐请求异常: %s", e)
        return None


@dataclass(slots=True, frozen=True)
class SongItem:
    song_name: str = ""
    singer_name: str = ""
    album_name: str = ""
    public_time: str = ""


@dataclass(slots=True, frozen=True)
class MusicSearchResult:
    keyword: str
    list: List[SongItem] = dc_field(default_factory=list)


class MusicSearchStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class MusicSearchToolOutput(BaseModel):
    status: MusicSearchStatus
    keyword: str = ""
    list: List[SongItem] = Field(default_factory=list)
    message: str = ""
    error_msg: str = ""


async def search_song(query: str, page: int = 1, page_size: int = 15) -> MusicSearchResult:
    """搜索歌曲。"""
    q = (query or "").replace("最近", "").strip() or "热门"
    res = await _qq_request(
        "fcg_music_custom_search.fcg",
        {"w": q, "p": page, "num": page_size, "t": 0},
    )
    if not res:
        return MusicSearchResult(keyword=q, list=[])
    lst = res.get("list", [])
    return MusicSearchResult(
        keyword=str(res.get("keyword", q)),
        list=[
            SongItem(
                song_name=str(item.get("song_name", "")),
                singer_name=str(item.get("singer_name", "")),
                album_name=str(item.get("album_name", "")),
                public_time=str(item.get("public_time", "")),
            )
            for item in lst
        ],
    )


class MusicSearchInput(BaseModel):
    """音乐检索关键词。不要带年月等时间类关键字。"""
    query: str = Field(description="要查询的歌曲或歌手名，如：周杰伦 稻香、热门榜单")


class MusicSearchTool(BaseTool):
    """音乐检索工具：QQ 音乐 API。"""
    name: str = "music_search"
    description: str = "查询歌曲和榜单信息，可按歌名、歌手搜索。注意不要带「最近」「今年」等时间类关键词。"
    args_schema: type[BaseModel] = MusicSearchInput

    def _run(self, query: str) -> dict:
        raise NotImplementedError("音乐检索请使用异步调用 ainvoke/astream")

    async def _arun(self, query: str) -> MusicSearchToolOutput:
        try:
            result = await search_song(query)
            lst = result.list
            return MusicSearchToolOutput(
                status=MusicSearchStatus.SUCCESS,
                keyword=result.keyword,
                list=lst,
                message=f"共 {len(lst)} 条结果" if lst else "未找到相关歌曲",
            )
        except Exception as e:
            logger.exception("search_song error: %s", e)
            return MusicSearchToolOutput(
                status=MusicSearchStatus.ERROR,
                list=[],
                message=f"检索异常: {e}",
                error_msg=str(e),
            )
