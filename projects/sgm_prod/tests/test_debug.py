from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from projects.sgm_prod.classification.engine import arbitrate_simple_complex_decision

async def main() -> None:
    query = "导航去迪士尼先去嘉定北地铁站接老婆再去找一个可以把车开进去取餐的麦当劳"
    decision = await arbitrate_simple_complex_decision(
        query,
        project="Volvo",
    )
    print(f"Query: {query}")
    print(f"Result: {decision.label} ({decision.source})")
    print(f"Decision path: {decision.trace.decision_path}")
    print(f"Risk flags: {decision.trace.risk_flags}")
    print(f"Matched candidates:")
    for c in decision.trace.matched_candidates:
        print(f"  - {c.capability_id}: covered='{c.covered_text}' unconsumed='{c.unconsumed_text}' risk={c.risk_flags} confidence={c.confidence}")

if __name__ == "__main__":
    asyncio.run(main())
