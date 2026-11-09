from __future__ import annotations

from typing import Any

from projects.sgm_prod.classification.engine import arbitrate_simple_complex_decision
from projects.sgm_prod.classification.models import IntentType


async def arbitrate_simple_complex(
    query: str,
    *,
    project: str = "default",
    history: list[dict[str, Any]] | None = None,
) -> tuple[IntentType, str]:
    decision = await arbitrate_simple_complex_decision(
        query,
        project=project,
        history=history,
        use_exact_match=True,
    )
    return decision.label, decision.source
