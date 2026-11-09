from typing import Annotated
from pydantic import BaseModel, Field, SerializeAsAny, ConfigDict

class BaseTool(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)  # 也不影响类型的正确

    name: str = "base"

class DerivedTool(BaseTool):
    extra_field: str = "特有字段"


class Base[T: BaseTool](BaseModel):
    # 既保留类型，又禁止 dump
    #tool: list[Annotated[T, SerializeAsAny()]] = Field(exclude=True)
    tool: list[T] = Field(exclude=True)   # 这样写类型也是对的！SerializeAsAny没有作用。

class Derived(Base[DerivedTool]):
    pass

def test_pydantic_serialize_as_any():

    # 传入实例对象
    c = Derived(tool=[DerivedTool(extra_field="特有数据")])

    # 1. 验证类型是否保留
    print(type(c.tool[0]))  
    # 输出: <class '__main__.DerivedTool'> (完美！类型没有降级)

    # 2. 验证是否被 dump
    print(c.model_dump())
    # 输出: {} (完美！tool 字段被彻底排除，不会触发不可 dump 的报错)

if __name__ == "__main__":
    test_pydantic_serialize_as_any()