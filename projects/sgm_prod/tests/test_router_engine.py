from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

import projects.sgm_prod.classification.engine as router_engine
from projects.sgm_prod.classification import (
    arbitrate_simple_complex,
    arbitrate_simple_complex_decision,
)
from projects.sgm_prod.classification.models import RouterDecision, RouterTrace
from projects.sgm_prod.classification.tools import (
    evaluate_router_assets,
    evaluate_router_e2e_llm,
    evaluate_router_rules,
)
from projects.sgm_prod.classification.tools._asset_dir import use_router_asset_dir


@pytest.mark.asyncio
async def test_arbitration_trace_records_requested_project() -> None:
    decision = await arbitrate_simple_complex_decision(
        "打开主驾车窗",
        project="SGM",
        use_llm_fallback=False,
    )

    assert decision.trace.project == "SGM"


@pytest.mark.asyncio
async def test_baic_uses_sgm_assets_but_preserves_requested_project_in_trace() -> None:
    decision = await arbitrate_simple_complex_decision(
        "打开主驾车窗",
        project="baic",
        use_llm_fallback=False,
    )

    assert decision.label == "simple"
    assert decision.trace.project == "baic"


@pytest.mark.asyncio
async def test_exact_simple_wins_before_risk_words() -> None:
    # 这条 query 包含 conditional_automation 的 "自动" 子串，但 exact_simple 应优先
    decision = await arbitrate_simple_complex_decision("空调风量设为自动")

    assert decision.label == "simple"
    assert decision.source == "exact_simple"
    assert decision.trace.decision_path[0] == "exact_simple:hit"


@pytest.mark.asyncio
async def test_exact_complex_wins_before_parser() -> None:
    decision = await arbitrate_simple_complex_decision("关闭所有车窗和天窗")

    assert decision.label == "complex"
    assert decision.source == "exact_complex"


@pytest.mark.asyncio
async def test_exact_simple_wins_even_with_history() -> None:
    decision = await arbitrate_simple_complex_decision(
        "把空调调到23度",
        history=[{"q": "刚才问了什么", "a": "天气"}],
    )

    assert decision.label == "simple"
    assert decision.source == "exact_simple"
    assert decision.trace.decision_path[0] == "exact_simple:hit"


@pytest.mark.asyncio
async def test_complex_boundary_case_does_not_fall_to_simple_parser() -> None:
    decision = await arbitrate_simple_complex_decision("如果车内温度超过25度，就把空调打开")

    assert decision.label == "complex"
    assert decision.source in {"exact_complex", "parser_veto"}


@pytest.mark.asyncio
async def test_parser_simple_path_returns_trace() -> None:
    decision = await arbitrate_simple_complex_decision("打开主驾车窗")

    assert decision.label == "simple"
    assert decision.source in {"exact_simple", "parser_simple"}
    assert decision.trace.rule_version.startswith("router_rules_")


@pytest.mark.asyncio
async def test_rule_only_keeps_multi_capability_sequence_complex() -> None:
    decision = await arbitrate_simple_complex_decision(
        "打开空调，关闭所有车窗",
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source == "parser_veto"


@pytest.mark.asyncio
async def test_rule_only_flags_same_capability_parallel_target_as_complex() -> None:
    # P0：同 capability 多 target 走 parser_veto
    decision = await arbitrate_simple_complex_decision(
        "关闭车道保持和车道居中",
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source == "parser_veto"


@pytest.mark.parametrize(
    "query",
    [
        "我的电量还剩下多少",
        "我的胎压是多少",
        "车里真冷，调下温度",
        "车窗透透气",
        "打开天窗",
    ],
)
@pytest.mark.asyncio
async def test_volvo_rule_only_keeps_latest_false_simple_cases_complex(
    query: str,
) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        project="Volvo",
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source in {"parser_veto", "default_complex"}


@pytest.mark.parametrize(
    "query",
    [
        "最后一个",
        "添加服务区为途经点",
        "添加加油站为途经点",
        "添加xxx为常用地点",
        "到下个途经点有多远",
        "到途经点蓝天幼儿园有多远",
        "我要给你洗澡了",
        "给你洗好澡了",
    ],
)
@pytest.mark.asyncio
async def test_volvo_rule_only_covers_latest_false_complex_simple_cases(
    query: str,
) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        project="Volvo",
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "simple"
    assert decision.source == "parser_simple"


@pytest.mark.parametrize(
    "query",
    [
        "看看外面的空气怎么样？帮我设置一下空调",
        "氛围灯随大灯开启",
        "让灯光跟着音乐的节奏闪动",
        "明天适合旅游吗？",
        "播放我喜欢的男偶像的音乐我的偶像们有没有合唱的歌，帮我找一首听听",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_keeps_risk_boundary_cases_complex(query: str) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source in {"parser_veto", "default_complex"}


@pytest.mark.parametrize(
    "query",
    [
        "导航去合肥政务中心，途经合肥市中医院",
        "找合肥逍遥津公园 2 公里范围内评分 4.5 以上、环境好的西餐厅",
        "去合肥南站接乘坐G3159次高铁的亲戚，规划到合肥南站对应列车出站口的接站路线",
        "帮我查下合肥银泰中心的营业时间和地址",
        "车没油了，找最近的加油站，越快越好",
        "我要去北京出差，帮我规划一下路线并查找一下附近的酒店，再查一下北京的天气。",
        "上班路上买杯咖啡，再放点我喜欢的音乐",
        "车子出现故障，搜我周边的汽修店，全程沿着北二环路行驶",
        "今天不上班，带我去打篮球避开高峰路段，去常去额篮球场",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_keeps_byd_navigation_complex_boundary_cases_complex(
    query: str,
) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source in {"parser_veto", "default_complex"}


@pytest.mark.parametrize(
    "query",
    [
        "上班路上给我买一杯瑞幸的拿铁咖啡，再播放周杰伦的《青花瓷》",
        "我车现在电量还有 80%，能开到浦东机场，直接带我去浦东机场 T2 航站楼",
        "电量还剩10km，带我去合肥第八人民医院",
        "车子故障搜我附近的途虎养车汽修门店，我现在很难受",
        "我现在从合肥南站落地，去包河绿地中心，我想把车开到人堆",
        "突然肚子疼。查下周边医院接诊时间，再看下路程和预计时长",
        "带我去紫蓬山森林公园，想早点到达，但是一路上不想等红绿灯",
        "帮我查下那条带彩虹的路建成时间，就是我以前经常路过的那条网红路",
        "合肥罍街好玩吗，在哪天路上面，我想开车冲进去",
        "我现在在哪里",
        "你帮我搜索一下附近有没有健身房",
        "请你先用四川话帮我讲一个段子，然后再用林黛玉的语气帮我播报一下今天的天气，然后呢？再给我唱一首我只在乎你",
        "给我唱一首《爱心便利贴》",
        "车内温度现在多少，室外温度是多少",
        "自动大灯开了吗，自动驻车是什么状态",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_keeps_remaining_byd_false_simple_cases_complex(
    query: str,
) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source in {"parser_veto", "default_complex"}


@pytest.mark.parametrize(
    "query",
    [
        "主驾座椅加热开了吗，档位是多少",
        "副驾座椅加热开了吗，没开的话开到1档",
        "后排空调开了吗，没开打开下",
        "马上经过隧道了，大灯要开吗，开近光还是远光",
        "胎压正常不？有问题的话赶紧提醒我，直接去打气",
        "外面晒不晒，看看要不要提起打开遮阳帘",
        "雨刮现在是几档，自动模式开了吗",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_keeps_question_and_conditional_control_complex(
    query: str,
) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source in {"parser_veto", "default_complex"}


@pytest.mark.parametrize(
    "query",
    [
        "把氛围灯调成蓝色然后座椅加热也开一下",
        "冻死了，给我调个暖气，窗户也得赶紧关上",
        "车窗关上，暖气给我调成最大",
        "调一下空调风量和吹风模式",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_keeps_weak_connector_multi_capability_complex(
    query: str,
) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source in {"parser_veto", "default_complex"}


@pytest.mark.parametrize(
    "query",
    [
        "车里空气不流通，帮我调下",
        "空气潮湿闷热",
        "玻璃上哈气了帮我处理下",
        "前挡玻璃上哈气了帮我处理下",
        "驾驶员手都够不到方向盘了",
        "座椅太靠后了",
        "后视镜都快要碰到旁边的墙了",
        "后排坐的老人，座椅调整下",
        "后视镜加热与温度联动",
        "我快到隧道了，帮我开后视镜加热",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_keeps_broad_vehicle_target_descriptions_complex(
    query: str,
) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source in {"parser_veto", "default_complex"}


@pytest.mark.parametrize(
    "query",
    [
        "外面现在刮风吗？",
        "车窗起雾了，除雾",
        "打开除霜除雾",
        "打开前除霜",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_keeps_weather_and_explicit_defog_simple(query: str) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "simple"
    assert decision.source == "parser_simple"


@pytest.mark.parametrize(
    "query",
    [
        "后窗除霜关掉",
        "前除霜加热丝开启",
        "切换到近光",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_parses_specific_defog_and_light_aliases(query: str) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "simple"
    assert decision.source == "parser_simple"


@pytest.mark.parametrize(
    "query",
    [
        "打开后视镜自动折叠",
        "后视镜自动折叠打开",
        "调亮后视镜",
        "后视镜调到最亮",
        "展开后视镜",
        "后视镜加热",
        "下雨了，后视镜加热",
        "展开主驾座椅",
        "座椅便利进出打开",
        "打开座椅Auto",
        "后排座椅一键放倒",
        "副驾座椅切换到女王座模式",
        "打开主驾座椅智能温控",
        "风大一些",
        "主驾风大一些",
        "出风不要太猛",
        "激活水平扫风模式",
        "厦门今天的风力有几级？",
        "现在外面的能见度怎么样？",
        "明天会不会刮大风？",
        "空气悬架阻尼调到舒适",
        "空气悬挂高度上升一点",
        "打开后面的玻璃",
        "我感觉有点燥热",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_parses_dedicated_vehicle_recovery_cards(query: str) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "simple"
    assert decision.source == "parser_simple"


@pytest.mark.parametrize(
    "query",
    [
        "去合肥南站",
        "带我去北京市朝阳区三里屯太古里",
        "前往包河万达广场",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_leaves_open_destination_navigation_to_fallback(query: str) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source == "default_complex"


@pytest.mark.parametrize(
    "query",
    [
        "开始导航",
        "发起导航",
        "继续导航",
        "结束导航",
        "关闭导航",
        "导航去",
        "导航到",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_keeps_navigation_session_controls_simple(query: str) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "simple"
    assert decision.source == "parser_simple"


@pytest.mark.parametrize(
    "query",
    [
        "导航去合肥政务中心，途经合肥市中医院",
        "导航找个附近修轮胎的地方",
        "开车去滁州出差",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_routes_open_navigation_away_from_parser_veto(query: str) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source == "default_complex"
    assert "parser:navigation_open_target_to_llm" in decision.trace.decision_path


@pytest.mark.asyncio
async def test_navigation_open_target_uses_llm_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_llm(query: str, *, history=None, prompt=None):
        assert query == "导航去合肥南站"
        assert prompt
        return "simple"

    monkeypatch.setattr(router_engine, "llm_fallback", fake_llm)

    decision = await arbitrate_simple_complex_decision(
        "导航去合肥南站",
        use_exact_match=False,
        use_llm_fallback=True,
    )

    assert decision.label == "simple"
    assert decision.source == "llm_simple"
    assert "parser:navigation_open_target_to_llm" in decision.trace.decision_path


@pytest.mark.parametrize(
    "query",
    [
        "我要导航",
        "我要导航去东方明珠",
        "附近有快充桩的充电站",
        "把路线设为高速优先",
    ],
)
@pytest.mark.asyncio
async def test_sgm_rule_only_parses_single_navigation_requests(query: str) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        project="SGM",
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "simple"
    assert decision.source == "parser_simple"


@pytest.mark.parametrize(
    "query",
    [
        "导航回家，回去之前要买个面包，还要去必胜客给孩子买他最喜欢吃的披萨",
        "我要回家，回家之前要先充个电，还要在路上的KFC买个疯狂星期四",
    ],
)
@pytest.mark.asyncio
async def test_sgm_rule_only_keeps_pre_navigation_errands_complex(query: str) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        project="SGM",
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source in {"parser_veto", "default_complex"}


@pytest.mark.parametrize(
    "query",
    [
        "设置家庭地址",
        "把公司地址改为该酒店",
        "沿途找一下充电站",
        "附近有没有酒店",
        "帮我查附近酒店",
        "看看附近有没有酒店",
        "附近有没有希尔顿酒店",
        "查一下附近的 1 公里以内的停车场",
        "查询广州塔附近餐厅",
        "查一下天安门附近的停车场",
        "查找广场边停车场",
        "家附近的停车场",
        "沿途会经过多少个红绿灯",
        "查看全程",
        "查询前方拥堵情况",
        "深南大道堵吗",
        "我在哪里",
        "目的地是哪里",
        "打开柱状视图",
        "把和平饭店设为顺路点",
        "把 50 米以内加油站添加到收藏夹",
    ],
)
@pytest.mark.asyncio
async def test_sgm_rule_only_parses_navigation_risk_words_when_consumed(
    query: str,
) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        project="SGM",
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "simple"
    assert decision.source == "parser_simple"


@pytest.mark.parametrize(
    "query",
    [
        "附近哪里有加油站",
        "推荐附近篮球场",
        "帮我找鸟巢旁边的停车场",
        "找个在双子塔附近能吃海鲜的大排档",
    ],
)
@pytest.mark.asyncio
async def test_sgm_rule_only_keeps_open_scoped_poi_selection_complex(
    query: str,
) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        project="SGM",
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source in {"parser_veto", "default_complex"}


@pytest.mark.parametrize(
    "query",
    [
        "帮我找个在鸟巢旁边能带孩子玩的公园",
        "导航到小蛮腰下面适合拍夜景的打卡点",
        "我想去海边的加油站",
    ],
)
@pytest.mark.asyncio
async def test_sgm_rule_only_keeps_open_navigation_selection_complex(
    query: str,
) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        project="SGM",
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source in {"parser_veto", "default_complex"}


@pytest.mark.asyncio
async def test_engine_routes_card_configured_fallback_intent_to_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_llm(query: str, *, history=None, prompt=None):
        assert query == "开车去滁州出差"
        assert prompt
        return "complex"

    monkeypatch.setattr(router_engine, "llm_fallback", fake_llm)

    decision = await arbitrate_simple_complex_decision(
        "开车去滁州出差",
        use_exact_match=False,
        use_llm_fallback=True,
    )

    assert decision.label == "complex"
    assert decision.source == "llm_complex"
    assert "parser:navigation_open_target_to_llm" in decision.trace.decision_path


@pytest.mark.asyncio
async def test_media_fallback_card_overrides_cross_executor_parser_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_llm(query: str, *, history=None, prompt=None):
        assert query == "打开主驾屏幕上的QQ音乐"
        assert prompt
        return "complex"

    monkeypatch.setattr(router_engine, "llm_fallback", fake_llm)

    decision = await arbitrate_simple_complex_decision(
        "打开主驾屏幕上的QQ音乐",
        use_exact_match=False,
        use_llm_fallback=True,
    )

    assert decision.label == "complex"
    assert decision.source == "llm_complex"
    assert "parser:media_open_target_to_llm" in decision.trace.decision_path


@pytest.mark.parametrize(
    "query",
    [
        "特朗普现在在干什么？",
        "附近的星巴克门店几点开门？",
        "讲一个适合开车听的冷笑话",
        "推荐几首适合开车听的歌",
        "今天早高峰上海中环会堵车吗？",
    ],
)
@pytest.mark.asyncio
async def test_volvo_open_domain_queries_route_to_llm_as_simple(
    query: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str | None]] = []

    async def fake_llm(query: str, *, history=None, prompt=None):
        calls.append((query, prompt))
        return "simple"

    monkeypatch.setattr(router_engine, "llm_fallback", fake_llm)

    decision = await arbitrate_simple_complex_decision(
        query,
        project="Volvo",
        use_exact_match=False,
        use_llm_fallback=True,
    )

    assert decision.label == "simple"
    assert decision.source == "llm_simple"
    assert calls
    assert calls[0][1] is not None
    assert "联网搜索" in calls[0][1]


@pytest.mark.asyncio
async def test_volvo_open_domain_marker_keeps_mixed_control_joke_out_of_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_llm(query: str, *, history=None, prompt=None):
        assert query == "讲个笑话,空调低点"
        return "complex"

    monkeypatch.setattr(router_engine, "llm_fallback", fake_llm)

    decision = await arbitrate_simple_complex_decision(
        "讲个笑话，空调低点",
        project="Volvo",
        use_exact_match=False,
        use_llm_fallback=True,
    )

    assert decision.label == "complex"
    assert decision.source == "llm_complex"
    assert "llm_fallback:start" in decision.trace.decision_path


@pytest.mark.asyncio
async def test_volvo_rule_only_keeps_temperature_plus_errand_complex() -> None:
    decision = await arbitrate_simple_complex_decision(
        "现在好热，调低空调，出发去找个全家买冰淇凌",
        project="Volvo",
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source in {"parser_veto", "default_complex"}


@pytest.mark.asyncio
async def test_volume_card_does_not_absorb_open_media_quality_target() -> None:
    decision = await arbitrate_simple_complex_decision(
        "我要调高音质",
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source == "default_complex"
    assert "parser:media_open_target_to_llm" in decision.trace.decision_path


@pytest.mark.parametrize(
    "query",
    [
        "最近有点累了，想去打打篮球放松一下",
        "推荐附近篮球场",
        "讲个睡前故事",
        "唱一首歌",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_does_not_keep_removed_open_domain_and_chat_as_simple(
    query: str,
) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "complex"
    assert decision.source in {"parser_veto", "default_complex"}


@pytest.mark.parametrize(
    "query",
    [
        "中控屏亮一点",
        "切换主题",
        "启动录音",
        "香氛切换到云栖雪松",
        "切换时间格式",
        "我要把语音包换成广东方言",
        "HUD向左移动一点",
        "转向补盲切换到HUD",
        "启动自动泊入",
        "腿托向上调节",
        "解锁后排儿童锁",
        "启动热点",
        "看看小计里程",
        "打开自动驻车",
        "关闭自动驻车功能",
    ],
)
@pytest.mark.asyncio
async def test_rule_only_parses_batch_a_vehicle_and_system_cards(query: str) -> None:
    decision = await arbitrate_simple_complex_decision(
        query,
        use_exact_match=False,
        use_llm_fallback=False,
    )

    assert decision.label == "simple"
    assert decision.source == "parser_simple"


@pytest.mark.parametrize(
    ("query", "capability_id"),
    [
        ("声场模式调节为全车平衡", "media.sound_field.set"),
        ("打开4D音效", "media.sound_effect.set"),
        ("连接一下那个wifi", "system.network.set"),
        ("显示一下那个无线密码", "system.network.status"),
        ("帮我打开急速降温", "climate.quick_cooling.set"),
        ("快打开HDC", "vehicle.hdc.set"),
        ("打开负离子", "vehicle.air_quality.set"),
        ("看看当前的胎压是多少", "vehicle.status.query"),
    ],
)
@pytest.mark.asyncio
async def test_benz_rule_only_parses_closed_executable_profile_cards(
    query: str,
    capability_id: str,
) -> None:
    with use_router_asset_dir(
        Path("projects/sgm_prod/classification/assets/benz")
    ):
        decision = await arbitrate_simple_complex_decision(
            query,
            use_exact_match=False,
            use_llm_fallback=False,
        )

    assert decision.label == "simple"
    assert decision.source == "parser_simple"
    assert decision.trace.matched_candidates[0].capability_id == capability_id


@pytest.mark.parametrize(
    "query",
    [
        "车里有点臭",
        "我看不见了",
        "屁股太凉了",
        "太吵了",
        "打开氛围灯，让它随着音乐节奏动",
        "空调吹脚和吹窗",
        "把大灯高度调到比较高的位置",
        "打开后位置灯，让它随着日行灯一块儿点亮",
        "开始休憩",
        "车子起雾了",
    ],
)
@pytest.mark.asyncio
async def test_benz_rule_only_parses_hardcoded_review_cases(query: str) -> None:
    with use_router_asset_dir(
        Path("projects/sgm_prod/classification/assets/benz")
    ):
        decision = await arbitrate_simple_complex_decision(
            query,
            use_exact_match=False,
            use_llm_fallback=False,
        )

    assert decision.label == "simple"
    assert decision.source == "parser_simple"
    assert decision.trace.matched_candidates[0].capability_id == "benz.review_cases.simple"


@pytest.mark.asyncio
async def test_legacy_tuple_api_still_works() -> None:
    label, source = await arbitrate_simple_complex("把空调调到23度")

    assert label == "simple"
    assert source in {"exact_simple", "parser_simple"}


@pytest.mark.asyncio
async def test_asset_evaluation_requires_exact_source(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_decision(query: str) -> RouterDecision:
        return RouterDecision(
            label="simple",
            source="parser_simple",
            trace=RouterTrace(
                project="default",
                query=query,
                normalized_query=query,
                decision_path=["parser:complete"],
                rule_version="router_rules_test",
            ),
        )

    monkeypatch.setattr(evaluate_router_assets, "arbitrate_simple_complex_decision", fake_decision)
    source_counts, failures = await evaluate_router_assets._evaluate(
        [
            evaluate_router_assets.Case(
                path=Path("data/simple.csv"),
                line_number=2,
                query="打开主驾车窗",
                expected_label="simple",
                asset_source="fixture",
            )
        ]
    )

    assert source_counts["parser_simple"] == 1
    assert failures[0].failure_type == "non_exact_source"


def test_rule_evaluation_filters_cases_by_domain(tmp_path: Path) -> None:
    asset_dir = tmp_path / "assets"
    data_dir = asset_dir / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "simple.csv").write_text(
        (
            "query,label,source,domain\n"
            "打开车窗,simple,车控,BYD\n"
            "把空调调到23度,simple,简单RAG,BENZ\n"
        ),
        encoding="utf-8",
    )
    (data_dir / "complex.csv").write_text(
        (
            "query,label,source,domain\n"
            "打开空调再开窗,complex,车控,BYD\n"
            "主驾24度副驾25度,complex,复杂RAG,BENZ\n"
        ),
        encoding="utf-8",
    )

    assert [
        case["query"] for case in evaluate_router_rules._load_cases(asset_dir, "byd")
    ] == ["打开车窗", "打开空调再开窗"]
    assert [
        case["query"] for case in evaluate_router_rules._load_cases(asset_dir, "benz")
    ] == ["把空调调到23度", "主驾24度副驾25度"]
    assert len(evaluate_router_rules._load_cases(asset_dir, "all")) == 4


def test_e2e_llm_parse_args_accepts_report_txt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_router_e2e_llm",
            "--asset-dir",
            "projects/sgm_prod/classification/assets",
            "--report-txt",
            "projects/sgm_prod/classification/reports/e2e_llm_report.txt",
        ],
    )

    args = evaluate_router_e2e_llm._parse_args()

    assert args.report_txt == Path("projects/sgm_prod/classification/reports/e2e_llm_report.txt")


def test_e2e_llm_report_txt_excludes_failure_examples(tmp_path: Path) -> None:
    results = [
        evaluate_router_e2e_llm.EvalResult(
            case=evaluate_router_e2e_llm.Case(
                path=Path("data/simple.csv"),
                line_number=2,
                query="打开主驾车窗",
                expected_label="simple",
                asset_source="车控",
                domain="BYD",
            ),
            actual_label="simple",
            decision_source="parser_simple",
            correct=True,
            latency_ms=10.0,
            llm_routed=False,
            decision_path="parser:complete",
            normalized_query="打开主驾车窗",
            top_candidate_id="vehicle.window.set",
            top_missing_slots="",
            top_risk_flags="",
            top_unconsumed_text="",
        ),
        evaluate_router_e2e_llm.EvalResult(
            case=evaluate_router_e2e_llm.Case(
                path=Path("data/complex.csv"),
                line_number=2,
                query="打开空调再开窗",
                expected_label="complex",
                asset_source="复杂query",
                domain="BYD",
            ),
            actual_label="simple",
            decision_source="llm_simple",
            correct=False,
            latency_ms=120.0,
            llm_routed=True,
            decision_path="parser:veto -> llm_fallback:start -> llm_fallback:simple",
            normalized_query="打开空调再开窗",
            top_candidate_id="vehicle.window.set",
            top_missing_slots="",
            top_risk_flags="multi_action",
            top_unconsumed_text="再开窗",
        ),
    ]
    report_path = tmp_path / "reports" / "e2e_llm_report.txt"

    evaluate_router_e2e_llm._write_report_txt(
        report_path,
        results=results,
        domain_filter="all",
        artifact_rows=[
            ["report_txt", report_path],
            ["output_csv", Path("reports/predictions.csv")],
        ],
    )

    report_text = report_path.read_text(encoding="utf-8")
    assert "E2E Router Evaluation" in report_text
    assert "Overall Metrics" in report_text
    assert "false_simple" in report_text
    assert "By Domain" in report_text
    assert "By Asset Source" in report_text
    assert "Artifacts" in report_text
    assert "report_txt" in report_text
    assert str(report_path) in report_text
    assert "reports/predictions.csv" in report_text
    assert "First " not in report_text
    assert "打开空调再开窗" not in report_text



RULE_ONLY_CASES: list[dict[str, str]] = [
    {
        "name": "简单车控",
        "query": "把空调调到23度",
    },
    {
        "name": "简单系统控制",
        "query": "中控屏亮一点",
    },
    {
        "name": "多能力复杂",
        "query": "打开空调，关闭所有车窗",
    },
    {
        "name": "开放域默认复杂",
        "query": "讲个睡前故事",
    },
]


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "-"


def _print_rule_only_decision(idx: int, case: dict[str, str], decision: RouterDecision) -> None:
    print(f"[CASE {idx}] {case['name']}")
    print(f"  query: {case['query']}")
    print(f"  label/source: {decision.label}/{decision.source}")
    print(f"  normalized: {decision.trace.normalized_query}")
    print(f"  decision_path: {' -> '.join(decision.trace.decision_path)}")
    if decision.trace.risk_flags:
        print(f"  trace_risks: {_format_list(decision.trace.risk_flags)}")
    if not decision.trace.matched_candidates:
        print("  candidates: -")
        return

    print("  candidates:")
    for candidate in decision.trace.matched_candidates:
        print(
            "    "
            f"- {candidate.capability_id} "
            f"confidence={candidate.confidence:.2f} "
            f"missing={_format_list(candidate.missing_slots)} "
            f"risks={_format_list(candidate.risk_flags)} "
            f"unconsumed={candidate.unconsumed_text or '-'} "
            f"covered={candidate.covered_text or '-'}"
        )


async def run_rule_only_cases(cases: list[dict[str, str]]) -> None:
    print("rule_only: use_exact_match=False, use_llm_fallback=False")
    for idx, case in enumerate(cases, start=1):
        decision = await arbitrate_simple_complex_decision(
            case["query"],
            use_exact_match=False,
            use_llm_fallback=False,
        )
        _print_rule_only_decision(idx, case, decision)


def main() -> None:
    queries = sys.argv[1:]
    cases = (
        [{"name": f"手动输入 {idx}", "query": query} for idx, query in enumerate(queries, start=1)]
        if queries
        else RULE_ONLY_CASES
    )
    asyncio.run(run_rule_only_cases(cases))


if __name__ == "__main__":
    main()
