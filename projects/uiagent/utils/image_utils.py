import base64
from io import BytesIO
from PIL import Image
import tempfile


def get_image_dimensions(base64_string):
    """
    从base64字符串解析图片宽高

    Args:
        base64_string (str): 图片的base64编码字符串

    Returns:
        tuple: (width, height) 图片的宽高
    """
    # 如果base64字符串包含data URI前缀，则去除前缀
    if base64_string.startswith('data:image'):
        base64_string = base64_string.split(',')[1]

    # 解码base64字符串
    image_data = base64.b64decode(base64_string)

    # 创建BytesIO对象并加载图片
    image_buffer = BytesIO(image_data)
    image = Image.open(image_buffer)

    # 获取图片尺寸
    width, height = image.size

    return width, height


def base64_to_bytes(base64_string: str) -> bytes:
    """
    将base64编码的字符串转换为二进制数据

    Args:
        base64_string (str): base64编码的字符串

    Returns:
        bytes: 解码后的二进制数据
    """
    # 如果base64字符串包含data URI前缀，则移除前缀
    if base64_string.startswith('data:'):
        # 找到第一个逗号后的内容
        base64_string = base64_string.split(',', 1)[1]

    # 解码base64字符串为二进制数据
    binary_data = base64.b64decode(base64_string)
    return binary_data


def base64_to_temp_file(base64_string: str, suffix: str = '.png') -> str:
    """
    将base64编码的图片保存为临时文件并返回路径

    Args:
        base64_string: base64编码的图片数据
        suffix: 文件后缀名，默认为.png

    Returns:
        临时文件的路径
    """
    # 如果base64字符串包含data URI前缀，需要先移除
    if ',' in base64_string:
        base64_string = base64_string.split(',')[1]

    # 解码base64数据
    image_data = base64.b64decode(base64_string)

    # 创建临时文件
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
        temp_file.write(image_data)
        temp_path = temp_file.name

    return temp_path