from __future__ import annotations

import logging
from typing import Annotated, Any

import httpx
from typing import Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from aicore.utils.volc_client.httpx_client import HttpClient, HttpxTransport

logger = logging.getLogger(__name__)

AMAP_GEO_PATH = "/v3/geocode/geo"
AMAP_REGEO_PATH = "/v3/geocode/regeo"
AMAP_TEXT_SEARCH_PATH = "/v5/place/text"
AMAP_AROUND_SEARCH_PATH = "/v5/place/around"
AMAP_DETAIL_PATH = "/v5/place/detail"
AMAP_INPUTTIPS_PATH = "/v3/assistant/inputtips"

# TODO: 不能hardcode
AMAP_API_KEY: str = "a53f6c8c2e40a2dc7436260d2f4bdb10"
AMAP_API_URL: str = "https://restapi.amap.com"

_http_client: HttpClient | None = None


def _get_client() -> HttpClient:
    global _http_client
    if _http_client is None:
        _http_client = HttpClient(HttpxTransport(httpx.AsyncClient(timeout=httpx.Timeout(10.0))))
    return _http_client


async def amap_request(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """
    高德 HTTP 调用公共封装：自动补 key，失败返回 None。
    重试逻辑交给调用方，此处保持单次简洁。
    """
    url = f"{AMAP_API_URL}{path}"
    resp = await _get_client().get(url, params={**params, "key": AMAP_API_KEY})
    if isinstance(resp.json, dict):
        return resp.json
    logger.warning("高德接口返回非 JSON 响应: path=%s text=%s", path, resp.text)
    return None


# 高德在字段无值时返回 [] 而非 null，用此类型统一转成 None
# TODO: NullableStr这个名字有点问题。其字面语义是 str | None，非常通用，但BeforeValidator的实现跟高德的实现相关。因此，又不能通用。
# 理应拆开为两部分，但又显得太啰嗦。暂时先这么用着。
NullableStr = Annotated[str | None, BeforeValidator(lambda v: None if isinstance(v, list) else v)]


# ── /v3/geocode/geo ───────────────────────────────────────────────────────────


class GeoRequest(BaseModel):
    """高德地理编码请求参数（/v3/geocode/geo）。"""

    address: str = Field(..., description="结构化地址，如：北京市朝阳区阜通东大街6号")
    city: str | None = Field(default=None, description="指定城市，中文/全拼/citycode/adcode均可")


class GeocodeResult(BaseModel):
    """单条地理编码结果，对应响应 geocodes 列表中的每个元素。"""

    model_config = ConfigDict(frozen=True)

    country: NullableStr = Field(default=None, description="国家")
    province: NullableStr = Field(default=None, description="省份")
    city: NullableStr = Field(default=None, description="城市")
    citycode: NullableStr = Field(default=None, description="城市编码，如 010")
    district: NullableStr = Field(default=None, description="区县")
    street: NullableStr = Field(default=None, description="街道")
    number: NullableStr = Field(default=None, description="门牌号")
    adcode: NullableStr = Field(default=None, description="区域编码，如 110101")
    location: str = Field(..., description='坐标点，格式为"经度,纬度"')
    level: NullableStr = Field(default=None, description="匹配级别，如：门牌号、道路")


class GeoResponse(BaseModel):
    """高德地理编码接口完整响应。"""

    status: str = Field(..., description="0=失败，1=成功")
    count: str = Field(default="0", description="返回结果数目")
    info: str = Field(default="", description="状态说明，成功时为 OK")
    geocodes: list[GeocodeResult] = Field(default_factory=list)


async def amap_geo(request: GeoRequest) -> GeoResponse:
    """
    高德地理编码：将地址转为经纬度坐标。

    失败时抛 ValueError（地址无匹配）或 RuntimeError（接口异常）。
    """
    params: dict[str, Any] = {"address": request.address}
    if request.city:
        params["city"] = request.city

    data = await amap_request(AMAP_GEO_PATH, params)
    if data is None:
        raise RuntimeError(f"高德地理编码接口请求失败: address={request.address!r}")

    response = GeoResponse.model_validate(data)
    if response.status != "1" or not response.geocodes:
        raise ValueError(f"高德地理编码无匹配结果: address={request.address!r} info={response.info!r}")

    return response


async def amap_regeo(location: str, *, extensions: str = "all") -> dict[str, Any] | None:
    """
    高德逆地理编码（/v3/geocode/regeo）：经纬度转地址等信息。
    extensions: base 仅返回基础；all 含周边 POI、道路等（与高德文档一致）。
    返回原始 JSON dict，失败或异常响应结构与 geo 一致，由调用方判断 status。
    """
    params: dict[str, Any] = {"location": location, "extensions": extensions}
    return await amap_request(AMAP_REGEO_PATH, params)


# ── /v5/place/text ────────────────────────────────────────────────────────────


class TextSearchRequest(BaseModel):
    """高德关键字搜索请求参数（/v5/place/text）。"""

    keywords: str = Field(..., description="搜索关键词，如：美食、麦当劳")
    region: str | None = Field(default=None, description="搜索区域，cityname/citycode/adcode均可")
    city_limit: bool = Field(default=False, description="是否将结果限定在 region 内")
    show_fields: str = Field(default="", description="附加返回字段，逗号分隔")
    page_size: int = Field(default=5, ge=1, le=25, description="每页条数，范围 1-25")
    page_num: int = Field(default=1, ge=1, description="页码，从 1 开始")

    @model_validator(mode="after")
    def _check_city_limit(self) -> Self:
        if self.city_limit and not self.region:
            raise ValueError("city_limit=True 时必须同时指定 region")
        return self

    def to_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "keywords": self.keywords,
            "show_fields": self.show_fields,
            "page_size": self.page_size,
            "page_num": self.page_num,
        }
        if self.region:
            params["region"] = self.region
        if self.city_limit:
            params["city_limit"] = "true"
        return params


class BusinessItem(BaseModel):
    """商业信息（show_fields=business）。"""
    business_area: NullableStr = Field(default=None, description="POI 所属商圈", title="商圈")
    rating: NullableStr = Field(default=None, description="评分", title="评分")
    cost: NullableStr = Field(default=None, description="人均消费", title="人均消费")
    opentime_today: NullableStr = Field(default=None, description="今天营业时间", title="今天营业时间")
    opentime_week: NullableStr = Field(default=None, description="每周营业时间", title="每周营业时间")
    tel: NullableStr = Field(default=None, description="联系电话", title="联系电话")
    tag: NullableStr = Field(default=None, description="特色内容", title="特色内容")
    parking_type: NullableStr = Field(default=None, description="停车场类型（地下、地面、路边）", title="停车场类型")
    alias: NullableStr = Field(default=None, description="POI 别名", title="别名")
    keytag: NullableStr = Field(default=None, description="POI 标识，用于确认 POI 信息类型", title="标识")
    rectag: NullableStr = Field(default=None, description="用于再次确认信息类型", title="推荐标识")

class ChildrenItem(BaseModel):
    """子 POI 列表（show_fields=children）。"""
    id: NullableStr = Field(default=None, description="子 POI 唯一标识", title="id")
    name: NullableStr = Field(default=None, description="子 POI 名称", title="name")
    location: NullableStr = Field(default=None, description='子 POI 坐标点，格式为"经度,纬度"', title="坐标")
    address: NullableStr = Field(default=None, description="子 POI 详细地址", title="详细地址")
    subtype: NullableStr = Field(default=None, description="子 POI 所属类型", title="subtype")
    typecode: NullableStr = Field(default=None, description="子 POI 分类编码", title="typecode")
    sname: NullableStr = Field(default=None, description="子 POI 分类信息", title="sname")


class IndoorItem(BaseModel):
    """室内信息（show_fields=indoor）。"""
    indoor_map: NullableStr = Field(default=None, description="是否有室内地图标志，1=有，0=没有", title="室内地图")
    cpid: NullableStr = Field(default=None, description="建筑物 POI ID", title="建筑物ID")
    floor: NullableStr = Field(default=None, description="楼层索引（通常为数字）", title="楼层索引（物理楼层）")
    truefloor: NullableStr = Field(default=None, description="所在楼层（可能带字母）", title="楼层索引（展示楼层）")


class NaviItem(BaseModel):
    """导航信息（show_fields=navi）。"""
    navi_poiid: NullableStr = Field(default=None, description="导航引导点坐标 ID", title="navi_poiid")
    entr_location: NullableStr = Field(default=None, description='入口经纬度，格式为"经度,纬度"', title="导航地址入口")
    exit_location: NullableStr = Field(default=None, description='出口经纬度，格式为"经度,纬度"', title="导航地址出口")
    gridcode: NullableStr = Field(default=None, description="地理格 ID", title="gridcode")


class PhotoItem(BaseModel):
    """图片信息（show_fields=photos）。"""
    title: NullableStr = Field(default=None, description="图片标题", title="图片标题")
    url: NullableStr = Field(default=None, description="图片链接", title="图片链接")

    

class PoiItem(BaseModel):
    """单条 POI 结果（text search 和 around search 共用）。"""

    model_config = ConfigDict(frozen=True)

    id: NullableStr = Field(default=None, description="POI 唯一标识", title="id")
    name: NullableStr = Field(default=None, description="POI 名称", title="name")
    parent: NullableStr = Field(default=None, description="父 POI 的 ID，无父 POI 时为空", title="parent")
    location: NullableStr = Field(default=None, description='坐标点，格式为"经度,纬度"', title="坐标")
    distance: NullableStr = Field(default=None, description="离中心点距离，单位米（仅周边搜索返回）", title="距离")
    type: NullableStr = Field(default=None, description="POI 所属类型", title="type")
    typecode: NullableStr = Field(default=None, description="POI 分类编码", title="typecode")
    address: NullableStr = Field(default=None, description="详细地址", title="详细地址")
    pname: NullableStr = Field(default=None, description="所属省份", title="省份")
    cityname: NullableStr = Field(default=None, description="所属城市", title="城市")
    adname: NullableStr = Field(default=None, description="所属区县", title="区县")
    pcode: NullableStr = Field(default=None, description="省份编码", title="省份编码")
    adcode: NullableStr = Field(default=None, description="区域编码", title="区域编码")
    citycode: NullableStr = Field(default=None, description="城市编码", title="城市编码")
    # show_fields 扩展对象（纯嵌套结构，不做拍平），嵌套basemodel可以不用title，否则会看起来很怪
    business: BusinessItem | None = Field(default=None, description="商业信息（show_fields=business）")
    children: list[ChildrenItem] | None = Field(default=None, description="子 POI 列表（show_fields=children）")
    indoor: IndoorItem | None = Field(default=None, description="楼层室内地图（show_fields=indoor）")
    navi: NaviItem | None = Field(default=None, description="poi出入口（show_fields=navi）")
    photos: list[PhotoItem] | None = Field(default=None, description="图片信息（show_fields=photos）")


class PoiSearchResponse(BaseModel):
    """高德 POI 搜索接口响应（关键字搜索 / 周边搜索共用）。"""

    status: str = Field(..., description="0=失败，1=成功")
    info: str = Field(default="", description="状态说明，成功时为 ok")
    infocode: str = Field(default="", description="状态码，10000 表示成功")
    count: str = Field(default="0", description="返回 POI 数目")
    pois: list[PoiItem] = Field(default_factory=list)


async def amap_text_search(request: TextSearchRequest) -> PoiSearchResponse:
    """
    高德关键字搜索（/v5/place/text）。

    失败时抛 ValueError（无结果）或 RuntimeError（接口异常）。
    """
    data = await amap_request(AMAP_TEXT_SEARCH_PATH, request.to_params())
    if data is None:
        raise RuntimeError(f"高德关键字搜索接口请求失败: keywords={request.keywords!r}")

    response = PoiSearchResponse.model_validate(data)
    if response.status != "1":
        raise ValueError(f"高德关键字搜索失败: keywords={request.keywords!r} info={response.info!r}")

    return response


# ── /v5/place/around ──────────────────────────────────────────────────────────


class AroundSearchRequest(BaseModel):
    """高德周边搜索请求参数（/v5/place/around）。"""

    location: str = Field(..., description='搜索中心点坐标，格式为"经度,纬度"')
    keywords: str | None = Field(default=None, description="搜索关键词，如：美食、停车场")
    radius: int = Field(default=5000, ge=0, le=50000, description="搜索半径，单位米，范围 0-50000")
    sortrule: str = Field(default="distance", description="排序规则：distance（距离）/ weight（综合）")
    region: str | None = Field(default=None, description="搜索区域，配合 city_limit 使用")
    city_limit: bool = Field(default=False, description="是否将结果限定在 region 内")
    show_fields: str = Field(default="", description="附加返回字段，逗号分隔")
    page_size: int = Field(default=5, ge=1, le=25, description="每页条数，范围 1-25")
    page_num: int = Field(default=1, ge=1, description="页码，从 1 开始")

    @model_validator(mode="after")
    def _check_city_limit(self) -> Self:
        if self.city_limit and not self.region:
            raise ValueError("city_limit=True 时必须同时指定 region")
        return self

    def to_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "location": self.location,
            "radius": self.radius,
            "sortrule": self.sortrule,
            "show_fields": self.show_fields,
            "page_size": self.page_size,
            "page_num": self.page_num,
        }
        if self.keywords:
            params["keywords"] = self.keywords
        if self.region:
            params["region"] = self.region
        if self.city_limit:
            params["city_limit"] = "true"
        return params


async def amap_around_search(request: AroundSearchRequest) -> PoiSearchResponse:
    """
    高德周边搜索（/v5/place/around）：基于中心坐标 + 半径搜索 POI。
    响应结构与关键字搜索相同，POI 中额外包含 distance 字段。

    失败时抛 ValueError（无结果）或 RuntimeError（接口异常）。
    """
    data = await amap_request(AMAP_AROUND_SEARCH_PATH, request.to_params())

    if data is None:
        raise RuntimeError(f"高德周边搜索接口请求失败: location={request.location!r}")

    response = PoiSearchResponse.model_validate(data)
    if response.status != "1":
        raise ValueError(f"高德周边搜索失败: location={request.location!r} info={response.info!r}")

    return response


# ── /v5/place/detail ──────────────────────────────────────────────────────────


class PoiDetailRequest(BaseModel):
    """高德 POI ID 搜索请求参数（/v5/place/detail）。"""

    id: str = Field(..., description="POI 唯一标识，多个 ID 用'|'分隔，最多 10 个")
    show_fields: str = Field(default="", description="附加返回字段，逗号分隔")

    def to_params(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "show_fields": self.show_fields,
        }


class PoiDetailResponse(BaseModel):
    """高德 POI ID 搜索接口响应（无 count 字段）。"""

    status: str = Field(..., description="0=失败，1=成功")
    info: str = Field(default="", description="状态说明，成功时为 ok")
    infocode: str = Field(default="", description="状态码，10000 表示成功")
    pois: list[PoiItem] = Field(default_factory=list)


async def amap_poi_detail(request: PoiDetailRequest) -> PoiDetailResponse:
    """
    高德 POI ID 搜索（/v5/place/detail）：通过 POI ID 获取详细信息，最多 10 个。

    失败时抛 ValueError（ID 无结果）或 RuntimeError（接口异常）。
    """
    data = await amap_request(AMAP_DETAIL_PATH, request.to_params())
    if data is None:
        raise RuntimeError(f"高德 POI ID 搜索接口请求失败: id={request.id!r}")

    response = PoiDetailResponse.model_validate(data)
    if response.status != "1":
        raise ValueError(f"高德 POI ID 搜索失败: id={request.id!r} info={response.info!r}")

    return response


# ── /v3/assistant/inputtips ───────────────────────────────────────────────────


class InputTipsRequest(BaseModel):
    """高德输入提示请求参数（/v3/assistant/inputtips）。"""

    keywords: str = Field(..., description="查询关键词")
    type: str | None = Field(default=None, description="POI 分类，多类型用'|'分隔，建议使用分类代码")
    location: str | None = Field(default=None, description='坐标，格式为"经度,纬度"，填写后优先返回附近结果')
    city: str | None = Field(default=None, description="搜索城市，citycode 或 adcode")
    citylimit: bool = Field(default=False, description="是否仅返回指定城市数据")
    datatype: str = Field(default="all", description="返回数据类型：all / poi / bus / busline")

    def to_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {"keywords": self.keywords, "datatype": self.datatype}
        if self.type:
            params["type"] = self.type
        if self.location:
            params["location"] = self.location
        if self.city:
            params["city"] = self.city
        if self.citylimit:
            params["citylimit"] = "true"
        return params


class InputTip(BaseModel):
    """单条输入提示结果。"""

    id: NullableStr = Field(default=None, description="POI / bus / busline ID")
    name: NullableStr = Field(default=None, description="tip 名称")
    district: NullableStr = Field(default=None, description="所属区域（省+市+区）")
    adcode: NullableStr = Field(default=None, description="区域编码，六位区县编码")
    location: NullableStr = Field(default=None, description="tip 中心点坐标，busline 类型时不返回")
    address: NullableStr = Field(default=None, description="详细地址")


class InputTipsResponse(BaseModel):
    """高德输入提示接口响应。"""

    status: str = Field(..., description="0=失败，1=成功")
    info: str = Field(default="", description="状态说明，成功时为 OK")
    count: str = Field(default="0", description="返回结果总数目")
    tips: list[InputTip] = Field(default_factory=list)


async def amap_inputtips(request: InputTipsRequest) -> InputTipsResponse:
    """
    高德输入提示（/v3/assistant/inputtips）：根据关键词返回联想提示列表。

    失败时抛 ValueError（无结果）或 RuntimeError（接口异常）。
    """
    data = await amap_request(AMAP_INPUTTIPS_PATH, request.to_params())
    if data is None:
        raise RuntimeError(f"高德输入提示接口请求失败: keywords={request.keywords!r}")

    response = InputTipsResponse.model_validate(data)
    if response.status != "1":
        raise ValueError(f"高德输入提示失败: keywords={request.keywords!r} info={response.info!r}")

    return response
