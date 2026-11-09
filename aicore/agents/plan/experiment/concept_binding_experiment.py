from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

from pydantic import BaseModel, Field

from aicore.models.model_api import UserMessage
from aicore.tools.experiments.entity_search_tool import (
    collect_schema_attributes,
    flatten_concept_paths,
)
from aicore.utils._concepts.meta import (
    ArrayType,
    Attribute,
    Concept,
    ObjectType,
    PrimitiveAttributeType,
)


PATH_ONLY_REF_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
POC_REF_TOKEN_RE = re.compile(r"\$[A-Za-z_]\w*(?:\.[^\s,，、;；)}]+)?")
_IDENT_RE = re.compile(r"^[A-Za-z_]\w*(?:\[\]|\[\d+\])?$")
_ARRAY_SELECTOR_RE = re.compile(r"^\d+$|^\*$")


class GoldStep(BaseModel):
    step_id: str
    op: str
    depends_on: list[str] = Field(default_factory=list)


class GoldInputBinding(BaseModel):
    step_id: str
    input_name: str
    source_step_id: str
    source_path: str
    acceptable_source_paths: list[str] = Field(default_factory=list)


class ExperimentCase(BaseModel):
    case_id: str
    query: str
    gold_steps: list[GoldStep]
    gold_required_output_fields: dict[str, list[str]] = Field(default_factory=dict)
    gold_input_bindings: list[GoldInputBinding] = Field(default_factory=list)
    gold_useful_output_fields: dict[str, list[str]] = Field(default_factory=dict)


class ToolContract(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    output_paths: list[str] = Field(default_factory=list)
    input_model: type[BaseModel] | None = Field(default=None, exclude=True)


class BaselineStep(BaseModel):
    step_id: str
    op: str
    depends_on: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)


class BaselinePlan(BaseModel):
    steps: list[BaselineStep]


class DynamicOutputSpec(BaseModel):
    concept_name: str
    is_list: bool
    selected_paths: list[str]


class ConceptStep(BaseModel):
    step_id: str
    op: str
    depends_on: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: DynamicOutputSpec


class ConceptPlan(BaseModel):
    steps: list[ConceptStep]


type POCPlanGenerator = Callable[[ExperimentCase], Awaitable[BaselinePlan]]
type ConceptPlanGenerator = Callable[[ExperimentCase], Awaitable[ConceptPlan]]


@dataclass(frozen=True)
class ExperimentError:
    error_type: str
    message: str
    step_id: str | None = None
    input_name: str | None = None
    ref: str | None = None
    field_path: str | None = None

    @property
    def is_diagnosable(self) -> bool:
        return any((self.step_id, self.input_name, self.ref, self.field_path))


@dataclass
class ArmEvaluation:
    case_id: str
    arm: str
    pre_execution_valid: bool
    errors: list[ExperimentError] = field(default_factory=list)
    required_field_recall: float | None = None
    output_field_precision: float | None = None
    binding_semantic_accuracy: float | None = None
    static_catch_rate: float = 0.0
    repair_success_rate: float | None = None
    avg_repair_rounds: float | None = None
    new_error_after_repair_rate: float | None = None
    e2e_success_rate: float | None = None

    @property
    def error_types(self) -> list[str]:
        return [error.error_type for error in self.errors]

    @property
    def diagnosable_error_rate(self) -> float:
        if not self.errors:
            return 1.0
        return sum(1 for error in self.errors if error.is_diagnosable) / len(self.errors)

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "arm": self.arm,
            "pre_execution_valid": self.pre_execution_valid,
            "error_types": "|".join(self.error_types),
            "errors_json": json.dumps(
                [error.__dict__ for error in self.errors],
                ensure_ascii=False,
                default=str,
            ),
            "required_field_recall": self.required_field_recall,
            "output_field_precision": self.output_field_precision,
            "binding_semantic_accuracy": self.binding_semantic_accuracy,
            "static_catch_rate": self.static_catch_rate,
            "diagnosable_error_rate": self.diagnosable_error_rate,
            "repair_success_rate": self.repair_success_rate,
            "avg_repair_rounds": self.avg_repair_rounds,
            "new_error_after_repair_rate": self.new_error_after_repair_rate,
            "e2e_success_rate": self.e2e_success_rate,
        }


@dataclass
class SmokeArmEvaluation:
    case_id: str
    query: str
    arm: str
    parse_success: bool
    pre_execution_valid: bool
    errors: list[ExperimentError] = field(default_factory=list)
    parse_error: str | None = None
    selected_path_valid_rate: float | None = None
    compression_rate: float | None = None
    ref_resolvability_rate: float | None = None
    args_schema_validation_rate: float | None = None
    plan_json: str | None = None

    @property
    def error_types(self) -> list[str]:
        return [error.error_type for error in self.errors]

    @property
    def diagnosable_error_rate(self) -> float:
        if not self.errors:
            return 1.0
        return sum(1 for error in self.errors if error.is_diagnosable) / len(self.errors)

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "query": self.query,
            "arm": self.arm,
            "parse_success": self.parse_success,
            "pre_execution_valid": self.pre_execution_valid,
            "error_types": "|".join(self.error_types),
            "errors_json": json.dumps(
                [error.__dict__ for error in self.errors],
                ensure_ascii=False,
                default=str,
            ),
            "parse_error": self.parse_error,
            "selected_path_valid_rate": self.selected_path_valid_rate,
            "compression_rate": self.compression_rate,
            "ref_resolvability_rate": self.ref_resolvability_rate,
            "args_schema_validation_rate": self.args_schema_validation_rate,
            "diagnosable_error_rate": self.diagnosable_error_rate,
            "plan_json": self.plan_json,
        }


class _PathNode:
    def __init__(self) -> None:
        self.children: dict[str, _PathNode] = {}
        self.is_array = False


@dataclass(frozen=True)
class _ParsedRef:
    step_id: str
    concept_name: str | None
    source_path: str
    uses_top_level_list_selector: bool = False


def compile_selected_paths(concept_name: str, selected_paths: list[str]) -> Concept:
    root = _PathNode()
    for path in selected_paths:
        tokens = _parse_relative_path(path)
        _insert_path(root, tokens)

    return Concept(
        name=concept_name,
        definition="动态选择的工具输出字段",
        attributes=_node_to_attributes(root),
    )


def evaluate_poc_plan(case: ExperimentCase, plan: BaselinePlan) -> ArmEvaluation:
    errors = _check_common_plan_errors(case, plan.steps, has_concept_contract=False)
    accuracy, binding_errors = _binding_semantic_accuracy(case, plan.steps)
    errors.extend(binding_errors)
    pre_valid = not errors
    return ArmEvaluation(
        case_id=case.case_id,
        arm="poc",
        pre_execution_valid=pre_valid,
        errors=errors,
        required_field_recall=None,
        output_field_precision=None,
        binding_semantic_accuracy=accuracy,
        static_catch_rate=_static_catch_rate(errors, has_concept_contract=False),
    )


def evaluate_concept_plan(case: ExperimentCase, plan: ConceptPlan) -> ArmEvaluation:
    concepts = {
        step.step_id: compile_selected_paths(
            step.outputs.concept_name,
            step.outputs.selected_paths,
        )
        for step in plan.steps
    }
    selected = {
        step.step_id: {_normalize_gold_path(path) for path in step.outputs.selected_paths}
        for step in plan.steps
    }

    errors = _check_common_plan_errors(case, plan.steps, has_concept_contract=True)
    errors.extend(_check_required_outputs(case, selected))
    errors.extend(_check_over_selected_outputs(case, selected))
    errors.extend(_check_concept_refs(plan.steps, concepts))
    accuracy, binding_errors = _binding_semantic_accuracy(case, plan.steps)
    errors.extend(binding_errors)

    return ArmEvaluation(
        case_id=case.case_id,
        arm="concept",
        pre_execution_valid=not errors,
        errors=errors,
        required_field_recall=_required_field_recall(case, selected),
        output_field_precision=_output_field_precision(case, selected),
        binding_semantic_accuracy=accuracy,
        static_catch_rate=_static_catch_rate(errors, has_concept_contract=True),
    )


def summarize_results(results: list[ArmEvaluation]) -> dict[str, Any]:
    return {
        "case_count": len(results),
        "pre_execution_valid_rate": _mean_bool(
            result.pre_execution_valid for result in results
        ),
        "avg_required_field_recall": _mean_optional(
            result.required_field_recall for result in results
        ),
        "avg_output_field_precision": _mean_optional(
            result.output_field_precision for result in results
        ),
        "avg_binding_semantic_accuracy": _mean_optional(
            result.binding_semantic_accuracy for result in results
        ),
        "avg_static_catch_rate": _mean_optional(
            result.static_catch_rate for result in results
        ),
        "avg_diagnosable_error_rate": _mean_optional(
            result.diagnosable_error_rate for result in results
        ),
        "error_type_counts": _error_type_counts(results),
    }


def build_poc_prompt(query: str, tools: list[ToolContract]) -> str:
    tool_text = "\n\n".join(
        (
            f"工具: {tool.name}\n"
            f"描述: {tool.description}\n"
            f"输入 schema:\n{json.dumps(tool.input_schema, ensure_ascii=False, indent=2)}"
        )
        for tool in tools
    )
    return (
        "你是 POC baseline plan generator。请一次性生成完整 DAG plan。\n"
        "输出字段只包含 steps / step_id / op / step_goal / depends_on / inputs。\n"
        "inputs 可以直接写 POC 引用表达，但不要输出 outputs、Concept、selected_paths。\n"
        "保持 POC 已有引用风格：动态引用可使用 $step_id.field，例如 $s1.address。\n"
        "不要输出 selected_paths。\n\n"
        f"用户 query:\n{query}\n\n"
        f"可用工具:\n{tool_text}"
    )


def build_concept_prompt(query: str, tools: list[ToolContract]) -> str:
    tool_text = "\n\n".join(
        (
            f"工具: {tool.name}\n"
            f"描述: {tool.description}\n"
            f"输入 schema:\n{json.dumps(tool.input_schema, ensure_ascii=False, indent=2)}\n"
            "可选择输出 path-only jq 字段:\n"
            + "\n".join(f"- {path}" for path in tool.output_paths)
        )
        for tool in tools
    )
    return (
        "你是 Concept dynamic binding plan generator。请一次性生成完整 DAG plan。\n"
        "每个 step 必须包含 steps / step_id / op / step_goal / depends_on / inputs / outputs。\n"
        "outputs 包含 concept_name、is_list、selected_paths。\n"
        "selected_paths 是相对该工具 raw output 的 path-only jq，例如 .address 或 .songs[].song_name。\n"
        "inputs 中的动态引用继续使用 {{...}}，但变量内容必须是当前 runner 的 slash ref。\n"
        "引用非列表 Concept 字段：{{/s1/outputs/WeatherInfo/weather_condition}}；"
        "引用 is_list=True 的 Concept 字段：{{/s1/outputs/SelectedPOI/0/address}}；"
        "批量引用列表字段：{{/s1/outputs/SelectedSong/*/song_name}}。\n"
        "ConceptName 和字段名必须来自上游 step.outputs.selected_paths 编译后的 Concept；"
        "不要使用 .s1.outputs、$s1、Python 表达式、jq 管道或 {{#if}}/{{#each}} 这类模板控制流。\n\n"
        f"用户 query:\n{query}\n\n"
        f"可用工具:\n{tool_text}"
    )


def default_tool_contracts() -> list[ToolContract]:
    from aicore.tools.dag.operator_models import (
        AudioPlayOutput,
        AudioPlayParams,
        CarControlOutput,
        CarControlParams,
        MusicSearchOutput,
        MusicSearchParams,
        NavigationOutput,
        NavigationParams,
        POISearchOutput,
        POISearchParams,
        WebSearchOutput,
        WebSearchParams,
    )

    specs: list[tuple[str, str, type[BaseModel], type[BaseModel]]] = [
        ("poi_search", "POI 搜索", POISearchParams, POISearchOutput),
        ("navigation", "路线规划与导航", NavigationParams, NavigationOutput),
        ("music_search", "音乐搜索", MusicSearchParams, MusicSearchOutput),
        ("audio_play", "音频播放控制", AudioPlayParams, AudioPlayOutput),
        ("car_control", "车辆控制", CarControlParams, CarControlOutput),
        ("web_search", "通用网页搜索", WebSearchParams, WebSearchOutput),
    ]
    return [
        ToolContract(
            name=name,
            description=description,
            input_schema=input_model.model_json_schema(),
            input_model=input_model,
            output_paths=[
                f".{path}" for path in collect_schema_attributes(output_model).keys()
            ],
        )
        for name, description, input_model, output_model in specs
    ]


async def run_experiment(
    cases: list[ExperimentCase],
    *,
    poc_generator: POCPlanGenerator,
    concept_generator: ConceptPlanGenerator,
) -> list[ArmEvaluation]:
    results: list[ArmEvaluation] = []
    for case in cases:
        poc_plan = await poc_generator(case)
        results.append(evaluate_poc_plan(case, poc_plan))
        concept_plan = await concept_generator(case)
        results.append(evaluate_concept_plan(case, concept_plan))
    return results


def load_query_txt(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def run_smoke_experiment(
    queries: list[str],
    *,
    tools: list[ToolContract],
    poc_generator: POCPlanGenerator,
    concept_generator: ConceptPlanGenerator,
) -> list[SmokeArmEvaluation]:
    results: list[SmokeArmEvaluation] = []
    for idx, query in enumerate(queries, start=1):
        case = ExperimentCase(case_id=f"q{idx:03d}", query=query, gold_steps=[])

        try:
            poc_plan = await poc_generator(case)
        except Exception as exc:
            results.append(_parse_failure(case, "poc", exc))
        else:
            results.append(evaluate_poc_smoke(case, poc_plan, tools))

        try:
            concept_plan = await concept_generator(case)
        except Exception as exc:
            results.append(_parse_failure(case, "concept", exc))
        else:
            results.append(evaluate_concept_smoke(case, concept_plan, tools))

    return results


def evaluate_poc_smoke(
    case: ExperimentCase,
    plan: BaselinePlan,
    tools: list[ToolContract],
) -> SmokeArmEvaluation:
    errors = _check_common_plan_errors(case, plan.steps, has_concept_contract=False)
    errors.extend(_check_args_schema(plan.steps, tools))
    total_refs = _count_refs(plan.steps, has_concept_contract=False)
    return SmokeArmEvaluation(
        case_id=case.case_id,
        query=case.query,
        arm="poc",
        parse_success=True,
        pre_execution_valid=not errors,
        errors=errors,
        selected_path_valid_rate=None,
        compression_rate=None,
        ref_resolvability_rate=_ref_resolvability_rate(total_refs, errors),
        args_schema_validation_rate=_args_schema_validation_rate(plan.steps, tools, errors),
        plan_json=plan.model_dump_json(),
    )


def evaluate_concept_smoke(
    case: ExperimentCase,
    plan: ConceptPlan,
    tools: list[ToolContract],
) -> SmokeArmEvaluation:
    tool_by_name = {tool.name: tool for tool in tools}
    concepts = {
        step.step_id: compile_selected_paths(
            step.outputs.concept_name,
            step.outputs.selected_paths,
        )
        for step in plan.steps
    }
    errors = _check_common_plan_errors(case, plan.steps, has_concept_contract=True)
    errors.extend(_check_selected_paths_against_inventory(plan, tool_by_name))
    errors.extend(_check_concept_refs(plan.steps, concepts))
    errors.extend(_check_args_schema(plan.steps, tools))
    total_refs = _count_refs(plan.steps, has_concept_contract=True)
    return SmokeArmEvaluation(
        case_id=case.case_id,
        query=case.query,
        arm="concept",
        parse_success=True,
        pre_execution_valid=not errors,
        errors=errors,
        selected_path_valid_rate=_selected_path_valid_rate(plan, tool_by_name),
        compression_rate=_compression_rate(plan, tool_by_name),
        ref_resolvability_rate=_ref_resolvability_rate(total_refs, errors),
        args_schema_validation_rate=_args_schema_validation_rate(plan.steps, tools, errors),
        plan_json=plan.model_dump_json(),
    )


def summarize_smoke_results(results: list[SmokeArmEvaluation]) -> dict[str, Any]:
    by_arm: dict[str, dict[str, Any]] = {}
    for arm in sorted({result.arm for result in results}):
        arm_results = [result for result in results if result.arm == arm]
        by_arm[arm] = {
            "row_count": len(arm_results),
            "parse_success_rate": _mean_bool(result.parse_success for result in arm_results),
            "pre_execution_valid_rate": _mean_bool(
                result.pre_execution_valid for result in arm_results
            ),
            "diagnosable_error_rate": _mean_optional(
                result.diagnosable_error_rate for result in arm_results
            ),
            "selected_path_valid_rate": _mean_optional(
                result.selected_path_valid_rate for result in arm_results
            ),
            "avg_compression_rate": _mean_optional(
                result.compression_rate for result in arm_results
            ),
            "ref_resolvability_rate": _mean_optional(
                result.ref_resolvability_rate for result in arm_results
            ),
            "args_schema_validation_rate": _mean_optional(
                result.args_schema_validation_rate for result in arm_results
            ),
            "static_error_breakdown": _smoke_error_type_counts(arm_results),
        }
    return {
        "case_count": len({result.case_id for result in results}),
        "row_count": len(results),
        "by_arm": by_arm,
    }


async def generate_poc_plan(
    model_api: Any,
    case: ExperimentCase,
    tools: list[ToolContract],
    *,
    params: Any | None = None,
) -> BaselinePlan:
    prompt = build_poc_prompt(case.query, tools)
    state = model_api.initial_state()
    response = await model_api.structured_output(
        UserMessage(text=prompt),
        output_type=BaselinePlan,
        state=state,
        params=params,
    )
    if response.parsed is None:
        raise ValueError(f"poc plan generation failed: {getattr(response, 'metadata', {})}")
    return response.parsed


async def generate_concept_plan(
    model_api: Any,
    case: ExperimentCase,
    tools: list[ToolContract],
    *,
    params: Any | None = None,
) -> ConceptPlan:
    prompt = build_concept_prompt(case.query, tools)
    state = model_api.initial_state()
    response = await model_api.structured_output(
        UserMessage(text=prompt),
        output_type=ConceptPlan,
        state=state,
        params=params,
    )
    if response.parsed is None:
        raise ValueError(f"concept plan generation failed: {getattr(response, 'metadata', {})}")
    return response.parsed


def write_case_csv(results: list[ArmEvaluation], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [result.to_csv_row() for result in results]
    if not rows:
        output_path.write_text("", encoding="utf-8")
        return

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_summary_report(results: list[ArmEvaluation], output_path: Path) -> None:
    summary = summarize_results(results)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def write_smoke_csv(results: list[SmokeArmEvaluation], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [result.to_csv_row() for result in results]
    if not rows:
        output_path.write_text("", encoding="utf-8")
        return

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_smoke_summary_report(
    results: list[SmokeArmEvaluation],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summarize_smoke_results(results), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _parse_relative_path(path: str) -> list[tuple[str, bool]]:
    raw = path.strip()
    if not raw.startswith("."):
        raise ValueError(f"selected path must start with '.', got {path!r}")
    raw = raw[1:]
    if not raw:
        raise ValueError("selected path cannot be empty")

    tokens: list[tuple[str, bool]] = []
    for segment in raw.split("."):
        if not _IDENT_RE.fullmatch(segment):
            raise ValueError(f"invalid path segment {segment!r} in {path!r}")
        is_array = segment.endswith("[]")
        name = segment[:-2] if is_array else re.sub(r"\[\d+\]$", "", segment)
        tokens.append((name, is_array))
    return tokens


def _insert_path(root: _PathNode, tokens: list[tuple[str, bool]]) -> None:
    cur = root
    for name, is_array in tokens:
        child = cur.children.setdefault(name, _PathNode())
        child.is_array = child.is_array or is_array
        cur = child


def _node_to_attributes(node: _PathNode) -> list[Attribute]:
    return [
        _node_child_to_attribute(name, child)
        for name, child in node.children.items()
    ]


def _node_child_to_attribute(name: str, child: _PathNode) -> Attribute:
    if child.children:
        value_type: Any = ObjectType(properties=_node_to_attributes(child))
        if child.is_array:
            value_type = ArrayType(item_type=value_type)
    else:
        value_type = PrimitiveAttributeType.STRING
        if child.is_array:
            value_type = ArrayType(item_type=value_type)

    return Attribute(
        name=name,
        title=name,
        description=name,
        type=value_type,
        is_required=False,
    )


def _check_common_plan_errors(
    case: ExperimentCase,
    steps: list[Any],
    *,
    has_concept_contract: bool,
) -> list[ExperimentError]:
    errors: list[ExperimentError] = []
    step_ids = [step.step_id for step in steps]
    known_steps = set(step_ids)
    ancestors = _ancestors_by_step(steps)

    for step in steps:
        refs = (
            _extract_input_refs(step.inputs)
            if has_concept_contract
            else _extract_poc_input_refs(step.inputs)
        )
        for ref in refs:
            parsed = (
                _parse_input_ref(ref)
                if has_concept_contract
                else _parse_poc_input_ref(ref)
            )
            if parsed is None:
                errors.append(ExperimentError(
                    "invalid_ref_syntax",
                    f"input ref {ref!r} is not a valid {'slash ref' if has_concept_contract else '$ref'}",
                    step_id=step.step_id,
                    ref=ref,
                ))
                continue
            if parsed.step_id not in known_steps:
                errors.append(ExperimentError(
                    "unknown_step_ref",
                    f"ref points to unknown step {parsed.step_id!r}",
                    step_id=step.step_id,
                    ref=ref,
                ))
                continue
            if parsed.step_id not in ancestors.get(step.step_id, set()):
                errors.append(ExperimentError(
                    "undeclared_dependency_ref",
                    f"step {step.step_id!r} references {parsed.step_id!r} outside depends_on ancestors",
                    step_id=step.step_id,
                    ref=ref,
                ))

    gold_ops = {step.step_id: step.op for step in case.gold_steps}
    for step in steps:
        if step.step_id in gold_ops and step.op != gold_ops[step.step_id]:
            errors.append(ExperimentError(
                "op_mismatch",
                f"step {step.step_id!r} op {step.op!r} != gold {gold_ops[step.step_id]!r}",
                step_id=step.step_id,
            ))

    if has_concept_contract:
        return errors
    return errors


def _check_required_outputs(
    case: ExperimentCase,
    selected: dict[str, set[str]],
) -> list[ExperimentError]:
    errors: list[ExperimentError] = []
    for step_id, required_paths in case.gold_required_output_fields.items():
        selected_paths = selected.get(step_id, set())
        for required in required_paths:
            required_norm = _normalize_gold_path(required)
            if not any(_paths_match(required_norm, path) for path in selected_paths):
                errors.append(ExperimentError(
                    "missing_required_output_field",
                    f"step {step_id!r} did not select required output field {required_norm}",
                    step_id=step_id,
                    field_path=required_norm,
                ))
    return errors


def _check_over_selected_outputs(
    case: ExperimentCase,
    selected: dict[str, set[str]],
) -> list[ExperimentError]:
    errors: list[ExperimentError] = []
    useful = _useful_output_fields(case)
    for step_id, selected_paths in selected.items():
        useful_paths = useful.get(step_id, set())
        if not useful_paths:
            continue
        for path in selected_paths:
            if not any(_paths_match(path, useful_path) for useful_path in useful_paths):
                errors.append(ExperimentError(
                    "over_selected_output_fields",
                    f"step {step_id!r} selected non-gold output field {path}",
                    step_id=step_id,
                    field_path=path,
                ))
    return errors


def _check_concept_refs(
    steps: list[ConceptStep],
    concepts: dict[str, Concept],
) -> list[ExperimentError]:
    errors: list[ExperimentError] = []
    concept_names = {step.step_id: step.outputs.concept_name for step in steps}
    is_list_by_step = {step.step_id: step.outputs.is_list for step in steps}
    concept_paths = {
        step_id: {_normalize_gold_path(path) for path in flatten_concept_paths(concept)}
        for step_id, concept in concepts.items()
    }

    for step in steps:
        for ref in _extract_input_refs(step.inputs):
            parsed = _parse_input_ref(ref, concept_names_by_step=concept_names)
            if parsed is None or parsed.step_id not in concept_paths:
                continue
            if parsed.concept_name is not None and parsed.concept_name != concept_names[parsed.step_id]:
                errors.append(ExperimentError(
                    "unknown_output_field",
                    f"ref concept {parsed.concept_name!r} does not match step output concept {concept_names[parsed.step_id]!r}",
                    step_id=step.step_id,
                    ref=ref,
                ))
                continue
            if parsed.uses_top_level_list_selector != is_list_by_step.get(parsed.step_id, False):
                errors.append(ExperimentError(
                    "array_shape_mismatch",
                    f"ref {ref!r} does not match is_list={is_list_by_step.get(parsed.step_id, False)} for step {parsed.step_id!r}",
                    step_id=step.step_id,
                    ref=ref,
                    field_path=parsed.source_path,
                ))
                continue
            if not any(_paths_match(parsed.source_path, path) for path in concept_paths[parsed.step_id]):
                errors.append(ExperimentError(
                    "unknown_output_field",
                    f"ref path {parsed.source_path} is not declared by step {parsed.step_id!r}",
                    step_id=step.step_id,
                    ref=ref,
                    field_path=parsed.source_path,
                ))
    return errors


def _check_selected_paths_against_inventory(
    plan: ConceptPlan,
    tool_by_name: dict[str, ToolContract],
) -> list[ExperimentError]:
    errors: list[ExperimentError] = []
    for step in plan.steps:
        allowed = {_normalize_gold_path(path) for path in tool_by_name.get(step.op, ToolContract(name=step.op, description="", input_schema={})).output_paths}
        if not allowed:
            continue
        for path in step.outputs.selected_paths:
            normalized = _normalize_gold_path(path)
            if not any(_paths_match(normalized, allowed_path) for allowed_path in allowed):
                errors.append(ExperimentError(
                    "unknown_output_field",
                    f"step {step.step_id!r} selected path {normalized} not in tool {step.op!r} output inventory",
                    step_id=step.step_id,
                    field_path=normalized,
                ))
    return errors


def _check_args_schema(steps: list[Any], tools: list[ToolContract]) -> list[ExperimentError]:
    tool_by_name = {tool.name: tool for tool in tools}
    errors: list[ExperimentError] = []
    for step in steps:
        tool = tool_by_name.get(step.op)
        if tool is None or tool.input_model is None:
            continue
        try:
            tool.input_model.model_validate(_mock_resolve_inputs(step.inputs))
        except Exception as exc:
            errors.append(ExperimentError(
                "input_args_schema_mismatch",
                f"step {step.step_id!r} inputs do not validate against {step.op!r}: {exc}",
                step_id=step.step_id,
            ))
    return errors


def _selected_path_valid_rate(
    plan: ConceptPlan,
    tool_by_name: dict[str, ToolContract],
) -> float | None:
    total = 0
    valid = 0
    for step in plan.steps:
        allowed = {_normalize_gold_path(path) for path in tool_by_name.get(step.op, ToolContract(name=step.op, description="", input_schema={})).output_paths}
        if not allowed:
            continue
        for path in step.outputs.selected_paths:
            total += 1
            normalized = _normalize_gold_path(path)
            if any(_paths_match(normalized, allowed_path) for allowed_path in allowed):
                valid += 1
    return valid / total if total else None


def _compression_rate(
    plan: ConceptPlan,
    tool_by_name: dict[str, ToolContract],
) -> float | None:
    total_available = 0
    total_selected = 0
    for step in plan.steps:
        tool = tool_by_name.get(step.op)
        if tool is None or not tool.output_paths:
            continue
        total_available += len(tool.output_paths)
        total_selected += len(step.outputs.selected_paths)
    if total_available == 0:
        return None
    return 1.0 - total_selected / total_available


def _ref_resolvability_rate(total_refs: int, errors: list[ExperimentError]) -> float | None:
    if total_refs == 0:
        return None
    unresolved = sum(
        1
        for error in errors
        if error.error_type in {
            "invalid_ref_syntax",
            "unknown_step_ref",
            "undeclared_dependency_ref",
            "unknown_output_field",
        }
        and error.ref is not None
    )
    return max(0.0, (total_refs - unresolved) / total_refs)


def _args_schema_validation_rate(
    steps: list[Any],
    tools: list[ToolContract],
    errors: list[ExperimentError],
) -> float | None:
    validated_step_ids = {
        step.step_id
        for step in steps
        for tool in tools
        if tool.name == step.op and tool.input_model is not None
    }
    if not validated_step_ids:
        return None
    failed = {
        error.step_id
        for error in errors
        if error.error_type == "input_args_schema_mismatch" and error.step_id is not None
    }
    return (len(validated_step_ids) - len(failed)) / len(validated_step_ids)


def _mock_resolve_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    def resolve(value: Any) -> Any:
        if isinstance(value, str) and "{{" in value:
            value = PATH_ONLY_REF_RE.sub("mock_ref", value)
        if isinstance(value, str) and "$" in value:
            return POC_REF_TOKEN_RE.sub("mock_ref", value)
        if isinstance(value, dict):
            return {key: resolve(child) for key, child in value.items()}
        if isinstance(value, list):
            return [resolve(child) for child in value]
        return value

    return {key: resolve(value) for key, value in inputs.items()}


def _count_refs(steps: list[Any], *, has_concept_contract: bool) -> int:
    extract_refs = _extract_input_refs if has_concept_contract else _extract_poc_input_refs
    return sum(len(extract_refs(step.inputs)) for step in steps)


def _parse_failure(
    case: ExperimentCase,
    arm: str,
    exc: Exception,
) -> SmokeArmEvaluation:
    message = f"{type(exc).__name__}: {exc}"
    return SmokeArmEvaluation(
        case_id=case.case_id,
        query=case.query,
        arm=arm,
        parse_success=False,
        pre_execution_valid=False,
        parse_error=message,
        errors=[ExperimentError("parse_failure", message)],
    )


def _binding_semantic_accuracy(
    case: ExperimentCase,
    steps: list[Any],
) -> tuple[float | None, list[ExperimentError]]:
    if not case.gold_input_bindings:
        return None, []

    steps_by_id = {step.step_id: step for step in steps}
    concept_names = {
        step.step_id: step.outputs.concept_name
        for step in steps
        if hasattr(step, "outputs") and hasattr(step.outputs, "concept_name")
    }
    has_concept_contract = bool(concept_names)
    correct = 0
    errors: list[ExperimentError] = []

    for gold in case.gold_input_bindings:
        step = steps_by_id.get(gold.step_id)
        if step and has_concept_contract:
            refs = _extract_input_refs({gold.input_name: step.inputs.get(gold.input_name)})
        elif step:
            refs = _extract_poc_input_refs({gold.input_name: step.inputs.get(gold.input_name)})
        else:
            refs = []
        parsed_refs = [
            parsed
            for ref in refs
            if (
                parsed := (
                    _parse_input_ref(ref, concept_names_by_step=concept_names)
                    if has_concept_contract
                    else _parse_poc_input_ref(ref)
                )
            ) is not None
        ]
        acceptable_paths = {
            _normalize_gold_path(gold.source_path),
            *(_normalize_gold_path(path) for path in gold.acceptable_source_paths),
        }
        is_correct = any(
            parsed.step_id == gold.source_step_id
            and any(_paths_match(parsed.source_path, path) for path in acceptable_paths)
            for parsed in parsed_refs
        )
        if is_correct:
            correct += 1
        else:
            errors.append(ExperimentError(
                "semantic_misbinding",
                f"input {gold.step_id}.{gold.input_name} does not bind to {gold.source_step_id}{gold.source_path}",
                step_id=gold.step_id,
                input_name=gold.input_name,
                field_path=_normalize_gold_path(gold.source_path),
            ))

    return correct / len(case.gold_input_bindings), errors


def _extract_input_refs(value: Any) -> list[str]:
    refs: list[str] = []

    def scan(v: Any) -> None:
        if isinstance(v, str) and "{{" in v:
            refs.extend(match.group(1).strip() for match in PATH_ONLY_REF_RE.finditer(v))
        elif isinstance(v, dict):
            for child in v.values():
                scan(child)
        elif isinstance(v, list):
            for child in v:
                scan(child)

    scan(value)
    return refs


def _extract_poc_input_refs(value: Any) -> list[str]:
    refs: list[str] = []

    def scan(v: Any) -> None:
        if isinstance(v, str):
            scrubbed = v
            if "{{" in v:
                refs.extend(match.group(0).strip() for match in PATH_ONLY_REF_RE.finditer(v))
                scrubbed = PATH_ONLY_REF_RE.sub("", v)
            refs.extend(match.group(0).strip() for match in POC_REF_TOKEN_RE.finditer(scrubbed))
        elif isinstance(v, dict):
            for child in v.values():
                scan(child)
        elif isinstance(v, list):
            for child in v:
                scan(child)

    scan(value)
    return refs


def _parse_poc_input_ref(ref: str) -> _ParsedRef | None:
    raw = ref.strip()
    if not raw.startswith("$") or raw.startswith("${"):
        return None

    body = raw[1:]
    if not body:
        return None
    step_id, sep, path = body.partition(".")
    if not step_id or re.search(r"\s|[{}]", step_id):
        return None
    if not sep:
        return _ParsedRef(step_id=step_id, concept_name=None, source_path=".")

    normalized = _poc_path_to_source_path(path)
    if normalized is None:
        return None
    return _ParsedRef(step_id=step_id, concept_name=None, source_path=normalized)


def _parse_input_ref(
    ref: str,
    *,
    concept_names_by_step: dict[str, str] | None = None,
) -> _ParsedRef | None:
    raw = ref.strip()
    if not raw.startswith("/"):
        return None
    parts = raw[1:].split("/")
    if (
        len(parts) < 3
        or not parts[0]
        or parts[1] != "outputs"
        or any(not part or re.search(r"\s|[{}\[\]]", part) for part in parts)
    ):
        return None

    step_id = parts[0]
    output_tokens = parts[2:]
    concept_name = None
    path_tokens = output_tokens
    uses_top_level_list_selector = False

    expected_concept = (concept_names_by_step or {}).get(step_id)
    if expected_concept is not None:
        concept_name = output_tokens[0]
        path_tokens = output_tokens[1:]
        if path_tokens and _is_array_selector(path_tokens[0]):
            uses_top_level_list_selector = True
            path_tokens = path_tokens[1:]

    normalized = _slash_path_tokens_to_source_path(path_tokens)
    if normalized is None:
        return None
    return _ParsedRef(
        step_id=step_id,
        concept_name=concept_name,
        source_path=normalized,
        uses_top_level_list_selector=uses_top_level_list_selector,
    )


def _poc_path_to_source_path(path: str) -> str | None:
    if not path or re.search(r"\s|[{}]", path):
        return None

    segments: list[str] = []
    for segment in path.split("."):
        if not segment:
            return None
        normalized = re.sub(r"\[(?:\d+|\*)\]", "[]", segment)
        if not normalized or "[" in normalized or "]" in normalized:
            return None
        segments.append(normalized)
    return "." + ".".join(segments)


def _is_array_selector(token: str) -> bool:
    return bool(_ARRAY_SELECTOR_RE.fullmatch(token))


def _slash_path_tokens_to_source_path(tokens: list[str]) -> str | None:
    if not tokens:
        return "."

    segments: list[str] = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if _is_array_selector(token):
            return None
        if idx + 1 < len(tokens) and _is_array_selector(tokens[idx + 1]):
            segments.append(f"{token}[]")
            idx += 2
        else:
            segments.append(token)
            idx += 1

    return "." + ".".join(segments)


def _ancestors_by_step(steps: list[Any]) -> dict[str, set[str]]:
    dep_map = {step.step_id: list(step.depends_on) for step in steps}
    cache: dict[str, set[str]] = {}

    def ancestors(step_id: str, visiting: set[str]) -> set[str]:
        if step_id in cache:
            return cache[step_id]
        if step_id in visiting:
            return set()
        visiting.add(step_id)
        result: set[str] = set()
        for dep in dep_map.get(step_id, []):
            result.add(dep)
            result |= ancestors(dep, visiting)
        visiting.discard(step_id)
        cache[step_id] = result
        return result

    return {step.step_id: ancestors(step.step_id, set()) for step in steps}


def _required_field_recall(
    case: ExperimentCase,
    selected: dict[str, set[str]],
) -> float | None:
    required = [
        (step_id, _normalize_gold_path(path))
        for step_id, paths in case.gold_required_output_fields.items()
        for path in paths
    ]
    if not required:
        return None
    matched = sum(
        1
        for step_id, path in required
        if any(_paths_match(path, selected_path) for selected_path in selected.get(step_id, set()))
    )
    return matched / len(required)


def _output_field_precision(
    case: ExperimentCase,
    selected: dict[str, set[str]],
) -> float | None:
    useful = _useful_output_fields(case)
    selected_pairs = [
        (step_id, path)
        for step_id, paths in selected.items()
        for path in paths
        if step_id in useful
    ]
    if not selected_pairs:
        return None
    matched = sum(
        1
        for step_id, path in selected_pairs
        if any(_paths_match(path, useful_path) for useful_path in useful.get(step_id, set()))
    )
    return matched / len(selected_pairs)


def _useful_output_fields(case: ExperimentCase) -> dict[str, set[str]]:
    useful: dict[str, set[str]] = {}
    for source in (case.gold_required_output_fields, case.gold_useful_output_fields):
        for step_id, paths in source.items():
            useful.setdefault(step_id, set()).update(_normalize_gold_path(path) for path in paths)
    return useful


def _static_catch_rate(errors: list[ExperimentError], *, has_concept_contract: bool) -> float:
    if not has_concept_contract:
        return 0.0
    binding_errors = [
        error
        for error in errors
        if error.error_type in {
            "unknown_output_field",
            "missing_required_output_field",
            "invalid_ref_syntax",
            "array_shape_mismatch",
            "semantic_misbinding",
        }
    ]
    if not binding_errors:
        return 1.0
    return sum(1 for error in binding_errors if error.is_diagnosable) / len(binding_errors)


def _paths_match(left: str, right: str) -> bool:
    a = _normalize_gold_path(left)
    b = _normalize_gold_path(right)
    if a == b:
        return True
    a_body = a[1:]
    b_body = b[1:]
    return (
        b_body.startswith(a_body)
        and len(b_body) > len(a_body)
        and b_body[len(a_body)] in (".", "[")
    ) or (
        a_body.startswith(b_body)
        and len(a_body) > len(b_body)
        and a_body[len(b_body)] in (".", "[")
    )


def _normalize_gold_path(path: str) -> str:
    raw = path.strip()
    if not raw:
        return "."
    if not raw.startswith("."):
        raw = "." + raw
    raw = re.sub(r"\[\d+\]", "[]", raw)
    return raw


def _mean_bool(values: Iterable[bool]) -> float:
    vals = list(values)
    return sum(1 for value in vals if value) / len(vals) if vals else 0.0


def _mean_optional(values: Iterable[float | None]) -> float:
    vals = [value for value in values if value is not None]
    return sum(vals) / len(vals) if vals else 0.0


def _error_type_counts(results: list[ArmEvaluation]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        for error_type in result.error_types:
            counts[error_type] = counts.get(error_type, 0) + 1
    return dict(sorted(counts.items()))


def _smoke_error_type_counts(results: list[SmokeArmEvaluation]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        for error_type in result.error_types:
            counts[error_type] = counts.get(error_type, 0) + 1
    return dict(sorted(counts.items()))


def _parse_model_name(raw: str) -> str:
    from aicore.models.credentials import ModelName

    if raw in ModelName.__members__:
        return ModelName[raw].value
    try:
        return ModelName(raw).value
    except ValueError:
        return raw


def _parse_smoke_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run unlabeled POC-vs-Concept one-shot binding smoke experiment."
    )
    parser.add_argument(
        "--query-file",
        type=Path,
        default=Path("aicore/agents/plan/experiment/complex_query_v0.txt"),
        help="Line-oriented txt file. Non-empty lines are used as queries.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("aicore/agents/plan/experiment/reports"),
        help="Directory for smoke CSV and summary JSON outputs.",
    )
    parser.add_argument("--model", default="SEED_1_6_251015")
    parser.add_argument("--backend", choices=["chat", "responses"], default="responses")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args(argv)


async def _run_smoke_cli(args: argparse.Namespace) -> None:
    from aicore.models.model_api import ModelCallParams, create_model_api

    queries = load_query_txt(args.query_file)
    if args.limit is not None:
        queries = queries[: args.limit]

    tools = default_tool_contracts()
    model_api = create_model_api(
        model=_parse_model_name(args.model),
        backend=args.backend,
    )
    params = ModelCallParams(
        temperature=args.temperature,
        top_p=args.top_p,
        max_output_tokens=args.max_output_tokens,
    )

    async def poc_generator(case: ExperimentCase) -> BaselinePlan:
        return await generate_poc_plan(model_api, case, tools, params=params)

    async def concept_generator(case: ExperimentCase) -> ConceptPlan:
        return await generate_concept_plan(model_api, case, tools, params=params)

    results = await run_smoke_experiment(
        queries,
        tools=tools,
        poc_generator=poc_generator,
        concept_generator=concept_generator,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    case_csv = args.output_dir / "concept_binding_smoke_cases.csv"
    summary_json = args.output_dir / "concept_binding_smoke_summary.json"
    write_smoke_csv(results, case_csv)
    write_smoke_summary_report(results, summary_json)

    print(json.dumps(summarize_smoke_results(results), ensure_ascii=False, indent=2))
    print(f"\nwrote cases -> {case_csv}")
    print(f"wrote summary -> {summary_json}")


def main(argv: list[str] | None = None) -> None:
    import anyio

    args = _parse_smoke_args(argv)
    anyio.run(_run_smoke_cli, args, backend="asyncio")


if __name__ == "__main__":
    main()


__all__ = [
    "ArmEvaluation",
    "BaselinePlan",
    "BaselineStep",
    "ConceptPlan",
    "ConceptStep",
    "DynamicOutputSpec",
    "ExperimentCase",
    "ExperimentError",
    "GoldInputBinding",
    "GoldStep",
    "SmokeArmEvaluation",
    "ToolContract",
    "build_concept_prompt",
    "build_poc_prompt",
    "compile_selected_paths",
    "default_tool_contracts",
    "evaluate_concept_smoke",
    "evaluate_concept_plan",
    "evaluate_poc_smoke",
    "evaluate_poc_plan",
    "generate_concept_plan",
    "generate_poc_plan",
    "load_query_txt",
    "run_experiment",
    "run_smoke_experiment",
    "summarize_smoke_results",
    "summarize_results",
    "write_case_csv",
    "write_smoke_csv",
    "write_smoke_summary_report",
    "write_summary_report",
]
