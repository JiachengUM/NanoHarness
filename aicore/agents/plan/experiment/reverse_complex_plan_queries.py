from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

import anyio
from pydantic import BaseModel, Field
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from aicore.agents.plan.experiment.synthetic_complex_plan_cases import (
    SyntheticPlanCase,
    build_reverse_query_prompt,
    load_synthetic_case_file,
)
from aicore.models.model_api import UserMessage, create_model_api


class ReverseQueryOutput(BaseModel):
    query: str = Field(description="反向生成的自然语言用户 query")
    notes: str = Field(default="", description="一句话说明 query 覆盖的依赖关系")


class QueryNaturalnessJudgeOutput(BaseModel):
    is_natural: bool = Field(description="query 是否像自然用户请求")
    naturalness_score: int = Field(ge=1, le=5, description="综合质量评分，1=很差，5=很好")
    covers_plan: bool = Field(description="query 是否覆盖 plan 的主要步骤和依赖")
    is_logically_coherent: bool = Field(description="query 的业务因果和字段绑定是否合理")
    logic_score: int = Field(ge=1, le=5, description="业务逻辑合理性评分，1=明显荒唐，5=合理自然")
    logic_issues: list[str] = Field(description="业务逻辑、因果关系或字段绑定不合理的问题列表")
    leaks_implementation: bool = Field(description="query 是否泄露 $s1/op/schema/DAG 等实现细节")
    reason: str = Field(default="", description="简短判断理由")


ReverseQueryGenerator = Callable[[str], Awaitable[ReverseQueryOutput]]
QueryJudge = Callable[[str], Awaitable[QueryNaturalnessJudgeOutput]]
ProgressCallback = Callable[[dict[str, Any]], None]


async def run_reverse_query_generation(
    cases: list[SyntheticPlanCase],
    generator: ReverseQueryGenerator,
    *,
    judge: QueryJudge | None = None,
    concurrency: int = 20,
    api_timeout_seconds: float = 60,
    max_retries: int = 3,
    progress_callback: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any] | None] = [None] * len(cases)
    sem = anyio.Semaphore(concurrency)
    progress_lock = anyio.Lock()
    completed = 0
    generation_errors = 0
    judge_errors = 0

    _emit_progress(progress_callback, {"event": "start", "total": len(cases)})

    async def _run(idx: int, case: SyntheticPlanCase) -> None:
        nonlocal completed, generation_errors, judge_errors
        async with sem:
            _emit_progress(
                progress_callback,
                {
                    "event": "case_start",
                    "index": idx + 1,
                    "total": len(cases),
                    "case_id": case.case_id,
                    "topology_pattern": case.topology_pattern,
                },
            )
            rows[idx] = await _generate_one(
                case,
                generator,
                judge,
                api_timeout_seconds=api_timeout_seconds,
                max_retries=max_retries,
            )
            row = rows[idx] or {}
            generation_status = "error" if row.get("error") else "ok"
            judge_status = "skipped"
            if judge is not None:
                judge_status = "error" if row.get("judge_error") else "ok"
            async with progress_lock:
                completed += 1
                if generation_status == "error":
                    generation_errors += 1
                if judge_status == "error":
                    judge_errors += 1
                _emit_progress(
                    progress_callback,
                    {
                        "event": "case_done",
                        "index": idx + 1,
                        "total": len(cases),
                        "completed": completed,
                        "case_id": case.case_id,
                        "topology_pattern": case.topology_pattern,
                        "generation_status": generation_status,
                        "judge_status": judge_status,
                        "generation_errors": generation_errors,
                        "judge_errors": judge_errors,
                    },
                )

    async with anyio.create_task_group() as tg:
        for idx, case in enumerate(cases):
            tg.start_soon(_run, idx, case)

    _emit_progress(
        progress_callback,
        {
            "event": "finish",
            "total": len(cases),
            "completed": completed,
            "generation_errors": generation_errors,
            "judge_errors": judge_errors,
        },
    )
    return rows  # type: ignore[return-value]


def write_reverse_query_file(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "case_count": len(rows),
        "judge_summary": _judge_summary(rows),
        "cases": rows,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_reverse_query_filtered_file(
    rows: list[dict[str, Any]],
    output_path: Path,
    *,
    min_score: int = 4,
) -> None:
    write_reverse_query_file(_filter_rows_by_score(rows, min_score), output_path)


def write_reverse_query_subset_file(
    rows: list[dict[str, Any]],
    output_path: Path,
    *,
    min_score: int = 4,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subset_rows = [_subset_row(row) for row in _filter_rows_by_score(rows, min_score)]
    payload = {
        "version": 1,
        "case_count": len(subset_rows),
        "cases": subset_rows,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_query_judge_prompt(case: SyntheticPlanCase, generated_query: str) -> str:
    return (
        "你是 query 质量评估器。请判断 generated_query 是否像真实用户自然提出的问题，"
        "是否覆盖给定 synthetic plan 的主要意图，以及业务逻辑和因果关系是否合理。\n\n"
        "判断标准：\n"
        "- is_natural: 是否像自然用户表达，不能像 JSON 翻译或步骤机械转写。\n"
        "- covers_plan: 是否覆盖主要步骤和依赖关系。\n"
        "- is_logically_coherent: query 的业务目标、工具动作、字段绑定是否有现实语义。\n"
        "- logic_score: 1 到 5。评估业务因果是否合理，尤其关注上游字段是否适合驱动下游动作。\n"
        "- logic_issues: 列出所有牵强或无意义的业务逻辑，例如把唱片公司、歌名、播放动作等字段用于控制空调。\n"
        "- leaks_implementation: 是否出现 $s1、step_id、op、schema、DAG 等实现细节。\n"
        "- naturalness_score: 1 到 5 的综合可用质量分，不只是语言流畅度。"
        "如果 is_logically_coherent=false 或 logic_score <= 2，naturalness_score 不得超过 2。\n\n"
        "业务逻辑低分示例：\n"
        "- 根据唱片公司调整空调：唱片公司不是温度、风量、空调模式或车控意图，字段绑定没有现实因果，logic_score 应为 1 或 2。\n"
        "- 把唱片公司相关的信息加到播放列表：播放列表通常需要歌曲、专辑、歌手或音频内容，普通公司信息不适合作为播放内容，logic_score 应降低。\n"
        "- 用播放动作决定车控动作：除非 query 明确说这是用户自定义映射，否则属于牵强绑定。\n\n"
        "请输出 JSON：\n"
        "{\n"
        "  \"is_natural\": true,\n"
        "  \"naturalness_score\": 2,\n"
        "  \"covers_plan\": true,\n"
        "  \"is_logically_coherent\": false,\n"
        "  \"logic_score\": 1,\n"
        "  \"logic_issues\": [\"根据唱片公司调整空调缺少现实业务因果\"],\n"
        "  \"leaks_implementation\": false,\n"
        "  \"reason\": \"...\"\n"
        "}\n\n"
        f"generated_query: {generated_query}\n\n"
        "case:\n"
        f"{json.dumps(case.to_json_dict(), ensure_ascii=False, indent=2)}"
    )


async def _generate_one(
    case: SyntheticPlanCase,
    generator: ReverseQueryGenerator,
    judge: QueryJudge | None,
    *,
    api_timeout_seconds: float,
    max_retries: int,
) -> dict[str, Any]:
    prompt = build_reverse_query_prompt(case)
    try:
        output = await _call_api_with_retries(
            lambda: generator(prompt),
            operation="generation",
            timeout_seconds=api_timeout_seconds,
            max_retries=max_retries,
        )
        judge_result: dict[str, Any] | None = None
        judge_error: str | None = None
        if judge is not None:
            try:
                judge_prompt = build_query_judge_prompt(case, output.query)
                judge_output = await _call_api_with_retries(
                    lambda: judge(judge_prompt),
                    operation="judge",
                    timeout_seconds=api_timeout_seconds,
                    max_retries=max_retries,
                )
                judge_result = judge_output.model_dump()
            except Exception as exc:
                judge_error = f"{type(exc).__name__}: {exc}"
        return {
            "case": case.to_json_dict(),
            "prompt": prompt,
            "generated_query": output.query,
            "notes": output.notes,
            "judge": judge_result,
            "judge_error": judge_error,
            "error": None,
        }
    except Exception as exc:
        return {
            "case": case.to_json_dict(),
            "prompt": prompt,
            "generated_query": "",
            "notes": "",
            "judge": None,
            "judge_error": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def _call_api_with_retries(
    call: Callable[[], Awaitable[Any]],
    *,
    operation: str,
    timeout_seconds: float,
    max_retries: int,
) -> Any:
    attempts = max_retries + 1
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with anyio.fail_after(timeout_seconds):
                return await call()
        except Exception as exc:
            last_exc = exc
            if attempt == attempts:
                break
    assert last_exc is not None
    raise RuntimeError(
        f"{operation} failed after {attempts} attempts: "
        f"{type(last_exc).__name__}: {last_exc}"
    ) from last_exc


def _make_live_reverse_generator(
    *,
    model: str,
    backend: Literal["chat", "responses"],
) -> ReverseQueryGenerator:
    model_api = create_model_api(backend=backend, model=model)

    async def generate(prompt: str) -> ReverseQueryOutput:
        response = await model_api.structured_output(
            UserMessage(text=prompt),
            output_type=ReverseQueryOutput,
            state=model_api.initial_state(),
        )
        if response.parsed is None:
            raise ValueError(f"reverse query generation failed: {response.metadata}")
        return response.parsed

    return generate


def _make_live_judge(
    *,
    model: str,
    backend: Literal["chat", "responses"],
) -> QueryJudge:
    model_api = create_model_api(backend=backend, model=model)

    async def judge(prompt: str) -> QueryNaturalnessJudgeOutput:
        response = await model_api.structured_output(
            UserMessage(text=prompt),
            output_type=QueryNaturalnessJudgeOutput,
            state=model_api.initial_state(),
        )
        if response.parsed is None:
            raise ValueError(f"query judge failed: {response.metadata}")
        return response.parsed

    return judge


def _make_dry_run_generator() -> ReverseQueryGenerator:
    async def generate(prompt: str) -> ReverseQueryOutput:
        del prompt
        return ReverseQueryOutput(query="", notes="dry_run: prompt only")

    return generate


def _emit_progress(callback: ProgressCallback | None, event: dict[str, Any]) -> None:
    if callback is not None:
        callback(event)


class _RichProgressStatus:
    def __init__(self, total: int):
        self._total = total
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.fields[status]}"),
            TimeElapsedColumn(),
        )
        self._task_id = None

    def __enter__(self) -> "_RichProgressStatus":
        self._progress.__enter__()
        self._task_id = self._progress.add_task(
            "reverse queries",
            total=self._total,
            status="starting",
        )
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self._progress.__exit__(exc_type, exc, traceback)

    def callback(self, event: dict[str, Any]) -> None:
        if self._task_id is None:
            return
        if event["event"] == "case_start":
            self._progress.update(
                self._task_id,
                status=f"running {event['case_id']} ({event['topology_pattern']})",
            )
        elif event["event"] == "case_done":
            self._progress.update(
                self._task_id,
                completed=event["completed"],
                status=(
                    f"done {event['case_id']} "
                    f"gen={event['generation_status']} judge={event['judge_status']} "
                    f"errors={event['generation_errors']}/{event['judge_errors']}"
                ),
            )
        elif event["event"] == "finish":
            self._progress.update(
                self._task_id,
                completed=event["completed"],
                status=(
                    f"finished gen_errors={event['generation_errors']} "
                    f"judge_errors={event['judge_errors']}"
                ),
            )


def _judge_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [row["judge"] for row in rows if row.get("judge")]
    if not judged:
        return {
            "judged_count": 0,
            "natural_count": 0,
            "covers_plan_count": 0,
            "logically_coherent_count": 0,
            "leaks_implementation_count": 0,
            "avg_naturalness_score": None,
            "avg_logic_score": None,
        }
    return {
        "judged_count": len(judged),
        "natural_count": sum(1 for item in judged if item.get("is_natural")),
        "covers_plan_count": sum(1 for item in judged if item.get("covers_plan")),
        "logically_coherent_count": sum(1 for item in judged if item.get("is_logically_coherent")),
        "leaks_implementation_count": sum(1 for item in judged if item.get("leaks_implementation")),
        "avg_naturalness_score": sum(int(item.get("naturalness_score") or 0) for item in judged) / len(judged),
        "avg_logic_score": sum(int(item.get("logic_score") or 0) for item in judged) / len(judged),
    }


def _subset_row(row: dict[str, Any]) -> dict[str, Any]:
    case = row.get("case") or {}
    return {
        "case_id": case.get("case_id", ""),
        "topology_pattern": case.get("topology_pattern", ""),
        "generated_query": row.get("generated_query", ""),
        "plan": case.get("plan", {}),
    }


def _passes_subset_score_filter(row: dict[str, Any], min_score: int) -> bool:
    judge = row.get("judge")
    if not judge:
        return True
    score = judge.get("naturalness_score")
    if score is None:
        return True
    return int(score) >= min_score


def _filter_rows_by_score(rows: list[dict[str, Any]], min_score: int) -> list[dict[str, Any]]:
    return [row for row in rows if _passes_subset_score_filter(row, min_score)]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and judge natural user queries from synthetic complex plans.")
    parser.add_argument("--input", type=Path, default=Path("synthetic_complex_plan_cases.json"))
    parser.add_argument("--output", type=Path, default=Path("synthetic_complex_plan_queries.json"))
    parser.add_argument("--subset-output", type=Path, default=None)
    parser.add_argument("--filtered-full-output", type=Path, default=None)
    parser.add_argument("--model", default="SEED_1_6_251015")
    parser.add_argument("--backend", choices=["chat", "responses"], default="responses")
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--judge-backend", choices=["chat", "responses"], default=None)
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true", help="Write prompts without live LLM generation.")
    parser.add_argument("--no-progress", action="store_true", help="Disable rich progress output.")
    return parser.parse_args()


def _main() -> None:
    args = _parse_args()
    cases = load_synthetic_case_file(args.input)
    if args.limit is not None:
        cases = cases[: args.limit]

    generator = _make_dry_run_generator() if args.dry_run else _make_live_reverse_generator(
        model=args.model,
        backend=args.backend,
    )
    judge = None
    if not args.dry_run and not args.skip_judge:
        judge = _make_live_judge(
            model=args.judge_model or args.model,
            backend=args.judge_backend or args.backend,
        )

    async def _run(progress_callback: ProgressCallback | None = None) -> list[dict[str, Any]]:
        return await run_reverse_query_generation(
            cases,
            generator,
            judge=judge,
            concurrency=args.concurrency,
            progress_callback=progress_callback,
        )

    if args.no_progress:
        rows = anyio.run(_run)
    else:
        with _RichProgressStatus(total=len(cases)) as progress_status:
            rows = anyio.run(_run, progress_status.callback)
    write_reverse_query_file(rows, args.output)
    if args.subset_output is not None:
        write_reverse_query_subset_file(rows, args.subset_output)
    if args.filtered_full_output is not None:
        write_reverse_query_filtered_file(rows, args.filtered_full_output)
    error_count = sum(1 for row in rows if row.get("error"))
    judge_error_count = sum(1 for row in rows if row.get("judge_error"))
    print(
        f"wrote {len(rows)} rows ({error_count} generation errors, "
        f"{judge_error_count} judge errors) -> {args.output}"
    )


if __name__ == "__main__":
    _main()
