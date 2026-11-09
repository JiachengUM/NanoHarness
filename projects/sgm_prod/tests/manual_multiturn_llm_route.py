"""
手动多轮 LLM 路由测试脚本。

直接运行内置样例：
    python projects/sgm_prod/tests/manual_multiturn_llm_route.py

快速测试单个当前轮：
    python projects/sgm_prod/tests/manual_multiturn_llm_route.py \
      --query "第一个" \
      --history-json '[{"query":"导航去深圳湾公园","route":"simple"}]' \
      --expected simple

也可以传入完整 session JSON：
    python projects/sgm_prod/tests/manual_multiturn_llm_route.py \
      --cases-json '[{"name":"nav","turns":[{"query":"导航去深圳湾公园","route":"simple"},{"query":"第一个","route":"simple"}]}]'
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from projects.sgm_prod.classification.llm import llm_multiturn_route
from projects.sgm_prod.classification.models import IntentType


DEFAULT_SESSIONS: list[dict[str, Any]] = [
    # {
    #     "name": "simple navigation flow",
    #     "turns": [
    #         {"query": "导航去深圳湾公园", "route": "simple"},
    #         {"query": "第一个", "route": "simple"},
    #         {"query": "开始导航", "route": "simple"},
    #     ],
    # },
    # {
    #     "name": "complex recommendation flow",
    #     "turns": [
    #         {"query": "推荐一个适合带孩子玩的地方", "route": "complex"},
    #         {"query": "第一个", "route": "complex"},
    #         {"query": "再换一个类似的", "route": "complex"},
    #     ],
    # },
    # {
    #     "name": "new simple task interrupts history",
    #     "turns": [
    #         {"query": "推荐几首适合开长途听的歌", "route": "complex"},
    #         {"query": "播放张学友的吻别", "route": "simple"},
    #     ],
    # },
    # {
    #     "name": "simple music flow",
    #     "turns": [
    #         {"query": "播放周杰伦的七里香", "route": "simple"},
    #         {"query": "下一首", "route": "simple"},
    #         {"query": "打开歌词", "route": "simple"},
    #     ],
    # },
    {
        "name": "Hard positive1",
        "turns": [
            {"query": "找附近停车场", "route": "simple"},
            {"query": "便宜一点的", "route": "complex"},
        ],
    },
    {
        "name": "Hard positive2",
        "turns": [
            {"query": "帮我找附近的商场", "route": "simple"},
            {"query": "第二个停车方便吗", "route": "complex"},
        ],
    },
    {
        "name": "Hard positive3",
        "turns": [
            {"query": "播放张学友的吻别", "route": "simple"},
            {"query": "换成现场版", "route": "complex"},
        ],
    },
    {
        "name": "Hard negative1",
        "turns": [
            {"query": "导航去虹桥机场", "route": "simple"},
            {"query": "虹桥机场停车费贵吗，比浦东机场便宜吗", "route": "complex"},
        ],
    },
    {
        "name": "Hard negative2",
        "turns": [
            {"query": "导航去虹桥机场", "route": "simple"},
            {"query": "上海今天的天气怎么样", "route": "complex"},
        ],
    },
    {
        "name": "架构问题，planner，否则无解",
        "turns": [
            {"query": "帮我导航到最近商场", "route": "simple"},
            {"query": "现在先帮我找个附近的洗手间，再去接一下我老婆", "route": "complex"},
        ],
    },
]


@dataclass(frozen=True)
class ManualTurnCase:
    name: str
    turn_index: int
    query: str
    history: list[dict[str, str]]
    expected: IntentType | None = None


@dataclass(frozen=True)
class ManualTurnResult:
    case: ManualTurnCase
    actual: IntentType
    latency_ms: float

    @property
    def correct(self) -> bool | None:
        if self.case.expected is None:
            return None
        return self.actual == self.case.expected


def normalize_route(value: Any) -> IntentType:
    route = str(value).strip().lower()
    if route in {"simple", "简单"}:
        return "simple"
    if route in {"complex", "复杂"}:
        return "complex"
    raise ValueError(f"invalid route: {value!r}; expected simple/complex/简单/复杂")


def _turn_query(turn: dict[str, Any], *, session_name: str, turn_index: int) -> str:
    query = str(turn.get("query") or turn.get("q") or "").strip()
    if not query:
        raise ValueError(f"{session_name}: turn {turn_index} missing query")
    return query


def _turn_route(turn: dict[str, Any], *, session_name: str, turn_index: int) -> IntentType:
    raw_route = turn.get("route", turn.get("expected"))
    if raw_route is None or str(raw_route).strip() == "":
        raise ValueError(
            f"{session_name}: turn {turn_index} missing route/expected; "
            "previous turns must have known labels"
        )
    return normalize_route(raw_route)


def build_turn_cases(sessions: list[dict[str, Any]]) -> list[ManualTurnCase]:
    cases: list[ManualTurnCase] = []
    for session_index, session in enumerate(sessions, start=1):
        name = str(session.get("name") or f"session_{session_index}").strip()
        turns = session.get("turns")
        if not isinstance(turns, list) or len(turns) < 2:
            raise ValueError(f"{name}: session must contain at least two turns")

        history: list[dict[str, str]] = []
        for turn_index, turn in enumerate(turns, start=1):
            if not isinstance(turn, dict):
                raise ValueError(f"{name}: turn {turn_index} must be an object")
            query = _turn_query(turn, session_name=name, turn_index=turn_index)
            route = _turn_route(turn, session_name=name, turn_index=turn_index)
            if turn_index > 1:
                cases.append(
                    ManualTurnCase(
                        name=name,
                        turn_index=turn_index,
                        query=query,
                        history=list(history),
                        expected=route,
                    )
                )
            history.append({"query": query, "route": route})
    return cases


def _load_json_arg(raw: str) -> Any:
    stripped = raw.strip()
    if stripped.startswith(("{", "[")):
        return json.loads(stripped)
    path = Path(raw)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(stripped)


def _load_cases_from_args(args: argparse.Namespace) -> list[ManualTurnCase]:
    if args.query:
        history = _load_json_arg(args.history_json) if args.history_json else []
        if not isinstance(history, list):
            raise ValueError("--history-json must be a JSON list")
        expected = normalize_route(args.expected) if args.expected else None
        return [
            ManualTurnCase(
                name="single query",
                turn_index=len(history) + 1,
                query=args.query,
                history=history,
                expected=expected,
            )
        ]

    if args.cases_json:
        payload = _load_json_arg(args.cases_json)
    else:
        payload = DEFAULT_SESSIONS

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("--cases-json must be a JSON object or list")
    return build_turn_cases(payload)


async def run_cases(cases: list[ManualTurnCase]) -> list[ManualTurnResult]:
    results: list[ManualTurnResult] = []
    for case in cases:
        started = time.perf_counter()
        actual = await llm_multiturn_route(case.query, history=case.history)
        latency_ms = (time.perf_counter() - started) * 1000
        result = ManualTurnResult(case=case, actual=actual, latency_ms=latency_ms)
        results.append(result)
        _print_result(result)
    return results


def _print_result(result: ManualTurnResult) -> None:
    case = result.case
    print("=" * 80)
    print(f"name       : {case.name}")
    print(f"turn       : Q{case.turn_index}")
    print(f"query      : {case.query}")
    print(f"history    : {json.dumps(case.history, ensure_ascii=False)}")
    print(f"expected   : {case.expected or 'n/a'}")
    print(f"actual     : {result.actual}")
    print(f"correct    : {result.correct if result.correct is not None else 'n/a'}")
    print(f"latency_ms : {result.latency_ms:.3f}")


def _print_summary(results: list[ManualTurnResult]) -> None:
    judged = [result for result in results if result.correct is not None]
    correct = sum(1 for result in judged if result.correct)
    total_latency = sum(result.latency_ms for result in results)
    avg_latency = total_latency / len(results) if results else 0.0
    false_simple = sum(
        1
        for result in judged
        if result.case.expected == "complex" and result.actual == "simple"
    )
    false_complex = sum(
        1
        for result in judged
        if result.case.expected == "simple" and result.actual == "complex"
    )

    print("=" * 80)
    print("Summary")
    print(f"total        : {len(results)}")
    print(f"judged       : {len(judged)}")
    print(f"correct      : {correct}")
    print(f"accuracy     : {correct / len(judged):.6f}" if judged else "accuracy     : n/a")
    print(f"false_simple : {false_simple}")
    print(f"false_complex: {false_complex}")
    print(f"avg_latency_ms: {avg_latency:.3f}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual local runner for llm_multiturn_route(query, history=...)."
    )
    parser.add_argument("--query", help="Run one current user query.")
    parser.add_argument(
        "--history-json",
        default="[]",
        help='History JSON list, e.g. [{"query":"导航去深圳湾公园","route":"simple"}].',
    )
    parser.add_argument("--expected", help="Optional expected route: simple/complex.")
    parser.add_argument(
        "--cases-json",
        help=(
            "Inline JSON or a local JSON file path. Shape: "
            '[{"name":"case","turns":[{"query":"...","route":"simple"}]}].'
        ),
    )
    return parser.parse_args()


async def _main_async() -> None:
    args = _parse_args()
    cases = _load_cases_from_args(args)
    results = await run_cases(cases)
    _print_summary(results)


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
