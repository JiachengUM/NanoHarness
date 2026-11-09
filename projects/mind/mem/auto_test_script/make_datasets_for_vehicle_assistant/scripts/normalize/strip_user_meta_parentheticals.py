#!/usr/bin/env python3
"""Remove dataset-author parentheticals from user-facing lines (user_query_lists +
 mirrored 「用户：」 lines in expected_script). Real users don't say 「概括即可」等."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# Exact phrases to strip entirely (full-width parentheses unit).
_STRIP_EXACT: tuple[str, ...] = (
    "（概括即可）",
    "（口述即可）",
    "（概括一句）",
    "（概括）",
    "（口述）",
    "（口述策略即可）",
    "（概括假设）",
    "（概括语境）",
    "（概括层面）",
    "（概括风险）",
    "（概括对话复盘）",
    "（概括封路假设）",
    "（概括院区假设）",
    "（概括小区假设）",
    "（概括歌手口述）",
    "（概括坐标假设）",
    "（概括设备粒度假设）",
    "（概括能力边界假设）",
    "（概括政策语境）",
    "（概括若硬件允许）",
    "（推测口述）",
    "（事件口述）",
    "（场景口述）",
    "（粤语混搭口述）",
    "（故意错别字口述）",
    "（网络梗夸张说法）",
    "（夹杂语气词）",
    "（连环追问）",
    "（承接上文）",
    "（补充）",
    "（危险口述）",
    "（模糊指代）",
    "（省略对象）",
    "（用户口误）",
    "（歌手名口述）",
    "（电台名口述）",
    "（专辑名口述即可）",
    "（仅两字提示）",
    "（替儿童转述）",
    "（副驾语音混淆）",
    "（语音突然被打断只剩半截）",
    "（口音很重像「官」又很短）",
    "（连说两遍完全相同）",
    "（三连指令）",
    "（未说明对象）",
    "（未说明是哪一家）",
    "（未指明天窗还是遮阳帘）",
    "（未说明音乐路噪还是施工）",
    "（你给我文本建议就行）。",
    "（你给我文本建议就行）",
    "（概括语境）",
    "（常用地点已设为湖里某小区口述存在）",
)

# Regex: trailing annotational parenthetical (dataset notes / staged prompts).
_END_META_RE = re.compile(
    r"（[^）]{0,120}?(?:概括|口述|假设|复盘|转述|混淆|追问|承接|标注|演练|"
    r"错别字|网络梗|夹杂|故意|打断|未说明|未指明|专辑名|歌手名|电台名|粒度假设|"
    r"边界假设|封路假设|院区假设|小区假设|策略即可|政策语境|硬件允许|"
    r"顺路假设|坐标假设|语境|风险层面|两句提示|三字)[^）]{0,80}?）\s*$"
)


def clean_user_visible_line(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return s
    # Repeatedly peel exact suffix chunks (longest first)
    changed = True
    while changed:
        changed = False
        for frag in sorted(_STRIP_EXACT, key=len, reverse=True):
            if s.endswith(frag):
                s = s[: -len(frag)].rstrip()
                changed = True
                break
        if changed:
            continue
        m = _END_META_RE.search(s)
        if m and m.start() > 0:
            inner = m.group(0)
            # Don't strip plausible location hints: short proper-name-like only
            if len(inner) <= 15 and re.match(r"^（[\u4e00-\u9fff]{2,8}）$", inner):
                break
            s = s[: m.start()].rstrip()
            changed = True
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def clean_expected_script_users(es: str) -> str:
    if not es:
        return es
    out_lines = []
    for line in es.split("\n"):
        if "用户：" in line:
            idx = line.index("用户：")
            prefix = line[: idx + len("用户：")]
            rest = line[idx + len("用户：") :]
            out_lines.append(prefix + clean_user_visible_line(rest))
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def main() -> int:
    root = Path(__file__).resolve().parent
    path = root / "vehicle_assistant_leaf_cases.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    n_user = 0
    n_es = 0
    for case in data:
        touched = False
        for b in case.get("user_query_lists") or []:
            msgs = b.get("user_query_list") if isinstance(b, dict) else b
            for m in msgs or []:
                if m.get("role") != "user":
                    continue
                old = m.get("content") or ""
                new = clean_user_visible_line(old)
                if new != old:
                    m["content"] = new
                    n_user += 1
                    touched = True
        es = case.get("expected_script") or ""
        new_es = clean_expected_script_users(es)
        if new_es != es:
            case["expected_script"] = new_es
            n_es += 1
            touched = True
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"cleaned user_query_list user messages: {n_user}")
    print(f"updated expected_script (user lines): {n_es} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
