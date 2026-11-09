from projects.uiagent.coffee_purchase.datasets import DATASET_ROOT
from projects.uiagent.coffee_purchase.workflow import CoffeePurchaseUiFlow, CoffeePurchaseStep
from pydantic import BaseModel
from typing import Any
from enum import StrEnum
from projects.uiagent.core.flow_data import _END_STEP

class TaskType(StrEnum):
    UI = "ui"
    NL = "nl"

class WorkflowDatas(BaseModel):
    name: str
    description: str
    datas: list[dict[str, Any]]

id_1_data =[
    {
        "comment": "瑞幸点咖啡全流程",
        "query": "帮我在维璟印象城B1店自提一杯咖啡",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "提取到咖啡名",
        "expect_next_step": CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP,
        "task_type": TaskType.NL,
    },    
    {
        "comment": "选择自取",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "点击到店取按钮",
        "expect_next_step": CoffeePurchaseStep.SELECT_ADDRESS,
        "task_type": TaskType.UI,
    },
    {
        "comment": "假设第一次使用瑞幸点咖啡，选择自取，需要选店铺地址",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "002_选门店01_维璟.jpg"),
        "expected_result": "直接点击对应的店铺",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },
    
]
ID_1 = WorkflowDatas(
    name="CASE_1，测试用餐方式选择，状态跳转，选店铺地址",
    description="测试用餐方式选择，状态跳转，选店铺地址",
    datas=id_1_data,
)

id_2_data =[
    {
        "comment": "瑞幸点咖啡全流程",
        "query": "帮我自提一杯咖啡",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "提取到咖啡名",
        "expect_next_step": CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP,
        "task_type": TaskType.NL,
    },    
    {
        "comment": "选择自取",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "点击到店取按钮",
        "expect_next_step": CoffeePurchaseStep.SELECT_ADDRESS,
        "task_type": TaskType.UI,
    },
    {
        "comment": "假设第一次使用瑞幸点咖啡，选择自取，需要选店铺地址",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "002_选门店01_维璟.jpg"),
        "expected_result": "询问用户要选择哪个店铺",
        "expect_next_step": CoffeePurchaseStep.SELECT_ADDRESS,
        "task_type": TaskType.UI,
    },    
]
ID_2 = WorkflowDatas(
    name="CASE_2，测试用餐方式选择，状态跳转，选店铺地址",
    description="测试用餐方式选择，状态跳转，选店铺地址",
    datas=id_2_data,
)

id_3_data =[
    {
        "comment": "瑞幸点咖啡全流程",
        "query": "帮我自提一杯咖啡",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "提取到咖啡名",
        "expect_next_step": CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP,
        "task_type": TaskType.NL,
    },    
    {
        "comment": "选择自取",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "点击到店取按钮",
        "expect_next_step": CoffeePurchaseStep.SELECT_ADDRESS,
        "task_type": TaskType.UI,
    },
    {
        "comment": "假设第一次使用瑞幸点咖啡，选择自取，需要选店铺地址",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "002_选门店01_维璟.jpg"),
        "expected_result": "询问用户要选择哪个店铺",
        "expect_next_step": CoffeePurchaseStep.SELECT_ADDRESS,
        "task_type": TaskType.UI,
    },   
    {
        "comment": "上一步问我选哪个店铺，我回答了第一家，现在继续点咖啡",
        "query": "第一家吧",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "002_选门店01_维璟.jpg"),
        "expected_result": "点击第一家",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.NL,
    },    
    
]
ID_3 = WorkflowDatas(
    name="CASE_3，测试用户回答后，继续点咖啡",
    description="测试用户回答后，继续点咖啡",
    datas=id_3_data,
)

id_4_data = [
    {
        "comment": "瑞幸点咖啡全流程",
        "query": "帮我在维璟印象城B1店自提一杯咖啡",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "提取到咖啡名",
        "expect_next_step": CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP,
        "task_type": TaskType.NL,
    },    
    {
        "comment": "选择自取",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "点击到店取按钮",
        "expect_next_step": CoffeePurchaseStep.SELECT_ADDRESS,
        "task_type": TaskType.UI,
    },
    {
        "comment": "假设第一次使用瑞幸点咖啡，选择自取，需要选店铺地址",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "002_选门店01_维璟.jpg"),
        "expected_result": "直接点击对应的店铺",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入菜单页面，没有咖啡信息",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "003_菜单选品02_主页.jpg"),
        "expected_result": "点击搜索框",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },    
    {
        "comment": "询问商品名",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "004_键盘输入.jpg"),
        "expected_result": "询问用户要选择哪个商品",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },
]
ID_4 = WorkflowDatas(
    name="CASE_4，测试无咖啡信息，可能先去问或者店家名字",
    description="测试无咖啡信息，可能先去问或者店家名字",
    datas=id_4_data,
)


id_5_data =[
    {
        "comment": "瑞幸点咖啡全流程",
        "query": "帮我在维璟印象城B1店自提一杯咖啡",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "提取到咖啡名",
        "expect_next_step": CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP,
        "task_type": TaskType.NL,
    },    
    {
        "comment": "选择自取",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "点击到店取按钮",
        "expect_next_step": CoffeePurchaseStep.SELECT_ADDRESS,
        "task_type": TaskType.UI,
    },
    {
        "comment": "假设第一次使用瑞幸点咖啡，选择自取，需要选店铺地址",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "002_选门店01_维璟.jpg"),
        "expected_result": "直接点击对应的店铺",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入菜单页面，没有咖啡信息",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "003_菜单选品02_主页.jpg"),
        "expected_result": "点击搜索框",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },    
    {
        "comment": "询问商品名",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "004_键盘输入.jpg"),
        "expected_result": "询问用户要选择哪个商品",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },      
    {
        "comment": "询问商品名,这一步提供商品信息",
        "query": "我要标准美式",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "004_键盘输入.jpg"),
        "expected_result": "没有咖啡信息或者为‘咖啡’时，询问",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.NL,
    },     
]
ID_5 = WorkflowDatas(
    name="CASE_5，测试无咖啡信息，可能先去问或者店家名字，提供商品信息",
    description="测试无咖啡信息，可能先去问或者店家名字，提供商品信息",
    datas=id_5_data,
)

id_6_data =[
    {
        "comment": "瑞幸点咖啡全流程",
        "query": "帮我在维璟印象城B1店自提一杯标准美式",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "提取到用餐方式",
        "expect_next_step": CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP,
        "task_type": TaskType.NL,
    },    
    {
        "comment": "选择自取",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "点击到店取按钮",
        "expect_next_step": CoffeePurchaseStep.SELECT_ADDRESS,
        "task_type": TaskType.UI,
    },
    {
        "comment": "假设第一次使用瑞幸点咖啡，选择自取，需要选店铺地址",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "002_选门店01_维璟.jpg"),
        "expected_result": "直接点击对应的店铺",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入菜单页面，没有咖啡信息",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "003_菜单选品02_主页.jpg"),
        "expected_result": "点击搜索框",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },    
    {
        "comment": "上一步点了搜索框，这一步type输入",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "004_键盘输入.jpg"),
        "expected_result": "type输入",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },      
    {
        "comment": "上一步type输入了标准美式，这一步去点击搜索按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "005_键盘输入_标准美式.jpg"),
        "expected_result": "点击搜索按钮",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },     
    {
        "comment": "上一步点击了搜索按钮，这一步去点击商品按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "006_标准美式_选商品.png"),
        "expected_result": "点击标准美式商品按钮,状态跳转选属性",
        "expect_next_step": CoffeePurchaseStep.SELECT_SPEC,
        "task_type": TaskType.UI,
    },
]
ID_6 = WorkflowDatas(
    name="CASE_6，有取餐，有店，有商品，测试点击搜索，跳转商品属性",
    description="有取餐，有店，有商品，测试点击搜索，跳转商品属性",
    datas=id_6_data,
)


id_7_data =[
    {
        "comment": "瑞幸点咖啡全流程",
        "query": "帮我在维璟印象城B1店自提一杯标准美式",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "提取到用餐方式",
        "expect_next_step": CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP,
        "task_type": TaskType.NL,
    },    
    {
        "comment": "选择自取",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "点击到店取按钮",
        "expect_next_step": CoffeePurchaseStep.SELECT_ADDRESS,
        "task_type": TaskType.UI,
    },
    {
        "comment": "假设第一次使用瑞幸点咖啡，选择自取，需要选店铺地址",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "002_选门店01_维璟.jpg"),
        "expected_result": "直接点击对应的店铺",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入菜单页面，没有咖啡信息",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "003_菜单选品02_主页.jpg"),
        "expected_result": "点击搜索框",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },    
    {
        "comment": "上一步点了搜索框，这一步type输入",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "004_键盘输入.jpg"),
        "expected_result": "type输入",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },      
    {
        "comment": "上一步type输入了标准美式，这一步去点击搜索按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "005_键盘输入_标准美式.jpg"),
        "expected_result": "点击搜索按钮",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },     
    {
        "comment": "上一步点击了搜索按钮，这一步去点击商品按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "006_标准美式_选商品.png"),
        "expected_result": "点击标准美式商品按钮,状态跳转选属性",
        "expect_next_step": CoffeePurchaseStep.SELECT_SPEC,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点击了商品属性按钮，这一步发现没有更多属性，可能要交互操作",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "007_标准美式_选规格.png"),
        "expected_result": "无更多属性，可能要交互操作",
        "expect_next_step": CoffeePurchaseStep.SELECT_SPEC,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点击了商品属性按钮，这一步发现没有更多属性，可能要交互操作",
        "query": "可以，就这样吧",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "007_标准美式_选规格.png"),
        "expected_result": "无更多属性，可能要交互操作",
        "expect_next_step": CoffeePurchaseStep.CONFIRM_ORDER,
        "task_type": TaskType.NL,
    },
]
ID_7 = WorkflowDatas(
    name="CASE_7，有取餐,有店,有商品,测试点击商品属性",
    description="有取餐,有店,有商品,测试点击商品属性",
    datas=id_7_data,
)

id_8_data =[
    {
        "comment": "瑞幸点咖啡全流程",
        "query": "帮我在红点城店自提一杯标准美式",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "提取到用餐方式",
        "expect_next_step": CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP,
        "task_type": TaskType.NL,
    },    
    {
        "comment": "选择自取",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "001_首页.jpg"),
        "expected_result": "点击到店取按钮",
        "expect_next_step": CoffeePurchaseStep.SELECT_ADDRESS,
        "task_type": TaskType.UI,
    },
    {
        "comment": "假设直接跳转菜单页弹窗，",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "003_菜单选品01_弹窗.jpg"),
        "expected_result": "直接点击对应的店铺",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入菜单页面，没有咖啡信息",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "003_菜单选品02_主页.jpg"),
        "expected_result": "点击搜索框",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },    
    {
        "comment": "上一步点了搜索框，这一步type输入",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "004_键盘输入.jpg"),
        "expected_result": "type输入",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },      
    {
        "comment": "上一步type输入了标准美式，这一步去点击搜索按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "005_键盘输入_标准美式.jpg"),
        "expected_result": "点击搜索按钮",
        "expect_next_step": CoffeePurchaseStep.SELECT_PRODUCT,
        "task_type": TaskType.UI,
    },     
    {
        "comment": "上一步点击了搜索按钮，这一步去点击商品按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "006_标准美式_选商品.png"),
        "expected_result": "点击标准美式商品按钮,状态跳转选属性",
        "expect_next_step": CoffeePurchaseStep.SELECT_SPEC,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点击了商品属性按钮，这一步发现没有更多属性，可能要交互操作",
        "query": "",
        "image_path": str(DATASET_ROOT /"coffee" / "images" / "007_标准美式_选规格.png"),
        "expected_result": "无更多属性，可能要交互操作",
        "expect_next_step": CoffeePurchaseStep.SELECT_SPEC,
        "task_type": TaskType.UI,
    },
    # {
    #     "comment": "上一步点击了商品属性按钮，这一步发现没有更多属性，可能要交互操作",
    #     "query": "可以，就这样吧",
    #     "image_path": str(DATASET_ROOT /"coffee" / "images" / "007_标准美式_选规格.png"),
    #     "expected_result": "无更多属性，可能要交互操作",
    #     "expect_next_step": CoffeePurchaseStep.CONFIRM_ORDER,
    #     "task_type": TaskType.NL,
    # },
]
ID_8 = WorkflowDatas(
    name="CASE_8，有取餐,有店,有商品,测试点击商品属性",
    description="有取餐,有店,有商品,测试点击商品属性",
    datas=id_8_data,
)
if __name__ == "__main__":
    P0 = [ID_1, ID_2, ID_3, ID_4, ID_5, ID_6]

    from nanoai.utils.async_utils import amap
    import asyncio
    from projects.uiagent.coffee_purchase.test_workflow import test_normal_workflow
    Test = [ID_8]
    for workflow_case in Test:
        asyncio.run(test_normal_workflow(CoffeePurchaseUiFlow(), workflow_case, debug=True))

