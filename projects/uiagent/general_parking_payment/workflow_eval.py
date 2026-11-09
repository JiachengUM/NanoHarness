import asyncio
from typing import Final, Any
from projects.uiagent.core.uiflow import run_ui_step
from projects.uiagent.general_parking_payment.datasets import DATASET_ROOT
from rich import print
from projects.uiagent.general_parking_payment.workflow import (
    ParkingSteps,
    GeneralParkingPaymentUIFlow,
    PlateNumber,
)
from projects.uiagent.core.flow_data import MiddleInfoType
    
TEST_CASES: Final[dict[ParkingSteps, list[dict[str, Any]]]] = {

    ParkingSteps.GENERAL_PARKING_PAYMENT: [

        # {
        #     "image": "000_输车牌.jpg",
        #     "info": PlateNumber(plate_number="粤B12345"),
        #     "expected_result": "点击输入框",
        # },
        # {
        #     "image": "000_输车牌.jpg",
        #     "info": PlateNumber(plate_number="粤B12345",scratchpad="假设当前已经点击了输入框了！"),
        #     "expected_result": "type输入内容粤B12345",
        # },
        # {
        #     "image": "000_输车牌.jpg",
        #     "info": PlateNumber(plate_number="粤B12345",scratchpad="假设当前已经点击了输入框了且已经完成了输入车牌！！！记住已经完成了输入车牌！！！"),
        #     "expected_result": "点击确定按钮",
        # },
        # {
        #     "image": "001_点击输入框.jpg",
        #     "info": PlateNumber(plate_number="粤B12345"),
        #     "expected_result": "键盘点击",
        # },

        # {
        #     "image": "002_查询后无记录.jpg",
        #     "info": PlateNumber(plate_number="粤B12345"),
        #     "expected_result": "播报出来，finished",
        # },
        # {
        #     "image": "003_输入车牌_自带省份.jpg",
        #     "info": PlateNumber(plate_number="粤B12345"),
        #     "expected_result": "省份不对，去点击",
        # },
        {
            "image": str(DATASET_ROOT / "parking_payment" /"images"/ "004_玉溪L.png"),
            "info": PlateNumber(plate_number="云F933LL"),
            "expected_result": "点L",
        },

    ],
}


async def test_workflow_ui_step(
    step: ParkingSteps,
    image_path: str,
    info: MiddleInfoType | None,
) -> None:
    """测试单个步骤"""
    print(f"\n==============test_workflow_ui_step: step: {step}=====================")
    print(f"image: {image_path}")
    print(f"info: {info}")
    
    result = await run_ui_step(
        GeneralParkingPaymentUIFlow, 
        image_path, 
        step, 
        info=info, 
    )
    # 增加可视化
    from projects.uiagent.core.visualize import draw_step_result
    import time
    draw_step_result(
        image_path=image_path,
        query="",
        runresult=result.results,
        output_dir=str(DATASET_ROOT / "tests"),
        sample_id=int(time.time()),# 用时间戳作为样本id
    )

    print(f"\n{result}")

def run_test_case(step: ParkingSteps, case_index: int = 0, test_cases: dict[ParkingSteps, list[dict[str, Any]]] = TEST_CASES) -> None:
    """运行指定步骤的指定测试用例"""
    if step not in test_cases:
        print(f"❌ 步骤 {step} 没有测试用例")
        return
    
    cases = test_cases[step]
    if case_index >= len(cases):
        print(f"❌ 步骤 {step} 只有 {len(cases)} 个测试用例，索引 {case_index} 超出范围")
        return
    
    case = cases[case_index]
    image_path = case["image"]
    info = case["info"]
    print("\n" + "*"*100)
    expected_result = case.get("expected_result", "无预期结果")
    print(f"expected_result: {expected_result}")
    asyncio.run(test_workflow_ui_step(step, image_path, info))


def main() -> None:
    # 运行多个步骤的指定用例
    run_test_case(ParkingSteps.GENERAL_PARKING_PAYMENT, case_index=0, test_cases=TEST_CASES)

if __name__ == "__main__":
    main()