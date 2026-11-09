"""TimelineEngine：虚拟时间引擎（自然流逝 + 快进）。

核心模型（ARCHITECTURE §7.5 自然时间流逝）：
- 虚拟时间 mock_time 与真实时间 wall time 通过锚点对 (anchor_mock, anchor_wall) 连续锚定
- 任意时刻 mock_time = anchor_mock + (now - anchor_wall)，即两者 1:1 自然流逝
- 唯一的时间跳跃方式是 accelerate_to（快进）：重新锚定并记录跳跃历史
- 不存在"时间冻结"：助手回复、假人说话、LLM 生成期间，虚拟时间照常流逝

因此：
- 假人/助手的话语都是耗时说出来的，时间戳直观反映实际发生时刻
- 助手在回复期间调 set_reminder 等工具拿到的是实时虚拟时间，无需任何偏移修正
- 打断时刻 = 触发打断的锚点时刻，天然不会因果倒置
"""

from __future__ import annotations

from datetime import datetime, timedelta


# 锚点对齐容差：事件按真实时间等待触发时的事件循环误差（毫秒级~亚秒级）
# 在容差内把虚拟时间精确对齐到锚点，让时间戳显示干净（如 T0+3.000s）
PIN_TOLERANCE: timedelta = timedelta(seconds=5.0)


class TimelineEngine:
    """虚拟时间引擎：wall↔mock 连续锚定，支持快进。"""

    def __init__(self, t0: datetime) -> None:
        self._t0: datetime = t0
        # 锚点对：虚拟锚点时刻 + 设定锚点时的真实时刻
        self._anchor_mock: datetime = t0
        self._anchor_wall: datetime = datetime.now()
        self._accelerations: list[tuple[datetime, datetime]] = []

    @property
    def t0(self) -> datetime:
        return self._t0

    @property
    def mock_time(self) -> datetime:
        """当前虚拟时间（实时计算）：锚点虚拟时刻 + 真实流逝时长。

        每次读取都基于真实时钟实时计算，时间永远在自然流逝。
        """
        return self._anchor_mock + (datetime.now() - self._anchor_wall)

    def wall_to_mock(self, wall_time: datetime) -> datetime:
        """把一个真实时刻映射为虚拟时刻（1:1 流逝期间的双向换算）。

        用于把事件流携带的 wall_time 时间戳换算进虚拟时间线。
        注意：若换算发生在快进之后，结果会偏离快进前的语义——
        调用方应确保事件发生后立即换算（本框架内均如此）。
        """
        return self._anchor_mock + (wall_time - self._anchor_wall)

    def accelerate_to(self, target: datetime) -> None:
        """快进虚拟时间到 target（唯一的时间跳跃方式）。

        重新锚定 (target, now)，并记录跳跃历史。
        target 不早于当前虚拟时间才生效。
        """
        current = self.mock_time
        if target > current:
            self._accelerations.append((current, target))
            self._anchor_mock = target
            self._anchor_wall = datetime.now()

    def pin_to(self, target: datetime) -> bool:
        """把虚拟时间精确对齐到 target（仅在漂移 ≤ PIN_TOLERANCE 时生效）。

        调度器按真实时间等待锚点事件，触发时刻存在毫秒级误差；
        对齐后时间戳显示干净（T0+3.000s 而非 T0+3.012s）。
        漂移过大（事件被前序执行拖晚）时不对齐——事件晚了就如实记录晚的时刻。
        """
        drift = (self.mock_time - target).total_seconds()
        if abs(drift) <= PIN_TOLERANCE.total_seconds():
            self._anchor_mock = target
            self._anchor_wall = datetime.now()
            return True
        return False

    def jump_to(self, target: datetime) -> None:
        """强制把虚拟时间重设为 target（不记录快进）。

        仅 fast_mode（单元测试跳过真实等待）使用：事件密集回放时
        虚拟时间直接跟随事件锚点走，不等真实时间。
        """
        self._anchor_mock = target
        self._anchor_wall = datetime.now()

    @property
    def accelerations(self) -> list[tuple[datetime, datetime]]:
        """快进历史：[(from, to), ...]"""
        return list(self._accelerations)
