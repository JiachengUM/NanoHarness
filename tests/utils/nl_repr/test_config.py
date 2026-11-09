"""全局配置测试模块"""

import pytest

from aicore.utils.nl_repr import nl_repr, set_bool_texts


# 布尔值全局配置测试
bool_test_cases = [
    ("True", "False", "True", "False"),
    ("是", "否", "是", "否"),
    ("启用", "禁用", "启用", "禁用"),
]


@pytest.mark.parametrize("true_text,false_text,expected_true,expected_false", bool_test_cases)
def test_bool_cases_global(true_text, false_text, expected_true, expected_false):
    set_bool_texts(true_text, false_text)
    assert nl_repr(True) == expected_true
    assert nl_repr(False) == expected_false
    # 恢复默认
    set_bool_texts("True", "False")


def test_bool_cases():
    # 保存原始状态
    original_true = "True"
    original_false = "False"

    try:
        # 自动化断言部分
        assert nl_repr(True) == "True"
        assert nl_repr(False) == "False"

        # 测试自定义文本
        set_bool_texts("是", "否")
        assert nl_repr(True) == "是"
        assert nl_repr(False) == "否"

        # 测试恢复默认
        set_bool_texts("True", "False")
        assert nl_repr(True) == "True"
        assert nl_repr(False) == "False"

    finally:
        # 确保恢复原始状态
        set_bool_texts(original_true, original_false)

    # 人工演示部分
    print("\n" + "=" * 50)
    print("nl_repr 布尔值格式化演示")
    print("=" * 50)
    print("\n1. 默认格式：")
    print(f"True: {nl_repr(True)}")
    print(f"False: {nl_repr(False)}")

    print("\n2. 中文格式：")
    set_bool_texts("是", "否")
    print(f"True: {nl_repr(True)}")
    print(f"False: {nl_repr(False)}")

    print("\n3. 启用/禁用格式：")
    set_bool_texts("启用", "禁用")
    print(f"True: {nl_repr(True)}")
    print(f"False: {nl_repr(False)}")

    print("\n4. 恢复默认：")
    set_bool_texts("True", "False")
    print(f"True: {nl_repr(True)}")
    print(f"False: {nl_repr(False)}")

    print("\n" + "=" * 50)
    print("演示结束")
    print("=" * 50)



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