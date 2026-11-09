"""类型注册表测试模块"""

import pytest

from aicore.utils.nl_repr.base import NLReprError, register, _type_registry
from aicore.utils.nl_repr.core import nl_repr, nl_repr_safe

def test_type_registry():
    """测试类型注册表功能"""

    # 1. 正常注册和使用
    class CustomType:
        def __init__(self, value):
            self.value = value

    @register(CustomType)
    def custom_handler(obj: CustomType, **kwargs) -> str:
        return f"Custom: {obj.value}"

    obj = CustomType("test")
    assert nl_repr(obj) == "Custom: test"

    # 2. 验证kwargs传递
    @register(CustomType)
    def custom_handler_with_kwargs(obj: CustomType, **kwargs) -> str:
        style = kwargs.get("style", "default")
        return f"Custom({style}): {obj.value}"

    assert nl_repr(obj, style="fancy") == "Custom(fancy): test"

    # 3. 测试非callable handler
    # 注意：装饰器会自动调用函数，所以这里需要直接设置注册表
    # 使用类型忽略来绕过类型检查
    _type_registry[CustomType] = "not_callable"  # type: ignore
    with pytest.raises(NLReprError) as exc_info:
        nl_repr(obj)
    assert "registered handler must be callable" in str(exc_info.value)

    # 4. 清理注册表，避免影响后续测试
    if CustomType in _type_registry:
        del _type_registry[CustomType]

    # 5. 测试handler内部异常直接抛出
    @register(CustomType)
    def exception_handler(obj: CustomType, **kwargs) -> str:
        raise ValueError("handler error")

    with pytest.raises(ValueError):
        nl_repr(obj)

    # 6. 测试精确类型匹配
    class SubType(CustomType):
        pass

    sub_obj = SubType("sub")
    # 应该抛出NLReprError，因为SubType没有注册
    with pytest.raises(NLReprError):
        nl_repr(sub_obj)
    # 兜底返回str(x)
    assert nl_repr_safe(sub_obj) == str(sub_obj)


def test_type_registry_multiple_types():
    """测试注册多个类型"""
    class TypeA:
        def __init__(self, value):
            self.value = value

    class TypeB:
        def __init__(self, value):
            self.value = value

    class TypeC:
        def __init__(self, value):
            self.value = value

    @register(TypeA)
    def handler_a(obj: TypeA, **kwargs) -> str:
        return f"TypeA: {obj.value}"

    @register(TypeB)
    def handler_b(obj: TypeB, **kwargs) -> str:
        return f"TypeB: {obj.value}"

    @register(TypeC)
    def handler_c(obj: TypeC, **kwargs) -> str:
        return f"TypeC: {obj.value}"

    assert nl_repr(TypeA("a")) == "TypeA: a"
    assert nl_repr(TypeB("b")) == "TypeB: b"
    assert nl_repr(TypeC("c")) == "TypeC: c"


def test_type_registry_override():
    """测试覆盖已注册的类型"""
    class MyType:
        def __init__(self, value):
            self.value = value

    @register(MyType)
    def handler_v1(obj: MyType, **kwargs) -> str:
        return f"V1: {obj.value}"

    @register(MyType)
    def handler_v2(obj: MyType, **kwargs) -> str:
        return f"V2: {obj.value}"

    obj = MyType("test")
    # 后注册的handler应该覆盖先注册的
    assert nl_repr(obj) == "V2: test"


def test_type_registry_with_nested():
    """测试类型注册表处理嵌套结构"""
    class CustomType:
        def __init__(self, value):
            self.value = value

    @register(CustomType)
    def custom_handler(obj: CustomType, **kwargs) -> str:
        return f"Custom: {obj.value}"

    # 列表中的自定义类型
    lst = [CustomType("a"), CustomType("b"), CustomType("c")]
    result = nl_repr(lst)
    assert "Custom: a" in result
    assert "Custom: b" in result
    assert "Custom: c" in result

    # 字典中的自定义类型
    dct = {"key1": CustomType("x"), "key2": CustomType("y")}
    result = nl_repr(dct)
    assert "Custom: x" in result
    assert "Custom: y" in result


def test_type_registry_cleanup():
    """测试清理类型注册表"""
    class TempType:
        def __init__(self, value):
            self.value = value

    @register(TempType)
    def temp_handler(obj: TempType, **kwargs) -> str:
        return f"Temp: {obj.value}"

    obj = TempType("test")
    assert nl_repr(obj) == "Temp: test"

    # 清理注册表
    del _type_registry[TempType]

    # 清理后应该抛出NLReprError
    with pytest.raises(NLReprError):
        nl_repr(obj)


def test_type_registry_with_kwargs():
    """测试类型注册表处理器接收kwargs"""
    class ParametricType:
        def __init__(self, value):
            self.value = value

    @register(ParametricType)
    def parametric_handler(obj: ParametricType, **kwargs) -> str:
        prefix = kwargs.get("prefix", "")
        suffix = kwargs.get("suffix", "")
        return f"{prefix}{obj.value}{suffix}"

    obj = ParametricType("test")
    assert nl_repr(obj) == "test"
    assert nl_repr(obj, prefix="[") == "[test"
    assert nl_repr(obj, suffix="]") == "test]"
    assert nl_repr(obj, prefix="[", suffix="]") == "[test]"


RUN_PYTEST = True

def main():
    pass

if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        # 使用 -v 参数显示详细输出
        pytest.main(["-vs", __file__])
    else:
        # 可以这么写，是不报错的。
        # f"no format".format(arg = 1)
        main()