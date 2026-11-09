from __future__ import annotations

from collections import Counter
import json
import random
import sys
from pathlib import Path

import anyio
import pytest

from aicore.agents.plan.experiment.reverse_complex_plan_queries import (
    QueryNaturalnessJudgeOutput,
    ReverseQueryOutput,
    _main as reverse_query_main,
    build_query_judge_prompt,
    run_reverse_query_generation,
    write_reverse_query_filtered_file,
    write_reverse_query_file,
    write_reverse_query_subset_file,
)
from aicore.agents.plan.experiment.synthetic_complex_plan_cases import (
    MAIN_TOPOLOGIES,
    MULTI_UPSTREAM_TOPOS,
    REFERENCE_PATTERNS,
    REF_PATTERN_CONSTRAINTS,
    SELF_DOMAIN_ALLOW_LIST,
    TOPOLOGY_PATTERNS,
    EdgeCandidate,
    EdgeUsageCounter,
    RefBinding,
    _ITEM_REF_RE,
    _REF_RE,
    _edge_from_binding,
    _materialize_chain,
    _materialize_conditional_branch,
    _materialize_deep_chain,
    _materialize_fanout_join,
    _materialize_gather_reduce,
    _materialize_map_foreach,
    _materialize_self_domain_chain,
    _pick_edge,
    _pick_topology,
    _target_step,
    _topo_compatible,
    build_coverage_report,
    build_coverage_targets,
    build_high_recall_edge_pool,
    build_output_schema_subset,
    build_reverse_query_prompt,
    collect_operator_schema_inventory,
    generate_synthetic_plan_cases,
    load_synthetic_case_file,
    normalize_ref_path,
    validate_synthetic_case,
    write_coverage_report,
    write_synthetic_case_file,
)


def test_high_recall_edge_pool_is_schema_cartesian_not_semantic_subset() -> None:
    inventory = collect_operator_schema_inventory()
    edges = build_high_recall_edge_pool(inventory)
    output_count = sum(len(info.output_paths) for info in inventory.values())
    input_count = sum(len(info.input_fields) for info in inventory.values())
    keys = {(edge.source_op, edge.source_path, edge.target_op, edge.target_param) for edge in edges}

    assert len(edges) == output_count * input_count
    assert ("poi_search", "business.rating", "audio_play", "volume") in keys
    assert ("music_search", "songs[].song_name", "navigation", "route_preference") in keys
    assert ("web_search", "train.train_price", "car_control", "command") in keys

    for edge in edges:
        assert edge.source_path in inventory[edge.source_op].output_paths
        assert edge.target_param in inventory[edge.target_op].input_fields


def test_generate_cases_cover_topology_and_reference_patterns() -> None:
    cases = generate_synthetic_plan_cases(seed=7, max_cases=333)
    topologies = {case.topology_pattern for case in cases}
    ref_patterns = {
        edge["reference_pattern"]
        for case in cases
        for edge in case.dependency_edges
    }

    assert set(TOPOLOGY_PATTERNS).issubset(topologies)
    assert set(REFERENCE_PATTERNS).issubset(ref_patterns)
    assert any(len(case.dependency_edges) > 1 for case in cases)

    for case in cases:
        assert validate_synthetic_case(case) == []
        assert case.plan["steps"]
        assert case.dependency_edges
        assert "goal" not in case.plan
        assert "合成复杂计划" not in json.dumps(case.plan, ensure_ascii=False)
        assert "生成 " not in json.dumps(case.plan, ensure_ascii=False)


def test_coverage_report_tracks_unused_outputs_and_target_inputs() -> None:
    inventory = collect_operator_schema_inventory()
    cases = generate_synthetic_plan_cases(seed=9, max_cases=12)
    report = build_coverage_report(cases, inventory)

    assert report["case_count"] >= 333
    assert report["total_output_fields"] >= report["used_output_field_count"]
    assert report["total_target_inputs"] >= report["used_target_input_count"]
    assert report["unused_output_fields"] == {}
    assert "tool_edge_coverage" in report
    assert "reference_pattern_coverage" in report
    assert "topology_pattern_coverage" in report


def test_large_generation_covers_all_output_fields_and_target_inputs() -> None:
    inventory = collect_operator_schema_inventory()
    output_count = sum(len(info.output_paths) for info in inventory.values())
    cases = generate_synthetic_plan_cases(seed=11, max_cases=output_count)
    report = build_coverage_report(cases, inventory)

    assert report["unused_output_fields"] == {}
    assert report["used_output_field_count"] == report["total_output_fields"]
    assert report["input_x_ref_pattern"]["missing"] == []
    assert report["topology_x_ref_pattern"]["missing"] == []
    assert report["output_x_input"]["covered"] > 0


def test_case_file_and_coverage_file_round_trip(tmp_path: Path) -> None:
    cases = generate_synthetic_plan_cases(seed=5, max_cases=16)
    case_path = tmp_path / "cases.json"
    coverage_path = tmp_path / "coverage.json"

    write_synthetic_case_file(cases, case_path)
    write_coverage_report(build_coverage_report(cases), coverage_path)

    loaded = load_synthetic_case_file(case_path)
    case_payload = json.loads(case_path.read_text(encoding="utf-8"))
    coverage_payload = json.loads(coverage_path.read_text(encoding="utf-8"))

    assert case_payload["version"] == 3
    assert case_payload["coverage_report"]["case_count"] == len(cases)
    assert loaded[0].case_id == cases[0].case_id
    assert coverage_payload["case_count"] == len(cases)


def test_reference_helpers_preserve_nested_objects_and_arrays() -> None:
    assert build_output_schema_subset(["business.rating", "address"]) == {
        "address": "",
        "business": {"rating": ""},
    }
    assert build_output_schema_subset(["songs[].song_name", "songs[].singer_name"]) == {
        "songs": [{"singer_name": "", "song_name": ""}],
    }
    assert normalize_ref_path("songs[0].song_name") == "songs[].song_name"
    assert normalize_ref_path("songs[*].song_name") == "songs[].song_name"


def test_ref_regexes_match_empty_brackets_and_item_refs() -> None:
    assert _REF_RE.findall("$s1.songs[].song_name") == [("s1", "songs[].song_name")]
    assert _REF_RE.findall("结合 $s2.business.rating 和 $s3.address") == [
        ("s2", "business.rating"),
        ("s3", "address"),
    ]
    assert _ITEM_REF_RE.findall("$item.song_name 和 $item.business.rating") == [
        "song_name",
        "business.rating",
    ]


def test_edge_usage_counter_and_pick_edge_balance_candidates() -> None:
    edges = [
        EdgeCandidate("poi_search", "address", "navigation", "destination"),
        EdgeCandidate("poi_search", "name", "navigation", "destination"),
        EdgeCandidate("poi_search", "business.rating", "navigation", "destination"),
    ]
    counter = EdgeUsageCounter()
    counter.record_edge(edges[0])
    counter.record_edge(edges[0])
    counter.record_edge(edges[1])

    picked = _pick_edge(
        edges,
        counter=counter,
        rng=random.Random(0),
        source_op="poi_search",
        target_op="navigation",
        target_param="destination",
        top_k=1,
    )

    assert counter.count(edges[0]) == 2
    assert counter.count(edges[2]) == 0
    assert picked == edges[2]
    assert _pick_edge(
        edges,
        counter=counter,
        rng=random.Random(0),
        source_op="missing",
        exclude={edges[2]},
        top_k=1,
    ) in {edges[0], edges[1]}


def test_coverage_targets_are_input_by_ref_pattern_targets() -> None:
    inventory = collect_operator_schema_inventory()
    targets = build_coverage_targets(inventory)
    target_keys = {(target.target_op, target.target_param, target.reference_pattern) for target in targets}
    indexed_or_wildcard = {
        pattern
        for target in targets
        if target.target_op == "navigation" and target.target_param == "destination"
        for pattern in [target.reference_pattern]
    }

    expected_targets = sum(len(info.input_fields) for info in inventory.values()) * len(REFERENCE_PATTERNS)
    assert len(targets) == expected_targets
    assert len(target_keys) == len(targets)
    assert ("navigation", "destination", "direct_ref") in target_keys
    assert {"indexed_ref", "wildcard_ref"}.issubset(indexed_or_wildcard)
    assert REF_PATTERN_CONSTRAINTS["indexed_ref"](
        EdgeCandidate("music_search", "songs[].song_name", "navigation", "destination")
    )
    assert not REF_PATTERN_CONSTRAINTS["indexed_ref"](
        EdgeCandidate("poi_search", "address", "navigation", "destination")
    )


def test_pick_topology_respects_multi_ref_compatibility() -> None:
    counter: Counter[str] = Counter({"chain": 3, "join": 0})
    assert _pick_topology(
        list(MAIN_TOPOLOGIES),
        counter,
        random.Random(0),
        ref_pattern="multi_ref_query",
        covered_pairs=set(),
    ) in MULTI_UPSTREAM_TOPOS
    assert _topo_compatible("join", "multi_ref_query")
    assert not _topo_compatible("chain", "multi_ref_query")
    first = _pick_topology(
        list(MAIN_TOPOLOGIES),
        Counter(),
        random.Random(0),
        ref_pattern="direct_ref",
        covered_pairs=set(),
    )
    second = _pick_topology(
        list(MAIN_TOPOLOGIES),
        Counter({first: 1}),
        random.Random(0),
        ref_pattern="direct_ref",
        covered_pairs={(first, "direct_ref")},
    )
    assert first in MAIN_TOPOLOGIES
    assert second in MAIN_TOPOLOGIES
    assert second != first


def test_target_step_renders_ref_bindings_and_edge_metadata() -> None:
    binding = RefBinding(
        target_param="destination",
        ref_step="s1",
        ref_path="address",
        reference_pattern="embedded_query_ref",
    )
    step = _target_step(
        "s2",
        "navigation",
        depends_on=["s1"],
        target_output_paths=["route_summary"],
        bindings=[binding],
        case_idx=1,
    )
    edge = EdgeCandidate("poi_search", "address", "navigation", "destination")

    assert step["inputs"]["destination"] == "围绕 $s1.address 继续查询相关信息"
    assert step["outputs"] == {"route_summary": ""}
    assert _edge_from_binding("s1", edge, "s2", binding)["to_param"] == "destination"


def test_validate_rejects_direct_ref_metadata_on_embedded_input() -> None:
    inventory = collect_operator_schema_inventory()
    edge_pool = build_high_recall_edge_pool(inventory)
    case = _materialize_chain(
        0,
        EdgeCandidate("poi_search", "address", "navigation", "destination"),
        "direct_ref",
        edge_pool,
        inventory,
        random.Random(0),
        EdgeUsageCounter(),
        topology="chain",
    )
    s2 = case.plan["steps"][1]
    s2["inputs"]["destination"] = "围绕 $s1.address 继续查询相关信息"

    assert validate_synthetic_case(case) != []


def test_new_topology_materializers_are_valid() -> None:
    inventory = collect_operator_schema_inventory()
    edge_pool = build_high_recall_edge_pool(inventory)
    counter = EdgeUsageCounter()
    rng = random.Random(7)
    primary = next(edge for edge in edge_pool if "[]" in edge.source_path and edge.source_op in SELF_DOMAIN_ALLOW_LIST)
    cases = [
        _materialize_deep_chain(1, primary, "direct_ref", edge_pool, inventory, rng, counter),
        _materialize_map_foreach(2, primary, "wildcard_ref", edge_pool, inventory, rng, counter),
        _materialize_conditional_branch(3, primary, "conditional_ref", edge_pool, inventory, rng, counter),
        _materialize_gather_reduce(4, primary, "multi_ref_query", edge_pool, inventory, rng, counter),
        _materialize_self_domain_chain(5, primary, "direct_ref", edge_pool, inventory, rng, counter),
    ]

    for case in cases:
        assert validate_synthetic_case(case) == []

    assert 4 <= len(cases[0].plan["steps"]) <= 7
    map_step = cases[1].plan["steps"][1]
    assert map_step["iteration"]["over"].startswith("$s1.")
    assert "$item." in json.dumps(map_step["inputs"], ensure_ascii=False)
    conditional_step = cases[2].plan["steps"][-1]
    assert "$s" in conditional_step["condition"]
    gather_step = cases[3].plan["steps"][-1]
    assert 4 <= len(cases[3].plan["steps"]) <= 5
    assert gather_step["gather"]["strategy"] == "concat"
    assert len(gather_step["gather"]["sources"]) >= 2
    self_ops = {step["op"] for step in cases[4].plan["steps"]}
    assert len(self_ops) == 1
    assert next(iter(self_ops)) in SELF_DOMAIN_ALLOW_LIST


def test_fanout_join_prefers_different_join_params_when_possible() -> None:
    inventory = collect_operator_schema_inventory()
    edge_pool = build_high_recall_edge_pool(inventory)
    primary = next(
        edge
        for edge in edge_pool
        if edge.target_op == "web_search" and edge.target_param == "query"
    )
    case = _materialize_fanout_join(
        9,
        primary,
        "direct_ref",
        edge_pool,
        inventory,
        random.Random(9),
        EdgeUsageCounter(),
    )
    join_edges = [edge for edge in case.dependency_edges if edge["to_step"] == "s4"]
    join_params = {edge["to_param"] for edge in join_edges}

    assert validate_synthetic_case(case) == []
    assert len(join_edges) == 2
    if len(inventory[join_edges[0]["to_op"]].input_fields) > 1:
        assert len(join_params) == 2


def test_generate_cases_v3_minimum_and_cross_dimension_coverage() -> None:
    with pytest.warns(UserWarning, match="below minimum"):
        cases = generate_synthetic_plan_cases(seed=3, max_cases=100)
    report = build_coverage_report(cases)
    topologies = {case.topology_pattern for case in cases}

    assert len(cases) >= report["input_x_ref_pattern"]["total"]
    assert set(MAIN_TOPOLOGIES).issubset(topologies)
    assert "self_domain_chain" in topologies
    assert report["input_x_ref_pattern"]["total"] == len(build_coverage_targets())
    assert report["input_x_ref_pattern"]["missing"] == []
    assert report["topology_x_ref_pattern"]["missing"] == []
    assert report["tool_pair_x_ref_pattern"]["covered"] > 0
    assert report["output_x_input"]["covered"] > 0
    assert all(validate_synthetic_case(case) == [] for case in cases)


def test_reverse_query_prompt_mentions_topology_and_reference_patterns() -> None:
    case = generate_synthetic_plan_cases(seed=13, max_cases=1)[0]
    prompt = build_reverse_query_prompt(case)

    assert "该 DAG 没有预设用户 goal" in prompt
    assert "iteration 表示对上游列表元素逐个重复执行" in prompt
    assert "condition 表示满足条件时执行步骤" in prompt
    assert "gather 表示聚合多个上游结果" in prompt
    assert "dependency_edges" in prompt
    assert json.dumps(case.plan, ensure_ascii=False, indent=2) in prompt
    assert "不要在 query 中出现 $s1" in prompt
    assert "合成复杂计划" not in prompt
    assert "topology_pattern" not in prompt
    assert "reference_patterns" not in prompt


def test_query_judge_prompt_penalizes_business_logic_mismatch() -> None:
    case = generate_synthetic_plan_cases(seed=5, max_cases=333)[0]
    bad_query = (
        "帮我搜一下周杰伦的《晴天》，然后用搜索结果里第一个专辑所属的唱片公司来调整空调，"
        "同时把和这家唱片公司相关的信息加到播放列表里"
    )
    prompt = build_query_judge_prompt(case, bad_query)

    assert "业务逻辑" in prompt
    assert "因果" in prompt
    assert "根据唱片公司调整空调" in prompt
    assert "naturalness_score 不得超过 2" in prompt
    assert "logic_score" in prompt
    assert "logic_issues" in prompt


def test_query_judge_output_schema_tracks_logic_quality() -> None:
    field_names = set(QueryNaturalnessJudgeOutput.model_fields)

    assert {"is_logically_coherent", "logic_score", "logic_issues"}.issubset(field_names)


async def _fake_reverse_generator(prompt: str) -> ReverseQueryOutput:
    assert "请根据给定 DAG plan" in prompt
    return ReverseQueryOutput(query="帮我先查一下相关信息，再根据结果继续处理", notes="覆盖合成依赖")


async def _fake_judge(prompt: str) -> QueryNaturalnessJudgeOutput:
    assert "generated_query" in prompt
    return QueryNaturalnessJudgeOutput(
        is_natural=True,
        naturalness_score=4,
        covers_plan=True,
        is_logically_coherent=True,
        logic_score=4,
        logic_issues=[],
        leaks_implementation=False,
        reason="自然且没有暴露实现细节",
    )


def test_reverse_query_generation_runs_optional_judge(tmp_path: Path) -> None:
    cases = generate_synthetic_plan_cases(seed=5, max_cases=333)[:2]

    async def _run():
        return await run_reverse_query_generation(
            cases,
            _fake_reverse_generator,
            judge=_fake_judge,
        )

    rows = anyio.run(_run)
    output = tmp_path / "reverse_queries.json"
    write_reverse_query_file(rows, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert rows[0]["generated_query"]
    assert rows[0]["judge"]["is_natural"] is True
    assert rows[0]["case"]["case_id"] == cases[0].case_id
    assert payload["version"] == 2


def test_reverse_query_generation_retries_transient_generation_errors() -> None:
    cases = generate_synthetic_plan_cases(seed=5, max_cases=333)[:1]
    attempts = 0

    async def flaky_generator(prompt: str) -> ReverseQueryOutput:
        nonlocal attempts
        assert "请根据给定 DAG plan" in prompt
        attempts += 1
        if attempts < 3:
            raise ValueError("transient invalid json")
        return ReverseQueryOutput(query="第三次成功", notes="retry ok")

    async def _run():
        return await run_reverse_query_generation(
            cases,
            flaky_generator,
            api_timeout_seconds=1,
            max_retries=3,
        )

    rows = anyio.run(_run)

    assert attempts == 3
    assert rows[0]["generated_query"] == "第三次成功"
    assert rows[0]["error"] is None


def test_reverse_query_generation_retries_transient_judge_errors() -> None:
    cases = generate_synthetic_plan_cases(seed=5, max_cases=333)[:1]
    attempts = 0

    async def flaky_judge(prompt: str) -> QueryNaturalnessJudgeOutput:
        nonlocal attempts
        assert "generated_query" in prompt
        attempts += 1
        if attempts < 3:
            raise ValueError("transient judge invalid json")
        return await _fake_judge(prompt)

    async def _run():
        return await run_reverse_query_generation(
            cases,
            _fake_reverse_generator,
            judge=flaky_judge,
            api_timeout_seconds=1,
            max_retries=3,
        )

    rows = anyio.run(_run)

    assert attempts == 3
    assert rows[0]["judge"]["is_natural"] is True
    assert rows[0]["judge_error"] is None


def test_reverse_query_generation_times_out_and_exhausts_retries() -> None:
    cases = generate_synthetic_plan_cases(seed=5, max_cases=333)[:1]
    attempts = 0

    async def hanging_generator(prompt: str) -> ReverseQueryOutput:
        nonlocal attempts
        del prompt
        attempts += 1
        await anyio.sleep(0.05)
        return ReverseQueryOutput(query="too late")

    async def _run():
        return await run_reverse_query_generation(
            cases,
            hanging_generator,
            api_timeout_seconds=0.001,
            max_retries=2,
        )

    rows = anyio.run(_run)

    assert attempts == 3
    assert rows[0]["generated_query"] == ""
    assert "generation failed after 3 attempts" in rows[0]["error"]
    assert "TimeoutError" in rows[0]["error"]


def test_reverse_query_subset_file_keeps_only_browsing_fields(tmp_path: Path) -> None:
    cases = generate_synthetic_plan_cases(seed=5, max_cases=333)[:1]

    async def _run():
        return await run_reverse_query_generation(cases, _fake_reverse_generator, judge=_fake_judge)

    rows = anyio.run(_run)
    output = tmp_path / "reverse_queries_subset.json"
    write_reverse_query_subset_file(rows, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["version"] == 1
    assert payload["case_count"] == 1
    assert list(payload["cases"][0].keys()) == [
        "case_id",
        "topology_pattern",
        "generated_query",
        "plan",
    ]
    assert payload["cases"][0]["case_id"] == cases[0].case_id
    assert payload["cases"][0]["topology_pattern"] == cases[0].topology_pattern
    assert payload["cases"][0]["generated_query"] == "帮我先查一下相关信息，再根据结果继续处理"
    assert payload["cases"][0]["plan"] == cases[0].plan


def test_reverse_query_subset_file_filters_low_score_rows(tmp_path: Path) -> None:
    cases = generate_synthetic_plan_cases(seed=5, max_cases=333)[:2]

    rows = [
        {
            "case": cases[0].to_json_dict(),
            "generated_query": "质量足够好的 query",
            "judge": {
                "is_natural": True,
                "naturalness_score": 4,
                "covers_plan": True,
                "is_logically_coherent": True,
                "logic_score": 4,
                "logic_issues": [],
                "leaks_implementation": False,
                "reason": "可用",
            },
        },
        {
            "case": cases[1].to_json_dict(),
            "generated_query": "低质量 query",
            "judge": {
                "is_natural": True,
                "naturalness_score": 3,
                "covers_plan": True,
                "is_logically_coherent": False,
                "logic_score": 2,
                "logic_issues": ["业务逻辑牵强"],
                "leaks_implementation": False,
                "reason": "低分",
            },
        },
    ]
    output = tmp_path / "reverse_queries_subset.json"
    write_reverse_query_subset_file(rows, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["case_count"] == 1
    assert payload["cases"][0]["case_id"] == cases[0].case_id
    assert payload["cases"][0]["generated_query"] == "质量足够好的 query"


def test_reverse_query_filtered_file_filters_scores_and_keeps_full_rows(tmp_path: Path) -> None:
    cases = generate_synthetic_plan_cases(seed=5, max_cases=333)[:2]

    async def _run():
        return await run_reverse_query_generation(cases, _fake_reverse_generator, judge=_fake_judge)

    rows = anyio.run(_run)
    rows[0]["judge"]["naturalness_score"] = 4
    rows[1]["judge"]["naturalness_score"] = 3
    output = tmp_path / "reverse_queries_filtered_full.json"
    write_reverse_query_filtered_file(rows, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["version"] == 2
    assert payload["case_count"] == 1
    assert payload["cases"][0]["case"]["case_id"] == cases[0].case_id
    assert payload["cases"][0]["prompt"]
    assert payload["cases"][0]["judge"]["naturalness_score"] == 4
    assert set(payload["cases"][0]).issuperset({"case", "prompt", "generated_query", "notes", "judge"})


def test_reverse_query_generation_reports_progress_status() -> None:
    cases = generate_synthetic_plan_cases(seed=5, max_cases=333)[:2]
    events: list[dict] = []

    async def _run():
        return await run_reverse_query_generation(
            cases,
            _fake_reverse_generator,
            judge=_fake_judge,
            concurrency=2,
            progress_callback=events.append,
        )

    rows = anyio.run(_run)
    done_events = [event for event in events if event["event"] == "case_done"]

    assert len(rows) == 2
    assert events[0] == {"event": "start", "total": 2}
    assert len(done_events) == 2
    assert {event["generation_status"] for event in done_events} == {"ok"}
    assert {event["judge_status"] for event in done_events} == {"ok"}
    assert events[-1]["event"] == "finish"
    assert events[-1]["completed"] == 2
    assert events[-1]["generation_errors"] == 0
    assert events[-1]["judge_errors"] == 0


def test_reverse_query_cli_dry_run_accepts_judge_flags(tmp_path: Path, monkeypatch) -> None:
    cases = generate_synthetic_plan_cases(seed=5, max_cases=3)
    input_path = tmp_path / "cases.json"
    output_path = tmp_path / "queries.json"
    subset_output_path = tmp_path / "queries_subset.json"
    filtered_full_output_path = tmp_path / "queries_filtered_full.json"
    write_synthetic_case_file(cases, input_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "reverse_complex_plan_queries",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--subset-output",
            str(subset_output_path),
            "--filtered-full-output",
            str(filtered_full_output_path),
            "--dry-run",
            "--skip-judge",
            "--limit",
            "2",
            "--concurrency",
            "2",
            "--no-progress",
        ],
    )

    reverse_query_main()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    subset_payload = json.loads(subset_output_path.read_text(encoding="utf-8"))
    filtered_full_payload = json.loads(filtered_full_output_path.read_text(encoding="utf-8"))

    assert payload["version"] == 2
    assert payload["case_count"] == 2
    assert payload["cases"][0]["notes"] == "dry_run: prompt only"
    assert subset_payload["case_count"] == 2
    assert list(subset_payload["cases"][0].keys()) == [
        "case_id",
        "topology_pattern",
        "generated_query",
        "plan",
    ]
    assert filtered_full_payload["version"] == 2
    assert filtered_full_payload["case_count"] == 2
    assert "prompt" in filtered_full_payload["cases"][0]
    assert "case" in filtered_full_payload["cases"][0]
