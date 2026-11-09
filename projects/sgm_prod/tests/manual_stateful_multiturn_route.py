"""
手动状态化多轮 planner 测试脚本。

直接运行内置样例：
    python projects/sgm_prod/tests/manual_stateful_multiturn_route.py

快速测试单个当前轮：
    python projects/sgm_prod/tests/manual_stateful_multiturn_route.py \
      --query "便宜一点的" \
      --history-json '[{"query":"找附近停车场","route":"simple"}]' \
      --state-json '{"active_route":"simple","active_domain":"navigation","status":"candidates_returned","candidates":[{"id":"p1","name":"停车场A","price":"12元/小时"},{"id":"p2","name":"停车场B","price":"8元/小时"}]}' \
      --expected complex

完整 session 里，上一轮的 state_after 会作为下一轮的 state 传入。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from projects.sgm_prod.classification.llm import llm_stateful_multiturn_route
from projects.sgm_prod.classification.models import IntentType
from projects.sgm_prod.tests.manual_multiturn_llm_route import normalize_route


DEFAULT_STATEFUL_SESSIONS: list[dict[str, Any]] = [
    {
        "name": "parking candidates then price refinement",
        "turns": [
            {
                "query": "找附近停车场",
                "route": "simple",
                "state_after": {
                    "active_route": "simple",
                    "active_domain": "navigation",
                    "status": "candidates_returned",
                    "expected_user_action": "select_or_refine_candidates",
                    "candidates": [
                        {"id": "p1", "name": "西岸停车场A", "type": "parking", "price": "12元/小时"},
                        {"id": "p2", "name": "西岸停车场B", "type": "parking", "price": "8元/小时"},
                    ],
                },
            },
            {"query": "便宜一点的", "route": "complex"},
        ],
    },
    {
        "name": "mall candidates then ask second candidate attribute",
        "turns": [
            {
                "query": "帮我找附近的商场",
                "route": "simple",
                "state_after": {
                    "active_route": "simple",
                    "active_domain": "navigation",
                    "status": "candidates_returned",
                    "expected_user_action": "select_candidate",
                    "candidates": [
                        {"id": "m1", "name": "西岸凤巢", "type": "mall"},
                        {"id": "m2", "name": "正大乐城", "type": "mall"},
                    ],
                },
            },
            {"query": "第二个停车方便吗", "route": "complex"},
        ],
    },
    {
        "name": "complex recommendation resolved to executable action",
        "turns": [
            {
                "query": "推荐一个适合带孩子玩的地方",
                "route": "complex",
                "state_after": {
                    "active_route": "complex",
                    "active_domain": "navigation",
                    "status": "candidates_returned",
                    "expected_user_action": "select_candidate",
                    "executable_actions": ["navigate"],
                    "candidates": [
                        {"id": "poi1", "name": "上海自然博物馆", "type": "poi"},
                        {"id": "poi2", "name": "上海科技馆", "type": "poi"},
                    ],
                },
            },
            {"query": "第一个，开始导航", "route": "simple"},
        ],
    },
    {
        "name": "direct new task ignores stale state",
        "turns": [
            {
                "query": "帮我找附近的商场",
                "route": "simple",
                "state_after": {
                    "active_route": "simple",
                    "active_domain": "navigation",
                    "status": "candidates_returned",
                    "candidates": [{"id": "m1", "name": "西岸凤巢", "type": "mall"}],
                },
            },
            {"query": "播放张学友的吻别", "route": "simple"},
        ],
    },
]


@dataclass(frozen=True)
class StatefulTurnCase:
    name: str
    turn_index: int
    query: str
    history: list[dict[str, str]]
    state: dict[str, Any] | None
    expected: IntentType | None = None


@dataclass(frozen=True)
class StatefulTurnResult:
    case: StatefulTurnCase
    actual: IntentType
    latency_ms: float

    @property
    def correct(self) -> bool | None:
        if self.case.expected is None:
            return None
        return self.actual == self.case.expected


def _load_json_arg(raw: str) -> Any:
    stripped = raw.strip()
    if stripped.startswith(("{", "[")):
        return json.loads(stripped)
    path = Path(raw)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(stripped)


def _turn_query(turn: dict[str, Any], *, session_name: str, turn_index: int) -> str:
    query = str(turn.get("query") or turn.get("q") or "").strip()
    if not query:
        raise ValueError(f"{session_name}: turn {turn_index} missing query")
    return query


def _turn_route(turn: dict[str, Any], *, session_name: str, turn_index: int) -> IntentType:
    raw_route = turn.get("route", turn.get("expected"))
    if raw_route is None or str(raw_route).strip() == "":
        raise ValueError(f"{session_name}: turn {turn_index} missing route/expected")
    return normalize_route(raw_route)


def _state_after(turn: dict[str, Any]) -> dict[str, Any] | None:
    state = turn.get("state_after", turn.get("result_state"))
    if state is None:
        return None
    if not isinstance(state, dict):
        raise ValueError("state_after/result_state must be a JSON object")
    return state


def build_stateful_turn_cases(sessions: list[dict[str, Any]]) -> list[StatefulTurnCase]:
    cases: list[StatefulTurnCase] = []
    for session_index, session in enumerate(sessions, start=1):
        name = str(session.get("name") or f"session_{session_index}").strip()
        turns = session.get("turns")
        if not isinstance(turns, list) or len(turns) < 2:
            raise ValueError(f"{name}: session must contain at least two turns")

        history: list[dict[str, str]] = []
        active_state: dict[str, Any] | None = None
        for turn_index, turn in enumerate(turns, start=1):
            if not isinstance(turn, dict):
                raise ValueError(f"{name}: turn {turn_index} must be an object")
            query = _turn_query(turn, session_name=name, turn_index=turn_index)
            route = _turn_route(turn, session_name=name, turn_index=turn_index)
            state = turn.get("state", active_state)
            if state is not None and not isinstance(state, dict):
                raise ValueError(f"{name}: turn {turn_index} state must be a JSON object")

            if turn_index > 1:
                cases.append(
                    StatefulTurnCase(
                        name=name,
                        turn_index=turn_index,
                        query=query,
                        history=list(history),
                        state=state,
                        expected=route,
                    )
                )

            history.append({"query": query, "route": route})
            next_state = _state_after(turn)
            if next_state is not None:
                active_state = next_state
    return cases


def _load_cases_from_args(args: argparse.Namespace) -> list[StatefulTurnCase]:
    if args.query:
        history = _load_json_arg(args.history_json) if args.history_json else []
        state = _load_json_arg(args.state_json) if args.state_json else None
        if not isinstance(history, list):
            raise ValueError("--history-json must be a JSON list")
        if state is not None and not isinstance(state, dict):
            raise ValueError("--state-json must be a JSON object")
        expected = normalize_route(args.expected) if args.expected else None
        return [
            StatefulTurnCase(
                name="single stateful query",
                turn_index=len(history) + 1,
                query=args.query,
                history=history,
                state=state,
                expected=expected,
            )
        ]

    if args.cases_json:
        payload = _load_json_arg(args.cases_json)
    else:
        payload = DEFAULT_STATEFUL_SESSIONS

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("--cases-json must be a JSON object or list")
    return build_stateful_turn_cases(payload)


async def run_cases(cases: list[StatefulTurnCase]) -> list[StatefulTurnResult]:
    results: list[StatefulTurnResult] = []
    for case in cases:
        started = time.perf_counter()
        actual = await llm_stateful_multiturn_route(
            case.query,
            history=case.history,
            state=case.state,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        result = StatefulTurnResult(case=case, actual=actual, latency_ms=latency_ms)
        results.append(result)
        _print_result(result)
    return results


def _print_result(result: StatefulTurnResult) -> None:
    case = result.case
    print("=" * 80)
    print(f"name       : {case.name}")
    print(f"turn       : Q{case.turn_index}")
    print(f"query      : {case.query}")
    print(f"history    : {json.dumps(case.history, ensure_ascii=False)}")
    print(f"state      : {json.dumps(case.state, ensure_ascii=False)}")
    print(f"expected   : {case.expected or 'n/a'}")
    print(f"actual     : {result.actual}")
    print(f"correct    : {result.correct if result.correct is not None else 'n/a'}")
    print(f"latency_ms : {result.latency_ms:.3f}")


def _print_summary(results: list[StatefulTurnResult]) -> None:
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
    print(f"total         : {len(results)}")
    print(f"judged        : {len(judged)}")
    print(f"correct       : {correct}")
    print(f"accuracy      : {correct / len(judged):.6f}" if judged else "accuracy      : n/a")
    print(f"false_simple  : {false_simple}")
    print(f"false_complex : {false_complex}")
    print(f"avg_latency_ms: {avg_latency:.3f}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual local runner for llm_stateful_multiturn_route(query, history, state)."
    )
    parser.add_argument("--query", help="Run one current user query.")
    parser.add_argument(
        "--history-json",
        default="[]",
        help='History JSON list, e.g. [{"query":"找附近停车场","route":"simple"}].',
    )
    parser.add_argument("--state-json", help="Structured state JSON object or local JSON file path.")
    parser.add_argument("--expected", help="Optional expected route: simple/complex.")
    parser.add_argument(
        "--cases-json",
        help=(
            "Inline JSON or a local JSON file path. Shape: "
            '[{"name":"case","turns":[{"query":"...","route":"simple","state_after":{}}]}].'
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
