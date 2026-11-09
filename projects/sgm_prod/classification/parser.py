"""规则解析层：把 query 降解到一张可执行能力卡上。

本模块不直接给 simple/complex 最终结论，而是为每张高精度白名单能力卡
产出 ParseCandidate。后续 engine 会根据缺槽、残留文本、风险标记和置信度做仲裁。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from projects.sgm_prod.classification.assets import RouterAssets
from projects.sgm_prod.classification.models import ParseCandidate
from projects.sgm_prod.classification.normalize import normalize_query


@dataclass(frozen=True)
class _Span:
    start: int
    end: int
    text: str
    slot: str


def _alias_identity(alias: str, slot: str, assets: RouterAssets) -> str:
    """返回用于去重的槽位身份。

    大多数 lexicon target 可以折叠到 canonical；但少数 canonical 只是维护分组，
    例如“灯光/车窗/座椅舒适”。这类分组不能吞掉真实 surface，否则多 target 会被误判成单意图。
    """
    for entry in assets.lexicon:
        if entry.slot != slot:
            continue
        if entry.canonical == alias or alias in entry.aliases:
            if (
                slot == "target"
                and entry.canonical in set(assets.parser_rules.broad_target_canonicals)
            ):
                return alias
            return entry.canonical
    return alias


def _expand_aliases(slot: str, allowed_values: list[str], assets: RouterAssets) -> list[str]:
    aliases: set[str] = set()
    allowed = {value for value in allowed_values if value}
    for value in allowed:
        aliases.add(value)
    for entry in assets.lexicon:
        if entry.slot != slot:
            continue
        if entry.canonical in allowed:
            aliases.update({entry.canonical, *entry.aliases})
    return sorted(aliases, key=lambda item: (-len(item), item))


def _find_spans(query: str, aliases: list[str], slot: str) -> list[_Span]:
    spans: list[_Span] = []
    for alias in aliases:
        start = query.find(alias)
        while start >= 0:
            spans.append(_Span(start, start + len(alias), alias, slot))
            start = query.find(alias, start + 1)
    return sorted(spans, key=lambda item: (-len(item.text), item.start, item.text))


def _overlaps(span: _Span, consumed: list[_Span]) -> bool:
    return any(span.start < item.end and item.start < span.end for item in consumed)


def _consume_slot(
    query: str,
    aliases: list[str],
    slot: str,
    consumed: list[_Span],
) -> bool:
    for span in _find_spans(query, aliases, slot):
        if not _overlaps(span, consumed):
            consumed.append(span)
            return True
    return False


def _consume_all_target_spans(
    query: str,
    aliases: list[str],
    consumed: list[_Span],
) -> int:
    """消费同一卡片内所有不重叠 target，用于后续识别单卡多对象。"""
    count = 0
    for span in _find_spans(query, aliases, "target"):
        if not _overlaps(span, consumed):
            consumed.append(span)
            count += 1
    return count


@lru_cache(maxsize=64)
def _compile_patterns(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pat) for pat in patterns)


def _consume_value_patterns(
    query: str,
    patterns: list[str],
    consumed: list[_Span],
) -> int:
    """按卡片声明的正则签名消费长尾 value，如温度、颜色、档位、百分比。"""
    if not patterns:
        return 0
    count = 0
    for regex in _compile_patterns(tuple(patterns)):
        for match in regex.finditer(query):
            span = _Span(match.start(), match.end(), match.group(), "value")
            if not _overlaps(span, consumed):
                consumed.append(span)
                count += 1
    return count


def _is_slot_covered_inside_consumed_slot(
    aliases: list[str],
    containing_slot: str,
    consumed: list[_Span],
) -> bool:
    return any(
        span.slot == containing_slot
        and any(alias and alias in span.text for alias in aliases)
        for span in consumed
    )


def _consumed_intervals(consumed: list[_Span]) -> list[tuple[int, int]]:
    return [(span.start, span.end) for span in consumed]


def _pattern_fully_consumed(
    query: str,
    pattern: str,
    intervals: list[tuple[int, int]],
) -> bool:
    pos = query.find(pattern)
    while pos >= 0:
        end = pos + len(pattern)
        if not any(start <= pos and end <= stop for start, stop in intervals):
            return False
        pos = query.find(pattern, pos + 1)
    return True


def _global_veto_risks(
    query: str,
    consumed: list[_Span],
    assets: RouterAssets,
) -> list[str]:
    intervals = _consumed_intervals(consumed)
    flags: list[str] = []
    for rule in assets.risks:
        # weak 只作为“可能多意图”的辅助信号；硬拦截只看 strong/global 风险。
        if rule.severity == "weak":
            continue
        for pattern in rule.patterns:
            if not pattern or pattern not in query:
                continue
            if _pattern_fully_consumed(query, pattern, intervals):
                continue
            flags.append(rule.risk_id)
            break
    return flags


def _intent_markers_by_severity(
    assets: RouterAssets, severity: str
) -> tuple[str, ...]:
    markers: list[str] = []
    for rule in assets.risks:
        if rule.severity != severity:
            continue
        if rule.risk_id not in {"multi_capability_connector", "intent_weak_connector"}:
            continue
        markers.extend(p for p in rule.patterns if p)
    return tuple(markers)


def _strong_intent_markers(assets: RouterAssets) -> tuple[str, ...]:
    return _intent_markers_by_severity(assets, "strong")


def _weak_intent_markers(assets: RouterAssets) -> tuple[str, ...]:
    return _intent_markers_by_severity(assets, "weak")


def _all_intent_markers(assets: RouterAssets) -> tuple[str, ...]:
    return _strong_intent_markers(assets) + _weak_intent_markers(assets)


def _count_value_tokens(text: str, consumed: list[_Span], assets: RouterAssets) -> int:
    intervals = _consumed_intervals(consumed)
    count = 0
    for regex in _compile_patterns(tuple(assets.parser_rules.generic_value_patterns)):
        for match in regex.finditer(text):
            if any(start <= match.start() and match.end() <= stop for start, stop in intervals):
                continue
            count += 1
    return count


def _scope_markers_from_assets(assets: RouterAssets) -> list[str]:
    aliases: set[str] = set()
    for entry in assets.lexicon:
        if entry.slot != "scope":
            continue
        aliases.add(entry.canonical)
        aliases.update(entry.aliases)
    return sorted(aliases, key=lambda item: (-len(item), item))


def _count_scope_markers(text: str, consumed: list[_Span], assets: RouterAssets) -> int:
    intervals = _consumed_intervals(consumed)
    sorted_markers = _scope_markers_from_assets(assets)
    found: list[tuple[int, int]] = []
    for marker in sorted_markers:
        pos = text.find(marker)
        while pos >= 0:
            end = pos + len(marker)
            inside_consumed = any(start <= pos and end <= stop for start, stop in intervals)
            overlaps_found = any(pos < stop and start < end for start, stop in found)
            if not inside_consumed and not overlaps_found:
                found.append((pos, end))
            pos = text.find(marker, pos + 1)
    return len(found)


def _known_target_aliases(assets: RouterAssets) -> list[str]:
    aliases: set[str] = set()
    for card in assets.capabilities.values():
        aliases.update(card.targets)
    for entry in assets.lexicon:
        if entry.slot == "target":
            aliases.add(entry.canonical)
            aliases.update(entry.aliases)
    return sorted(
        {alias for alias in aliases if len(alias) >= 2},
        key=lambda item: (-len(item), item),
    )


def _has_alias(text: str, aliases: list[str]) -> bool:
    return any(alias and alias in text for alias in aliases)


def _action_aliases(assets: RouterAssets) -> list[str]:
    aliases: set[str] = set()
    for card in assets.capabilities.values():
        aliases.update(card.actions)
    for entry in assets.lexicon:
        if entry.slot == "action":
            aliases.add(entry.canonical)
            aliases.update(entry.aliases)
    return sorted(
        {alias for alias in aliases if len(alias) >= 2},
        key=lambda item: (-len(item), item),
    )


def _has_extra_capability_mention(
    text: str,
    target_aliases: list[str],
    current_aliases: set[str],
) -> bool:
    return any(
        alias not in current_aliases and alias in text
        for alias in target_aliases
    )


def _has_same_capability_action_and_target(
    text: str,
    action_aliases: list[str],
    target_aliases: list[str],
) -> bool:
    return _has_alias(text, action_aliases) and _has_alias(text, target_aliases)


def _has_multi_intent_connector(text: str, assets: RouterAssets) -> bool:
    return any(marker in text for marker in _all_intent_markers(assets))


def _has_strong_intent_marker(text: str, assets: RouterAssets) -> bool:
    return any(marker in text for marker in _strong_intent_markers(assets))


def _has_unconsumed_marker(
    text: str,
    markers: tuple[str, ...],
    consumed: list[_Span],
) -> bool:
    intervals = _consumed_intervals(consumed)
    return any(
        marker in text and not _pattern_fully_consumed(text, marker, intervals)
        for marker in markers
    )


def _has_question_or_condition(
    text: str,
    consumed: list[_Span],
    assets: RouterAssets,
) -> bool:
    markers = (
        *assets.parser_rules.question_or_condition_markers,
        *assets.parser_rules.conditional_markers,
    )
    return _has_unconsumed_marker(
        text,
        tuple(markers),
        consumed,
    )


def _has_conditional_marker(
    text: str,
    consumed: list[_Span],
    assets: RouterAssets,
) -> bool:
    return _has_unconsumed_marker(
        text,
        tuple(assets.parser_rules.conditional_markers),
        consumed,
    )


def _unconsumed_text(query: str, consumed: list[_Span]) -> str:
    if not consumed:
        return query
    chars = list(query)
    for span in consumed:
        for idx in range(span.start, span.end):
            chars[idx] = ""
    return "".join(chars)


def _cleanup_unconsumed_text(unconsumed: str, assets: RouterAssets) -> str:
    cleaned = unconsumed
    for filler in assets.parser_rules.harmless_fillers:
        cleaned = cleaned.replace(filler, "")
    return cleaned


def _is_residue_negligible(text: str, assets: RouterAssets) -> bool:
    cleaned = _cleanup_unconsumed_text(text, assets)
    for marker in _all_intent_markers(assets):
        cleaned = cleaned.replace(marker, "")
    return not cleaned.strip()


def _sort_key(candidate: ParseCandidate) -> tuple[float, int, int, int, int, str]:
    return (
        -candidate.confidence,
        len(candidate.missing_slots),
        len(candidate.unconsumed_text),
        len(candidate.risk_flags),
        -len(candidate.covered_text),
        candidate.capability_id,
    )


def parse_simple_candidates(query: str, assets: RouterAssets) -> list[ParseCandidate]:
    """按能力卡生成候选解析结果。

    主流程：
    1. 归一化 query，并准备全局 action/target 词表，用于识别“当前卡片之外”的能力痕迹。
    2. 逐张遍历非 exact_match 能力卡，只消费该卡显式声明的 action、target、value。
    3. 基于已消费 span 计算残留文本；残留越多，越可能是缺槽、修饰语或多意图。
    4. 运行全局风险：未被槽位消费掉的风险词会进入 risk_flags。
    5. 用 target/value/scope 数量、连接词和残留动作判断多意图；再按卡片策略处理开放 target 和安全修饰语。
    6. 输出带 trace 的 ParseCandidate；最终 simple/complex 判定由 engine 完成。
    """
    normalized = normalize_query(query)
    candidates: list[ParseCandidate] = []
    all_action_aliases = _action_aliases(assets)
    all_target_aliases = _known_target_aliases(assets)

    for card in assets.capabilities.values():
        if card.executor == "exact_match":
            continue

        consumed: list[_Span] = []
        missing_slots: list[str] = []

        action_aliases = _expand_aliases("action", card.actions, assets)
        target_aliases = _expand_aliases("target", card.targets, assets)
        value_aliases = sorted(set(card.values.literals), key=lambda v: (-len(v), v))

        # 第一段：槽位消费。parser 只消费当前能力卡授权的词，避免一个宽泛别名把别的能力也吃掉。
        has_action = _consume_slot(normalized, action_aliases, "action", consumed)
        target_spans_count = _consume_all_target_spans(normalized, target_aliases, consumed)
        has_target = target_spans_count > 0
        _consume_slot(normalized, value_aliases, "value", consumed)
        _consume_value_patterns(normalized, card.values.patterns, consumed)
        if not has_target:
            has_target = _is_slot_covered_inside_consumed_slot(
                target_aliases,
                "action",
                consumed,
            )
        has_value = any(span.slot == "value" for span in consumed)
        if "action" in card.required_slots and not has_action:
            missing_slots.append("action")
        if "target" in card.required_slots and not has_target and not has_value:
            missing_slots.append("target")

        raw_unconsumed = _unconsumed_text(normalized, consumed)
        unconsumed = _cleanup_unconsumed_text(raw_unconsumed, assets)

        risk_flags = _global_veto_risks(normalized, consumed, assets)

        # 第二段：多意图探测。target/value/scope 是最稳定的结构化信号；
        # 连接词单独出现不一定复杂，但连接词叠加额外对象/取值时风险会明显升高。
        target_spans = [span for span in consumed if span.slot == "target"]
        distinct_target_count = len(
            {_alias_identity(span.text, "target", assets) for span in target_spans}
        )
        consumed_value_texts = {span.text for span in consumed if span.slot == "value"}
        extra_value_aliases_in_raw = sum(
            1 for v in value_aliases
            if v and v in raw_unconsumed and v not in consumed_value_texts
        )
        value_signal_count = (
            len(consumed_value_texts)
            + extra_value_aliases_in_raw
            + _count_value_tokens(normalized, consumed, assets)
        )
        scope_marker_count = _count_scope_markers(normalized, consumed, assets)
        extra_value_signal_count = (
            extra_value_aliases_in_raw + _count_value_tokens(normalized, consumed, assets)
        )
        has_separator = _has_multi_intent_connector(normalized, assets)
        if distinct_target_count >= 2 or (
            has_separator
            and (
                value_signal_count >= 2
                or scope_marker_count >= 2
                or (extra_value_signal_count >= 1 and distinct_target_count >= 1)
            )
        ):
            if "multi_capability_connector" not in risk_flags:
                risk_flags.append("multi_capability_connector")

        # 第三段：场景化辅助词。它们只能在完整命中当前卡片时解释残留，
        # 防止“车里有异味，开外循环”被误判成开放闲聊或情绪风险。
        aux_targets = set(assets.parser_rules.scenario_capability_aux.get(card.id, []))
        current_aliases = {
            alias
            for alias in [*action_aliases, *target_aliases, *value_aliases]
            if alias
        }
        known_for_extra = current_aliases | set(aux_targets)
        has_extra_capability = _has_extra_capability_mention(
            raw_unconsumed,
            all_target_aliases,
            known_for_extra,
        )
        aux_hit_in_residue = any(token in raw_unconsumed for token in aux_targets)
        if aux_targets and has_action and has_target and aux_hit_in_residue:
            risk_flags = [
                flag
                for flag in risk_flags
                if flag not in set(assets.parser_rules.scenario_friendly_risks)
            ]

        # 疑问/条件句不是直接执行证明。对控制类能力，"开了吗/要不要/如果...的话"
        # 这类话语应走复杂链路；纯天气查询保留，但天气词后面夹带车控对象时也 veto。
        has_question_or_condition = _has_question_or_condition(normalized, consumed, assets)
        has_conditional_marker = _has_conditional_marker(normalized, consumed, assets)
        if consumed and has_question_or_condition:
            should_veto_question = False
            if has_conditional_marker:
                should_veto_question = True
            elif card.id == "open_domain.weather.query":
                should_veto_question = has_extra_capability or _has_alias(
                    raw_unconsumed,
                    all_action_aliases,
                )
            elif card.id in set(assets.parser_rules.query_like_capabilities):
                should_veto_question = not _is_residue_negligible(
                    raw_unconsumed,
                    assets,
                )
            else:
                should_veto_question = True
            if should_veto_question and "question_or_condition" not in risk_flags:
                risk_flags.append("question_or_condition")

        # 第四段：残留动作判断。重复口吃可以豁免；真正的“又做一次同卡动作”
        # 或“残留里出现别的能力对象”会被标记为多意图。
        consumed_texts = {span.text for span in consumed}
        stutter_stripped = raw_unconsumed
        for txt in consumed_texts:
            stutter_stripped = stutter_stripped.replace(txt, "")
        stutter_only = _is_residue_negligible(stutter_stripped, assets)
        has_same_capability_extra_command = (
            not stutter_only
            and _has_same_capability_action_and_target(raw_unconsumed, action_aliases, target_aliases)
        )
        if consumed and raw_unconsumed and (
            (
                (
                    _has_multi_intent_connector(raw_unconsumed, assets)
                    or _has_alias(raw_unconsumed, all_action_aliases)
                )
                and has_extra_capability
            )
            or has_same_capability_extra_command
        ):
            if "multi_capability_connector" not in risk_flags:
                risk_flags.append("multi_capability_connector")

        # 第五段：卡片策略。open_after_action 支持“打开某个未枚举对象”；
        # safe_modifier 支持“调亮一点/开大一点”这类不影响执行边界的残留。
        open_target_eligible = (
            card.target_policy == "open_after_action"
            and has_action
            and "target" in card.required_slots
            and not has_target
            and raw_unconsumed
            and not risk_flags
            and not has_extra_capability
            and not has_same_capability_extra_command
            and not _has_multi_intent_connector(raw_unconsumed, assets)
            and distinct_target_count == 0
            and value_signal_count < 2
            and scope_marker_count < 2
        )
        if open_target_eligible:
            has_target = True
            if "target" in missing_slots:
                missing_slots.remove("target")
            unconsumed = ""

        weak_with_extra = (
            _has_multi_intent_connector(raw_unconsumed, assets) and has_extra_capability
        )
        residue_is_safe = (
            not has_same_capability_extra_command
            and not _has_strong_intent_marker(raw_unconsumed, assets)
            and not weak_with_extra
        )
        if (
            card.residue_policy == "safe_modifier"
            and has_action
            and not missing_slots
            and not risk_flags
            and residue_is_safe
        ):
            unconsumed = ""
        if (
            card.residue_policy == "safe_modifier"
            and "action" not in card.required_slots
            and has_target
            and not missing_slots
            and not risk_flags
            and residue_is_safe
        ):
            unconsumed = ""
        confidence = 1.0
        if missing_slots:
            confidence -= 0.4
        if unconsumed:
            confidence -= 0.2
        if risk_flags:
            confidence -= 0.2

        candidates.append(
            ParseCandidate(
                capability_id=card.id,
                covered_text="".join(
                    span.text for span in sorted(consumed, key=lambda item: item.start)
                ),
                unconsumed_text=unconsumed,
                missing_slots=missing_slots,
                risk_flags=risk_flags,
                confidence=max(confidence, 0.0),
            )
        )

    return sorted(candidates, key=_sort_key)
