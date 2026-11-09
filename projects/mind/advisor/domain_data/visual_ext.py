from pydantic import BaseModel, Field

class VisualExterior(BaseModel):
    """外部视觉信息"""

    weather: str | None = Field(default=None, title="天气状态", description="天气状态")
    road: str | None = Field(default=None, title="道路状态", description="道路状态")
    building: str | None = Field(default=None, title="建筑状态", description="建筑状态")
    traffic: str | None = Field(default=None, title="交通状态", description="交通状态")

    other_state: dict[str, str] | None = Field(default=None, title="其它状态", description="其它状态")
    '''上面未定义的属性，在这里动态添加'''
