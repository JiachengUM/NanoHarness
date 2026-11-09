"""字典相关测试模块"""

import pytest

from aicore.utils.nl_repr import nl_repr, nl_repr_safe


def test_dict_basic():
    """测试基本字典功能"""
    # 简单字典
    result = nl_repr({"name": "张三", "age": 25})
    assert "name: 张三" in result
    assert "age: 25" in result

    # 包含None值的字典
    result = nl_repr({"用户": "张三", "状态": None, "权限": ["读取", "写入"]})
    assert "用户: 张三" in result
    assert "状态: 无" in result
    assert "权限:" in result
    assert "1. 读取" in result
    assert "2. 写入" in result

    # 空字典
    result = nl_repr({})
    assert result == "无"


def test_dict_nested():
    """测试嵌套字典"""
    nested = {
        "用户": {
            "姓名": "张三",
            "年龄": 25,
            "地址": {"城市": "北京", "街道": "中关村"}
        }
    }
    result = nl_repr(nested)
    assert "用户:" in result
    assert "姓名: 张三" in result
    assert "年龄: 25" in result
    assert "地址:" in result
    assert "城市: 北京" in result
    assert "街道: 中关村" in result


def test_dict_with_list():
    """测试包含列表的字典"""
    data = {
        "课程": "Python编程",
        "学生": ["张三", "李四", "王五"],
        "成绩": [90, 85, 95]
    }
    result = nl_repr(data)
    assert "课程: Python编程" in result
    assert "学生:" in result
    assert "1. 张三" in result
    assert "2. 李四" in result
    assert "3. 王五" in result
    assert "成绩:" in result
    assert "1. 90" in result
    assert "2. 85" in result
    assert "3. 95" in result


def test_nl_repr_safe_with_dict():
    """测试nl_repr_safe处理字典"""
    # 正常字典
    assert nl_repr_safe({"a": 1, "b": 2}) == "a: 1\nb: 2"

    # 包含不支持的对象
    class NotSupported:
        pass

    not_supported_obj = NotSupported()
    not_supported_str = str(not_supported_obj)
    mixed_dict = {"key1": "value", "key2": not_supported_obj}
    result = nl_repr_safe(mixed_dict)
    assert "key1" in result
    assert not_supported_str in result


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