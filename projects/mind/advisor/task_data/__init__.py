from pydantic import BaseModel, Field, field_validator

from nanoai.model.config import ModelName

from projects.mind.advisor.domain_data import (
    UserBase, 
    EpisodicMemory,
    VehicleState, 
    VisualExterior, 
    VisualInterior,
    EventBase, 
    WorldInfo,
    )

__all__ = [
    "AdvisorContext",
    "AdvisorInput",
    "AdvisorDatasetMeta",
]


class AdvisorContext(BaseModel):
    '''
    advisor的工作环境上下文
    '''
    user: str | UserBase | None = Field(default=None, title="用户画像", description="用户画像")

    memory: str | EpisodicMemory | None = Field(default=None, title="记忆", description="记忆")
    
    vehicle_state: str | VehicleState | None = Field(default=None, title="车辆状态", description="车辆状态")
    
    visual_exterior: str | VisualExterior | None = Field(default=None, title="外部视觉信息", description="外部视觉信息")
    
    visual_interior: str | VisualInterior | None = Field(default=None, title="内部视觉信息", description="内部视觉信息")
    
    world_info: str | WorldInfo | None = Field(default=None, title="世界信息", description="世界信息")


class AdvisorInput(BaseModel):
    '''
    advisor的输入
    '''
    event: EventBase | str = Field(...,  title="事件", description="事件")

    context: AdvisorContext | str = Field(..., title="工作环境上下文", description="工作环境上下文")

class AdvisorDatasetMeta(BaseModel):
    '''
    advisor的输入数据集
    '''
    name : str = Field(..., title="数据集名称", description="数据集名称")

    description: str | None = Field(default=None, title="数据集描述", description="数据集描述")


class AdvisorParam(BaseModel):
    model: str = Field(default=ModelName.DOUBAO_SEED_1_6_251015, title="模型名称", description="模型名称")
    # TODO: 这里的缺省值不确定是否合理
    
    sys_prompt: str | None = Field(default=None, title="系统提示", description="系统提示")
    '''允许通过外部输入来控制系统提示词。'''

    user_prompt: str | None = Field(default=None, title="用户提示", description="用户提示。必须包括事件(event)和上下文信息(context)这两个参数。")
    '''允许通过外部输入来控制用户提示词。必须是一个格式化字符串，包含{event}和{context}这两个参数。'''


    @field_validator('user_prompt')
    @classmethod
    def validate_user_prompt(cls, v: str | None) -> str | None:
        if v is not None:
            if '{event}' not in v:
                raise ValueError('user_prompt must contain {event} placeholder')
            if '{context}' not in v:
                raise ValueError('user_prompt must contain {context} placeholder')
        return v


class AdviserOutput(BaseModel):
    advice: str | None = Field(default=None, title="建议", description="具体建议")
    think: str | None = Field(default=None, title="思考过程", description="思考过程")
    reason: str | None = Field(default=None, title="原因", description="原因")

    @staticmethod
    def model_output_prompt() -> str:
        """用于提示语言模型输出该类型对象时的prompt。"""

        return """请以JSON格式返回你的具体建议(advice)和思考过程(think)。请用中文。"""


class AdvisorRunResult(BaseModel):
    '''
    执行过程中的内部数据，不是结果的一部分。
    用于分析、归因、调试、改进等。
    '''
    
    sys_prompt: str = Field(..., title="系统提示", description="系统提示")
    user_prompt: str = Field(..., title="用户提示", description="用户提示")
