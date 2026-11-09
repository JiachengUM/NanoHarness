"""异常处理测试模块"""

import pytest
from typing import Any
from pydantic import BaseModel, Field

from aicore.utils.nl_repr import nl_repr, nl_repr_safe


def test_exception_handling():
    """测试Exception类型的处理"""

    # 1. 基本异常类型
    assert nl_repr(ValueError("测试错误")) == "错误: ValueError: 测试错误"
    assert nl_repr(TypeError("类型错误")) == "错误: TypeError: 类型错误"
    assert nl_repr(RuntimeError("运行时错误")) == "错误: RuntimeError: 运行时错误"

    # 2. 自定义异常
    class CustomError(Exception):
        pass

    custom_exc = CustomError("自定义错误消息")
    assert nl_repr(custom_exc) == "错误: CustomError: 自定义错误消息"

    # 3. 异常包含特殊字符
    special_exc = ValueError("包含\n换行符和\t制表符的错误")
    assert nl_repr(special_exc) == "错误: ValueError: 包含\n换行符和\t制表符的错误"

    # 4. 空消息的异常
    empty_exc = ValueError("")
    assert nl_repr(empty_exc) == "错误: ValueError: "

    # 5. 异常在列表中的处理
    mixed_list = ["正常字符串", ValueError("列表中的错误"), 42]
    result = nl_repr(mixed_list)
    assert "正常字符串" in result
    assert "错误: ValueError: 列表中的错误" in result
    assert "42" in result

    # 6. 异常在BaseModel中的处理（使用Any类型避免Pydantic错误）
    class ModelWithException(BaseModel):
        name: str = Field(title="名称")
        error: Any = Field(title="错误信息")

    model = ModelWithException(name="测试模型", error=ValueError("模型中的错误"))
    result = nl_repr(model)
    assert "名称: 测试模型" in result
    assert "错误信息: 错误: ValueError: 模型中的错误" in result

    # 7. 异常链
    try:
        try:
            raise ValueError("内层错误")
        except ValueError as e:
            raise RuntimeError("外层错误") from e
    except RuntimeError as e:
        assert nl_repr(e) == "错误: RuntimeError: 外层错误"

    # 8. 测试nl_repr_safe对异常的处理（应该直接使用nl_repr）
    exc = ValueError("安全测试")
    assert nl_repr_safe(exc) == "错误: ValueError: 安全测试"


def test_exception_in_nested_structures():
    """测试异常在嵌套结构中的处理"""
    # 嵌套列表中的异常
    nested_list = [
        ["第一层", ValueError("错误1")],
        [ValueError("错误2"), "正常"]
    ]
    result = nl_repr(nested_list)
    assert "错误: ValueError: 错误1" in result
    assert "错误: ValueError: 错误2" in result

    # 嵌套字典中的异常
    nested_dict = {
        "outer": {
            "inner1": ValueError("内层错误1"),
            "inner2": "正常值"
        },
        "error": ValueError("外层错误")
    }
    result = nl_repr(nested_dict)
    assert "错误: ValueError: 内层错误1" in result
    assert "错误: ValueError: 外层错误" in result

    # 混合嵌套
    mixed = {
        "list": [ValueError("列表中的异常"), "正常"],
        "dict": {"key": ValueError("字典中的异常")}
    }
    result = nl_repr(mixed)
    assert "错误: ValueError: 列表中的异常" in result
    assert "错误: ValueError: 字典中的异常" in result


def test_exception_with_none_message():
    """测试异常消息为None的情况"""
    exc = ValueError(None)
    result = nl_repr(exc)
    assert "错误: ValueError: None" in result


def test_exception_with_complex_message():
    """测试异常消息包含复杂对象"""
    class CustomObj:
        def __str__(self):
            return "CustomObject"

    exc = ValueError(CustomObj())
    result = nl_repr(exc)
    assert "错误: ValueError: CustomObject" in result


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