from datetime import datetime
from enum import StrEnum, Enum
from typing import List, Optional, Union, Dict, Any

from pydantic import BaseModel, Field


# 定义枚举
class Status(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"

class Color(Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"

# 定义嵌套的BaseModel
class Address(BaseModel):
    street: str = Field(description="街道地址")
    city: str = Field(description="城市")
    zip_code: str = Field(description="邮政编码")

# 主模型
class User(BaseModel):
    name: str = Field(description="用户名")
    age: Optional[int] = Field(None, description="年龄")
    status: Status = Field(description="用户状态")
    favorite_colors: List[Color] = Field(default_factory=list, description="喜欢的颜色")
    address: Address = Field(description="地址信息")
    created_at: datetime = Field(description="创建时间")
    tags: List[str] = Field(default_factory=list, description="标签")


# 定义动作项模型
class ActionItem(BaseModel):
    """动作项"""
    action: str = Field(
        ...,
        description="要执行的具体动作",
        min_length=1,
        max_length=200,
        examples=["调温至22°C", "开启空气净化"]
    )

    reasoning: str = Field(
        ...,
        description="执行动作的原因和逻辑说明",
        min_length=1,
        max_length=1000,
        examples=["将车内温度降至22°C以增强凉爽感"]
    )

    priority: Optional[int] = Field(
        default=2,
        ge=1,
        le=5,
        description="动作优先级，1-5，1为最高"
    )

    parameters: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="动作参数"
    )


# 舒适建议模型
class ComfortAdviceOutput(BaseModel):
    """舒适建议输出"""
    model_config = {
        'populate_by_name': True
    }

    current_issue: str = Field(
        default="",
        alias="当前的舒适性问题",
        description="当前存在的舒适性问题描述"
    )

    suggestion: List[ActionItem] = Field(
        default_factory=list,
        alias="应对建议",
        description="针对舒适性问题的建议措施列表"
    )

    severity: Optional[str] = Field(
        default="medium",
        alias="问题严重程度",
        description="问题严重程度: low/medium/high/critical"
    )

    timestamp: datetime = Field(
        default_factory=datetime.now,
        alias="生成时间",
        description="建议生成时间戳"
    )

    # 实用方法
    def to_json_string(self, **kwargs) -> str:
        """转换为JSON字符串"""
        return self.model_dump_json(by_alias=True, **kwargs)

    def to_legacy_format(self) -> Dict[str, Union[str, List[Dict[str, str]]]]:
        """转换为旧格式（兼容原有结构）"""
        return {
            "current_issue": self.current_issue,
            "suggestion": [
                {
                    "action": item.action,
                    "reasoning": item.reasoning
                }
                for item in self.suggestion
            ]
        }

    def get_high_priority_actions(self, min_priority: int = 2) -> List[ActionItem]:
        """获取高优先级动作"""
        return [item for item in self.suggestion if item.priority and item.priority <= min_priority]

    def has_suggestions(self) -> bool:
        """是否有建议"""
        return len(self.suggestion) > 0

    def summary(self) -> Dict[str, Any]:
        """生成摘要"""
        return {
            "issue": self.current_issue,
            "suggestion_count": len(self.suggestion),
            "high_priority_count": len(self.get_high_priority_actions(min_priority=2)),
            "severity": self.severity,
            "confidence": self.confidence
        }

# 智能座舱舒适场景枚举
class ComfortScenario(StrEnum):
    """智能座舱舒适场景枚举"""
    TemperatureControl = "温度调节场景"
    SeatAdjustment = "座椅调节场景"
    LightingScene = "灯光场景"
    AudioControl = "音频控制场景"
    AirQuality = "空气质量场景"
    MultiMode = "多模式组合场景"

# QAList 对话数据模型
class QAItem(BaseModel):
    """单轮对话数据模型"""
    question: str = Field(..., description="用户问题")
    answer: str = Field(..., description="系统回答")
    think: Optional[str] = Field(default=None, description="思考过程")

class QAList(BaseModel):
    """对话列表数据模型"""
    qa_list: List[QAItem] = Field(..., description="对话列表")

# 车控场景描述模型
class VehicleControlScene(BaseModel):
    """车控场景描述模型"""
    scenario_type: ComfortScenario = Field(..., description="场景类型")
    parameters: dict = Field(..., description="场景参数", examples=[{"temperature": 22, "mode": "auto"}])
    description: str = Field(..., description="场景描述")
    target_role: Optional[str] = Field(default=None, description="目标角色")

# 车内角色设定模型
class InCarRole(BaseModel):
    """车内角色设定模型"""
    name: str = Field(..., description="角色名称")
    type: str = Field(..., description="角色类型", examples=["驾驶员", "乘客", "儿童", "老人"])
    preferences: Optional[dict] = Field(default=None, description="角色偏好", examples=[{"temperature": "warm", "seat": "reclined"}])
    status: Optional[dict] = Field(default=None, description="角色状态", examples=[{"fatigue": "medium", "mood": "relaxed"}])


    def update(self, other: Union['InCarRole', BaseModel, Dict[str, Any]]) -> 'InCarRole':
        """
        用其他模型或字典更新当前实例
        使用方式: A.update(B) 或 A.update(dict)
        """
        # 处理不同类型输入
        if isinstance(other, BaseModel):
            other_data = other.model_dump(exclude_unset=True)
        elif isinstance(other, dict):
            other_data = other

        # 筛选当前模型存在的字段
        updates = {k: v for k, v in other_data.items() if k in self.model_fields}

        # 返回更新后的新实例
        return self.model_copy(update=updates)

