import asyncio

from rich import print

from projects.mind.toolset.amap import (
    AroundSearchRequest,
    GeoRequest,
    InputTipsRequest,
    PoiDetailRequest,
    TextSearchRequest,
    amap_around_search,
    amap_geo,
    amap_inputtips,
    amap_poi_detail,
    amap_regeo,
    amap_text_search,
)


async def test_amap_geo():
    print("test_amap_geo")

    cases = [
        # GeoRequest(address="北京市海淀区"),           # 最简单 case
        # GeoRequest(address="吴中区"),                 # 缺 city，但唯一
        # GeoRequest(address="南京路"),                 # 缺 city，多结果
        # GeoRequest(address="南京路", city="上海"),     # 加 city 消歧义
        # GeoRequest(address="未知地点"),               # 奇怪的地址
        # GeoRequest(address="100000"),                 # 纯数字
        # GeoRequest(address="#%@QH^*&%"),              # 乱码，应该失败
        GeoRequest(address="浦东圆湖"),
        GeoRequest(address="上海市平金中心1号楼"),
        GeoRequest(address="上海环球金融中心", city="上海"),          
        GeoRequest(address="上海中心大厦", city="上海"),         
        GeoRequest(address="上海市黄浦区中山东一路18号", city="上海"),            # 外滩18号
        GeoRequest(address="上海市静安区南京西路1266号", city="上海"),           # 恒隆广场
        GeoRequest(address="上海市徐汇区虹桥路1号", city="上海"),                 # 港汇恒隆广场
        GeoRequest(address="上海市闵行区申长路688号", city="上海"),               # 虹桥天地
        GeoRequest(address="上海市普陀区中山北路3300号", city="上海"),            # 环球港
        GeoRequest(address="上海市杨浦区淞沪路1号", city="上海"),                 # 五角场万达
    ]

    for req in cases:
        print(f"address={req.address!r} city={req.city!r}")
        try:
            resp = await amap_geo(req)
            print(resp)
            # 用 geo 返回的经纬度做逆编码，对照「推断地址」实际落点含义
            loc = resp.geocodes[0].location
            regeo_dict = await amap_regeo(loc)
            print({"location_from_geo": loc, "regeo_v3": regeo_dict})
        except Exception as e:
            print(e)


async def test_amap_text_search():
    print("test_amap_text_search")

    cases = [
        TextSearchRequest(keywords="美食", region="上海"),                          # 有 region
        TextSearchRequest(keywords="麦当劳", region="北京", city_limit=True),        # city_limit 限定
        TextSearchRequest(keywords="美食", region="上海", page_size=3),              # 限制返回数量
        TextSearchRequest(keywords="我喜欢吃的东西"),                                # 模糊描述
        TextSearchRequest(keywords="#%@QH^*&%"),                                    # 乱码
    ]

    for req in cases:
        print(f"keywords={req.keywords!r} region={req.region!r} city_limit={req.city_limit}")
        try:
            resp = await amap_text_search(req)
            print(resp)
        except Exception as e:
            print(e)


async def test_amap_around_search():
    print("test_amap_around_search")

    # 先用 geo 拿到坐标，再做周边搜索
    geo = await amap_geo(GeoRequest(address="莘庄维璟印象城"))
    location = geo.geocodes[0].location
    print(f"莘庄维璟印象城坐标: {location}")

    cases = [
        AroundSearchRequest(location=location, keywords="盒马生鲜", radius=1000),                       # 1km 内美食
        # AroundSearchRequest(location=location, keywords="咖啡", radius=500, sortrule="weight"),      # 综合排序
        # AroundSearchRequest(location=location, keywords="餐饮", radius=2000),                        # 2km 内餐饮
        # AroundSearchRequest(location=location, keywords="停车场", radius=50000),                     # 最大半径
    ]

    for req in cases:
        print(f"keywords={req.keywords!r} radius={req.radius}")
        try:
            resp = await amap_around_search(req)
            print(resp)
        except Exception as e:
            print(e)


# 
async def test_amap_text_search_with_all_show_fields():
    print("test_amap_text_search_with_all_show_fields")

    show_fields = "business,children,indoor,navi,photos"
    req = TextSearchRequest(
        keywords="徐家汇附近的海底捞火锅",
        region="上海",
        city_limit=True,
        show_fields=show_fields,
        page_size=25,
    )

    print(f"keywords={req.keywords!r} region={req.region!r} show_fields={show_fields!r}")
    resp = await amap_text_search(req)
    print(resp.model_dump())


async def test_amap_around_search_with_all_show_fields():
    print("test_amap_around_search_with_all_show_fields")

    geo = await amap_geo(GeoRequest(address="上海市平金中心"))
    location = geo.geocodes[0].location
    show_fields = "business,children,indoor,navi,photos"
    req = AroundSearchRequest(
        location=location,
        keywords="火锅店",
        radius=10000,
        sortrule="weight",
        region="上海",
        city_limit=True,
        show_fields=show_fields,
        page_size=5,
    )
    print(f"location={location!r} keywords={req.keywords!r} show_fields={show_fields!r}")
    resp = await amap_around_search(req)
    print(resp.model_dump())


async def test_amap_poi_detail():
    print("test_amap_poi_detail")

    req = PoiDetailRequest(id="B0KK1HWNYY", show_fields="business,children,indoor,navi,photos")
    print(f"id={req.id!r} show_fields={req.show_fields!r}")
    resp = await amap_poi_detail(req)
    print(resp.model_dump())


async def test_amap_inputtips():
    print("test_amap_inputtips")

    req = InputTipsRequest(keywords="haidilao", city="上海", citylimit=True, datatype="poi")
    # cases = [
    #     # 基础：限定城市的 POI 联想
    #     InputTipsRequest(keywords="海底", city="上海", citylimit=True, datatype="poi"),
    #     # 带坐标：优先返回附近结果
    #     InputTipsRequest(keywords="停车", city="上海", location="121.4924,31.2355", citylimit=True, datatype="poi"),
    #     # 指定 POI 分类代码：餐饮（050000）
    #     InputTipsRequest(keywords="火锅", city="北京", citylimit=True, type="050000", datatype="poi"),
    #     # 不限城市：全国范围搜索
    #     InputTipsRequest(keywords="西湖", datatype="poi"),
    #     # 极短词：单字联想
    #     InputTipsRequest(keywords="麦", city="上海", citylimit=True, datatype="poi"),
    #     # 拼音输入联想
    #     InputTipsRequest(keywords="haidilao", city="上海", citylimit=True, datatype="poi"),
    # ]
    print(f"keywords={req.keywords!r} city={req.city!r} citylimit={req.citylimit}")
    resp = await amap_inputtips(req)
    print(resp.model_dump())


async def main():
    # await test_amap_geo()
    # await test_amap_text_search()
    # await test_amap_around_search()
    # await test_amap_text_search_with_all_show_fields()
    # await test_amap_around_search_with_all_show_fields()
    await test_amap_poi_detail()
    await test_amap_inputtips()


if __name__ == "__main__":
    asyncio.run(main())
