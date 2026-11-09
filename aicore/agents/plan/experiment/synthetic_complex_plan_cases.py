from __future__ import annotations

import argparse
import json
import random
import re
import warnings
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from aicore.tools.dag.operator_registry import OperatorRegistry
from aicore.tools.experiments.entity_search_tool import collect_schema_attributes


MAIN_TOPOLOGIES = (
    "chain",
    "branch",
    "join",
    "fanout_join",
    "parallel_then_action",
    "deep_chain",
    "map_foreach",
    "conditional_branch",
    "gather_reduce",
)

TOPOLOGY_PATTERNS = MAIN_TOPOLOGIES + ("self_domain_chain",)

REFERENCE_PATTERNS = (
    "direct_ref",
    "indexed_ref",
    "wildcard_ref",
    "embedded_query_ref",
    "multi_ref_query",
    "conditional_ref",
    "list_param_ref",
    "object_param_ref",
    "mixed_literal_ref",
)

MULTI_UPSTREAM_TOPOS = {"join", "fanout_join", "parallel_then_action", "gather_reduce"}
SELF_DOMAIN_ALLOW_LIST = {"poi_search", "web_search", "music_search"}
REF_PATTERN_CONSTRAINTS: dict[str, Callable[["EdgeCandidate"], bool]] = {
    "direct_ref": lambda edge: True,
    "indexed_ref": lambda edge: "[]" in edge.source_path,
    "wildcard_ref": lambda edge: "[]" in edge.source_path,
    "embedded_query_ref": lambda edge: True,
    "multi_ref_query": lambda edge: True,
    "conditional_ref": lambda edge: True,
    "list_param_ref": lambda edge: True,
    "object_param_ref": lambda edge: True,
    "mixed_literal_ref": lambda edge: True,
}

OPERATOR_ALIASES = {
    "AudioPlay": "audio_play",
    "CarControl": "car_control",
    "MusicSearch": "music_search",
    "Navigation": "navigation",
    "POISearch": "poi_search",
    "WebSearch": "web_search",
}


@dataclass(frozen=True)
class OperatorSchemaInfo:
    op: str
    input_model: str
    output_model: str
    input_fields: list[str]
    output_paths: list[str]


@dataclass(frozen=True)
class EdgeCandidate:
    source_op: str
    source_path: str
    target_op: str
    target_param: str


@dataclass(frozen=True)
class CoverageTarget:
    target_op: str
    target_param: str
    reference_pattern: str

    def __iter__(self):
        yield self.target_op
        yield self.target_param
        yield self.reference_pattern

    def __len__(self) -> int:
        return 3


@dataclass(frozen=True)
class RefBinding:
    target_param: str
    ref_step: str
    ref_path: str
    reference_pattern: str


@dataclass(frozen=True)
class SyntheticPlanCase:
    case_id: str
    topology_pattern: str
    reference_patterns: list[str]
    plan: dict[str, Any]
    dependency_edges: list[dict[str, Any]]
    notes: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


class EdgeUsageCounter:
    def __init__(self) -> None:
        self._counts: Counter[tuple[str, str, str, str]] = Counter()

    def count(self, edge: EdgeCandidate) -> int:
        return self._counts[_edge_key(edge)]

    def record_edge(self, edge: EdgeCandidate) -> None:
        self._counts[_edge_key(edge)] += 1

    def record_edges(self, edges: list[EdgeCandidate] | list[dict[str, Any]]) -> None:
        for edge in edges:
            if isinstance(edge, EdgeCandidate):
                self.record_edge(edge)
            else:
                self._counts[(edge["from_op"], edge["from_path"], edge["to_op"], edge["to_param"])] += 1


def collect_operator_schema_inventory() -> dict[str, OperatorSchemaInfo]:
    inventory: dict[str, OperatorSchemaInfo] = {}
    registry = OperatorRegistry.get_registry_model()
    for op, info in sorted(registry.operators.items()):
        input_model = info.input_model
        output_model = info.output_model
        output_paths = sorted(collect_schema_attributes(output_model).keys())
        if not output_paths:
            continue
        normalized_op = OPERATOR_ALIASES.get(op, op)
        inventory[normalized_op] = OperatorSchemaInfo(
            op=normalized_op,
            input_model=input_model.__name__,
            output_model=output_model.__name__,
            input_fields=sorted(input_model.model_fields.keys()),
            output_paths=output_paths,
        )
    return inventory


def build_high_recall_edge_pool(
    inventory: dict[str, OperatorSchemaInfo] | None = None,
) -> list[EdgeCandidate]:
    """Build all schema-legal output leaf -> target input combinations.

    This intentionally avoids semantic filtering. The only requirement is that
    the source output path and target input field exist in their operator
    schemas. Naturalness is evaluated later by query generation and judge.
    """
    inventory = inventory or collect_operator_schema_inventory()
    edges: list[EdgeCandidate] = []
    for source_op, source_info in sorted(inventory.items()):
        for source_path in source_info.output_paths:
            for target_op, target_info in sorted(inventory.items()):
                for target_param in target_info.input_fields:
                    edges.append(
                        EdgeCandidate(
                            source_op=source_op,
                            source_path=source_path,
                            target_op=target_op,
                            target_param=target_param,
                        )
                    )
    return edges


def generate_synthetic_plan_cases(
    *,
    seed: int = 0,
    max_cases: int | None = None,
) -> list[SyntheticPlanCase]:
    inventory = collect_operator_schema_inventory()
    edge_pool = build_high_recall_edge_pool(inventory)
    targets = build_coverage_targets(inventory, edge_pool)
    minimum_cases = len(targets) + len(SELF_DOMAIN_ALLOW_LIST) * len(REFERENCE_PATTERNS)
    total_cases = max_cases if max_cases is not None else minimum_cases
    if total_cases < minimum_cases:
        warnings.warn(
            f"max_cases={total_cases} is below minimum coverage target {minimum_cases}; "
            f"generating {minimum_cases} cases",
            UserWarning,
            stacklevel=2,
        )
        total_cases = minimum_cases
    rng = random.Random(seed)
    if not targets or not edge_pool:
        return []

    cases: list[SyntheticPlanCase] = []
    edge_counter = EdgeUsageCounter()
    topology_counter: Counter[str] = Counter()
    ref_pattern_counter: Counter[str] = Counter()
    topo_ref_covered: set[tuple[str, str]] = set()
    shuffled_targets = list(targets)
    rng.shuffle(shuffled_targets)

    def _append_case(primary: EdgeCandidate, topology: str, ref_pattern: str) -> None:
        case = _materialize_case(
            case_idx=len(cases),
            primary=primary,
            topology=topology,
            reference_pattern=ref_pattern,
            edge_pool=edge_pool,
            inventory=inventory,
            rng=rng,
            counter=edge_counter,
        )
        cases.append(case)
        topology_counter[case.topology_pattern] += 1
        for pattern in case.reference_patterns:
            ref_pattern_counter[pattern] += 1
            topo_ref_covered.add((case.topology_pattern, pattern))

    for target in shuffled_targets:
        primary = _pick_edge(
            edge_pool,
            counter=edge_counter,
            rng=rng,
            target_op=target.target_op,
            target_param=target.target_param,
            ref_constraint=REF_PATTERN_CONSTRAINTS[target.reference_pattern],
        )
        compatible_topos = [
            topology
            for topology in MAIN_TOPOLOGIES
            if _topo_compatible(topology, target.reference_pattern)
        ]
        topology = _pick_topology(
            compatible_topos,
            topology_counter,
            rng,
            ref_pattern=target.reference_pattern,
            covered_pairs=topo_ref_covered,
        )
        _append_case(primary, topology, target.reference_pattern)

    self_domain_ops = sorted(
        op
        for op in SELF_DOMAIN_ALLOW_LIST
        if any(edge.source_op == op and edge.target_op == op for edge in edge_pool)
    )
    for ref_pattern in REFERENCE_PATTERNS:
        compatible_ops = [
            op
            for op in self_domain_ops
            if any(
                edge.source_op == op
                and edge.target_op == op
                and REF_PATTERN_CONSTRAINTS[ref_pattern](edge)
                for edge in edge_pool
            )
        ] or self_domain_ops
        for op in compatible_ops:
            primary = _pick_edge(
                edge_pool,
                counter=edge_counter,
                rng=rng,
                source_op=op,
                target_op=op,
                ref_constraint=REF_PATTERN_CONSTRAINTS[ref_pattern],
            )
            _append_case(primary, "self_domain_chain", ref_pattern)

    # If some allow-listed ops cannot express array-only patterns, still add one
    # non-array self-domain chain so every allowed domain appears in Phase 2.
    covered_self_ops = {
        step["op"]
        for case in cases
        if case.topology_pattern == "self_domain_chain"
        for step in case.plan["steps"]
    }
    for op in self_domain_ops:
        if op in covered_self_ops:
            continue
        primary = _pick_edge(edge_pool, counter=edge_counter, rng=rng, source_op=op, target_op=op)
        _append_case(primary, "self_domain_chain", "direct_ref")

    # Phase 2 intentionally filters impossible self-domain pairs like
    # poi_search+wildcard_ref, so top up to the 333-case minimum if needed.
    while len(cases) < minimum_cases:
        for ref_pattern in REFERENCE_PATTERNS:
            primary = _pick_edge(
                edge_pool,
                counter=edge_counter,
                rng=rng,
                ref_constraint=REF_PATTERN_CONSTRAINTS[ref_pattern],
            )
            _append_case(primary, "self_domain_chain", ref_pattern)
            if len(cases) >= minimum_cases:
                break

    # Phase 3: every output leaf must be referenced at least once. The primary
    # coverage matrix is input/ref-pattern oriented, so complete source coverage
    # explicitly before honoring any larger max_cases fill request.
    for source_op, source_path in _unused_output_keys(cases, inventory):
        primary = _pick_edge(
            edge_pool,
            counter=edge_counter,
            rng=rng,
            source_op=source_op,
            source_path=source_path,
        )
        _append_case(primary, "chain", "direct_ref")

    remaining_outputs = _unused_output_keys(cases, inventory)
    if remaining_outputs:
        preview = ", ".join(f"{op}.{path}" for op, path in remaining_outputs[:5])
        raise RuntimeError(f"failed to cover output leaf fields: {preview}")

    while len(cases) < total_cases:
        ref_pattern = _least_used(list(REFERENCE_PATTERNS), ref_pattern_counter, rng)
        topology = _pick_topology(
            list(MAIN_TOPOLOGIES),
            topology_counter,
            rng,
            ref_pattern=ref_pattern,
            covered_pairs=topo_ref_covered,
        )
        primary = _pick_edge(
            edge_pool,
            counter=edge_counter,
            rng=rng,
            ref_constraint=REF_PATTERN_CONSTRAINTS[ref_pattern],
        )
        _append_case(primary, topology, ref_pattern)

    return cases


def build_coverage_targets(
    inventory: dict[str, OperatorSchemaInfo] | None = None,
    edge_pool: list[EdgeCandidate] | None = None,
) -> list[CoverageTarget]:
    inventory = inventory or collect_operator_schema_inventory()
    edge_pool = edge_pool or build_high_recall_edge_pool(inventory)
    targets: list[CoverageTarget] = []
    for op, info in sorted(inventory.items()):
        for field in info.input_fields:
            for reference_pattern in REFERENCE_PATTERNS:
                constraint = REF_PATTERN_CONSTRAINTS[reference_pattern]
                if not any(
                    edge.target_op == op
                    and edge.target_param == field
                    and constraint(edge)
                    for edge in edge_pool
                ):
                    continue
                targets.append(CoverageTarget(op, field, reference_pattern))
    return targets


def _topo_compatible(topology: str, reference_pattern: str) -> bool:
    if reference_pattern == "multi_ref_query":
        return topology in {"join", "parallel_then_action", "gather_reduce"}
    if reference_pattern == "indexed_ref" and topology == "map_foreach":
        return False
    return topology in TOPOLOGY_PATTERNS


def _pick_topology(
    compatible_topos: list[str],
    topology_counter: Counter[str],
    rng: random.Random,
    *,
    ref_pattern: str,
    covered_pairs: set[tuple[str, str]],
) -> str:
    candidates = [
        topology
        for topology in compatible_topos
        if _topo_compatible(topology, ref_pattern)
    ]
    uncovered = [topology for topology in candidates if (topology, ref_pattern) not in covered_pairs]
    if uncovered:
        return _least_used(uncovered, topology_counter, rng)
    return _least_used(candidates, topology_counter, rng)


def _least_used(
    values: list[str] | tuple[str, ...],
    counter: Counter[str],
    rng: random.Random,
) -> str:
    min_count = min(counter[value] for value in values)
    return rng.choice([value for value in values if counter[value] == min_count])


def _pick_edge(
    edge_pool: list[EdgeCandidate],
    counter: EdgeUsageCounter,
    rng: random.Random,
    *,
    source_op: str | None = None,
    source_path: str | None = None,
    target_op: str | None = None,
    target_param: str | None = None,
    exclude: set[EdgeCandidate] | set[tuple[str, str, str, str]] | None = None,
    ref_constraint: Callable[[EdgeCandidate], bool] | None = None,
    top_k: int = 5,
) -> EdgeCandidate:
    exclude = exclude or set()

    def _matches(edge: EdgeCandidate, *, strict: bool, use_ref_constraint: bool) -> bool:
        if edge in exclude or _edge_key(edge) in exclude:
            return False
        if not strict:
            return True
        if source_op is not None and edge.source_op != source_op:
            return False
        if source_path is not None and edge.source_path != source_path:
            return False
        if target_op is not None and edge.target_op != target_op:
            return False
        if target_param is not None and edge.target_param != target_param:
            return False
        if use_ref_constraint and ref_constraint is not None and not ref_constraint(edge):
            return False
        return True

    candidates = [edge for edge in edge_pool if _matches(edge, strict=True, use_ref_constraint=True)]
    if not candidates and ref_constraint is not None:
        candidates = [edge for edge in edge_pool if _matches(edge, strict=True, use_ref_constraint=False)]
    if not candidates:
        candidates = [edge for edge in edge_pool if _matches(edge, strict=False, use_ref_constraint=False)]
    if not candidates:
        candidates = list(edge_pool)
    candidates = sorted(candidates, key=lambda edge: (counter.count(edge), _edge_key(edge)))
    top = candidates[: max(1, min(top_k, len(candidates)))]
    return rng.choice(top)


def build_coverage_report(
    cases: list[SyntheticPlanCase],
    inventory: dict[str, OperatorSchemaInfo] | None = None,
) -> dict[str, Any]:
    inventory = inventory or collect_operator_schema_inventory()
    all_outputs = {
        f"{op}.{path}"
        for op, info in inventory.items()
        for path in info.output_paths
    }
    all_inputs = {
        f"{op}.{field}"
        for op, info in inventory.items()
        for field in info.input_fields
    }
    output_usage: dict[str, int] = {}
    input_usage: dict[str, int] = {}
    tool_edges: dict[str, int] = {}
    reference_patterns: dict[str, int] = {}
    topology_patterns: dict[str, int] = {}
    input_ref_usage: set[tuple[str, str, str]] = set()
    topology_ref_usage: set[tuple[str, str]] = set()
    tool_pair_ref_usage: set[tuple[str, str, str]] = set()
    output_input_usage: set[tuple[str, str, str, str]] = set()
    tool_pair_ref_counts: Counter[tuple[str, str, str]] = Counter()

    for case in cases:
        topology_patterns[case.topology_pattern] = topology_patterns.get(case.topology_pattern, 0) + 1
        for pattern in case.reference_patterns:
            topology_ref_usage.add((case.topology_pattern, pattern))
        for edge in case.dependency_edges:
            output_key = f"{edge['from_op']}.{edge['from_path']}"
            input_key = f"{edge['to_op']}.{edge['to_param']}"
            tool_key = f"{edge['from_op']}->{edge['to_op']}"
            ref_pattern = str(edge["reference_pattern"])
            output_usage[output_key] = output_usage.get(output_key, 0) + 1
            input_usage[input_key] = input_usage.get(input_key, 0) + 1
            tool_edges[tool_key] = tool_edges.get(tool_key, 0) + 1
            reference_patterns[ref_pattern] = reference_patterns.get(ref_pattern, 0) + 1
            input_ref_usage.add((edge["to_op"], edge["to_param"], ref_pattern))
            tool_pair_ref_usage.add((edge["from_op"], edge["to_op"], ref_pattern))
            tool_pair_ref_counts[(edge["from_op"], edge["to_op"], ref_pattern)] += 1
            output_input_usage.add((edge["from_op"], edge["from_path"], edge["to_op"], edge["to_param"]))

    unused_outputs = _group_unused(all_outputs - output_usage.keys())
    unused_inputs = _group_unused(all_inputs - input_usage.keys())
    input_ref_targets = {
        (target.target_op, target.target_param, target.reference_pattern)
        for target in build_coverage_targets(inventory)
    }
    topology_ref_targets = {
        (topology, ref_pattern)
        for topology in TOPOLOGY_PATTERNS
        for ref_pattern in REFERENCE_PATTERNS
        if _topo_compatible(topology, ref_pattern)
    }
    tool_pair_total = len(inventory) * len(inventory) * len(REFERENCE_PATTERNS)
    output_input_total = len(all_outputs) * len(all_inputs)
    return {
        "case_count": len(cases),
        "total_output_fields": len(all_outputs),
        "used_output_field_count": len(output_usage),
        "unused_output_fields": unused_outputs,
        "total_target_inputs": len(all_inputs),
        "used_target_input_count": len(input_usage),
        "unused_target_inputs": unused_inputs,
        "output_field_usage": dict(sorted(output_usage.items())),
        "target_input_usage": dict(sorted(input_usage.items())),
        "tool_edge_coverage": dict(sorted(tool_edges.items())),
        "reference_pattern_coverage": dict(sorted(reference_patterns.items())),
        "topology_pattern_coverage": dict(sorted(topology_patterns.items())),
        "input_x_ref_pattern": _coverage_axis(input_ref_targets, input_ref_usage),
        "topology_x_ref_pattern": _coverage_axis(topology_ref_targets, topology_ref_usage),
        "tool_pair_x_ref_pattern": {
            "total": tool_pair_total,
            "covered": len(tool_pair_ref_usage),
            "coverage_rate": _coverage_rate(len(tool_pair_ref_usage), tool_pair_total),
            "least_covered": _least_covered_tool_pair_refs(inventory, tool_pair_ref_counts),
            "observed": _stringify_tuple_set(tool_pair_ref_usage),
        },
        "output_x_input": {
            "total": output_input_total,
            "covered": len(output_input_usage),
            "coverage_rate": _coverage_rate(len(output_input_usage), output_input_total),
            "observed": _stringify_tuple_set(output_input_usage),
        },
    }


def write_synthetic_case_file(cases: list[SyntheticPlanCase], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 3,
        "case_count": len(cases),
        "coverage_report": build_coverage_report(cases),
        "cases": [case.to_json_dict() for case in cases],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_coverage_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def load_synthetic_case_file(path: Path) -> list[SyntheticPlanCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["cases"] if isinstance(payload, dict) and "cases" in payload else payload
    return [SyntheticPlanCase(**row) for row in rows]


def validate_synthetic_case(case: SyntheticPlanCase) -> list[str]:
    issues: list[str] = []
    inventory = collect_operator_schema_inventory()
    steps = case.plan.get("steps") or []
    step_by_id = {step.get("step_id"): step for step in steps if isinstance(step, dict)}
    declared_outputs = {
        step_id: set(_extract_paths(step.get("outputs") or {}))
        for step_id, step in step_by_id.items()
    }

    for step in steps:
        step_id = str(step.get("step_id"))
        op = str(step.get("op"))
        if op not in inventory:
            issues.append(f"{step_id}: unknown op {op}")
            continue
        input_fields = set(inventory[op].input_fields)
        output_paths = set(inventory[op].output_paths)
        inputs = step.get("inputs") or {}
        if not isinstance(inputs, dict):
            issues.append(f"{step_id}: inputs must be dict")
            continue
        for key in inputs:
            if key not in input_fields:
                issues.append(f"{step_id}: input field {key} not in {op}")
        for path in _extract_paths(step.get("outputs") or {}):
            if path not in output_paths:
                issues.append(f"{step_id}: output path {path} not in {op}")
        for ref_step, ref_path in _extract_refs(inputs):
            _validate_step_ref(
                issues,
                step_id=step_id,
                step=step,
                ref_step=ref_step,
                ref_path=ref_path,
                step_by_id=step_by_id,
                declared_outputs=declared_outputs,
            )
        for ref_step, ref_path in _extract_refs(step.get("condition")):
            _validate_step_ref(
                issues,
                step_id=step_id,
                step=step,
                ref_step=ref_step,
                ref_path=ref_path,
                step_by_id=step_by_id,
                declared_outputs=declared_outputs,
            )
        gather = step.get("gather") or {}
        if isinstance(gather, dict):
            for ref_step, ref_path in _extract_refs(gather.get("sources") or []):
                _validate_step_ref(
                    issues,
                    step_id=step_id,
                    step=step,
                    ref_step=ref_step,
                    ref_path=ref_path,
                    step_by_id=step_by_id,
                    declared_outputs=declared_outputs,
                )
        if "iteration" in step:
            iteration = step.get("iteration")
            if not isinstance(iteration, dict):
                issues.append(f"{step_id}: iteration must be dict")
                continue
            _validate_iteration_refs(
                issues,
                step_id=step_id,
                step=step,
                inputs=inputs,
                iteration=iteration,
                step_by_id=step_by_id,
                declared_outputs=declared_outputs,
            )

    for edge in case.dependency_edges:
        from_step = step_by_id.get(edge.get("from_step"))
        to_step = step_by_id.get(edge.get("to_step"))
        if from_step is None:
            issues.append(f"edge: from_step {edge.get('from_step')} does not exist")
        elif from_step.get("op") != edge.get("from_op"):
            issues.append(
                f"edge: from_step {edge['from_step']} op {from_step.get('op')} != {edge['from_op']}"
            )
        if to_step is None:
            issues.append(f"edge: to_step {edge.get('to_step')} does not exist")
        elif to_step.get("op") != edge.get("to_op"):
            issues.append(
                f"edge: to_step {edge['to_step']} op {to_step.get('op')} != {edge['to_op']}"
            )
        if to_step is not None and edge.get("from_step") not in set(to_step.get("depends_on") or []):
            issues.append(f"edge: {edge['from_step']} missing from {edge['to_step']}.depends_on")

        if edge["from_op"] not in inventory:
            issues.append(f"edge: unknown from_op {edge['from_op']}")
        elif edge["from_path"] not in inventory[edge["from_op"]].output_paths:
            issues.append(f"edge: invalid source {edge['from_op']}.{edge['from_path']}")
        if edge["to_op"] not in inventory:
            issues.append(f"edge: unknown to_op {edge['to_op']}")
        elif edge["to_param"] not in inventory[edge["to_op"]].input_fields:
            issues.append(f"edge: invalid target {edge['to_op']}.{edge['to_param']}")
        if edge["from_path"] not in declared_outputs.get(edge["from_step"], set()):
            issues.append(f"edge: {edge['from_step']}.{edge['from_path']} not declared")
        if to_step is not None:
            inputs = to_step.get("inputs") or {}
            if edge["to_param"] not in inputs:
                issues.append(f"edge: target input {edge['to_step']}.{edge['to_param']} missing")
            elif not _value_matches_reference_pattern(inputs[edge["to_param"]], str(edge["reference_pattern"])):
                issues.append(
                    f"edge: target input {edge['to_step']}.{edge['to_param']} does not match {edge['reference_pattern']}"
                )
            refs = edge.get("refs") or []
            ref_keys = {
                (str(ref.get("step")), normalize_ref_path(str(ref.get("path"))))
                for ref in refs
                if isinstance(ref, dict)
            }
            if edge["reference_pattern"] == "multi_ref_query" and len(ref_keys) < 2:
                issues.append(f"edge: multi_ref_query for {edge['to_step']}.{edge['to_param']} has fewer than 2 refs")
            for ref in refs:
                if not isinstance(ref, dict):
                    issues.append(f"edge: malformed ref metadata for {edge['to_step']}.{edge['to_param']}")
                    continue
                ref_step = str(ref.get("step"))
                ref_path = str(ref.get("path"))
                _validate_step_ref(
                    issues,
                    step_id=str(edge["to_step"]),
                    step=to_step,
                    ref_step=ref_step,
                    ref_path=ref_path,
                    step_by_id=step_by_id,
                    declared_outputs=declared_outputs,
                    allow_prefix=True,
                )
                if not _target_step_represents_ref(to_step, edge["to_param"], ref_step, ref_path):
                    issues.append(
                        f"edge: ref {ref_step}.{normalize_ref_path(ref_path)} not represented in {edge['to_step']}.{edge['to_param']}"
                    )

    return issues


def build_reverse_query_prompt(case: SyntheticPlanCase) -> str:
    return (
        "你是车机场景复杂用户问题生成器。请根据给定 DAG plan，反向生成一个真实用户日常生活中"
        "可能向 agent 助手提出的中文 query。\n\n"
        "该 DAG 没有预设用户 goal；它只提供工具调用、参数、输出字段和跨步骤引用关系。"
        "你需要理解这些结构，反推出一个自然的用户请求。\n\n"
        "要求：\n"
        "- query 必须自然，像用户一次性提出的请求，不要逐条复述 JSON。\n"
        "- query 必须尽量覆盖工具调用顺序、参数约束和跨步骤字段依赖。\n"
        "- 不要在 query 中出现 $s1、$s2、step_id、op、DAG、JSON schema 等实现细节。\n"
        "- 允许结构连接组合略显抽象，但 query 必须表达为用户可理解的日常生活需求。\n"
        "- 不要编造与 plan 完全无关的业务目标。\n\n"
        "字段说明：\n"
        "- iteration 表示对上游列表元素逐个重复执行。\n"
        "- condition 表示满足条件时执行步骤。\n"
        "- gather 表示聚合多个上游结果。\n\n"
        "请输出 JSON：\n"
        "{\n"
        "  \"query\": \"...\",\n"
        "  \"notes\": \"一句话说明 query 覆盖了哪些依赖\"\n"
        "}\n\n"
        "dependency_edges:\n"
        f"{json.dumps(_prompt_dependency_edges(case), ensure_ascii=False, indent=2)}\n\n"
        "plan:\n"
        f"{json.dumps(case.plan, ensure_ascii=False, indent=2)}"
    )


def build_output_schema_subset(paths: list[str]) -> dict[str, Any]:
    root: dict[str, Any] = {}
    for path in sorted(paths):
        _insert_path(root, path.split("."))
    return root


def normalize_ref_path(path: str) -> str:
    return re.sub(r"\[(?:\d+|\*)\]", "[]", path)


def _edge_key(edge: EdgeCandidate) -> tuple[str, str, str, str]:
    return (edge.source_op, edge.source_path, edge.target_op, edge.target_param)


def _materialize_case(
    *,
    case_idx: int,
    primary: EdgeCandidate,
    topology: str,
    reference_pattern: str,
    edge_pool: list[EdgeCandidate],
    inventory: dict[str, OperatorSchemaInfo],
    rng: random.Random,
    counter: EdgeUsageCounter,
) -> SyntheticPlanCase:
    if topology == "branch":
        return _materialize_branch(case_idx, primary, reference_pattern, edge_pool, inventory, rng, counter)
    if topology == "join":
        return _materialize_join(case_idx, primary, reference_pattern, edge_pool, inventory, rng, counter)
    if topology == "fanout_join":
        return _materialize_fanout_join(case_idx, primary, reference_pattern, edge_pool, inventory, rng, counter)
    if topology == "parallel_then_action":
        return _materialize_parallel_then_action(case_idx, primary, reference_pattern, edge_pool, inventory, rng, counter)
    if topology == "deep_chain":
        return _materialize_deep_chain(case_idx, primary, reference_pattern, edge_pool, inventory, rng, counter)
    if topology == "map_foreach":
        return _materialize_map_foreach(case_idx, primary, reference_pattern, edge_pool, inventory, rng, counter)
    if topology == "conditional_branch":
        return _materialize_conditional_branch(case_idx, primary, reference_pattern, edge_pool, inventory, rng, counter)
    if topology == "gather_reduce":
        return _materialize_gather_reduce(case_idx, primary, reference_pattern, edge_pool, inventory, rng, counter)
    if topology == "self_domain_chain":
        return _materialize_self_domain_chain(case_idx, primary, reference_pattern, edge_pool, inventory, rng, counter)
    return _materialize_chain(case_idx, primary, reference_pattern, edge_pool, inventory, rng, counter, topology=topology)


def _materialize_chain(
    case_idx: int,
    primary: EdgeCandidate,
    reference_pattern: str,
    edge_pool: list[EdgeCandidate],
    inventory: dict[str, OperatorSchemaInfo],
    rng: random.Random,
    counter: EdgeUsageCounter,
    *,
    topology: str,
) -> SyntheticPlanCase:
    secondary = _pick_edge(edge_pool, counter=counter, rng=rng, source_op=primary.target_op)
    s1 = _source_step("s1", primary.source_op, primary.source_path, case_idx)
    s2_output = secondary.source_path
    binding1 = RefBinding(primary.target_param, "s1", primary.source_path, reference_pattern)
    s2 = _target_step(
        "s2",
        primary.target_op,
        depends_on=["s1"],
        target_output_paths=[s2_output],
        bindings=[binding1],
        case_idx=case_idx,
    )
    s3_ref_pattern = _rotated_reference_pattern(reference_pattern, 1, edge=secondary)
    binding2 = RefBinding(secondary.target_param, "s2", secondary.source_path, s3_ref_pattern)
    s3 = _target_step(
        "s3",
        secondary.target_op,
        depends_on=["s2"],
        target_output_paths=[_first_output(secondary.target_op, inventory)],
        bindings=[binding2],
        case_idx=case_idx + 1,
    )
    edges = [
        _edge_from_binding("s1", primary, "s2", binding1),
        _edge_from_binding("s2", secondary, "s3", binding2),
    ]
    counter.record_edges([primary, secondary])
    return _case(case_idx, topology, [reference_pattern, s3_ref_pattern], [s1, s2, s3], edges)


def _materialize_branch(
    case_idx: int,
    primary: EdgeCandidate,
    reference_pattern: str,
    edge_pool: list[EdgeCandidate],
    inventory: dict[str, OperatorSchemaInfo],
    rng: random.Random,
    counter: EdgeUsageCounter,
) -> SyntheticPlanCase:
    sibling_target = _pick_edge(edge_pool, counter=counter, rng=rng)
    sibling = EdgeCandidate(primary.source_op, primary.source_path, sibling_target.target_op, sibling_target.target_param)
    second_pattern = _rotated_reference_pattern(reference_pattern, 2, edge=sibling)
    s1 = _source_step("s1", primary.source_op, primary.source_path, case_idx)
    binding1 = RefBinding(primary.target_param, "s1", primary.source_path, reference_pattern)
    s2 = _target_step(
        "s2",
        primary.target_op,
        depends_on=["s1"],
        target_output_paths=[_first_output(primary.target_op, inventory)],
        bindings=[binding1],
        case_idx=case_idx,
    )
    binding2 = RefBinding(sibling.target_param, "s1", primary.source_path, second_pattern)
    s3 = _target_step(
        "s3",
        sibling.target_op,
        depends_on=["s1"],
        target_output_paths=[_first_output(sibling.target_op, inventory)],
        bindings=[binding2],
        case_idx=case_idx + 1,
    )
    edges = [
        _edge_from_binding("s1", primary, "s2", binding1),
        _edge_from_binding("s1", sibling, "s3", binding2),
    ]
    counter.record_edges([primary, sibling])
    return _case(case_idx, "branch", [reference_pattern, second_pattern], [s1, s2, s3], edges)


def _materialize_join(
    case_idx: int,
    primary: EdgeCandidate,
    reference_pattern: str,
    edge_pool: list[EdgeCandidate],
    inventory: dict[str, OperatorSchemaInfo],
    rng: random.Random,
    counter: EdgeUsageCounter,
) -> SyntheticPlanCase:
    companion = _pick_edge(edge_pool, counter=counter, rng=rng, target_op=primary.target_op)
    companion_target_param = (
        primary.target_param
        if reference_pattern == "multi_ref_query"
        else _alternate_target_param(inventory, primary.target_op, primary.target_param) or primary.target_param
    )
    companion_pattern = (
        "multi_ref_query"
        if reference_pattern == "multi_ref_query"
        else reference_pattern if companion_target_param == primary.target_param else "object_param_ref"
    )
    companion = EdgeCandidate(
        companion.source_op,
        companion.source_path,
        primary.target_op,
        companion_target_param,
    )
    s1 = _source_step("s1", primary.source_op, primary.source_path, case_idx)
    s2 = _source_step("s2", companion.source_op, companion.source_path, case_idx + 1)
    binding1 = RefBinding(primary.target_param, "s1", primary.source_path, reference_pattern)
    binding2 = RefBinding(companion.target_param, "s2", companion.source_path, companion_pattern)
    bindings = [binding1, binding2]
    s3 = _target_step(
        "s3",
        primary.target_op,
        depends_on=["s1", "s2"],
        target_output_paths=[_first_output(primary.target_op, inventory)],
        bindings=bindings,
        case_idx=case_idx,
    )
    binding1_refs = _same_param_bindings(bindings, binding1)
    binding2_refs = _same_param_bindings(bindings, binding2)
    edges = [
        _edge_from_binding("s1", primary, "s3", binding1, ref_bindings=binding1_refs),
        _edge_from_binding("s2", companion, "s3", binding2, ref_bindings=binding2_refs),
    ]
    counter.record_edges([primary, companion])
    return _case(case_idx, "join", [reference_pattern, companion_pattern], [s1, s2, s3], edges)


def _materialize_fanout_join(
    case_idx: int,
    primary: EdgeCandidate,
    reference_pattern: str,
    edge_pool: list[EdgeCandidate],
    inventory: dict[str, OperatorSchemaInfo],
    rng: random.Random,
    counter: EdgeUsageCounter,
) -> SyntheticPlanCase:
    branch_target = _pick_edge(edge_pool, counter=counter, rng=rng)
    branch_target = EdgeCandidate(primary.source_op, primary.source_path, branch_target.target_op, branch_target.target_param)
    join_edge_a = _pick_edge(edge_pool, counter=counter, rng=rng, source_op=primary.target_op)
    alternate_join_param = _alternate_target_param(inventory, join_edge_a.target_op, join_edge_a.target_param)
    join_edge_b = _pick_edge(
        edge_pool,
        counter=counter,
        rng=rng,
        source_op=branch_target.target_op,
        target_op=join_edge_a.target_op,
        target_param=alternate_join_param or join_edge_a.target_param,
    )
    if join_edge_b.source_op != branch_target.target_op or join_edge_b.target_op != join_edge_a.target_op:
        join_edge_b = EdgeCandidate(
            branch_target.target_op,
            _first_output(branch_target.target_op, inventory),
            join_edge_a.target_op,
            alternate_join_param or join_edge_a.target_param,
        )
    s1 = _source_step("s1", primary.source_op, primary.source_path, case_idx)
    s2_output = join_edge_a.source_path
    s3_output = join_edge_b.source_path
    binding1 = RefBinding(primary.target_param, "s1", primary.source_path, reference_pattern)
    binding2 = RefBinding(branch_target.target_param, "s1", primary.source_path, "embedded_query_ref")
    join_pattern = "multi_ref_query" if join_edge_b.target_param == join_edge_a.target_param else "object_param_ref"
    join_pattern_b = join_pattern if join_pattern == "multi_ref_query" else "mixed_literal_ref"
    join_binding_a = RefBinding(join_edge_a.target_param, "s2", s2_output, join_pattern)
    join_binding_b = RefBinding(join_edge_b.target_param, "s3", s3_output, join_pattern_b)
    join_bindings = [join_binding_a, join_binding_b]
    s2 = _target_step("s2", primary.target_op, depends_on=["s1"], target_output_paths=[s2_output], bindings=[binding1], case_idx=case_idx)
    s3 = _target_step("s3", branch_target.target_op, depends_on=["s1"], target_output_paths=[s3_output], bindings=[binding2], case_idx=case_idx + 1)
    s4 = _target_step("s4", join_edge_a.target_op, depends_on=["s2", "s3"], target_output_paths=[_first_output(join_edge_a.target_op, inventory)], bindings=join_bindings, case_idx=case_idx + 2)
    edges = [
        _edge_from_binding("s1", primary, "s2", binding1),
        _edge_from_binding("s1", branch_target, "s3", binding2),
        _edge_from_binding("s2", join_edge_a, "s4", join_binding_a, ref_bindings=_same_param_bindings(join_bindings, join_binding_a)),
        _edge_from_binding("s3", join_edge_b, "s4", join_binding_b, ref_bindings=_same_param_bindings(join_bindings, join_binding_b)),
    ]
    counter.record_edges([primary, branch_target, join_edge_a, join_edge_b])
    return _case(case_idx, "fanout_join", [reference_pattern, "embedded_query_ref", "multi_ref_query", join_pattern_b], [s1, s2, s3, s4], edges)


def _materialize_parallel_then_action(
    case_idx: int,
    primary: EdgeCandidate,
    reference_pattern: str,
    edge_pool: list[EdgeCandidate],
    inventory: dict[str, OperatorSchemaInfo],
    rng: random.Random,
    counter: EdgeUsageCounter,
) -> SyntheticPlanCase:
    companion = _pick_edge(edge_pool, counter=counter, rng=rng)
    companion_target_param = (
        primary.target_param
        if reference_pattern == "multi_ref_query"
        else _alternate_target_param(inventory, primary.target_op, primary.target_param) or primary.target_param
    )
    companion_pattern = (
        "multi_ref_query"
        if reference_pattern == "multi_ref_query"
        else reference_pattern if companion_target_param == primary.target_param else "object_param_ref"
    )
    action_edge = EdgeCandidate(
        primary.source_op,
        primary.source_path,
        primary.target_op,
        primary.target_param,
    )
    s1 = _source_step("s1", primary.source_op, primary.source_path, case_idx)
    s2 = _source_step("s2", companion.source_op, companion.source_path, case_idx + 1)
    binding1 = RefBinding(action_edge.target_param, "s1", primary.source_path, reference_pattern)
    binding2 = RefBinding(
        companion_target_param,
        "s2",
        companion.source_path,
        companion_pattern,
    )
    s3 = _target_step(
        "s3",
        action_edge.target_op,
        depends_on=["s1", "s2"],
        target_output_paths=[_first_output(action_edge.target_op, inventory)],
        bindings=[binding1, binding2],
        case_idx=case_idx,
    )
    companion_edge = EdgeCandidate(
        companion.source_op,
        companion.source_path,
        action_edge.target_op,
        companion_target_param,
    )
    bindings = [binding1, binding2]
    edges = [
        _edge_from_binding("s1", action_edge, "s3", binding1, ref_bindings=_same_param_bindings(bindings, binding1)),
        _edge_from_binding("s2", companion_edge, "s3", binding2, ref_bindings=_same_param_bindings(bindings, binding2)),
    ]
    counter.record_edges([action_edge, companion_edge])
    return _case(case_idx, "parallel_then_action", [reference_pattern, companion_pattern], [s1, s2, s3], edges)


def _materialize_deep_chain(
    case_idx: int,
    primary: EdgeCandidate,
    reference_pattern: str,
    edge_pool: list[EdgeCandidate],
    inventory: dict[str, OperatorSchemaInfo],
    rng: random.Random,
    counter: EdgeUsageCounter,
) -> SyntheticPlanCase:
    depth = rng.randint(4, 7)
    steps = [_source_step("s1", primary.source_op, primary.source_path, case_idx)]
    edges: list[dict[str, Any]] = []
    ref_patterns: list[str] = []
    used_edges: list[EdgeCandidate] = []
    current_edge = primary
    for idx in range(2, depth + 1):
        pattern = _rotated_reference_pattern(reference_pattern, idx - 2, edge=current_edge)
        next_edge = None
        if idx < depth:
            next_pattern = _rotated_reference_pattern(reference_pattern, idx - 1)
            next_edge = _pick_edge(
                edge_pool,
                counter=counter,
                rng=rng,
                source_op=current_edge.target_op,
                ref_constraint=REF_PATTERN_CONSTRAINTS[next_pattern],
            )
            output_path = next_edge.source_path
        else:
            output_path = _first_output(current_edge.target_op, inventory)

        previous_step = f"s{idx - 1}"
        binding = RefBinding(current_edge.target_param, previous_step, current_edge.source_path, pattern)
        step_id = f"s{idx}"
        steps.append(
            _target_step(
                step_id,
                current_edge.target_op,
                depends_on=[previous_step],
                target_output_paths=[output_path],
                bindings=[binding],
                case_idx=case_idx + idx,
            )
        )
        edges.append(_edge_from_binding(previous_step, current_edge, step_id, binding))
        used_edges.append(current_edge)
        ref_patterns.append(pattern)
        if next_edge is not None:
            current_edge = next_edge
    counter.record_edges(used_edges)
    return _case(case_idx, "deep_chain", ref_patterns, steps, edges)


def _materialize_map_foreach(
    case_idx: int,
    primary: EdgeCandidate,
    reference_pattern: str,
    edge_pool: list[EdgeCandidate],
    inventory: dict[str, OperatorSchemaInfo],
    rng: random.Random,
    counter: EdgeUsageCounter,
) -> SyntheticPlanCase:
    if "[]" not in primary.source_path:
        primary = _pick_edge(
            edge_pool,
            counter=counter,
            rng=rng,
            target_op=primary.target_op,
            target_param=primary.target_param,
            ref_constraint=lambda edge: "[]" in edge.source_path,
        )
    array_base, item_leaf = _array_iteration_parts(primary.source_path)
    s1 = _source_step("s1", primary.source_op, primary.source_path, case_idx)
    s2 = _target_step(
        "s2",
        primary.target_op,
        depends_on=["s1"],
        target_output_paths=[_first_output(primary.target_op, inventory)],
        bindings=[],
        case_idx=case_idx,
        iteration={"over": f"$s1.{array_base}[*]", "as": "$item"},
    )
    s2["inputs"][primary.target_param] = _render_item_ref_value(reference_pattern, f"$item.{item_leaf}")
    binding = RefBinding(primary.target_param, "s1", primary.source_path, reference_pattern)
    edges = [_edge_from_binding("s1", primary, "s2", binding)]
    counter.record_edge(primary)
    return _case(case_idx, "map_foreach", [reference_pattern], [s1, s2], edges)


def _materialize_conditional_branch(
    case_idx: int,
    primary: EdgeCandidate,
    reference_pattern: str,
    edge_pool: list[EdgeCandidate],
    inventory: dict[str, OperatorSchemaInfo],
    rng: random.Random,
    counter: EdgeUsageCounter,
) -> SyntheticPlanCase:
    sibling_target = _pick_edge(edge_pool, counter=counter, rng=rng)
    sibling = EdgeCandidate(primary.source_op, primary.source_path, sibling_target.target_op, sibling_target.target_param)
    s1 = _source_step("s1", primary.source_op, primary.source_path, case_idx)
    condition = f"{_ref('s1', primary.source_path, mode='first')} != ''"
    binding1 = RefBinding(primary.target_param, "s1", primary.source_path, reference_pattern)
    binding2 = RefBinding(sibling.target_param, "s1", primary.source_path, "conditional_ref")
    s2 = _target_step(
        "s2",
        primary.target_op,
        depends_on=["s1"],
        target_output_paths=[_first_output(primary.target_op, inventory)],
        bindings=[binding1],
        case_idx=case_idx,
        condition=condition,
    )
    s3 = _target_step(
        "s3",
        sibling.target_op,
        depends_on=["s1"],
        target_output_paths=[_first_output(sibling.target_op, inventory)],
        bindings=[binding2],
        case_idx=case_idx + 1,
        condition=f"not ({condition})",
    )
    edges = [
        _edge_from_binding("s1", primary, "s2", binding1),
        _edge_from_binding("s1", sibling, "s3", binding2),
    ]
    counter.record_edges([primary, sibling])
    return _case(case_idx, "conditional_branch", [reference_pattern, "conditional_ref"], [s1, s2, s3], edges)


def _materialize_gather_reduce(
    case_idx: int,
    primary: EdgeCandidate,
    reference_pattern: str,
    edge_pool: list[EdgeCandidate],
    inventory: dict[str, OperatorSchemaInfo],
    rng: random.Random,
    counter: EdgeUsageCounter,
) -> SyntheticPlanCase:
    n_sources = rng.randint(3, 4)
    source_edges = [primary]
    for _ in range(2, n_sources + 1):
        source_edges.append(_pick_edge(edge_pool, counter=counter, rng=rng))

    source_steps = [
        _source_step(f"s{idx}", edge.source_op, edge.source_path, case_idx + idx - 1)
        for idx, edge in enumerate(source_edges, 1)
    ]
    gather_step_id = f"s{n_sources + 1}"
    bindings = [
        RefBinding(primary.target_param, f"s{idx}", edge.source_path, reference_pattern)
        for idx, edge in enumerate(source_edges, 1)
    ]
    gather_refs = [
        _ref(f"s{idx}", edge.source_path, mode="first")
        for idx, edge in enumerate(source_edges, 1)
    ]
    gather_step = _target_step(
        gather_step_id,
        primary.target_op,
        depends_on=[f"s{idx}" for idx in range(1, n_sources + 1)],
        target_output_paths=[_first_output(primary.target_op, inventory)],
        bindings=bindings,
        case_idx=case_idx,
        gather={
            "sources": gather_refs,
            "strategy": "concat",
        },
    )
    gather_step["inputs"][primary.target_param] = _render_ref_value(reference_pattern, [
        (f"s{idx}", edge.source_path)
        for idx, edge in enumerate(source_edges, 1)
    ])
    edges = [
        _edge_from_binding(
            f"s{idx}",
            EdgeCandidate(edge.source_op, edge.source_path, primary.target_op, primary.target_param),
            gather_step_id,
            binding,
            ref_bindings=bindings,
        )
        for idx, (edge, binding) in enumerate(zip(source_edges, bindings), 1)
    ]
    counter.record_edges(source_edges)
    return _case(case_idx, "gather_reduce", [reference_pattern], source_steps + [gather_step], edges)


def _materialize_self_domain_chain(
    case_idx: int,
    primary: EdgeCandidate,
    reference_pattern: str,
    edge_pool: list[EdgeCandidate],
    inventory: dict[str, OperatorSchemaInfo],
    rng: random.Random,
    counter: EdgeUsageCounter,
) -> SyntheticPlanCase:
    op = primary.source_op if primary.source_op in SELF_DOMAIN_ALLOW_LIST else sorted(SELF_DOMAIN_ALLOW_LIST)[0]
    first = _pick_edge(
        edge_pool,
        counter=counter,
        rng=rng,
        source_op=op,
        target_op=op,
        ref_constraint=REF_PATTERN_CONSTRAINTS[reference_pattern],
    )
    if reference_pattern == "multi_ref_query":
        second = _pick_edge(
            edge_pool,
            counter=counter,
            rng=rng,
            source_op=op,
            target_op=op,
        )
        first = EdgeCandidate(first.source_op, first.source_path, op, first.target_param)
        second = EdgeCandidate(second.source_op, second.source_path, op, first.target_param)
        s1 = _source_step("s1", op, first.source_path, case_idx)
        s2 = _source_step("s2", op, second.source_path, case_idx + 1)
        bindings = [
            RefBinding(first.target_param, "s1", first.source_path, reference_pattern),
            RefBinding(first.target_param, "s2", second.source_path, reference_pattern),
        ]
        s3 = _target_step(
            "s3",
            op,
            depends_on=["s1", "s2"],
            target_output_paths=[_first_output(op, inventory)],
            bindings=bindings,
            case_idx=case_idx + 2,
        )
        edges = [
            _edge_from_binding("s1", first, "s3", bindings[0], ref_bindings=bindings),
            _edge_from_binding("s2", second, "s3", bindings[1], ref_bindings=bindings),
        ]
        counter.record_edges([first, second])
        return _case(case_idx, "self_domain_chain", [reference_pattern], [s1, s2, s3], edges)

    second = _pick_edge(
        edge_pool,
        counter=counter,
        rng=rng,
        source_op=op,
        target_op=op,
    )
    second_pattern = _rotated_reference_pattern(reference_pattern, 1, edge=second)
    s1 = _source_step("s1", op, first.source_path, case_idx)
    binding1 = RefBinding(first.target_param, "s1", first.source_path, reference_pattern)
    s2 = _target_step(
        "s2",
        op,
        depends_on=["s1"],
        target_output_paths=[second.source_path],
        bindings=[binding1],
        case_idx=case_idx,
    )
    binding2 = RefBinding(second.target_param, "s2", second.source_path, second_pattern)
    s3 = _target_step(
        "s3",
        op,
        depends_on=["s2"],
        target_output_paths=[_first_output(op, inventory)],
        bindings=[binding2],
        case_idx=case_idx + 1,
    )
    edges = [
        _edge_from_binding("s1", first, "s2", binding1),
        _edge_from_binding("s2", second, "s3", binding2),
    ]
    counter.record_edges([first, second])
    return _case(case_idx, "self_domain_chain", [reference_pattern, second_pattern], [s1, s2, s3], edges)


def _case(
    case_idx: int,
    topology: str,
    ref_patterns: list[str],
    steps: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> SyntheticPlanCase:
    return SyntheticPlanCase(
        case_id=f"{topology}_{case_idx:04d}",
        topology_pattern=topology,
        reference_patterns=sorted(set(ref_patterns), key=ref_patterns.index),
        plan={
            "steps": steps,
        },
        dependency_edges=edges,
        notes="high_recall_structural_synthetic_case",
    )


def _source_step(step_id: str, op: str, output_path: str, case_idx: int) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "op": op,
        "depends_on": [],
        "inputs": _seed_inputs(op, case_idx),
        "outputs": build_output_schema_subset([output_path]),
    }


def _target_step(
    step_id: str,
    op: str,
    *,
    depends_on: list[str],
    target_output_paths: list[str],
    bindings: list[RefBinding],
    case_idx: int,
    iteration: dict[str, Any] | None = None,
    condition: str | None = None,
    gather: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inputs = _seed_inputs(op, case_idx)
    grouped: dict[str, list[RefBinding]] = {}
    for binding in bindings:
        grouped.setdefault(binding.target_param, []).append(binding)
    for target_param, target_bindings in grouped.items():
        refs = [(binding.ref_step, binding.ref_path) for binding in target_bindings]
        inputs[target_param] = _render_ref_value(target_bindings[0].reference_pattern, refs)
    step = {
        "step_id": step_id,
        "op": op,
        "depends_on": depends_on,
        "inputs": inputs,
        "outputs": build_output_schema_subset(target_output_paths),
    }
    if iteration is not None:
        step["iteration"] = iteration
    if condition is not None:
        step["condition"] = condition
    if gather is not None:
        step["gather"] = gather
    return step


def _seed_inputs(op: str, case_idx: int) -> dict[str, Any]:
    if op == "poi_search":
        poi_types = ["火锅店", "充电站", "停车场", "咖啡店", "亲子乐园", "海鲜餐厅"]
        cities = ["上海", "北京", "广州", "深圳", "杭州", "青岛"]
        return {
            "poi_type": poi_types[case_idx % len(poi_types)],
            "city": cities[case_idx % len(cities)],
            "radius": [500, 1000, 3000, 5000][case_idx % 4],
        }
    if op == "navigation":
        destinations = ["上海虹桥站", "首都机场T3", "广州塔", "深圳湾公园", "杭州东站"]
        return {
            "destination": destinations[case_idx % len(destinations)],
            "route_preference": ["fastest", "shortest", "economical"][case_idx % 3],
        }
    if op == "music_search":
        music_inputs = [
            {"song_name": "晴天", "singer_name": "周杰伦", "content_type": "song", "limit": 5},
            {"mood": "适合开车", "genre": "轻音乐", "content_type": "song", "limit": 5},
            {"mood": "儿童故事", "content_type": "playlist", "limit": 5},
            {"album_name": "七里香", "content_type": "album", "limit": 5},
        ]
        return dict(music_inputs[case_idx % len(music_inputs)])
    if op == "audio_play":
        content_names = ["晴天", "轻音乐歌单", "儿童故事", "七里香"]
        return {
            "action": ["play", "add_to_playlist", "set_volume"][case_idx % 3],
            "content_name": content_names[case_idx % len(content_names)],
            "auto_continue": True,
            "volume": [None, 45, 60, 75][case_idx % 4],
        }
    if op == "car_control":
        return {
            "action": ["adjust_aircon", "set_window", "set_seat_heat"][case_idx % 3],
            "target": ["air_condition_system", "window", "seat_heater"][case_idx % 3],
            "value": ["26", "open", "level_2"][case_idx % 3],
        }
    if op == "web_search":
        queries = [
            "上海明天天气和气温",
            "北京国贸附近充电站空闲桩数",
            "广州塔附近停车场收费",
            "深圳今天空气质量和AQI",
            "首都机场航班状态",
        ]
        return {"query": queries[case_idx % len(queries)]}
    return {}


def _render_ref_value(pattern: str, refs: list[tuple[str, str]]) -> Any:
    first = _ref(*refs[0], mode="first")
    second = _ref(*refs[1], mode="first") if len(refs) > 1 else first
    if pattern == "direct_ref":
        return first if len(refs) == 1 else "、".join(_ref(*ref, mode="first") for ref in refs)
    if pattern == "indexed_ref":
        return first if len(refs) == 1 else f"{first}、{second}"
    if pattern == "wildcard_ref":
        wildcard_first = _ref(*refs[0], mode="wildcard")
        wildcard_second = _ref(*refs[1], mode="wildcard") if len(refs) > 1 else wildcard_first
        return wildcard_first if len(refs) == 1 else f"{wildcard_first}、{wildcard_second}"
    if pattern == "embedded_query_ref":
        suffix = f" 和 {second}" if len(refs) > 1 else ""
        return f"围绕 {first}{suffix} 继续查询相关信息"
    if pattern == "multi_ref_query":
        return f"结合 {first} 和 {second} 生成下一步条件"
    if pattern == "conditional_ref":
        condition = f"{first} 和 {second}" if len(refs) > 1 else first
        return f"{condition} ? '满足条件' : '不满足条件'"
    if pattern == "list_param_ref":
        return [first, second, "用户补充条件"]
    if pattern == "object_param_ref":
        return {"primary": first, "secondary": second, "hint": "用户关心的组合条件"}
    if pattern == "mixed_literal_ref":
        suffix = f"，同时参考 {second}" if len(refs) > 1 else ""
        return f"优先使用 {first}{suffix}，并结合用户补充限制"
    return first


def _render_item_ref_value(pattern: str, item_ref: str) -> Any:
    if pattern in {"direct_ref", "indexed_ref", "wildcard_ref"}:
        return item_ref
    if pattern == "embedded_query_ref":
        return f"围绕 {item_ref} 继续查询相关信息"
    if pattern == "multi_ref_query":
        return f"结合 {item_ref} 和 {item_ref} 生成下一步条件"
    if pattern == "conditional_ref":
        return f"{item_ref} ? '满足条件' : '不满足条件'"
    if pattern == "list_param_ref":
        return [item_ref, "用户补充条件"]
    if pattern == "object_param_ref":
        return {"primary": item_ref, "hint": "用户关心的迭代元素"}
    if pattern == "mixed_literal_ref":
        return f"优先使用 {item_ref}，并结合用户补充限制"
    return item_ref


def _ref(step_id: str, path: str, *, mode: str) -> str:
    if mode == "wildcard":
        return f"${step_id}.{path.replace('[]', '[*]')}"
    return f"${step_id}.{path.replace('[]', '[0]')}"


def _edge_from_binding(
    from_step: str,
    candidate: EdgeCandidate,
    to_step: str,
    binding: RefBinding,
    *,
    ref_bindings: list[RefBinding] | None = None,
) -> dict[str, Any]:
    refs = ref_bindings or [binding]
    return {
        "from_step": from_step,
        "from_op": candidate.source_op,
        "from_path": candidate.source_path,
        "to_step": to_step,
        "to_op": candidate.target_op,
        "to_param": binding.target_param,
        "reference_pattern": binding.reference_pattern,
        "refs": [
            {
                "step": ref_binding.ref_step,
                "path": ref_binding.ref_path,
                "ref": _ref(ref_binding.ref_step, ref_binding.ref_path, mode="first"),
            }
            for ref_binding in refs
        ],
    }


def _same_param_bindings(bindings: list[RefBinding], binding: RefBinding) -> list[RefBinding]:
    if binding.reference_pattern != "multi_ref_query":
        return [binding]
    same_param = [candidate for candidate in bindings if candidate.target_param == binding.target_param]
    return same_param or [binding]


def _rotated_reference_pattern(
    reference_pattern: str,
    offset: int,
    *,
    allow_multi: bool = False,
    edge: EdgeCandidate | None = None,
) -> str:
    patterns = list(REFERENCE_PATTERNS if allow_multi else tuple(p for p in REFERENCE_PATTERNS if p != "multi_ref_query"))
    if edge is not None:
        patterns = [pattern for pattern in patterns if REF_PATTERN_CONSTRAINTS[pattern](edge)]
    start = patterns.index(reference_pattern) if reference_pattern in patterns else 0
    return patterns[(start + offset) % len(patterns)]


def _prompt_dependency_edges(case: SyntheticPlanCase) -> list[dict[str, Any]]:
    return [
        {
            "from_step": edge["from_step"],
            "from_op": edge["from_op"],
            "from_path": edge["from_path"],
            "to_step": edge["to_step"],
            "to_op": edge["to_op"],
            "to_param": edge["to_param"],
            "refs": edge["refs"],
        }
        for edge in case.dependency_edges
    ]


def _alternate_target_param(
    inventory: dict[str, OperatorSchemaInfo],
    op: str,
    target_param: str,
) -> str | None:
    for field in inventory[op].input_fields:
        if field != target_param:
            return field
    return None


def _first_output(op: str, inventory: dict[str, OperatorSchemaInfo]) -> str:
    return inventory[op].output_paths[0]


def _extract_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key in sorted(value):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_extract_paths(value[key], child_prefix))
        return paths or ([prefix] if prefix else [])
    if isinstance(value, list):
        if not value:
            return [prefix] if prefix else []
        paths: list[str] = []
        for item in value:
            paths.extend(_extract_paths(item, f"{prefix}[]"))
        return sorted(set(paths))
    return [prefix] if prefix else []


_REF_RE = re.compile(r"\$(s\d+)\.([A-Za-z_][A-Za-z0-9_]*(?:\[(?:\d+|\*)?\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[(?:\d+|\*)?\])?)*)")
_ITEM_REF_RE = re.compile(r"\$item\.([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)")


def _extract_refs(value: Any) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    if isinstance(value, str):
        refs.extend((step, path) for step, path in _REF_RE.findall(value))
    elif isinstance(value, dict):
        for child in value.values():
            refs.extend(_extract_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_extract_refs(child))
    return refs


def _insert_path(root: dict[str, Any], parts: list[str]) -> None:
    current: dict[str, Any] = root
    for idx, raw_part in enumerate(parts):
        is_last = idx == len(parts) - 1
        is_array = raw_part.endswith("[]")
        part = raw_part[:-2] if is_array else raw_part
        if is_last:
            if is_array:
                current.setdefault(part, [""])
            else:
                current[part] = ""
            return
        if is_array:
            item = current.setdefault(part, [{}])
            current = item[0]
        else:
            current = current.setdefault(part, {})


def _validate_step_ref(
    issues: list[str],
    *,
    step_id: str,
    step: dict[str, Any],
    ref_step: str,
    ref_path: str,
    step_by_id: dict[Any, dict[str, Any]],
    declared_outputs: dict[Any, set[str]],
    allow_prefix: bool = False,
) -> None:
    if ref_step not in step_by_id:
        issues.append(f"{step_id}: ref step {ref_step} does not exist")
        return
    if ref_step not in set(step.get("depends_on") or []):
        issues.append(f"{step_id}: ref {ref_step}.{ref_path} missing depends_on")
    normalized = normalize_ref_path(ref_path)
    declared = declared_outputs.get(ref_step, set())
    if normalized in declared:
        return
    if allow_prefix and any(path.startswith(f"{normalized}.") for path in declared):
        return
    issues.append(f"{step_id}: ref {ref_step}.{normalized} not declared in outputs")


def _validate_iteration_refs(
    issues: list[str],
    *,
    step_id: str,
    step: dict[str, Any],
    inputs: dict[str, Any],
    iteration: dict[str, Any],
    step_by_id: dict[Any, dict[str, Any]],
    declared_outputs: dict[Any, set[str]],
) -> None:
    over = iteration.get("over")
    if not isinstance(over, str):
        issues.append(f"{step_id}: iteration.over must be string")
        return
    over_refs = _extract_refs(over)
    if len(over_refs) != 1:
        issues.append(f"{step_id}: iteration.over must contain one upstream ref")
        return
    ref_step, ref_path = over_refs[0]
    _validate_step_ref(
        issues,
        step_id=step_id,
        step=step,
        ref_step=ref_step,
        ref_path=ref_path,
        step_by_id=step_by_id,
        declared_outputs=declared_outputs,
        allow_prefix=True,
    )
    normalized_over = normalize_ref_path(ref_path)
    item_refs = _extract_item_refs(inputs)
    for item_path in item_refs:
        candidate = f"{normalized_over}.{item_path}"
        if candidate not in declared_outputs.get(ref_step, set()):
            issues.append(f"{step_id}: item ref $item.{item_path} does not map to {ref_step}.{normalized_over}")


def _extract_item_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, str):
        refs.extend(_ITEM_REF_RE.findall(value))
    elif isinstance(value, dict):
        for child in value.values():
            refs.extend(_extract_item_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_extract_item_refs(child))
    return refs


def _target_step_represents_ref(
    step: dict[str, Any],
    target_param: str,
    ref_step: str,
    ref_path: str,
) -> bool:
    normalized = normalize_ref_path(ref_path)
    refs = {
        (step_id, normalize_ref_path(path))
        for step_id, path in _extract_refs((step.get("inputs") or {}).get(target_param))
    }
    refs.update(
        (step_id, normalize_ref_path(path))
        for step_id, path in _extract_refs(step.get("condition"))
    )
    gather = step.get("gather")
    if isinstance(gather, dict):
        refs.update(
            (step_id, normalize_ref_path(path))
            for step_id, path in _extract_refs(gather.get("sources") or [])
        )
    if (ref_step, normalized) in refs:
        return True

    iteration = step.get("iteration")
    if not isinstance(iteration, dict):
        return False
    over_refs = _extract_refs(iteration.get("over"))
    if len(over_refs) != 1:
        return False
    over_step, over_path = over_refs[0]
    normalized_over = normalize_ref_path(over_path)
    if over_step != ref_step or not normalized.startswith(f"{normalized_over}."):
        return False
    item_path = normalized[len(normalized_over) + 1 :]
    return item_path in _extract_item_refs((step.get("inputs") or {}).get(target_param))


def _value_matches_reference_pattern(value: Any, reference_pattern: str) -> bool:
    if reference_pattern == "direct_ref":
        return _is_ref_only_string(value)
    if reference_pattern == "indexed_ref":
        return _is_ref_only_string(value) and any("[0]" in part for part in _ref_only_parts(value))
    if reference_pattern == "wildcard_ref":
        return _is_ref_only_string(value) and (
            any("[*]" in part for part in _ref_only_parts(value))
            or any(part.startswith("$item.") for part in _ref_only_parts(value))
        )
    if reference_pattern == "embedded_query_ref":
        return isinstance(value, str) and "围绕" in value and bool(_extract_refs(value) or _extract_item_refs(value))
    if reference_pattern == "multi_ref_query":
        return isinstance(value, str) and "结合" in value and bool(_extract_refs(value))
    if reference_pattern == "conditional_ref":
        return isinstance(value, str) and "?" in value and bool(_extract_refs(value) or _extract_item_refs(value))
    if reference_pattern == "list_param_ref":
        return isinstance(value, list) and bool(_extract_refs(value) or _extract_item_refs(value))
    if reference_pattern == "object_param_ref":
        return isinstance(value, dict) and bool(_extract_refs(value) or _extract_item_refs(value))
    if reference_pattern == "mixed_literal_ref":
        return isinstance(value, str) and "优先使用" in value and bool(_extract_refs(value) or _extract_item_refs(value))
    return True


def _is_ref_only_string(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parts = _ref_only_parts(value)
    if not parts or any(not part for part in parts):
        return False
    return all(_ITEM_REF_RE.fullmatch(part) or _REF_RE.fullmatch(part) for part in parts)


def _ref_only_parts(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return [part.strip() for part in value.split("、")]


def _array_iteration_parts(path: str) -> tuple[str, str]:
    before, after = path.split("[]", 1)
    item_leaf = after[1:] if after.startswith(".") else after
    if not item_leaf:
        item_leaf = before.rsplit(".", 1)[-1]
        before = before.rsplit(".", 1)[0] if "." in before else before
    return before, item_leaf


def _coverage_axis(
    targets: set[tuple[str, ...]],
    covered: set[tuple[str, ...]],
) -> dict[str, Any]:
    effective_covered = targets & covered
    missing = targets - covered
    return {
        "total": len(targets),
        "covered": len(effective_covered),
        "coverage_rate": _coverage_rate(len(effective_covered), len(targets)),
        "missing": _stringify_tuple_set(missing),
    }


def _coverage_rate(covered: int, total: int) -> float:
    if total == 0:
        return 1.0
    return round(covered / total, 6)


def _unused_output_keys(
    cases: list[SyntheticPlanCase],
    inventory: dict[str, OperatorSchemaInfo],
) -> list[tuple[str, str]]:
    used = {
        (edge["from_op"], edge["from_path"])
        for case in cases
        for edge in case.dependency_edges
    }
    return [
        (op, path)
        for op, info in sorted(inventory.items())
        for path in info.output_paths
        if (op, path) not in used
    ]


def _stringify_tuple_set(values: set[tuple[str, ...]]) -> list[str]:
    return ["|".join(value) for value in sorted(values)]


def _least_covered_tool_pair_refs(
    inventory: dict[str, OperatorSchemaInfo],
    counts: Counter[tuple[str, str, str]],
) -> list[dict[str, Any]]:
    rows = [
        {
            "pair": f"{source_op}->{target_op}",
            "ref_pattern": ref_pattern,
            "count": counts[(source_op, target_op, ref_pattern)],
        }
        for source_op in inventory
        for target_op in inventory
        for ref_pattern in REFERENCE_PATTERNS
    ]
    return sorted(rows, key=lambda row: (row["count"], row["pair"], row["ref_pattern"]))[:10]


def _group_unused(unused: set[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in sorted(unused):
        op, field = item.split(".", 1)
        grouped.setdefault(op, []).append(field)
    return grouped


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate high-recall synthetic complex plan cases.")
    parser.add_argument("--output", type=Path, default=Path("synthetic_complex_plan_cases.json"))
    parser.add_argument("--coverage-output", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-cases", type=int, default=None)
    return parser.parse_args()


def _main() -> None:
    args = _parse_args()
    cases = generate_synthetic_plan_cases(seed=args.seed, max_cases=args.max_cases)
    invalid = [(case.case_id, validate_synthetic_case(case)) for case in cases]
    invalid = [(case_id, issues) for case_id, issues in invalid if issues]
    if invalid:
        raise RuntimeError(f"generated invalid cases: {invalid[:3]}")
    report = build_coverage_report(cases)
    write_synthetic_case_file(cases, args.output)
    if args.coverage_output is not None:
        write_coverage_report(report, args.coverage_output)
    print(
        f"wrote {len(cases)} cases -> {args.output}; "
        f"covered outputs {report['used_output_field_count']}/{report['total_output_fields']}, "
        f"target inputs {report['used_target_input_count']}/{report['total_target_inputs']}"
    )


if __name__ == "__main__":
    _main()
