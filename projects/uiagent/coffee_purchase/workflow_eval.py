from projects.uiagent.core.test_utils import Environment
import asyncio
from typing import Final, Any
from projects.uiagent.core.uiflow import run_ui_step
from projects.uiagent.coffee_purchase.datasets import DATASET_ROOT
from rich import print
from projects.uiagent.coffee_purchase.workflow import ( 
    CoffeePurchaseStep, 
    CoffeePurchaseUiFlow, 
    Product_Spec,
    SelectSpecStep,
    ConfirmIntent,
    AddressInfo,
    TakeoutOrPickupInfo,
    ProductName
    
    
)
from projects.uiagent.core.flow_data import MiddleInfoType

IMAGE_ROOT = DATASET_ROOT / "coffee" / "images"

TEST_CASES: Final[dict[CoffeePurchaseStep, list[dict[str, Any]]]] = {

    CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP: [
        {
            "image": "000_首页广告.png",
            "info": TakeoutOrPickupInfo(name="自提"),
            "expected_result": "关闭弹窗",
        },
        {
            "image": "001_首页.jpg",
            "info": TakeoutOrPickupInfo(name="自提"),
            "expected_result": "点击到店取按钮",
        },
        {
            "image": "001_首页.jpg",
            "info": TakeoutOrPickupInfo(name=None),
            "expected_result": "点击到店取按钮",
        },
    ],

    CoffeePurchaseStep.SELECT_ADDRESS: [
        {
            "image": "002_0_送货上门_有默认地址.jpg",
            "info": AddressInfo(
                name="平金中心1号楼1605",
                scratchpad="刚刚点击了菜单页的定位信息入口，姓名为刘先生"
            ),
            "expected_result": "点击左上角定位信息入口按钮，去外送地址页面",
        },
        {
            "image": "002_0_送货上门_存在地址.jpg",
            "info": AddressInfo(
                name="平金中心1号楼1605",
                scratchpad="刚刚点击了菜单页的定位信息入口，姓名为刘先生"
            ),
            "expected_result": "页面一致，直接选择对应存在的地址",
        },
        {
            "image": "002_选门店01_维璟.jpg",
            "info": AddressInfo(
                name="维璟印象城店",
                scratchpad=None
            ),
            "expected_result": "直接点击已有的门店",
            
        },
        {
            "image": "002_0_送货上门_选地址_001.jpg",
            "info": AddressInfo(
                name="平金中心1号楼",
                scratchpad="刚刚点击了菜单页的定位信息入口，姓名为测试先生"
            ),
            "expected_result": "预计去点新增收货地址按钮，去新增收货地址页面",
        },
    ],
    CoffeePurchaseStep.SELECT_PRODUCT: [
        {
            "image": "003_菜单选品02_主页.jpg",
            "info": ProductName(name="奶皮子拿铁"),
            "expected_result": "点击对应的商品名or 点搜索框",
        },
    ],
    CoffeePurchaseStep.SELECT_SPEC: [
        {
            "image": "007_标准美式_选规格.png",
            "info": {
                # SelectSpecStep.EInfo.CONFIRM_INTENT: ConfirmIntent(is_confirmed=False),
                SelectSpecStep.EInfo.PRODUCT_SPEC: Product_Spec(
                    cup_size="大杯", 
                    quantity=2, 
                    sugar="少少甜"
                )
            },
            "expected_result": "点击对应的属性，少少糖",
        },
        {
            "image": "007_pad版_选规格_部分展示.png",
            "info": {
                # SelectSpecStep.EInfo.CONFIRM_INTENT: ConfirmIntent(is_confirmed=False),
                SelectSpecStep.EInfo.PRODUCT_SPEC: Product_Spec(
                    cup_size="大杯", 
                    quantity=1, 
                    sugar="少少甜"
                )
            },
            "expected_result": "无更多属性，去上下拖拽找信息",
        },
        {
            "image": "007_pad版_选规格_选择完整.png",
            "info": {
                # SelectSpecStep.EInfo.CONFIRM_INTENT: ConfirmIntent(is_confirmed=False),
                SelectSpecStep.EInfo.PRODUCT_SPEC: Product_Spec(
                    cup_size="大杯", 
                    quantity=2, 
                    sugar="少少甜"
                )
            },
            "expected_result": "已满足用户需求，去询问用户是否确认or直接去结账，实际继续去上下滑动找信息去了。",
        },
        {
            "image": "007_标准美式_选规格.png",
            "info": {
                # SelectSpecStep.EInfo.CONFIRM_INTENT: ConfirmIntent(is_confirmed=False),
                SelectSpecStep.EInfo.PRODUCT_SPEC: Product_Spec(
                    cup_size="大杯", 
                    quantity=1, 
                    temperature="冰",
                    sugar="不另外加糖"
                )
            },
            "expected_result": "已满足用户需求，去询问用户是否确认or直接去结账",
        },
    ],
    CoffeePurchaseStep.CONFIRM_ORDER: [

        {
            "image": "008_标准美式_确认订单_弹窗.jpg",
            "info": None,
            "expected_result": "关闭弹窗",
        },
        {
            "image": "009_标准美式_确认订单_001.png",
            "info": None,
            "expected_result": "点击订单支付按钮",
        },
        {
            "image": "010_确认订单_弹窗.png",
            "info": None,
            "expected_result": "点击`二维码支付`",
        },
        {
            "image": "011_确认订单_二维码.png",
            "info": None,
            "expected_result": "结束任务，并告知用户直接扫码支付",
        },
    ],
}

async def test_workflow_ui_step(
    step: CoffeePurchaseStep, 
    image_path: str,
    info: MiddleInfoType | None
) -> None:
    """测试单个步骤"""
    print(f"\n==============test_workflow_ui_step: step: {step}=====================")
    print(f"image: {image_path}")
    print(f"info: {info}")
    
    result = await run_ui_step(
        CoffeePurchaseUiFlow, 
        image_path, 
        step, 
        info=info, 
    )
    print(f"\n{result}")

def run_test_case(step: CoffeePurchaseStep, case_index: int = 0) -> None:
    """运行指定步骤的指定测试用例"""
    if step not in TEST_CASES:
        print(f"❌ 步骤 {step} 没有测试用例")
        return
    
    cases = TEST_CASES[step]
    if case_index >= len(cases):
        print(f"❌ 步骤 {step} 只有 {len(cases)} 个测试用例，索引 {case_index} 超出范围")
        return
    
    case = cases[case_index]
    image_path = str(DATASET_ROOT / "coffee" / "images" / case["image"])
    info = case["info"]
    print("\n" + "*"*100)
    expected_result = case.get("expected_result", "无预期结果")
    print(f"expected_result: {expected_result}")
    asyncio.run(test_workflow_ui_step(step, image_path, info))


def main() -> None:
    
    # 运行多个步骤的指定用例
    # run_test_case(CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP, case_index=0)
    # run_test_case(CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP, case_index=1)
    # run_test_case(CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP, case_index=2)

    # run_test_case(CoffeePurchaseStep.SELECT_ADDRESS, case_index=0)
    # run_test_case(CoffeePurchaseStep.SELECT_ADDRESS, case_index=1)
    # run_test_case(CoffeePurchaseStep.SELECT_ADDRESS, case_index=2)
    # run_test_case(CoffeePurchaseStep.SELECT_ADDRESS, case_index=3)

    run_test_case(CoffeePurchaseStep.SELECT_PRODUCT, case_index=0)

    # run_test_case(CoffeePurchaseStep.SELECT_SPEC, case_index=0)
    # run_test_case(CoffeePurchaseStep.SELECT_SPEC, case_index=1)
    # run_test_case(CoffeePurchaseStep.SELECT_SPEC, case_index=2)
    # run_test_case(CoffeePurchaseStep.SELECT_SPEC, case_index=3)

    # run_test_case(CoffeePurchaseStep.CONFIRM_ORDER, case_index=0)
    # run_test_case(CoffeePurchaseStep.CONFIRM_ORDER, case_index=1)
    # run_test_case(CoffeePurchaseStep.CONFIRM_ORDER, case_index=2)
    # run_test_case(CoffeePurchaseStep.CONFIRM_ORDER, case_index=3)

if __name__ == "__main__":
    main()