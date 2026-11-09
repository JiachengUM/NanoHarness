"""按 ModelName × 取消工具版本运行最小批量对比实验。"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Any

import anyio

from aicore.models.credentials import ModelName
from aicore.runtime.task import TaskProjection
from aicore.v2.experiments.task_cancel_eval.eval import (
    CancelToolVariant,
    create_cancel_agent_builder,
    normalize_cancel_variant,
)
from aicore.v2.experiments.task_cancel_eval.runner import (
    CancelEvaluationResult,
    CancelEvaluationSettings,
    CaseEvaluationResult,
    ObservedCancelCall,
    TurnEvaluationResult,
    evaluate_cancel_evaluation,
)

__all__ = [
    "BatchEvaluationResult",
    "BatchRunResult",
    "BatchSummary",
    "DEFAULT_MODELS",
    "DEFAULT_VARIANTS",
    "batch_evaluation_to_dict",
    "format_batch_report",
    "iter_batch_log_records",
    "main",
    "print_batch_summary",
    "run_batch_evaluation",
    "summarize_batch_runs",
    "write_batch_evaluation_jsonl",
    "write_batch_evaluation_json",
    "write_batch_report",
]


DEFAULT_MODELS: tuple[ModelName, ...] = (
    ModelName.SEED_2_1_PRO_260628,
    ModelName.SEED_2_0_PRO_260215,
    ModelName.SEED_2_0_MINI_260428,
)
DEFAULT_VARIANTS: tuple[CancelToolVariant, ...] = ("v0", "v1")


@dataclass(frozen=True)
class BatchRunResult:
    model: str
    variant: CancelToolVariant
    repetition: int
    evaluation: CancelEvaluationResult


@dataclass(frozen=True)
class BatchSummary:
    model: str
    variant: CancelToolVariant
    repetitions: int
    passed_cases: int
    total_cases: int
    passed_turns: int
    total_turns: int
    average_turn_duration_s: float
    total_case_duration_s: float
    average_case_duration_s: float
    timeout_cases: int
    error_cases: int
    passed_cancel_turns: int
    expected_cancel_turns: int

    @property
    def case_pass_rate(self) -> float:
        return _safe_ratio(self.passed_cases, self.total_cases)

    @property
    def turn_pass_rate(self) -> float:
        return _safe_ratio(self.passed_turns, self.total_turns)

    @property
    def cancel_pass_rate(self) -> float:
        return _safe_ratio(
            self.passed_cancel_turns,
            self.expected_cancel_turns,
        )

    @property
    def passed(self) -> bool:
        return self.passed_cases == self.total_cases


@dataclass(frozen=True)
class BatchEvaluationResult:
    models: tuple[str, ...]
    variants: tuple[CancelToolVariant, ...]
    case_names: tuple[str, ...] | None
    repeat: int
    concurrency: int
    delay_scale: float
    case_timeout: float
    runs: tuple[BatchRunResult, ...]

    @property
    def summaries(self) -> tuple[BatchSummary, ...]:
        return summarize_batch_runs(self.runs)

    @property
    def passed(self) -> bool:
        return all(run.evaluation.passed for run in self.runs)


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _average(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _normalize_model_name(model: str | ModelName) -> str:
    if isinstance(model, ModelName):
        return model.value
    if model in ModelName.__members__:
        return ModelName[model].value
    try:
        return ModelName(model).value
    except ValueError as exc:
        available = ", ".join(ModelName.__members__)
        raise ValueError(
            f"未知 ModelName: {model!r}. 可使用枚举名: {available}"
        ) from exc


def summarize_batch_runs(
    runs: Sequence[BatchRunResult],
) -> tuple[BatchSummary, ...]:
    grouped: dict[
        tuple[str, CancelToolVariant],
        list[BatchRunResult],
    ] = {}
    for run in runs:
        grouped.setdefault((run.model, run.variant), []).append(run)

    summaries: list[BatchSummary] = []
    for (model, variant), grouped_runs in grouped.items():
        case_results = [
            case_result
            for run in grouped_runs
            for case_result in run.evaluation.cases
        ]
        turn_results = [
            turn_result
            for case_result in case_results
            for turn_result in case_result.turns
        ]
        case_durations = [
            case_result.duration_s
            for case_result in case_results
        ]
        summaries.append(
            BatchSummary(
                model=model,
                variant=variant,
                repetitions=len(grouped_runs),
                passed_cases=sum(
                    case_result.passed
                    for case_result in case_results
                ),
                total_cases=len(case_results),
                passed_turns=sum(
                    case_result.passed_turns
                    for case_result in case_results
                ),
                total_turns=sum(
                    case_result.total_turns
                    for case_result in case_results
                ),
                average_turn_duration_s=_average(
                    [
                        turn_result.duration_s
                        for turn_result in turn_results
                    ]
                ),
                total_case_duration_s=sum(case_durations),
                average_case_duration_s=_average(case_durations),
                timeout_cases=sum(
                    case_result.error_type == "timeout"
                    for case_result in case_results
                ),
                error_cases=sum(
                    case_result.error_type == "exception"
                    for case_result in case_results
                ),
                passed_cancel_turns=sum(
                    turn_result.passed
                    and turn_result.expectation.decision == "call"
                    for turn_result in turn_results
                ),
                expected_cancel_turns=sum(
                    turn_result.expectation.decision == "call"
                    for turn_result in turn_results
                ),
            )
        )
    return tuple(summaries)


async def run_batch_evaluation(
    *,
    models: Sequence[str | ModelName] = DEFAULT_MODELS,
    variants: Sequence[str] = DEFAULT_VARIANTS,
    case_names: Sequence[str] | None = None,
    repeat: int = 1,
    concurrency: int = 4,
    settings: CancelEvaluationSettings | None = None,
    verbose: bool = False,
    progress: Callable[[str], None] | None = None,
) -> BatchEvaluationResult:
    if repeat <= 0:
        raise ValueError("repeat 必须大于 0")
    if concurrency <= 0:
        raise ValueError("concurrency 必须大于 0")

    normalized_models = tuple(
        dict.fromkeys(
            _normalize_model_name(model)
            for model in models
        )
    )
    if not normalized_models:
        raise ValueError("至少需要一个 ModelName")

    normalized_variants = tuple(
        dict.fromkeys(
            normalize_cancel_variant(variant)
            for variant in variants
        )
    )
    if not normalized_variants:
        raise ValueError("至少需要一个取消工具版本")

    base_settings = settings or CancelEvaluationSettings.from_env()
    evaluation_settings = CancelEvaluationSettings(
        delay_scale=base_settings.delay_scale,
        case_timeout=base_settings.case_timeout,
        case_concurrency=concurrency,
    )
    selected_case_names = (
        tuple(case_names)
        if case_names is not None
        else None
    )
    runs: list[BatchRunResult] = []

    for model in normalized_models:
        for variant in normalized_variants:
            for repetition in range(1, repeat + 1):
                if progress is not None:
                    progress(
                        f"[RUN] model={model} variant={variant} "
                        f"repeat={repetition}/{repeat}"
                    )
                evaluation = await evaluate_cancel_evaluation(
                    selected_case_names,
                    agent_builder=create_cancel_agent_builder(
                        variant,
                        model=model,
                    ),
                    settings=evaluation_settings,
                    verbose=verbose,
                )
                runs.append(
                    BatchRunResult(
                        model=model,
                        variant=variant,
                        repetition=repetition,
                        evaluation=evaluation,
                    )
                )

    return BatchEvaluationResult(
        models=normalized_models,
        variants=normalized_variants,
        case_names=selected_case_names,
        repeat=repeat,
        concurrency=concurrency,
        delay_scale=evaluation_settings.delay_scale,
        case_timeout=evaluation_settings.case_timeout,
        runs=tuple(runs),
    )


def _model_to_json(value: object) -> object:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return str(value)


def _json_compatible(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _json_compatible(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _json_compatible(item)
            for item in value
        ]
    return value


def _observed_call_to_dict(call: ObservedCancelCall) -> dict[str, Any]:
    return {
        "task_id": call.task_id,
        "projection": (
            _projection_to_dict(call.projection)
            if call.projection is not None
            else None
        ),
        "outcome": _model_to_json(call.outcome),
    }


def _projection_to_dict(
    projection: TaskProjection,
) -> dict[str, Any]:
    return projection.model_dump(mode="json")


def _observed_tool_call_to_dict(
    call: ObservedCancelToolCall,
) -> dict[str, Any]:
    return {
        "name": call.name,
        "arguments": _json_compatible(call.arguments),
        "active_tasks": [
            _projection_to_dict(task)
            for task in call.active_tasks
        ],
        "matched_task_ids": (
            list(call.matched_task_ids)
            if call.matched_task_ids is not None
            else None
        ),
    }


def _turn_result_to_dict(
    result: TurnEvaluationResult,
) -> dict[str, Any]:
    return {
        "index": result.index,
        "query": result.query,
        "expectation": _json_compatible(asdict(result.expectation)),
        "passed": result.passed,
        "reasons": list(result.reasons),
        "assistant_text": result.assistant_text,
        "observed_tool_calls": [
            _observed_tool_call_to_dict(call)
            for call in result.observed_tool_calls
        ],
        "observed_calls": [
            _observed_call_to_dict(call)
            for call in result.observed_calls
        ],
        "duration_s": result.duration_s,
        "active_tasks_before": [
            _projection_to_dict(task)
            for task in result.active_tasks_before
        ],
        "active_tasks_after": [
            _projection_to_dict(task)
            for task in result.active_tasks_after
        ],
    }


def _case_result_to_dict(
    result: CaseEvaluationResult,
) -> dict[str, Any]:
    return {
        "case_name": result.case_name,
        "passed": result.passed,
        "passed_turns": result.passed_turns,
        "total_turns": result.total_turns,
        "duration_s": result.duration_s,
        "error_type": result.error_type,
        "error": result.error,
        "turns": [
            _turn_result_to_dict(turn)
            for turn in result.turns
        ],
    }


def _evaluation_to_dict(
    result: CancelEvaluationResult,
) -> dict[str, Any]:
    return {
        "passed": result.passed,
        "passed_cases": result.passed_cases,
        "total_cases": result.total_cases,
        "passed_turns": result.passed_turns,
        "total_turns": result.total_turns,
        "cancel_tool_calls": result.cancel_tool_calls,
        "manager_cancel_calls": result.manager_cancel_calls,
        "passed_cancel_turns": result.passed_cancel_turns,
        "expected_cancel_turns": result.expected_cancel_turns,
        "cases": [
            _case_result_to_dict(case_result)
            for case_result in result.cases
        ],
    }


def _summary_to_dict(result: BatchSummary) -> dict[str, Any]:
    return {
        **asdict(result),
        "case_pass_rate": result.case_pass_rate,
        "turn_pass_rate": result.turn_pass_rate,
        "cancel_pass_rate": result.cancel_pass_rate,
        "passed": result.passed,
    }


def batch_evaluation_to_dict(
    result: BatchEvaluationResult,
) -> dict[str, Any]:
    return {
        "version": 2,
        "config": {
            "models": list(result.models),
            "variants": list(result.variants),
            "case_names": (
                list(result.case_names)
                if result.case_names is not None
                else "all"
            ),
            "repeat": result.repeat,
            "concurrency": result.concurrency,
            "delay_scale": result.delay_scale,
            "case_timeout": result.case_timeout,
        },
        "passed": result.passed,
        "summary": [
            _summary_to_dict(summary)
            for summary in result.summaries
        ],
        "runs": [
            {
                "model": run.model,
                "variant": run.variant,
                "repetition": run.repetition,
                "evaluation": _evaluation_to_dict(run.evaluation),
            }
            for run in result.runs
        ],
    }


def write_batch_evaluation_json(
    result: BatchEvaluationResult,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f"{output_path.name}.tmp"
    )
    temporary_path.write_text(
        json.dumps(
            batch_evaluation_to_dict(result),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary_path.replace(output_path)


def _case_results_by_name(
    run: BatchRunResult,
) -> dict[str, CaseEvaluationResult]:
    return {
        case.case_name: case
        for case in run.evaluation.cases
    }


def _joined_case_names(case_names: Sequence[str]) -> str:
    return ", ".join(f"`{name}`" for name in case_names) or "无"


def _summary_report_lines(
    result: BatchEvaluationResult,
) -> list[str]:
    lines = [
        "## 汇总",
        "",
        (
            "| 模型 | 版本 | 用例 | 用例通过率 | 轮次 | 轮次通过率 | "
            "取消轮次 | 取消通过率 | 平均轮次耗时（秒） | "
            "平均用例耗时（秒） | 超时 | 异常 |"
        ),
        (
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | "
            "---: | ---: | ---: | ---: |"
        ),
    ]
    for summary in result.summaries:
        lines.append(
            f"| {summary.model} | {summary.variant} | "
            f"{summary.passed_cases}/{summary.total_cases} | "
            f"{summary.case_pass_rate:.1%} | "
            f"{summary.passed_turns}/{summary.total_turns} | "
            f"{summary.turn_pass_rate:.1%} | "
            f"{summary.passed_cancel_turns}/"
            f"{summary.expected_cancel_turns} | "
            f"{summary.cancel_pass_rate:.1%} | "
            f"{summary.average_turn_duration_s:.3f} | "
            f"{summary.average_case_duration_s:.3f} | "
            f"{summary.timeout_cases} | {summary.error_cases} |"
        )
    lines.append("")
    return lines


def _paired_report_lines(
    result: BatchEvaluationResult,
) -> list[str]:
    runs_by_key = {
        (run.model, run.variant, run.repetition): run
        for run in result.runs
    }
    lines = ["## v0 / v1 同模型对照", ""]
    pair_count = 0
    for model in result.models:
        for repetition in range(1, result.repeat + 1):
            v0 = runs_by_key.get((model, "v0", repetition))
            v1 = runs_by_key.get((model, "v1", repetition))
            if v0 is None or v1 is None:
                continue
            pair_count += 1
            v0_cases = _case_results_by_name(v0)
            v1_cases = _case_results_by_name(v1)
            shared_names = [
                case.case_name
                for case in v0.evaluation.cases
                if case.case_name in v1_cases
            ]
            v0_only = [
                name
                for name in shared_names
                if v0_cases[name].passed and not v1_cases[name].passed
            ]
            v1_only = [
                name
                for name in shared_names
                if v1_cases[name].passed and not v0_cases[name].passed
            ]
            both_failed = [
                name
                for name in shared_names
                if not v0_cases[name].passed and not v1_cases[name].passed
            ]
            both_passed = sum(
                v0_cases[name].passed and v1_cases[name].passed
                for name in shared_names
            )
            lines.extend(
                [
                    f"### {model} · 第 {repetition} 次",
                    "",
                    f"- v0 通过、v1 失败：{_joined_case_names(v0_only)}",
                    f"- v1 通过、v0 失败：{_joined_case_names(v1_only)}",
                    f"- 两者都失败：{_joined_case_names(both_failed)}",
                    f"- 两者都通过：{both_passed}/{len(shared_names)}",
                    "",
                ]
            )
    if not pair_count:
        lines.extend(["本次没有可配对的 v0 / v1 运行。", ""])
    return lines


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _task_report_line(task: TaskProjection) -> str:
    payload = _projection_to_dict(task)
    arguments = json.dumps(
        payload.get("arguments", {}),
        ensure_ascii=False,
        sort_keys=True,
    )
    return (
        f"`{payload.get('task_id')}` "
        f"{payload.get('tool_name')}({arguments}) "
        f"[{payload.get('status')}]"
    )


def _expectation_description(result: TurnEvaluationResult) -> str:
    descriptions = {
        "none": "不应调用取消工具",
        "call": "应调用取消工具",
        "clarify": "应澄清取消目标",
        "reject": "应拒绝调用取消工具",
    }
    return descriptions[result.expectation.decision]


def _turn_report_lines(
    run: BatchRunResult,
    case: CaseEvaluationResult,
    turn: TurnEvaluationResult,
) -> list[str]:
    status = "通过" if turn.passed else "错误"
    lines = [
        (
            f"### [{status}] {run.model} · {run.variant} · "
            f"第 {run.repetition} 次 · {case.case_name} · "
            f"第 {turn.index + 1} 轮"
        ),
        "",
        f"- 用户输入：{_single_line(turn.query)}",
        (
            "- 预期："
            f"{_expectation_description(turn)} · "
            f"{_single_line(turn.expectation.note)}"
        ),
        f"- 结果：{status}",
        f"- 耗时：{turn.duration_s:.3f}s",
    ]
    if turn.reasons:
        lines.append(
            "- 判分原因："
            + "；".join(_single_line(reason) for reason in turn.reasons)
        )

    lines.append("- 本轮开始时活跃任务：")
    if turn.active_tasks_before:
        lines.extend(
            f"  - {_task_report_line(task)}"
            for task in turn.active_tasks_before
        )
    else:
        lines.append("  - 无")

    lines.append("- 模型取消工具调用：")
    if not turn.observed_tool_calls:
        lines.append("  - 无")
    for call in turn.observed_tool_calls:
        arguments = json.dumps(
            call.arguments,
            ensure_ascii=False,
            sort_keys=True,
        )
        lines.append(f"  - `{call.name}` {arguments}")
        if call.matched_task_ids is not None:
            lines.append(
                "    - v1 后台匹配命中："
                f"{len(call.matched_task_ids)} 个 "
                f"{list(call.matched_task_ids)}"
            )
        lines.append("    - 调用时活跃任务：")
        if call.active_tasks:
            lines.extend(
                f"      - {_task_report_line(task)}"
                for task in call.active_tasks
            )
        else:
            lines.append("      - 无")

    lines.append("- 实际取消调用（TaskManager）：")
    if not turn.observed_calls:
        lines.append("  - 无")
    for call in turn.observed_calls:
        projection = (
            _task_report_line(call.projection)
            if call.projection is not None
            else f"`{call.task_id}` (projection missing)"
        )
        lines.append(f"  - {projection} -> `{call.outcome.status}`")

    lines.extend(
        [
            (
                "- Agent 回复："
                f"{_single_line(turn.assistant_text) or '无文本回复'}"
            ),
            "",
        ]
    )
    return lines


def format_batch_report(
    result: BatchEvaluationResult,
    *,
    include_passed: bool = False,
) -> str:
    """生成只包含通过状态、判分原因和逐轮原始证据的 Markdown 报告。"""

    lines = [
        "# 取消任务批量测评报告",
        "",
        (
            f"- 实验运行数：{len(result.runs)}"
            f"；重复次数：{result.repeat}"
            f"；用例并发数：{result.concurrency}"
        ),
        (
            f"- 用例通过数："
            f"{sum(summary.passed_cases for summary in result.summaries)}/"
            f"{sum(summary.total_cases for summary in result.summaries)}"
        ),
        (
            f"- 轮次通过数："
            f"{sum(summary.passed_turns for summary in result.summaries)}/"
            f"{sum(summary.total_turns for summary in result.summaries)}"
        ),
        "",
        *_summary_report_lines(result),
        *_paired_report_lines(result),
        "## 逐轮原始结果",
        "",
    ]
    detail_count = 0
    for run in result.runs:
        for case in run.evaluation.cases:
            if case.error is not None:
                detail_count += 1
                lines.extend(
                    [
                        (
                            f"### [错误] {run.model} · {run.variant} · "
                            f"第 {run.repetition} 次 · {case.case_name}"
                        ),
                        "",
                        f"- 用例异常：`{case.error_type}` {case.error}",
                        "",
                    ]
                )
            for turn in case.turns:
                if not include_passed and turn.passed:
                    continue
                detail_count += 1
                lines.extend(_turn_report_lines(run, case, turn))
    if not detail_count:
        lines.extend(["没有失败轮次。", ""])
    return "\n".join(lines).rstrip() + "\n"


def write_batch_report(
    result: BatchEvaluationResult,
    output_path: Path,
    *,
    include_passed: bool = False,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f"{output_path.name}.tmp")
    temporary_path.write_text(
        format_batch_report(result, include_passed=include_passed),
        encoding="utf-8",
    )
    temporary_path.replace(output_path)


def iter_batch_log_records(
    result: BatchEvaluationResult,
) -> Iterator[dict[str, Any]]:
    """按 case/turn 产出适合检索和 diff 的 JSONL 日志记录。"""

    for run in result.runs:
        for case in run.evaluation.cases:
            if case.error is not None:
                yield {
                    "record_type": "case_error",
                    "model": run.model,
                    "variant": run.variant,
                    "repetition": run.repetition,
                    "case_name": case.case_name,
                    "passed": False,
                    "duration_s": case.duration_s,
                    "error_type": case.error_type,
                    "error": case.error,
                }
            for turn in case.turns:
                yield {
                    "record_type": "turn",
                    "model": run.model,
                    "variant": run.variant,
                    "repetition": run.repetition,
                    "case_name": case.case_name,
                    "case_passed": case.passed,
                    "status": "pass" if turn.passed else "error",
                    "turn": _turn_result_to_dict(turn),
                }


def write_batch_evaluation_jsonl(
    result: BatchEvaluationResult,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f"{output_path.name}.tmp")
    content = "".join(
        json.dumps(record, ensure_ascii=False) + "\n"
        for record in iter_batch_log_records(result)
    )
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(output_path)


def print_batch_summary(result: BatchEvaluationResult) -> None:
    summaries = result.summaries
    print()
    print(
        "model".ljust(32),
        "ver",
        "cases".rjust(11),
        "case%".rjust(7),
        "turns".rjust(11),
        "turn%".rjust(7),
        "cancel".rjust(11),
        "avg_turn_s".rjust(10),
        "total_case_s".rjust(12),
        "avg_case_s".rjust(10),
        "timeout".rjust(7),
        "errors".rjust(6),
    )
    print("-" * 140)
    for summary in summaries:
        print(
            summary.model.ljust(32),
            summary.variant.rjust(3),
            (
                f"{summary.passed_cases}/{summary.total_cases}"
            ).rjust(11),
            f"{summary.case_pass_rate:.1%}".rjust(7),
            (
                f"{summary.passed_turns}/{summary.total_turns}"
            ).rjust(11),
            f"{summary.turn_pass_rate:.1%}".rjust(7),
            (
                f"{summary.passed_cancel_turns}/"
                f"{summary.expected_cancel_turns}"
            ).rjust(11),
            f"{summary.average_turn_duration_s:.3f}".rjust(10),
            f"{summary.total_case_duration_s:.3f}".rjust(12),
            f"{summary.average_case_duration_s:.3f}".rjust(10),
            str(summary.timeout_cases).rjust(7),
            str(summary.error_cases).rjust(6),
        )

    print(
        f"\n[BATCH {'PASS' if result.passed else 'FAIL'}] "
        f"runs={len(result.runs)} "
        f"concurrency={result.concurrency}"
    )


def _model_argument(value: str) -> str:
    try:
        return _normalize_model_name(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须大于 0")
    return parsed


def _parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "批量比较 task cancel v0/v1 "
            "在多个模型上的通过率与端到端耗时。"
        )
    )
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        type=_model_argument,
        help=(
            "ModelName 枚举名或值；可重复传入，"
            "默认使用内置三模型组。"
        ),
    )
    parser.add_argument(
        "--variant",
        dest="variants",
        action="append",
        choices=DEFAULT_VARIANTS,
        help="取消工具版本；可重复传入，默认运行 v0 和 v1。",
    )
    parser.add_argument(
        "--case",
        dest="case_names",
        action="append",
        help="case 名称；可重复传入，默认运行全部。",
    )
    parser.add_argument(
        "--repeat",
        type=_positive_integer,
        default=1,
    )
    parser.add_argument(
        "--concurrency",
        type=_positive_integer,
        default=4,
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="打印 runner 的逐 case/turn 过程。",
    )
    parser.add_argument(
        "--report",
        choices=("none", "failures", "all"),
        default="failures",
        help=(
            "终端诊断报告范围；默认输出失败轮次，"
            "all 会同时输出通过轮次。"
        ),
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=None,
        help="可选保存 Markdown 诊断报告。",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="可选的完整 JSON 结果输出路径。",
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=None,
        help="可选保存逐 turn、便于检索和 diff 的 JSONL 日志。",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    models = tuple(args.models or DEFAULT_MODELS)
    variants = tuple(args.variants or DEFAULT_VARIANTS)

    async def run() -> BatchEvaluationResult:
        return await run_batch_evaluation(
            models=models,
            variants=variants,
            case_names=args.case_names,
            repeat=args.repeat,
            concurrency=args.concurrency,
            verbose=args.verbose,
            progress=print,
        )

    try:
        result = anyio.run(run)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    print_batch_summary(result)
    include_passed = args.report == "all"
    if args.report != "none":
        print()
        print(
            format_batch_report(
                result,
                include_passed=include_passed,
            ),
            end="",
        )
    if args.output_report is not None:
        write_batch_report(
            result,
            args.output_report,
            include_passed=include_passed,
        )
        print(f"[WROTE] {args.output_report}")
    if args.output_json is not None:
        write_batch_evaluation_json(result, args.output_json)
        print(f"[WROTE] {args.output_json}")
    if args.output_jsonl is not None:
        write_batch_evaluation_jsonl(result, args.output_jsonl)
        print(f"[WROTE] {args.output_jsonl}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
