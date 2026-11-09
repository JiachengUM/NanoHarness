import pytest

from nanoai.utils.text_utils import extract_params, format_template

test_data = [
    ("生成{style}风格的{format}摘要", {"style": "简洁", "format": "段落"}, "生成简洁风格的段落摘要"),
    (
        "长度约为原文的{length_ratio}%，质量达到{quality_score}",
        {"length_ratio": 25, "quality_score": 0.95},
        "长度约为原文的25%，质量达到0.95",
    ),
    (
        "包含关键点：{include_points}，包含来源：{include_source}",
        {"include_points": True, "include_source": False},
        "包含关键点：True，包含来源：False",
    ),
    (
        "最大对象数：{max_objects}，焦点属性：{focus_properties}",
        {"max_objects": None, "focus_properties": None},
        "最大对象数：None，焦点属性：None",
    ),
    (
        "对象类型：{object_types}，焦点区域：{focus_areas}",
        {"object_types": ["人物", "地点", "时间"], "focus_areas": {"区域1", "区域2"}},
        None,
    ),
]


@pytest.mark.parametrize("text, placeholders, expected", test_data)
def test_format_template_basic(text, placeholders, expected):
    result = format_template(text, placeholders)
    if expected is not None:
        assert result == expected
    else:
        # 复杂对象只需断言主要内容
        assert "人物" in result and "地点" in result and "时间" in result


def test_extract_params_cases():
    assert extract_params("") == set()
    assert extract_params("普通文本") == set()
    assert extract_params("生成{style}风格的{style}摘要，{style}很重要") == {"style"}
    assert extract_params("测试{param1}和{param_2}以及{param3}") == {"param1", "param_2", "param3"}
    assert extract_params("测试{Style}和{style}以及{STYLE}") == {"Style", "style", "STYLE"}
    assert extract_params("测试{}和{123}以及{invalid-param}") == {"123"}


def test_missing_placeholder():
    text = "生成{style}风格的{format}摘要，要求{extra}"
    placeholders = {"style": "简洁", "format": "段落"}
    with pytest.raises(KeyError) as exc_info:
        format_template(text, placeholders)
    assert "缺少参数" in str(exc_info.value)
    assert "extra" in str(exc_info.value)


def test_unstringable_value():
    class Unstringable:
        def __str__(self):
            raise Exception("Cannot convert to string")

    text = "测试{param}"
    placeholders = {"param": Unstringable()}
    with pytest.raises(TypeError) as exc_info:
        format_template(text, placeholders)
    assert "无法将参数" in str(exc_info.value)
    assert "param" in str(exc_info.value)


def test_required_params_and_debug_check():
    text = "生成{style}风格的{format}摘要，要求{extra}"
    placeholders = {"style": "简洁", "format": "段落", "extra": "高质量"}
    required_params = {"style", "format"}  # 缺少extra
    # debug_check=True时，required_params不完整应报错
    with pytest.raises(ValueError) as exc_info:
        format_template(text, placeholders, required_params, debug_check=True)
    assert "预计算的参数集合不完整" in str(exc_info.value)
    assert "extra" in str(exc_info.value)
    # debug_check=False时，跳过验证，extra不会被替换
    result = format_template(text, placeholders, required_params, debug_check=False)
    assert result == "生成简洁风格的段落摘要，要求{extra}"


def main():
    for text, placeholders, expected in test_data:
        test_format_template_basic(text, placeholders, expected)

    test_extract_params_cases()
    test_missing_placeholder()

    test_unstringable_value()
    test_required_params_and_debug_check()


RUN_PYTEST = False

if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        # 使用 -v 参数显示详细输出
        pytest.main(["-vs", __file__])
    else:
        # 可以这么写，是不报错的。
        # f"no format".format(arg = 1)
        main()
