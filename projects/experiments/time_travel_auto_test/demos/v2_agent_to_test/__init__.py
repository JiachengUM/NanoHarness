"""TimeTravelRunner 被测 Agent：基于 aicore v2 ReAct 的参考实现。"""

from projects.experiments.time_travel_auto_test.demos.v2_agent_to_test.tested_assistant import (
    DEFAULT_SYSTEM_PROMPT,
    TestedAssistant,
)

__all__ = [
    "TestedAssistant",
    "DEFAULT_SYSTEM_PROMPT",
]
