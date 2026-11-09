interface DomainCommon extends Common {
  brief?: string // 简单总结
}

// ==================== User ====================
interface PersonBasicInfo {
  name?: string // 名字
  age?: number | string // 年龄
  gender?: string // 性别
}

interface UserEntity {
  basic_info?: PersonBasicInfo // 个人基本信息
  profile?: string[] // 用户偏好
  attributes?: Record<string, string> // 用户属性（动态属性）
}

interface User extends DomainCommon {
  entity?: UserEntity
}

// ==================== Vehicle State ====================
interface ADSDState {
  adaptive_cruise?: Record<string, string> | string // 自适应巡航
  full_speed_driving_assist?: Record<string, string> | string // 全速驾驶辅助
  pilot_assist?: Record<string, string> | string // 领航辅助
  lane_change_confirm?: Record<string, string> | string // 变道确认开关
  trust_enhance?: Record<string, string> | string // 信任增强开关
  open_road_noa?: Record<string, string> | string // 开放道路NOA
  pilot_full_speed?: Record<string, string> | string // Pilot全速驾驶辅助
  calc_lane_change?: Record<string, string> | string // 指令自动变道CALC
  driving_style?: Record<string, string> | string // 智驾风格选项
  start_reminder?: Record<string, string> | string // 起步提醒选项开关
  speed_limit_range?: Record<string, string> | string // 限速调整区间
  speed_limit_fixed?: Record<string, string> | string // 限速调整固定速度
  speed_limit_percent?: Record<string, string> | string // 限速百分比调整
  speed_limit_alarm?: Record<string, string> | string // 限速报警
  forward_collision_warning?: Record<string, string> | string // 前向碰撞预警
  fcw_sensitivity?: Record<string, string> | string // 前向碰撞预警灵敏度
  aeb?: Record<string, string> | string // 自动紧急制动
  rear_collision_warning?: Record<string, string> | string // 后向碰撞预警
  blind_spot_warning?: Record<string, string> | string // 盲点预警
  rear_cross_traffic?: Record<string, string> | string // 后侧方来车预警
  door_open_warning?: Record<string, string> | string // 开门预警
  lane_departure_assist?: Record<string, string> | string // 车道偏离辅助
  lda_sensitivity?: Record<string, string> | string // 车道偏离辅助预警灵敏度
  ldw_alert_mode?: Record<string, string> | string // 车道偏离预警警示方式
  lane_keep?: Record<string, string> | string // 车道保持辅助
}

interface MediaState {
  audio_signal?: Record<string, string> | string // 音频信号
  video_signal?: Record<string, string> | string // 视频信号
}

interface NavigationState {
  navigation_status?: Record<string, string> | string // 导航状态
  destination?: Record<string, string> | string // 目的地
  destination_type?: Record<string, string> | string // 目的地类型
  destination_info?: Record<string, string> | string // 目的地信息
  road_condition?: Record<string, string> | string // 路况
  heavy_traffic?: Record<string, string> | string // 严重拥堵
  waypoint?: Record<string, string> | string // 途径点
  service_area?: Record<string, string> | string // 服务区
}

interface SignalLightState {
  low_beam?: Record<string, string> | string // 近光灯
  high_beam?: Record<string, string> | string // 远光灯
  high_beam_switch?: Record<string, string> | string // 远光灯开关
  rear_fog_light?: Record<string, string> | string // 后雾灯
  position_light?: Record<string, string> | string // 位置灯
  left_turn_signal?: Record<string, string> | string // 左转向灯
  right_turn_signal?: Record<string, string> | string // 右转向灯
  intelligent_headlight?: Record<string, string> | string // 智能大灯
  afs_fault?: Record<string, string> | string // AFS故障
  abs_fault?: Record<string, string> | string // ABS故障
  brake_fault?: Record<string, string> | string // 制动故障
  esp_fault?: Record<string, string> | string // ESP故障
  esp_working?: Record<string, string> | string // ESP工作状态
  tcs_fault?: Record<string, string> | string // TCS故障
  autohold_active?: Record<string, string> | string // 自动驻车激活
  autohold_ready?: Record<string, string> | string // 自动驻车待命
  autohold_fault?: Record<string, string> | string // Autohold故障
  four_wheel_drive?: Record<string, string> | string // 四驱系统
  tire_pressure_warning?: Record<string, string> | string // 胎压异常
  tire_pressure_fault?: Record<string, string> | string // 胎压系统故障
  charging_fault?: Record<string, string> | string // 充电系统故障
  auxiliary_power_fault?: Record<string, string> | string // 辅助系统供电故障
  airbag_fault?: Record<string, string> | string // 安全气囊故障
  airbag_uncalibrated?: Record<string, string> | string // 安全气囊未标定
  front_seatbelt_warning?: Record<string, string> | string // 第一排安全带未系提醒
  rear_seatbelt_warning?: Record<string, string> | string // 第二排安全带未系提示
  pedestrian_protection_warning?: Record<string, string> | string // 行人保护提醒
  steering_fault?: Record<string, string> | string // 转向故障
  steering_angle_fault?: Record<string, string> | string // 方向盘角度故障
  escl_fault?: Record<string, string> | string // ESCL故障
  steering_reduced?: Record<string, string> | string // 转向降低
  epb_indicator?: Record<string, string> | string // EPB指示
  epb_not_released?: Record<string, string> | string // EPB未释放
  epb_fault?: Record<string, string> | string // EPB故障
  key_warning?: Record<string, string> | string // 钥匙不在车内/防盗
  power_battery_fault?: Record<string, string> | string // 动力电池故障
  power_battery_level?: Record<string, string> | string // 动力电池电量
  power_battery_low?: Record<string, string> | string // 动力电池电量低
  charge_gun_connected?: Record<string, string> | string // 充放电枪连接
  charging?: Record<string, string> | string // 充电中
  charge_discharge_fault?: Record<string, string> | string // 充放电故障
  discharging?: Record<string, string> | string // 放电中
  gear_invalid?: Record<string, string> | string // 挡位信号无效
  system_ready?: Record<string, string> | string // 系统就绪
  system_fault?: Record<string, string> | string // 系统故障
  power_limited?: Record<string, string> | string // 功率受限
  motor_fault?: Record<string, string> | string // 电机故障
  air_suspension_fault?: Record<string, string> | string // 空气悬架故障
  ecall_status?: Record<string, string> | string // Ecall状态
  rear_wheel_steering_fault?: Record<string, string> | string // 后轮转向故障
  hazard_warning?: Record<string, string> | string // 危险报警灯
  ambient_light?: Record<string, string> | string // 氛围灯
  reading_light?: Record<string, string> | string // 阅读灯
}

interface SystemControlState {
  maintenance_info?: Record<string, string> | string // 保养信息
  display_mode?: Record<string, string> | string // 显示模式
  passenger_info?: Record<string, string>[] | string // 乘客信息
}

interface VehicleControlState {
  driving_mode?: Record<string, string> | string // 驾驶模式
  vehicle_speed?: Record<string, string> | string // 车速
  energy_recovery?: Record<string, string> | string // 能量回收
  gear?: Record<string, string> | string // 档位
  regenerative_braking?: Record<string, string> | string // 再生制动
  tire_info?: Record<string, string>[] | string // 轮胎信息
  charging_port?: Record<string, string> | string // 充电盖
  charging_status?: Record<string, string> | string // 充电状态
  charging_limit?: Record<string, string> | string // 充电限制
  battery_info?: Record<string, string> | string // 电池信息
  air_condition?: Record<string, string>[] | string // 空调状态
  air_direction?: Record<string, string> | string // 空调风向
  air_circulation?: Record<string, string> | string // 空调循环模式
  air_cooling?: Record<string, string> | string // 空调制冷
  defrost_defog?: Record<string, string>[] | string // 除霜除雾
  air_purification?: Record<string, string> | string // 空气净化
  fan_speed_front?: Record<string, string> | string // 前排风量
  fan_speed_rear?: Record<string, string> | string // 后排风量
  interior_temperature?: Record<string, string>[] | string // 车内温度
  seat_position?: Record<string, string>[] | string // 座椅位置
  seat_ventilation?: Record<string, string>[] | string // 座椅通风
  seat_heating?: Record<string, string>[] | string // 座椅加热
  seat_massage?: Record<string, string>[] | string // 座椅按摩
  seat_belt_status?: Record<string, string> | string // 安全带状态
  window_status?: Record<string, string>[] | string // 车窗状态
  door_status?: Record<string, string>[] | string // 车门状态
  sunshade_left_rear?: Record<string, string> | string // 左后遮阳帘
  sunshade_right_rear?: Record<string, string> | string // 右后遮阳帘
  rearview_mirror?: Record<string, string> | string // 后视镜状态
  wiper_status?: Record<string, string> | string // 雨刮状态
  steering_wheel_heating?: Record<string, string> | string // 方向盘加热
  fragrance_system?: Record<string, string>[] | string // 香氛系统
  volume_status?: Record<string, string> | string // 音量状态
  sunroof_status?: Record<string, string> | string // 天窗状态
  tailgate_status?: Record<string, string> | string // 尾门状态
  radar_status?: Record<string, string> | string // 雷达状态
  panoramic_camera?: Record<string, string> | string // 360全景影像
  calendar_time?: Record<string, string> | string // 日历时间
  auto_parking?: Record<string, string> | string // 自动泊车
}

interface VehicleStateEntity {
  adsd?: ADSDState | string // ADSD状态
  media?: MediaState | string // 媒体状态
  navigation?: NavigationState | string // 导航状态
  signal_light?: SignalLightState | string // 信号灯状态
  system_control?: SystemControlState | string // 系统控制状态
  vehicle_control?: VehicleControlState | string // 车辆控制状态
  more_states?: Record<string, any> // 其它状态（动态属性）
}

interface VehicleState extends DomainCommon {
  entity?: VehicleStateEntity
}

// ==================== Visual Exterior ====================
interface VisualExteriorEntity {
  weather?: string // 天气状态
  road?: string // 道路状态
  building?: string // 建筑状态
  traffic?: string // 交通状态
  other_state?: Record<string, string> // 其它状态（动态属性）
}

interface VisualExterior extends DomainCommon {
  entity?: VisualExteriorEntity
}

// ==================== Visual Interior ====================
interface PersonState {
  position?: string // 位置
  sex?: string // 性别
  age?: string // 年龄
  expression?: string // 表情
  seat_belt_status?: string // 安全带状态
  appearance?: Record<string, string> | string // 外观
  clothes?: Record<string, string> | string // 衣服
  accessories?: string[] | string // 配饰
  action?: string[] | string // 动作
}

interface InteriorScene {
  persons?: PersonState[] | string // 人员情况
  child_seat?: Record<string, string> | string // 儿童座椅
  pet?: Record<string, string> | string // 宠物
}

interface VisualInteriorEntity {
  scenes?: Record<string, InteriorScene> | string // 场景描述 (key: camera id, value: 场景描述)
  other_state?: Record<string, string> // 其它状态（动态属性）
}

interface VisualInterior extends DomainCommon {
  entity?: VisualInteriorEntity
}

// ==================== World Info ====================
interface CityInfo {
  name?: string // 城市名称
  id?: string // 城市ID
  lat?: string // 纬度
  lon?: string // 经度
  adm2?: string // 二级行政区
  adm1?: string // 一级行政区
  country?: string // 国家
  tz?: string // 时区
  type?: string // 类型
}

interface WeatherForecast {
  obs_time?: string // 观测时间
  temp?: string // 温度
  feels_like?: string // 体感温度
  text?: string // 天气现象
  wind_dir?: string // 风向
  wind_scale?: string // 风力等级
  wind_speed?: string // 风速
  humidity?: string // 相对湿度
  precip?: string // 降水量
  cloud?: string // 云量
  pressure?: string // 大气压强
  vis?: string // 能见度
}

interface DateInfo {
  date?: string // 日期
  lunar_date?: string // 农历日期
  lunar_holiday?: string | string[] // 农历节日
  solar_holiday?: string | string[] // 公历节日
  solar_terms?: string // 节气
}

interface WorldInfoEntity {
  city?: CityInfo | string // 城市
  weather?: WeatherForecast | string // 天气
  date?: DateInfo | string // 日期
  attributes?: Record<string, string> // 其它属性（动态属性）
}

interface WorldInfo extends DomainCommon {
  entity?: WorldInfoEntity
}

// ==================== Memory ====================
interface EpisodicMemoryBlock {
  date_time?: string // 时间
  location?: string // 地点
  content?: string // 事件描述
  feel?: string // 感受
  details?: Record<string, unknown> // 其它细节
}

interface EpisodicMemoryEntity {
  instant?: string | EpisodicMemoryBlock[] // 瞬时记忆（20分钟内的20条QA对话+事件）
  short?: string | EpisodicMemoryBlock[] // 短期记忆（1天之内的记忆）
  long?: string | EpisodicMemoryBlock[] // 长期情景记忆（1天之前的记忆）
}

interface EpisodicMemory extends DomainCommon {
  entity?: EpisodicMemoryEntity
}

interface ContextLog extends Common {
  log_id?: string // 日志ID
  context?: Record<string, unknown> // 实车环境车辆状态上下文信息
  log_type?: string // 日志类型（全量日志full或diff日志diff）
  remark?: string // 备注
}
