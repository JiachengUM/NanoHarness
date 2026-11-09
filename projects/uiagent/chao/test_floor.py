from uitars import uitars_call
from uitars import uitars_call_with_prompt
from doubao import doubao_call_with_prompt
import prompt_floor
import json
import pytest

#下限测试

@pytest.mark.parametrize("image_path, query, prompt", [
    ("../datasets/lssf/001.png", "点击搜索框", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/lssf/002.png", "在输入框输入“庐上帅府”，然后点击搜索", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/lssf/003.png", "在搜索结果中选择第一个餐厅点击", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/lssf/004.png", "点击AI帮订按钮", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/lssf/005.png", "点击明天", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/lssf/006.png", "点击19:00", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/lssf/007.png", "点击8人", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/lssf/008.png", "点击下一步", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/lssf/009.png", "点击确认订座", prompt_floor.UI_TARS_PROMPT_1),
])
def test_lssf(image_path: str, query: str, prompt: str):
    """
    用户query：帮我在庐上帅府订个座，明天晚上19:00，8个人
    拆解为以下步骤：
    1、点击搜索框 ✅
    2、在输入框输入“庐上帅府”，然后点击搜索 ✅
    3、在搜索结果中选择第一个餐厅点击 ✅
    4、点击订座按钮 ✅
    5、点击明天 ✅
    6、点击19:00 ✅
    7、点击8人 ✅
    8、点击下一步 ✅
    9、点击确认订座 ✅

    页面按钮可见可点击的情况下，使用同一prompt，完成订座流程(不涉及滑动)
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
    ("../datasets/hwc/001.png", "点击搜索框", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/hwc/002.png", "在输入框输入“徽皖厨”，然后点击搜索", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/hwc/003.png", "在搜索结果中选择第一个餐厅点击", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/hwc/004.png", "点击订座按钮", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/hwc/005.png", "点击10.01", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/hwc/006.png", "点击19:00", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/hwc/007.png", "点击5人", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/hwc/008.png", "点击包间", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/hwc/009.png", "点击下一步", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/hwc/010.png", "点击确认订座", prompt_floor.UI_TARS_PROMPT_1),
])
def test_hwc(image_path: str, query: str, prompt: str):
    """
    用户query：帮我在徽皖厨订个座，10月1号晚上19:00，5个人的包间
    拆解为以下步骤：
    1、点击搜索框 ✅
    2、在输入框输入“徽皖厨”，然后点击搜索 ✅
    3、在搜索结果中选择第一个餐厅点击 ✅
    4、点击订座按钮 ✅
    5、点击10.01 ✅
    6、点击19:00 ✅
    7、点击5人 ✅
    8、点击包间 ✅
    9、点击下一步 ✅
    10、点击确认订座 ✅

    页面按钮可见可点击的情况下，使用同一prompt，完成订座流程(不涉及滑动)
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
    ("../datasets/bhj/001.png", "点击搜索框", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/bhj/002.png", "在输入框输入“半壶居”，然后点击搜索", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/bhj/003.png", "在搜索结果中选择第一个餐厅点击", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/bhj/004.png", "点击订座按钮", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/bhj/005.png", "点击10.01", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/bhj/006.png", "点击11:30", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/bhj/007.png", "点击4人", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/bhj/008.png", "点击包间", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/bhj/009.png", "点击下一步", prompt_floor.UI_TARS_PROMPT_1),
    ("../datasets/bhj/010.png", "点击确认订座", prompt_floor.UI_TARS_PROMPT_1),
])
def test_bhj(image_path: str, query: str, prompt: str):
    """
    用户query：帮我在半壶居订个座，10月1号中午11:30，4个人的包间
    拆解为以下步骤：
    1、点击搜索框 ✅
    2、在输入框输入“半壶居”，然后点击搜索 ✅
    3、在搜索结果中选择第一个餐厅点击 ✅
    4、点击订座按钮 ✅
    5、点击10.01 ✅
    6、点击11:30 ✅
    7、点击4人 ✅
    8、点击包间 ✅
    9、点击下一步 ✅
    10、点击确认订座 ✅

    页面按钮可见可点击的情况下，使用同一prompt，完成订座流程(不涉及滑动)
    """
    print(f"=== 开始-{image_path} ===")

    try:
        result = uitars_call_with_prompt(image_path, query, prompt)
        if result['success']:
            print(json.dumps(result, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result