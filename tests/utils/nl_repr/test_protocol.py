"""__nl_repr__协议测试模块"""

import pytest

from aicore.utils.nl_repr import NLReprError, nl_repr


# 对象类型测试用例拆分
object_normal_cases = [
    ("desc", "desc"),
    ("desc2", "desc2"),
]


@pytest.mark.parametrize("desc, expected", object_normal_cases)
def test_object_normal_cases(desc, expected):
    if desc == "desc2":

        class ObjMethod:
            def __init__(self, desc):
                self._desc = desc

            def __nl_repr__(self, **kwargs):
                return self._desc

        assert nl_repr(ObjMethod(desc)) == expected
    else:

        class Obj:
            def __init__(self, desc):
                self._desc = desc

            def __nl_repr__(self, **kwargs):
                return self._desc

        assert nl_repr(Obj(desc)) == expected


object_error_cases = [
    (123, r"__nl_repr__.*必须返回str"),
    (None, r"对于类型.*NoDesc.*未实现nl_repr"),
]


@pytest.mark.parametrize("desc, expected_exc", object_error_cases)
def test_object_error_cases(desc, expected_exc):
    with pytest.raises(Exception) as exc_info:
        if desc == 123:

            class BadObj:
                def __nl_repr__(self, **kwargs):
                    return desc

            nl_repr(BadObj())
        elif desc is None:

            class NoDesc:
                pass

            nl_repr(NoDesc())
    print("实际异常消息:", str(exc_info.value))
    import re

    # 允许异常信息前缀有nl_repr转换失败等内容
    assert re.search(expected_exc, str(exc_info.value)), f"异常信息不匹配: {str(exc_info.value)}"


# __nl_repr__协议验证测试用例
nl_repr_protocol_error_cases = [
    ("not_callable", NLReprError, r"__nl_repr__ must be callable"),
    (123, NLReprError, r"__nl_repr__ must be callable"),
    (None, NLReprError, r"__nl_repr__ must be callable"),
    ([], NLReprError, r"__nl_repr__ must be callable"),
]


@pytest.mark.parametrize("bad_value, exc_type, expected_exc", nl_repr_protocol_error_cases)
def test_nl_repr_protocol_validation(bad_value, exc_type, expected_exc):
    """测试__nl_repr__协议验证：非callable的__nl_repr__应该抛出NLReprError"""

    class BadObj:
        __nl_repr__ = bad_value

    with pytest.raises(exc_type) as exc_info:
        nl_repr(BadObj())
    print("实际异常消息:", str(exc_info.value))
    import re

    assert re.search(expected_exc, str(exc_info.value))


def test_nl_repr_protocol_with_kwargs():
    """测试__nl_repr__方法接收kwargs参数"""
    class ParametricObj:
        def __init__(self, name, value):
            self.name = name
            self.value = value

        def __nl_repr__(self, **kwargs):
            prefix = kwargs.get("prefix", "")
            suffix = kwargs.get("suffix", "")
            return f"{prefix}{self.name}: {self.value}{suffix}"

    param_obj = ParametricObj("测试对象", 42)
    
    # 默认参数
    assert nl_repr(param_obj) == "测试对象: 42"
    
    # 带前缀
    assert nl_repr(param_obj, prefix="→ ") == "→ 测试对象: 42"
    
    # 带后缀
    assert nl_repr(param_obj, suffix=" ←") == "测试对象: 42 ←"
    
    # 带前缀和后缀
    assert nl_repr(param_obj, prefix="【", suffix="】") == "【测试对象: 42】"


def test_nl_repr_protocol_priority():
    """测试__nl_repr__协议的优先级"""
    from aicore.utils.nl_repr import register, _nl_repr_list

    class CustomList(list):
        def __nl_repr__(self, **kwargs):
            return f"Custom: {len(self)} items"

    custom_lst = CustomList([1, 2, 3])
    
    # __nl_repr__ 协议应该优先于内置list处理
    assert nl_repr(custom_lst) == "Custom: 3 items"
    
    # 注册类型处理器
    @register(CustomList)
    def registry_handler(obj: CustomList, **kwargs) -> str:
        return f"Registry: {len(obj)} items"
    
    # __nl_repr__ 协议应该优先于类型注册表
    assert nl_repr(custom_lst) == "Custom: 3 items"
    assert nl_repr(custom_lst) != "Registry: 3 items"


def test_nl_repr_protocol_not_callable():
    """测试非callable的__nl_repr__应该抛出NLReprError"""
    class BadObj:
        __nl_repr__ = "not a callable"

    with pytest.raises(NLReprError, match="__nl_repr__ must be callable"):
        nl_repr(BadObj())


def test_nl_repr_protocol_return_non_str():
    """测试__nl_repr__返回非str类型应该抛出NLReprError"""
    class BadReturnType:
        def __nl_repr__(self, **kwargs):
            return 123

    with pytest.raises(NLReprError, match="__nl_repr__.*必须返回str"):
        nl_repr(BadReturnType())



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