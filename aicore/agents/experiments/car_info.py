from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# 枚举类型定义
class Gear(Enum):
    """档位枚举"""
    P = "P档（驻车档）"
    R = "R档（倒车档）"
    N = "N档（空档）"
    D = "D档（前进档）"
    S = "S档（运动档）"


class SpeedStatus(Enum):
    """速度状态枚举"""
    STATIONARY = "静止状态"
    MOVING = "行驶中"
    IDLING = "怠速状态"


class TemperatureMode(Enum):
    """温度模式枚举"""
    COMFORT = "舒适模式"
    ECO = "节能模式"
    SPORT = "运动模式"
    AUTO = "自动模式"


class PowerMode(Enum):
    """动力模式枚举"""
    EV = "纯电模式"
    HEV = "混动模式"
    ICE = "燃油模式"


class AirConditionerStatus(Enum):
    """空调状态枚举"""
    OFF = "关闭中"
    COOLING = "制冷中"
    HEATING = "制热中"
    AUTO = "自动模式"


class AirQualityLevel(Enum):
    """空气质量等级枚举"""
    EXCELLENT = "优"
    GOOD = "良"
    MODERATE = "中度污染"
    POOR = "重度污染"


class TirePressureStatus(Enum):
    """胎压状态枚举"""
    NORMAL = "正常"
    LOW = "偏低"
    HIGH = "偏高"
    ERROR = "传感器故障"


class DemoMode(Enum):
    """演示模式枚举"""
    ON = "演示模式已开启"
    OFF = "演示模式已关闭"


class Location(BaseModel):
    """位置信息模型"""
    address: str = Field(default="上海平金中心", description="地址")
    longitude: float = Field(default=121.357, ge= -180, le= 180, description="经度")
    latitude: float = Field(default=31.134, ge= -90, le= 90, description="纬度")
    
    def __str__(self) -> str:
        return f"{self.address}，经度{self.longitude}°，纬度{self.latitude}°"


class ValueWithUnit(BaseModel):
    """带单位的数值模型"""
    value: float = Field(description="数值")
    unit: str = Field(description="单位")
    
    def __str__(self) -> str:
        return f"{self.value}{self.unit}"


class Speed(BaseModel):
    """速度信息模型"""
    value: float = Field(default=0.0, ge= 0, le= 300, description="速度值")
    unit: str = Field(default="km/h", description="速度单位")
    
    def __str__(self) -> str:
        return f"{self.value} {self.unit}（{self.status.value}）"


class Temperature(BaseModel):
    """温度信息模型"""
    value: float = Field(ge= -40, le= 80, description="温度值")
    unit: str = Field(default="摄氏度", description="温度单位")
    
    def __str__(self) -> str:
        if self.mode:
            return f"{self.value}{self.unit}（{self.mode.value}）"
        return f"{self.value}{self.unit}"


class BatteryInfo(BaseModel):
    """电池信息模型"""
    percentage: ValueWithUnit = Field(default=ValueWithUnit(value=70.0, unit="%"), ge= 0, le= 100, description="电池电量百分比")
    remaining_range: ValueWithUnit = Field(default=ValueWithUnit(value=510.0, unit="km"), ge= 0, description="剩余续航里程")
    
    def __str__(self) -> str:
        return f"电量{self.percentage}，续航{self.remaining_range}"


class SunroofStatus(BaseModel):
    """天窗与遮阳帘状态模型"""
    sunroof_open: bool = Field(default=True, description="天窗是否打开")
    sunshade_open: bool = Field(default=False, description="遮阳帘是否打开")
    
    def __str__(self) -> str:
        sunroof_str = "已打开" if self.sunroof_open else "已关闭"
        sunshade_str = "打开" if self.sunshade_open else "关闭"
        return f"天窗{sunroof_str}，遮阳帘{sunshade_str}"


class AirQuality(BaseModel):
    """空气质量信息模型"""
    pm25: float = Field(default=15.0, ge= 0, description="PM2.5值")
    unit: str = Field(default="μg/m³", description="PM2.5单位")
    level: AirQualityLevel = Field(default=AirQualityLevel.EXCELLENT, description="空气质量等级")
    
    def __str__(self) -> str:
        return f"PM2.5 {self.pm25}{self.unit}（{self.level.value}）"


class TirePressure(BaseModel):
    """胎压监测模型"""
    front_left: ValueWithUnit = Field(default=ValueWithUnit(value=2.3, unit="bar"), ge= 1.5, le= 3.5, description="左前胎压")
    front_right: ValueWithUnit = Field(default=ValueWithUnit(value=2.3, unit="bar"), ge= 1.5, le= 3.5, description="右前胎压")
    rear_left: ValueWithUnit = Field(default=ValueWithUnit(value=2.2, unit="bar"), ge= 1.5, le= 3.5, description="左后胎压")
    rear_right: ValueWithUnit = Field(default=ValueWithUnit(value=2.2, unit="bar"), ge= 1.5, le= 3.5, description="右后胎压")
    status: TirePressureStatus = Field(default=TirePressureStatus.NORMAL, description="胎压状态")
    
    def __str__(self) -> str:
        return f"左前{self.front_left}，右前{self.front_right}，左后{self.rear_left}，右后{self.rear_right}（{self.status.value}）"


class Mileage(BaseModel):
    """里程信息模型"""
    value: float = Field(default=15.0, ge= 0, description="里程值")
    unit: str = Field(default="km", description="里程单位")
    description: str = Field(default="展车测试里程", description="里程描述")
    
    def __str__(self) -> str:
        return f"{self.value} {self.unit}（{self.description}）"


class VehicleState(BaseModel):
    """车辆状态信息模型"""
    
    # 基础信息
    current_time: datetime = Field(description="当前系统时间")
    location: Location = Field(default=Location(), description="当前位置")
    
    # 行驶状态
    gear: Gear = Field(default=Gear.P, description="车辆当前档位")
    speed: Speed = Field(default=Speed(), description="车辆当前行驶速度")
    
    # 温度信息
    interior_temperature: Temperature = Field(default=Temperature(value=24.0, mode=TemperatureMode.COMFORT), description="车内温度")
    exterior_temperature: Temperature = Field(default=Temperature(value=20.0), description="车外温度")
    
    # 动力与续航（新能源车）
    power_mode: PowerMode = Field(default=PowerMode.EV, description="车辆动力模式")
    battery: BatteryInfo = Field(default=BatteryInfo(), description="电池信息")
    
    # 天窗与遮阳帘
    sunroof_status: SunroofStatus = Field(default=SunroofStatus(), description="天窗与遮阳帘状态")
    
    # 空调与空气质量
    air_conditioner_status: AirConditionerStatus = Field(default=AirConditionerStatus.OFF, description="空调开启状态及模式")
    air_quality: AirQuality = Field(default=AirQuality(), description="车内空气质量")
    
    # 智能座舱
    center_screen_status: str = Field(default="演示模式 - 智能座舱功能展示页面", description="中控屏幕状态")
    voice_assistant_wake_word: str = Field(default="你好小涂", description="语音助手唤醒词")
    
    # 胎压监测
    tire_pressure: TirePressure = Field(default=TirePressure(), description="四轮胎压监测")
    
    # 里程与状态
    total_mileage: Mileage = Field(default=Mileage(), description="总里程数")
    warning_info: str = Field(default="无告警", description="车辆告警/故障信息")
    demo_mode: DemoMode = Field(default=DemoMode.ON, description="车辆展示模式")
    
    def to_prompt_string(self) -> str:
        """转换为提示词字符串格式"""
        return f"""'当前系统时间': {self.current_time},
'当前位置': '{self.location}',
'车辆当前档位': '{self.gear.value}',
'车辆当前行驶速度': '{self.speed}',
'车内温度': '{self.interior_temperature}',
'车外温度': '{self.exterior_temperature}',
'车辆动力模式（新能源车/混动车专用）': '{self.power_mode.value}',
'动力电池电量百分比（新能源车必需）': '{self.battery.percentage}',
'剩余续航里程（新能源车）': '{self.battery.remaining_range}',
'天窗状态': '{'已打开' if self.sunroof_status.sunroof_open else '已关闭'}',
'遮阳帘状态': '{'打开' if self.sunroof_status.sunshade_open else '关闭'}',
'空调开启状态及模式': '{self.air_conditioner_status.value}',
'车内空气质量（智能车功能）': '{self.air_quality}',
'中控屏幕状态（智能车重点）': '{self.center_screen_status}',
'语音助手唤醒词': '唤醒词\"{self.voice_assistant_wake_word}\"',
'四轮胎压监测': '{self.tire_pressure}',
'总里程数': '{self.total_mileage}',
'车辆告警/故障信息': '{self.warning_info}',
'车辆展示模式（车展专用）': '{self.demo_mode.value}'"""


# 默认车辆状态实例
DEFAULT_VEHICLE_STATE = VehicleState(
    current_time=datetime.now()
)