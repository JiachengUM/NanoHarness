"""算子数据模型定义

本模块定义了 DAG 算子体系中所有输入/输出参数的 Pydantic 模型，
按业务域划分为以下类别：

1. 基础设施：BaseSchema — 所有模型的公共基类，提供 dump() 方法过滤空值字段
2. 地理检索：Location / POISearchParams / POISearchOutput — POI 搜索相关
3. 导航：NavigationParams / NavigationOutput — 路线规划与导航
4. 音乐检索：SongItem / PlaylistItem / AlbumItem / SongSearchParams / SongSearchOutput / PlaylistSearchParams / PlaylistSearchOutput / AlbumSearchParams / AlbumSearchOutput
5. 媒体控制：AudioPlayParams / AudioPlayAction / AUDIO_PLAY_ACTIONS / AudioPlayOutput
6. 车辆控制：CarControlParams / CarControlOutput
7. 通用检索：WebSearchParams / WebSearchOutput 及其子项（加油站/停车场/天气等）
8. 记忆召回：MemoryRecallParams / MemoryRecallOutput — 动态获取后台记忆数据（接口未就绪时转换为向用户索取信息的提问）
9. 注册元数据：OperatorInfo / OperatorRegistryModel — 算子注册表用
"""
import re
from typing import List, Dict, Optional, Union, Any, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


# $ref 占位符正则 — 与 base_classes._REF_PATTERN 保持一致
# 因 base_classes 反向依赖本模块的 BaseSchema（循环依赖），此处本地定义，
# 不从 base_classes 反向导入。两处正则需同步修改。
_REF_PATTERN = re.compile(r"\$(\w+)\.([\w.\[\]]+)")


class BaseSchema(BaseModel):
    """所有算子数据模型的公共基类。

    配置 frozen=True 保证不可变性，extra="ignore" 丢弃未定义字段。
    dump() 方法序列化时自动过滤 None、False、空列表/字典/字符串等无意义值。
    """
    model_config = ConfigDict(frozen=True, extra="ignore")

    def dump(self) -> Dict[str, Any]:
        """只检查第一层字段：过滤 False、[]、{}、""

        注意：用 `is not False` 严格判断布尔类型，避免 `0 == False` 误过滤合法数值。
        None 已被 exclude_none=True 处理，无需重复判断。
        """
        data = self.model_dump(exclude_none=True, exclude_unset=True)

        # 只过滤第一层；用 `is not False` 严格类型判断，保留 0/0.0 等合法数值
        return {k: v for k, v in data.items() if v is not False and (not hasattr(v, "__len__") or v)}


class Location(BaseSchema):
    """地理位置信息 - 原子能力：地理编码"""

    address: Optional[str] = Field(default=None, description="地址")
    city: Optional[str] = Field(default=None, description="城市")
    district: Optional[str] = Field(default=None, description="区县")
    

class POISearchParams(BaseSchema):
    """POI 搜索参数 - 原子能力：周边检索、关键词搜索"""
    poi_type: str = Field(description="POI或POI类型，多个用|分割")
    address: Optional[str] = Field(default=None, description="地址")
    city: Optional[str] = Field(default=None, description="城市")
    radius: Optional[int] = Field(default=3000, ge=0, le=5000, description="搜索中心半径(米)，0表示不限制距离")
    limit: Optional[int] = Field(default=10, ge=1, le=25, description="期望返回的结果数量上限，范围 1-25")
    


class BusinessItem(BaseSchema):
    """商业信息"""

    business_area: Optional[str] = Field(default=None, description="所属商圈")
    rating: Optional[str] = Field(default=None, description="评分")
    cost: Optional[str] = Field(default=None, description="人均消费")
    opentime_today: Optional[str] = Field(default=None, description="今日营业时间")
    opentime_week: Optional[str] = Field(default=None, description="每周营业时间")
    tel: Optional[str] = Field(default=None, description="联系电话")
    alias: Optional[str] = Field(default=None, description="POI别名")
    tag: Optional[str] = Field(default=None, description="特色内容")
    parking_type: Optional[str] = Field(default=None, description="停车场类型（地下、地面、路边）")



class IndoorItem(BaseSchema):
    """室内地图信息（对应amap的IndoorItem）"""

    floor: Optional[str] = Field(default=None, description="楼层")
    indoor_map: Optional[str] = Field(default=None, description="是否有室内地图标志，1=有，0=没有")


class POISearchOutput(BaseSchema):
    """POI搜索出参"""
    # 基础字段
    poi: Optional[str] = Field(default=None, description="POI名称", title="name")
    distance: Optional[str] = Field(default=None, description="离中心点距离(米)")
    type: Optional[str] = Field(default=None, description="POI所属类型")
    address: Optional[str] = Field(default=None, description="详细地址")

    # 行政区域字段
    pname: Optional[str] = Field(default=None, title="province", description="所属省份")
    cityname: Optional[str] = Field(default=None, title="city", description="所属城市")
    adname: Optional[str] = Field(default=None, title="district", description="所属区县")

    # 扩展字段（需要show_fields参数）
    business: Optional[BusinessItem] = Field(default=None, description="商业信息")
    indoor: Optional[IndoorItem] = Field(default=None, description="楼层室内地图")


class NavigationParams(BaseSchema):
    """导航参数 - 原子能力：路线规划与导航"""

    destination: Optional[str] = Field(default="", description="目的地")

    # 可选字段
    origin: Optional[str] = Field(
        default=None,
        description="出发地，默认使用当前位置"
    )
    
    departure_time: Optional[str] = Field(
        default=None,
        description="期望出发时间，格式: HH:MM"
    )

    # 路线偏好
    route_preference: Optional[Literal["fastest", "shortest", "economical", "scenic"]] = Field(
        default=None,
        description="路线偏好: fastest(最快), shortest(最短)"
    )

    # # 途经点
    # via_points: Optional[List[Optional[str]]] = Field(
    #     default_factory=list,
    #     description="途经点列表"
    # )
    #
    # # 避障选项
    # avoid_highway: Optional[bool] = Field(
    #     default=False,
    #     description="是否避开高速公路"
    # )
    # avoid_tolls: Optional[bool] = Field(
    #     default=False,
    #     description="是否避开收费路段"
    # )
    # avoid_ferry: Optional[bool] = Field(
    #     default=False,
    #     description="是否避开轮渡"
    # )


class NavigationOutput(BaseSchema):
    """导航执行输出"""

    message: str = Field(default="", description="导航结果描述")
    destination: str = Field(default="", description="目的地")


class SongItem(BaseSchema):
    """单曲信息项（对应 QQ 音乐 song API 返回）"""

    song_name: Optional[str] = Field(default=None, description="歌曲名称")
    song_title: Optional[str] = Field(default=None, description="歌曲标题")
    singer_name: Optional[str] = Field(default=None, description="歌手/演唱者姓名")
    singer_title: Optional[str] = Field(default=None, description="歌手展示标题")
    album_name: Optional[str] = Field(default=None, description="所属专辑名称")
    language: Optional[str] = Field(default=None, description="歌曲语言")
    genre: Optional[str] = Field(default=None, description="歌曲流派/曲风")
    author: Optional[str] = Field(default=None, description="作词/作曲信息")
    public_time: Optional[str] = Field(default=None, description="歌曲发行时间")
    match_lyric: Optional[str] = Field(default=None, description="匹配歌词片段")


class PlaylistItem(BaseSchema):
    """歌单信息项（对应 QQ 音乐 diss/歌单 API 返回）"""

    dissname: Optional[str] = Field(default=None, description="歌单名称")
    creator_name: Optional[str] = Field(default=None, description="创建者/编辑者昵称")
    creator_uin: Optional[str] = Field(default=None, description="创建者 QQ UIN（用户ID）")
    song_count: Optional[int] = Field(default=None, description="歌单包含的歌曲数量")
    createtime: Optional[int] = Field(default=None, description="歌单创建时间（Unix 时间戳，秒级）")
    diss_cover: Optional[str] = Field(default=None, description="歌单封面图 URL")
    diss_tags: Optional[str] = Field(default=None, description="歌单标签（逗号/竖线分隔的字符串）")
    intro: Optional[str] = Field(default=None, description="歌单简介/说明文案")


class AlbumItem(BaseSchema):
    """专辑信息项（对应 QQ 音乐 album API 返回）"""

    album_name: Optional[str] = Field(default=None, description="专辑名称")
    singer_name: Optional[str] = Field(default=None, description="专辑歌手（演唱者）")
    public_time: Optional[str] = Field(default=None, description="专辑发行时间（YYYY-MM-DD 或 YYYY）")
    company: Optional[str] = Field(default=None, description="发行公司/唱片公司")
    genre: Optional[str] = Field(default=None, description="专辑流派/曲风（如 流行/古典/爵士）")
    language: Optional[str] = Field(default=None, description="专辑语言")
    intro: Optional[str] = Field(default=None, description="专辑简介")
    song_count: Optional[int] = Field(default=None, description="专辑包含的歌曲数量")


class SongSearchParams(BaseSchema):
    """单曲搜索参数 - 原子能力：单曲检索"""

    song_name: Optional[str] = Field(default=None, description="歌曲名称")
    singer_name: Optional[str] = Field(default=None, description="歌手姓名")
    lyrics: Optional[str] = Field(default=None, description="歌词片段")
    language: Optional[str] = Field(default=None, description="歌曲语言筛选")
    genre: Optional[str] = Field(default=None, description="歌曲流派/曲风")
    mood: Optional[str] = Field(default=None, description="氛围/场景标签")
    year_range: Optional[str] = Field(default=None, description="发行年代范围")
    limit: Optional[int] = Field(default=5, description="期望返回的结果数量，5条起步")


class SongSearchOutput(BaseSchema):
    """单曲搜索输出"""
    songs: List[SongItem] = Field(default_factory=list, description="单曲结果列表")


class PlaylistSearchParams(BaseSchema):
    """歌单搜索参数 - 原子能力：歌单检索"""

    keyword: Optional[str] = Field(default=None, description="歌单主题/关键词")
    language: Optional[str] = Field(default=None, description="歌单语言筛选")
    genre: Optional[str] = Field(default=None, description="歌单流派/曲风")
    mood: Optional[str] = Field(default=None, description="氛围/场景标签")
    year_range: Optional[str] = Field(default=None, description="歌单年代范围")
    limit: Optional[int] = Field(default=5, description="期望返回的结果数量，5条起步")


class PlaylistSearchOutput(BaseSchema):
    """歌单搜索输出"""
    playlists: List[PlaylistItem] = Field(default_factory=list, description="歌单结果列表")


class AlbumSearchParams(BaseSchema):
    """专辑搜索参数 - 原子能力：专辑检索"""

    album_name: Optional[str] = Field(default=None, description="专辑名称")
    singer_name: Optional[str] = Field(default=None, description="专辑歌手")
    language: Optional[str] = Field(default=None, description="专辑语言筛选")
    genre: Optional[str] = Field(default=None, description="专辑流派/曲风")
    year_range: Optional[str] = Field(default=None, description="发行年代范围")
    limit: Optional[int] = Field(default=5, description="期望返回的结果数量，5条起步")


class AlbumSearchOutput(BaseSchema):
    """专辑搜索输出"""
    albums: List[AlbumItem] = Field(default_factory=list, description="专辑结果列表")


class AudioPlayParams(BaseSchema):
    """音频播放参数 - 原子能力：媒体控制"""

    action: Optional[Literal["play", "pause", "resume", "next", "previous", "set_volume", "add_to_playlist"]] = Field(
        default="",
        description=(
            "操作类型: play(播放)/pause(暂停)/resume(恢复)/"
            "next(下一首)/previous(上一首)/set_volume(调音量)/"
            "add_to_playlist(加入播放列表)"
        ),
    )
    content_name: Optional[str] = Field(
        default=None,
        description="播放内容：歌曲名称（song_name）/歌单名称（dissname）/专辑名称（album_name）")
    start_position: Optional[float] = Field(default=0, description="开始位置(秒)，仅 play 时有效")
    auto_continue: Optional[bool] = Field(default=True, description="自动继续播放下一首，仅 play 时有效")
    volume: Optional[int] = Field(default=None, ge=0, le=100, description="音量，仅 set_volume 时有效")


class AudioPlayAction(BaseSchema):
    """音频播放动作定义 - action 与自然语言指令模板的映射"""

    action: str = Field(description="操作类型")
    command: str = Field(description="自然语言指令模板，支持 {content_name}/{volume} 占位符")


AUDIO_PLAY_ACTIONS: List[AudioPlayAction] = [
    AudioPlayAction(action="play", command="播放{content_name}"),
    AudioPlayAction(action="pause", command="暂停播放"),
    AudioPlayAction(action="resume", command="继续播放"),
    AudioPlayAction(action="next", command="下一首"),
    AudioPlayAction(action="previous", command="上一首"),
    AudioPlayAction(action="set_volume", command="音量调到{volume}"),
    AudioPlayAction(action="add_to_playlist", command="把{content_name}加入播放列表"),
]


class AudioPlayOutput(BaseSchema):
    """音频播放执行输出"""

    status: str = Field(default="", description="执行状态: success/failed")
    action: str = Field(default="", description="执行的操作类型")
    content_name: Optional[str] = Field(default=None, description="当前播放内容名称（歌曲名/歌单名/专辑名）")
    is_playing: bool = Field(default=False, description="当前是否正在播放")
    current_position: Optional[float] = Field(default=None, description="当前播放位置(秒)")
    duration: Optional[float] = Field(default=None, description="总时长(秒)")
    volume: Optional[int] = Field(default=None, ge=0, le=100, description="当前音量(0-100)")
    message: str = Field(default="", description="执行结果描述")


class CarControlParams(BaseSchema):
    """车控参数 - 原子能力：车辆控制"""

    action: str = Field(description="操作类型")
    target: Optional[str] = Field(default=None, description="控制目标")
    value: Optional[Union[str, int, float]] = Field(default=None, description="设定值")
    command: Optional[str] = Field(default=None, description="完整指令")


class CarControlOutput(BaseSchema):
    """车控执行输出"""

    status: str = Field(default="", description="执行状态: success/failed")
    action: str = Field(default="", description="操作类型")
    message: str = Field(default="", description="执行结果消息")


class GasStationItem(BaseSchema):
    """加油站信息"""

    gas_brand: Optional[str] = Field(default=None, description="加油品牌")
    oil_price: Optional[str] = Field(default=None, description="油价")
    gas_address: Optional[str] = Field(default=None, description="加油地址")
    gas_payment: Optional[str] = Field(default=None, description="加油支付方式")


class ParkingItem(BaseSchema):
    """停车场信息"""

    parking_address: Optional[str] = Field(default=None, description="停车场地址")
    parking_fee: Optional[str] = Field(default=None, description="停车场收费标准")
    parking_available_spaces: Optional[str] = Field(default=None, description="停车场车位余量")
    parking_type: Optional[str] = Field(default=None, description="停车场类型")
    parking_opentime: Optional[str] = Field(default=None, description="停车场营业时间")
    parking_charging_info: Optional[str] = Field(default=None, description="停车场是否有充电桩")


class ServiceAreaItem(BaseSchema):
    """服务区信息"""

    service_area_address: Optional[str] = Field(default=None, description="服务区地址")
    service_area_facilities: Optional[str] = Field(default=None, description="服务区设施")
    service_area_opentime: Optional[str] = Field(default=None, description="服务区营业时间")


class ChargingStationItem(BaseSchema):
    """充电站信息"""

    charging_station_address: Optional[str] = Field(default=None, description="充电站地址")
    charging_station_brand: Optional[str] = Field(default=None, description="充电站品牌")
    charging_station_power: Optional[str] = Field(default=None, description="充电站功率")
    charging_station_connector_type: Optional[str] = Field(default=None, description="充电站接口类型")
    charging_station_price: Optional[str] = Field(default=None, description="充电站价格")
    charging_station_available_piles: Optional[str] = Field(default=None, description="充电站空闲桩数")


class NewsItem(BaseSchema):
    """新闻信息"""

    news_title: Optional[str] = Field(default=None, description="新闻标题")
    news_summary: Optional[str] = Field(default=None, description="新闻摘要")
    news_source: Optional[str] = Field(default=None, description="新闻来源")
    news_publish_time: Optional[str] = Field(default=None, description="新闻发布时间")


class TrafficItem(BaseSchema):
    """交通信息"""

    traffic_status: Optional[str] = Field(default=None, description="交通路况状态")
    traffic_congestion_index: Optional[str] = Field(default=None, description="交通拥堵指数")
    traffic_incident: Optional[str] = Field(default=None, description="交通事故/施工信息")
    traffic_estimated_time: Optional[str] = Field(default=None, description="交通预计通行时间")


class WeatherItem(BaseSchema):
    """天气或气候信息"""

    weather_temperature: Optional[str] = Field(default=None, description="气温")
    weather_feels_like: Optional[str] = Field(default=None, description="体感温度")
    weather_humidity: Optional[str] = Field(default=None, description="湿度")
    weather_wind: Optional[str] = Field(default=None, description="风力风向")
    weather_condition: Optional[str] = Field(default=None, description="天气状况")
    weather_sunrise_sunset: Optional[str] = Field(default=None, description="日出日落")
    weather_forecast: Optional[str] = Field(default=None, description="未来预报")


class AirQualityItem(BaseSchema):
    """空气质量信息"""

    aqi: Optional[str] = Field(default=None, description="AQI指数")
    primary_pollutant: Optional[str] = Field(default=None, description="主要污染物")
    air_quality_level: Optional[str] = Field(default=None, description="空气质量等级")


class FlightItem(BaseSchema):
    """航班信息"""

    flight_no: Optional[str] = Field(default=None, description="航班号")
    flight_departure_city: Optional[str] = Field(default=None, description="出发城市")
    flight_arrival_city: Optional[str] = Field(default=None, description="到达城市")
    flight_scheduled_departure: Optional[str] = Field(default=None, description="计划起飞时间")
    flight_scheduled_arrival: Optional[str] = Field(default=None, description="计划到达时间")
    flight_actual_departure: Optional[str] = Field(default=None, description="实际起飞时间")
    flight_actual_arrival: Optional[str] = Field(default=None, description="实际到达时间")
    flight_status: Optional[str] = Field(default=None, description="状态(准点/延误/取消)")
    flight_terminal_gate: Optional[str] = Field(default=None, description="航站楼/登机口")


class TrainItem(BaseSchema):
    """列车信息"""

    train_no: Optional[str] = Field(default=None, description="车次")
    train_departure_station: Optional[str] = Field(default=None, description="出发站")
    train_arrival_station: Optional[str] = Field(default=None, description="到达站")
    train_departure_time: Optional[str] = Field(default=None, description="出发时间")
    train_arrival_time: Optional[str] = Field(default=None, description="到达时间")
    train_duration: Optional[str] = Field(default=None, description="历时")
    train_price: Optional[str] = Field(default=None, description="票价")
    train_type: Optional[str] = Field(default=None, description="列车类型")
    train_remaining_tickets: Optional[str] = Field(default=None, description="余票")


class WebSearchParams(BaseSchema):
    """网页搜索参数 - 原子能力：通用信息检索

    query 中可包含 $step_id.field 占位符引用上游步骤输出，
    缺失部分在 DAG 执行时由依赖注入自动填充。
    """
    query: str = Field(description="中心词和搜索条件")


class WebSearchOutput(BaseSchema):
    """网页搜索输出 - 支持多种搜索类型的结果"""

    gas_station: Optional[GasStationItem] = Field(default=None, description="加油站信息")
    parking: Optional[ParkingItem] = Field(default=None, description="停车场信息")
    service_area: Optional[ServiceAreaItem] = Field(default=None, description="服务区信息")
    charging_station: Optional[ChargingStationItem] = Field(default=None, description="充电站信息")
    news: Optional[NewsItem] = Field(default=None, description="新闻信息")
    traffic: Optional[TrafficItem] = Field(default=None, description="交通信息")
    weather: Optional[WeatherItem] = Field(default=None, description="天气或气候信息")
    air_quality: Optional[AirQualityItem] = Field(default=None, description="空气质量信息")
    flight: Optional[FlightItem] = Field(default=None, description="航班信息")
    train: Optional[TrainItem] = Field(default=None, description="列车信息")
    # 通用兜底字段：声明 WebSearch 的 query 能搜索任意开放域信息
    # 该字段核心价值是通过 _generate_operator_description 被提取后展示给 LLM，
    # 让 LLM 知道当用户问题超出上述 10 种结构化类型时，可声明 step_output=["general"] 承接开放域查询
    general: Optional[str] = Field(
        default=None,
        description="当用户查询意图无法归入注册算子类型时启用",
    )


class SourceExtraInfo(BaseSchema):
    """附加信息模型"""

    auth_info: str = Field(..., description="信息权威性评级")
    freshness_info: str = Field(..., description="时效性信息")
    rel_info: str = Field(..., description="相关性信息")


class WebsearchToolOutput(BaseSchema):
    """网页搜索结果文档模型"""

    extra: SourceExtraInfo = Field(..., description="附加元数据")
    publish_time: str = Field(..., description="信息发布时间")
    site_name: str = Field(..., description="网站名称")
    summary: str = Field(..., description="搜索内容摘要")
    title: str = Field(..., description="内容标题")


class OperatorInfo(BaseSchema):
    """算子信息模型"""

    operator_type: str = Field(description="算子类型标识")
    description: str = Field(description="算子描述")
    input_model: type = Field(description="输入参数模型类")
    output_model: type = Field(description="输出参数模型类")


class OperatorRegistryModel(BaseSchema):
    """算子注册表模型"""

    operators: Dict[str, OperatorInfo] = Field(default_factory=dict, description="算子信息字典")


# ==================== 条件判断算子 ====================
class ConditionRule(BaseSchema):
    """条件算子-规则项：单条 when(条件描述)→then(命中时结构化输出) 映射"""

    when: str = Field(..., description="条件描述")
    then: Dict[str, Any] = Field(..., description="命中时的结构化输出")


class ConditionParams(BaseSchema):
    """条件算子-入参：facts(上游信息) + rules(有序规则表) + default(兜底输出)
    facts 为整个 Condition 算子声明的上游依赖字段总集：
    - when 条件判断所依赖的字段必须在此声明
    - then 中所有 $ref 引用必须在此声明
    - 元素为 $ref 占位符（如 $s1.weather.temperature）
    """

    facts: List[str] = Field(..., description="描述条件和结果")
    rules: List[ConditionRule] = Field(..., description="有序条件规则表")
    default: Dict[str, Any] = Field(..., description="所有规则均不命中时的兜底输出")


class ConditionOutput(BaseSchema):
    """条件算子-出参：动态字段输出，承载命中规则 then 的字段，下游引用通过 $step_id.field"""

    model_config = ConfigDict(frozen=True, extra="allow")


# ==================== 目标验证算子 ====================
class DownstreamNodeRef(BaseSchema):
    """下游节点引用 — 当前节点输出的消费者"""
    node_id: str = Field(description="下游节点ID")
    operator_type: str = Field(default="", description="下游节点算子类型")
    step_goal: str = Field(default="", description="下游节点步骤目标")
    step_output: List[str] = Field(default_factory=list, description="当前节点字段列表")


class ValidatorParams(BaseSchema):
    """目标验证算子入参：下游后继节点信息"""
    downstream_nodes: List[DownstreamNodeRef] = Field(
        default_factory=list,
        description="当前节点的下游后继节点列表（依赖当前节点输出的节点）"
    )


class ImprovementPoint(BaseSchema):
    """节点级改进点"""
    node_id: str = Field(description="目标节点ID")
    issue_type: str = Field(description="问题类型: goal_not_achieved / output_insufficient / output_misaligned / downstream_blocker")
    description: str = Field(description="改进建议描述")
    severity: str = Field(default="medium", description="严重级别: low/medium/high")


class ValidatorOutput(BaseSchema):
    """目标验证算子出参：结构化目标达成判定 + 节点级改进点"""
    goal_achieved: bool = Field(description="当前节点 step_goal 是否达成")
    confidence: str = Field(default="high", description="判断置信度: high/medium/low")
    current_improvements: List[ImprovementPoint] = Field(
        default_factory=list, description="当前节点的改进点列表"
    )
    downstream_improvements: List[ImprovementPoint] = Field(
        default_factory=list, description="下游后继节点的改进点列表（基于当前产出对下游的影响）"
    )
    reasoning: str = Field(default="", description="判断依据简述")


# ==================== 记忆召回算子 ====================
class MemoryRecallParams(BaseSchema):
    """记忆召回参数 - 原子能力：动态获取后台记忆数据

    入参对应"调用记忆数据接口的请求参数"。由于记忆数据接口尚未就绪，
    执行器不真正调用接口，而是由 LLM 根据查询参数 mock 出合理的记忆数据，
    供下游算子正常消费，使 Plan 链路可以在无真实记忆接口时跑通。
    """
    query: str = Field(description="记忆查询描述，如'用户的音乐偏好'、'上次导航的目的地'")
    memory_type: Literal["preference", "history", "context", "profile"] = Field(
        default="preference",
        description="记忆类型: preference(偏好)/history(历史)/context(上下文)/profile(用户画像)",
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="可选过滤条件，如时间范围、标签等",
    )
    limit: Optional[int] = Field(
        default=5,
        ge=1,
        le=20,
        description="期望返回的记忆条数",
    )


class MemoryRecallOutput(BaseSchema):
    """记忆召回输出 - LLM mock 的记忆事实数据

    真实记忆接口就绪后，直接替换为真实接口返回结构即可。
    """
    facts: str = Field(default="", description="mock 的记忆事实文本，直接可被下游消费使用")
