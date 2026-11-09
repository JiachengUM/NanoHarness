"""把控的具体实现（plact core 只依赖 :mod:`aicore.agents.plan.judge` 的协议）。

======================  ==========================================================================
实现                     说明
======================  ==========================================================================
:class:`JevJudge`        TypeSafe System One（``system_one``）：一次往返回答任意多个原子问题，
                        裁决由代码组合方程算出；失败直接抛错，不静默降级
:class:`LlmJudge`        对照组 / 无 Jev 时的可用路径：同一份裁剪后的 state + 结构化输出，
                        判定失败在实现内部转成保守裁决
======================  ==========================================================================

两个实现共享 :mod:`.points` 的判定点表（问题集 / LLM 契约 / 组合方程 / 共享路由）与
:mod:`aicore.agents.plan.trim` 的证据裁剪，所以"换谁来判"是构造参数的一处改动。
"""

from aicore.agents.plan.judges.jev import JevJudge
from aicore.agents.plan.judges.jev_client import (
    DEFAULT_JEV_TIMEOUT,
    AsyncJevClient,
    JevAnswer,
    JevClient,
    JevError,
    JevResponse,
    JevTimeoutError,
    load_typesafe_api_key,
)
from aicore.agents.plan.judges.llm import LlmJudge, LlmJudgeError
from aicore.agents.plan.judges.points import (
    ALL_POINTS as DECISION_POINTS,
    DecisionPoint,
    clause_question_id,
    clause_quality_question_id,
)

__all__ = [
    # 实现
    "JevJudge",
    "LlmJudge",
    "LlmJudgeError",
    # 客户端
    "AsyncJevClient",
    "JevClient",
    "JevAnswer",
    "JevResponse",
    "JevError",
    "JevTimeoutError",
    "DEFAULT_JEV_TIMEOUT",
    "load_typesafe_api_key",
    # 判定点表
    "DecisionPoint",
    "DECISION_POINTS",
    "clause_question_id",
    "clause_quality_question_id",
]
