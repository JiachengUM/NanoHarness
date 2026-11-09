"""
UITars 测试
运行: 
# 运行单个测试文件
pytest projects/uiagent/wei/test_workflow.py -s

# 运行单个测试函数
pytest projects/uiagent/wei/test_workflow.py::test_chaojie -s

"""

import time
import pytest
from typing import Literal

# 导入本地模块
from .prompt import (UI_TARS_PROMPT_chaojie_1, UI_TARS_PROMPT_DINGZUO, UI_TARS_PROMPT_DINGZUOREN_info)
from ..model.uitars import uitars_call
from .image_check import draw_rectangle_pillow
from .utils import parse_x_y, parse_action
from nanoai.model.config import create_client, ModelName
from volcenginesdkarkruntime import Ark

# 数据集目录
datasets_dir_chaojie = r"D:\yitu\2509\nanoai-ui-agent-datasets\chaojie"
datasets_dir_xinfaxian = r"D:\yitu\2509\nanoai-ui-agent-datasets\xinfaxian"
datasets_dir_car_meituan = r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan"
client, _ = create_client(ModelName.DOUBAO_1_5_UI_TARS_250428, Ark)
#验证：最简整体流程
@pytest.mark.parametrize("image_path, query, custom_prompt, prompt_type", [
    (f"{datasets_dir_chaojie}/001.jpg", "帮我在潮界订个座位", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #首页点搜索栏 correct!
    (f"{datasets_dir_chaojie}/015.jpg", "准备输入“潮界”进行搜索", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击搜索框输入文本 correct!
    (f"{datasets_dir_chaojie}/015.jpg", "已经输入“潮界”，开始搜索", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击搜索按钮 correct!
    (f"{datasets_dir_chaojie}/003.jpg", "选择第一家店（支持订座的）", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击第一家 correct!
    (f"{datasets_dir_chaojie}/004.jpg", "开始订座", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击订座 correct!
    (f"{datasets_dir_chaojie}/005.jpg", "日期选择明天", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击日期 correct!
    (f"{datasets_dir_chaojie}/005.jpg", "时间选择14：00", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击时间 correct!
    (f"{datasets_dir_chaojie}/005.jpg", "人数选择4人", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击人数 correct!
    (f"{datasets_dir_chaojie}/005.jpg", "就餐位置选择大厅", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击大厅 correct!
    (f"{datasets_dir_chaojie}/005.jpg", "点击下一步", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击下一步 correct!
    (f"{datasets_dir_chaojie}/012.jpg", "输入姓名:弋途", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击姓名输入框，内容为弋途 correct!
    (f"{datasets_dir_chaojie}/013.jpg", "确定订座", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击确定订座 correct!
    (f"{datasets_dir_chaojie}/014.jpg", "当前订座已完成，用户query为`帮我订个座`", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #订座完成，返回finished！ correct!
])
def test_chaojie(image_path: str, query: str, custom_prompt: str, prompt_type: str):
    """
    潮界订座的流程
    总结，单步推理很强，不涉及多action，均能正确完成。
    """
    print(f"=== 开始-{prompt_type} ===query:{query}===")

    try:
        result = uitars_call(client, image_path, query, custom_prompt, prompt_type)
        content = result.content
        print("模型输出：\n", content)

        # 解析坐标并标注
        try:
            x, y = parse_x_y(content)
            print(f"解析坐标: x={x}, y={y}")
            draw_rectangle_pillow(image_path=image_path, output_path="check.png", x=x, y=y, color="green", width=20)
        except Exception as pe:
            print(f"坐标解析或绘制失败: {pe}")
        print("\n")
        
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        raise  # 让pytest知道测试失败了

#验证：最简整体流程
@pytest.mark.parametrize("image_path, query, custom_prompt, prompt_type", [
    # (f"{datasets_dir_xinfaxian}/001.jpg", "帮我在新发现订个座位", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #首页点搜索栏 correct!
    # (f"{datasets_dir_xinfaxian}/002.jpg", "准备输入“新发现”", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击搜索框输入文本 correct!
    # (f"{datasets_dir_xinfaxian}/003.jpg", "已经输入“新发现”，选择第一个店铺列", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击列表第一个 correct!
    (f"{datasets_dir_xinfaxian}/004.jpg", "选择第一家店（非外卖店）", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击第一家 correct!
    # (f"{datasets_dir_xinfaxian}/005.jpg", "开始订座（若不支持，则结束）", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击订座 correct!
])
def test_xinfaxian(image_path: str, query: str, custom_prompt: str, prompt_type: str):
    """
    新发现订座的流程（不支持订座）
    总结，不给足够的信息，识别不出来当前页面不支持订座。而是进行向下滑动操作。
    """
    print(f"=== 开始-{prompt_type} ===query:{query}===")

    try:
        result = uitars_call(client, image_path, query, custom_prompt, prompt_type)
        content = result.content
        print("模型输出：\n", content)

        # 解析坐标并标注
        try:
            x, y = parse_x_y(content)
            print(f"解析坐标: x={x}, y={y}")
            draw_rectangle_pillow(image_path=image_path, output_path="check.png", x=x, y=y, color="green", width=20)
        except Exception as pe:
            print(f"坐标解析或绘制失败: {pe}")
        print("\n")
        
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        raise  # 让pytest知道测试失败了

@pytest.mark.parametrize("image_path, query, custom_prompt, prompt_type", [
    (f"{datasets_dir_car_meituan}/009.png", "五六七点的2个人", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #提示不支持订座
    # (f"{datasets_dir_car_meituan}/001.jpeg", "关闭当前页面", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #正确点击到位置
    # (f"{datasets_dir_car_meituan}/001.png", "开始订座", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #正确点击到位置 1280*720 655KB
    # (f"{datasets_dir_car_meituan}/001_compressed_1.png", "开始订座", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #正确点击到位置 1280*720 211KB
    # (f"{datasets_dir_car_meituan}/001_compressed_2.png", "开始订座", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #正确点击到位置 1280*720 167KB

    # (f"{datasets_dir_car_meituan}/001_resize.png", "开始订座", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #正确点击到位置 972*690 678KB
    # (f"{datasets_dir_car_meituan}/001_resize_1.png", "开始订座", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #正确点击到位置 604*690 228KB

    # (f"{datasets_dir_car_meituan}/002.png", "准备输入“新发现”", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击搜索框输入文本 correct!
    # (f"{datasets_dir_car_meituan}/003.png", "已经输入“新发现”，选择第一个店铺列", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击列表第一个 correct!
    # (f"{datasets_dir_car_meituan}/004.png", "选择第一家店（非外卖店）", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击第一家 correct!
    # (f"{datasets_dir_car_meituan}/005.png", "开始订座（若不支持，则结束）", UI_TARS_PROMPT_chaojie_1, "custom_prompt"), #点击订座 correct!
])
def test_car_meituan(image_path: str, query: str, custom_prompt: str, prompt_type: str):
    """
    新发现订座的流程（不支持订座）
    总结，不给足够的信息，识别不出来当前页面不支持订座。而是进行向下滑动操作。
    """
    print(f"=== 开始-{prompt_type} ===query:{query}===")

    try:
        model_start_time = time.perf_counter()
        result = uitars_call(client, image_path, query, custom_prompt, prompt_type)
        model_end_time = time.perf_counter()
        model_elapsed_time = model_end_time - model_start_time
        content = result.content
        print("模型输出：\n", content)
        print(f"模型推理耗时: {model_elapsed_time:.4f} 秒")
# 解析action
        actions = parse_action(result)
        print(f"解析到的actions: {actions}")
        
        # 断言验证
        assert len(actions) > 0, "应该至少有一个action"
        assert actions[0].get('action') == 'click', f"期望click动作，实际: {actions[0].get('action')}"
        print("✅ 测试通过")
        
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        raise  # 让pytest知道测试失败了 

#验证：最简整体流程
@pytest.mark.parametrize("image_path, query, custom_prompt, prompt_type", [
    # (r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\verify_dingzuo.jpg", "帮我订座", UI_TARS_PROMPT_DINGZUO, "custom_prompt"), #有订座
    (r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\dingzuo_unsupported.jpg", "帮我订座", UI_TARS_PROMPT_DINGZUO, "custom_prompt"), #无订座
])
def test_dingzuo(image_path: str, query: str, custom_prompt: str, prompt_type: str):
    """
    判别订座
    """
    print(f"=== 开始-{prompt_type} ===query:{query}===")

    try:
        result = uitars_call(client, image_path, query, custom_prompt, prompt_type)
        content = result.content
        print("模型输出：\n", content)

        # 解析坐标并标注
        try:
            x, y = parse_x_y(content)
            print(f"解析坐标: x={x}, y={y}")
            draw_rectangle_pillow(image_path=image_path, output_path="check.png", x=x, y=y, color="green", width=20)
        except Exception as pe:
            print(f"坐标解析或绘制失败: {pe}")
        print("\n")
        
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        raise  # 让pytest知道测试失败了

    #验证：最简整体流程
@pytest.mark.parametrize("image_path, query, custom_prompt, prompt_type", [
    (r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\dingzuoren_info.png", "返回上一步", UI_TARS_PROMPT_DINGZUOREN_info, "custom_prompt"), #上一步
    (r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\dingzuoren_info.png", "用餐人是张三", UI_TARS_PROMPT_DINGZUOREN_info, "custom_prompt"), #输入用餐人信息
    (r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\dingzuoren_info.png", "填写用餐人", UI_TARS_PROMPT_DINGZUOREN_info, "custom_prompt"), #输入用餐人信息
    (r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\dingzuoren_info.png", "电话号码是138xxxxxxxx", UI_TARS_PROMPT_DINGZUOREN_info, "custom_prompt"), #输入用餐人信息
    (r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\dingzuoren_info.png", "备注选第一个", UI_TARS_PROMPT_DINGZUOREN_info, "custom_prompt"), #输入用餐人信息
    (r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\dingzuoren_info.png", "备注需要宝宝椅", UI_TARS_PROMPT_DINGZUOREN_info, "custom_prompt"), #输入用餐人信息
    (r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\dingzuoren_info.png", "同意协议", UI_TARS_PROMPT_DINGZUOREN_info, "custom_prompt"), #输入用餐人信息
    (r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\dingzuoren_info.png", "确认订座", UI_TARS_PROMPT_DINGZUOREN_info, "custom_prompt"), #输入用餐人信息

])
def test_dingzuoren_info(image_path: str, query: str, custom_prompt: str, prompt_type: str):
    """
    判别订座
    """
    print(f"=== 开始-{prompt_type} ===query:{query}===")

    try:
        result = uitars_call(client, image_path, query, custom_prompt, prompt_type)
        content = result.content
        print("模型输出：\n", content)

        # 解析坐标并标注
        try:
            x, y = parse_x_y(content)
            print(f"解析坐标: x={x}, y={y}")
            draw_rectangle_pillow(image_path=image_path, output_path="check.png", x=x, y=y, color="green", width=20)
        except Exception as pe:
            print(f"坐标解析或绘制失败: {pe}")
        print("\n")
        
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        raise  # 让pytest知道测试失败了