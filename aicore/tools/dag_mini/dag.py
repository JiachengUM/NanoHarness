"""DAG Mini — 拓扑分层（Kahn's algorithm）。"""

from __future__ import annotations

import logging
import time

from pydantic import BaseModel, ConfigDict, Field

from aicore.tools.dag_mini.models import StepGoal

logger = logging.getLogger(__name__)


class DAG(BaseModel):
    """DAG 节点集合 + 拓扑分层。"""

    model_config = ConfigDict(extra="ignore")

    nodes: list[StepGoal] = Field(default_factory=list)

    def to_layers(self) -> list[list[StepGoal]]:
        """按 depends_on 拓扑分层（Kahn's algorithm）。

        Returns:
            分层后的节点列表：layers[0] 是无依赖节点；layers[i+1] 依赖 layers[0..i]。

        Raises:
            ValueError: 依赖引用未声明的 step_id；拓扑图存在 cycle。
        """
        t0 = time.monotonic()
        by_id = {n.step_id: n for n in self.nodes}
        for n in self.nodes:
            for dep in n.depends_on:
                if dep not in by_id:
                    raise ValueError(f"DAG 节点 {n.step_id} 引用未知依赖: {dep}")

        remaining: dict[str, list[str]] = {n.step_id: list(n.depends_on) for n in self.nodes}
        layers: list[list[StepGoal]] = []

        while remaining:
            ready = [sid for sid, deps in remaining.items() if not deps]
            if not ready:
                raise ValueError(f"DAG 拓扑分层检测到 cycle，剩余节点: {list(remaining.keys())}")
            layers.append([by_id[sid] for sid in ready])
            ready_set = set(ready)
            remaining = {
                sid: [d for d in deps if d not in ready_set]
                for sid, deps in remaining.items()
                if sid not in ready_set
            }

        logger.info(
            "DAG.to_layers 完成: %d nodes → %d 层, 耗时=%.3fs",
            len(self.nodes), len(layers), time.monotonic() - t0,
        )
        return layers
