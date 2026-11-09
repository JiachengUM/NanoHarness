#!/usr/bin/env python3
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from projects.mind.mem.auto_test_script.case_schema import TestCase

DATA_PATH = Path(__file__).resolve().parent / "vehicle_assistant_leaf_cases.json"


def main():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    ok = 0
    fail_list = []

    for i, c in enumerate(data):
        try:
            TestCase(**c)
            ok += 1
        except Exception as e:
            fail_list.append((i, c.get("id", "?"), e))

    print(f"total={len(data)}  ok={ok}  fail={len(fail_list)}")

    if not fail_list:
        print("All cases pass schema validation!")
        return

    print(f"\n{'='*60}")
    print("Failed cases detail:")
    print(f"{'='*60}")

    for idx, cid, exc in fail_list:
        c = data[idx]
        print(f"\n--- [{idx}] {cid} ---")
        print(f"  Error: {type(exc).__name__}: {str(exc)[:300]}")

        if "context_config" not in c:
            print("  [MISSING] context_config field")

        uql = c.get("user_query_lists", [])
        for si, sess in enumerate(uql):
            if isinstance(sess, dict):
                print(f"  user_query_lists[{si}] is DICT (DialogueRoundConfig): keys={list(sess.keys())}")
            elif isinstance(sess, list):
                for mi, m in enumerate(sess):
                    if isinstance(m, str):
                        print(f"  user_query_lists[{si}][{mi}] is STR: {m[:80]}")
                    elif isinstance(m, dict):
                        ct = type(m.get("content")).__name__
                        print(f"  user_query_lists[{si}][{mi}] is DICT: role={m.get('role')}, content_type={ct}")


if __name__ == "__main__":
    main()
