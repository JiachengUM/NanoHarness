"""
UITars 模块的 pytest 测试用例
"""
import os
from typing import Final

import pytest

from projects.uiagent.model.uitars import uitars_call, encode_image
from nanoai.model.config import create_client, ModelName
from volcenginesdkarkruntime import Ark

# 获取项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# 获取uiagent目录
UIAGENT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_create_client():
    """测试客户端创建"""
    print("测试客户端创建")
    try:
        client, _ = create_client(ModelName.DOUBAO_1_5_UI_TARS_250428, Ark)
        print(f"创建成功：{type(client)}")
    except Exception as e:
        print(f"创建失败：{e}")


def test_uitars_call_with_real_image():
    """测试使用真实图片调用UITars"""
    print("测试使用真实图片调用UITars")
    try:
        client, _ = create_client(ModelName.DOUBAO_1_5_UI_TARS_250428, Ark)
        # 使用绝对路径
        image_path = os.path.join(UIAGENT_ROOT, "datasets", "hehuiyan", "004.png")
        print(f"图片路径: {image_path}")
        result = uitars_call(client, image_path, "开始订座", custom_prompt=None, prompt_type="official")
        print(f"调用成功：\n{result.model_dump()}")
    except Exception as e:
        print(f"调用失败：\n{e}")


def test_uitars_call_with_custom_prompt():
    """测试使用自定义提示词调用UITars"""
    try:
        client, _ = create_client(ModelName.DOUBAO_1_5_UI_TARS_250428, Ark)
        custom_prompt = "请分析图片中的UI元素，并给出详细按钮：{instruction}"
        # 使用绝对路径
        image_path = os.path.join(UIAGENT_ROOT, "datasets", "hehuiyan", "004.png")
        result = uitars_call(client, image_path, "开始分析", custom_prompt=custom_prompt, prompt_type="custom_prompt")
        print(f"调用成功：\n{result.model_dump()}")
    except Exception as e:
        print(f"调用失败：\n{e}")


def test_encode_image_with_url():
    """测试编码图片URL"""
    try:
        image_url = "http://47.117.182.61/test_result_img/result_2025-10-15_22-18-41/prefix_3_action_click.png"
        image_base64 = encode_image(image_url)
        print(f"编码图片URL成功：\n{image_base64[:20]}...")
    except Exception as e:
        print(f"编码失败：\n{e}")


def test_encode_image_with_bad_url():
    """测试编码错误的图片URL"""
    try:
        image_url = "http://47.117.182.61/test_result_img/result_2025-10-15_22-18-41/prefix_3_action_click.jpg"
        image_base64 = encode_image(image_url)
        print(f"编码图片URL成功：\n{image_base64[:20]}...")
    except Exception as e:
        print(f"编码失败：\n{e}")


def test_encode_image_with_file():
    """测试编码图片文件"""
    try:
        # 使用绝对路径
        image_file = os.path.join(UIAGENT_ROOT, "datasets", "hehuiyan", "004.png")
        print(f"图片路径: {image_file}")
        image_base64 = encode_image(image_file)
        print(f"编码图片文件成功：\n{image_base64[:20]}...")
    except Exception as e:
        print(f"编码失败：\n{e}")

# ============= 主函数 =============
RUN_PYTEST: Final = False

def main():
    
    test_create_client()
    
    test_uitars_call_with_real_image()
    
    test_uitars_call_with_custom_prompt()
    
    test_encode_image_with_url()
    
    test_encode_image_with_bad_url()
    
    test_encode_image_with_file()
    

if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        pytest.main(["-vs", __file__])
    else:
        main()
