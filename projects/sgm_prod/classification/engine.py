from __future__ import annotations

from typing import Any

from projects.sgm_prod.classification.assets import RouterAssets, get_router_assets
from projects.sgm_prod.classification.llm import llm_fallback
from projects.sgm_prod.classification.models import (
    CapabilityCard,
    ParseCandidate,
    RouterDecision,
    RouterTrace,
)
from projects.sgm_prod.classification.normalize import normalize_query
from projects.sgm_prod.classification.parser import parse_simple_candidates


def _base_trace(
    project: str,
    query: str,
    normalized: str,
    rule_version: str,
) -> RouterTrace:
    return RouterTrace(
        project=project,
        query=query,
        normalized_query=normalized,
        rule_version=rule_version,
    )


def _card_for_candidate(
    candidate: ParseCandidate | None,
    assets: RouterAssets,
) -> CapabilityCard | None:
    if candidate is None:
        return None
    return assets.capabilities.get(candidate.capability_id)


def _fallback_intent_card(normalized: str, assets: RouterAssets) -> CapabilityCard | None:
    for card in assets.capabilities.values():
        if card.route_policy != "llm_fallback":
            continue
        if any(marker and marker in normalized for marker in card.intent_markers):
            return card
    return None


def _fallback_trace_step(card: CapabilityCard) -> str:
    if card.executor == "导航":
        return "parser:navigation_open_target_to_llm"
    if card.executor == "媒体":
        return "parser:media_open_target_to_llm"
    return f"parser:{card.id}_to_llm"


def _should_route_to_llm(
    normalized: str,
    best: ParseCandidate | None,
    assets: RouterAssets,
) -> CapabilityCard | None:
    best_card = _card_for_candidate(best, assets)
    if best_card and best_card.route_policy == "llm_fallback":
        return best_card
    fallback_card = _fallback_intent_card(normalized, assets)
    if not fallback_card:
        return None
    if not best or not best.is_complete:
        return fallback_card
    if (
        fallback_card.intent_marker_policy == "override_cross_executor"
        and best_card
        and best_card.executor != fallback_card.executor
    ):
        return fallback_card
    return None


async def arbitrate_simple_complex_decision(
    query: str,
    *,
    project: str = "default",
    history: list[dict[str, Any]] | None = None,
    use_exact_match: bool = True,
    use_llm_fallback: bool = True,
    simple_queries: frozenset[str] | None = None,
    complex_queries: frozenset[str] | None = None,
    llm_prompt: str | None = None,
) -> RouterDecision:
    assets = get_router_assets(project)
    normalized = normalize_query(query)
    trace = _base_trace(assets.project, query, normalized, assets.rule_version)

    effective_simple = simple_queries if simple_queries is not None else assets.simple_queries
    effective_complex = complex_queries if complex_queries is not None else assets.complex_queries
    use_exact = use_exact_match or simple_queries is not None or complex_queries is not None

    if use_exact and normalized in effective_simple:
        trace.decision_path.append("exact_simple:hit")
        return RouterDecision(label="simple", source="exact_simple", trace=trace)
    trace.decision_path.append("exact_simple:not_hit")

    if use_exact and normalized in effective_complex:
        trace.decision_path.append("exact_complex:hit")
        return RouterDecision(label="complex", source="exact_complex", trace=trace)
    trace.decision_path.append("exact_complex:not_hit")

    candidates = parse_simple_candidates(normalized, assets)
    trace.matched_candidates = candidates[:3]
    best = candidates[0] if candidates else None
    best_card = _card_for_candidate(best, assets)
    route_to_llm_card = _should_route_to_llm(normalized, best, assets)
    if (
        best
        and best.is_complete
        and best_card
        and best_card.route_policy == "parser_simple"
        and route_to_llm_card is None
    ):
        trace.decision_path.append("parser:complete")
        return RouterDecision(label="simple", source="parser_simple", trace=trace)

    if route_to_llm_card:
        trace.decision_path.append(_fallback_trace_step(route_to_llm_card))
    elif best and best.risk_flags and best.confidence >= 0.8:
        trace.risk_flags = best.risk_flags
        trace.decision_path.append("parser:partial_with_risk")
        return RouterDecision(label="complex", source="parser_veto", trace=trace)

    if not use_llm_fallback:
        trace.decision_path.append("llm_fallback:disabled")
        return RouterDecision(label="complex", source="default_complex", trace=trace)

    trace.decision_path.append("llm_fallback:start")
    try:
        label = await llm_fallback(
            normalized,
            history=history,
            prompt=llm_prompt or assets.llm_prompts["default"].system_prompt,
        )
    except Exception:
        trace.decision_path.append("llm_fallback:error")
        return RouterDecision(label="complex", source="default_complex", trace=trace)

    trace.decision_path.append(f"llm_fallback:{label}")
    return RouterDecision(
        label=label,
        source="llm_simple" if label == "simple" else "llm_complex",
        trace=trace,
    )
