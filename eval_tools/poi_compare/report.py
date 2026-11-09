"""
Report：读取results.json，输出汇总矩阵和case详情。
与runner解耦，可独立重跑。
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from eval_tools.poi_compare.models import ExperimentRecord

RESULTS_PATH = Path(__file__).parent / "results.json"

DIMENSION_LABELS = {
    "criteria_complexity": "需求复杂度",
    "planning": "规划复杂度",
    "error_recovery": "纠错能力",
}


def _print_indented_block(title: str, content: str) -> None:
    print(f"    {title}:")
    for line in content.splitlines():
        print(f"      {line}")


def print_report(results_path: Path = RESULTS_PATH) -> None:
    with open(results_path, encoding="utf-8") as f:
        data = json.load(f)

    records = [ExperimentRecord(**r) for r in data]

    by_dim: dict[str, list[ExperimentRecord]] = defaultdict(list)
    for r in records:
        by_dim[r.dimension].append(r)

    print("\n" + "=" * 64)
    print("POI Search: ReAct vs Ralph Loop 对比实验报告")
    print("=" * 64)

    print(f"\n{'维度':<16} {'ReAct通过率':<14} {'Ralph通过率':<14} {'平均分差'}")
    print("-" * 60)

    total_react_pass = total_ralph_pass = 0
    total_react_score = total_ralph_score = 0
    total = 0

    for dim_key, dim_label in DIMENSION_LABELS.items():
        dim_records = by_dim.get(dim_key, [])
        if not dim_records:
            continue
        n = len(dim_records)
        react_pass = sum(1 for r in dim_records if r.react_result.pass_fail)
        ralph_pass = sum(1 for r in dim_records if r.ralph_result.pass_fail)
        react_avg = sum(r.react_result.score for r in dim_records) / n
        ralph_avg = sum(r.ralph_result.score for r in dim_records) / n
        diff = ralph_avg - react_avg

        sign = "+" if diff >= 0 else ""
        print(f"{dim_label:<16} {react_pass}/{n:<12} {ralph_pass}/{n:<12} {sign}{diff:.1f}")

        total_react_pass += react_pass
        total_ralph_pass += ralph_pass
        total_react_score += sum(r.react_result.score for r in dim_records)
        total_ralph_score += sum(r.ralph_result.score for r in dim_records)
        total += n

    if total:
        total_diff = (total_ralph_score - total_react_score) / total
        sign = "+" if total_diff >= 0 else ""
        print("-" * 60)
        print(f"{'总计':<16} {total_react_pass}/{total:<12} {total_ralph_pass}/{total:<12} {sign}{total_diff:.1f}")

    print("\n" + "=" * 64)
    print("Case 详情")
    print("=" * 64)

    for r in records:
        print(f"\n[{r.case_id}] (维度:{r.dimension} Level:{r.level})")
        print(f"  Goal: {r.goal}")
        print(f"  ReAct  — score={r.react_result.score} {'PASS' if r.react_result.pass_fail else 'FAIL'} steps={r.react_steps}")
        print(f"    理由: {r.react_result.reason[:200]}")
        # if r.react_trajectory:
        #     _print_indented_block("ReAct轨迹", r.react_trajectory)
        print(f"  Ralph  — score={r.ralph_result.score} {'PASS' if r.ralph_result.pass_fail else 'FAIL'} rounds={r.ralph_rounds}")
        print(f"    理由: {r.ralph_result.reason[:200]}")
        # if r.ralph_trajectories:
        #     print("    Ralph轨迹:")
        #     for idx, trajectory in enumerate(r.ralph_trajectories, 1):
        #         _print_indented_block(f"第{idx}轮", trajectory)


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS_PATH
    print_report(path)
