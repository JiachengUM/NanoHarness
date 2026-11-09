from uitars import uitars_call
from uitars import uitars_call_with_prompt
from doubao import doubao_call_with_prompt
import prompt
import json
import pytest

#滑动动作的测试
#在订座页面测试滑动动作输出，出现如下一些现象：
#1、在平板截图（合徽宴店）中，官方提示词输出左滑右滑动作比较稳定且准确，偶现点击动作；自己写的提示词出现向上、或与预期不符的滑动方向，且输出不稳定
#2、在手机截图（合徽宴、郇厨店）中，官方提示词和自己写的提示词输出的方向都准确且稳定
#猜想：图的类型(平板截的图和手机截的图)是否对效果存在一些影响？
@pytest.mark.parametrize("image_path, query, prompt_type", [
    ("../datasets/hehuiyan/005.png", "帮我订今天16:30 10个人的座位", "official"),
    ("../datasets/hehuiyan/005.png", "帮我订今天16:30 10个人的座位", "own"),
])
def test_uitars_table_reservation1(image_path: str, query: str, prompt_type: str):
    """
    页面：订座页面（平板） query:帮我订今天16:30 10个人的座位  预期结果：朝右滑动
    官方：向右   结合下面几个测试来看，官方定义滑动的方向是想看哪个方向的内容就朝那方向滑动
    自己写的：出现向右或向左滑动
    结论：自己写的提示词输出滑动方向不稳定
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
    ("../datasets/hehuiyan/006.png", "帮我订明天13:00 3个人的座位", "official"),
    ("../datasets/hehuiyan/006.png", "帮我订明天13:00 3个人的座位", "own"),
])
def test_uitars_table_reservation2(image_path: str, query: str, prompt_type: str):
    """
    页面：订座页面(平板) query:帮我订明天13:00 3个人的座位
    官方：向左滑动，偶先出现点击动作
    自己写的：出现向上或向左滑动，输出不稳定
    结论：自己写的提示词滑动方向不稳定
    在提示词中规定只能左右滑动后，未出现上划动作，方法可行
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
    ("../datasets/huanchu/001.png", "帮我订周一12:30 4个人的座位", "official"),
    ("../datasets/huanchu/001.png", "帮我订周一12:30 4个人的座位", "own"),
])
def test_uitars_table_reservation3(image_path: str, query: str, prompt_type: str):
    """
    页面：郇厨订座页面(手机) query:帮我订周一12:30 4个人的座位
    官方：输出左滑
    自己写的：输出左滑
    结论：符合预期
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
    ("../datasets/huanchu/002.png", "帮我订周一11:00 10个人的座位", "official"),
    ("../datasets/huanchu/002.png", "帮我订周一11:00 10个人的座位", "own"),
])
def test_uitars_table_reservation4(image_path: str, query: str, prompt_type: str):
    """
    页面：郇厨订座页面（手机） query:帮我订周一11:00 10个人的座位
    官方：输出右滑
    自己写的：输出右滑
    结论：符合预期
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
    ("../datasets/hehuiyan/008.png", "帮我订今天19:00 4个人的座位", "official"),
    ("../datasets/hehuiyan/008.png", "帮我订今天19:00 4个人的座位", "own"),
])
def test_uitars_table_reservation5(image_path: str, query: str, prompt_type: str):
    """
    页面：合徽宴订座页面(手机) query:帮我订今天19:00 4个人的座位
    官方：输出左滑
    自己写的：输出左滑
    结论：符合预期
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
    ("../datasets/hehuiyan/008.png", "帮我订今天19:00 10个人的座位", "official"),
    ("../datasets/hehuiyan/008.png", "帮我订今天19:00 10个人的座位", "own"),
])
def test_uitars_table_reservation6(image_path: str, query: str, prompt_type: str):
    """
    页面：合徽宴订座页面(手机) query:帮我订今天19:00 4个人的座位
    官方：输出右滑
    自己写的：输出右滑
    结论：符合预期
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
    ("../datasets/hehuiyan/008.png", "帮我订今天19:00 10个人的座位", prompt.UI_TARS_PROMPT_5),
])
def test_uitars_table_reservation7(image_path: str, query: str, prompt: str):
    """
    测试欢动距离输出
    输出了滑动+距离
    结论：符合预期
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
    ("../datasets/hehuiyan/008.png", "帮我在合徽宴订今天19:00 10个人的座位", prompt.PIC_PROMPT_6),
])
def test_uitars_table_reservation8(image_path: str, query: str, prompt: str):
    """

    """
    print(f"=== 开始-{image_path} ===")

    try:
        result = doubao_call_with_prompt(image_path, query, prompt)
        if result['success']:
            print(json.dumps(result, indent=4, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result