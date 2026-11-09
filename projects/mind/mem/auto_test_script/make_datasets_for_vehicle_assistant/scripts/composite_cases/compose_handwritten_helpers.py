"""Helpers to build composite-style case dicts with less boilerplate (content still authored per call)."""
from __future__ import annotations

from typing import Any

# Tags used only for difficulty / structure — omit from「围绕标签」台词引导（与 normalize_composite_expected_scripts 一致）
_SCRIPT_META_TAGS = {
    "可完成",
    "应降级处理",
    "需澄清",
    "应拒绝",
}
_SCRIPT_META_PREFIXES = (
    "单轮对话",
    "多轮对话",
    "多次多轮",
    "跨轮延续",
    "跨轮",
    "长链路任务",
    "单轮任务",
    "单任务",
    "多轮任务",
)


def director_script(user_line: str, tags: list[str], body: str, focus: str) -> str:
    """Expected_script aligned with vehicle_assistant_leaf_cases.json: 用户 / 管家（…） / 重点."""
    ft = [
        t
        for t in tags
        if t not in _SCRIPT_META_TAGS
        and not any(t.startswith(p) for p in _SCRIPT_META_PREFIXES)
    ]
    tag_str = "」「".join(ft[:6]) if ft else "综合车机助手能力"
    return (
        f"用户：{user_line}\n"
        f"管家：（围绕标签「{tag_str}」：{body}）\n"
        f"（重点：{focus}）"
    )


def ctx(car_info: str) -> dict[str, Any]:
    return {"car_info": car_info}


def rnd(cfg: str, lines: list[list[dict[str, str]]]) -> list[list[dict[str, str]]]:
    """Old-style: list of rounds, each round list of messages."""
    return lines


def sess(
    utter: str,
    mock_car: str,
    mock_time: str,
) -> dict[str, Any]:
    """One dict entry = one automated dialogue session (see DialogueRoundConfig).

    Multiple sess(...) in ``user_query_lists`` ⇒ multiple independent runs (cold start
    is always ``user_query_list[0]`` only). Use separate sessions for distinct times /
    memory persistence tests.

    **Cold-start wording:** later sessions should not read like the immediate next turn
    of the same chat (no「附上」「把我刚才」etc.); each ``utter`` should stand alone or
    anchor on calendar/memory — see vehicle-assistant-composite-cases SKILL.

    For multiple **rounds within the same chat**, use a single block with one cold-start
    user line; put round 2+ user lines in ``expected_script`` for the actor / FakePerson.
    """
    return {
        "user_query_list": [{"role": "user", "content": utter}],
        "mock_info": {"car_info": mock_car},
        "mock_time": mock_time,
    }


def four_session_expected_script(
    tags: list[str],
    quad: list[tuple[str, str, str, str]],
    whole_summary: str,
) -> str:
    """四轮会话 expected_script：「用户：」后仅为口述台词；导演提示写在管家括号内。

    quad[i] = (user_line, mock_car, mock_time, butler_hint)，前三项与 ``sess`` 一致。
    """
    ft = [
        t
        for t in tags
        if t not in _SCRIPT_META_TAGS
        and not any(t.startswith(p) for p in _SCRIPT_META_PREFIXES)
    ]
    tag_str = "」「".join(ft[:8]) if ft else "综合车机助手能力"
    names = ("第一会话", "第二会话", "第三会话", "第四会话")
    parts: list[str] = []
    for i in range(4):
        u, _, _, h = quad[i]
        hdr = names[i]
        if i < 3:
            parts.append(f"{hdr}\n用户：{u}\n管家：（{h}）")
        else:
            parts.append(f"{hdr}\n用户：{u}\n管家：（围绕标签「{tag_str}」：{h}）")
    parts.append(f"（整场串联要点：{whole_summary}）")
    return "\n".join(parts)


def pattern_case(
    idx: int,
    case_id: str,
    ctx_car: str,
    tags: list[str],
    quad: list[tuple[str, str, str, str]],
    nls: list[str],
    desc: str,
    summ: str,
    max_round: int = 16,
) -> dict[str, Any]:
    """Four cold-start sessions + ``four_session_expected_script`` wrapper."""
    uqs = [sess(u, c, m) for u, c, m, _ in quad]
    es = four_session_expected_script(tags, quad, summ)
    return case(idx, case_id, ctx_car, max_round, uqs, es, nls, desc, tags)


def case(
    idx: int,
    case_id: str,
    car_info: str,
    max_round: int,
    user_query_lists: Any,
    expected_script: str,
    nl_assertion: list[str],
    case_description: str,
    tags: list[str],
) -> dict[str, Any]:
    return {
        "id": f"composite-{idx}",
        "case_id": case_id,
        "context_config": ctx(car_info),
        "max_round": max_round,
        "user_query_lists": user_query_lists,
        "expected_script": expected_script,
        "nl_assertion": nl_assertion,
        "case_description": case_description,
        "tags": tags,
    }
