from pydantic import BaseModel, Field, ConfigDict

from functools import cached_property

from volcenginesdkarkruntime.types.shared_params.thinking import Thinking

from typing_extensions import TypedDict, Literal

from aicore.models.credentials import get_client

from .core import AsyncArk

class Caching(TypedDict, total=False):
    """
    缓存用于避免重复计算，降低成本。
    type: 是否使用缓存。"enabled"表示使用缓存，"disabled"表示不使用缓存。
    prefix: 是否使用前缀缓存。true：仅创建公共前缀缓存，模型不回复。
    不可与 instructions 字段、tools（除自定义函数 Function Calling 外）字段一起使用。
    创建前缀缓存场景限制：Input tokens需要大于等于 256 tokens，否则会报错；stream参数不能设置为true。
    """
    type: Literal["enabled", "disabled"]

    prefix: bool | None

class ResponseParams(BaseModel):
    """
    控制大语言模型文本生成行为的运行时参数。
    
    仅包含与生成策略相关的参数，不包含：
    - 模型名称（由外部 str 表示）
    - 认证信息（api_key等）
    - 模型能力（由 ModelProfile 描述）
    - 工具定义（由 tools 列表传入）
    
    所有字段均可选。

    TODO: 目前内容很少。根据需要随时扩展。
    """

    temperature: float | None = None

    top_p: float | None = None

    thinking: Thinking | None = None

    caching: Caching | None = Caching(type="disabled") # 是否使用缓存

    store: bool | None = True  # 是否存储Response。为True时，会存储Response，方便后续查询。

    max_output_tokens: int | None = None  # 模型输出最大 token 数（Chat API：通过参数 max_completion_tokens 控制模型最大输出长度）


    instructions: str | None = None  # 模型指令
    """在模型上下文中插入系统消息或者开发者作为第一条指令。当与 previous_response_id 一起使用时，前一个回复中的指令不会被继承到下一个回复中。
    这样可以方便地在新的回复中替换系统（或开发者）消息。
    不可与缓存能力一起使用。配置了instructions 字段后，本轮请求无法写入缓存和使用缓存，表现为：
    caching 字段配置为 {"type":"enabled"} 时报错。
    传入带缓存的 previous_response_id 时，缓存输入（cached_tokens）为0。"""

    max_tool_calls: int | None = None  # 模型最大调用工具次数，实测不支持自定义工具,还没有验证火山内置的tool。
    """最大工具调用轮次（一轮里不限制次数）。在工具调用达到此限制次数后，提示模型停止更多工具调用并进行回答。
    注意：该参数为尽力而为（best effort）机制，不保证成功，最终调用次数会受模型推理效果、工具返回结果有效性等因素影响。"""


class ModelParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = Field(..., description="模型名称")
    params: ResponseParams = Field(default=ResponseParams(thinking = {"type": "disabled"}), description="模型参数")

    @cached_property
    def client(self) -> AsyncArk:
        """创建 AsyncArk 客户端。"""
        return get_client(AsyncArk)