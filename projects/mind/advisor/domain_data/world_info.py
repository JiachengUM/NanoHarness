from pydantic import BaseModel, Field

class CityInfo(BaseModel):
    """城市信息"""
    name: str | None = Field(default=None, title="城市名称", description="城市名称")
    id: str | None = Field(default=None, title="城市ID", description="城市ID")
    lat: str | None = Field(default=None, title="纬度", description="纬度")
    lon: str | None = Field(default=None, title="经度", description="经度")
    adm2: str | None = Field(default=None, title="二级行政区", description="二级行政区")
    adm1: str | None = Field(default=None, title="一级行政区", description="一级行政区")
    country: str | None = Field(default=None, title="国家", description="国家")
    tz: str | None = Field(default=None, title="时区", description="时区")
    type: str | None = Field(default=None, title="类型", description="类型")


class WeatherForecast(BaseModel):
    """天气预报"""
    obs_time: str | None = Field(default=None, title="观测时间", description="观测时间")
    temp: str | None = Field(default=None, title="温度", description="温度")
    feels_like: str | None = Field(default=None, title="体感温度", description="体感温度")
    text: str | None = Field(default=None, title="天气现象", description="天气现象")
    wind_dir: str | None = Field(default=None, title="风向", description="风向")
    wind_scale: str | None = Field(default=None, title="风力等级", description="风力等级")
    wind_speed: str | None = Field(default=None, title="风速", description="风速")
    humidity: str | None = Field(default=None, title="相对湿度", description="相对湿度")
    precip: str | None = Field(default=None, title="降水量", description="降水量")
    cloud: str | None = Field(default=None, title="云量", description="云量")
    pressure: str | None = Field(default=None, title="大气压强", description="大气压强")
    vis: str | None = Field(default=None, title="能见度", description="能见度")

class DateInfo(BaseModel):
    """日期信息"""
    date: str | None = Field(default=None, title="日期", description="日期")
    lunar_date: str | None = Field(default=None, title="农历日期", description="农历日期")
    lunar_holiday: list[str] | str | None = Field(default=None, title="农历节日", description="农历节日")
    solar_holiday: list[str] | str | None = Field(default=None, title="公历节日", description="公历节日")
    solar_terms: str | None = Field(default=None, title="节气", description="节气")

class WorldInfo(BaseModel):
    '''世界信息'''

    city: CityInfo | str | None = Field(default=None, title="城市", description="城市")
    weather: WeatherForecast | str | None = Field(default=None, title="天气", description="天气")
    date: DateInfo | str | None = Field(default=None, title="日期", description="日期")

    attributes: dict[str, str] | None = Field(default=None, title="其它属性", description="其它属性")
    '''上面未定义的属性，在这里动态添加'''
