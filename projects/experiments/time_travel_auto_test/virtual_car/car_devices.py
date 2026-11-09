"""虚拟车详细设备状态定义。

对应真实车控可操作的设备：空调、座椅、车窗、天窗、遮阳帘、灯光、
方向盘加热、车载电视、车载冰箱、媒体、导航等。
设备覆盖面参考车机助手评测标签树的"车控操作"子树：
空调操作 / 车窗天窗遮阳帘操作 / 座椅操作 / 方向盘加热 / 灯光操作 /
电视操作 / 冰箱操作 / 车门舱门操作。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ==================== 空调系统 ====================

class ACMode(str, Enum):
    OFF = "关闭"
    COOLING = "制冷"
    HEATING = "加热"
    VENTILATION = "通风"
    AUTO = "自动"


class ACFanLevel(int, Enum):
    OFF = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    AUTO = 4


class ACAirDirection(str, Enum):
    FACE = "吹脸"
    FEET = "吹脚"
    FACE_FEET = "吹脸和脚"
    AUTO = "自动"


class AirConditioner(BaseModel):
    """空调系统状态"""

    is_on: bool = Field(default=False, description="是否开启")
    mode: ACMode = Field(default=ACMode.OFF, description="模式")
    temperature: int = Field(default=24, ge=16, le=30, description="目标温度°C")
    fan_level: ACFanLevel = Field(default=ACFanLevel.AUTO, description="风量等级")
    air_direction: ACAirDirection = Field(default=ACAirDirection.AUTO, description="风向")
    is_sync: bool = Field(default=True, description="是否分区同步")
    # 分区控制（前排左右、后排）
    driver_temp: int = Field(default=24, ge=16, le=30, description="驾驶位温度")
    passenger_temp: int = Field(default=24, ge=16, le=30, description="副驾位温度")
    rear_temp: int = Field(default=24, ge=16, le=30, description="后排温度")
    # 外部传感器
    outside_temp_c: int = Field(default=25, ge=-40, le=60, description="车外温度°C")


# ==================== 座椅系统 ====================

class SeatHeatLevel(int, Enum):
    OFF = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class SeatPosition(BaseModel):
    """座椅位置"""

    position: int = Field(default=50, ge=0, le=100, description="前后位置 0-100")
    backrest_angle: int = Field(default=90, ge=60, le=120, description="靠背角度")
    height: int = Field(default=50, ge=0, le=100, description="高度")


class Seat(BaseModel):
    """单个座椅状态"""

    seat_id: str = Field(description="座椅ID: driver/passenger/rear_left/rear_right")
    is_occupied: bool = Field(default=False, description="是否有人乘坐")
    seat_belt: bool = Field(default=False, description="安全带是否系好")
    heater_level: SeatHeatLevel = Field(default=SeatHeatLevel.OFF, description="加热等级 0-3")
    ventilation_level: SeatHeatLevel = Field(default=SeatHeatLevel.OFF, description="通风等级 0-3")
    massage_mode: str = Field(default="关闭", description="按摩模式: 关闭/轻柔/舒缓/活力")
    seat_mode: str = Field(default="标准", description="座椅模式: 标准/零重力")
    position: SeatPosition = Field(default_factory=SeatPosition)


# ==================== 车门/车窗 ====================

class DoorState(str, Enum):
    CLOSED_LOCKED = "关闭并上锁"
    CLOSED_UNLOCKED = "关闭未上锁"
    OPEN = "打开"
    AJAR = "虚掩"


class WindowState(str, Enum):
    CLOSED = "关闭"
    OPEN = "打开"
    PARTIAL = "半开"


class DoorWindow(BaseModel):
    """车门+车窗状态"""

    door_id: str = Field(description="门ID: driver/passenger/rear_left/rear_right/trunk/hood")
    door_state: DoorState = Field(default=DoorState.CLOSED_LOCKED, description="门状态")
    window_state: WindowState = Field(default=WindowState.CLOSED, description="窗状态")
    window_open_percent: int = Field(default=0, ge=0, le=100, description="开窗百分比")


# ==================== 天窗 ====================

class SunroofState(str, Enum):
    CLOSED = "关闭"
    OPEN = "打开"
    TILT = "翘起"
    PARTIAL = "半开"


class Sunroof(BaseModel):
    """天窗状态"""

    state: SunroofState = Field(default=SunroofState.CLOSED, description="天窗状态")
    open_percent: int = Field(default=0, ge=0, le=100, description="开启百分比")
    shade_open_percent: int = Field(default=0, ge=0, le=100, description="遮阳帘开启百分比")


# ==================== 灯光系统 ====================

class LightMode(str, Enum):
    OFF = "关闭"
    POSITION = "示廓灯"
    LOW_BEAM = "近光灯"
    HIGH_BEAM = "远光灯"
    AUTO = "自动"


class AmbientLightMode(str, Enum):
    CONSTANT = "常亮"
    BREATHING = "呼吸"
    FLOWING = "流动"
    MUSIC = "随音乐律动"


class InteriorLight(BaseModel):
    """车内灯光"""

    dome_light: bool = Field(default=False, description="顶灯")
    reading_light_driver: bool = Field(default=False, description="驾驶位阅读灯")
    reading_light_passenger: bool = Field(default=False, description="副驾阅读灯")
    reading_light_brightness: int = Field(default=70, ge=0, le=100, description="阅读灯亮度")
    ambient_light_on: bool = Field(default=False, description="氛围灯开关")
    ambient_light_color: str = Field(default="蓝色", description="氛围灯颜色")
    ambient_light_brightness: int = Field(default=50, ge=0, le=100, description="氛围灯亮度")
    ambient_light_mode: AmbientLightMode = Field(default=AmbientLightMode.FLOWING, description="氛围灯模式")


class ExteriorLight(BaseModel):
    """车外灯光"""

    headlight_mode: LightMode = Field(default=LightMode.OFF, description="大灯模式")
    fog_light_front: bool = Field(default=False, description="前雾灯")
    fog_light_rear: bool = Field(default=False, description="后雾灯")
    turn_signal_left: bool = Field(default=False, description="左转向灯")
    turn_signal_right: bool = Field(default=False, description="右转向灯")
    hazard_light: bool = Field(default=False, description="危险警示灯")
    brake_light: bool = Field(default=False, description="刹车灯")


# ==================== 驾驶系统 ====================

class Gear(str, Enum):
    P = "P档"
    R = "R档"
    N = "N档"
    D = "D档"
    S = "S档"


class IgnitionState(str, Enum):
    OFF = "关闭"
    ACC = "附件"
    ON = "通电"
    START = "启动"


class DriveMode(str, Enum):
    ECO = "经济"
    COMFORT = "舒适"
    SPORT = "运动"
    INDIVIDUAL = "自定义"


class DrivingState(BaseModel):
    """驾驶状态"""

    speed_kmh: int = Field(default=0, ge=0, le=300, description="车速 km/h")
    gear: Gear = Field(default=Gear.P, description="档位")
    handbrake: bool = Field(default=True, description="手刹")
    ignition: IgnitionState = Field(default=IgnitionState.ON, description="点火状态")
    drive_mode: DriveMode = Field(default=DriveMode.COMFORT, description="驾驶模式")
    odometer_km: int = Field(default=0, description="总里程")
    range_km: int = Field(default=500, description="剩余续航 km")


# ==================== 媒体系统 ====================

class MediaPlaybackStatus(str, Enum):
    PLAYING = "播放中"
    PAUSED = "暂停中"
    STOPPED = "停止中"


class MediaState(BaseModel):
    """媒体播放状态"""

    playback_status: MediaPlaybackStatus = Field(
        default=MediaPlaybackStatus.STOPPED, description="播放状态: 播放中/暂停中/停止中"
    )
    volume: int = Field(default=30, ge=0, le=100, description="音量 0-100")
    source: str = Field(default="蓝牙音乐", description="音源: 蓝牙音乐/在线音乐/收音机/USB")
    current_track: Optional[str] = Field(default=None, description="正在播放的歌曲名")
    artist: Optional[str] = Field(default=None, description="正在播放的歌曲歌手名")
    playlist: Optional[str] = Field(default=None, description="正在播放的歌曲所属歌单名")


# ==================== 导航 ====================

class NavigationState(BaseModel):
    """导航状态"""

    is_navigating: bool = Field(default=False, description="是否导航中")
    destination: Optional[str] = Field(default=None, description="目的地")
    remaining_distance_km: Optional[float] = Field(default=None, description="剩余距离 km")
    estimated_arrival: Optional[str] = Field(default=None, description="预计到达时间")
    route_info: Optional[str] = Field(default=None, description="路线信息")


# ==================== 能源系统 ====================

class ChargingStatus(str, Enum):
    NOT_CHARGING = "未充电"
    SLOW_CHARGING = "慢充中"
    FAST_CHARGING = "快充中"


class EnergyState(BaseModel):
    """能源状态（新能源车为主，兼容混动/燃油）"""

    battery_soc_pct: int = Field(default=80, ge=0, le=100, description="电池电量百分比")
    fuel_level_pct: int = Field(default=100, ge=0, le=100, description="燃油余量百分比（混动/燃油车）")
    charging_status: ChargingStatus = Field(default=ChargingStatus.NOT_CHARGING, description="充电状态")
    eco_mode: bool = Field(default=False, description="节能模式")


# ==================== 方向盘 ====================

class SteeringWheel(BaseModel):
    """方向盘状态"""

    heating_level: SeatHeatLevel = Field(
        default=SeatHeatLevel.OFF, description="方向盘加热等级: 关闭/低/中/高"
    )


# ==================== 车载电视 ====================

class VehicleTV(BaseModel):
    """车载电视状态"""

    is_on: bool = Field(default=False, description="是否开启")


# ==================== 车载冰箱 ====================

class FridgeMode(str, Enum):
    REFRIGERATION = "冷藏"
    FREEZING = "冷冻"


class Fridge(BaseModel):
    """车载冰箱状态"""

    is_on: bool = Field(default=False, description="是否开启")
    temperature: int = Field(default=4, ge=-20, le=10, description="目标温度°C")
    mode: FridgeMode = Field(default=FridgeMode.REFRIGERATION, description="冷藏/冷冻")


# ==================== 整车状态汇总 ====================

class VirtualCarDevices(BaseModel):
    """虚拟车所有设备状态汇总

    对应 projects/mind/toolset/car_control.py 可控制的设备。
    """

    # 驾驶
    driving: DrivingState = Field(default_factory=DrivingState)

    # 能源
    energy: EnergyState = Field(default_factory=EnergyState)

    # 空调
    ac: AirConditioner = Field(default_factory=AirConditioner)

    # 天窗
    sunroof: Sunroof = Field(default_factory=Sunroof)

    # 座椅（4座）
    seats: dict[str, Seat] = Field(
        default_factory=lambda: {
            "driver": Seat(seat_id="driver"),
            "passenger": Seat(seat_id="passenger"),
            "rear_left": Seat(seat_id="rear_left"),
            "rear_right": Seat(seat_id="rear_right"),
        }
    )

    # 车门/窗
    doors: dict[str, DoorWindow] = Field(
        default_factory=lambda: {
            "driver": DoorWindow(door_id="driver"),
            "passenger": DoorWindow(door_id="passenger"),
            "rear_left": DoorWindow(door_id="rear_left"),
            "rear_right": DoorWindow(door_id="rear_right"),
            "trunk": DoorWindow(door_id="trunk"),
            "hood": DoorWindow(door_id="hood"),
        }
    )

    # 灯光
    interior_light: InteriorLight = Field(default_factory=InteriorLight)
    exterior_light: ExteriorLight = Field(default_factory=ExteriorLight)

    # 媒体
    media: MediaState = Field(default_factory=MediaState)

    # 导航
    navigation: NavigationState = Field(default_factory=NavigationState)

    # 方向盘
    steering_wheel: SteeringWheel = Field(default_factory=SteeringWheel)

    # 车载电视
    tv: VehicleTV = Field(default_factory=VehicleTV)

    # 车载冰箱
    fridge: Fridge = Field(default_factory=Fridge)

    
