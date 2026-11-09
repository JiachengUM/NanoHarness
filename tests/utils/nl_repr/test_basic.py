"""基础类型测试模块"""

import pytest

from aicore.utils.nl_repr import NLReprError, nl_repr


basic_normal_cases = [
    (0, "0"),
    (3.14, "3.14"),
    (True, "True"),
    ("hello", "hello"),
    ("你好世界", "你好世界"),
    ("🚀🌟💡", "🚀🌟💡"),
    ("a" * 1000, "a" * 1000),
    ([f"item_{i}" for i in range(20)], None),
    (None, "None"),
]


basic_error_cases = [
    ((1, 2), "对于类型<class 'tuple'>未实现nl_repr"),
]


@pytest.mark.parametrize("value, expected", basic_normal_cases)
def test_basic_normal_cases(value, expected):
    if isinstance(value, list) and len(value) == 20:
        result = nl_repr(value)
        assert result.startswith("\n1. item_0")
        assert result.endswith("\n20. item_19")
        assert len(result.split("\n")) == 21
    else:
        assert nl_repr(value) == expected


@pytest.mark.parametrize("value, expected_exc", basic_error_cases)
def test_basic_error_cases(value, expected_exc):
    with pytest.raises(NLReprError) as exc_info:
        nl_repr(value)
    assert expected_exc in str(exc_info.value)


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
