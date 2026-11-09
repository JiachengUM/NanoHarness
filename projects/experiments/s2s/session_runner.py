"""会话重置哨兵：在 Agent.astream 入口拦截，无需自定义 Runner。

``AgentRunnerBase._run_agent`` 被 ``typing.final`` 锁定不可覆盖时，用 :class:`SessionResetInterceptAgent`
包裹 :class:`~aicore.v1.experiments.agent.Agent`，仍使用框架自带的 ``AgentRunnerBase``。

多轮对话（S2STUIAgentApp）侧的机制与本模块的关系：
------------------------------------------------------------------
- ``S2STUIAgentApp`` 在用户静音超时、关键字结束等时机，会向 ``QueueUserDataSource`` 投递
  特殊串 :data:`SESSION_RESET_INPUT`（不得与普通 ASR 文本相同）。
- Runner 拉出该字符串并作为 ``query`` 调 ``agent.astream`` 时，本封装类拦截该次调用：
  **不**把该串写入模型上下文，而是 ``await inner.new_session()``（清空 ReAct/记忆与会话侧的
  「一轮多轮对话」语义边界），然后可选触发 ``on_after_session_reset``，供上层打印「第N次多轮对话结束」。
- 因此：**只有**内层 ``Agent`` 被包在 :class:`SessionResetInterceptAgent` 里时，App 里追加的
  ``SESSION_RESET_INPUT`` 才会真正执行 ``new_session``；若 Runner 直连未包裹的 Agent，则
  哨兵串可能被当普通用户话处理，多轮边界行为与预期不符。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, AsyncGenerator

from aicore.core.event import EventGenerator
from aicore.v1.experiments.agent import Agent, AgentEvent

# 放入 UserDataSource 队列的特殊字符串，禁止与普通 ASR 文案冲突。
# S2STUIAgentApp 在「结束当前多轮」时向同一队列 put 该串；Runner 顺序消费。
SESSION_RESET_INPUT = "__s2s_session_reset__"


class SessionResetInterceptAgent(EventGenerator[AgentEvent]):
    """收到 :data:`SESSION_RESET_INPUT` 时只执行 ``await inner.new_session()``，不向模型投递。

    与多轮边界：
        一次「多轮对话」在用户侧由首条 finalized ASR 注入开始（见 App 内 ``_maybe_log_multiturn_session_begin``），
        在 ``new_session()`` 完成后结束（``on_after_session_reset`` 中打「第N次多轮对话结束」）。
        中间若用户继续说话，仍属同一多轮，不再重复「第N次多轮对话开始」。
    """

    def __init__(
        self,
        inner: Agent,
        *,
        on_after_session_reset: Callable[[], None] | None = None,
    ) -> None:
        self._inner = inner
        # S2STUIAgentApp 若检测到 runner._agent 为本类实例，会挂上此回调以同步记日志 / TUI。
        self.on_after_session_reset = on_after_session_reset

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def astream(
        self,
        query: str,
        /,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentEvent, None]:
        if query == SESSION_RESET_INPUT:
            # 静音超时：告别 TTS 已在上游完成；关键字结束：通常在本轮用户话之后另 put 了本哨兵，
            # Runner 与正常 ASR 一样串行处理，此处仅刷新会话，不产生模型 token。
            await self._inner.new_session()
            cb = self.on_after_session_reset
            if cb is not None:
                cb()
            return
        async for event in self._inner.astream(query, **kwargs):
            yield event


__all__ = ["SESSION_RESET_INPUT", "SessionResetInterceptAgent"]
