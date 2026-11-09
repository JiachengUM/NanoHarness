from pydantic import BaseModel, Field

class PersonBasicInfo(BaseModel):
    '''非常基础的人的信息。与场景、应用等完全解耦'''
    name: str | None = Field(default=None, title="名字", description="名字")

    age: int | str | None = Field(default=None, title="年龄", description="年龄")
    
    gender: str | None = Field(default=None, title="性别", description="性别")

class UserBase(BaseModel):
    """用户。很难定义。先简单写。"""

    basic_info: PersonBasicInfo | str | None = Field(default=None, description="基础信息")
    '''通用信息，跟场景、应用等无关'''

    profile: list[str] | str | None = Field(default=None, description="用户画像")
    '''场景、应用、角色相关'''

    attributes: dict[str, str] | None = Field(default=None, title="其它用户属性", description="其它用户属性")
    '''为了灵活和通用性的任意属性'''
