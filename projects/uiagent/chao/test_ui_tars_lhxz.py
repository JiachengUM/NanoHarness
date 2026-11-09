from uitars import uitars_call
from uitars import uitars_call_with_prompt
from doubao import doubao_call_with_prompt
import prompt
import json
import pytest


@pytest.mark.parametrize("image_path, query, prompt", [
    # ("../datasets/lhxz/001.png", "点击搜索框", prompt.UI_TARS_PROMPT_5),
    # ("../datasets/lhxz/002.png", "在输入框输入“老好小灶”，然后点击搜索", prompt.UI_TARS_PROMPT_5),
    # ("../datasets/lhxz/003.png", "在搜索结果中选择第一个餐厅点击", prompt.UI_TARS_PROMPT_5),
    # ("../datasets/lhxz/004.png", "点击订座按钮", prompt.UI_TARS_PROMPT_5),
    # ("../datasets/lhxz/005.png", "滑动日期选项，点击周六", prompt.UI_TARS_PROMPT_5),
    # ("../datasets/lhxz/006.png", "滑动时间选项，点击11:30", prompt.UI_TARS_PROMPT_5),
    # ("../datasets/lhxz/006.png", "滑动人数选项，点击6人", prompt.UI_TARS_PROMPT_5),
    # ("../datasets/lhxz/008.png", "滑动人数选项，点击6人", prompt.UI_TARS_PROMPT_5),
    # ("../datasets/lhxz/009.png", "点击大厅", prompt.UI_TARS_PROMPT_5),
    # ("../datasets/lhxz/009.png", "点击下一步", prompt.UI_TARS_PROMPT_5),
    ("../datasets/lhxz/009.png", "点击确认订座", prompt.UI_TARS_PROMPT_5),
])
def test_uitars_lhxz_2(image_path: str, query: str, prompt: str):
    """
    用户query：帮我在老好小灶订个座，周六上午十一点半，6个人
    拆解为以下步骤：
    1、点击搜索框
    2、在输入框输入“老好小灶”，然后点击搜索 (从query中提取店名)
    3、在搜索结果中选择第一个餐厅点击
    4、点击订座按钮
    5、滑动日期选项，点击周六 （提取日期）
    6、滑动时间选项，点击11:30
    7、滑动人数选项，点击6人
    8、点击大厅
    9、点击下一步
    10、点击确认订座

    结论：
    拆解一步步流程走下去问题不大

    问题：
    1、如何将用户指令拆解为一步一步的任务？
    参数提取
    2、选座页 滑动可能会多次操作才能选到，如何处理

    """
    print(f"=== 开始-{image_path} ===")

    try:
        result = uitars_call_with_prompt(image_path, query, prompt)
        if result['success']:
            print(json.dumps(result, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result


@pytest.mark.parametrize("image_path, query, prompt", [
    # ("../datasets/huanchu/y_001.png", "点击搜索框", prompt.UI_TARS_PROMPT_5),
    # ("../datasets/huanchu/y_002.png", "在输入框输入“郇厨”，然后点击搜索", prompt.UI_TARS_PROMPT_5),
    # ("../datasets/huanchu/y_003.png", "在搜索结果中选择第一个餐厅点击", prompt.UI_TARS_PROMPT_5),
    # ("../datasets/huanchu/y_004.png", "点击订座按钮", prompt.UI_TARS_PROMPT_5),
    # ("../datasets/huanchu/y_005.png", "点击6人", prompt.UI_TARS_PROMPT_5),
    ("../datasets/huanchu/y_005.png", "点击周二", prompt.UI_TARS_PROMPT_5),
])
def test_uitars_lhxz_3(image_path: str, query: str, prompt: str):
    """
    用户query：帮我在老好小灶订个座，周六上午十一点半，6个人


    问题：
    1、当页面中日期选项只有周一，左滑右滑都不会出现数据，这时官方提示词会返回点击周一的按钮以触发时间选择功能，但实际不会出现;
    在自己编的提示词中明确规定如果页面中“没有用户指令中操作的信息，比如图中日期只显示了周一，但用户要点击周二，那就直接输出“流程结束”动作”，但还是会输出滑动

    """
    print(f"=== 开始-{image_path} ===")

    try:
        result = uitars_call_with_prompt(image_path, query, prompt)
        if result['success']:
            print(json.dumps(result, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result

