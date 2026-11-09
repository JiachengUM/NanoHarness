"""校验 cases JSON 文件格式是否合法，并做基本字段检查。

用法:
    py scripts/leaf_cases/check_json_format.py [cases_json_path]

不带参数时默认校验 benz 项目 cases 文件。
"""
import json
import sys
from pathlib import Path


def check(path: str) -> int:
    p = Path(path)
    if not p.exists():
        print(f"[FAIL] 文件不存在: {path}")
        return 1

    raw = p.read_text(encoding="utf-8")

    # 1. JSON 格式校验
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[FAIL] JSON 解析失败: {e.msg} (行 {e.lineno} 列 {e.colno})")
        lines = raw.splitlines()
        start = max(0, e.lineno - 3)
        end = min(len(lines), e.lineno + 2)
        print(f"  上下文（行 {start + 1}-{end}）:")
        for i in range(start, end):
            marker = " >>> " if i + 1 == e.lineno else "     "
            print(f"{marker}{i + 1}: {lines[i]}")
        return 1

    if not isinstance(data, list):
        print(f"[FAIL] 顶层应为数组，实际为 {type(data).__name__}")
        return 1

    # 2. 基本 schema 字段检查
    required = [
        "id", "case_id", "context_config", "max_round",
        "user_query_lists", "expected_script", "nl_assertion",
        "code_assertion", "case_description", "tags",
    ]
    errors = 0
    ids = set()
    for i, case in enumerate(data):
        cid = case.get("id", f"index[{i}]")
        for k in required:
            if k not in case:
                print(f"[FAIL] {cid} 缺字段: {k}")
                errors += 1
        if cid in ids:
            print(f"[FAIL] id 重复: {cid}")
            errors += 1
        ids.add(cid)
        if "tags" in case and not isinstance(case["tags"], list):
            print(f"[FAIL] {cid} tags 应为数组")
            errors += 1
        if "user_query_lists" in case:
            uql = case["user_query_lists"]
            if not isinstance(uql, list) or not uql:
                print(f"[FAIL] {cid} user_query_lists 应为非空数组")
                errors += 1
            else:
                for si, session in enumerate(uql):
                    if not isinstance(session, list) or not session:
                        print(f"[FAIL] {cid} user_query_lists[{si}] 应为非空数组")
                        errors += 1
                        continue
                    # C1 原则：每 session 仅1条 user（冷启动入口单条）
                    user_count = sum(1 for m in session if isinstance(m, dict) and m.get("role") == "user")
                    if user_count > 1:
                        print(f"[FAIL] {cid} user_query_lists[{si}] 有 {user_count} 条 user（C1 违反：每 session 仅1条 user，第2轮起写在 expected_script）")
                        errors += 1
                    # F5 原则：自动测试集不应包含电话类 case（通话态阻塞，无法自动测）
                    # 例外：定时提醒语境（记得/提醒...打电话）是让助手设提醒，不会进入通话态，不视为电话类
                    phone_kws = ["打电话", "拨打", "拨号", "呼叫", "拨通"]
                    remind_kws = ["记得", "提醒", "别忘"]
                    for m in session:
                        if isinstance(m, dict):
                            content = m.get("content", "")
                            if any(kw in content for kw in phone_kws):
                                is_remind = any(rk in content for rk in remind_kws)
                                if not is_remind:
                                    print(f"[FAIL] {cid} 含电话拨打意图（F5 违反：电话类case无法自动测试，应移至 phone_cases_manual_only.json）")
                                    errors += 1
        # F5 原则：expected_script 也不应含电话拨打意图
        es = case.get("expected_script", "")
        phone_kws = ["打电话", "拨打", "拨号", "呼叫", "拨通"]
        remind_kws = ["记得", "提醒", "别忘"]
        if any(kw in es for kw in phone_kws):
            # 排除定时提醒语境（记得/提醒...打电话），以及先导段里出现的词
            # 逐行检查含电话关键词的行，若同时含提醒关键词则不算违规
            viol_lines = 0
            for line in es.split("\n"):
                if any(kw in line for kw in phone_kws) and not any(rk in line for rk in remind_kws):
                    viol_lines += 1
            if viol_lines > 0:
                print(f"[FAIL] {cid} expected_script 含电话拨打意图（F5 违反：电话类case无法自动测试）")
                errors += 1
        if "nl_assertion" in case and not isinstance(case["nl_assertion"], list):
            print(f"[FAIL] {cid} nl_assertion 应为数组")
            errors += 1

    if errors:
        print(f"[FAIL] 共 {errors} 处字段错误")
        return 1

    print(f"[OK] {path}")
    print(f"     {len(data)} 条 case，JSON 格式合法，字段完整，id 唯一")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        path = "artifacts/projects/benz_project/cases/vehicle_assistant_cases.json"
    else:
        path = sys.argv[1]
    sys.exit(check(path))
