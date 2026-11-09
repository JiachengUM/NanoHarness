from __future__ import annotations

import pytest

from projects.sgm_prod.classification.assets import load_router_assets
from projects.sgm_prod.classification.parser import parse_simple_candidates


def _best(query: str):
    return parse_simple_candidates(query, load_router_assets())[0]


def test_parser_consumes_compound_blind_entity_as_simple() -> None:
    candidate = _best("打开天窗遮阳帘")

    assert candidate.capability_id == "vehicle.blind.set"
    assert candidate.is_complete


def test_parser_leaves_multi_capability_connector_unconsumed() -> None:
    candidate = _best("关闭所有车窗和天窗")

    assert candidate.capability_id == "vehicle.window.set"
    assert candidate.unconsumed_text == "和天窗"
    assert "multi_capability_connector" in candidate.risk_flags


def test_parser_consumes_media_title_that_contains_risk_word() -> None:
    candidate = _best("播放如果可以")

    assert candidate.capability_id == "media.music.search"
    assert candidate.is_complete


def test_parser_consumes_playback_continuation_phrase_as_simple() -> None:
    candidate = _best("继续播放")

    assert candidate.capability_id == "media.playback.continue"
    assert candidate.is_complete


def test_parser_treats_consumed_risk_alias_as_song_title() -> None:
    # "如果可以" 是音乐 card 的 target alias，整段被 span 消费后，
    # conditional_automation 的 "如果" pattern 不应再触发 veto
    candidate = _best("如果可以播放")

    assert candidate.capability_id == "media.music.search"
    assert candidate.is_complete
    assert "conditional_automation" not in candidate.risk_flags


def test_parser_does_not_infer_vehicle_target_from_arbitrary_free_text() -> None:
    candidate = _best("开内循环，风量2档")

    assert not candidate.is_complete


def test_parser_allows_sequential_prefix_for_single_command() -> None:
    candidate = _best("然后打开空调")

    assert candidate.capability_id == "vehicle.temperature.set"
    assert candidate.is_complete


def test_parser_flags_same_capability_parallel_targets_as_complex() -> None:
    # P0：同 capability 多 target 一律 complex
    candidate = _best("关闭车道保持和车道居中")

    assert candidate.capability_id == "vehicle.feature.set"
    assert not candidate.is_complete
    assert "multi_capability_connector" in candidate.risk_flags


def test_parser_does_not_expand_unrelated_lexicon_group_by_alias_overlap() -> None:
    candidates = parse_simple_candidates("打开车道保持", load_router_assets())
    radio_candidate = next(
        candidate
        for candidate in candidates
        if candidate.capability_id == "media.radio.tune"
    )

    assert candidates[0].capability_id == "vehicle.feature.set"
    assert not radio_candidate.is_complete


def test_parser_flags_multi_capability_without_punctuation() -> None:
    candidate = _best("前排座椅通风打开，空调风量调高")

    assert not candidate.is_complete
    assert "multi_capability_connector" in candidate.risk_flags


def test_parser_flags_risk_substring_in_unconsumed_song_title() -> None:
    # "播放如果当时" 里 "如果" 没被任何 target alias 消费，conditional_automation
    # 还是会 veto；这是 substring rule 的已知 false-positive，记录现状
    candidate = _best("播放如果当时")

    assert candidate.capability_id in {"media.music.search", "media.playback.start"}
    assert not candidate.is_complete
    assert "conditional_automation" in candidate.risk_flags


@pytest.mark.parametrize(
    ("query", "capability_id"),
    [
        ("把空调调到23度", "vehicle.temperature.set"),
        ("打开主驾车窗", "vehicle.window.set"),
        ("打开天窗遮阳帘", "vehicle.blind.set"),
        ("我喜欢蓝色", "vehicle.ambient_light.set"),
        ("播放如果可以", "media.music.search"),
        ("继续播放音乐", "media.playback.continue"),
    ],
)
def test_parser_consumes_seed_simple_cases_as_complete(
    query: str,
    capability_id: str,
) -> None:
    candidate = _best(query)

    assert candidate.capability_id == capability_id
    assert candidate.is_complete
