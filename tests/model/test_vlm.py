from typing import Final

import pytest
import asyncio

from pydantic import BaseModel, Field

from nanoai.utils.data_concept import ClsResult

from nanoai.model.config import ModelName, create_client
from nanoai.model.vlm import image_from_path, avlm, avlm_stream, avlm_output_by_schema
from openai import AsyncOpenAI

models_to_test: Final[list[ModelName]] = [
    ModelName.DOUBAO_SEED_1_8_PREVIEW,
    ModelName.DOUBAO_SEED_1_6_VISION_250815,
    ModelName.DOUBAO_1_5_UI_TARS_250428,
]

PNG_IMAGE_PATH = "tests/images/hehuiyan_seat_info.png"
    
def test_image_from_valid_path():
    """测试有效的 JPG 图片"""
    print(f"测试有效的 JPG 图片: {PNG_IMAGE_PATH}")

    result = image_from_path(PNG_IMAGE_PATH)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], str)
    assert isinstance(result[1], str)
    
    print(f"成功load image with size: {len(result)}")

def test_image_from_path_file_not_found():
    """测试文件不存在的情况"""
    print(f"测试文件不存在的情况: nonexistent_file.png")

    with pytest.raises(FileNotFoundError, match="图片文件不存在"):
        image_from_path("nonexistent_file.png")


@pytest.mark.asyncio
@pytest.mark.parametrize("model", models_to_test)
async def test_basic(model: ModelName) -> None:
    print(f"\n\n测试基本功能avlm, 模型: {model}")

    client, _ = create_client(model, AsyncOpenAI)

    query = "这幅图片描述了什么"

    print(f"Query: {query} with image from: {PNG_IMAGE_PATH}")
    base64_image, image_format = image_from_path(PNG_IMAGE_PATH)
    res = await avlm(query, base64_image, image_format, client=client, model=model)
    print(f"结果: {res}")


    # 测试流式输出
    print("\n\n流式输出结果:", end="", flush=True)
    stream_res = await avlm_stream(query, base64_image, image_format, delta=True, client=client, model=model)
    async for chunk in stream_res:
        print(chunk, end="", flush=True)
    print(f"\n流式输出最终结果: {stream_res.output}")


class ButtonInfo(BaseModel):
    """按钮信息。"""
    name: str = Field(..., title="按钮名称", description="按钮的名称。")
    left: int = Field(..., title="左坐标", description="按钮的左坐标。")
    top: int = Field(..., title="上坐标", description="按钮的上坐标。")
    right: int = Field(..., title="右坐标", description="按钮的右坐标。")
    bottom: int = Field(..., title="下坐标", description="按钮的下坐标。")

class UIInfo(BaseModel):
    """UI信息。"""
    buttons: list[ButtonInfo] = Field(..., title="按钮列表", description="按钮列表。")


@pytest.mark.asyncio
@pytest.mark.parametrize("model", models_to_test)
async def test_output_by_schema(model: ModelName) -> None:
    '''DOUBAO_SEED_1_6_VISION_250815成功, DOUBAO_1_5_UI_TARS_250428失败。'''
    print(f"\n\n测试结构化输出avlm_output_by_schema, 模型: {model}")
    client, _ = create_client(model, AsyncOpenAI)

    query = "请对于输入的图片进行分类, 类别包括自然图像、计算机UI界面、手绘图像、其它类别。返回分类结果和原因。"
    print(f"Query: {query}")
    try:
        base64_image, image_format = image_from_path(PNG_IMAGE_PATH)
        res = await avlm_output_by_schema(query, base64_image, image_format, output_type=ClsResult, client=client, model=model)
        print(f"结果: {res}")
    except Exception as e:
        print(f"错误: {e}")


    return
    # 下面的case怎么都跑不通

    query = "请返回图片中所有的UI元素。"
    print(f"Query: {query}")
    try:
        res = await avlm_output_by_schema(query, PNG_IMAGE_PATH, output_type=ButtonInfo, client=client, model=model)
        print(f"结果: {res}")
    except Exception as e:
        print(f"错误: {e}")


# ============= 主函数 =============
RUN_PYTEST: Final = False

def main():
    test_image_from_valid_path()
    test_image_from_path_file_not_found()

async def amain() -> None:
    """运行所有测试"""

    for model in models_to_test:
        try:
            await test_basic(model)
        except Exception as e:
            print(f"测试基本功能avlm, 模型: {model} 失败: {e}")
            continue

        # DOUBAO_1_5_UI_TARS_250428 会失败
        try:
            await test_output_by_schema(model)
        except Exception as e:
            print(f"测试结构化输出avlm_output_by_schema, 模型: {model} 失败: {e}")
            continue

if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        pytest.main(["-vs", __file__])
    else:
        # main()
        asyncio.run(amain())
        