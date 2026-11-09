"""
UITars 测试
运行: 
# 运行单个测试文件
pytest projects/uiagent/wei/test_workflow_coffee.py -s

# 运行单个测试函数
pytest projects/uiagent/wei/test_workflow_coffee.py::test_coffee -s
"""

import pytest
from typing import Literal
from nanoai.model.config import create_client, ModelName
from volcenginesdkarkruntime import Ark
# 导入本地模块
from .prompt import UI_TARS_PROMPT_coffee
from ..model.uitars import uitars_call
from .image_check import draw_rectangle_pillow
from .utils import parse_x_y

# 数据集目录
datasets_dir_coffee = r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\coffee"

client, _ = create_client(ModelName.DOUBAO_1_5_UI_TARS_250428, Ark)
#验证：最简整体流程
@pytest.mark.parametrize("image_path, query, custom_prompt, prompt_type", [
    (f"{datasets_dir_coffee}/首页.jpg", "我要到店自提", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/首页.jpg", "点击外卖配送", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/首页.jpg", "到店自取个咖啡", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/选门店_001.jpg", "选第一家店", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/选门店_001.jpg", "搜索红点城中心店", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/选地址_001.jpg", "选第一个地址", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/选地址_001.jpg", "新建一个地址", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/选品_001.jpg", "选择第一个维璟", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/选品_002.jpg", "搜一个冰美式", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/选品_003.jpg", "选择小桑葚大杯", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/商品属性页_001.jpg", "冰的，标准糖", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/商品属性页_002.jpg", "加入购物车", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/商品属性页_003.jpg", "立即购买", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/商品属性_004.jpg", "不要下料，立即购买", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/备注_001.jpg", "需要无接触配送", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/确认订单_004.jpg", "更改优惠", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/更改优惠_001.jpg", "选择优惠券", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/更改支付_001.jpg", "用钱包账户支付", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/确认订单_001.jpg", "加购第一个", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/确认订单_002.jpg", "加购一个奶皮子", UI_TARS_PROMPT_coffee, "custom_prompt"),
    (f"{datasets_dir_coffee}/确认订单_003.jpg", "我需要加备注", UI_TARS_PROMPT_coffee, "custom_prompt"),
])
def test_coffee(image_path: str, query: str, custom_prompt: str, prompt_type: Literal["official","custom_prompt"]):
    """
    潮界订座的流程
    总结，单步推理很强，不涉及多action，均能正确完成。
    """
    print(f"=== 开始-{prompt_type} ===query:{query}===")

    try:
        result = uitars_call(client,image_path, query, custom_prompt, prompt_type)
        content = result.content
        print("模型输出：\n", content)

        # 解析坐标并标注
        try:
            x, y = parse_x_y(content or "")
            print(f"解析坐标: x={x}, y={y}")
            draw_rectangle_pillow(image_path=image_path, output_path="check.png", x=x, y=y, color="green", width=20)
        except Exception as pe:
            print(f"坐标解析或绘制失败: {pe}")
        print("\n")
        
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        raise  # 让pytest知道测试失败了

