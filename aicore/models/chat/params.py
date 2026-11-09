from pydantic import BaseModel

from volcenginesdkarkruntime.types.chat.completion_create_params import Thinking

class ChatParams(BaseModel):
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
