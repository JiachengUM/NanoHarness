#!/usr/bin/env python3
"""
清理 vehicle_assistant_cases.json 中 expected_script 前导段里残留的旧版重试说明。

策略：
1. 标准 preamble 已在 expected_script 开头，形如 "管家可能耳背..."。
2. 检查 preamble 之后、第一个 "用户：" 之前的"前导段"中，是否还含有重复的重试说明
   （特征：含 "重试" + "你好，你好奔驰" 或 "你好奔驰" 或 "最多重试3次" 等关键词）。
3. 若是整段都是重复的重试说明（以 "（测试执行说明" / "（导演说明" 开头并整段都在讲重试），
   则整段删除；若该段还含有 case 特定的非重试说明（如泄题约束等），仅删除重试相关句子。
4. 保留 expected_script 开头的新版先导和正文（"用户：..."起）。
"""
import json
import re
from pathlib import Path

CASES_FILE = Path(__file__).resolve().parents[2] / "artifacts" / "projects" / "benz_project" / "cases" / "vehicle_assistant_cases.json"

NEW_PREAMBLE = "管家可能耳背，有时听不到导致没能回复你，那么你扮演用户时如果发现管家没说话的话，你可以重试最多3次，每次重试时都需要在指令前加上固定的唤醒词“你好奔驰”，且你可以把除了唤醒词之外的内容换各种同义说法重试。"

# 识别"重试说明"句子的关键词组合
RETRY_SENTENCE_PATTERNS = [
    r"若[^。]*?重试[^。]*?你好，你好奔驰[^。]*?。",
    r"若[^。]*?重试[^。]*?你好奔驰[^。]*?。",
    r"可最多重试3次[^。]*?你好，你好奔驰[^。]*?。",
    r"可最多重试3次[^。]*?你好奔驰[^。]*?。",
    r"重试时需[^。]*?你好，你好奔驰[^。]*?。",
    r"重试时需[^。]*?你好奔驰[^。]*?。",
    r"需[^。]*?加唤醒词[^。]*?你好，你好奔驰[^。]*?。",
    r"需[^。]*?加唤醒词[^。]*?你好奔驰[^。]*?。",
    r"重试[^。]*?需加[^。]*?你好，你好奔驰[^。]*?。",
    r"重试[^。]*?需加[^。]*?你好奔驰[^。]*?。",
    r"需在[^。]*?加唤醒词[^。]*?你好，你好奔驰[^。]*?。",
    r"需在[^。]*?加唤醒词[^。]*?你好奔驰[^。]*?。",
    r"重试时需在[^。]*?你好，你好奔驰[^。]*?。",
    r"重试时需在[^。]*?你好奔驰[^。]*?。",
    r"重试前需加唤醒词[^。]*?你好，你好奔驰[^。]*?。",
    r"重试前需加唤醒词[^。]*?你好奔驰[^。]*?。",
    r"需在内容前加唤醒词[^。]*?你好，你好奔驰[^。]*?。",
    r"需在内容前加唤醒词[^。]*?你好奔驰[^。]*?。",
    r"需在指令前加唤醒词[^。]*?你好，你好奔驰[^。]*?。",
    r"需在指令前加唤醒词[^。]*?你好奔驰[^。]*?。",
    r"重试时需在指令前加[^。]*?你好，你好奔驰[^。]*?。",
    r"重试时需在指令前加[^。]*?你好奔驰[^。]*?。",
]
RETRY_REGEX = re.compile("|".join(RETRY_SENTENCE_PATTERNS))

# 整段都是重试说明的标志（以这些开头，且段落核心是重试）
PURE_RETRY_PARENS_PREFIXES = [
    "（测试执行说明",
    "（导演说明",
]

def clean_expected_script(es: str) -> tuple[str, list[str]]:
    """清理 expected_script，返回 (新内容, 变更说明列表)"""
    changes = []
    if not es.startswith(NEW_PREAMBLE):
        # 开头不是标准先导，交给外层处理
        return es, changes

    # 拆分：preamble + "\n\n" + 前导段(可选) + "\n\n" + 正文(从"用户："开始)
    rest = es[len(NEW_PREAMBLE):]
    if not rest.startswith("\n\n"):
        # 没有前导段，直接进正文
        return es, changes

    # 找到正文起点：第一个 "\n用户：" 或开头的 "用户："
    # 先剥离前导部分的 prefix "\n\n"
    after_preamble = rest[2:]  # 去掉 "\n\n"

    # 找正文起点
    body_start_idx = None
    # 找 "\n用户：" 或开头 "用户：" 或 "（第一次对话）" 或 "（重启新的对话"
    for marker in ["\n用户：", "用户：", "（第一次对话）", "（重启新的对话"]:
        idx = after_preamble.find(marker)
        if idx == 0:
            body_start_idx = 0
            break
        if idx > 0 and (body_start_idx is None or idx < body_start_idx):
            # 前导段必须连续，不允许 marker 出现在前导段中部
            # 简化：取最小的正 idx
            body_start_idx = idx

    if body_start_idx is None:
        # 没有正文起点，整段都是前导，不处理
        return es, changes

    preamble_section = after_preamble[:body_start_idx].rstrip()
    body_section = after_preamble[body_start_idx:]

    if not preamble_section:
        return es, changes

    # 检查前导段中是否含旧版唤醒词
    has_old_wake = "你好，你好奔驰" in preamble_section
    # 检查前导段中是否含任何重试说明
    has_retry_mention = "重试" in preamble_section and ("你好奔驰" in preamble_section or "你好，你好奔驰" in preamble_section)

    if not has_old_wake and not has_retry_mention:
        return es, changes

    # 把前导段按 "（）" 包裹的子段拆分
    # 模式：匹配 （...）  作为一段；其余为普通文本段
    parts = []
    i = 0
    while i < len(preamble_section):
        if preamble_section[i] == "（":
            # 找到对应的 ）
            j = preamble_section.find("）", i)
            if j == -1:
                parts.append(("text", preamble_section[i:]))
                break
            parts.append(("paren", preamble_section[i:j+1]))
            i = j + 1
            # 跳过换行
            while i < len(preamble_section) and preamble_section[i] in "\n":
                i += 1
        else:
            # 找下一个 （
            j = preamble_section.find("（", i)
            if j == -1:
                parts.append(("text", preamble_section[i:]))
                break
            parts.append(("text", preamble_section[i:j].strip()))
            if parts[-1][1] == "":
                parts.pop()
            i = j

    new_parts = []
    removed_any = False
    for ptype, pcontent in parts:
        if ptype == "paren":
            # 判断这一段是否是纯重试说明
            is_pure_retry = any(pcontent.startswith(prefix) for prefix in PURE_RETRY_PARENS_PREFIXES) and \
                            "重试" in pcontent and \
                            ("你好奔驰" in pcontent or "你好，你好奔驰" in pcontent)
            if is_pure_retry:
                changes.append(f"删除纯重试说明段: {pcontent[:60]}...")
                removed_any = True
                continue
            # 不是纯重试说明，但可能内含重试句子 - 用正则删除句子
            new_pcontent = RETRY_REGEX.sub("", pcontent)
            # 清理多余的分号、空格
            new_pcontent = re.sub(r"[；;]\s*[；;]", "；", new_pcontent)
            new_pcontent = re.sub(r"^[；;]\s*", "", new_pcontent.strip())
            new_pcontent = re.sub(r"\s*[；;]\s*$", "", new_pcontent)
            # 去除空的括号段
            inner = new_pcontent[1:-1].strip() if new_pcontent.startswith("（") and new_pcontent.endswith("）") else new_pcontent.strip()
            if not inner:
                changes.append(f"段内重试句删空，整段移除: {pcontent[:60]}...")
                removed_any = True
                continue
            if new_pcontent != pcontent:
                changes.append(f"段内删除重试句: {pcontent[:60]}... -> {new_pcontent[:60]}...")
            new_parts.append(("paren", new_pcontent))
        else:
            new_parts.append((ptype, pcontent))

    if not removed_any:
        # 没有整段删除，尝试句子级清理
        # 对整段 preamble_section 做一次 RETRY_REGEX 替换
        new_preamble_section = RETRY_REGEX.sub("", preamble_section)
        new_preamble_section = re.sub(r"[；;]\s*[；;]", "；", new_preamble_section)
        new_preamble_section = re.sub(r"^[；;]\s*", "", new_preamble_section.strip())
        new_preamble_section = re.sub(r"\s*[；;]\s*$", "", new_preamble_section)
        if new_preamble_section != preamble_section:
            changes.append(f"句子级清理: {preamble_section[:60]}... -> {new_preamble_section[:60]}...")
            preamble_section = new_preamble_section
    else:
        # 重新组装
        new_preamble_section = ""
        for ptype, pcontent in new_parts:
            if ptype == "paren":
                new_preamble_section += pcontent + "\n\n"
            else:
                if pcontent:
                    new_preamble_section += pcontent + "\n\n"
        new_preamble_section = new_preamble_section.rstrip()

    # 重新组装 expected_script
    if new_preamble_section:
        new_es = NEW_PREAMBLE + "\n\n" + new_preamble_section + "\n\n" + body_section.lstrip()
    else:
        new_es = NEW_PREAMBLE + "\n\n" + body_section.lstrip()

    return new_es, changes


def main():
    data = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    print(f"总case数: {len(data)}")

    modified = 0
    for i, case in enumerate(data):
        cid = case.get("id", "?")
        es = case.get("expected_script", "")
        new_es, changes = clean_expected_script(es)
        if changes:
            case["expected_script"] = new_es
            modified += 1
            print(f"\n[{i}] {cid} ({case.get('case_id', '?')})")
            for ch in changes:
                print(f"  - {ch}")

    CASES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n修改: {modified} 条")
    print(f"已写回: {CASES_FILE}")


if __name__ == "__main__":
    main()
