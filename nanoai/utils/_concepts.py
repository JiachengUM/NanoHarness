import dataclasses
from dataclasses import field
from typing import List, NotRequired, Optional, TypedDict, Union

from pydantic import BaseModel, Field


class Product(BaseModel):
    """商品模型"""

    name: str = Field(..., description="商品名称", examples=["苹果", "香蕉", "橙子"])
    price: float = Field(..., ge=0, description="商品价格", examples=[1.99, 2.5, 3.0])
    quantity: int = Field(..., ge=0, description="商品数量", examples=[10, 20, 30])
    discount: float = Field(0.0, ge=0, le=1.0, description="商品折扣", examples=[0.1, 0.2, 0.5])
    category: Optional[str] = Field(None, description="商品类别", examples=["水果", "电子产品", "日用品"])
    in_stock: Optional[bool] = Field(True, description="是否有库存", examples=[True, False])


class PersonBasicInfo(BaseModel):
    """
    PersonBasicInfo这个概念表示人的基本信息，包括个人身份、性别、年龄等。
    """

    name: str = Field(default="", description="全名。")
    gender: str = Field(default="", description="性别，如男、女或其他。")
    age: int = Field(default=0, description="当前年龄。")
    date_of_birth: str = Field(default="", description="出生日期。")
    id_number: str = Field(default="", description="身份证号码。")
    contact_info: str = Field(default="", description="联系电话或电子邮箱等联系方式。")
    marital_status: str = Field(default="", description="婚姻状况，如未婚、已婚、离异等。")
    occupation: str = Field(default="", description="角色职业", examples=["工程师", "医生", "教师"])
    education_level: str = Field("", description="教育程度。")


class Character(PersonBasicInfo):
    """角色模型，用于生成游戏或者小说中的角色"""

    personality: str = Field("未知", description="角色性格特点", examples=["开朗", "内向", "严谨"])
    background: str = Field(
        "未知", description="角色背景故事", examples=["从小在农村长大", "城市知识分子家庭", "海外留学归来"]
    )
    skills: List[str] = Field(
        default_factory=list,
        description="角色技能列表",
        examples=[["编程", "设计"], ["医疗", "护理"], ["教学", "研究"]],
    )
    level: int = Field(1, ge=1, le=100, description="角色等级", examples=[1, 10, 50])
    experience: Union[int, None] = Field(0, ge=0, description="角色经验值", examples=[0, 1000, 5000])
    health: Optional[int] = Field(100, ge=0, le=100, description="角色健康值", examples=[100, 80, 50])


# TypedDict版本的Character
class CharacterDict(TypedDict):
    """角色模型 (TypedDict)"""

    name: str  # 角色名称
    age: int  # 角色年龄
    sex: str  # 角色性别
    occupation: str  # 角色职业
    personality: str  # 角色性格特点
    background: str  # 角色背景故事
    skills: List[str]  # 角色技能列表
    level: NotRequired[int]  # 角色等级
    experience: NotRequired[Union[int, None]]  # 角色经验值
    health: NotRequired[Optional[int]]  # 角色健康值


# dataclass版本的Character
@dataclasses.dataclass
class CharacterData:
    """角色模型 (dataclass)"""

    name: str  # 角色名称
    age: int  # 角色年龄
    sex: str  # 角色性别
    occupation: str  # 角色职业
    personality: str  # 角色性格特点
    background: str  # 角色背景故事
    skills: List[str] = field(default_factory=list)  # 角色技能列表
    level: int = 1  # 角色等级
    experience: Union[int, None] = 0  # 角色经验值
    health: Optional[int] = None  # 角色健康值
