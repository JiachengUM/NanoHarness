from typing import Final

import pytest
import asyncio

from pydantic import BaseModel, Field

from nanoai.model.config import ModelName, create_client
from nanoai.model.vlm import image_from_path, avlm, avlm_stream, avlm_output_by_schema
from openai import AsyncOpenAI

models_to_test_uiagent: Final[list[ModelName]] = [
        ModelName.DOUBAO_SEED_1_6_VISION_250815,
        ModelName.DOUBAO_SEED_1_8_PREVIEW,
    ]

PNG_IMAGE_PATH = "tests/images/hehuiyan_seat_info.png"

class ButtonInfo(BaseModel):
    """按钮信息。"""
    name: str = Field(..., title="按钮名称", description="按钮的名称。")
    left: int = Field(..., title="左坐标", description="按钮的左坐标。")
    top: int = Field(..., title="上坐标", description="按钮的上坐标。")
    right: int = Field(..., title="右坐标", description="按钮的右坐标。")
    bottom: int = Field(..., title="下坐标", description="按钮的下坐标。")

from projects.uiagent.core.action import Action
# uiagent的输出结构,如果成功，可避免parse_action失败的问题。
class UITaskOutput(BaseModel):
    """UI任务的输出结构"""
    thought: str = Field(title="思考", description="如何完成用户任务的思考")
    actions: list[Action] = Field(title="动作列表", description="要执行的动作列表")

@pytest.mark.asyncio
@pytest.mark.parametrize("model", models_to_test_uiagent)
async def test_uiagent_output_by_schema(model: ModelName) -> None:
    '''
    1.背景，如果uiagent的输出结构成功，可避免parse_action失败的问题。1.8模型支持schema输出。 
    2.在简单schema情况下(ButtonInfo)，1.6和1.8都能成功。
    3.在复杂schema情况下(UITaskOutput)，1.6成功，1.8失败。。
    
    经调试发现：1.8模型在复杂schema情况下，会出现重复输出，出现幻觉。输出如下：
    message=ChatCompletionMessage(
    content='{"thought":"用户需要点击下一步按钮，当前界面底部有黄色的下一步按钮，对应已选择的09月22日今天16:30，2人，大厅的预订信息，现在执行点击操 
    作","actions":[{"name":"click","name":"click","name":"click","name":"click","name":"click","name":"click","name":"click","name":"click","name":"click","name":"c
    lick","name":"click","name":"click","name":"click","name":"click","name":"click","name":"click","name":"click","name":"click","name":"click","name":"click","nam
    e":"click","name":"click","name":"click",........
    一直重复
    '''
    
    print(f"\n\n测试相对简单的uiagent输出结构avlm_output_by_schema, 模型: {model}")
    client, _ = create_client(model, AsyncOpenAI)
    
    # 相对简单的schema
    query = "请返回图片中的下一步按钮的坐标。"
    print(f"Query: {query}")
    try:
        base64_image, image_format = image_from_path(PNG_IMAGE_PATH)
        res = await avlm_output_by_schema(query, base64_image, image_format, output_type=ButtonInfo, client=client, model=model)
        print(f"结果: {res}")
    except Exception as e:
        print(f"错误: {e}")


    print(f"\n\n测试相对复杂的uiagent输出结构avlm_output_by_schema, 模型: {model}")
    query = "点击下一步按钮"
    print(f"Query: {query}")
    try:
        base64_image, image_format = image_from_path(PNG_IMAGE_PATH)
        extra_body={ 
            # "reasoning_effort": "low", 
            "thinking": {
                # "type": "disabled" # 不使用深度思考能力
                "type": "enabled" # 默认使用深度思考能力
            },
        }
        res = await avlm_output_by_schema(query, base64_image, image_format, output_type=UITaskOutput, client=client, model=model, extra_body=extra_body)
        print(f"结果: {res}")
    except Exception as e:
        print(f"错误: {e}")

# ============= 主函数 =============
RUN_PYTEST: Final = False


async def amain_uiagent() -> None:
    """运行uiagent的输出结构测试"""
    for model in models_to_test_uiagent:
        try:
            await test_uiagent_output_by_schema(model)
        except Exception as e:
            print(f"测试uiagent输出结构avlm_output_by_schema, 模型: {model} 失败: {e}")

if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        pytest.main(["-vs", __file__])
    else:
        asyncio.run(amain_uiagent())
        