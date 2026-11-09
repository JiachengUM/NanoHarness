"""nl_repr_safe测试模块"""

import pytest

from aicore.utils.nl_repr.core import nl_repr_safe


def test_nl_repr_safe():
    # 1. 能正常转换的对象
    assert nl_repr_safe("abc") == "abc"
    assert nl_repr_safe(42) == "42"
    assert nl_repr_safe(True) == "True"

    # 2. 不支持的对象，兜底返回str(x)
    class NotSupported:
        pass

    obj = NotSupported()
    assert nl_repr_safe(obj) == str(obj)

    # 3. kwargs正常传递
    class CustomObj:
        def __nl_repr__(self, **kwargs):
            return f"custom_{kwargs.get('style', 'default')}"

    custom_obj = CustomObj()
    assert nl_repr_safe(custom_obj, style="fancy") == "custom_fancy"

    # 4. __nl_repr__抛出非NLReprError异常，应该继续抛出
    class Buggy:
        def __nl_repr__(self, **kwargs):
            raise ValueError("should not be caught")

    with pytest.raises(ValueError):
        nl_repr_safe(Buggy())


def test_nl_repr_safe_preserves_exceptions():
    """测试nl_repr_safe不捕获非NLReprError异常"""
    class RaisesValueError:
        def __nl_repr__(self, **kwargs):
            raise ValueError("ValueError should propagate")

    class RaisesTypeError:
        def __nl_repr__(self, **kwargs):
            raise TypeError("TypeError should propagate")

    class RaisesRuntimeError:
        def __nl_repr__(self, **kwargs):
            raise RuntimeError("RuntimeError should propagate")

    with pytest.raises(ValueError, match="ValueError should propagate"):
        nl_repr_safe(RaisesValueError())

    with pytest.raises(TypeError, match="TypeError should propagate"):
        nl_repr_safe(RaisesTypeError())

    with pytest.raises(RuntimeError, match="RuntimeError should propagate"):
        nl_repr_safe(RaisesRuntimeError())


RUN_PYTEST = False

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