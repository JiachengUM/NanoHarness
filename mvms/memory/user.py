"""用户画像模型。这是mvms的核心数据结构。会贯穿整个项目。"""

from pydantic import BaseModel, Field

class UserProfile(BaseModel):
    """用户画像模型。
    为了方便和灵活性，所有字段类型都为str。缺省值都为"未知"。
    """

    name: str = Field(default="未知", description="用户姓名")
    age: str = Field(default="未知", description="用户年龄")
    gender: str = Field(default="未知", description="用户性别")
    occupation: str = Field(default="未知", description="职业")
    education: str = Field(default="未知", description="教育背景")
    location: str = Field(default="未知", description="居住地")
    interests: str = Field(default="未知", description="兴趣爱好")
    personality: str = Field(default="未知", description="性格特点")
    communication_style: str = Field(default="未知", description="沟通风格")
    lifestyle: str = Field(default="未知", description="生活方式")


# 仅用于最基本的测试
EXAMPLE_USERS: list[UserProfile] = [
    UserProfile(
        name="李小明",
        age="30",
        gender="男",
        occupation="程序员",
        education="硕士",
        location="北京",
        interests="篮球",
        personality="开朗",
        communication_style="幽默",
        lifestyle="宅男"),
    
    UserProfile(
        name="张小红",
        age="25",
        gender="女",
        occupation="教师",
        education="硕士",
        location="上海",
        interests="阅读",
        personality="内向",
        communication_style="严谨",
        lifestyle="白领"),
]
