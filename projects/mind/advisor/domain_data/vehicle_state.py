from typing import Any

from pydantic import BaseModel, Field

class VehicleStateSimple(BaseModel):
    """车辆状态"""

    # 基础硬件
    light: dict[str, str] | str | None = Field(default=None, title="车灯状态", description="车灯状态")
    door: dict[str, str] | str | None = Field(default=None, title="门状态", description="门状态")
    window: dict[str, str] | str | None = Field(default=None, title="车窗状态", description="车窗状态")
    tire: dict[str, str] | str | None = Field(default=None, title="轮胎状态", description="轮胎状态")
    seat: dict[str, str] | str | None = Field(default=None, title="座椅状态", description="座椅状态")
    seat_belt: dict[str, str] | str | None = Field(default=None, title="安全带状态", description="安全带状态")
    rearview_mirror: dict[str, str] | str | None = Field(default=None, title="后视图镜状态", description="后视图镜状态")
    wiper: dict[str, str] | str | None = Field(default=None, title="ipers状态", description="ipers状态")
    defogger: dict[str, str] | str | None = Field(default=None, title="雾灯状态", description="雾灯状态")
    air_condition: dict[str, str] | str | None = Field(default=None, title="空调状态", description="空调状态")

    # 驾驶相关
    battery: dict[str, str] | str | None = Field(default=None, title="电池状态", description="电池状态")
    driving_assist: dict[str, str] | str | None = Field(default=None, title="驾驶辅助状态", description="驾驶辅助状态")
    navigation: dict[str, str] | str | None = Field(default=None, title="导航状态", description="导航状态")
    
    # 其它
    audio: dict[str, str] | str | None = Field(default=None, title="音频状态", description="音频状态")
    seat_occupancy: dict[str, str] | str | None = Field(default=None, title="座椅占用状态", description="座椅占用状态")
    
    
    other_state: dict[str, str] | None = Field(default=None, title="其它状态", description="其它状态")
    '''上面未定义的属性，在这里动态添加'''


class ADSDState(BaseModel):
    adaptive_cruise: dict[str, str] | str | None = Field(default=None, title="自适应巡航", description="该状态为自适应巡航功能属于辅助驾驶功能状态。其可在行车中辅助加减速，可自主设定巡航时速与跟车时距，自动切换模式，无车按设定速行驶，有车保持安全距，前车停启可跟随，弯道能控速")
    full_speed_driving_assist: dict[str, str] | str | None = Field(default=None, title="全速驾驶辅助", description="该状态为全速驾驶辅助，选择后可对 NOA、变道确认、信任增强、起步提醒、语音播报进行设置。用户询问智能/自动/辅助驾驶功能使用方法时参考此状态")
    pilot_assist: dict[str, str] | str | None = Field(default=None, title="领航辅助", description="该状态为领航辅助，导航开启时激活可实现自动汇入、变道、下匝道等高阶智能辅助驾驶功能，用户询问封闭道路NOA相关问题时参考")
    lane_change_confirm: dict[str, str] | str | None = Field(default=None, title="变道确认开关", description="该状态为变道确认开关，仅高速领航辅助（NOA）可设置。NOA运行时车辆变道，仪表屏会出现变道提示")
    trust_enhance: dict[str, str] | str | None = Field(default=None, title="信任增强开关", description="该状态为信任增强开关，开启后特定场景中，仪表车模上方会显示智驾置信度等级图标")
    open_road_noa: dict[str, str] | str | None = Field(default=None, title="开放道路NOA", description="该状态为开放道路NOA（城市领航辅助 UNP）开关，导航开启激活后实现自动汇入、变道等功能。开启时驾驶员要握方向盘、关注路况并在特殊情况及时接管")
    pilot_full_speed: dict[str, str] | str | None = Field(default=None, title="Pilot全速驾驶辅助", description="该状态为 Pilot 全速驾驶辅助，开启后可对 NOA、变道确认、信任增强、起步提醒、语音播报提示进行设置")
    calc_lane_change: dict[str, str] | str | None = Field(default=None, title="指令自动变道CALC", description="该状态为指令自动变道CALC（打灯变道），智能巡航时拨转向灯发指令，系统判环境满足条件则换道，完成后转车道保持")
    driving_style: dict[str, str] | str | None = Field(default=None, title="智驾风格选项", description="该状态为智驾风格选项，Pilot 开启时，智驾风格影响变道敏捷度与弯道减速程度，用户描述自动驾驶风格相关问题可参考此信号")
    start_reminder: dict[str, str] | str | None = Field(default=None, title="起步提醒选项开关", description="该状态为起步提醒选项开关，开启后，跟车停车前车起步或在路口最前方遇信号灯变红转绿，车辆会以声音和仪表提示起步")
    speed_limit_range: dict[str, str] | str | None = Field(default=None, title="限速调整区间", description="该状态为限速调整区间，可自定义调节车辆特定场景最大速度（上限 120km/h），用户反馈自动驾驶速度问题时可参考")
    speed_limit_fixed: dict[str, str] | str | None = Field(default=None, title="限速调整固定速度", description="该状态为限速调整固定速度，选固定值时，最大速度为当前道路限速加固定值，用户反馈自动驾驶速度问题时可参考")
    speed_limit_percent: dict[str, str] | str | None = Field(default=None, title="限速百分比调整", description="该状态是限速百分比调整，可参考它反馈车速问题")
    speed_limit_alarm: dict[str, str] | str | None = Field(default=None, title="限速报警", description="用户可以通过限速报警设置项开启或关闭限速报警")
    forward_collision_warning: dict[str, str] | str | None = Field(default=None, title="前向碰撞预警", description="用户可以通过前向碰撞预警设置开启/关闭前向碰撞预警")
    fcw_sensitivity: dict[str, str] | str | None = Field(default=None, title="前向碰撞预警灵敏度", description="用于设置前向碰撞预警的灵敏度，可设置低/中/高")
    aeb: dict[str, str] | str | None = Field(default=None, title="自动紧急制动", description="摄像头和雷达系统实时监测前车，判断与本车的距离、方位和相对速度，检测到即将碰撞（含行人）时自动刹车。")
    rear_collision_warning: dict[str, str] | str | None = Field(default=None, title="后向碰撞预警", description="后向碰撞预警属于主动安全功能，包括盲点预警、侧后方来车辅助、后侧方来车制动、开门预警等功能")
    blind_spot_warning: dict[str, str] | str | None = Field(default=None, title="盲点预警", description="在行车时警告驾驶员侧后方盲区有车辆接近本车，提醒驾驶员注意避免发生碰撞风险。")
    rear_cross_traffic: dict[str, str] | str | None = Field(default=None, title="后侧方来车预警", description="后侧方来车预警属主动安全功能，无需手动激活。相关设置开启后，倒车时监测侧后方风险目标，有碰撞风险则视觉和声音提醒。制动开启时自动刹停。")
    door_open_warning: dict[str, str] | str | None = Field(default=None, title="开门预警", description="对车辆内的乘员开门时进行提醒，避免开门时与附近的车辆，行人等发生碰撞。")
    lane_departure_assist: dict[str, str] | str | None = Field(default=None, title="车道偏离辅助", description="车速＞60km/h且前方车道线清晰，车辆偏道时仪表声光报警，系统控方向盘使车回车道，咨询车道相关功能问题可参考此信号")
    lda_sensitivity: dict[str, str] | str | None = Field(default=None, title="车道偏离辅助预警灵敏度", description="用于设置车道偏离辅助预警的灵敏度，可设置低/中/高")
    ldw_alert_mode: dict[str, str] | str | None = Field(default=None, title="车道偏离预警警示方式", description="车道偏离预警的警示方式包括声音、振动、声音+振动")
    lane_keep: dict[str, str] | str | None = Field(default=None, title="车道保持辅助", description="当车辆无意识偏离车道，且检测到相邻车道有对向来车、后向超车或旁侧有道路边缘时，系统会横向干预方向盘降低碰撞风险。")


class MediaState(BaseModel):
    """媒体资源项"""
    audio_signal: dict[str, str] | str | None = Field(default=None, title="音频信号", description="该信号为当前播放音频信号，可显示正在播放音频的类型、名称、作者、播放应用名称和所属专辑名称。")
    video_signal: dict[str, str] | str | None = Field(default=None, title="视频信号", description="该信号为当前播放视频信号，体现正在播放视频的名称、类型、标签、演员名字、导演名字、媒体源名、集数和季数。")


class NavigationState(BaseModel):
    """导航状态"""
    navigation_status: dict[str, str] | str | None = Field(default=None, title="导航状态", description="导航状态")
    destination: dict[str, str] | str | None = Field(default=None, title="目的地", description="目的地")
    destination_type: dict[str, str] | str | None = Field(default=None, title="目的地类型", description="目的地类型")
    destination_info: dict[str, str] | str | None = Field(default=None, title="目的地信息", description="该信号为车辆导航目的地信息信号，包含目的地具体地址、当前位置到POI的剩余距离、剩余时长、到达POI时的剩余电量以及到达POI的具体时间。")
    road_condition: dict[str, str] | str | None = Field(default=None, title="路况", description="路况")
    heavy_traffic: dict[str, str] | str | None = Field(default=None, title="严重拥堵", description="严重拥堵")
    waypoint: dict[str, str] | str | None = Field(default=None, title="途径点", description="该信号为车辆导航途径点信号，包含途径点具体地址、当前位置到POI的剩余距离、剩余时长、到达POI时的剩余电量以及到达POI的具体时间。")
    service_area: dict[str, str] | str | None = Field(default=None, title="服务区", description="该信号为车辆导航沿途服务区位置信息信号，涵盖服务区具体地址、沿途顺序、当前位置距服务区的剩余距离、到达服务区时的剩余电量以及到达服务区的具体时间。")


class SignalLightState(BaseModel):
    """信号灯状态"""
    low_beam: dict[str, str] | str | None = Field(default=None, title="近光灯", description="该灯为近光灯指示灯，其亮了表示车辆的近光灯已经开启。近光灯用于夜间或视线不佳的条件时提供足够的照明距离和清晰度")
    high_beam: dict[str, str] | str | None = Field(default=None, title="远光灯", description="该灯为远光灯指示灯，其亮了表示车辆的远光灯已经开启。远光灯用于提供比近光灯更远的照明效果")
    high_beam_switch: dict[str, str] | str | None = Field(default=None, title="远光灯开关", description="远光灯开关")
    rear_fog_light: dict[str, str] | str | None = Field(default=None, title="后雾灯", description="该灯为后雾灯指示灯，其亮了表示车辆的后雾灯已经开启。用于低能见度环境（雾、雪、雨、灰尘等），提醒后方车辆本车位置，降低追尾风险")
    position_light: dict[str, str] | str | None = Field(default=None, title="位置灯", description="该灯为位置灯指示灯，其亮了表示车辆的位置灯已开启。位置灯用于在光线不佳时显示车辆的外部轮廓，保障行车安全")
    left_turn_signal: dict[str, str] | str | None = Field(default=None, title="左转向灯", description="该灯为左转向灯指示灯，其亮时表示车辆左转向灯开启并闪烁。若同时开启危险警告灯，左右转向灯会同时闪烁，关闭转向灯后指示灯应熄灭")
    right_turn_signal: dict[str, str] | str | None = Field(default=None, title="右转向灯", description="该灯为右转向灯指示灯，亮起表示右转向灯开启并闪烁。若同时开启危险警告灯，左右转向灯同时闪烁，关闭转向灯后指示灯熄灭。")
    intelligent_headlight: dict[str, str] | str | None = Field(default=None, title="智能大灯", description="该灯为智能大灯控制系统开启提示灯，亮灯表示智能远光灯辅助系统检测到前方无对向或同向车辆、环境和交通状况合适时，自动点亮远光灯，用于夜间照明和改善视野。可通过操作方向盘左侧组合开关手动控制远光灯开关")
    afs_fault: dict[str, str] | str | None = Field(default=None, title="AFS故障", description="该灯为AFS灯光故障指示灯，其亮起表示车辆前照灯系统出现故障，会影响照明与行车安全")
    abs_fault: dict[str, str] | str | None = Field(default=None, title="ABS故障", description="该灯为ABS故障指示灯，其亮起表示车辆防抱死制动系统存在故障，需尽快联系销售服务商检修")
    brake_fault: dict[str, str] | str | None = Field(default=None, title="制动故障", description="该灯为制动灯故障指示灯，其亮起表示制动液液位过低或制动系统存在故障，需尽快联系销售服务商检修")
    esp_fault: dict[str, str] | str | None = Field(default=None, title="ESP故障", description="该灯为 ESP/SCS 灯故障提示灯，其常亮表示车身稳定系统处于屏蔽状态，可能因系统故障或被手动关闭")
    esp_working: dict[str, str] | str | None = Field(default=None, title="ESP工作状态", description="该灯为 ESP/SCSP 工作状态指示灯，其关闭，意味着系统正常且处于开启状态；其闪烁，意味着车辆可能处于湿滑路面或急转弯状态，系统正在主动干预，保持平稳驾驶，无需手动操作")
    tcs_fault: dict[str, str] | str | None = Field(default=None, title="TCS故障", description="该灯为 TCS 灯故障提示灯，其闪烁表示车辆牵引力控制系统正在工作；常亮表示车身稳定系统存在故障，需尽快联系销售服务商检修")
    autohold_active: dict[str, str] | str | None = Field(default=None, title="自动驻车激活", description="该灯亮起代表自动驻车已激活，停车自动锁止，无需手动。若灯闪烁或常亮，系统可能故障，需送修。")
    autohold_ready: dict[str, str] | str | None = Field(default=None, title="自动驻车待命", description="该灯亮起表示自动驻车功能待命，可正常使用，停车需手动触发。若灯不亮或闪烁，系统可能故障，需送修。")
    autohold_fault: dict[str, str] | str | None = Field(default=None, title="Autohold故障", description="该灯为Autohold故障灯，亮起代表自动驻车系统故障，需尽快送修")
    four_wheel_drive: dict[str, str] | str | None = Field(default=None, title="四驱系统", description="该灯为四驱系统状态指示灯，包含 2 种状态：激活：四驱系统开启并正常工作，指示灯为绿色常亮，可借此判断当前驾驶模式；故障：四驱系统出现异常，指示灯为黄色常亮，需及时检修。")
    tire_pressure_warning: dict[str, str] | str | None = Field(default=None, title="胎压异常", description="该灯为胎压异常提示灯，亮起代表胎压故障，需检查并尽快联系服务商检修")
    tire_pressure_fault: dict[str, str] | str | None = Field(default=None, title="胎压系统故障", description="该灯为胎压系统故障灯，其亮起表示车辆胎压存在故障。此时需检查胎压是否异常，若异常应尽快联系销售服务商检修。")
    charging_fault: dict[str, str] | str | None = Field(default=None, title="充电系统故障", description="该灯为充电系统故障灯，启动时亮几秒后熄灭，说明蓄电池系统正常；若常亮，代表充电异常或低压供电系统故障，应停车并尽快联系检修。")
    auxiliary_power_fault: dict[str, str] | str | None = Field(default=None, title="辅助系统供电故障", description="此灯为辅助系统供电故障指示灯，常亮意味着充电或低压供电故障，需停车并速连售后。")
    airbag_fault: dict[str, str] | str | None = Field(default=None, title="安全气囊故障", description="该灯为安全气囊故障灯，亮起表示安全气囊有故障，需尽快检修")
    airbag_uncalibrated: dict[str, str] | str | None = Field(default=None, title="安全气囊未标定", description="该灯为安全气囊未标定指示灯，灯亮表示安全气囊有故障，需尽快检修。")
    front_seatbelt_warning: dict[str, str] | str | None = Field(default=None, title="第一排安全带未系提醒", description="该灯为第一排安全带未系提醒指示灯，车辆上电后，若前排安全带未系或未系到位，灯亮以提醒系好安全带保障安全。若灯误亮，可调整座椅、乘客姿势或移开重物")
    rear_seatbelt_warning: dict[str, str] | str | None = Field(default=None, title="第二排安全带未系提示", description="该灯为第二排安全带未系提示灯，车辆上电后，若后排安全带未系或未系到位，灯亮提醒系安全带，增加意外时的保护。若无人但灯亮，可能是重量传感器误判或系统故障，可调整座椅位置或重量分布，无法解决则送修。")
    pedestrian_protection_warning: dict[str, str] | str | None = Field(default=None, title="行人保护提醒", description="该灯为行人保护提醒报警灯，灯亮或因传感器故障、缺维护、油品等问题，需检修")
    steering_fault: dict[str, str] | str | None = Field(default=None, title="转向故障", description="该灯是转向故障指示灯，亮灯代表电动助力转向系统故障，需检修")
    steering_angle_fault: dict[str, str] | str | None = Field(default=None, title="方向盘角度故障", description="该灯为方向盘角度故障提示灯，灯亮代表电动助力转向系统故障，需检修")
    escl_fault: dict[str, str] | str | None = Field(default=None, title="ESCL故障", description="该灯为 ESCL 故障提示灯，也叫电动助力转向系统故障指示灯。若显示黄色为一般故障，可能出现解锁困难；若显示红色为严重故障，可能导致方向盘锁死或车辆无法启动")
    steering_reduced: dict[str, str] | str | None = Field(default=None, title="转向降低", description="该灯为转向降低提示灯，也是电动助力转向系统故障指示灯。若显示黄色表示转向助力部分降低，操控难度增加；若显示红色表示转向助力大幅降低甚至完全消失，转向极度沉重")
    epb_indicator: dict[str, str] | str | None = Field(default=None, title="EPB指示", description="该灯为EPB指示提示灯，灯亮表示电子驻车制动系统已将车辆锁定在停车位置，无需手动拉手刹。行车时可通过操作电子驻车开关或踩油门踏板解除。若灯闪烁或长亮不灭，可能系统故障，需送修。")
    epb_not_released: dict[str, str] | str | None = Field(default=None, title="EPB未释放", description="该灯为EPB未释放提示灯，灯亮意味着电子驻车制动系统未释放，车辆处于驻车锁定状态，无需手动拉手刹以确保停车安全。行车需解除时，可操作电子驻车开关或踩油门踏板，具体可参考车辆手册或咨询维修人员。若灯闪烁或长亮，可能系统故障，需送修。")
    epb_fault: dict[str, str] | str | None = Field(default=None, title="EPB故障", description="该灯为 EPB 故障提示灯，灯亮表明电子驻车故障，坡道有溜车风险。应停至安全处并联系服务商检修")
    key_warning: dict[str, str] | str | None = Field(default=None, title="钥匙不在车内/防盗", description="该灯为钥匙不在车内/防盗指示灯，灯亮或因防盗系统激活/故障，先确认钥匙在车内且车门关闭，若灯仍亮需送修。")
    power_battery_fault: dict[str, str] | str | None = Field(default=None, title="动力电池故障", description="该灯为动力电池故障指示灯，灯亮代表有严重故障，勿自行处理、勿驾车，需尽快检修。")
    power_battery_level: dict[str, str] | str | None = Field(default=None, title="动力电池电量", description="该灯为动力电池电量灯，灯亮表示当前电量正")
    power_battery_low: dict[str, str] | str | None = Field(default=None, title="动力电池电量低", description="该灯为动力电池电量低提示灯，亮起表示电量低，需尽快充电")
    charge_gun_connected: dict[str, str] | str | None = Field(default=None, title="充放电枪连接", description="该灯为充放电枪连接灯，亮起表示充/放电枪已连接")
    charging: dict[str, str] | str | None = Field(default=None, title="充电中", description="该灯为充电灯，也叫充电中状态指示灯，亮起表示车辆正在充电")
    charge_discharge_fault: dict[str, str] | str | None = Field(default=None, title="充放电故障", description="该灯为充放电故障灯，亮起意味着车辆充放电功能有故障，需检修")
    discharging: dict[str, str] | str | None = Field(default=None, title="放电中", description="该灯为放电灯，也叫充电中状态指示灯，亮起表示车辆正在放电。")
    gear_invalid: dict[str, str] | str | None = Field(default=None, title="挡位信号无效", description="该灯为挡位信号无效提示灯，亮起意味着挡位信号无效，需重新挂档，若灯仍亮则需检修")
    system_ready: dict[str, str] | str | None = Field(default=None, title="系统就绪", description="该灯为系统就绪灯，亮起表示车辆完成自检，电池、驱动、充电等关键系统就绪，可安全行驶")
    system_fault: dict[str, str] | str | None = Field(default=None, title="系统故障", description="该灯为系统故障灯，亮起表示动力系统有故障，需尽快检修")
    power_limited: dict[str, str] | str | None = Field(default=None, title="功率受限", description="该灯为功率受限灯，亮起表示车辆功率与加速性能受限，可能因动力系统或电路故障，需检修")
    motor_fault: dict[str, str] | str | None = Field(default=None, title="电机故障", description="该灯为电机故障灯，也叫驱动系统故障指示灯，亮起表示车辆驱动系统可能有故障，应尽快检修。前往维修前勿驾车")
    air_suspension_fault: dict[str, str] | str | None = Field(default=None, title="空气悬架故障", description="该灯为空气悬架指示灯，灯亮意味着悬架系统故障，需检修。")
    ecall_status: dict[str, str] | str | None = Field(default=None, title="Ecall状态", description="该灯为 Ecall 状态灯，亮灯表明车内 eCall 系统激活。可停车重启，若 SOS 提示仍在，需检修")
    rear_wheel_steering_fault: dict[str, str] | str | None = Field(default=None, title="后轮转向故障", description="该灯为后轮转向故障灯，亮灯表明后轮转向系统故障，影响操作安全，勿继续驾驶，需检修")
    hazard_warning: dict[str, str] | str | None = Field(default=None, title="危险报警灯", description="该灯为危险报警灯（俗称双闪），用于紧急、临时停车，开启时类似左右转弯灯同时闪烁")
    ambient_light: dict[str, str] | str | None = Field(default=None, title="氛围灯", description="该灯为氛围灯，用户反馈车内氛围不强或单调时可参考此灯状态")
    reading_light: dict[str, str] | str | None = Field(default=None, title="阅读灯", description="该灯为阅读灯。可调节车内光线强弱，用户提及睡觉休息、光线刺眼或太弱时参考此状态，化妆灯相关信息无需参考")


class SystemControlState(BaseModel):
    """系统控制状态"""
    maintenance_info: dict[str, str] | str | None = Field(default=None, title="保养信息", description="该信号为剩余保养时间和里程信号，可显示距离下次维保的剩余天数、剩余里程以及下次维保的日期。")
    display_mode: dict[str, str] | str | None = Field(default=None, title="显示模式", description="显示模式")
    passenger_info: list[dict[str, str]] | str | None = Field(default=None, title="乘客信息", description="该信号为乘客身份信息，含该位置乘客的身份名称")


class VehicleControlState(BaseModel):
    """车辆控制状态"""
    driving_mode: dict[str, str] | str | None = Field(default=None, title="驾驶模式", description="该场景信号指车辆行进情况，含模式（经济、运动等）、档位（P、D 等）和实时车速。应用场景：车控自动调动力输出与换挡逻辑；主动安全结合信息预警风险；供用户查询行进状态信息")
    vehicle_speed: dict[str, str] | str | None = Field(default=None, title="车速", description="车速")
    energy_recovery: dict[str, str] | str | None = Field(default=None, title="能量回收", description="能量回收")
    gear: dict[str, str] | str | None = Field(default=None, title="档位", description="档位")
    regenerative_braking: dict[str, str] | str | None = Field(default=None, title="再生制动", description="再生制动")
    tire_info: list[dict[str, str]] | str | None = Field(default=None, title="轮胎信息", description="该信号反映四轮实时胎压、胎温")
    charging_port: dict[str, str] | str | None = Field(default=None, title="充电盖", description="该信号表示车辆充电盖的开启或关闭状态")
    charging_status: dict[str, str] | str | None = Field(default=None, title="充电状态", description="该场景信号指车辆充电状况，含充电状态（如充电中、未充电）、类型（快充、慢充）、剩余时长。")
    charging_limit: dict[str, str] | str | None = Field(default=None, title="充电限制", description="该场景信号指设置的充电上限和可充最大电量")
    battery_info: dict[str, str] | str | None = Field(default=None, title="电池信息", description="该信号描述车辆电池状况，含剩余电量和剩余续航里程")
    air_condition: list[dict[str, str]] | str | None = Field(default=None, title="空调状态", description="该信号为车内空调状态信号，可显示空调开关状态、操作所在座位、温度、运行模式，以及自动和手动空调风量档位状态")
    air_direction: dict[str, str] | str | None = Field(default=None, title="空调风向", description="该信号为空调风向模式信号，含空调吹风方向和模式")
    air_circulation: dict[str, str] | str | None = Field(default=None, title="空调循环模式", description="该信号为空调循环模式信号，涵盖内循环、外循环和自动循环三种模式。")
    air_cooling: dict[str, str] | str | None = Field(default=None, title="空调制冷", description="空调制冷开关直接影响车内制冷能力，因此影响车内温度。用户表达自身冷热感受相关的说法，应当参考此状态。")
    defrost_defog: list[dict[str, str]] | str | None = Field(default=None, title="除霜除雾", description="除霜除雾开关可以影响车辆视野。用户表达玻璃上起雾、起霜、看不清前车/后车等相关说法时，应当参考此状态。")
    air_purification: dict[str, str] | str | None = Field(default=None, title="空气净化", description="当用户表达车里空气不好（如太臭、难闻、异味等）的意思时，应当参考此状态。用户表达晕车相关说法时，应当参考此状态。")
    fan_speed_front: dict[str, str] | str | None = Field(default=None, title="前排风量", description="前排风量")
    fan_speed_rear: dict[str, str] | str | None = Field(default=None, title="后排风量", description="后排风量")
    interior_temperature: list[dict[str, str]] | str | None = Field(default=None, title="车内外温度", description="车内外温度")
    seat_position: list[dict[str, str]] | str | None = Field(default=None, title="座椅位置", description="该信号为车辆座椅位置状态信号，体现当前指代座位及其水平、靠背、高度位置。")
    seat_ventilation: list[dict[str, str]] | str | None = Field(default=None, title="座椅通风", description="座椅通风开关状态会影响车内温度和用户冷热感受，尤其是用户背部冷热感受。用户表示下面有点闷、屁股闷、背上闷、热、冷、背上出汗、身上出汗、通风凉等相关说法时，应当参考此信号")
    seat_heating: list[dict[str, str]] | str | None = Field(default=None, title="座椅加热", description="座椅加热状态会影响车内温度和用户冷热感受，尤其是用户背部冷热感受。用户表示后背太闷、背上出汗、冷、热等相关说法时，应当参考此信号")
    seat_massage: list[dict[str, str]] | str | None = Field(default=None, title="座椅按摩", description="该信号为车辆座椅按摩功能设置信号，可显示按摩档位状态、操作所在座位及功能模式。")
    seat_belt_status: dict[str, str] | str | None = Field(default=None, title="安全带状态", description="安全带状态")
    window_status: list[dict[str, str]] | str | None = Field(default=None, title="车窗状态", description="车窗的开关可以影响车里的温度、光线、声音等多种环境因素。用户表达想要休息、睡觉、小憩等需求时，或是表达车里空气不好（如太臭、难闻、异味等）的意思时，或是表达风太大了、风吹得太厉害了、头/脸热/凉、外面吵、车里味道大、听不清声音、车里冷、车里热、外面太亮/暗等意思时，应当参考此状态。用户表达太阳太晒、雨水进车了等说法时，应当参考此状态。")
    door_status: list[dict[str, str]] | str | None = Field(default=None, title="车门状态", description="该信号为车辆车门状态信号，可显示车门的开启状态、开启程度以及指代车门的位置。")
    sunshade_left_rear: dict[str, str] | str | None = Field(default=None, title="左后遮阳帘", description="左后遮阳帘")
    sunshade_right_rear: dict[str, str] | str | None = Field(default=None, title="右后遮阳帘", description="右后遮阳帘")
    rearview_mirror: dict[str, str] | str | None = Field(default=None, title="后视镜状态", description="后视镜状态可以影响车后的视野情况。")
    wiper_status: dict[str, str] | str | None = Field(default=None, title="雨刮状态", description="用户表达下雨导致视线受阻、雨水飘进车里等相关说法时，应当参考此状态。")
    steering_wheel_heating: dict[str, str] | str | None = Field(default=None, title="方向盘加热", description="方向盘加热可以使得驾驶员在驾驶时手部温度升高。用户表达手冷/冰、手热/烫等说法时，应当参考此状态。仅限于手冷/热，若用户表达脚冷/热或腿冷/热等说法时，与此状态无关，不可输出此状态。")
    fragrance_system: list[dict[str, str]] | str | None = Field(default=None, title="香氛系统", description="当用户表达车里空气不好（如太臭、难闻、异味等）的意思时，应当参考此状态。")
    volume_status: dict[str, str] | str | None = Field(default=None, title="音量状态", description="用户表达想要休息、睡觉、小憩等需求时，应当参考此状态。用户表达听不清语音、声音太吵等说法时，应当参考此状态。")
    sunroof_status: dict[str, str] | str | None = Field(default=None, title="天窗状态", description="天窗状态")
    tailgate_status: dict[str, str] | str | None = Field(default=None, title="尾门状态", description="尾门状态")
    radar_status: dict[str, str] | str | None = Field(default=None, title="雷达状态", description="雷达状态")
    panoramic_camera: dict[str, str] | str | None = Field(default=None, title="360全景影像", description="360全景影像")
    calendar_time: dict[str, str] | str | None = Field(default=None, title="日历时间", description="日历时间")
    auto_parking: dict[str, str] | str | None = Field(default=None, title="自动泊车", description="自动泊车")


class VehicleState(BaseModel):
    adsd: ADSDState | str | None = Field(default=None, title="ADSD状态", description="ADSD状态")
    media: MediaState | str | None = Field(default=None, title="媒体状态", description="媒体状态")
    navigation: NavigationState | str | None = Field(default=None, title="导航状态", description="导航状态")
    signal_light: SignalLightState | str | None = Field(default=None, title="信号灯状态", description="信号灯状态")
    system_control: SystemControlState | str | None = Field(default=None, title="系统控制状态", description="系统控制状态")
    vehicle_control: VehicleControlState | str | None = Field(default=None, title="车辆控制状态", description="车辆控制状态")

    more_states: dict[str, Any] | None = Field(default=None, title="其它状态", description="其它状态")
