from __future__ import annotations

"""Audit router capability assets for maintainability, not runtime accuracy.

This module is a review aid for humans and coding agents who maintain the
simple/complex router whitelist. It scans the capability YAML files and reports
places where future rule edits are likely to become ambiguous:

- P0: blocking asset defects, such as duplicate capability IDs or duplicate
  lexicon keys. These must be fixed before trusting the assets.
- P1: review-required boundary risks, such as broad targets, one-character
  targets, cross-executor action/target overlap, or risk words consumed by a
  capability. These are not automatically wrong, but they deserve human review.
- P2: informational overlap, usually within one executor. These often reflect
  valid neighboring abilities, but they are useful clues when investigating a
  false positive or deciding whether to add a new capability card.

The audit output is deliberately separate from accuracy evaluation. Use
evaluate_router_rules.py for rule-only coverage and classification metrics.
Use this audit to decide whether the whitelist remains readable and safe to
extend.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


BROAD_TOKENS = {"系统", "模式", "设置", "屏幕", "车机", "功能", "自动", "页面", "应用"}


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} 必须包含 YAML 映射")
    return data


def _capability_items(asset_dir: Path) -> list[dict[str, Any]]:
    capability_dir = asset_dir / "capabilities"
    if not capability_dir.is_dir():
        raise ValueError(f"{capability_dir} 必须是能力 YAML 目录")

    cards: list[dict[str, Any]] = []
    for path in sorted(capability_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        data = _read_yaml(path)
        executor = str(data.get("executor", "")).strip()
        for card in data.get("capabilities", []):
            if not isinstance(card, dict):
                raise ValueError(f"{path} 中的 capability 必须是 YAML 映射")
            cards.append({**card, "executor": executor, "_file": path.name})
    return cards


def _read_optional_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_yaml(path)


def _items(
    asset_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    capabilities = _capability_items(asset_dir)
    rules_dir = asset_dir / "rules"
    lexicon = _read_yaml(rules_dir / "lexicon.yaml").get("entries", [])
    risks = _read_yaml(rules_dir / "global_risks.yaml").get("risks", [])
    parser_rules = _read_optional_yaml(rules_dir / "parser_rules.yaml")
    return capabilities, lexicon, risks, parser_rules


def _as_set(card: dict[str, Any], key: str) -> set[str]:
    return {str(item) for item in card.get(key, []) if str(item)}


def _value_literals(card: dict[str, Any]) -> set[str]:
    values = card.get("values", {})
    if not isinstance(values, dict):
        return set()
    return {str(item) for item in values.get("literals", []) if str(item)}


def _emit(rows: list[dict[str, str]], severity: str, check: str, item: str, detail: str) -> None:
    rows.append({"severity": severity, "check": check, "item": item, "detail": detail})


def audit(asset_dir: Path) -> list[dict[str, str]]:
    cards, lexicon, risks, parser_rules = _items(asset_dir)
    rows: list[dict[str, str]] = []

    # P0: structural identity checks. Duplicate IDs or lexicon keys make traces
    # and later card edits ambiguous, so they block maintenance.
    ids: defaultdict[str, list[str]] = defaultdict(list)
    for card in cards:
        ids[str(card.get("id", ""))].append(str(card.get("name", "")))
    for capability_id, names in ids.items():
        if not capability_id:
            _emit(rows, "P0", "capability_id", "<empty>", "capability id 为空")
        if len(names) > 1:
            _emit(rows, "P0", "capability_id", capability_id, f"重复名称={names}")

    lex_keys: defaultdict[tuple[str, str], int] = defaultdict(int)
    for entry in lexicon:
        lex_keys[(str(entry.get("slot", "")), str(entry.get("canonical", "")))] += 1
    for (slot, canonical), count in lex_keys.items():
        if count > 1:
            _emit(rows, "P0", "lexicon", f"{slot}/{canonical}", f"重复数量={count}")

    # P1: overly broad or overly short targets. They may be valid dataset
    # shortcuts, but they make new rules harder to reason about and can swallow
    # unrelated queries.
    for card in cards:
        cid = str(card.get("id", ""))
        route_policy = str(card.get("route_policy", "parser_simple"))
        if route_policy not in {"parser_simple", "llm_fallback"}:
            _emit(rows, "P0", "route_policy非法", cid, f"route_policy={route_policy}")
        intent_marker_policy = str(card.get("intent_marker_policy", "when_unresolved"))
        if intent_marker_policy not in {"when_unresolved", "override_cross_executor"}:
            _emit(
                rows,
                "P0",
                "intent_marker_policy非法",
                cid,
                f"intent_marker_policy={intent_marker_policy}",
            )
        if card.get("intent_markers") and route_policy != "llm_fallback":
            _emit(rows, "P2", "intent_markers未生效", cid, "只有 llm_fallback card 会使用 intent_markers")
        for target in sorted(_as_set(card, "targets")):
            if target in BROAD_TOKENS:
                _emit(rows, "P1", "宽泛target", cid, f"宽泛target={target}")
            if len(target) == 1 and not target.isascii():
                _emit(rows, "P1", "过短target", cid, f"单字target={target}")

    # Boundary overlap checks. Cross-executor action+target overlap is P1
    # because different tools may compete for the same query. Same-executor
    # overlap is P2 because neighboring cards often share nouns such as
    # "音乐" or "电话", but the overlap is still useful during错例排查.
    for i, left in enumerate(cards):
        for right in cards[i + 1 :]:
            left_id = str(left.get("id", ""))
            right_id = str(right.get("id", ""))
            target_overlap = _as_set(left, "targets") & _as_set(right, "targets")
            action_overlap = _as_set(left, "actions") & _as_set(right, "actions")
            if target_overlap and action_overlap:
                severity = "P1" if left.get("executor") != right.get("executor") else "P2"
                detail = (
                    f"targets={sorted(target_overlap)[:12]} "
                    f"actions={sorted(action_overlap)[:12]}"
                )
                _emit(rows, severity, "target_action重叠", f"{left_id} <-> {right_id}", detail)
            elif target_overlap:
                _emit(
                    rows,
                    "P2",
                    "target重叠",
                    f"{left_id} <-> {right_id}",
                    f"targets={sorted(target_overlap)[:12]}",
                )

    # P1: risk words consumed by capability cards. If a risk pattern is also a
    # target/action/value, the parser may hide a signal that was meant to
    # upgrade a query to complex.
    risk_patterns = {
        str(pattern)
        for risk in risks
        for pattern in risk.get("patterns", [])
        if str(pattern)
    }
    for card in cards:
        cid = str(card.get("id", ""))
        card_terms = _as_set(card, "targets") | _as_set(card, "actions") | _value_literals(card)
        overlap = sorted(risk_patterns & card_terms)
        if overlap:
            _emit(rows, "P1", "风险pattern被消费", cid, f"risk_patterns={overlap[:12]}")

    # Parser rules are config too. Stale capability/risk references make trace
    # behavior surprising even if YAML can still be read.
    card_ids = {str(card.get("id", "")) for card in cards if str(card.get("id", ""))}
    risk_ids = {str(risk.get("risk_id", "")) for risk in risks if str(risk.get("risk_id", ""))}
    target_canonicals = {
        str(entry.get("canonical", ""))
        for entry in lexicon
        if str(entry.get("slot", "")) == "target" and str(entry.get("canonical", ""))
    }

    for legacy_key in (
        "navigation_hard_control_capabilities",
        "navigation_intent_markers",
        "media_hard_control_capabilities",
        "media_open_intent_markers",
    ):
        if legacy_key in parser_rules:
            _emit(
                rows,
                "P1",
                "parser_rules旧engine配置",
                legacy_key,
                "请迁移到 capability card 的 route_policy/intent_markers",
            )

    for capability_id in parser_rules.get("query_like_capabilities", []) or []:
        if str(capability_id) not in card_ids:
            _emit(rows, "P1", "parser_query_like未知能力", str(capability_id), "capability 不存在")

    scenario_aux = parser_rules.get("scenario_capability_aux", {}) or {}
    if isinstance(scenario_aux, dict):
        for capability_id in scenario_aux:
            if str(capability_id) not in card_ids:
                _emit(rows, "P1", "parser_aux未知能力", str(capability_id), "capability 不存在")

    for risk_id in parser_rules.get("scenario_friendly_risks", []) or []:
        if str(risk_id) not in risk_ids:
            _emit(rows, "P1", "parser_aux未知风险", str(risk_id), "risk_id 不存在")

    for canonical in parser_rules.get("broad_target_canonicals", []) or []:
        if str(canonical) not in target_canonicals:
            _emit(rows, "P2", "parser宽泛canonical未入词表", str(canonical), "target canonical 不存在")

    return rows


def write_report(rows: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["severity", "check", "item", "detail"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="审计路由器能力白名单边界。")
    parser.add_argument(
        "--asset-dir",
        type=Path,
        default=Path("projects/sgm_prod/classification/assets/default"),
        help="需要审计的 router 资产目录。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("projects/sgm_prod/classification/reports/card_audit_latest.csv"),
        help="审计 CSV 输出路径。",
    )
    args = parser.parse_args()

    rows = audit(args.asset_dir)
    write_report(rows, args.output)
    counts: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["severity"]] += 1
    print(f"审计发现数量: {len(rows)}")
    for severity in ("P0", "P1", "P2"):
        print(f"{severity}: {counts[severity]}")
    print(f"审计CSV: {args.output}")


if __name__ == "__main__":
    main()
