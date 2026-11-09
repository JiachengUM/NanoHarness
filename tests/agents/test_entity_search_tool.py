from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aicore.tools.runner.task_tool_runner import TaskToolRunner
from aicore.agents.plan.experiment.entity_search_schema_eval import (
    EvaluationResult,
    _make_tool_generator,
    load_case_file,
    run_eval,
    write_excel,
)
from aicore.agents.plan.experiment.entity_search_schema_cases import (
    extract_plan_cases,
    load_cases_from_excel,
    write_case_file,
)
from aicore.tools.dag.operator_models import (
    MusicSearchOutput,
    POISearchOutput,
    WebSearchOutput,
)
from aicore.tools.experiments.entity_search_tool import (
    EntitySearchSchemaWorker,
    EntitySearchToolInput,
    collect_schema_attributes,
    concept_to_schema,
    create_entity_search_tool,
    flatten_concept_paths,
)
from aicore.tools.experiments.entity_search_tool_v2 import (
    EntitySearchSchemaWorkerV2,
    EntitySearchToolInputV2,
    attributes_to_field_types,
    attributes_to_fields,
    build_prompt_v2,
    create_entity_search_tool_v2,
    flatten_simple_concept_paths,
    simple_concept_to_schema,
)
from aicore.utils._concepts.meta import (
    ArrayType,
    Attribute,
    Concept,
    ObjectType,
    PrimitiveAttribute,
    PrimitiveAttributeType,
    SimpleConcept,
)


def test_collect_schema_attributes_expands_nested_and_list_fields() -> None:
    poi_fields = collect_schema_attributes(POISearchOutput)
    web_fields = collect_schema_attributes(WebSearchOutput)
    music_fields = collect_schema_attributes(MusicSearchOutput)

    assert "poi" in poi_fields
    assert "business.rating" in poi_fields
    assert poi_fields["business.rating"].name == "business_rating"
    assert poi_fields["business.rating"].description == "评分"
    assert poi_fields["business.rating"].type == PrimitiveAttributeType.STRING

    assert "weather.weather_temperature" in web_fields
    assert "air_quality.air_quality_level" in web_fields
    assert "parking.parking_fee" in web_fields

    assert "songs[].song_name" in music_fields
    assert "playlists[].dissname" in music_fields
    assert "albums[].album_name" in music_fields


def test_entity_search_schema_worker_is_worker_only() -> None:
    worker = EntitySearchSchemaWorker(model_api=object())

    assert not hasattr(worker, "generate")
    assert callable(worker)


@pytest.mark.asyncio
async def test_entity_search_schema_worker_does_not_send_empty_system_prompt() -> None:
    concept = Concept(
        name="SelectedPOIOutput",
        definition="字段子集",
        attributes=[
            Attribute(
                name="name",
                type=PrimitiveAttributeType.STRING,
                title="名称",
                description="POI名称",
                is_required=False,
            )
        ],
    )

    class _Response:
        parsed = concept
        metadata = {}

    class _ModelAPI:
        def __init__(self) -> None:
            self.system_prompts: list[str | None] = []

        def initial_state(self, *, system_prompt: str | None = None):
            self.system_prompts.append(system_prompt)
            return object()

        async def structured_output(self, *args, **kwargs):
            return _Response()

    model_api = _ModelAPI()
    worker = EntitySearchSchemaWorker(model_api=model_api)

    result = await worker(
        query="搜索评分最高的火锅店",
        tool_name="poi_search",
        output_schema=POISearchOutput.model_json_schema(),
    )

    assert result == concept
    assert model_api.system_prompts == [None]


@pytest.mark.asyncio
async def test_create_entity_search_tool_runs_as_standard_task_tool() -> None:
    async def worker(
        query: str,
        tool_name: str,
        output_schema: dict,
    ) -> Concept:
        assert query == "搜索评分最高的火锅店"
        assert tool_name == "poi_search"
        return Concept(
            name="SelectedPOIOutput",
            definition="字段子集",
            attributes=[
                Attribute(
                    name="name",
                    type=PrimitiveAttributeType.STRING,
                    title="名称",
                    description="POI名称",
                    is_required=False,
                )
            ],
        )

    tool = create_entity_search_tool(worker)
    runner = TaskToolRunner()
    runner.add_tool(
        tool,
        EntitySearchToolInput(
            query="搜索评分最高的火锅店",
            tool_name="poi_search",
            output_schema=POISearchOutput.model_json_schema(),
        ),
    )

    async for _ in runner.run():
        pass

    assert runner.results[0].is_success
    assert runner.results[0].data.attributes[0].name == "name"


def test_extract_plan_cases_keeps_independent_search_steps_only(tmp_path: Path) -> None:
    payload = [
        {
            "index": 0,
            "query": "source query",
            "success": True,
            "plan": {
                "steps": [
                    {
                        "step_id": "s1",
                        "op": "POISearch",
                        "step_goal": "找火锅店",
                        "depends_on": [],
                        "inputs": {"poi_type": "火锅店"},
                        "outputs": {"name": "", "address": ""},
                    },
                    {
                        "step_id": "s2",
                        "op": "WebSearch",
                        "step_goal": "查停车场",
                        "depends_on": ["s1"],
                        "inputs": {"query": "$s1.address 附近停车场"},
                        "outputs": {"parking": None},
                    },
                    {
                        "step_id": "s3",
                        "op": "music_search",
                        "step_goal": "搜轻音乐",
                        "depends_on": [],
                        "inputs": {"genre": "轻音乐"},
                        "outputs": {"songs": []},
                    },
                    {
                        "step_id": "s4",
                        "op": "Navigation",
                        "step_goal": "导航过去",
                        "depends_on": ["s1"],
                        "inputs": {"destination": "$s1.address"},
                        "outputs": {"message": ""},
                    },
                ]
            },
        }
    ]
    path = tmp_path / "plans.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    cases = extract_plan_cases(path)

    assert [(case.step_id, case.op, case.schema_query) for case in cases] == [
        ("s1", "poi_search", "找火锅店"),
        ("s3", "music_search", "搜轻音乐"),
    ]
    assert cases[0].reference_paths == ["address", "name"]


def test_case_file_round_trips_reviewable_json(tmp_path: Path) -> None:
    source = _write_plan_fixture(tmp_path, outputs={"name": "", "address": ""})
    cases = extract_plan_cases(source)
    output = tmp_path / "cases.json"

    write_case_file(cases, output, source=source)
    loaded = load_case_file(output)

    assert loaded[0].case_id == cases[0].case_id
    assert loaded[0].inputs == {"poi_type": "火锅店", "city": "北京"}
    assert loaded[0].reference_paths == ["address", "name"]
    assert loaded[0].op == "poi_search"


# ---------------------------------------------------------------------------
# concept_to_schema / flatten_concept_paths 测试
# ---------------------------------------------------------------------------


def test_flatten_concept_paths_flat_and_nested() -> None:
    concept = Concept(
        name="SelectedPOIOutput",
        definition="子集",
        attributes=[
            Attribute(
                name="name",
                type=PrimitiveAttributeType.STRING,
                title="名称",
                description="POI名称",
                is_required=False,
            ),
            Attribute(
                name="business",
                type=ObjectType(
                    properties=[
                        Attribute(
                            name="rating",
                            type=PrimitiveAttributeType.STRING,
                            title="评分",
                            description="评分",
                            is_required=False,
                        ),
                    ]
                ),
                title="商户信息",
                description="商户",
                is_required=False,
            ),
        ],
    )

    paths = flatten_concept_paths(concept)
    assert paths == ["name", "business.rating"]


def test_flatten_concept_paths_array_with_children() -> None:
    concept = Concept(
        name="SelectedMusicOutput",
        definition="子集",
        attributes=[
            Attribute(
                name="songs",
                type=ArrayType(
                    item_type=ObjectType(
                        properties=[
                            Attribute(
                                name="song_name",
                                type=PrimitiveAttributeType.STRING,
                                title="歌曲名",
                                description="歌曲名称",
                                is_required=False,
                            ),
                            Attribute(
                                name="singer_name",
                                type=PrimitiveAttributeType.STRING,
                                title="歌手",
                                description="歌手名称",
                                is_required=False,
                            ),
                        ]
                    )
                ),
                title="歌曲列表",
                description="单曲",
                is_required=False,
            ),
        ],
    )

    paths = flatten_concept_paths(concept)
    assert paths == ["songs[].song_name", "songs[].singer_name"]


def test_concept_to_schema_nested_object() -> None:
    concept = Concept(
        name="SelectedPOIOutput",
        definition="子集",
        attributes=[
            Attribute(
                name="name",
                type=PrimitiveAttributeType.STRING,
                title="名称",
                description="POI名称",
                is_required=False,
            ),
            Attribute(
                name="business",
                type=ObjectType(
                    properties=[
                        Attribute(
                            name="rating",
                            type=PrimitiveAttributeType.STRING,
                            title="评分",
                            description="评分",
                            is_required=False,
                        ),
                    ]
                ),
                title="商户信息",
                description="商户",
                is_required=False,
            ),
        ],
    )

    schema = concept_to_schema(concept)

    assert schema["title"] == "SelectedPOIOutput"
    assert schema["properties"]["name"]["type"] == "string"
    assert schema["properties"]["business"]["type"] == "object"
    assert "rating" in schema["properties"]["business"]["properties"]


def test_concept_to_schema_array_with_object_items() -> None:
    concept = Concept(
        name="SelectedMusicOutput",
        definition="子集",
        attributes=[
            Attribute(
                name="songs",
                type=ArrayType(
                    item_type=ObjectType(
                        properties=[
                            Attribute(
                                name="song_name",
                                type=PrimitiveAttributeType.STRING,
                                title="歌曲名",
                                description="歌曲名称",
                                is_required=False,
                            ),
                            Attribute(
                                name="singer_name",
                                type=PrimitiveAttributeType.STRING,
                                title="歌手",
                                description="歌手名称",
                                is_required=False,
                            ),
                        ]
                    )
                ),
                title="歌曲",
                description="单曲列表",
                is_required=False,
            ),
            Attribute(
                name="playlists",
                type=ArrayType(
                    item_type=ObjectType(
                        properties=[
                            Attribute(
                                name="dissname",
                                type=PrimitiveAttributeType.STRING,
                                title="歌单名",
                                description="歌单名称",
                                is_required=False,
                            ),
                        ]
                    )
                ),
                title="歌单",
                description="歌单列表",
                is_required=False,
            ),
        ],
    )

    schema = concept_to_schema(concept)

    assert set(schema["properties"]) == {"songs", "playlists"}
    assert schema["properties"]["songs"]["type"] == "array"
    song_items = schema["properties"]["songs"]["items"]["properties"]
    assert set(song_items) == {"song_name", "singer_name"}
    playlist_items = schema["properties"]["playlists"]["items"]["properties"]
    assert set(playlist_items) == {"dissname"}


# ---------------------------------------------------------------------------
# Excel / eval 测试
# ---------------------------------------------------------------------------


def test_write_excel_creates_review_workbook(tmp_path: Path) -> None:
    case = extract_plan_cases(
        _write_plan_fixture(
            tmp_path,
            outputs={"name": "", "address": ""},
        )
    )[0]
    result = EvaluationResult(
        case=case,
        generated_concept={
            "name": "SelectedPOIOutput",
            "definition": "字段子集",
            "attributes": [],
        },
        generated_paths=["name"],
        invalid_generated_paths=[],
        generated_schema={"type": "object", "properties": {"name": {"type": "string"}}},
        error=None,
        duration_s=1.23,
        input_chars=500,
        total_leaf_count=18,
        generated_leaf_count=1,
        compression_rate=1.0 - 1 / 18,
        prompt_text="test prompt",
    )
    output = tmp_path / "review.xlsx"

    write_excel([result], output)

    sheets = pd.read_excel(output, sheet_name=None)
    assert set(sheets) == {"cases", "schemas", "summary"}
    assert sheets["cases"].loc[0, "case_id"] == case.case_id
    assert sheets["summary"].loc[0, "op"] == "poi_search"
    # 新增指标列存在
    assert "avg_precision" in sheets["summary"].columns
    assert "avg_recall" in sheets["summary"].columns
    assert "avg_f1" in sheets["summary"].columns


def test_load_cases_from_excel_reconstructs_reviewed_case_json(tmp_path: Path) -> None:
    case = extract_plan_cases(_write_plan_fixture(tmp_path, outputs={"name": "", "address": ""}))[0]
    workbook = tmp_path / "reviewed.xlsx"
    pd.DataFrame(
        [
            {
                "case_id": case.case_id,
                "plan_index": case.plan_index,
                "step_id": case.step_id,
                "source_user_query": case.source_user_query,
                "schema_query": case.schema_query,
                "op": case.op,
                "input_json": json.dumps(case.inputs, ensure_ascii=False),
                "reference_paths": "name\naddress",
            }
        ]
    ).to_excel(workbook, sheet_name="cases", index=False)

    cases = load_cases_from_excel(workbook)

    assert cases[0].case_id == case.case_id
    assert cases[0].reference_paths == ["name", "address"]
    assert cases[0].inputs == case.inputs


async def _stub_generator(case):
    """生成只包含第一个字段的嵌套 Concept stub。"""
    fields = collect_schema_attributes(case.output_model)
    first_path = next(iter(fields))
    return Concept(
        name="SelectedOutput",
        definition="字段子集",
        attributes=[
            Attribute(
                name=first_path,
                type=PrimitiveAttributeType.STRING,
                title="stub",
                description="stub",
                is_required=False,
            )
        ],
    )


@pytest.mark.asyncio
async def test_run_eval_uses_generator_and_builds_comparison_result(tmp_path: Path) -> None:
    path = _write_plan_fixture(tmp_path, outputs={"name": "", "address": ""})
    cases = extract_plan_cases(path)

    results = await run_eval(cases, _stub_generator)

    assert len(results) == 1
    assert results[0].error is None
    assert results[0].generated_paths
    assert results[0].generated_schema["type"] == "object"


@pytest.mark.asyncio
async def test_eval_generator_runs_standard_entity_search_tool(tmp_path: Path) -> None:
    path = _write_plan_fixture(tmp_path, outputs={"name": "", "address": ""})
    case = extract_plan_cases(path)[0]
    seen: dict[str, object] = {}

    async def worker(query: str, tool_name: str, output_schema: dict) -> Concept:
        seen["query"] = query
        seen["tool_name"] = tool_name
        seen["output_schema"] = output_schema
        return Concept(
            name="SelectedPOIOutput",
            definition="字段子集",
            attributes=[
                Attribute(
                    name="name",
                    type=PrimitiveAttributeType.STRING,
                    title="名称",
                    description="POI名称",
                    is_required=False,
                )
            ],
        )

    generator = _make_tool_generator(create_entity_search_tool(worker))
    result = await generator(case)

    assert result.attributes[0].name == "name"
    assert seen["query"] == "搜索评分最高的火锅店"
    assert seen["tool_name"] == "poi_search"
    # 现在传入的是标准 JSON Schema
    assert "properties" in seen["output_schema"]


# ---------------------------------------------------------------------------
# V2 flat-path 测试（输出 SimpleConcept）
# ---------------------------------------------------------------------------


def test_simple_concept_to_schema_flat() -> None:
    """simple_concept_to_schema 生成 flat JSON Schema，property key 为 dot-path。"""
    sc = SimpleConcept(
        name="SelectedPOIOutput",
        definition="子集",
        attributes=[
            PrimitiveAttribute(
                name="poi", type=PrimitiveAttributeType.STRING,
                title="名称", description="POI名称", is_required=False,
            ),
            PrimitiveAttribute(
                name="business.rating", type=PrimitiveAttributeType.STRING,
                title="评分", description="评分", is_required=False,
            ),
        ],
    )
    schema = simple_concept_to_schema(sc)
    assert schema["title"] == "SelectedPOIOutput"
    assert "poi" in schema["properties"]
    assert "business.rating" in schema["properties"]
    assert schema["properties"]["poi"]["type"] == "string"


def test_attributes_to_fields_produces_path_desc_mapping() -> None:
    all_attrs = collect_schema_attributes(POISearchOutput)
    fields = attributes_to_fields(all_attrs)
    assert "business.rating" in fields
    assert fields["business.rating"] == "评分"


def test_build_prompt_v2_contains_paths() -> None:
    fields = {"name": "POI名称", "business.rating": "评分"}
    field_types = {"name": "string", "business.rating": "string"}
    prompt = build_prompt_v2("找火锅店", "poi_search", fields, field_types)
    assert "name (string): POI名称" in prompt
    assert "business.rating (string): 评分" in prompt
    assert "poi_search" in prompt


@pytest.mark.asyncio
async def test_v2_worker_returns_simple_concept() -> None:
    """V2 worker: mock LLM 直接返回 SimpleConcept。"""
    expected_sc = SimpleConcept(
        name="SelectedPOIOutput",
        definition="字段子集",
        attributes=[
            PrimitiveAttribute(
                name="poi",
                type=PrimitiveAttributeType.STRING,
                title="名称",
                description="POI名称",
                is_required=False,
            ),
            PrimitiveAttribute(
                name="business.rating",
                type=PrimitiveAttributeType.STRING,
                title="评分",
                description="评分",
                is_required=False,
            ),
        ],
    )

    class _Response:
        parsed = expected_sc
        metadata = {}

    class _ModelAPI:
        def initial_state(self, **kwargs):
            return object()

        async def structured_output(self, *args, **kwargs):
            assert kwargs.get("output_type") is SimpleConcept
            return _Response()

    all_attrs = collect_schema_attributes(POISearchOutput)
    fields = attributes_to_fields(all_attrs)
    field_types = attributes_to_field_types(all_attrs)

    worker = EntitySearchSchemaWorkerV2(model_api=_ModelAPI())
    sc = await worker(
        query="搜索评分最高的火锅店",
        tool_name="poi_search",
        fields=fields,
        field_types=field_types,
    )

    assert sc is expected_sc
    paths = flatten_simple_concept_paths(sc)
    assert "poi" in paths
    assert "business.rating" in paths


@pytest.mark.asyncio
async def test_create_entity_search_tool_v2_runs_as_task_tool() -> None:
    """V2 tool 通过 TaskToolRunner 正常执行，输出 SimpleConcept。"""
    all_attrs = collect_schema_attributes(POISearchOutput)

    async def worker(
        query: str,
        tool_name: str,
        fields: dict[str, str],
        field_types: dict[str, str],
    ) -> SimpleConcept:
        assert query == "搜索评分最高的火锅店"
        assert tool_name == "poi_search"
        return SimpleConcept(
            name="SelectedPOIOutput",
            definition="子集",
            attributes=[
                PrimitiveAttribute(
                    name="poi", type=PrimitiveAttributeType.STRING,
                    title="名称", description="POI名称", is_required=False,
                ),
                PrimitiveAttribute(
                    name="business.rating", type=PrimitiveAttributeType.STRING,
                    title="评分", description="评分", is_required=False,
                ),
            ],
        )

    tool = create_entity_search_tool_v2(worker)
    runner = TaskToolRunner()
    runner.add_tool(
        tool,
        EntitySearchToolInputV2(
            query="搜索评分最高的火锅店",
            tool_name="poi_search",
            fields=attributes_to_fields(all_attrs),
            field_types=attributes_to_field_types(all_attrs),
        ),
    )

    async for _ in runner.run():
        pass

    assert runner.results[0].is_success
    sc = runner.results[0].data
    assert isinstance(sc, SimpleConcept)
    paths = flatten_simple_concept_paths(sc)
    assert "poi" in paths
    assert "business.rating" in paths


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_plan_fixture(tmp_path: Path, outputs: dict) -> Path:
    path = tmp_path / "plans.json"
    payload = [
        {
            "index": 3,
            "query": "帮我找一家火锅店",
            "success": True,
            "plan": {
                "steps": [
                    {
                        "step_id": "s1",
                        "op": "POISearch",
                        "step_goal": "搜索评分最高的火锅店",
                        "depends_on": [],
                        "inputs": {"poi_type": "火锅店", "city": "北京"},
                        "outputs": outputs,
                    }
                ]
            },
        }
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path
