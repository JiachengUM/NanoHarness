"""继承优先级测试模块"""

import pytest
from pydantic import BaseModel, Field

from aicore.utils.nl_repr import nl_repr_base_model, _nl_repr_list, nl_repr, register


def test_inheritance_priority_list():
    """测试继承list的类，__nl_repr__协议优先级高于内置list处理"""

    class CustomList(list):
        def __nl_repr__(self, **kwargs) -> str:
            # 复用内置list处理，添加前缀
            base_result = _nl_repr_list(self, nl_repr, **kwargs)
            return f"CustomList: {base_result}"

    custom_lst = CustomList([1, 2, 3])

    # 验证前缀和底层逻辑都正确
    result = nl_repr(custom_lst)
    assert result.startswith("CustomList: ")
    assert "1. 1" in result
    assert "2. 2" in result
    assert "3. 3" in result


def test_inheritance_priority_base_model():
    """测试继承BaseModel的类，__nl_repr__协议优先级高于内置BaseModel处理"""
    class CustomModel(BaseModel):
        name: str = Field(title="用户姓名")
        age: int = Field(title="用户年龄")

        def __nl_repr__(self, **kwargs) -> str:
            # 复用内置BaseModel处理，添加前缀
            base_result = nl_repr_base_model(self, nl_repr)
            return f"CustomModel: {base_result}"

    custom_model = CustomModel(name="张三", age=25)

    # 验证前缀和底层逻辑都正确
    result = nl_repr(custom_model)
    assert result.startswith("CustomModel: ")
    assert "用户姓名: 张三" in result
    assert "用户年龄: 25" in result


def test_inheritance_vs_registry_priority():
    """测试继承类的__nl_repr__协议优先级高于类型注册表"""

    class CustomList(list):
        def __nl_repr__(self, **kwargs) -> str:
            base_result = _nl_repr_list(self, nl_repr, **kwargs)
            return f"Protocol: {base_result}"

    # 注册类型处理器
    @register(CustomList)
    def registry_handler(obj: CustomList, **kwargs) -> str:
        return f"Registry: {len(obj)} items"

    custom_lst = CustomList([1, 2, 3])

    # __nl_repr__ 协议应该优先于类型注册表
    result = nl_repr(custom_lst)
    assert result.startswith("Protocol: ")
    assert "1. 1" in result
    assert result != "Registry: 3 items"


def test_inheritance_protocol_vs_builtin():
    """测试__nl_repr__协议优先级高于内置处理"""
    class CustomStr(str):
        def __nl_repr__(self, **kwargs) -> str:
            return f"CustomStr: {self}"

    custom_str = CustomStr("hello")
    result = nl_repr(custom_str)
    assert result == "CustomStr: hello"
    assert result != "hello"


def test_inheritance_with_nested():
    """测试继承类的嵌套处理"""
    class CustomList(list):
        def __nl_repr__(self, **kwargs) -> str:
            return f"Custom: {len(self)} items"

    # 嵌套自定义列表
    nested = [CustomList([1, 2]), CustomList([3, 4, 5])]
    result = nl_repr(nested)
    assert "Custom: 2 items" in result
    assert "Custom: 3 items" in result

    # 自定义列表在字典中
    dct = {"list1": CustomList([1, 2]), "list2": CustomList([3, 4])}
    result = nl_repr(dct)
    assert "Custom: 2 items" in result


def test_inheritance_base_model_with_protocol():
    """测试BaseModel子类实现__nl_repr__协议"""
    class User(BaseModel):
        name: str = Field(title="用户姓名")
        age: int = Field(title="用户年龄")

        def __nl_repr__(self, **kwargs) -> str:
            style = kwargs.get("style", "default")
            if style == "brief":
                return f"{self.name}({self.age})"
            elif style == "formal":
                return f"姓名：{self.name}，年龄：{self.age}岁"
            else:
                return f"用户{self.name}，年龄{self.age}岁"

    user = User(name="张三", age=25)

    # 默认样式
    assert nl_repr(user) == "用户张三，年龄25岁"

    # 简洁样式
    assert nl_repr(user, style="brief") == "张三(25)"

    # 正式样式
    assert nl_repr(user, style="formal") == "姓名：张三，年龄：25岁"


def test_inheritance_multiple_levels():
    """测试多级继承的优先级"""
    class Base:
        def __nl_repr__(self, **kwargs) -> str:
            return "Base"

    class Middle(Base):
        def __nl_repr__(self, **kwargs) -> str:
            return "Middle"

    class Derived(Middle):
        def __nl_repr__(self, **kwargs) -> str:
            return "Derived"

    derived = Derived()
    # 应该使用最底层的__nl_repr__实现
    assert nl_repr(derived) == "Derived"


def test_inheritance_no_protocol():
    """测试没有__nl_repr__协议的继承类使用内置处理"""
    class CustomList(list):
        pass

    custom_lst = CustomList([1, 2, 3])
    # 应该使用内置list处理
    result = nl_repr(custom_lst)
    assert "1. 1" in result
    assert "2. 2" in result
    assert "3. 3" in result


def test_inheritance_with_registry_and_protocol():
    """测试同时有类型注册表和__nl_repr__协议时的优先级"""
    class CustomType:
        def __init__(self, value):
            self.value = value

        def __nl_repr__(self, **kwargs) -> str:
            return f"Protocol: {self.value}"

    # 注册类型处理器
    @register(CustomType)
    def registry_handler(obj: CustomType, **kwargs) -> str:
        return f"Registry: {obj.value}"

    obj = CustomType("test")
    # __nl_repr__ 协议应该优先于类型注册表
    assert nl_repr(obj) == "Protocol: test"
    assert nl_repr(obj) != "Registry: test"
