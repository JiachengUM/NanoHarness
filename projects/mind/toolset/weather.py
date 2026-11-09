"""
天气查询工具：对应原 complex_reasoning_agent WeatherAgent 的 weather_search 路径。
weather_search 通过火山 call_plugin(intent_type="weather") 获取天气结果（JSON 字符串），
与 CarControlTool / NavigateTool 的调用方式完全一致。
"""

import json
import logging
from typing import Callable, Awaitable

from pydantic import BaseModel, Field

from aicore.tools import create_tool

from projects.mind.complex_reasoning.utils.exception import FcException
from projects.mind.complex_reasoning.utils.plugins import IntentType, call_fc

__all__ = ["WeatherInput", "WeatherItem", "WeatherOutput", "WeatherTool"]

logger = logging.getLogger(__name__)


class WeatherInput(BaseModel):
    # 与 complex_reasoning_agent weather_agent query_describe 一致。

    # query: str = Field(description="用户想查询的天气信息，需包含城市/位置，如：北京今天天气怎么样、上海明天后天天气、杭州最近三天天气")
    query: str = Field(description="包含位置的气候查询描述")


class WeatherItem(BaseModel):
    """单条天气预报数据。"""

    id: str = ""
    provinceName: str = ""
    cityName: str = ""
    districtName: str = ""
    date: str = ""
    textDay: str = ""
    textNight: str = ""
    high: str = ""
    low: str = ""
    precip: str = ""
    windDirection: str = ""
    windDirectionDegree: str = ""
    windSpeed: str = ""
    windScale: str = ""
    humidity: str = ""
    sunRise: str = ""
    sunDown: str = ""


class WeatherOutput(BaseModel):
    forecasts: list[WeatherItem] = Field(
        default_factory=list, description="天气预报列表"
    )
    message: str = Field(default="", description="结果说明或错误信息")
    raw_output: str | None = Field(
        default=None,
        description="当天气服务返回非 JSON 或 JSON 解析失败时保留的原始返回文本，供后续模型判断",
    )


async def _weather_worker(query: str, *, chat_id: str) -> WeatherOutput:
    raw_output: str | None = None
    try:
        result = await call_fc(query, chat_id, intent_type=IntentType.WEATHER)
        raw_output = result
        df = json.loads(result.strip())
        if isinstance(df, list):
            items = [WeatherItem(**item) for item in df]
            return WeatherOutput(forecasts=items)
        elif isinstance(df, dict):
            lst = next((v for v in df.values() if isinstance(v, list)), None)
            items = [WeatherItem(**item) for item in (lst or [df])]
            return WeatherOutput(forecasts=items)
        return WeatherOutput(message=str(df or "天气查询无结果"), raw_output=raw_output)
    except FcException as e:
        logger.warning("call_fc FcException: %s", e)
        return WeatherOutput(message=str(e))
    except Exception as e:
        logger.exception("weather call_fc error: %s", e)
        return WeatherOutput(message=f"天气查询异常: {e}", raw_output=raw_output)


class VolcWeatherWorker:
    def __init__(self, chat_id: str):
        self.chat_id = chat_id

    async def __call__(self, query: str) -> WeatherOutput:
        return await _weather_worker(query, chat_id=self.chat_id)


WeatherWorker = Callable[..., Awaitable[WeatherOutput]]


def WeatherTool(
    chat_id: str, worker: WeatherWorker | None = None, *, timeout: float | None = None
):
    """天气查询工具。调用火山 function_call 插件。"""
    return create_tool(
        name="weather_agent",
        description="根据位置查询气候",
        args_schema=WeatherInput,
        worker=worker if worker is not None else VolcWeatherWorker(chat_id),
        timeout=timeout,
    )
