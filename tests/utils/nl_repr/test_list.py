"""列表相关测试模块"""

import pytest

from aicore.utils.nl_repr import nl_repr
from aicore.utils.nl_repr.list import set_list_params


def test_list_params_global():
    """测试列表格式化参数的全局配置"""
    lst = ["apple", "banana", "cherry"]

    # 保存原始状态
    original_separator = "\n"
    original_numbering = "{i}. "
    original_use_numbering = True

    try:
        # 默认格式
        assert nl_repr(lst) == "\n1. apple\n2. banana\n3. cherry"

        # 全局设置中文风格
        set_list_params(separator="、", numbering="({i}) ", use_numbering=True)
        assert nl_repr(lst) == "(1) apple、(2) banana、(3) cherry"

        # 局部覆盖
        assert nl_repr(lst, separator=" | ") == "(1) apple | (2) banana | (3) cherry"
        assert nl_repr(lst, numbering="") == "apple、banana、cherry"

        # 测试不使用编号
        set_list_params(use_numbering=False)
        assert nl_repr(lst) == "apple、banana、cherry"

    finally:
        # 恢复默认
        set_list_params(separator=original_separator, numbering=original_numbering, use_numbering=original_use_numbering)


def test_list_params_start():
    """测试列表编号起始值"""
    lst = ["a", "b", "c"]

    try:
        # 默认起始值为1
        assert nl_repr(lst) == "\n1. a\n2. b\n3. c"

        # 设置起始值为0
        set_list_params(start=0)
        assert nl_repr(lst) == "\n0. a\n1. b\n2. c"

        # 设置起始值为10
        set_list_params(start=10)
        assert nl_repr(lst) == "\n10. a\n11. b\n12. c"

    finally:
        # 恢复默认
        set_list_params(start=1)


def test_list_params_prefix_suffix():
    """测试列表项的前缀和后缀"""
    lst = ["apple", "banana", "cherry"]

    try:
        # 测试前缀
        set_list_params(prefix="🍎 ")
        result = nl_repr(lst)
        assert "🍎 apple" in result
        assert "🍎 banana" in result
        assert "🍎 cherry" in result

        # 测试后缀
        set_list_params(prefix="", suffix=" 🍎")
        result = nl_repr(lst)
        assert "apple 🍎" in result
        assert "banana 🍎" in result
        assert "cherry 🍎" in result

        # 测试前缀和后缀
        set_list_params(prefix="【", suffix="】")
        result = nl_repr(lst)
        assert "【apple】" in result
        assert "【banana】" in result
        assert "【cherry】" in result

    finally:
        # 恢复默认
        set_list_params(prefix="", suffix="")


def test_list_params_invalid():
    """测试无效的列表格式化参数"""
    with pytest.raises(ValueError, match="未知的list格式化参数"):
        set_list_params(invalid_param="value")



list_cases = [
    ([42], "1. 42", {}),
    (["a", "b", "c"], "\n1. a\n2. b\n3. c", {}),
    ([1, "hello", True], "\n1. 1\n2. hello\n3. True", {}),
    (["🚀", "🌟", "💡"], "\n1. 🚀\n2. 🌟\n3. 💡", {}),
    (["apple", "banana", "cherry"], "(1) apple、(2) banana、(3) cherry", {"separator": "、", "numbering": "({i}) "}),
    (["apple", "banana", "cherry"], "(1) apple | (2) banana | (3) cherry", {"separator": " | ", "numbering": "({i}) "}),
    (["apple", "banana", "cherry"], "apple、banana、cherry", {"separator": "、", "use_numbering": False}),
]

def test_empty_list():
    """测试空列表处理"""
    result = nl_repr([])
    assert result == "无"


def test_single_element_list():
    """测试单元素列表处理"""

    # 默认格式
    result = nl_repr([42])
    assert result == "1. 42"

    # 自定义格式
    set_list_params(separator="、", numbering="({i}) ", use_numbering=True)
    result = nl_repr([42])
    assert result == "(1) 42"

    # 不使用编号
    set_list_params(use_numbering=False)
    result = nl_repr([42])
    assert result == "42"

    # 恢复默认
    set_list_params(separator="\n", numbering="{i}. ", use_numbering=True)

    # 测试复杂元素
    result = nl_repr([True])
    assert result == "1. True"

    result = nl_repr(["hello"])
    assert result == "1. hello"

    result = nl_repr([["nested"]])
    assert result == "1. 1. nested"



@pytest.mark.parametrize("lst, expected, params", list_cases)
def test_list_cases(lst, expected, params):
    # 设置全局参数
    if "separator" in params or "numbering" in params:
        set_list_params(
            separator=params.get("separator", "\n"),
            numbering=params.get("numbering", "{i}. "),
            use_numbering=params.get("use_numbering", True),
        )
    # 调用并断言
    result = nl_repr(lst, **{k: v for k, v in params.items() if k not in ["separator", "numbering"]})
    assert result == expected
    # 恢复默认
    set_list_params(separator="\n", numbering="{i}. ", use_numbering=True)


def test_list_formatting():
    """测试列表格式化功能"""
    lst = ["apple", "banana", "cherry"]

    try:
        # 自动化断言部分
        # 默认格式
        assert nl_repr(lst) == "\n1. apple\n2. banana\n3. cherry"
        # 全局设置中文风格
        set_list_params(separator="、", numbering="({i}) ", use_numbering=True)
        assert nl_repr(lst) == "(1) apple、(2) banana、(3) cherry"
        # 局部覆盖
        assert nl_repr(lst, separator=" | ") == "(1) apple | (2) banana | (3) cherry"
        assert nl_repr(lst, numbering="") == "apple、banana、cherry"
    finally:
        # 恢复默认
        set_list_params(separator="\n", numbering="{i}. ", use_numbering=True)

    # 人工演示部分
    print("\n" + "=" * 50)
    print("nl_repr 列表格式化演示")
    print("=" * 50)
    fruits = ["apple", "banana", "cherry"]
    numbers = [1, 2, 3, 4, 5]
    print("\n1. 默认格式化（换行分隔，数字编号）：")
    print(nl_repr(fruits))
    print("\n2. 自定义分隔符：")
    print("竖线分隔:", nl_repr(fruits, separator=" | "))
    print("中文分隔:", nl_repr(fruits, separator="、"))
    print("数学符号:", nl_repr(numbers, separator=" + "))
    print("\n3. 编号样式：")
    print("圆括号:", nl_repr(fruits, numbering="({i}) "))
    print("字母编号:", nl_repr(fruits, numbering="a. "))
    print("无编号:", nl_repr(fruits, use_numbering=False))
    print("\n4. 装饰效果：")
    print("表情符号:", nl_repr(fruits, prefix="🍎 ", suffix=" 🍎"))
    print("箭头装饰:", nl_repr(fruits, prefix="→ ", suffix=" ←"))
    print("\n5. 组合效果：")
    print(nl_repr(fruits, numbering="a. ", separator=" | ", prefix="• "))
    print("\n6. 嵌套列表：")
    nested = [["a", "b"], ["c", "d"]]
    print("默认格式:")
    print(nl_repr(nested))
    print("自定义格式:")
    print(nl_repr(nested, separator=" | ", prefix="→ "))
    print("\n" + "=" * 50)
    print("演示结束")
    print("=" * 50)


RUN_PYTEST = True

def main():
    test_list_formatting()

if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        # 使用 -v 参数显示详细输出
        pytest.main(["-vs", __file__])
    else:
        # 可以这么写，是不报错的。
        # f"no format".format(arg = 1)
        main()
