"""
天气查询工具：对应原 complex_reasoning_agent WeatherAgent 的 weather_search 路径。
weather_search 通过火山 call_plugin(intent_type="weather") 获取天气结果（JSON 字符串），
与 CarControlTool / NavigateTool 的调用方式完全一致。
"""
import json
import logging

from pydantic import BaseModel, Field

from aicore.tools import BaseTool

from projects.mind.complex_reasoning.utils.exception import FcException
from projects.mind.complex_reasoning.utils.plugins import IntentType, call_fc

__all__ = ["WeatherInput", "WeatherItem", "WeatherOutput", "WeatherTool"]

logger = logging.getLogger(__name__)


class WeatherInput(BaseModel):
    """与 complex_reasoning_agent weather_agent query_describe 一致。"""
    query: str = Field(description="用户想查询的天气信息，需包含城市/位置，如：北京今天天气怎么样、上海明天后天天气、杭州最近三天天气")


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
    forecasts: list[WeatherItem] = Field(default_factory=list, description="天气预报列表")
    message: str = Field(default="", description="结果说明或错误信息")


class WeatherTool(BaseTool):
    """天气查询工具：通过火山 weather 插件查询当前或未来几天的天气情况。"""
    name: str = "weather_agent"
    description: str = (
        "天气查询工具。使用此工具，可以查询当前或未来几天的天气情况，需要提供城市/位置信息。"
    )
    args_schema: type[BaseModel] = WeatherInput
    chat_id: str = Field(..., description="会话 ID，用于请求火山天气插件")

    def _run(self, query: str) -> WeatherOutput:
        raise NotImplementedError("天气查询请使用异步调用 ainvoke/astream")

    async def _arun(self, query: str) -> WeatherOutput:
        try:
            result = await call_fc(query, self.chat_id, intent_type=IntentType.WEATHER)
            if not isinstance(result, str):
                return WeatherOutput(message="天气查询无结果")
            raw = result.strip()
            if raw.startswith("["):
                items = [WeatherItem(**item) for item in json.loads(raw)]
                return WeatherOutput(forecasts=items)
            if raw.startswith("{"):
                data = json.loads(raw)
                lst = next((v for v in data.values() if isinstance(v, list)), None)
                items = [WeatherItem(**item) for item in (lst or [data])]
                return WeatherOutput(forecasts=items)
            return WeatherOutput(message=raw or "天气查询无结果")
        except FcException as e:
            logger.warning("weather call_fc FcException: %s", e)
            return WeatherOutput(message=str(e))
        except Exception as e:
            logger.exception("weather call_fc error: %s", e)
            return WeatherOutput(message=f"天气查询异常: {e}")
