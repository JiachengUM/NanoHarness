from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

import pandas as pd

from projects.sgm_prod.classification.normalize import normalize_query

DEFAULT_DOMAIN = "BENZ"

SimpleSheet = Literal["端侧直接执行", "简单RAG"]
ComplexSheet = Literal[
    "复杂RAG",
    "复杂RAG（副本）",
    "复杂RAG（基准版）",
    "复杂RAG(设计版)",
    "多轮tag规则",
]

SIMPLE_SHEETS: tuple[SimpleSheet, ...] = ("简单RAG",)
COMPLEX_SHEETS: tuple[ComplexSheet, ...] = (
    "复杂RAG",
    "复杂RAG（副本）",
    "复杂RAG（基准版）",
    "复杂RAG(设计版)",
    "多轮tag规则",
)
EXCLUDED_SIMPLE_INTENTS = {"联网搜索", "S2S闲聊"}


@dataclass(frozen=True)
class CaseRow:
    query: str
    label: Literal["simple", "complex"]
    source: str
    domain: str


def _clean_cell(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _first_existing_column(columns: Iterable[object], candidates: tuple[str, ...]) -> str | None:
    names = {str(column).strip(): str(column) for column in columns}
    for candidate in candidates:
        if candidate in names:
            return names[candidate]
    return None


def _metadata(row: pd.Series, candidates: tuple[str, ...]) -> str:
    for column in candidates:
        if column in row.index:
            value = _clean_cell(row[column])
            if value:
                return value
    return ""


def _simple_rows(workbook: pd.ExcelFile) -> list[CaseRow]:
    rows: list[CaseRow] = []
    for sheet_name in SIMPLE_SHEETS:
        if sheet_name not in workbook.sheet_names:
            continue
        data = workbook.parse(sheet_name)
        query_column = _first_existing_column(data.columns, ("query", "Query"))
        if query_column is None:
            continue
        for _, row in data.iterrows():
            intent = _metadata(row, ("input_intent", "意图领域", "domain"))
            if intent in EXCLUDED_SIMPLE_INTENTS:
                continue
            query = _clean_cell(row[query_column])
            if not normalize_query(query):
                continue
            rows.append(
                CaseRow(
                    query=query,
                    label="simple",
                    source=sheet_name,
                    domain=DEFAULT_DOMAIN,
                )
            )
    return rows


def _complex_rows(workbook: pd.ExcelFile) -> list[CaseRow]:
    rows: list[CaseRow] = []
    for sheet_name in COMPLEX_SHEETS:
        if sheet_name not in workbook.sheet_names:
            continue
        data = workbook.parse(sheet_name)
        query_candidates = ("Query2", "query2") if sheet_name == "多轮tag规则" else ("query", "Query")
        query_column = _first_existing_column(data.columns, query_candidates)
        if query_column is None:
            continue
        for _, row in data.iterrows():
            query = _clean_cell(row[query_column])
            if not normalize_query(query):
                continue
            rows.append(
                CaseRow(
                    query=query,
                    label="complex",
                    source=sheet_name,
                    domain=DEFAULT_DOMAIN,
                )
            )
    return rows


def _dedupe_by_normalized_query(rows: list[CaseRow]) -> list[CaseRow]:
    deduped: list[CaseRow] = []
    seen: set[str] = set()
    for row in rows:
        normalized_query = normalize_query(row.query)
        if normalized_query in seen:
            continue
        seen.add(normalized_query)
        deduped.append(row)
    return deduped


def _raise_on_cross_label_conflicts(simple_rows: list[CaseRow], complex_rows: list[CaseRow]) -> None:
    simple_queries = {normalize_query(row.query) for row in simple_rows}
    complex_queries = {normalize_query(row.query) for row in complex_rows}
    conflicts = simple_queries & complex_queries
    if conflicts:
        examples = ", ".join(sorted(conflicts)[:10])
        raise ValueError(f"simple/complex exact query conflicts: {examples}")


def _write_simple_cases(path: Path, rows: list[CaseRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(("query", "label", "source", "domain"))
        for row in rows:
            writer.writerow((row.query, row.label, row.source, row.domain))


def _write_complex_cases(path: Path, rows: list[CaseRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(("query", "label", "source", "domain"))
        for row in rows:
            writer.writerow((row.query, row.label, row.source, row.domain))


def build_assets_from_workbook(workbook_path: Path, output_dir: Path) -> None:
    workbook = pd.ExcelFile(workbook_path)
    simple_rows = _dedupe_by_normalized_query(_simple_rows(workbook))
    complex_rows = _dedupe_by_normalized_query(_complex_rows(workbook))
    _raise_on_cross_label_conflicts(simple_rows, complex_rows)

    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_simple_cases(data_dir / "simple.csv", simple_rows)
    _write_complex_cases(data_dir / "complex.csv", complex_rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build router exact-case CSV assets.")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    build_assets_from_workbook(args.workbook, args.output_dir)


if __name__ == "__main__":
    main()
