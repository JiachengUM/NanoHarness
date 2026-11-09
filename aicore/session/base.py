from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field


class SessionStatus(StrEnum):
    """Session 生命周期状态。"""

    IDLE = "idle"
    RUNNING = "running"
    CLOSED = "closed"


class SessionTurnStatus(StrEnum):
    """Session 中单个 turn 的生命周期状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionContext(BaseModel):
    """Session 上下文定义。

    在本项目中，context 表达静态信息。Session context 描述创建 Session 时
    已经确定、且不应随单轮输入自然变化的信息，例如所属用户、入口来源、
    业务域、权限边界或默认执行配置。

    会随时间变化的外部事实不应写入 context；它们应通过 state_update 进入
    SessionState。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    values: dict[str, Any] = Field(default_factory=dict, description="会话静态上下文")
    """创建 Session 时确定的静态信息。"""


class SessionStateUpdate(BaseModel):
    """Session 状态更新。

    submit 时携带的动态信息最终应落到 SessionState 中，因此这里不命名为
    context。它表示本轮输入附带的最新外部事实，例如当前位置、设备状态、
    前端状态或业务对象的临时变化。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    values: dict[str, Any] = Field(default_factory=dict, description="会话状态更新")
    """需要合并进 SessionState.values 的动态事实。"""


class SessionSubmission(BaseModel):
    """Session 提交结果。

    submit 只表示输入是否成功进入会话处理流程，不携带实际响应。
    Session 在接受输入时为其创建 turn 并分配 turn_id。
    """

    accepted: bool = Field(..., description="消息是否提交成功")
    """消息是否已被 Session 接收。"""

    turn_id: str = Field(..., description="提交的 turn 标识")
    """Session 为本次提交创建的 turn 标识。"""

    reason: str | None = Field(default=None, description="提交失败原因")
    """提交失败时给调用方的原因说明。"""


class SessionOutput(BaseModel):
    """Session 对外输出。

    SessionOutput 是调用方可消费的输出流元素。它只表达 Session 层的可观察
    输出，不规定底层执行内核如何生成消息、事件或模型响应。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    turn_id: str = Field(..., description="所属 turn 标识")
    """产生该输出的 turn 标识。"""

    data: Any = Field(..., description="输出载荷")
    """对外输出的具体载荷。"""

    metadata: dict[str, Any] = Field(default_factory=dict, description="输出元数据")
    """输出相关的附加信息，例如序号、来源、消息类型或追踪标识。"""


class SessionTrace(BaseModel):
    """Session turn 的运行轨迹。

    Trace 用于观察和调试 Session 内部的运行过程。它不同于普通输出：
    输出面向产品交互，trace 面向诊断、审计和回放。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    turn_id: str = Field(..., description="所属 turn 标识")
    """产生该轨迹的 turn 标识。"""

    data: Any = Field(..., description="轨迹载荷")
    """运行轨迹的具体载荷。"""

    metadata: dict[str, Any] = Field(default_factory=dict, description="轨迹元数据")
    """轨迹相关的附加信息，例如阶段、时间、来源或调试标识。"""


class SessionTurn(BaseModel):
    """Session 中一次完整的输入、执行和结果记录。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(..., description="turn 唯一标识")
    """由 Session 分配、在 Session 内唯一的 turn 标识。"""

    input: Any = Field(..., description="本 turn 的输入")
    """提交给 Session 的输入载荷。"""

    status: SessionTurnStatus = Field(
        default=SessionTurnStatus.PENDING, description="turn 生命周期状态"
    )
    """本 turn 当前的执行状态。"""

    outputs: list[SessionOutput] = Field(
        default_factory=list, description="本 turn 的对外输出"
    )
    """按产生顺序记录的产品侧输出。"""

    traces: list[SessionTrace] = Field(
        default_factory=list, description="本 turn 的运行轨迹"
    )
    """按产生顺序记录的诊断、审计或回放轨迹。"""

    error: str | None = Field(default=None, description="失败或取消原因")
    """仅在失败或取消时记录原因。"""

    metadata: dict[str, Any] = Field(default_factory=dict, description="turn 元数据")
    """调用来源、时间、调度等非推理语义附加信息。"""


class SessionState(BaseModel):
    """Session 状态定义。

    state 表示可能会变化的信息。它记录这段持续交互在运行期间形成的资产，
    例如生命周期状态、动态外部事实和 turn 历史。

    它不同于 context：context 是创建 Session 时确定的静态输入；state 是
    Session 在运行中持续变化、并需要用于恢复或接着对话的信息。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: SessionStatus = Field(
        default=SessionStatus.IDLE, description="会话生命周期状态"
    )
    """当前 Session 是否空闲、运行中或已经关闭。"""

    values: dict[str, Any] = Field(default_factory=dict, description="会话动态状态")
    """运行过程中持续变化的外部事实。submit 的 state_update 应最终合入这里。"""

    history: list[SessionTurn] = Field(
        default_factory=list, description="会话 turn 历史"
    )
    """这段 Session 已提交的完整 turn，按提交顺序排列。"""


class SessionDumpPayload(BaseModel):
    """Session 持久化结构。

    该结构用于保存或恢复一段 Session 的最小语义状态。
    它只表达 Session 作为交互边界所拥有的信息，不包含执行内核的私有实现细节。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str = Field(..., description="会话唯一标识")
    """Session 的稳定唯一标识。"""

    context: SessionContext = Field(
        default_factory=SessionContext, description="会话静态上下文"
    )
    """恢复 Session 时需要保留的静态上下文。"""

    state: SessionState = Field(default_factory=SessionState, description="会话状态")
    """恢复 Session 时需要保留的动态状态。"""

    metadata: dict[str, Any] = Field(default_factory=dict, description="会话元数据")
    """追踪、来源、设备、租户等附加信息。"""


class SessionBase(ABC):
    """Session 基础抽象。

    Session 是一次持续交互的边界。它负责定义这段交互的静态上下文、
    动态状态、生命周期、turn 历史和持久化形态。

    Session 可以使用任意执行内核完成工作，但执行内核只是实现细节；
    Session 的公开属性和方法应围绕会话自身的概念命名。
    """

    @classmethod
    @abstractmethod
    def new_session(
        cls,
        context: SessionContext | Mapping[str, Any] | None = None,
        /,
        *,
        metadata: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Self:
        """创建一个新的 Session。

        new_session 表示开始一段新的连续交互。需要重新开始时，应创建新的
        Session，而不是在已有 Session 上暴露状态清空语义。
        """
        ...

    @classmethod
    @abstractmethod
    def restore(
        cls,
        payload: SessionDumpPayload,
        /,
        **kwargs: Any,
    ) -> Self:
        """从持久化结构恢复 Session。

        restore 用于对外提供“接着对话”的能力。具体实现应根据 payload 中的
        context、state 和 metadata 重建会话边界，但不要求暴露底层执行内核细节。
        """
        ...

    @property
    @abstractmethod
    def id(self) -> str:
        """会话唯一标识。"""
        ...

    @property
    @abstractmethod
    def context(self) -> SessionContext:
        """会话静态上下文。

        context 表达创建 Session 时确定的静态信息。会随轮次变化的信息应进入
        state，而不是修改 context。
        """
        ...

    @property
    @abstractmethod
    def state(self) -> SessionState:
        """会话动态状态。

        state 表示 Session 在运行中持续变化的信息，包括生命周期、动态事实和
        完整的 turn 历史。
        """
        ...

    @property
    @abstractmethod
    def metadata(self) -> Mapping[str, Any]:
        """会话元数据。

        元数据用于承载追踪、来源、设备、租户等附加信息。
        它不应成为推理语义的主要输入。
        """
        ...

    @abstractmethod
    def update_state(
        self, state_update: SessionStateUpdate | Mapping[str, Any], /
    ) -> SessionState:
        """更新会话动态状态。

        该方法用于把新的外部事实写入 SessionState.values。
        具体实现可以选择替换、浅合并或带 schema 的合并策略，但应在文档中说明。
        """
        ...

    @abstractmethod
    async def cancel(self, turn_id: str, /) -> SessionTurn:
        """取消指定的运行中或等待中的 turn。

        实现应将对应 turn 置为 cancelled，并保留该 turn 已产生的输出和轨迹。
        已完成、失败或不存在的 turn 如何处理由具体实现定义并文档化。
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """关闭 Session。

        close 表示会话生命周期结束。具体实现应释放会话占用的运行资源，
        并使后续 submit 行为进入明确的不可用状态或重新创建流程。
        """
        ...

    @abstractmethod
    async def dump(self) -> SessionDumpPayload:
        """导出 Session 持久化结构。

        dump 应返回恢复这段 Session 语义状态所需的最小数据。
        它不应泄露执行内核的私有对象、连接句柄或不可序列化运行资源。
        """
        ...
