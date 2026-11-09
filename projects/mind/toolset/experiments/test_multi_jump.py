from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from projects.mind.toolset.experiments.multi_jump import MultiHopPoiCandidate, MultiHopPoiWorker


DEFAULT_CASES = [
    "帮我搜一个周围带书店的公园",
    "帮我找一个附近有咖啡店的书店",
    "帮我找一个周边有停车场的餐厅",
]


def _print_candidate(candidate: MultiHopPoiCandidate, index: int) -> None:
    poi = candidate.poi
    print(f"\n[{index}] {poi.name}")
    print(f"  type: {poi.type}")
    print(f"  address: {poi.address}")
    print(f"  location: {poi.location}")
    print(f"  score: {candidate.score}")
    print(f"  reason: {candidate.reason}")

    for evidence in candidate.related:
        print(f"  nearby: {evidence.keywords} / radius={evidence.radius}m / count={evidence.matched_count}")
        if evidence.nearest_distance is not None:
            print(f"  nearest: {evidence.nearest_distance}m")
        for related_poi in evidence.pois[:5]:
            print(f"    - {related_poi.name} ({related_poi.distance}m) {related_poi.address}")


async def run_case(worker: MultiHopPoiWorker, query: str, *, city: str | None, radius: int, limit: int, raw: bool) -> None:
    print("\n" + "=" * 100)
    print(f"query: {query}")
    print(f"city={city}, radius={radius}, candidate_limit={limit}")

    output = await worker(query=query, city=city, radius=radius, candidate_limit=limit)

    print("\n--- plan ---")
    print(output.plan.model_dump(exclude_none=True))

    print("\n--- result ---")
    print(output.message)
    for index, candidate in enumerate(output.candidates, start=1):
        _print_candidate(candidate, index)

    if raw:
        print("\n--- raw output ---")
        print(output.model_dump(exclude_none=True))


async def run_cases(queries: list[str], *, city: str | None, radius: int, limit: int, raw: bool) -> None:
    worker = MultiHopPoiWorker()
    for query in queries:
        try:
            await run_case(worker, query, city=city, radius=radius, limit=limit, raw=raw)
        except Exception as e:
            print("\n" + "=" * 100)
            print(f"query: {query}")
            print(f"error: {type(e).__name__}: {e}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real multi-hop POI search cases.")
    parser.add_argument("query", nargs="*", help="可选。传入一个查询；包含空格时请用引号包起来。")
    parser.add_argument("--case", action="append", default=[], help="追加一个查询 case；可重复传多次。")
    parser.add_argument("--city", default="上海", help="搜索城市；传空字符串表示不指定。默认：上海")
    parser.add_argument("--radius", type=int, default=1000, help="周边关系检索半径，单位米。默认：1000")
    parser.add_argument("--limit", type=int, default=10, help="第一跳主目标候选数量上限。默认：10")
    parser.add_argument("--raw", action="store_true", help="额外打印完整 model_dump 输出。")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    queries: list[str] = []
    if args.query:
        queries.append(" ".join(args.query))
    queries.extend(args.case)
    if not queries:
        queries = DEFAULT_CASES

    city = args.city or None
    asyncio.run(run_cases(queries, city=city, radius=args.radius, limit=args.limit, raw=args.raw))


if __name__ == "__main__":
    main()
