"""VirtualCar：虚拟车运行数据模型。

设计原则：
- devices 是唯一真相源（Pydantic 数据模型，带类型约束和校验）
- car_info dict 是只读派生视图，供假人 prompt 和 JSON 导出
- 前端 JSON 通过 _init_from_car_info 解析到 devices 实例
- 行为由 VirtualCarDriver 负责

设备覆盖面参考车机助手评测标签树的"车控操作"子树：
空调（开关/模式/温度/风量/风向）/ 车窗天窗遮阳帘（开合度）/
座椅（加热/通风/按摩/零重力模式）/ 方向盘加热 / 车内灯光（阅读灯/氛围灯）/
车外灯光（大灯模式）/ 车载电视 / 车载冰箱（温度/模式）/ 车门舱门（后备箱），
另含观察类信息：媒体（歌曲/歌手/歌单/三态播放状态/音源/音量）、
导航（状态/目的地）、乘员占用（四座是否有人/安全带）。

CAR_INFO_GROUPS 描述 car_info key 的展示分组（有序），
随 case_started 事件下发前端，供虚拟车状态面板分层分组展示。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from projects.experiments.time_travel_auto_test.virtual_car.car_devices import (
    ACAirDirection,
    ACFanLevel,
    ACMode,
    AmbientLightMode,
    ChargingStatus,
    DoorState,
    FridgeMode,
    Gear,
    IgnitionState,
    LightMode,
    MediaPlaybackStatus,
    SeatHeatLevel,
    SunroofState,
    VirtualCarDevices,
    WindowState,
)


# ============================================================
# 解析/格式化辅助
# ============================================================

def _parse_int_from_km_str(value: str) -> int:
    """从 '40 km/h'、'510 km' 等格式提取数值"""
    match = re.search(r'(\d+)\s*km', str(value))
    return int(match.group(1)) if match else 0


def _parse_int(value: Any, default: int) -> int:
    """从任意文本提取整数（'28摄氏度' → 28），无数字给默认值。"""
    match = re.search(r'(-?\d+)', str(value))
    return int(match.group(1)) if match else default


def _parse_bool(value: Any, default: bool = False) -> bool:
    """中文布尔解析：'开启'/'有人'/'已系'/'拉起' → True；'关闭'/'没人'/'未系' → False。"""
    v = str(value)
    if any(k in v for k in ("关", "没", "无", "否", "未", "停", "放下")):
        return False
    if any(k in v for k in ("开", "是", "有", "系", "拉")):
        return True
    return default


def _parse_level(value: Any, default: SeatHeatLevel = SeatHeatLevel.OFF) -> SeatHeatLevel:
    """档位解析：'关闭'/'1档'/'低'/'2档'/'中'/'3档'/'高' → 0-3。"""
    v = str(value)
    if "关" in v or "停" in v:
        return SeatHeatLevel.OFF
    for pat, lv in (("3", 3), ("三", 3), ("高", 3), ("2", 2), ("二", 2), ("两", 2), ("中", 2), ("1", 1), ("一", 1), ("低", 1)):
        if pat in v:
            return SeatHeatLevel(lv)
    return default


def _format_level(level: SeatHeatLevel) -> str:
    """档位 → '关闭'/'1档'/'2档'/'3档'。"""
    return {0: "关闭", 1: "1档", 2: "2档", 3: "3档"}.get(int(level), "关闭")


def _parse_open_percent(value: Any, default: int = 100) -> int:
    """开合度解析：'关闭'→0，'打开'→100，'半开 (50%)'/'50%'→50，'一条缝'→15。"""
    v = str(value)
    if "关" in v and "未关" not in v:
        return 0
    match = re.search(r'(\d+)', v)
    if match:
        return min(100, max(0, int(match.group(1))))
    if "缝" in v:
        return 15
    if "半" in v:
        return 50
    if "开" in v:
        return 100
    return default


def _format_open_percent(pct: int) -> str:
    """开合度 → '关闭'/'打开'/'半开 (50%)'。"""
    if pct <= 0:
        return "关闭"
    if pct >= 100:
        return "打开"
    return f"半开 ({pct}%)"


def _match_enum(value: Any, enum_cls: type, default: Any) -> Any:
    """中文文本匹配枚举成员（长值优先，避免'吹脸和脚'被'吹脸'抢先命中）。"""
    v = str(value)
    for member in sorted(enum_cls, key=lambda m: -len(m.value)):
        if member.value in v:
            return member
    return default


def _parse_gear(value: str) -> Gear:
    """从 'P档（驻车档）' 提取档位枚举"""
    for g in Gear:
        if g.value in str(value):
            return g
    return Gear.P


def _parse_ac_state(value: str) -> tuple[bool, ACMode]:
    """从 '制冷中' / '关闭中' / '加热中' 解析空调开关和模式"""
    v = str(value)
    if "关闭" in v:
        return False, ACMode.OFF
    if "制冷" in v:
        return True, ACMode.COOLING
    if "加热" in v or "制热" in v or "暖风" in v:
        return True, ACMode.HEATING
    if "通风" in v:
        return True, ACMode.VENTILATION
    if "自动" in v:
        return True, ACMode.AUTO
    return False, ACMode.OFF


def _format_ac_state(car: VirtualCar) -> str:  # type: ignore[type-arg]  # forward ref ok
    """空调状态 → car_info 文本"""
    ac = car.devices.ac
    if not ac.is_on or ac.mode == ACMode.OFF:
        return "关闭中"
    return f"{ac.mode.value}中"


def _parse_fan_level(value: Any) -> ACFanLevel:
    """空调风量：'自动'/'关闭'/'N档'/'低中高' → ACFanLevel。"""
    v = str(value)
    if "自动" in v:
        return ACFanLevel.AUTO
    if "关" in v:
        return ACFanLevel.OFF
    for pat, lv in (("3", 3), ("三", 3), ("高", 3), ("2", 2), ("二", 2), ("两", 2), ("中", 2), ("1", 1), ("一", 1), ("低", 1)):
        if pat in v:
            return ACFanLevel(lv)
    return ACFanLevel.AUTO


def _format_fan_level(level: ACFanLevel) -> str:
    """空调风量 → '关闭'/'1档'/'2档'/'3档'/'自动'。"""
    if level == ACFanLevel.AUTO:
        return "自动"
    return {0: "关闭", 1: "1档", 2: "2档", 3: "3档"}.get(int(level), "自动")


def _set_media_track(car: VirtualCar, field: str, value: Any) -> None:  # type: ignore[type-arg]
    """歌曲名/歌手名/歌单名：'无'/空 → None（未在播放）。"""
    v = str(value).strip()
    setattr(car.devices.media, field, None if (not v or v == "无") else v)


# ============================================================
# car_info key ↔ devices 字段映射
# ============================================================

# car_info key → (设定函数, 读取函数)
CAR_INFO_FIELD_MAP: dict[str, tuple] = {
    # ---- 行驶 ----
    "车辆当前行驶速度": (
        lambda car, v: setattr(car.devices.driving, "speed_kmh", _parse_int_from_km_str(v)),
        lambda car: f"{car.devices.driving.speed_kmh} km/h" + ("（静止）" if car.devices.driving.speed_kmh == 0 else ""),
    ),
    "车辆当前档位": (
        lambda car, v: setattr(car.devices.driving, "gear", _parse_gear(v)),
        lambda car: car.devices.driving.gear.value + f"（{_gear_label(car.devices.driving.gear)}）",
    ),
    "手刹状态": (
        lambda car, v: setattr(car.devices.driving, "handbrake", "拉起" in str(v)),
        lambda car: "拉起" if car.devices.driving.handbrake else "放下",
    ),
    "车辆点火状态": (
        lambda car, v: setattr(car.devices.driving, "ignition", _parse_ignition(v)),
        lambda car: car.devices.driving.ignition.value,
    ),
    "驾驶模式": (
        lambda car, v: _apply_drive_mode(car, v),
        lambda car: car.devices.driving.drive_mode.value,
    ),
    # ---- 能源 ----
    "剩余续航里程（新能源车）": (
        lambda car, v: setattr(car.devices.driving, "range_km", _parse_int_from_km_str(v)),
        lambda car: f"{car.devices.driving.range_km} km",
    ),
    "电池电量": (
        lambda car, v: setattr(car.devices.energy, "battery_soc_pct", _parse_int(v, 80)),
        lambda car: f"{car.devices.energy.battery_soc_pct}%",
    ),
    "充电状态": (
        lambda car, v: setattr(car.devices.energy, "charging_status", _parse_charging_status(v)),
        lambda car: car.devices.energy.charging_status.value,
    ),
    # ---- 空调 ----
    "空调开启状态及模式": (
        lambda car, v: _apply_ac_state(car, v),
        _format_ac_state,
    ),
    "空调温度": (
        lambda car, v: setattr(car.devices.ac, "temperature", _parse_int(v, 24)),
        lambda car: f"{car.devices.ac.temperature}°C",
    ),
    "车内温度": (
        lambda car, v: setattr(car.devices.ac, "temperature", _parse_int(v, 24)),
        lambda car: f"{car.devices.ac.temperature}摄氏度",
    ),
    "空调风量": (
        lambda car, v: setattr(car.devices.ac, "fan_level", _parse_fan_level(v)),
        lambda car: _format_fan_level(car.devices.ac.fan_level),
    ),
    "空调风向": (
        lambda car, v: setattr(car.devices.ac, "air_direction", _match_enum(v, ACAirDirection, ACAirDirection.AUTO)),
        lambda car: car.devices.ac.air_direction.value,
    ),
    "车外温度": (
        lambda car, v: setattr(car.devices.ac, "outside_temp_c", _parse_int(v, 25)),
        lambda car: f"{car.devices.ac.outside_temp_c}°C",
    ),
    # ---- 方向盘 ----
    "方向盘加热": (
        lambda car, v: setattr(car.devices.steering_wheel, "heating_level", _parse_level(v)),
        lambda car: _format_level(car.devices.steering_wheel.heating_level),
    ),
    # ---- 座椅/乘员/门窗（四座统一注册，见 _register_seat_fields） ----
    # ---- 后备箱 ----
    "后备箱状态": (
        lambda car, v: _apply_door_state(car, "trunk", v),
        lambda car: car.devices.doors["trunk"].door_state.value,
    ),
    # ---- 安全带 ----
    "主驾安全带": (
        lambda car, v: setattr(car.devices.seats["driver"], "seat_belt", _parse_bool(v)),
        lambda car: "已系" if car.devices.seats["driver"].seat_belt else "未系",
    ),
    "副驾安全带": (
        lambda car, v: setattr(car.devices.seats["passenger"], "seat_belt", _parse_bool(v)),
        lambda car: "已系" if car.devices.seats["passenger"].seat_belt else "未系",
    ),
    # ---- 天窗 / 遮阳帘 ----
    "天窗状态": (
        lambda car, v: _apply_sunroof_state(car, v),
        lambda car: _format_sunroof_state(car),
    ),
    "遮阳帘开合度": (
        lambda car, v: setattr(car.devices.sunroof, "shade_open_percent", _parse_open_percent(v, default=0)),
        lambda car: _format_open_percent(car.devices.sunroof.shade_open_percent),
    ),
    # ---- 车内灯光 ----
    "主驾阅读灯": (
        lambda car, v: setattr(car.devices.interior_light, "reading_light_driver", _parse_bool(v)),
        lambda car: "开启" if car.devices.interior_light.reading_light_driver else "关闭",
    ),
    "副驾阅读灯": (
        lambda car, v: setattr(car.devices.interior_light, "reading_light_passenger", _parse_bool(v)),
        lambda car: "开启" if car.devices.interior_light.reading_light_passenger else "关闭",
    ),
    "阅读灯亮度": (
        lambda car, v: setattr(car.devices.interior_light, "reading_light_brightness", _parse_int(v, 70)),
        lambda car: f"{car.devices.interior_light.reading_light_brightness}%",
    ),
    "氛围灯": (
        lambda car, v: setattr(car.devices.interior_light, "ambient_light_on", _parse_bool(v)),
        lambda car: "开启" if car.devices.interior_light.ambient_light_on else "关闭",
    ),
    "氛围灯颜色": (
        lambda car, v: setattr(car.devices.interior_light, "ambient_light_color", str(v)),
        lambda car: car.devices.interior_light.ambient_light_color,
    ),
    "氛围灯亮度": (
        lambda car, v: setattr(car.devices.interior_light, "ambient_light_brightness", _parse_int(v, 50)),
        lambda car: f"{car.devices.interior_light.ambient_light_brightness}%",
    ),
    "氛围灯模式": (
        lambda car, v: setattr(car.devices.interior_light, "ambient_light_mode", _match_enum(v, AmbientLightMode, AmbientLightMode.FLOWING)),
        lambda car: car.devices.interior_light.ambient_light_mode.value,
    ),
    # ---- 车外灯光 ----
    "大灯模式": (
        lambda car, v: setattr(car.devices.exterior_light, "headlight_mode", _match_enum(v, LightMode, LightMode.AUTO)),
        lambda car: car.devices.exterior_light.headlight_mode.value,
    ),
    # ---- 媒体 ----
    "多媒体播放状态": (
        lambda car, v: setattr(car.devices.media, "playback_status", _match_enum(v, MediaPlaybackStatus, MediaPlaybackStatus.STOPPED)),
        lambda car: car.devices.media.playback_status.value,
    ),
    "正在播放的歌曲名": (
        lambda car, v: _set_media_track(car, "current_track", v),
        lambda car: car.devices.media.current_track or "无",
    ),
    "正在播放的歌手名": (
        lambda car, v: _set_media_track(car, "artist", v),
        lambda car: car.devices.media.artist or "无",
    ),
    "正在播放的歌单名": (
        lambda car, v: _set_media_track(car, "playlist", v),
        lambda car: car.devices.media.playlist or "无",
    ),
    "音源": (
        lambda car, v: setattr(car.devices.media, "source", str(v)),
        lambda car: car.devices.media.source,
    ),
    "音量": (
        lambda car, v: setattr(car.devices.media, "volume", _parse_int(v, 30)),
        lambda car: f"{car.devices.media.volume}%",
    ),
    # ---- 导航 ----
    "导航目的地": (
        lambda car, v: _apply_nav_destination(car, v),
        lambda car: car.devices.navigation.destination or "未设置",
    ),
    "导航状态": (
        lambda car, v: setattr(car.devices.navigation, "is_navigating", "导航中" in str(v) or "是" in str(v)),
        lambda car: "导航中" if car.devices.navigation.is_navigating else "未导航",
    ),
    # ---- 车载电器 ----
    "车载电视": (
        lambda car, v: setattr(car.devices.tv, "is_on", _parse_bool(v)),
        lambda car: "开启中" if car.devices.tv.is_on else "关闭中",
    ),
    "车载冰箱": (
        lambda car, v: setattr(car.devices.fridge, "is_on", _parse_bool(v)),
        lambda car: "开启中" if car.devices.fridge.is_on else "关闭中",
    ),
    "冰箱温度": (
        lambda car, v: setattr(car.devices.fridge, "temperature", _parse_int(v, 4)),
        lambda car: f"{car.devices.fridge.temperature}°C",
    ),
    "冰箱模式": (
        lambda car, v: setattr(car.devices.fridge, "mode", _match_enum(v, FridgeMode, FridgeMode.REFRIGERATION)),
        lambda car: car.devices.fridge.mode.value,
    ),
}

# 四座统一注册：座椅加热/通风/按摩/模式 + 是否有人 + 门状态 + 车窗开合度
_SEAT_PREFIXES: list[tuple[str, str]] = [
    ("主驾", "driver"),
    ("副驾", "passenger"),
    ("二排左侧", "rear_left"),
    ("二排右侧", "rear_right"),
]
_SEAT_FUNCS: list[str] = ["加热", "通风", "按摩", "模式"]


def _register_seat_fields() -> None:
    """按 座位前缀 × 功能 批量注册 car_info 字段（闭包用默认参数绑定 seat_id）。"""
    for prefix, seat_id in _SEAT_PREFIXES:
        CAR_INFO_FIELD_MAP[f"{prefix}座椅加热"] = (
            lambda car, v, sid=seat_id: setattr(car.devices.seats[sid], "heater_level", _parse_level(v)),
            lambda car, sid=seat_id: _format_level(car.devices.seats[sid].heater_level),
        )
        CAR_INFO_FIELD_MAP[f"{prefix}座椅通风"] = (
            lambda car, v, sid=seat_id: setattr(car.devices.seats[sid], "ventilation_level", _parse_level(v)),
            lambda car, sid=seat_id: _format_level(car.devices.seats[sid].ventilation_level),
        )
        CAR_INFO_FIELD_MAP[f"{prefix}座椅按摩"] = (
            lambda car, v, sid=seat_id: _apply_massage_mode(car, sid, v),
            lambda car, sid=seat_id: car.devices.seats[sid].massage_mode,
        )
        CAR_INFO_FIELD_MAP[f"{prefix}座椅模式"] = (
            lambda car, v, sid=seat_id: setattr(
                car.devices.seats[sid], "seat_mode", "零重力" if "零重力" in str(v) else "标准"
            ),
            lambda car, sid=seat_id: car.devices.seats[sid].seat_mode,
        )
        CAR_INFO_FIELD_MAP[f"{prefix}是否有人"] = (
            lambda car, v, sid=seat_id: setattr(car.devices.seats[sid], "is_occupied", _parse_bool(v)),
            lambda car, sid=seat_id: "有人" if car.devices.seats[sid].is_occupied else "没人",
        )
        CAR_INFO_FIELD_MAP[f"{prefix}门状态"] = (
            lambda car, v, sid=seat_id: _apply_door_state(car, sid, v),
            lambda car, sid=seat_id: car.devices.doors[sid].door_state.value,
        )
        CAR_INFO_FIELD_MAP[f"{prefix}车窗"] = (
            lambda car, v, sid=seat_id: _apply_window_percent(car, sid, v),
            lambda car, sid=seat_id: _format_open_percent(car.devices.doors[sid].window_open_percent),
        )


def _apply_massage_mode(car: VirtualCar, seat_id: str, value: Any) -> None:  # type: ignore[type-arg]
    """按摩模式：关闭/轻柔/舒缓/活力（未匹配值按关闭处理）。"""
    v = str(value)
    for mode in ("轻柔", "舒缓", "活力"):
        if mode in v:
            car.devices.seats[seat_id].massage_mode = mode
            return
    car.devices.seats[seat_id].massage_mode = "关闭"


def _apply_window_percent(car: VirtualCar, door_id: str, value: Any) -> None:  # type: ignore[type-arg]
    """车窗开合度：百分比 + 状态枚举联动。"""
    pct = _parse_open_percent(value)
    door = car.devices.doors[door_id]
    door.window_open_percent = pct
    door.window_state = (
        WindowState.CLOSED if pct <= 0 else (WindowState.OPEN if pct >= 100 else WindowState.PARTIAL)
    )


_register_seat_fields()

# car_info key 展示分组（有序）：随 case_started 下发前端，虚拟车状态面板分层展示
CAR_INFO_GROUPS: dict[str, list[str]] = {
    "行驶与能源": [
        "车辆当前行驶速度", "车辆当前档位", "手刹状态", "车辆点火状态", "驾驶模式",
        "剩余续航里程（新能源车）", "电池电量", "充电状态",
    ],
    "空调": [
        "空调开启状态及模式", "空调温度", "车内温度", "空调风量", "空调风向", "车外温度",
    ],
    "座椅与方向盘": [
        *(f"{p}座椅{func}" for p, _ in _SEAT_PREFIXES for func in _SEAT_FUNCS),
        "方向盘加热",
    ],
    "乘员": [
        *(f"{p}是否有人" for p, _ in _SEAT_PREFIXES),
        "主驾安全带", "副驾安全带",
    ],
    "门窗与天窗": [
        *(f"{p}门状态" for p, _ in _SEAT_PREFIXES),
        "后备箱状态",
        *(f"{p}车窗" for p, _ in _SEAT_PREFIXES),
        "天窗状态", "遮阳帘开合度",
    ],
    "灯光": [
        "主驾阅读灯", "副驾阅读灯", "阅读灯亮度",
        "氛围灯", "氛围灯颜色", "氛围灯亮度", "氛围灯模式",
        "大灯模式",
    ],
    "媒体": [
        "多媒体播放状态", "正在播放的歌曲名", "正在播放的歌手名",
        "正在播放的歌单名", "音源", "音量",
    ],
    "导航": ["导航状态", "导航目的地"],
    "车载电器": ["车载电视", "车载冰箱", "冰箱温度", "冰箱模式"],
}

# 无法预定义结构的自由元数据 key
FREE_FORM_KEYS = {
    "当前位置", "当前系统时间", "中控屏幕状态（智能车重点）",
    "语音助手唤醒词", "空调状态",
}


def _gear_label(gear: Gear) -> str:
    labels = {Gear.P: "驻车档", Gear.R: "倒档", Gear.N: "空档", Gear.D: "前进档", Gear.S: "运动档"}
    return labels.get(gear, "未知")


def _apply_ac_state(car: VirtualCar, value: str) -> None:  # type: ignore[type-arg]
    is_on, mode = _parse_ac_state(value)
    car.devices.ac.is_on = is_on
    car.devices.ac.mode = mode


def _apply_nav_destination(car: VirtualCar, value: str) -> None:  # type: ignore[type-arg]
    v = str(value)
    if v and v != "未设置":
        car.devices.navigation.destination = v
        car.devices.navigation.is_navigating = True
    else:
        car.devices.navigation.destination = None
        car.devices.navigation.is_navigating = False


def _apply_door_state(car: VirtualCar, door_id: str, value: str) -> None:  # type: ignore[type-arg]
    v = str(value)
    door = car.devices.doors[door_id]
    for state in DoorState:
        if state.value in v:
            door.door_state = state
            return
    door.door_state = DoorState.CLOSED_LOCKED


def _parse_ignition(value: str) -> IgnitionState:
    """从 '关闭' / '通电' / '启动' 等解析点火状态"""
    v = str(value)
    for state in IgnitionState:
        if state.value in v:
            return state
    return IgnitionState.ON


def _parse_charging_status(value: str) -> ChargingStatus:
    """从 '慢充中' / '快充中' / '未充电' 解析充电状态"""
    v = str(value)
    for status in ChargingStatus:
        if status.value in v or (status == ChargingStatus.SLOW_CHARGING and "慢充" in v) or (status == ChargingStatus.FAST_CHARGING and "快充" in v):
            return status
    return ChargingStatus.NOT_CHARGING


def _apply_sunroof_state(car: VirtualCar, value: str) -> None:  # type: ignore[type-arg]
    """从 '打开' / '关闭' / '翘起' / '半开 (50%)' 解析天窗状态"""
    v = str(value)
    pct_match = re.search(r'(\d+)%', v)
    if pct_match:
        car.devices.sunroof.open_percent = int(pct_match.group(1))
    for state in SunroofState:
        if state.value in v:
            car.devices.sunroof.state = state
            if state == SunroofState.CLOSED:
                car.devices.sunroof.open_percent = 0
            elif state == SunroofState.OPEN and car.devices.sunroof.open_percent == 0:
                car.devices.sunroof.open_percent = 100
            return
    car.devices.sunroof.state = SunroofState.CLOSED


def _format_sunroof_state(car: VirtualCar) -> str:  # type: ignore[type-arg]
    """天窗状态 → car_info 文本"""
    sr = car.devices.sunroof
    if sr.state == SunroofState.CLOSED:
        return "关闭"
    if sr.open_percent > 0 and sr.open_percent < 100:
        return f"{sr.state.value} ({sr.open_percent}%)"
    return sr.state.value


def _apply_drive_mode(car: VirtualCar, value: str) -> None:  # type: ignore[type-arg]
    """从 '经济' / '舒适' / '运动' / '自定义' 解析驾驶模式"""
    v = str(value)
    from projects.experiments.time_travel_auto_test.virtual_car.car_devices import DriveMode
    for mode in DriveMode:
        if mode.value in v:
            car.devices.driving.drive_mode = mode
            return
    car.devices.driving.drive_mode = DriveMode.COMFORT


# ============================================================
# Outcome 类型
# ============================================================

def format_car_info(car_info: dict[str, Any]) -> str:
    """将 car_info dict 格式化为假人 prompt 可读的多行文本。"""
    if not car_info:
        return "无"
    return "\n".join(f"- {key}: {value}" for key, value in car_info.items())


class VirtualCarSetStateOutcome(BaseModel):
    updated_fields: dict[str, Any] = Field(description="本次写入/覆盖的字段")
    car_info: dict[str, Any] = Field(description="更新后的完整 car_info 快照")


class VirtualCarStateCheckOutcome(BaseModel):
    expected_fields: dict[str, Any]
    passed: bool
    mismatches: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="未通过的字段：field → {expected, actual}",
    )
    car_info: dict[str, Any] = Field(description="断言时刻的 car_info 快照")


class VirtualCarEventResult(BaseModel):
    """虚拟车执行一次剧本事件的结果。"""

    event_at: Optional[datetime] = None
    outcome: VirtualCarSetStateOutcome | VirtualCarStateCheckOutcome


# ============================================================
# VirtualCar 纯数据模型
# ============================================================

class VirtualCar:
    """虚拟车：devices 为唯一真相源，car_info 为只读派生视图。

    行为由 VirtualCarDriver 负责。

    车态变更钩子（旁路观察，2026-08-27）：
    - on_field_change(key, old_value, new_value)：set_field 写入且值真正变化时回调
    - notify_enabled：剧本 set_state 等批量路径可临时关闭（该路径由 Runner 统一
      以"多字段一条"的既有格式记录 trace，避免逐字段拆分双记录）
    - 不注入钩子时零开销，纯数据模型语义不变（中立观察者原则）
    """

    def __init__(self, car_info: dict[str, Any] | None = None) -> None:
        self.devices: VirtualCarDevices = VirtualCarDevices()
        self._free_form_fields: dict[str, Any] = {}
        self.on_field_change: Callable[[str, Any, Any], None] | None = None
        self.notify_enabled: bool = True
        if car_info:
            self._init_from_car_info(car_info)

    def _init_from_car_info(self, car_info: dict[str, Any]) -> None:
        """从 JSON dict 初始化 devices 实例。"""
        for key, value in car_info.items():
            if key in CAR_INFO_FIELD_MAP:
                setter, _ = CAR_INFO_FIELD_MAP[key]
                setter(self, value)
            else:
                self._free_form_fields[key] = value

    # ---------------- car_info 只读视图 ----------------

    @property
    def car_info(self) -> dict[str, Any]:
        """devices → car_info dict（只读派生视图，含全部分类字段）。"""
        info: dict[str, Any] = {}
        for key, (_, getter) in CAR_INFO_FIELD_MAP.items():
            info[key] = getter(self)
        info.update(self._free_form_fields)
        return info

    def car_info_text(self) -> str:
        """供假人 prompt 使用的多行文本。"""
        return format_car_info(self.car_info)

    # ---------------- 设备快捷访问 ----------------

    @property
    def driving(self):
        return self.devices.driving

    @property
    def ac(self):
        return self.devices.ac

    @property
    def seats(self):
        return self.devices.seats

    @property
    def doors(self):
        return self.devices.doors

    @property
    def media(self):
        return self.devices.media

    @property
    def navigation(self):
        return self.devices.navigation

    # ---------------- 车控工具专用接口 ----------------

    def set_field(self, key: str, value: Any) -> None:
        """车控工具直接写单个字段（走 devices 映射或透传）。

        值真正变化且钩子注入时通知 on_field_change(key, old, new)——
        写后读值，保证通知值与 car_info 视图一致。
        """
        if key in CAR_INFO_FIELD_MAP:
            setter, getter = CAR_INFO_FIELD_MAP[key]
            old_value = getter(self)
            setter(self, value)
            new_value = getter(self)
        else:
            old_value = self._free_form_fields.get(key)
            self._free_form_fields[key] = value
            new_value = value
        if (
            self.on_field_change is not None
            and self.notify_enabled
            and old_value != new_value
        ):
            self.on_field_change(key, old_value, new_value)

    def get_field(self, key: str) -> Any:
        """车控工具读单个字段。"""
        if key in CAR_INFO_FIELD_MAP:
            _, getter = CAR_INFO_FIELD_MAP[key]
            return getter(self)
        return self._free_form_fields.get(key)
