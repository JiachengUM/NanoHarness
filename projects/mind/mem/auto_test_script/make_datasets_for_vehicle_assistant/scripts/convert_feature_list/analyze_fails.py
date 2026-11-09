"""Analyze FAIL cases and generate manual fix script."""
import json
from collections import Counter
from pathlib import Path

FAIL_FILE = Path(r"d:\yitu_projects\nanoai\projects\mind\mem\auto_test_script\make_datasets_for_vehicle_assistant\artifacts\projects\benz_project\audit_results\batch_fail_20260729_203704.json")
data = json.loads(FAIL_FILE.read_text(encoding="utf-8"))

issue_types = Counter()
for c in data:
    for iss in c.get("issues_if_failed", []):
        dim = iss.get("dimension", "?")
        issue_types[dim] += 1

print("FAIL case issue dimensions:")
for k, v in issue_types.most_common():
    print(f"  {k}: {v}")

print()
print(f"Total FAIL: {len(data)}")
print()

# Show all FAIL case ids and their primary issue
print("=== FAIL cases ===")
for c in data:
    cid = c["original_id"]
    issues = c.get("issues_if_failed", [])
    dims = [iss.get("dimension", "?") for iss in issues]
    print(f"{cid}: {dims}")
