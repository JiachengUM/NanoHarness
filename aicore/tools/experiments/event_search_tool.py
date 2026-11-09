"""
事件搜索工具，搜索一个时间区间内的所有事件
"""
from datetime import datetime
from typing import Callable, Awaitable

from pydantic import BaseModel, Field, field_validator, model_validator

from aicore.tools import TaskToolType, create_tool


class EventSearchToolInput(BaseModel):
    # 事件搜索工具输入参数
    
    # query: str | None = Field(default=None, description="用户的搜索查询语句（最多 4000 个字符）。如果提供 query，将基于查询内容进行语义匹配召回记忆，召回数量与 limit 值相关。如果不提供 query，将返回符合 filter 条件的记忆列表，按时间排序（优先最新），召回数量与 limit 值相关")
    
    start_time: str = Field(..., description="需要查询过往事件记录时你需要配置的的开始时间字符串，你必须传入符合格式要求的结束时间字符串，格式为：YYYY-MM-DD HH:MM:SS。")
    
    end_time: str = Field(..., description="需要查询过往事件记录时你需要配置的的结束时间字符串，你必须传入符合格式要求的结束时间字符串，格式为：YYYY-MM-DD HH:MM:SS。")

    # session_id: str | list[str] | None = Field(default=None, description="会话ID，用于过滤。支持单个ID或ID列表")

    limit: int = Field(default=10, le=5000, ge=1, description="需要查询过往事件记录时你需要配置的返回搜索结果数量。默认值为 10,允许范围 [1, 5000]")

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_datetime_format(cls, value: str) -> str:
        """校验日期时间字符串是否能按固定格式解析。"""
        try:
            datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise ValueError(
                f"时间格式{value}错误，请使用 YYYY-MM-DD HH:MM:SS"
            ) from exc
        return value

    @model_validator(mode="after")
    def validate_time_range(self) -> "EventSearchToolInput":
        """校验时间区间，确保开始时间不晚于结束时间。"""
        start_dt = datetime.strptime(self.start_time, "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(self.end_time, "%Y-%m-%d %H:%M:%S")
        if start_dt > end_dt:
            raise ValueError(f"时间区间错误：start_time {self.start_time} 不能晚于 end_time {self.end_time}")
        return self

    # time_decay_weight: float | None = Field(default=None, description="时间衰减权重，范围 [0, 1)，默认不传不衰减")

    # no_decay_period: int | None = Field(default=None, description="无衰减时间周期，单位为秒。默认值为 0，即不开启无衰减时间周期")

    # custom_weight: float | None = Field(default=None, description="自定义权重，范围 [0, 1)")
MemoryContentType = str | list[str] | int | list[int] | float | bool | None

class EventItem(BaseModel):
    """事件记忆检索结果列表元素"""
    id: str = Field(..., description="记忆条目（事件或画像实例）的唯一ID。")
    score: float | None = Field(default=None, description="记忆匹配度分数，范围 [0, 1]。如果 query 为空，该字段为空")
    memory_type: str = Field(..., description="记忆类型。")
    user_id: list[str] = Field(..., description="用户ID列表。")
    assistant_id: list[str] = Field(..., description="助手ID列表。")
    group_id: str | None = Field(default=None, description="群组ID，可能为空。")
    time: int = Field(..., description="记忆时间，毫秒时间戳。")
    status: str | None = Field(default=None, description="记忆状态，可能为空")
    labels: str | None = Field(default=None, description="记忆标签，可能为空")
    memory_info: dict[str, MemoryContentType] = Field(..., description="额外的详细信息。其结构取决于memory_type。")
    session_id: str = Field(..., description="会话ID。")
    origin_score: float | None = Field(default=None, description="原始的向量检索分数。当提供了 time_decay_config 或 custom_weight 时返回。")
    time_score: float | None = Field(default=None, description="时间衰减分数。当提供了 time_decay_config 时返回。")
    custom_weight_score: float | None = Field(default=None, description="自定义权重分数。当提供了 custom_weight 时返回。")


class EventSearchToolOutput(BaseModel):
    """事件搜索工具输出参数"""
    
    events: list[EventItem] = Field(..., description="事件记忆结果列表")
    messages: str | None = Field(default=None, description="报错信息以及提示信息。")


EventSearchToolOutputLike = EventSearchToolOutput | str

EventSearchWorker = Callable[..., Awaitable[EventSearchToolOutputLike]]

def event_search_tool(worker: EventSearchWorker) -> TaskToolType[EventSearchToolInput, EventSearchToolOutputLike, None, ...]:
    """事件搜索工具"""
    
    return create_tool(
        name="事件记录搜索工具",
        description="搜索一个时间区间内的事件记录。当你需要得知过往用户某些",
        args_schema=EventSearchToolInput,
        worker=worker,
    )
