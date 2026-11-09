from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from projects.sgm_prod.classification import assets as router_assets
from projects.sgm_prod.classification.assets import (
    load_llm_classification_prompt,
    load_router_assets,
)
from projects.sgm_prod.classification.models import (
    CapabilityCard,
    ParseCandidate,
    ParserRules,
    RouterDecision,
    RouterTrace,
)
from projects.sgm_prod.classification.normalize import normalize_query


def _write_temp_assets(
    asset_dir: Path,
    *,
    capability_yaml: str | None = None,
    lexicon_yaml: str | None = None,
    risks_yaml: str | None = None,
    simple_csv: str | None = None,
    complex_csv: str | None = None,
    prompt_py: str | None = None,
) -> None:
    asset_dir.mkdir(parents=True)
    capability_dir = asset_dir / "capabilities"
    capability_dir.mkdir()
    rules_dir = asset_dir / "rules"
    rules_dir.mkdir()
    data_dir = asset_dir / "data"
    data_dir.mkdir()
    prompt_dir = asset_dir / "llm_classfication"
    prompt_dir.mkdir()
    (capability_dir / "vehicle_control.yaml").write_text(
        capability_yaml
        or """
executor: 端侧车控
capabilities:
  - id: vehicle.window.set
    name: 车窗控制
""".lstrip(),
        encoding="utf-8",
    )
    (rules_dir / "lexicon.yaml").write_text(
        lexicon_yaml
        or """
entries:
  - slot: target
    canonical: 车窗
    aliases: [车窗]
""".lstrip(),
        encoding="utf-8",
    )
    (rules_dir / "global_risks.yaml").write_text(
        risks_yaml
        or """
risks:
  - risk_id: multi_capability_connector
    patterns: [和]
""".lstrip(),
        encoding="utf-8",
    )
    (data_dir / "simple.csv").write_text(
        simple_csv
        or "query,label,source,domain\n打开车窗,simple,test,BENZ\n",
        encoding="utf-8",
    )
    (data_dir / "complex.csv").write_text(
        complex_csv
        or "query,label,source,domain\n关闭车窗和天窗,complex,test,BENZ\n",
        encoding="utf-8",
    )
    (prompt_dir / "prompt.py").write_text(
        prompt_py
        or 'SYSTEM_PROMPT = "default profile prompt marker"\n',
        encoding="utf-8",
    )


def _load_temp_assets_expect_error(
    asset_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    match: str,
) -> None:
    monkeypatch.setattr(router_assets, "_ASSET_DIR", asset_dir)
    load_router_assets.cache_clear()
    try:
        with pytest.raises(ValueError, match=match):
            load_router_assets()
    finally:
        load_router_assets.cache_clear()


def test_router_decision_keeps_label_source_and_trace() -> None:
    trace = RouterTrace(
        project="default",
        query="关闭所有车窗和天窗",
        normalized_query="关闭所有车窗和天窗",
        decision_path=["exact_complex:not_hit", "parser:partial_match"],
        risk_flags=["multi_capability_connector"],
        matched_candidates=[
            ParseCandidate(
                capability_id="vehicle.window.set",
                covered_text="关闭所有车窗",
                unconsumed_text="和天窗",
                missing_slots=[],
                risk_flags=["multi_capability_connector"],
                confidence=0.7,
            )
        ],
        rule_version="router_rules_test",
    )
    decision = RouterDecision(label="complex", source="parser_veto", trace=trace)

    assert decision.label == "complex"
    assert decision.source == "parser_veto"
    assert decision.trace.matched_candidates[0].capability_id == "vehicle.window.set"


def test_capability_card_uses_minimal_short_schema_with_chinese_descriptions() -> None:
    card = CapabilityCard(
        id="vehicle.window.set",
        name="车窗控制",
        executor="端侧车控",
        required_slots=["action", "target"],
        route_policy="llm_fallback",
        intent_markers=["打开车窗"],
    )

    assert card.id == "vehicle.window.set"
    assert card.route_policy == "llm_fallback"
    assert card.intent_markers == ["打开车窗"]
    assert "能力项唯一ID" in CapabilityCard.model_fields["id"].description
    assert "具体执行工具" in CapabilityCard.model_fields["executor"].description
    assert "目标白名单" in CapabilityCard.model_fields["targets"].description
    assert "动作白名单" in CapabilityCard.model_fields["actions"].description
    assert "路由策略" in CapabilityCard.model_fields["route_policy"].description


def test_parser_rules_uses_config_schema_with_chinese_descriptions() -> None:
    rules = ParserRules(
        harmless_fillers=["请"],
        generic_value_patterns=[r"\d+度"],
        broad_target_canonicals=["灯光"],
        query_like_capabilities=["open_domain.weather.query"],
        question_or_condition_markers=["吗"],
        conditional_markers=["如果"],
        scenario_capability_aux={"vehicle.light.set": ["大雾"]},
        scenario_friendly_risks=["emotion_scene"],
    )

    assert rules.harmless_fillers == ["请"]
    assert "残留文本" in ParserRules.model_fields["harmless_fillers"].description
    assert "疑问" in ParserRules.model_fields["question_or_condition_markers"].description


@pytest.mark.parametrize(
    "legacy_field",
    [
        "capability_id",
        "owner",
        "max_actions",
        "max_capabilities",
        "default_route",
        "optional_slots",
        "allowed_targets",
        "allowed_actions",
        "allow_free_text",
        "free_text_target",
        "positive_cases",
        "negative_boundary_cases",
    ],
)
def test_capability_card_rejects_legacy_fields(legacy_field: str) -> None:
    with pytest.raises(ValidationError):
        CapabilityCard(
            id="vehicle.window.set",
            name="车窗控制",
            executor="端侧车控",
            **{legacy_field: "legacy"},
        )


def test_normalize_query_unifies_punctuation_space_and_digits() -> None:
    assert normalize_query(" 把空调调到２３度。 ") == "把空调调到23度"
    assert normalize_query(" A.B（C） ") == "ABC"


def test_load_router_assets_reads_cases_and_cards() -> None:
    assets = load_router_assets()

    assert assets.rule_version == "router_rules_navigation_llm_fallback"
    assert "把空调调到23度" in assets.simple_queries
    assert "关闭所有车窗和天窗" in assets.complex_queries
    assert "vehicle.window.set" in assets.capabilities
    assert assets.capabilities["vehicle.window.set"].id == "vehicle.window.set"
    assert any(entry.canonical == "车窗" for entry in assets.lexicon)
    assert any(rule.risk_id == "multi_capability_connector" for rule in assets.risks)
    assert "吗" in assets.parser_rules.question_or_condition_markers
    assert assets.capabilities["navigation.route.preference"].route_policy == "llm_fallback"
    assert "导航" in assets.capabilities["navigation.route.preference"].intent_markers


def test_load_llm_classification_prompt_reads_asset_prompt_py() -> None:
    prompt = load_llm_classification_prompt()

    assert "智能座舱助手的 Router 判定器" in prompt
    assert "只输出 JSON" in prompt


def test_load_router_profiles_reads_complete_project_profiles(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    _write_temp_assets(
        asset_root / "default",
        simple_csv="query,label,source,domain\n默认样本,simple,test,default\n",
        prompt_py='SYSTEM_PROMPT = "default prompt marker"\n',
    )
    _write_temp_assets(
        asset_root / "SGM",
        simple_csv="query,label,source,domain\nSGM样本,simple,test,SGM\n",
        prompt_py='SYSTEM_PROMPT = "sgm prompt marker"\n',
    )

    registry = router_assets.load_router_profiles(asset_root)

    assert set(registry.profiles) == {"default", "SGM"}
    assert registry.get("default").project == "default"
    assert registry.get("SGM").project == "SGM"
    assert "默认样本" in registry.get("default").simple_queries
    assert "SGM样本" in registry.get("SGM").simple_queries
    assert "vehicle.window.set" in registry.get("SGM").capabilities
    assert router_assets.get_router_assets("SGM", asset_root=asset_root).project == "SGM"


def test_baic_reuses_sgm_profile_but_preserves_project_in_trace_assets(
    tmp_path: Path,
) -> None:
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    _write_temp_assets(asset_root / "default")
    _write_temp_assets(
        asset_root / "SGM",
        simple_csv="query,label,source,domain\nSGM样本,simple,test,SGM\n",
        prompt_py='SYSTEM_PROMPT = "sgm prompt marker"\n',
    )

    assets = router_assets.get_router_assets("baic", asset_root=asset_root)

    assert assets.project == "baic"
    assert "SGM样本" in assets.simple_queries
    assert assets.llm_prompts["default"].system_prompt == "sgm prompt marker"


def test_get_router_assets_rejects_unknown_project(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    _write_temp_assets(asset_root / "default")

    with pytest.raises(ValueError, match="unknown router project: SGM"):
        router_assets.get_router_assets("SGM", asset_root=asset_root)


def test_llm_prompt_loader_reads_prompt_directory_as_assets(tmp_path: Path) -> None:
    asset_dir = tmp_path / "assets" / "SGM"
    _write_temp_assets(
        asset_dir,
        prompt_py='SYSTEM_PROMPT = "sgm directory prompt marker"\n',
    )

    assets = router_assets.load_router_assets_from_dir("SGM", asset_dir)

    assert assets.llm_prompts["default"].id == "default"
    assert assets.llm_prompts["default"].system_prompt == "sgm directory prompt marker"


def test_sgm_llm_prompt_separates_media_control_from_content_selection() -> None:
    asset_dir = Path("projects/sgm_prod/classification/assets/SGM")
    prompt = router_assets.load_router_assets_from_dir("SGM", asset_dir).llm_prompts[
        "default"
    ].system_prompt

    assert "播放音乐、播放歌曲、打开电台、开启电台、启动电台" in prompt
    assert "这些不是让系统选歌或推荐内容" in prompt
    assert "明确语种、年代、曲风、榜单、歌手或歌曲时仍按 simple" in prompt
    assert "只有没有明确内容目标的来点/放点/找一首才按 complex" in prompt
    assert "顺路/沿途补能或服务区查询本身不是 complex" in prompt


def test_sgm_llm_prompt_documents_music_fallback_tie_breakers() -> None:
    asset_dir = Path("projects/sgm_prod/classification/assets/SGM")
    prompt = router_assets.load_router_assets_from_dir("SGM", asset_dir).llm_prompts[
        "default"
    ].system_prompt

    assert "单一语种、年代、曲风/流派" in prompt
    assert "来点/放点/换一首后面带单一明确目标时仍按 simple" in prompt
    assert "影视/游戏/作品名 + 主题曲/片头曲/片尾曲/插曲/原声" in prompt
    assert "Live/现场/翻唱/清唱、无损/高清/环绕音质" in prompt
    assert "专辑里的某首、第几首、主打歌" in prompt
    assert "QQ音乐里的/蓝牙里的/中控屏QQ音乐播放 + 具体歌手、专辑、榜单或曲风" in prompt
    assert "普通播放列表、收藏、订阅、历史、歌词、当前播放状态仍按 simple" in prompt


def test_sgm_llm_prompt_documents_navigation_fallback_tie_breakers() -> None:
    asset_dir = Path("projects/sgm_prod/classification/assets/SGM")
    prompt = router_assets.load_router_assets_from_dir("SGM", asset_dir).llm_prompts[
        "default"
    ].system_prompt

    assert "两个以内明确目的地/途经点/顺路地点仍按 simple" in prompt
    assert "路线偏好叠加单一明确目的地仍按 simple" in prompt
    assert "补能点、途经点、收藏地址、导航历史、路况和路径信息的直接管理或查询仍按 simple" in prompt
    assert "规划一个充电站、找一个充电站、添加一个充电站规划、规划就近充电站仍按 simple" in prompt
    assert "刷新导航、刷新路径、进入设置界面、缩放地图、简洁语音、当前位置查询仍按 simple" in prompt
    assert "轻量范围 POI 查询仍按 simple" in prompt
    assert "附近酒店、周边商场、天安门附近停车、家周边肯德基、沿途 ATM、沿途找吃的仍按 simple" in prompt
    assert "公司附近充电枪、沿途充电点、附近快充充电站仍按 simple" in prompt
    assert "哪里、哪个、推荐、评分、人少、营业、适合、能、旁边、下面" in prompt
    assert "途经点/途径点/顺路点的新增、修改、删除、查询仍按 simple" in prompt
    assert "到开放地点的距离、时长、怎么走、是否畅通仍按 simple" in prompt
    assert "沿途服务区/收费站/红绿灯数量、限速、路况、到达时间仍按 simple" in prompt
    assert "将东方明珠换成杭州、删除全部、看还有多远到、帮我查到思必驰距离仍按 simple" in prompt
    assert "那边、那个、那里" in prompt
    assert "坐高铁的火车站" in prompt
    assert "能看烟花、能滑雪、能吃火锅、出片率高、圆圆的湖" in prompt


def test_volvo_llm_prompt_documents_open_domain_search_policy() -> None:
    asset_dir = Path("projects/sgm_prod/classification/assets/Volvo")
    prompt = router_assets.load_router_assets_from_dir("Volvo", asset_dir).llm_prompts[
        "default"
    ].system_prompt

    assert "联网搜索" in prompt
    assert "必须判 simple" in prompt
    assert "特朗普现在在干什么" in prompt
    assert "附近的星巴克门店几点开门" in prompt
    assert "推荐几首适合开车听的歌" in prompt
    assert "找个适合带娃野餐的公园" in prompt
    assert "点个到公司的星巴克拿铁" in prompt


def test_load_router_assets_reads_rules_and_data_subdirectories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_dir = tmp_path / "assets"
    capability_dir = asset_dir / "capabilities"
    rules_dir = asset_dir / "rules"
    data_dir = asset_dir / "data"
    prompt_dir = asset_dir / "llm_classfication"
    capability_dir.mkdir(parents=True)
    rules_dir.mkdir()
    data_dir.mkdir()
    prompt_dir.mkdir()

    (capability_dir / "vehicle_control.yaml").write_text(
        """
executor: 端侧车控
capabilities:
  - id: vehicle.window.set
    name: 车窗控制
""".lstrip(),
        encoding="utf-8",
    )
    (rules_dir / "lexicon.yaml").write_text(
        """
entries:
  - slot: target
    canonical: 车窗
    aliases: [车窗]
""".lstrip(),
        encoding="utf-8",
    )
    (rules_dir / "global_risks.yaml").write_text(
        """
risks:
  - risk_id: multi_capability_connector
    patterns: [和]
""".lstrip(),
        encoding="utf-8",
    )
    (data_dir / "simple.csv").write_text(
        "query,label,source,domain\n打开车窗,simple,test,BENZ\n",
        encoding="utf-8",
    )
    (data_dir / "complex.csv").write_text(
        "query,label,source,domain\n关闭车窗和天窗,complex,test,BENZ\n",
        encoding="utf-8",
    )
    (prompt_dir / "prompt.py").write_text(
        'SYSTEM_PROMPT = "temp prompt marker"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(router_assets, "_ASSET_DIR", asset_dir)
    load_router_assets.cache_clear()
    try:
        assets = load_router_assets()
    finally:
        load_router_assets.cache_clear()

    assert "打开车窗" in assets.simple_queries
    assert "关闭车窗和天窗" in assets.complex_queries
    assert any(entry.canonical == "车窗" for entry in assets.lexicon)
    assert any(rule.risk_id == "multi_capability_connector" for rule in assets.risks)


def test_use_router_asset_dir_temporarily_switches_loaded_assets(
    tmp_path: Path,
) -> None:
    from projects.sgm_prod.classification.tools._asset_dir import use_router_asset_dir

    asset_dir = tmp_path / "assets"
    _write_temp_assets(
        asset_dir,
        simple_csv="query,label,source,domain\n临时资产样本,simple,test,BENZ\n",
    )
    original_asset_dir = router_assets._ASSET_DIR

    with use_router_asset_dir(asset_dir):
        assets = load_router_assets()
        assert "临时资产样本" in assets.simple_queries

    assert router_assets._ASSET_DIR == original_asset_dir


def test_build_router_assets_from_workbook_writes_loadable_exact_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from projects.sgm_prod.classification.tools.build_router_assets import (
        build_assets_from_workbook,
    )

    workbook = tmp_path / "Router-case-mini.xlsx"
    with pd.ExcelWriter(workbook) as writer:
        pd.DataFrame(
            [
                {
                    "query": "打开主驾车窗",
                    "input_intent": "open_driver_window",
                }
            ]
        ).to_excel(writer, sheet_name="端侧直接执行", index=False)
        pd.DataFrame(
            [{"query": "把空调调到23度", "domain": "vehicle", "function": "temperature"}]
        ).to_excel(writer, sheet_name="简单RAG", index=False)
        pd.DataFrame([{"query": "小朋友在后排睡着了", "category": "scene_goal"}]).to_excel(
            writer,
            sheet_name="复杂RAG",
            index=False,
        )
        pd.DataFrame(
            [{"query": "关闭所有车窗和天窗", "category": "multi_capability_connector"}]
        ).to_excel(writer, sheet_name="复杂RAG（副本）", index=False)
        pd.DataFrame([{"query": "关闭所有车窗和天窗", "tag": "multi_turn"}]).to_excel(
            writer,
            sheet_name="多轮tag规则",
            index=False,
        )

    output_dir = tmp_path / "assets"
    build_assets_from_workbook(workbook, output_dir)

    simple_csv = (output_dir / "data" / "simple.csv").read_text(encoding="utf-8")
    complex_csv = (output_dir / "data" / "complex.csv").read_text(encoding="utf-8")
    assert "打开主驾车窗" not in simple_csv
    assert "把空调调到23度,simple,简单RAG,BENZ" in simple_csv
    assert "小朋友在后排睡着了,complex,复杂RAG,BENZ" in complex_csv
    assert "关闭所有车窗和天窗,complex,复杂RAG（副本）,BENZ" in complex_csv

    source_asset_dir = Path(router_assets.__file__).with_name("assets") / "default"
    shutil.copytree(source_asset_dir / "capabilities", output_dir / "capabilities")
    shutil.copytree(source_asset_dir / "rules", output_dir / "rules")
    shutil.copytree(source_asset_dir / "llm_classfication", output_dir / "llm_classfication")

    monkeypatch.setattr(router_assets, "_ASSET_DIR", output_dir)
    load_router_assets.cache_clear()
    try:
        assets = load_router_assets()
    finally:
        load_router_assets.cache_clear()

    assert "打开主驾车窗" not in assets.simple_queries
    assert "把空调调到23度" in assets.simple_queries
    assert "小朋友在后排睡着了" in assets.complex_queries
    assert "关闭所有车窗和天窗" in assets.complex_queries


def test_build_router_assets_filters_simple_open_chat_and_reads_v2_complex_sheets(
    tmp_path: Path,
) -> None:
    from projects.sgm_prod.classification.tools.build_router_assets import (
        build_assets_from_workbook,
    )

    workbook = tmp_path / "Router-case-v2-mini.xlsx"
    with pd.ExcelWriter(workbook) as writer:
        pd.DataFrame(
            [
                {"Query": "打开车窗", "意图领域": "简单车控", "具体功能": "车窗"},
                {"Query": "今天有什么新闻", "意图领域": "联网搜索", "具体功能": "新闻搜索"},
                {"Query": "讲个笑话", "意图领域": "S2S闲聊", "具体功能": "灵动畅聊"},
            ]
        ).to_excel(writer, sheet_name="简单RAG", index=False)
        pd.DataFrame(
            [{"Query": "如果下雨就关窗", "备注": "conditional_automation"}]
        ).to_excel(writer, sheet_name="复杂RAG(设计版)", index=False)
        pd.DataFrame(
            [{"Query": "帮我规划一天怎么玩", "备注": "open_ended_planning"}]
        ).to_excel(writer, sheet_name="复杂RAG（基准版）", index=False)

    output_dir = tmp_path / "assets"
    build_assets_from_workbook(workbook, output_dir)

    simple_csv = (output_dir / "data" / "simple.csv").read_text(encoding="utf-8")
    complex_csv = (output_dir / "data" / "complex.csv").read_text(encoding="utf-8")
    assert "打开车窗,simple,简单RAG,BENZ" in simple_csv
    assert "今天有什么新闻" not in simple_csv
    assert "讲个笑话" not in simple_csv
    assert "如果下雨就关窗,complex,复杂RAG(设计版),BENZ" in complex_csv
    assert "帮我规划一天怎么玩,complex,复杂RAG（基准版）,BENZ" in complex_csv


def test_load_router_assets_rejects_normalized_exact_conflicts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_dir = tmp_path / "assets"
    _write_temp_assets(
        asset_dir,
        simple_csv="query,label,source,domain\nA.B（C）,simple,test,BENZ\n",
        complex_csv="query,label,source,domain\nABC,complex,test,BENZ\n",
    )

    _load_temp_assets_expect_error(
        asset_dir,
        monkeypatch,
        "simple/complex exact query conflicts",
    )


def test_load_router_assets_rejects_duplicate_capability_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_dir = tmp_path / "assets"
    _write_temp_assets(
        asset_dir,
        capability_yaml="""
executor: 端侧车控
capabilities:
  - id: vehicle.window.set
    name: 车窗控制
  - id: vehicle.window.set
    name: 车窗控制
""".lstrip(),
    )

    _load_temp_assets_expect_error(asset_dir, monkeypatch, "duplicate capability_id")


@pytest.mark.parametrize(
    ("override_name", "override_value", "match"),
    [
        (
            "lexicon_yaml",
            """
entries:
  - slot: target
    canonical: 车窗
    aliases: [车窗]
  - slot: target
    canonical: 车窗
    aliases: [窗户]
""".lstrip(),
            r"duplicate lexicon entry",
        ),
        (
            "risks_yaml",
            """
risks:
  - risk_id: multi_capability_connector
    patterns: [和]
  - risk_id: multi_capability_connector
    patterns: [同时]
""".lstrip(),
            "duplicate risk_id",
        ),
    ],
)
def test_load_router_assets_rejects_duplicate_yaml_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    override_name: str,
    override_value: str,
    match: str,
) -> None:
    asset_dir = tmp_path / "assets"
    _write_temp_assets(asset_dir, **{override_name: override_value})

    _load_temp_assets_expect_error(asset_dir, monkeypatch, match)


@pytest.mark.parametrize(
    ("override_name", "override_value", "match"),
    [
        (
            "simple_csv",
            "query,label,source,domain\n打开车窗,complex,test,BENZ\n",
            "expected label simple",
        ),
        (
            "complex_csv",
            "query,label,source,domain\n关闭车窗,simple,test,BENZ\n",
            "expected label complex",
        ),
    ],
)
def test_load_router_assets_rejects_wrong_case_label(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    override_name: str,
    override_value: str,
    match: str,
) -> None:
    asset_dir = tmp_path / "assets"
    _write_temp_assets(asset_dir, **{override_name: override_value})

    _load_temp_assets_expect_error(asset_dir, monkeypatch, match)


def test_load_router_assets_allows_same_label_duplicate_normalized_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_dir = tmp_path / "assets"
    _write_temp_assets(
        asset_dir,
        simple_csv=(
            "query,label,source,domain\n"
            "A.B（C）,simple,test,BENZ\n"
            "ABC,simple,test,BYD\n"
        ),
    )

    monkeypatch.setattr(router_assets, "_ASSET_DIR", asset_dir)
    load_router_assets.cache_clear()
    try:
        assets = load_router_assets()
    finally:
        load_router_assets.cache_clear()

    assert "ABC" in assets.simple_queries


@pytest.mark.parametrize(
    "query",
    [
        "",
        "！！！",
    ],
)
def test_load_router_assets_rejects_missing_normalized_simple_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    asset_dir = tmp_path / "assets"
    _write_temp_assets(
        asset_dir,
        simple_csv=(
            "query,label,source,domain\n"
            f"{query},simple,test,BENZ\n"
        ),
    )

    _load_temp_assets_expect_error(asset_dir, monkeypatch, "missing query")


@pytest.mark.parametrize(
    ("override_name", "override_value", "match"),
    [
        (
            "simple_csv",
            "query,label,source,domain\n打开车窗,simple,,BENZ\n",
            "source",
        ),
        (
            "simple_csv",
            "query,label,source,domain\n打开车窗,simple,test,\n",
            "domain",
        ),
        (
            "complex_csv",
            "query,label,source,domain\n关闭车窗和天窗,complex,,BENZ\n",
            "source",
        ),
        (
            "complex_csv",
            "query,label,source,domain\n关闭车窗和天窗,complex,test,\n",
            "domain",
        ),
    ],
)
def test_load_router_assets_rejects_blank_case_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    override_name: str,
    override_value: str,
    match: str,
) -> None:
    asset_dir = tmp_path / "assets"
    _write_temp_assets(asset_dir, **{override_name: override_value})

    _load_temp_assets_expect_error(asset_dir, monkeypatch, match)


def test_audit_router_cards_reads_split_capability_files(tmp_path: Path) -> None:
    from projects.sgm_prod.classification.tools.audit_router_cards import audit

    asset_dir = tmp_path / "assets"
    _write_temp_assets(
        asset_dir,
        capability_yaml="""
executor: 端侧车控
capabilities:
  - id: vehicle.window.set
    name: 车窗控制
    targets: [车窗]
    actions: [打开]
  - id: vehicle.sunroof.set
    name: 天窗控制
    targets: [车窗]
    actions: [打开]
""".lstrip(),
    )

    rows = audit(asset_dir)

    assert any(row["check"] == "target_action重叠" for row in rows)


def test_audit_router_cards_flags_legacy_engine_routing_parser_rules(
    tmp_path: Path,
) -> None:
    from projects.sgm_prod.classification.tools.audit_router_cards import audit

    asset_dir = tmp_path / "assets"
    _write_temp_assets(asset_dir)
    (asset_dir / "rules" / "parser_rules.yaml").write_text(
        "navigation_hard_control_capabilities:\n  - navigation.missing\n",
        encoding="utf-8",
    )

    rows = audit(asset_dir)

    assert any(row["check"] == "parser_rules旧engine配置" for row in rows)
