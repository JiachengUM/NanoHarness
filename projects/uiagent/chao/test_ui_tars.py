from uitars import uitars_call
from uitars import uitars_call_with_prompt
import prompt
import json
import pytest

@pytest.mark.parametrize("image_path, query, prompt_type", [
    ("../datasets/hehuiyan/002.png", "在输入框内输入合徽宴", "official"),
    ("../datasets/hehuiyan/002.png", "在输入框内输入合徽宴", "own"),
])
def test_uitars_input(image_path: str, query: str, prompt_type: str):
    """
    页面：首页输入框 query:在输入框内输入合徽宴

    测试结论：
    提示词一：官方：需在图中匹配到光标，然后输出“输入”动作和“输入文本”；如果图中未匹配到光标，会输出点击输入框的动作
    提示词二：自己写的：输出(动作：input、坐标：point、内容：content)，一套完整的动作
    自己写的提示词效果更好
    """
    print(f"=== 开始-{prompt_type} ===")

    try:
        result = uitars_call(image_path, query, prompt_type)
        if result['success']:
            print(json.dumps(result, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result

@pytest.mark.parametrize("image_path, query, prompt_type", [
    ("../datasets/hehuiyan/003.png", "输出搜索到的内容", "official"),
    ("../datasets/hehuiyan/003.png", "输出搜索到的内容", "own"),
])
def test_uitars_output_list(image_path: str, query: str, prompt_type: str):
    """
    页面：搜索列表页 query:输出搜索到的内容
    测试结论：
    官方：输出“点击搜索”按钮
    自己写的：输出页面展示的店铺信息
    自己写的提示词效果更好
    """
    print(f"=== 开始-{prompt_type} ===")

    try:
        result = uitars_call(image_path, query, prompt_type)
        if result['success']:
            print(json.dumps(result, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result

@pytest.mark.parametrize("image_path, query, prompt_type", [
    ("../datasets/hehuiyan/003.png", "去第一家店", "official"),
    ("../datasets/hehuiyan/003.png", "去第一家店", "own"),
])
def test_uitars_go_first_shop(image_path: str, query: str, prompt_type: str):
    """
    页面：搜索列表页

    测试结论：
    官方：点击列表第一个店铺
    自己写的：点击列表第一个店铺
    两个效果一致，都正确点击了第一个店铺
    """
    print(f"=== 开始-{prompt_type} ===")

    try:
        result = uitars_call(image_path, query, prompt_type)
        if result['success']:
            print(json.dumps(result, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result

@pytest.mark.parametrize("image_path, query, prompt", [
    ("../datasets/hehuiyan/009.png", "先点击同意授权，再点击确认订座", prompt.UI_TARS_PROMPT),
    ("../datasets/hehuiyan/009.png", "先点击同意授权，再点击确认订座", prompt.UI_TARS_PROMPT_4),
])
def test_uitars_confirm(image_path: str, query: str, prompt: str):
    """
    页面：确认订座页
    官方：点击同意授权
    自己写的：先点击同意授权、再点击确认订座 两个动作
    符合预期
    """
    print(f"=== 开始 {image_path} ===")

    try:
        result = uitars_call_with_prompt(image_path, query, prompt)
        if result['success']:
            print(json.dumps(result, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result

@pytest.mark.parametrize("image_path, query, prompt", [
    ("../datasets/hehuiyan/010.png", "帮我订个座", prompt.UI_TARS_PROMPT),
    ("../datasets/hehuiyan/010.png", "帮我订个座", prompt.UI_TARS_PROMPT_4),
])
def test_uitars_finished(image_path: str, query: str, prompt: str):
    """
    页面：订座完成页
    官方：打开美团
    自己写的：输出完成动作

    """
    print(f"=== 开始 {image_path} ===")

    try:
        result = uitars_call_with_prompt(image_path, query, prompt)
        if result['success']:
            print(json.dumps(result, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result
