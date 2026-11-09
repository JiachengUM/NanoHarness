"""新接入协议：事件源适配器（Event-Source Adapter）模式。

设计目标（对照旧 assistant_protocol.py 的教训）：
- 旧协议是「5 个方法 + 8 个散落 hasattr 钩子」，把异步工具回灌、空闲判定、
  时间换算这些框架责任都甩给接入者，导致接入代码膨胀（见 v2 tested_assistant.py）。
- 新协议反客为主（内核提供），把「多源汇合、wall→mock 换算、task_id 配对、
  忙闲判定、快进拦截」全部收进框架 TurnMuxer，接入者只交：
    1. capabilities    —— 自报家门（能否打断/有没有异步工具/会不会主动说话）
    2. initial_sources —— 一个回合的初始原生事件源清单
    3. translate       —— 把单个原生事件翻译成统一事件（纯函数）
    4. on_result       —— 异步结果/到期提醒到达时，返回"接续回复"的新源
    5. apply_world_update —— 世界注入（推时间/车态），返回未来停靠点
    6. dump_history    —— 历史导出（供裁判回看）

彻底中立：本文件不 import 任何被测助手的实现，也不依赖旧 assistant_protocol。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable, Optional, Protocol, runtime_checkable


# ---------------- 能力声明 ----------------

@dataclass
class Capabilities:
    """被测助手的能力自报家门（取代旧协议的 hasattr 探测）。

    框架据此决定行为分支：
    - supports_barge_in：收到新用户输入（新 Turn）、上一个回合尚未耗尽时，
      助手会**自行中断**旧回合的底层生成流（对应旧协议 achat_stream 里
      self._active_reply.interrupt()）。注意：打断是助手的**能力**，不是框架
      动作——框架全程不主动 cancel 旧流，只在 initial_sources 被再次调用时
      把"新输入来了"这个事实自然暴露给助手，由助手自驱中断。
    - has_async_tools：工具是否异步返回（结果晚到、可能触发接续回复）
    - can_proactive_speak：是否会主动开口（定时提醒等，无用户输入）
    - needs_time_source：是否需要虚拟时钟取"当前时刻"
    """
    supports_barge_in: bool = False
    has_async_tools: bool = False
    can_proactive_speak: bool = False
    needs_time_source: bool = False


# ---------------- 环境（setup 注入） ----------------

@dataclass
class AdapterEnv:
    """create/setup 时框架注入的环境。

    - virtual_car：车控工具共享的虚拟车实例（改车态时直接操作它）
    - get_virtual_time：虚拟时钟取当前时刻（needs_time_source 时才注入）
    """
    session_id: str
    system_prompt: str = ""
    virtual_car: Any = None
    get_virtual_time: Optional[Callable[[], datetime]] = None


# ---------------- 回合（Turn） ----------------

class TurnKind(str, Enum):
    USER = "user"              # 用户说话
    PROACTIVE = "proactive"    # 主动话语（定时提醒到期等，无用户输入）


@dataclass
class Turn:
    """一次"从开口到彻底安静"的完整过程。

    - kind：USER（用户输入触发）/ PROACTIVE（主动话语触发）
    - text：USER 为用户文本；PROACTIVE 为触发缘由描述
    - at：该回合的虚拟起始时刻（框架盖，用于主动话语锚定时间区间）
    """
    kind: TurnKind
    text: str
    at: datetime


# ---------------- 统一事件 ----------------

class EventType(str, Enum):
    TEXT_DELTA = "text_delta"       # 流式文本增量
    TOOL_CALL = "tool_call"         # 工具调用开始
    TOOL_RESULT = "tool_result"     # 工具调用返回


@dataclass
class AssistantEvent:
    """接入者 translate 出的统一事件。

    时间戳只有 wall_time（真实墙钟）：接入者透传原生事件的 timestamp，
    无则 datetime.now()；mock 时间戳由框架 TurnMuxer 用 wall→mock 换算统一盖。
    """
    type: EventType
    wall_time: datetime
    # TEXT_DELTA
    delta: str = ""
    # TOOL_CALL / TOOL_RESULT
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: Any = None
    # 异步工具配对标识（并行同名工具靠它精确配对；同步工具传 None）
    task_id: Optional[str] = None


# ---------------- 世界更新 ----------------

@dataclass
class WorldUpdate:
    """框架推给助手的"外部世界发生了变化"。

    - car_info：车态变更（剧本 set_state 模拟的外部世界变化）
    - current_time：时间推进到的新虚拟时刻
    """
    car_info: Optional[dict[str, Any]] = None
    current_time: Optional[datetime] = None


# ---------------- 接入协议 ----------------

@runtime_checkable
class AssistantAdapter(Protocol):
    """被测助手接入协议（事件源适配器模式）。

    一个实现 = capabilities + setup + initial_sources + translate + on_result
    + apply_world_update + dump_history。除此之外框架全包。
    """

    @property
    def capabilities(self) -> Capabilities:
        """能力自报家门。"""
        ...

    def setup(self, env: AdapterEnv) -> None:
        """创建/重置会话，并接收虚拟车、虚拟时钟等环境引用。"""
        ...

    def initial_sources(self, turn: Turn) -> list[AsyncIterator[Any]]:
        """一个回合的初始原生事件源清单。

        每一条都是"往外冒碎片的线"（原生事件流）。框架 TurnMuxer 会：
        - 多路复用汇合成一条
        - 逐条调用 translate 翻译 + 盖 mock 戳
        - 逐条调用 on_result 判断是否要挂载"接续回复"的新源
        - 全部耗尽 → 回合自然结束（= 助手彻底安静）
        """
        ...

    def translate(self, raw: Any) -> Optional[AssistantEvent]:
        """把单个原生事件翻译成统一事件；无法/无需翻译时返回 None。

        纯函数，只做"土话翻译成平台普通话"，不关心时序、配对、快进。
        """
        ...

    def on_result(self, raw: Any) -> Optional[AsyncIterator[Any]]:
        """某个原生事件（异步工具结果 / 到期提醒）到达，是否要接续说一段？

        返回一个新的原生事件源（如底层 agent 用结果续接生成回复），
        None 表示不接续。这是"工具结果回来 → 助手接着往下说"的唯一落点。
        """
        ...

    async def apply_world_update(self, update: WorldUpdate) -> list[datetime]:
        """推入外部世界变化，返回"接下来应在哪些虚拟时刻停靠"。

        - 快进前用返回值插桩中间停靠点（如内部定时任务触发时刻）
        - 快进到停靠点时再调用一次 current_time，助手内部到期任务从而触发
        """
        ...

    def dump_history(self) -> list[dict[str, str]]:
        """导出对话历史，供裁判回看：[{"role": "user"/"assistant", "content": ...}]"""
        ...


# ---------------- 框架侧产物（SourcedEvent） ----------------

@dataclass
class SourcedEvent:
    """TurnMuxer 产出的、已盖 mock 戳的统一事件。

    上层（校验脚本 / 未来 runner）据此消费并复用 TraceRecorder 落盘。
    """
    mock_time: datetime          # 框架用 wall→mock 换算盖的虚拟时刻
    event: AssistantEvent        # 接入者翻译后的统一事件
    turn: Turn                   # 所属回合（区分普通/主动话语）


def is_adapter(obj: Any) -> bool:
    """检查对象是否实现 AssistantAdapter。"""
    return (
        isinstance(obj, AssistantAdapter)
        or (
            hasattr(obj, "capabilities")
            and hasattr(obj, "setup")
            and hasattr(obj, "initial_sources")
            and hasattr(obj, "translate")
            and hasattr(obj, "on_result")
            and hasattr(obj, "apply_world_update")
            and hasattr(obj, "dump_history")
        )
    )