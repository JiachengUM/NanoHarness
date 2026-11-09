"""把 remark_非VF车控数据 两份 xlsx 合并导出为 json，供转化脚本使用。

输出：artifacts/projects/benz_project/inputs/extracted/remark_non_vf_rows.json
每行字段：testcase_name / feature_name / query_name / grammar_tag / instruction_classification / source_file
"""
import json
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "artifacts" / "projects" / "benz_project" / "inputs" / "raw"
OUT = PROJECT_ROOT / "artifacts" / "projects" / "benz_project" / "inputs" / "extracted" / "remark_non_vf_rows.json"

FILES = [
    ("第一份", RAW_DIR / "remark_非VF车控数据_第一份.xlsx"),
    ("第二份", RAW_DIR / "remark_非VF车控数据_第二份.xlsx"),
]

all_rows = []
for tag, p in FILES:
    df = pd.read_excel(p, sheet_name="remark")
    for _, r in df.iterrows():
        all_rows.append({
            "testcase_name": str(r["testcase_name"]),
            "feature_name": str(r["feature_name"]) if pd.notna(r["feature_name"]) else "",
            "query_name": str(r["query_name"]) if pd.notna(r["query_name"]) else "",
            "grammar_tag": str(r["grammar_tag"]) if pd.notna(r["grammar_tag"]) else "",
            "instruction_classification": str(r["instruction_classification"]) if pd.notna(r["instruction_classification"]) else "",
            "source_file": tag,
        })

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"导出 {len(all_rows)} 条到 {OUT}")
print()
# 按 feature_name 统计
from collections import Counter
c = Counter(r["feature_name"] for r in all_rows)
for k, v in c.most_common():
    print(f"  {k}: {v}")
