from __future__ import annotations

from projects.sgm_prod.tests.manual_multiturn_llm_route import build_turn_cases


def test_build_turn_cases_uses_previous_golden_routes() -> None:
    cases = build_turn_cases(
        [
            {
                "name": "simple navigation session",
                "turns": [
                    {"query": "导航去深圳湾公园", "route": "simple"},
                    {"query": "第一个", "expected": "simple"},
                    {"query": "开始导航", "route": "simple"},
                ],
            }
        ]
    )

    assert [(case.name, case.turn_index, case.query, case.expected) for case in cases] == [
        ("simple navigation session", 2, "第一个", "simple"),
        ("simple navigation session", 3, "开始导航", "simple"),
    ]
    assert cases[0].history == [
        {"query": "导航去深圳湾公园", "route": "simple"},
    ]
    assert cases[1].history == [
        {"query": "导航去深圳湾公园", "route": "simple"},
        {"query": "第一个", "route": "simple"},
    ]
