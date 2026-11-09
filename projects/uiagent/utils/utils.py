import base64
from io import BytesIO
from pathlib import Path
from typing import Any, Optional, Union
import re
import io
from PIL import Image
import requests
import aiohttp
from ui_tars.action_parser import (
    convert_point_to_coordinates,
    smart_resize,
    parse_action_to_structure_output,
)


def encode_image(image_source: Any) -> str:
    """
    将图片文件编码为Base64字符串

    Args:
        image_source: 图片文件路径或图片URL（字符串）或内存内图片文件或BytesIO对象

    Returns:
        Base64编码的图片字符串

    Raises:
        FileNotFoundError: 当图片文件不存在时
        ValueError: 当文件不是有效图片格式时或URL失效时
    """
    # 检查是否为URL（以http://或https://开头）
    if isinstance(image_source, BytesIO):
        return base64.b64encode(image_source.getvalue()).decode("utf-8")
    elif isinstance(image_source, Image.Image):
        buffer = io.BytesIO()
        format = image_source.format
        image_source.save(buffer, format=format)
        img_bytes = buffer.getvalue()
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return img_base64
    elif image_source.startswith(("http://", "https://")):
        # 处理URL逻辑
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        }
        try:
            response = requests.get(image_source, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise ValueError(f"URL请求失败: {str(e)}") from e

        # 验证图片类型
        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            raise ValueError(f"URL返回非图片类型: {content_type}")

        return base64.b64encode(response.content).decode("utf-8")
    elif isinstance(image_source, (Path, str)):
        # 处理文件路径逻辑
        image_source = Path(image_source)
        if not image_source.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_source}")

        # 检查文件扩展名
        valid_extensions = {".png", ".jpg", ".jpeg"}
        if image_source.suffix.lower() not in valid_extensions:
            raise ValueError(f"不支持的图片格式: {image_source.suffix}")

        with open(image_source, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    else:
        return base64.b64encode(image_source).decode("utf-8")

def parse_thought_and_action_content(text: str) -> tuple[str, str]:
    """解析思考和动作内容"""
    text = text.strip()
    if "<point>" in text:
        text = convert_point_to_coordinates(text)
    if "start_point=" in text:
        text = text.replace("start_point=", "start_box=")
    if "end_point=" in text:
        text = text.replace("end_point=", "end_box=")
    if "point=" in text:
        text = text.replace("point=", "start_box=")
    # 正则表达式匹配 Action 字符串
    if text.startswith("Thought:"):
        thought_pattern = r"Thought: (.+?)(?=\s*Action: |$)"
        thought_hint = "Thought: "
    elif text.startswith("Reflection:"):
        thought_pattern = r"Reflection: (.+?)Action_Summary: (.+?)(?=\s*Action: |$)"
        thought_hint = "Reflection: "
    elif text.startswith("Action_Summary:"):
        thought_pattern = r"Action_Summary: (.+?)(?=\s*Action: |$)"
        thought_hint = "Action_Summary: "
    else:
        thought_pattern = r"Thought: (.+?)(?=\s*Action: |$)"
        thought_hint = "Thought: "
    reflection, thought = None, ""
    thought_match = re.search(thought_pattern, text, re.DOTALL)
    if thought_match:
        if len(thought_match.groups()) == 1:
            thought = thought_match.group(1).strip()
        elif len(thought_match.groups()) == 2:
            thought = thought_match.group(2).strip()
            reflection = thought_match.group(1).strip()
    assert "Action:" in text
    action_content = text.split("Action: ")[-1]
    return thought, action_content


def parse_action(image: Union[str, Path, BytesIO], content_to_parse: str) -> list[dict]:
    if isinstance(image, str) and image.startswith("http"):
        response = requests.get(image, timeout=10)
        response.raise_for_status  # 检查请求是否成功
        # 打开图片
        image = Image.open(BytesIO(response.content))
    elif isinstance(image, (Path, str)):
        image = Image.open(image)
    elif isinstance(image, BytesIO):
        image = Image.open(image)
    original_image_width, original_image_height = image.size
    new_height, new_width = smart_resize(original_image_height, original_image_width)
    try:
        parsed_dict_list = parse_action_to_structure_output(
            content_to_parse,
            factor=1000,
            origin_resized_height=new_height,
            origin_resized_width=new_width,
            model_type="qwen25vl",
        )
    except Exception as e:
        print(f"解析动作失败: {e}")
        raise e
    return parsed_dict_list


async def a_download_url_image_to_memory(url: str) -> Optional[BytesIO]:
    try:
        # 设置请求头模拟浏览器访问
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # 发起 GET 请求并设置超时
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                # 📄 获取响应内容
                content = await response.read()
                response.raise_for_status()

                # 验证是否为图片（可选）
                content_type = response.headers.get("Content-Type", "")
                if not content_type.startswith("image/"):
                    print("警告：返回内容不是图片格式")
                    return None

                # 将二进制数据写入内存
                image_memory = BytesIO(content)

                # 验证图片有效性（可选）
                try:
                    img = Image.open(image_memory)
                    img.verify()
                    image_memory.seek(0)  # 重置指针位置
                except Exception as e:
                    print(f"图片验证失败: {e}")
                    return None

                return image_memory

    except aiohttp.ClientError as e:
        print(f"下载失败: {e}")
        return None
    except Exception as e:
        print(f"发生未知错误: {e}")
        return None
