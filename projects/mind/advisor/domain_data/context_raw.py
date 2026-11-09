from typing import Any

from pydantic import BaseModel, Field, RootModel, model_validator

from rich import print

from projects.mind.advisor.domain_data.vehicle_state import (
    ADSDState,
    MediaState,
    NavigationState,
    SignalLightState,
    SystemControlState,
    VehicleControlState,
    VehicleState,
)

from projects.mind.advisor.domain_data.visual_int import PersonState, InteriorScene, VisualInterior

import projects.mind.advisor.domain_data.world_info as wi

from projects.mind.advisor.domain_data.memory import EpisodicMemoryBlock, EpisodicMemory

class Retrieval(BaseModel):
    """检索上下文"""
    basic_info: str = Field(default="", title="基本信息", description="基本信息")
    long_memory: str = Field(default="", title="长记忆", description="长记忆")


class VehicleResourceItem(BaseModel):
    """车辆资源项"""
    desc: str = Field(default="", title="描述", description="描述")
    args: list[dict[str, Any]] = Field(default_factory=list, title="参数", description="参数")
    old_args: list[dict[str, Any]] = Field(default_factory=list, title="旧参数", description="旧参数")


class VehicleResource(RootModel[dict[str, VehicleResourceItem]]):
    """车辆资源"""
    
    def as_state(self) -> VehicleState:
        """转换为车辆状态"""
        root = self.root
        
        media = MediaState(
            audio_signal=root["media_0001"].args[0] if root["media_0001"].args else None,
            video_signal=root["media_0002"].args[0] if root["media_0002"].args else None)

        adsd = ADSDState(
            adaptive_cruise=root["adsd_0001"].args[0] if root["adsd_0001"].args else None,
            full_speed_driving_assist=root["adsd_0002"].args[0] if root["adsd_0002"].args else None,
            pilot_assist=root["adsd_0003"].args[0] if root["adsd_0003"].args else None,
            lane_change_confirm=root["adsd_0004"].args[0] if root["adsd_0004"].args else None,
            trust_enhance=root["adsd_0005"].args[0] if root["adsd_0005"].args else None,
            open_road_noa=root["adsd_0006"].args[0] if root["adsd_0006"].args else None,
            pilot_full_speed=root["adsd_0007"].args[0] if root["adsd_0007"].args else None,
            calc_lane_change=root["adsd_0008"].args[0] if root["adsd_0008"].args else None,
            driving_style=root["adsd_0009"].args[0] if root["adsd_0009"].args else None,
            start_reminder=root["adsd_0010"].args[0] if root["adsd_0010"].args else None,
            speed_limit_range=root["adsd_0011"].args[0] if root["adsd_0011"].args else None,
            speed_limit_fixed=root["adsd_0012"].args[0] if root["adsd_0012"].args else None,
            speed_limit_percent=root["adsd_0013"].args[0] if root["adsd_0013"].args else None,
            speed_limit_alarm=root["adsd_0014"].args[0] if root["adsd_0014"].args else None,
            forward_collision_warning=root["adsd_0015"].args[0] if root["adsd_0015"].args else None,
            fcw_sensitivity=root["adsd_0016"].args[0] if root["adsd_0016"].args else None,
            aeb=root["adsd_0017"].args[0] if root["adsd_0017"].args else None,
            rear_collision_warning=root["adsd_0018"].args[0] if root["adsd_0018"].args else None,
            blind_spot_warning=root["adsd_0019"].args[0] if root["adsd_0019"].args else None,
            rear_cross_traffic=root["adsd_0020"].args[0] if root["adsd_0020"].args else None,
            door_open_warning=root["adsd_0021"].args[0] if root["adsd_0021"].args else None,
            lane_departure_assist=root["adsd_0022"].args[0] if root["adsd_0022"].args else None,
            lda_sensitivity=root["adsd_0023"].args[0] if root["adsd_0023"].args else None,
            ldw_alert_mode=root["adsd_0024"].args[0] if root["adsd_0024"].args else None,
            lane_keep=root["adsd_0025"].args[0] if root["adsd_0025"].args else None,
        )

        navigation = NavigationState(
            navigation_status=root["navigation_0001"].args[0] if root["navigation_0001"].args else None,
            destination=root["navigation_0002"].args[0] if root["navigation_0002"].args else None,
            destination_type=root["navigation_0003"].args[0] if root["navigation_0003"].args else None,
            destination_info=root["navigation_0004"].args[0] if root["navigation_0004"].args else None,
            road_condition=root["navigation_0005"].args[0] if root["navigation_0005"].args else None,
            heavy_traffic=root["navigation_0006"].args[0] if root["navigation_0006"].args else None,
            waypoint=root["navigation_0007"].args[0] if root["navigation_0007"].args else None,
            service_area=root["navigation_0008"].args[0] if root["navigation_0008"].args else None,
        )

        signal_light = SignalLightState(
            low_beam=root["signal_light_0001"].args[0] if root["signal_light_0001"].args else None,
            high_beam=root["signal_light_0002"].args[0] if root["signal_light_0002"].args else None,
            high_beam_switch=root["signal_light_0003"].args[0] if root["signal_light_0003"].args else None,
            rear_fog_light=root["signal_light_0004"].args[0] if root["signal_light_0004"].args else None,
            position_light=root["signal_light_0005"].args[0] if root["signal_light_0005"].args else None,
            left_turn_signal=root["signal_light_0006"].args[0] if root["signal_light_0006"].args else None,
            right_turn_signal=root["signal_light_0007"].args[0] if root["signal_light_0007"].args else None,
            intelligent_headlight=root["signal_light_0008"].args[0] if root["signal_light_0008"].args else None,
            afs_fault=root["signal_light_0009"].args[0] if root["signal_light_0009"].args else None,
            abs_fault=root["signal_light_0010"].args[0] if root["signal_light_0010"].args else None,
            brake_fault=root["signal_light_0011"].args[0] if root["signal_light_0011"].args else None,
            esp_fault=root["signal_light_0012"].args[0] if root["signal_light_0012"].args else None,
            esp_working=root["signal_light_0013"].args[0] if root["signal_light_0013"].args else None,
            tcs_fault=root["signal_light_0014"].args[0] if root["signal_light_0014"].args else None,
            autohold_active=root["signal_light_0015"].args[0] if root["signal_light_0015"].args else None,
            autohold_ready=root["signal_light_0016"].args[0] if root["signal_light_0016"].args else None,
            autohold_fault=root["signal_light_0017"].args[0] if root["signal_light_0017"].args else None,
            four_wheel_drive=root["signal_light_0018"].args[0] if root["signal_light_0018"].args else None,
            tire_pressure_warning=root["signal_light_0019"].args[0] if root["signal_light_0019"].args else None,
            tire_pressure_fault=root["signal_light_0020"].args[0] if root["signal_light_0020"].args else None,
            charging_fault=root["signal_light_0021"].args[0] if root["signal_light_0021"].args else None,
            auxiliary_power_fault=root["signal_light_0022"].args[0] if root["signal_light_0022"].args else None,
            airbag_fault=root["signal_light_0023"].args[0] if root["signal_light_0023"].args else None,
            airbag_uncalibrated=root["signal_light_0024"].args[0] if root["signal_light_0024"].args else None,
            front_seatbelt_warning=root["signal_light_0025"].args[0] if root["signal_light_0025"].args else None,
            rear_seatbelt_warning=root["signal_light_0026"].args[0] if root["signal_light_0026"].args else None,
            pedestrian_protection_warning=root["signal_light_0027"].args[0] if root["signal_light_0027"].args else None,
            steering_fault=root["signal_light_0028"].args[0] if root["signal_light_0028"].args else None,
            steering_angle_fault=root["signal_light_0029"].args[0] if root["signal_light_0029"].args else None,
            escl_fault=root["signal_light_0030"].args[0] if root["signal_light_0030"].args else None,
            steering_reduced=root["signal_light_0031"].args[0] if root["signal_light_0031"].args else None,
            epb_indicator=root["signal_light_0032"].args[0] if root["signal_light_0032"].args else None,
            epb_not_released=root["signal_light_0033"].args[0] if root["signal_light_0033"].args else None,
            epb_fault=root["signal_light_0034"].args[0] if root["signal_light_0034"].args else None,
            key_warning=root["signal_light_0035"].args[0] if root["signal_light_0035"].args else None,
            power_battery_fault=root["signal_light_0036"].args[0] if root["signal_light_0036"].args else None,
            power_battery_level=root["signal_light_0037"].args[0] if root["signal_light_0037"].args else None,
            power_battery_low=root["signal_light_0038"].args[0] if root["signal_light_0038"].args else None,
            charge_gun_connected=root["signal_light_0039"].args[0] if root["signal_light_0039"].args else None,
            charging=root["signal_light_0040"].args[0] if root["signal_light_0040"].args else None,
            charge_discharge_fault=root["signal_light_0041"].args[0] if root["signal_light_0041"].args else None,
            discharging=root["signal_light_0042"].args[0] if root["signal_light_0042"].args else None,
            gear_invalid=root["signal_light_0043"].args[0] if root["signal_light_0043"].args else None,
            system_ready=root["signal_light_0044"].args[0] if root["signal_light_0044"].args else None,
            system_fault=root["signal_light_0045"].args[0] if root["signal_light_0045"].args else None,
            power_limited=root["signal_light_0046"].args[0] if root["signal_light_0046"].args else None,
            motor_fault=root["signal_light_0047"].args[0] if root["signal_light_0047"].args else None,
            air_suspension_fault=root["signal_light_0048"].args[0] if root["signal_light_0048"].args else None,
            ecall_status=root["signal_light_0049"].args[0] if root["signal_light_0049"].args else None,
            rear_wheel_steering_fault=root["signal_light_0050"].args[0] if root["signal_light_0050"].args else None,
            hazard_warning=root["signal_light_0051"].args[0] if root["signal_light_0051"].args else None,
            ambient_light=root["signal_light_0052"].args[0] if root["signal_light_0052"].args else None,
            reading_light=root["signal_light_0053"].args[0] if root["signal_light_0053"].args else None,
        )

        system_control = SystemControlState(
            maintenance_info=root["system_control_0001"].args[0] if root["system_control_0001"].args else None,
            display_mode=root["system_control_0002"].args[0] if root["system_control_0002"].args else None,
            passenger_info=root["system_control_0003"].args[0] if root["system_control_0003"].args else None,
        )

        vehicle_control = VehicleControlState(
            driving_mode=root["vehicle_control_0003"].args[0] if root["vehicle_control_0003"].args else None,
            vehicle_speed=root["vehicle_control_0004"].args[0] if root["vehicle_control_0004"].args else None,
            energy_recovery=root["vehicle_control_0005"].args[0] if root["vehicle_control_0005"].args else None,
            gear=root["vehicle_control_0006"].args[0] if root["vehicle_control_0006"].args else None,
            regenerative_braking=root["vehicle_control_0007"].args[0] if root["vehicle_control_0007"].args else None,
            tire_info=root["vehicle_control_0008"].args[0] if root["vehicle_control_0008"].args else None,
            charging_port=root["vehicle_control_0009"].args[0] if root["vehicle_control_0009"].args else None,
            charging_status=root["vehicle_control_0010"].args[0] if root["vehicle_control_0010"].args else None,
            charging_limit=root["vehicle_control_0011"].args[0] if root["vehicle_control_0011"].args else None,
            battery_info=root["vehicle_control_0012"].args[0] if root["vehicle_control_0012"].args else None,
            air_condition=root["vehicle_control_0013"].args[0] if root["vehicle_control_0013"].args else None,
            air_direction=root["vehicle_control_0014"].args[0] if root["vehicle_control_0014"].args else None,
            air_circulation=root["vehicle_control_0015"].args[0] if root["vehicle_control_0015"].args else None,
            air_cooling=root["vehicle_control_0016"].args[0] if root["vehicle_control_0016"].args else None,
            defrost_defog=root["vehicle_control_0017"].args[0] if root["vehicle_control_0017"].args else None,
            air_purification=root["vehicle_control_0018"].args[0] if root["vehicle_control_0018"].args else None,
            fan_speed_front=root["vehicle_control_0019"].args[0] if root["vehicle_control_0019"].args else None,
            fan_speed_rear=root["vehicle_control_0020"].args[0] if root["vehicle_control_0020"].args else None,
            interior_temperature=root["vehicle_control_0021"].args[0] if root["vehicle_control_0021"].args else None,
            seat_position=root["vehicle_control_0022"].args[0] if root["vehicle_control_0022"].args else None,
            seat_ventilation=root["vehicle_control_0023"].args[0] if root["vehicle_control_0023"].args else None,
            seat_heating=root["vehicle_control_0024"].args[0] if root["vehicle_control_0024"].args else None,
            seat_massage=root["vehicle_control_0025"].args[0] if root["vehicle_control_0025"].args else None,
            seat_belt_status=root["vehicle_control_0026"].args[0] if root["vehicle_control_0026"].args else None,
            window_status=root["vehicle_control_0027"].args[0] if root["vehicle_control_0027"].args else None,
            door_status=root["vehicle_control_0028"].args[0] if root["vehicle_control_0028"].args else None,
            sunshade_left_rear=root["vehicle_control_0029"].args[0] if root["vehicle_control_0029"].args else None,
            sunshade_right_rear=root["vehicle_control_0030"].args[0] if root["vehicle_control_0030"].args else None,
            rearview_mirror=root["vehicle_control_0031"].args[0] if root["vehicle_control_0031"].args else None,
            wiper_status=root["vehicle_control_0032"].args[0] if root["vehicle_control_0032"].args else None,
            steering_wheel_heating=root["vehicle_control_0033"].args[0] if root["vehicle_control_0033"].args else None,
            fragrance_system=root["vehicle_control_0034"].args[0] if root["vehicle_control_0034"].args else None,
            volume_status=root["vehicle_control_0035"].args[0] if root["vehicle_control_0035"].args else None,
            sunroof_status=root["vehicle_control_0036"].args[0] if root["vehicle_control_0036"].args else None,
            tailgate_status=root["vehicle_control_0037"].args[0] if root["vehicle_control_0037"].args else None,
            radar_status=root["vehicle_control_0038"].args[0] if root["vehicle_control_0038"].args else None,
            panoramic_camera=root["vehicle_control_0039"].args[0] if root["vehicle_control_0039"].args else None,
            calendar_time=root["vehicle_control_0040"].args[0] if root["vehicle_control_0040"].args else None,
            auto_parking=root["vehicle_control_0041"].args[0] if root["vehicle_control_0041"].args else None,
        )

        return VehicleState(
            media=media,
            adsd=adsd,
            navigation=navigation,
            signal_light=signal_light,
            system_control=system_control,
            vehicle_control=vehicle_control,
        )


class Person(BaseModel):
    """人员信息"""
    position: str = Field(default="", title="位置", description="位置")
    sex: str = Field(default="", title="性别", description="性别")
    age: str = Field(default="", title="年龄", description="年龄")
    expression: str = Field(default="", title="表情", description="表情")
    seat_belt_status: str = Field(default="", title="安全带状态", description="安全带状态")
    appearance: dict[str, str] = Field(default_factory=dict, title="外貌", description="外貌")
    clothes: dict[str, str] = Field(default_factory=dict, title="衣服", description="衣服")
    accessories: list[str] = Field(default_factory=list, title="配饰", description="配饰")


class InCarItems(BaseModel):
    """车内物品"""
    child_seat: dict[str, str] = Field(default_factory=dict, title="儿童座椅", description="儿童座椅")
    pet: dict[str, str] = Field(default_factory=dict, title="宠物", description="宠物")


class SceneDescriptionItem(BaseModel):
    """场景描述项"""
    people: list[Person] = Field(default_factory=list, title="人员", description="人员")
    in_car_items: InCarItems = Field(default_factory=InCarItems, title="车内物品", description="车内物品")


class SceneDescription(RootModel[dict[str, list[SceneDescriptionItem]]]):
    """场景描述
    TODO: dict key 是camera id的意思? 那么, 需要融合多个camera的信息。
    SceneDescriptionItem内部都有list，已经完整描述了车内的人和物。
    TODO: 因此，dict value中的list非常奇怪。其理应只有一个元素。
    """
    
    @model_validator(mode="after")
    def validate_scene_description_items(self) -> "SceneDescription":
        for camera_id, items in self.root.items():
            if len(items) != 1:
                raise ValueError(f"Camera {camera_id} should have exactly one SceneDescriptionItem, but got {len(items)}")
        return self

    def as_visual_interior(self) -> VisualInterior:
        """转换为内部视觉信息"""

        scenes: dict[str, InteriorScene] = {}

        for camera_id, items in self.root.items():
            item = items[0]  # 只有一个
            
            scenes[camera_id] = InteriorScene(
                persons=[PersonState(**person.model_dump()) for person in item.people],
                child_seat=item.in_car_items.child_seat,
                pet=item.in_car_items.pet,
            )

        return VisualInterior(scenes=scenes)


class MemoryItem(BaseModel):
    """记忆项"""
    update_at: int = Field(default=0, title="更新时间", description="更新时间")

    memory: str = Field(default="", title="记忆", description="记忆")
    
    date: int = Field(default=0, title="日期", description="日期")
    '''
    居然是一个类似于20251226的int, 这工程素养也是醉了。
    # TODO: 需要转换类型
    '''

    def as_episodic_memory_block(self) -> EpisodicMemoryBlock:
        """转换为事件记忆块"""
        return EpisodicMemoryBlock(
            date_time=str(self.date),
            content=self.memory,
            details = {"update_at": self.update_at},
        )


class Memory(BaseModel):
    """记忆"""
    long_term_memory: list[MemoryItem] = Field(default_factory=list, title="长期记忆", description="长期记忆")
    '''长期记忆, 没有date。它实际上指的应该是类似于于用户偏好之类的语义记忆
    TODO: 应该还没有实现，不做转换了。需要确认。
    '''
    
    long_term_scene_memory: list[MemoryItem] = Field(default_factory=list, title="长期场景记忆", description="长期场景记忆")
    '''和long_term_memory的区别是, date有值, 所以是场景记忆'''
    
    short_term_scene_memory: list[MemoryItem] = Field(default_factory=list, title="短期场景记忆", description="短期场景记忆")

    def as_episodic_memory(self) -> EpisodicMemory:
        """转换为事件记忆"""

        return EpisodicMemory(
            long=[item.as_episodic_memory_block() for item in self.long_term_scene_memory],
            short=[item.as_episodic_memory_block() for item in self.short_term_scene_memory],
        )


class CityInfo(BaseModel):
    """城市信息"""
    name: str = Field(default="", title="城市名称", description="城市名称")
    id: str = Field(default="", title="城市ID", description="城市ID")
    lat: str = Field(default="", title="纬度", description="纬度")
    lon: str = Field(default="", title="经度", description="经度")
    adm2: str = Field(default="", title="二级行政区", description="二级行政区")
    adm1: str = Field(default="", title="一级行政区", description="一级行政区")
    country: str = Field(default="", title="国家", description="国家")
    tz: str = Field(default="", title="时区", description="时区")
    type: str = Field(default="", title="类型", description="类型")


class CurrentWeatherForecast(BaseModel):
    """当前天气预报"""
    obs_time: str = Field(default="", title="观测时间", description="观测时间")
    temp: str = Field(default="", title="温度", description="温度")
    feels_like: str = Field(default="", title="体感温度", description="体感温度")
    text: str = Field(default="", title="天气现象", description="天气现象")
    wind_dir: str = Field(default="", title="风向", description="风向")
    wind_scale: str = Field(default="", title="风力等级", description="风力等级")
    wind_speed: str = Field(default="", title="风速", description="风速")
    humidity: str = Field(default="", title="相对湿度", description="相对湿度")
    precip: str = Field(default="", title="降水量", description="降水量")
    cloud: str = Field(default="", title="云量", description="云量")
    pressure: str = Field(default="", title="大气压强", description="大气压强")
    vis: str = Field(default="", title="能见度", description="能见度")


class WeatherInfo(BaseModel):
    """天气信息"""
    city_info: CityInfo = Field(default_factory=CityInfo, title="城市信息", description="城市信息")
    current_weather_forecast: CurrentWeatherForecast = Field(default_factory=CurrentWeatherForecast, title="当前天气预报", description="当前天气预报")
    hourly_weather_forecast: Any = Field(default=None, title="每小时天气预报", description="每小时天气预报")
    daily_weather_forecast: Any = Field(default=None, title="每日天气预报", description="每日天气预报")


class DateInfo(BaseModel):
    """日期信息"""
    date: str = Field(default="", title="日期", description="日期")
    lunar_date: str = Field(default="", title="农历日期", description="农历日期")
    lunar_holiday: list[str] = Field(default_factory=list, title="农历节日", description="农历节日")
    solar_holiday: list[str] = Field(default_factory=list, title="公历节日", description="公历节日")
    solar_terms: str = Field(default="", title="节气", description="节气")


class Weather(BaseModel):
    """天气"""
    weather_info: WeatherInfo = Field(default_factory=WeatherInfo, title="天气信息", description="天气信息")
    date_info: DateInfo = Field(default_factory=DateInfo, title="日期信息", description="日期信息")

    def as_world_info(self) -> wi.WorldInfo:
        """转换为世界信息"""
        return wi.WorldInfo(
            city= wi.CityInfo(**self.weather_info.city_info.model_dump()),
            weather=wi.WeatherForecast(**self.weather_info.current_weather_forecast.model_dump()),
            date=wi.DateInfo(**self.date_info.model_dump()),
        )


class CostDuration(BaseModel):
    """耗时统计"""
    basic_info_with_struct: dict[str, Any] = Field(default_factory=dict, title="基本信息结构化", description="基本信息结构化")
    long_memory_with_struct: dict[str, Any] = Field(default_factory=dict, title="长记忆结构化", description="长记忆结构化")
    long_scene_memory_with_struct: dict[str, Any] = Field(default_factory=dict, title="长期场景记忆结构化", description="长期场景记忆结构化")
    scene_description_with_struct: dict[str, Any] = Field(default_factory=dict, title="场景描述结构化", description="场景描述结构化")
    short_memory_with_struct: dict[str, Any] = Field(default_factory=dict, title="短期记忆结构化", description="短期记忆结构化")
    vehicle_resource_with_struct: dict[str, Any] = Field(default_factory=dict, title="车辆资源结构化", description="车辆资源结构化")


class TokenInfo(BaseModel):
    """Token信息"""
    prompt_tokens: int = Field(default=0, title="提示词Token数", description="提示词Token数")
    completion_tokens: int = Field(default=0, title="完成Token数", description="完成Token数")
    total_tokens: int = Field(default=0, title="总Token数", description="总Token数")


class DebugInfo(BaseModel):
    """调试信息"""
    cost_duration: CostDuration = Field(default_factory=CostDuration, title="耗时统计", description="耗时统计")
    log_id: str = Field(default="", title="日志ID", description="日志ID")
    token_info: TokenInfo = Field(default_factory=TokenInfo, title="Token信息", description="Token信息")


class StRetrieval(BaseModel):
    """结构化检索"""
    vehicle_resource: VehicleResource = Field(default_factory=VehicleResource, title="车辆资源", description="车辆资源")
    scene_description: SceneDescription = Field(default_factory=SceneDescription, title="场景描述", description="场景描述")
    weather: Weather = Field(default_factory=Weather, title="天气", description="天气")
    memory: Memory = Field(default_factory=Memory, title="记忆", description="记忆")
    debug_info: DebugInfo = Field(default_factory=DebugInfo, title="调试信息", description="调试信息")


class ContextRaw(BaseModel):
    """原始上下文"""

    retrieval: Retrieval = Field(default_factory=Retrieval, title="检索上下文", description="检索上下文")
    structured_retrieval: StRetrieval = Field(default_factory=StRetrieval, title="结构化检索", description="结构化检索")

from pathlib import Path
import json


def test_copntext_raw():
    path = Path(".") / "projects" / "mind" / "advisor" / "domain_data"

    old_format = False

    if old_format:
        json_file = path / "字节的context结构化返回样例1.json"
        data = json.loads((open(json_file, "r", encoding="utf-8").read()))
        context = ContextRaw.model_validate(data["data"])
    else:
        json_file = path / "1769066167903-context.json"
        data = json.loads((open(json_file, "r", encoding="utf-8").read()))
        context = ContextRaw.model_validate(data["json_data"]["data"])


    vehicle_state = context.structured_retrieval.vehicle_resource.as_state()
    print(f"state:")
    print(vehicle_state)

    return

    visual_interior = context.structured_retrieval.scene_description.as_visual_interior()
    print(f"visual_interior:")
    print(visual_interior)

    world_info = context.structured_retrieval.weather.as_world_info()
    print(f"world_info:")
    print(world_info)

    memory_info = context.structured_retrieval.memory.as_episodic_memory()
    print(f"memory_info:")
    print(memory_info)


if __name__ == "__main__":
    test_copntext_raw()