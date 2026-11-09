from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable

from pydantic import BaseModel, Field

from aicore.runtime.task import TaskManager, TaskProgress, TaskSuccess
from aicore.tools import TaskAStreamWorker
from aicore.v2.tools.factory import create_tool
from projects.mind.complex_reasoning.utils.exception import FcException
from projects.mind.complex_reasoning.utils.plugins import IntentType, call_fc

logger = logging.getLogger(__name__)


class WeatherSearchInput(BaseModel):
    query: str = Field(..., description="包含城市或位置的天气查询描述，例如: 香港今天的天气")
    criteria: list[str] = Field(default_factory=list, description="除位置和时间外的天气关注点，例如湿度、风力、是否适合出行")


class WeatherItem(BaseModel):
    city: str = Field(default="", description="城市或地区")
    date: str = Field(default="", description="日期")
    condition: str = Field(default="", description="天气状况")
    temperature: str = Field(default="", description="温度范围")
    humidity: str | None = Field(default=None, description="湿度")
    wind: str | None = Field(default=None, description="风力")


class WeatherSearchOutput(BaseModel):
    items: list[WeatherItem] = Field(default_factory=list, description="天气结果")
    message: str = Field(default="", description="结果说明")


WeatherSearchWorker = Callable[..., Awaitable[WeatherSearchOutput]]
WeatherSearchStreamWorker = TaskAStreamWorker[str, WeatherSearchOutput, ...]


def _item_from_raw(raw: dict[str, str | int | float | None]) -> WeatherItem:
    return WeatherItem(
        city=str(raw.get("districtName") or raw.get("cityName") or raw.get("city") or ""),
        date=str(raw.get("date") or ""),
        condition=str(raw.get("textDay") or raw.get("condition") or ""),
        temperature=(
            str(raw.get("temperature"))
            if raw.get("temperature") is not None
            else f"{raw.get('low', '')}-{raw.get('high', '')}".strip("-")
        ),
        humidity=str(raw.get("humidity")) if raw.get("humidity") is not None else None,
        wind=str(raw.get("windScale") or raw.get("wind") or "") or None,
    )


async def volc_weather_worker(query: str, criteria: list[str] | None = None, *, chat_id: str) -> WeatherSearchOutput:
    try:
        result = await call_fc(query, chat_id, intent_type=IntentType.WEATHER)
        payload = json.loads(result.strip())
        if isinstance(payload, list):
            return WeatherSearchOutput(items=[_item_from_raw(item) for item in payload if isinstance(item, dict)])
        if isinstance(payload, dict):
            list_value = next((value for value in payload.values() if isinstance(value, list)), None)
            if list_value is not None:
                return WeatherSearchOutput(items=[_item_from_raw(item) for item in list_value if isinstance(item, dict)])
            return WeatherSearchOutput(items=[_item_from_raw(payload)])
        return WeatherSearchOutput(message=str(payload or "天气查询无结果"))
    except FcException as exc:
        logger.warning("weather call_fc failed: %s", exc)
        return WeatherSearchOutput(message=str(exc))
    except Exception as exc:
        logger.exception("weather worker failed: %s", exc)
        return WeatherSearchOutput(message=f"天气查询异常: {exc}")


class WeatherSearchV2Worker:
    def __init__(self, chat_id: str):
        self.chat_id = chat_id

    async def __call__(self, query: str, criteria: list[str] | None = None) -> WeatherSearchOutput:
        import asyncio
        await asyncio.sleep(10)
        return await volc_weather_worker(query, criteria, chat_id=self.chat_id)


class WeatherSearchV2StreamWorker:
    def __init__(self, worker: WeatherSearchWorker):
        self.worker = worker

    async def __call__(
        self,
        query: str,
        criteria: list[str] | None = None,
    ) -> AsyncGenerator[TaskProgress[str] | TaskSuccess[WeatherSearchOutput], None]:
        yield TaskProgress(progress="开始天气查询")
        yield TaskProgress(progress=f"查询条件: {query}")
        result = await self.worker(query=query, criteria=criteria or [])
        yield TaskSuccess(result=result)


def weather_search_v2_tool(
    worker: WeatherSearchWorker | WeatherSearchStreamWorker | None = None,
    *,
    chat_id: str | None = None,
    timeout: float | None = 15,
    task_manager: TaskManager,
):
    if worker is None:
        if chat_id is None:
            raise ValueError("使用默认真实天气 worker 时必须提供 chat_id")
        worker = WeatherSearchV2StreamWorker(WeatherSearchV2Worker(chat_id))

    return create_tool(
        name="天气查询工具",
        description="查询指定城市或位置在指定时间的天气。用户询问天气、气温、湿度、风力、出行天气时使用。",
        args_schema=WeatherSearchInput,
        worker=worker,
        timeout=timeout,
        asyncable="async",
        with_clarify=True,
        task_manager=task_manager,
    )


__all__ = [
    "WeatherSearchInput",
    "WeatherItem",
    "WeatherSearchOutput",
    "WeatherSearchWorker",
    "WeatherSearchV2Worker",
    "WeatherSearchV2StreamWorker",
    "weather_search_v2_tool",
    "volc_weather_worker",
]
