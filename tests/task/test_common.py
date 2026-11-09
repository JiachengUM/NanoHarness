import asyncio
from enum import StrEnum

import pytest

from nanoai.task.common import aclassify, acompare_judge, ajudge, classify, judge, compare_judge
from nanoai.utils.nl_repr import nl_repr
from tests.task.task_data import QUERIES_BOOL, QUERIES_COT

SYMBOL_CATEGORIES = [
    ("中文", "中文是中国的官方语言。"),
    ("英文", "英文是美国的官方语言。"),
    ("数字", "数字是用来计数的。"),
    ("符号", "符号是用来表示一些特殊含义的。"),
    ("乱码", "乱码是一些无法识别的字符。"),
    ("其它", "不属于上述任何类别。"),
]


SYMBOL_EXAMPLES = [
    "你好",
    "Hello",
    "123",
    "hello啊123" "!@#$%^&*()",
    "Z@%NK好滴额][]",
]


class TextUnitCategory(StrEnum):
    WORD = "词语"
    SENTENCE = "句子"
    PARAGRAPH = "段落"
    OTHER = "其它"


TEXT_UNIT_EXAMPLES = [
    "苹果",
    "苹果是红色的",
    "苹果是红色的。苹果是甜的。苹果是圆的。我爱吃苹果。",
    "Z@%NK好滴额][]",
]


def test_classify():
    print("测试classify")

    for input in SYMBOL_EXAMPLES:
        # 同步分类
        try:
            result = classify(input, SYMBOL_CATEGORIES)
            print(f"输入: {input}, 同步分类结果: {nl_repr(result)}")
        except Exception as e:
            print(f"同步分类错误: {e}")
            result = None
        
        # 异步分类
        try:
            result_async = asyncio.run(aclassify(input, SYMBOL_CATEGORIES))
            print(f"输入: {input}, 异步分类结果: {nl_repr(result_async)}")
        except Exception as e:
            print(f"异步分类错误: {e}")
            result_async = None
        
        # 检查结果一致性
        if result is not None and result_async is not None:
            if result.category != result_async.category:
                print(f"警告: 同步和异步结果不一致: {result} vs {result_async}")

    for input in TEXT_UNIT_EXAMPLES:
        # 同步分类
        try:
            result = classify(input, TextUnitCategory)
            print(f"输入: {input}, 同步分类结果: {nl_repr(result)}")
        except Exception as e:
            print(f"同步分类错误: {e}")
            result = None
        
        # 异步分类
        try:
            result_async = asyncio.run(aclassify(input, TextUnitCategory))
            print(f"输入: {input}, 异步分类结果: {nl_repr(result_async)}")
        except Exception as e:
            print(f"异步分类错误: {e}")
            result_async = None
        
        # 检查结果一致性
        if result is not None and result_async is not None:
            if result.category != result_async.category:
                print(f"警告: 同步和异步结果不一致: {result} vs {result_async}")



@pytest.mark.parametrize("use_classify", [True, False])
def test_judge(use_classify):
    print("测试judge")
    for input, expected in QUERIES_BOOL:
        # 同步判断
        try:
            result = judge(input, use_classify=use_classify)
            print(f"输入: {input}, expected: {expected}, 同步结果: {nl_repr(result)}")
        except Exception as e:
            print(f"同步判断错误: {e}")
            result = None
        
        # 异步判断
        try:
            result_async = asyncio.run(ajudge(input, use_classify=use_classify))
            print(f"输入: {input}, expected: {expected}, 异步结果: {nl_repr(result_async)}")
        except Exception as e:
            print(f"异步判断错误: {e}")
            result_async = None
        
        # 检查结果一致性
        if result is not None and result_async is not None:
            if result.judgment != result_async.judgment:
                print(f"警告: 同步和异步结果不一致: {result} vs {result_async}")

    # 这些问题并不能用True or False回答。但模型并不太能分辨的出来。。。
    for input, expected in QUERIES_COT:
        # 同步判断
        try:
            result = judge(input, use_classify=use_classify)
            print(f"输入: {input}, 同步结果: {nl_repr(result)}")
        except Exception as e:
            print(f"同步判断错误: {e}")
            result = None
        
        # 异步判断
        try:
            result_async = asyncio.run(ajudge(input, use_classify=use_classify))
            print(f"输入: {input}, 异步结果: {nl_repr(result_async)}")
        except Exception as e:
            print(f"异步判断错误: {e}")
            result_async = None
        
        # 检查结果一致性
        if result is not None and result_async is not None:
            if result.judgment != result_async.judgment:
                print(f"警告: 同步和异步结果不一致: {result} vs {result_async}")


COMPARE_JUDGE_TEST_CASES = [
    ("你好", "你好", "相同的文本"),
    ("你好", "Hello", "不同的文本"),
    ("Python是一种编程语言", "Python是编程语言", "相似但不完全相同的文本"),
]

@pytest.mark.parametrize("text1,text2,description", COMPARE_JUDGE_TEST_CASES)
def test_compare_judge(text1, text2, description):
    print(f"测试compare_judge: {description}")
    
    # 同步比较
    try:
        result = compare_judge(text1, text2)
        print(f"同步比较结果: {nl_repr(result)}")
    except Exception as e:
        print(f"同步比较错误: {e}")
        result = None
    
    # 异步比较
    try:
        result_async = asyncio.run(acompare_judge(text1, text2))
        print(f"异步比较结果: {nl_repr(result_async)}")
    except Exception as e:
        print(f"异步比较错误: {e}")
        result_async = None
    
    # 检查结果一致性
    if result is not None and result_async is not None:
        if result.judgment != result_async.judgment:
            print(f"警告: 同步和异步结果不一致: {result} vs {result_async}")


def main():
    test_classify()

    for use_classify in [True, False]:
         test_judge(use_classify)

    for text1, text2, description in COMPARE_JUDGE_TEST_CASES:
        test_compare_judge(text1, text2, description)


RUN_PYTEST = False

if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        # 使用 -v 参数显示详细输出
        pytest.main(["-vs", __file__])
    else:
        main()
