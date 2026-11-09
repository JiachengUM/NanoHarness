
from uitars import uitars_call_with_context
from uitars import uitars_call_with_prompt
import prompt
import json
import pytest

@pytest.mark.parametrize("image_path, query, prompt", [
    # ("../datasets/hehuiyan/scroll_001.png", "帮我选择12人的座位", prompt.UI_TARS_PROMPT_4),
    # ("../datasets/hehuiyan/scroll_002.png", "帮我选择12人的座位", prompt.UI_TARS_PROMPT_4),
    ("../datasets/hehuiyan/scroll_003.png", "帮我选择12人的座位", prompt.UI_TARS_PROMPT_4),
])
def test_uitars_scroll_no_context(image_path: str, query: str, prompt: str):
    """

    """
    print(f"=== 开始-{image_path} ===")

    try:
        result = uitars_call_with_prompt(image_path, query, prompt)
        if result['success']:
            print(json.dumps(result, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result

@pytest.mark.parametrize("image_path, query, prompt, chat_id", [
    # ("../datasets/hehuiyan/scroll_001.png", "帮我选择12人的座位", prompt.UI_TARS_PROMPT_SCROLL, "1001"),
    # ("../datasets/hehuiyan/scroll_002.png", "帮我选择12人的座位", prompt.UI_TARS_PROMPT_SCROLL, "1001"),
    # ("../datasets/hehuiyan/scroll_003.png", "帮我选择12人的座位", prompt.UI_TARS_PROMPT_SCROLL, "1001"),
    # ("../datasets/hehuiyan/scroll_003.png", "帮我选择12人的座位", prompt.UI_TARS_PROMPT_SCROLL, "1001"),
    ("../datasets/hehuiyan/scroll_003.png", "帮我选择12人的座位", prompt.UI_TARS_PROMPT_SCROLL, "1001"),
])
def test_uitars_scroll_with_context(image_path: str, query: str, prompt: str, chat_id: str):
    """
    人数店铺最多能选10人，query中让他选12人
    多次滑动之后，依然在003页面，最终模型输出：无法选择12人

    该场景能成功，可能跟页面中有 “大厅 包厢 2-10人可订”信息有关
    """
    print(f"=== 开始-{image_path} ===")

    try:
        result = uitars_call_with_context(image_path, query, prompt, chat_id)
        if result['success']:
            print(json.dumps(result, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result

@pytest.mark.parametrize("image_path, query, prompt, chat_id", [
    # ("../datasets/hehuiyan/scroll_001.png", "帮我选择10.07", prompt.UI_TARS_PROMPT_SCROLL, "1002"),
    # ("../datasets/hehuiyan/scroll_004.png", "帮我选择10.07", prompt.UI_TARS_PROMPT_SCROLL, "1002"),
    # ("../datasets/hehuiyan/scroll_004.png", "帮我选择10.07", prompt.UI_TARS_PROMPT_SCROLL, "1002"),
    # ("../datasets/hehuiyan/scroll_004.png", "帮我选择10.07", prompt.UI_TARS_PROMPT_SCROLL, "1002"),
    # ("../datasets/hehuiyan/scroll_004.png", "帮我选择10.07", prompt.UI_TARS_PROMPT_SCROLL, "1002"),
    ("../datasets/hehuiyan/scroll_004.png", "帮我选择10.07", prompt.UI_TARS_PROMPT_SCROLL, "1002"),
])
def test_uitars_scroll_with_context2(image_path: str, query: str, prompt: str, chat_id: str):
    """
    换一个日期来试验，多次滑动一直传004页面，模型还是一直输出滑动。
    该方法不可行
    """
    print(f"=== 开始-{image_path} ===")

    try:
        result = uitars_call_with_context(image_path, query, prompt, chat_id)
        if result['success']:
            print(json.dumps(result, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result

@pytest.mark.parametrize("image_path, query, prompt, chat_id", [
    # ("../datasets/hehuiyan/scroll_001.png", "帮我选择10.07", prompt.UI_TARS_PROMPT_SCROLL2, "1003"),
    # ("../datasets/hehuiyan/scroll_004.png", "帮我选择10.07", prompt.UI_TARS_PROMPT_SCROLL2, "1003"),
    # ("../datasets/hehuiyan/scroll_004.png", "帮我选择10.07", prompt.UI_TARS_PROMPT_SCROLL2, "1003"),
    ("../datasets/hehuiyan/scroll_004.png", "帮我选择10.07", prompt.UI_TARS_PROMPT_SCROLL2, "1003"),
])
def test_uitars_scroll_with_context3(image_path: str, query: str, prompt: str, chat_id: str):
    """
    基于test_uitars_scroll_with_context2场景，换了一个提示词，在提示词中规定，如果超过三次滑动，还没选到选项，那就提示用户选择不到了。
    这种方式通过。

    或许我们直接记录连续滑动次数，超过多少次就算不可行，这样更简单。让模型来做这种事情，可行但是收益不高。
    """
    print(f"=== 开始-{image_path} ===")

    try:
        result = uitars_call_with_context(image_path, query, prompt, chat_id)
        if result['success']:
            print(json.dumps(result, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result