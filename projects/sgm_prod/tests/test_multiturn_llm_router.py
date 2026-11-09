from __future__ import annotations

from pathlib import Path

import pandas as pd

from projects.sgm_prod.classification.tools.evaluate_multiturn_llm_router import (
    MultiturnCase,
    MultiturnResult,
    format_result_summary,
    load_multiturn_cases,
    summarize_by_turn,
)


def test_load_multiturn_cases_uses_previous_golden_labels(tmp_path: Path) -> None:
    workbook = tmp_path / "multi_turn.xlsx"
    with pd.ExcelWriter(workbook) as writer:
        pd.DataFrame(
            [
                {
                    "Query1": "导航去火车站",
                    "预期落域": "简单",
                    "Query2": "第一个",
                    "预期落域.1": "简单",
                    "Query3": "开始导航",
                    "预期落域.2": "简单",
                },
                {
                    "Query1": "找个适合带孩子玩的地方",
                    "预期落域": "复杂",
                    "Query2": "第一个",
                    "预期落域.1": "复杂",
                    "Query3": "",
                    "预期落域.2": "",
                },
            ]
        ).to_excel(writer, index=False, sheet_name="【整合】导航多轮表")
        pd.DataFrame(
            [
                {
                    "Query1": "播放周杰伦的七里香",
                    "预期落域": "简单",
                    "Query2": "下一首",
                    "预期落域.1": "简单",
                }
            ]
        ).to_excel(writer, index=False, sheet_name="【整合】音乐多轮表")

    cases = load_multiturn_cases(workbook)

    assert [(case.sheet_name, case.row_number, case.turn_index) for case in cases] == [
        ("【整合】导航多轮表", 2, 2),
        ("【整合】导航多轮表", 2, 3),
        ("【整合】导航多轮表", 3, 2),
        ("【整合】音乐多轮表", 2, 2),
    ]
    assert cases[0].query == "第一个"
    assert cases[0].expected == "simple"
    assert cases[0].history == [
        {"query": "导航去火车站", "route": "simple"},
    ]
    assert cases[1].history == [
        {"query": "导航去火车站", "route": "simple"},
        {"query": "第一个", "route": "simple"},
    ]
    assert cases[2].history == [
        {"query": "找个适合带孩子玩的地方", "route": "complex"},
    ]


def test_summarize_by_turn_reports_independent_turn_accuracy() -> None:
    summary = summarize_by_turn(
        [
            (2, "simple", "simple"),
            (2, "complex", "simple"),
            (3, "simple", "simple"),
        ]
    )

    assert summary[2].total == 2
    assert summary[2].correct == 1
    assert summary[2].accuracy == 0.5
    assert summary[3].total == 1
    assert summary[3].correct == 1
    assert summary[3].accuracy == 1.0


def test_format_result_summary_prints_readable_sections() -> None:
    case_a = MultiturnCase(
        sheet_name="【整合】导航多轮表",
        row_number=2,
        turn_index=2,
        domain="navigation",
        query="第一个",
        expected="simple",
        history=[{"query": "导航去火车站", "route": "simple"}],
    )
    case_b = MultiturnCase(
        sheet_name="【整合】音乐多轮表",
        row_number=3,
        turn_index=3,
        domain="music",
        query="第一首",
        expected="complex",
        history=[{"query": "播放最近很火的歌曲", "route": "complex"}],
    )

    text = format_result_summary(
        [
            MultiturnResult(case=case_a, actual="simple", correct=True, latency_ms=10.0),
            MultiturnResult(case=case_b, actual="simple", correct=False, latency_ms=20.0),
        ]
    )

    assert "Overall" in text
    assert "accuracy" in text
    assert "By Turn" in text
    assert "Q2" in text
    assert "Q3" in text
    assert "False simple" in text
    assert "Latency" in text
    assert "avg_ms" in text
    assert "p95_ms" in text
    assert "Run" in text
    assert "wall_time_s" in text
