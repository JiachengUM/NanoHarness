"""Check which Excel rows were skipped during initial conversion."""
import openpyxl
import json
from pathlib import Path

EXCEL = Path(r"d:\yitu_projects\nanoai\projects\mind\mem\auto_test_script\make_datasets_for_vehicle_assistant\artifacts\projects\benz_project\inputs\raw\弋途核心功能测试用例.xlsx")
NAV_ONLY = Path(r"d:\yitu_projects\nanoai\projects\mind\mem\auto_test_script\make_datasets_for_vehicle_assistant\artifacts\projects\benz_project\cases\vehicle_assistant_cases_from_excel_nav_only.json")

wb = openpyxl.load_workbook(str(EXCEL), data_only=True)
ws = wb["导航"]

# Get all queries from Excel nav sheet
excel_queries = []
for r in range(2, ws.max_row + 1):
    q = ws.cell(r, 5).value  # Query column (E, index 5)
    if q and str(q).strip():
        excel_queries.append((r, str(q).strip()))

print(f"Excel nav sheet: {len(excel_queries)} non-empty queries (rows 2-{ws.max_row})")

# Get all Q1 from nav_only
nav_data = json.loads(NAV_ONLY.read_text(encoding="utf-8"))
nav_q1s = set()
for c in nav_data:
    uq = c.get("user_query_lists", [[{}]])
    if uq and uq[0]:
        q1 = uq[0][0].get("content", "")
        nav_q1s.add(q1)

print(f"nav_only: {len(nav_data)} cases")

# Find Excel queries not in nav_only
missing = []
for r, q in excel_queries:
    # Check if this query (or part of it) is in any nav Q1
    found = False
    for nq in nav_q1s:
        if q in nq or nq in q:
            found = True
            break
        # Also check first 20 chars
        if len(q) > 10 and q[:20] in nq:
            found = True
            break
    if not found:
        missing.append((r, q))

print(f"\nMissing from nav_only: {len(missing)} queries")
print("\nFirst 30 missing:")
for r, q in missing[:30]:
    print(f"  R{r}: {q[:80]}")
