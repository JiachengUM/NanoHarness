from re import L
from pydantic import BaseModel, Field

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

    personality: str = Field(default="未知", description="角色性格特点", examples=["开朗", "内向", "严谨"])
    background: str = Field(
        default = "未知", description="角色背景故事", examples=["从小在农村长大", "城市知识分子家庭", "海外留学归来"]
    )
    skills: list[str] = Field(
        default_factory=list,
        description="角色技能列表",
        examples=[["编程", "设计"], ["医疗", "护理"], ["教学", "研究"]],
    )
    level: int = Field(default=1, ge=1, le=100, description="角色等级", examples=[1, 10, 50])
    experience: int = Field(default=0, ge=0, description="角色经验值", examples=[0, 1000, 5000])
    health: int = Field(default=100, ge=0, le=100, description="角色健康值", examples=[100, 80, 50])