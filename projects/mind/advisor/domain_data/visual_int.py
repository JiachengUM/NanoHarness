from pydantic import BaseModel, Field

class PersonState(BaseModel):
    """人员状态"""
    position: str | None = Field(default=None, title="位置", description="位置")
    sex: str | None = Field(default=None, title="性别", description="性别")
    age: str | None = Field(default=None, title="年龄", description="年龄")
    expression: str | None = Field(default=None, title="表情", description="表情")
    seat_belt_status: str | None = Field(default=None, title="安全带状态", description="是否系好安全带")
    appearance: dict[str, str] | str | None = Field(default=None, title="外观", description="外观")
    clothes: dict[str, str] | str | None = Field(default=None, title="衣服", description="衣服")
    accessories: list[str] | str | None = Field(default=None, title="配饰", description="配饰")
    action: list[str] | str | None = Field(
        default=None, title="动作", description="动作"
    )

class InteriorScene(BaseModel):
    '''单个cameran看到的场景描述'''

    persons: list[PersonState] | str | None = Field(default=None, title="人员情况", description="人员情况")

    """车内物品"""
    child_seat: dict[str, str] | str | None = Field(default=None, title="儿童座椅", description="儿童座椅")
    
    pet: dict[str, str] | str | None = Field(default=None, title="宠物", description="宠物")


class VisualInterior(BaseModel):
    """内部视觉信息"""
    
    scenes: dict[str, InteriorScene] | str | None = Field(default=None, title="场景描述", description="场景描述")
    '''key: camera id, value: camera看到的场景描述'''

    other_state: dict[str, str] | None = Field(default=None, title="其它状态", description="其它状态")
    '''上面未定义的属性，在这里动态添加'''
