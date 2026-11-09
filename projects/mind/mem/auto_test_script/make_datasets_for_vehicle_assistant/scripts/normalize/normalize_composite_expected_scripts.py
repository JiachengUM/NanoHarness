#!/usr/bin/env python3
"""Rewrite composite cases' expected_script to match leaf_cases director style:

用户：…
管家：（围绕「标签」…可照着演绎的指令与台词提示…）
（重点：…）

Multi-session / multi-round formats preserve session headers.
Non-dialogue (评测说明、串联要点等) uses full-width parentheses （…）.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


META_TAG_PREFIXES = (
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
META_TAG_EXACT = {
    "可完成",
    "应降级处理",
    "需澄清",
    "应拒绝",
}

ROUND_HEADER_RE = re.compile(r"^第\s*(\d+)\s*轮\s*$")
SESSION_HEADER_RE = re.compile(r"^第[一二三四五六七八九十百千零〇\d]+会话")


def functional_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    for t in tags:
        if t in META_TAG_EXACT:
            continue
        if any(t.startswith(p) for p in META_TAG_PREFIXES):
            continue
        out.append(t)
    return out[:6]


def extract_sessions(case: dict) -> list[list[str]]:
    """Each session -> ordered user utterances."""
    uql = case.get("user_query_lists") or []
    if not uql:
        return []
    if isinstance(uql[0], dict):
        sessions: list[list[str]] = []
        for block in uql:
            lines: list[str] = []
            for msg in block.get("user_query_list") or []:
                if isinstance(msg, dict) and msg.get("role") == "user":
                    c = (msg.get("content") or "").strip()
                    if c:
                        lines.append(c)
            if lines:
                sessions.append(lines)
        return sessions
    rounds: list[str] = []
    for round_msgs in uql:
        if not isinstance(round_msgs, list):
            continue
        for msg in round_msgs:
            if isinstance(msg, dict) and msg.get("role") == "user":
                c = (msg.get("content") or "").strip()
                if c:
                    rounds.append(c)
    return [rounds] if rounds else []


def strip_assistant_prefix(s: str) -> str:
    """Strip redundant「助手」subject but keep modal「不得/须/应…」so nl lines are not inverted."""
    s = s.strip()
    modal_pairs = (
        ("助手不得", "不得"),
        ("助手必须", "必须"),
        ("助手须", "须"),
        ("助手应", "应"),
        ("助手可", "可"),
        ("助手若", "若"),
    )
    for old_prefix, keep in modal_pairs:
        if s.startswith(old_prefix):
            return (keep + s[len(old_prefix) :]).strip().rstrip()
    for p in (
        "第一会话中，",
        "第二会话中，",
        "第三会话中",
        "第四会话中",
        "第五会话中",
        "第六会话中",
        "第一轮",
        "第二轮",
    ):
        if s.startswith(p):
            s = s[len(p) :].lstrip()
            break
    return s.rstrip()


def nl_to_direction(nl: list[str], max_items: int = 4) -> str:
    parts: list[str] = []
    for x in nl[:max_items]:
        parts.append(strip_assistant_prefix(x).rstrip("。"))
    return "；".join(parts)


def parse_old_triple(es: str) -> tuple[str, str, str]:
    """Parse legacy '场景。\\n管家：…\\n重点：…' or variants."""
    lines = [ln.strip() for ln in es.strip().split("\n") if ln.strip()]
    scene = ""
    butler = ""
    focus = ""
    if not lines:
        return scene, butler, focus
    if lines[0].startswith("用户：") or lines[0].startswith("第一"):
        return "", "", ""
    if ROUND_HEADER_RE.match(lines[0]):
        return "", "", ""
    scene = lines[0]
    if len(lines) > 1 and lines[1].startswith("管家："):
        butler = lines[1][len("管家：") :].strip()
    for ln in lines[2:]:
        if "重点" in ln[:6] or ln.startswith("（重点"):
            focus = re.sub(r"^[（]?重点[：:]", "", ln)
            focus = focus.rstrip("）").strip()
            break
    return scene, butler, focus


def partition_nl_by_session(nl: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Rough split for multi-session nl_assertion lines."""
    n1, n2, rest = [], [], []
    for x in nl:
        if "第一会话" in x[:12] or ("第一" in x[:8] and "会话" in x[:12]):
            n1.append(x)
        elif "第二会话" in x[:12] or ("第二" in x[:8] and "会话" in x[:12]):
            n2.append(x)
        elif "第三会话" in x[:12]:
            rest.append(x)
        else:
            rest.append(x)
    return n1, n2, rest


def focus_from_case(case: dict, focus_fallback: str) -> str:
    if focus_fallback:
        return focus_fallback[:200]
    desc = (case.get("case_description") or "").strip()
    if desc:
        seg = desc.split("；")[0].strip()
        if seg:
            return seg[:200]
    return "准确理解语境并完成用户意图，口头反馈可核对"


def strip_auto_eval_banner(es: str) -> tuple[str | None, str]:
    """Extract 【自动评测说明】 body; return (note_or_none, remainder)."""
    marker = "【自动评测说明】"
    if marker not in es:
        return None, es
    i = es.index(marker)
    before = es[:i].rstrip()
    after = es[i + len(marker) :].lstrip()
    lines = after.split("\n")
    note_lines: list[str] = []
    idx = 0
    while idx < len(lines):
        raw = lines[idx]
        s = raw.strip()
        if s == "":
            idx += 1
            if note_lines:
                break
            continue
        if ROUND_HEADER_RE.match(s) or SESSION_HEADER_RE.match(s):
            break
        note_lines.append(raw.rstrip())
        idx += 1
    tail = "\n".join(lines[idx:]).lstrip()
    note = "\n".join(note_lines).strip()
    merged = f"{before}\n{tail}".strip() if before else tail
    return (note if note else None), merged


def strip_normalized_eval_note(es: str) -> tuple[str | None, str]:
    """Remove leading （评测说明：…） block written by this normalizer."""
    es = es.lstrip()
    prefix = "（评测说明："
    if not es.startswith(prefix):
        return None, es
    depth = 0
    for i, ch in enumerate(es):
        if ch == "（":
            depth += 1
        elif ch == "）":
            depth -= 1
            if depth == 0:
                note = es[len(prefix) :i].strip()
                tail = es[i + 1 :].lstrip()
                return note, tail
    return None, es


def strip_eval_note(es: str) -> tuple[str | None, str]:
    """Extract evaluation note from 【自动评测说明】 or normalized （评测说明：…）."""
    note, rest = strip_auto_eval_banner(es)
    if note:
        return note, rest
    return strip_normalized_eval_note(es)


def extract_script_round_users(es: str) -> list[str]:
    """User lines from 「第n轮 + 换行 + 用户：」 blocks, in round order."""
    pairs: list[tuple[int, str]] = []
    for m in re.finditer(r"(?:^|\n)第\s*(\d+)\s*轮\s*\n用户：\s*([^\n]+)", es):
        pairs.append((int(m.group(1)), m.group(2).strip()))
    pairs.sort(key=lambda x: x[0])
    return [t for _, t in pairs]


def prune_duplicate_opening_user(es: str) -> str:
    """Drop leading 用户：… when identical to 第1轮\\n用户：…."""
    es = es.strip()
    m_open = re.match(r"^用户：([^\n]+)\n+", es)
    if not m_open:
        return es
    u1 = m_open.group(1).strip()
    rest = es[m_open.end() :]
    m_round = re.match(r"第\s*1\s*轮\s*\n用户：([^\n]+)", rest.lstrip())
    if not m_round:
        return es
    if m_round.group(1).strip() != u1:
        return es
    return rest.lstrip()


def first_meaningful_script_line(es: str) -> str:
    for ln in es.split("\n"):
        s = ln.strip()
        if s:
            return s
    return ""


def script_is_well_formed(es: str) -> bool:
    """Detect obvious violations: legacy scene-first triple, bare 管家：, auto-eval banner."""
    es = es.strip()
    if not es:
        return True
    if "【自动评测说明】" in es:
        return False
    lines = [ln.rstrip() for ln in es.split("\n")]
    first = first_meaningful_script_line(es)
    if first.startswith("管家：") and not first.startswith("管家：（"):
        return False
    if not (
        first.startswith("用户：")
        or SESSION_HEADER_RE.match(first)
        or ROUND_HEADER_RE.match(first)
    ):
        return False
    for ln in lines:
        t = ln.strip()
        if not t:
            continue
        if t.startswith("管家：") and not t.startswith("管家：（"):
            return False
    return True


def augment_sessions_from_script(sessions: list[list[str]], es: str) -> tuple[list[list[str]], bool]:
    """When cold-start has only round1 but expected_script lists 第n轮 users, merge."""
    rounds = extract_script_round_users(es)
    if len(sessions) != 1 or not sessions[0]:
        return sessions, False
    if len(rounds) <= 1:
        return sessions, False
    cold = sessions[0][0].strip()
    if len(sessions[0]) != 1:
        return sessions, False
    if rounds[0].strip() == cold:
        return [rounds], True
    return [[cold] + rounds], True


def extract_focus_from_paren(es: str) -> str:
    m = re.search(r"（重点：([^）]+)）", es)
    return m.group(1).strip() if m else ""


def compose_expected_script(
    case: dict,
    sessions: list[list[str]],
    es_hint: str,
    focus_source_es: str | None = None,
) -> str:
    """Build director-style script from sessions + legacy hints in es_hint."""
    tags = functional_tags(case.get("tags") or [])
    tag_join = "」「".join(tags) if tags else "综合车控与对话能力"
    nl = case.get("nl_assertion") or []
    fb_src = focus_source_es if focus_source_es is not None else es_hint
    scene, butler_legacy, focus_fb = parse_old_triple(es_hint)
    focus_fb = focus_fb or extract_focus_from_paren(fb_src)
    focus = focus_from_case(case, focus_fb)
    nl_dir = nl_to_direction(nl)

    scene_tip = f"场景提示：{scene.rstrip('。')}。" if scene.strip() else ""
    inner_common = (
        f"围绕标签「{tag_join}」演绎。"
        f"{scene_tip}"
        f"{' 管家动作提示：' + butler_legacy if butler_legacy else ''}"
        f" 台词与行为须体现：{nl_dir}。"
        " 口头汇报执行结果、边界或澄清问题；语气符合车载场景。"
    )

    if not sessions:
        return (
            f"用户：（本场未解析到用户台词，请对照 user_query_lists 手工补全。）\n"
            f"管家：（{inner_common}）\n（重点：{focus}）"
        )

    if len(sessions) > 1:
        labels = ["第一会话", "第二会话", "第三会话", "第四会话", "第五会话", "第六会话", "第七会话"]
        n1, n2, _tail_nl = partition_nl_by_session(nl)
        chunks: list[str] = []
        for si, sess_lines in enumerate(sessions):
            lab = labels[si] if si < len(labels) else f"第{si+1}会话"
            if si == 0 and n1:
                session_hint = nl_to_direction(n1, 4)
            elif si == 1 and n2:
                session_hint = nl_to_direction(n2, 4)
            else:
                session_hint = nl_dir
            if not session_hint:
                session_hint = nl_dir
            for ri, uline in enumerate(sess_lines):
                if len(sess_lines) > 1:
                    chunks.append(f"{lab}·第{ri+1}轮\n用户：{uline}")
                else:
                    chunks.append(f"{lab}\n用户：{uline}")
            chunks.append(
                f"管家：（{lab}：须体现 {session_hint}；"
                f"面向演员可直接据此设计与用户台词对应的应答与动作。）"
            )
        closing = (
            f"（整场串联要点：{scene.rstrip('。') if scene else case.get('case_id', '')}；"
            f"{butler_legacy + '；' if butler_legacy else ''}{nl_dir}）"
        )
        return "\n".join(chunks) + f"\n{closing}"

    rounds = sessions[0]
    if len(rounds) == 1:
        return f"用户：{rounds[0]}\n管家：（{inner_common}）\n（重点：{focus}）"

    parts: list[str] = []
    for i, uline in enumerate(rounds, 1):
        parts.append(f"第{i}轮\n用户：{uline}")
    parts.append(f"管家：（同一会话多轮：{inner_common}）\n（重点：{focus}）")
    return "\n".join(parts)


def build_expected_script(case: dict) -> str:
    es_orig = case.get("expected_script") or ""
    eval_note, es_banner = strip_eval_note(es_orig)
    es_work = prune_duplicate_opening_user(es_banner)

    sessions = extract_sessions(case)
    sessions_aug, augmented = augment_sessions_from_script(sessions, es_work)
    well = script_is_well_formed(es_work)

    if eval_note is None and not augmented and well:
        return es_orig

    body = compose_expected_script(case, sessions_aug, es_work, focus_source_es=es_orig)
    if eval_note:
        return f"（评测说明：{eval_note}）\n\n{body}"
    return body


def main() -> int:
    root = Path(__file__).resolve().parent
    path = root / "vehicle_assistant_leaf_cases.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    composite_only = 0
    for case in data:
        if not str(case.get("id", "")).startswith("composite-"):
            continue
        composite_only += 1
        new_es = build_expected_script(case)
        if new_es != case.get("expected_script"):
            case["expected_script"] = new_es
            changed += 1
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"updated expected_script on {changed} / {composite_only} composite-* cases ({len(data)} cases in file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
