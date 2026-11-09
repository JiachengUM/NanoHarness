from typing import Any, Dict,Optional
from typing_extensions import TypedDict, Annotated
from pydantic import BaseModel,Field

# 定义动作结构化信息
class Action(BaseModel):
    reflection: Any = Field(default=None, description="反思内容")
    thought: str = Field(description="思考过程")
    action_type: str = Field(description="操作类型")
    action_inputs: dict[str, Any] = Field(description="操作输入参数，结构可变")
    text: str = Field(description="模型原始输出")

# 现阶段端侧接受的Action信息结构
class ActionInfoClient(BaseModel):
    pass
class OverallState(BaseModel):
    previous_thought: str | None = Field(None, description="上一步为止的信息，内容包括用户反馈（可选，在上一步动作为反问时会有），至今为止任务进行情况，希望下一步进行什么动作，用于指导下一步动作输出，总是会包括着一个写死的完整订座行动规划")
    history: list | None = Field(None, description="对话记录")
    next_thought: str | None = Field(None, description="根据上一步为止的思考得出的新的思考")
    view_image_url: str | None = Field(None, description="当前视野")
    image_cache_path: str | None = Field(None, description="当前视野动作渲染图的缓存路径")
    encoded_image: str | None = Field(None, description="当前视野的base64编码")
    image_type: str | None = Field(None, description="当前视野的图片类型")
    next_action: Action | None = Field(None, description="动作结构化信息")
    decision: str | None = Field(None, description="下一步动作的业务名称")
    need_reflection: bool | None = Field(None, description="是否需要反思")
    store_reflection_result: bool | None = Field(None, description="是否存储反思结果,如果选择，则存储previous_thought，对应的view_image_url，动作渲染图片，模型反思判断正确与否的结果,只在反思打开时有效")
    reflection_result: str | None = Field(None, description="反思结果")
    reflection_advice: str | None = Field(None, description="反思建议")
    trace_id: str|int|None = Field(None, description="当前对话的唯一标识")
    main_prompt: str | None = Field(None, description="主提示词")
# 定义智能体输入接口
class AgentInputRequest(BaseModel):
    trace_id: str|int|None = Field(default=None, description="唯一标识一次会话的ID")
    previous_thought: str = Field(description="上一步为止的思考过程,如果未传入或为空，则可以测试无上一步为止思考时的效果")
    history: list = Field(description="和用户的聊天历史")
    view_image_url: str = Field(description="当前视野")
    need_reflection: bool = Field(default=False, description="是否打开所有节点的模型反思能力，可能可以提升正确率，但会有额外的计算成本")
    store_reflection_result: bool = Field(description="是否存储反思结果")

# 定义智能体输出接口
class AgentOutputResponse(BaseModel):
    trace_id: str|int|None = Field(description="当前对话的唯一标识")
    next_thought: str = Field(description="新的思考,用于指引之后的动作判断") # 端侧应直接引用并作为previous_thought在预测下一步动作前传回来
    next_action: Action = Field(description="动作结构化信息")
    reflection_result: str | None = Field(None, description="反思结果")
    reflection_advice: str | None = Field(None, description="反思建议")
    history: list | None = Field(None, description="对话记录")
    main_prompt: str | None = Field(None, description="主提示词")