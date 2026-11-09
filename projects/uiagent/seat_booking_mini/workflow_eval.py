import asyncio
from typing import Final, Any
from projects.uiagent.core.uiflow import run_ui_step
from projects.uiagent.seat_booking_mini.datasets import DATASET_ROOT
from rich import print
from projects.uiagent.seat_booking_mini.workflow import ( 
    SeatBookingStep,
    SeatBookingMiniUiFlow,
    SearchRestaurantInfo
)
from projects.uiagent.core.flow_data import MiddleInfoType


TEST_CASES: Final[dict[SeatBookingStep, list[dict[str, Any]]]] = {

    SeatBookingStep.SEARCH_RESTAURANT: [
        {
            "image": "page_1_7_餐厅.jpg",
            "info": SearchRestaurantInfo(name="海底捞"),
            "expected_result": "点击《订座》按钮,而不是《订座（已定x万+）》进入订座信息页",
        },
        {
            "image": "page_1_1_首页.jpg",
            "info": SearchRestaurantInfo(name=""),
            "expected_result": "点击《订座》按钮,而不是《订座（已定x万+）》进入订座信息页",
        },
        {
            "image": "page_1_3_美食.jpg",
            "info": SearchRestaurantInfo(name=""),
            "expected_result": "点击《订座》按钮,而不是《订座（已定x万+）》进入订座信息页",
        },
        {
            "image": "测试.png",
            "info": SearchRestaurantInfo(name="关闭弹窗"),
            "expected_result": "点击《搜索框》按钮",
        },
    ],

}

async def test_workflow_ui_step(
    step: SeatBookingStep, 
    image_path: str,
    info: MiddleInfoType | None
) -> None:
    """测试单个步骤"""
    print(f"\n==============test_workflow_ui_step: step: {step}=====================")
    print(f"image: {image_path}")
    print(f"info: {info}")
    
    result = await run_ui_step(
        SeatBookingMiniUiFlow, 
        image_path, 
        step, 
        info=info, 
    )
    print(f"\n{result}")

def run_test_case(step: SeatBookingStep, case_index: int = 0) -> None:
    """运行指定步骤的指定测试用例"""
    if step not in TEST_CASES:
        print(f"❌ 步骤 {step} 没有测试用例")
        return
    
    cases = TEST_CASES[step]
    if case_index >= len(cases):
        print(f"❌ 步骤 {step} 只有 {len(cases)} 个测试用例，索引 {case_index} 超出范围")
        return
    
    case = cases[case_index]
    image_path = str(DATASET_ROOT / "meituan" / "images" / case["image"])
    info = case["info"]
    expected_result = case.get("expected_result", "无预期结果")
    print(f"expected_result: {expected_result}")
    asyncio.run(test_workflow_ui_step(step, image_path, info))


def main() -> None:
    for _ in range(100):
        # 运行多个步骤的指定用例
        run_test_case(SeatBookingStep.SEARCH_RESTAURANT, case_index=3)
        # run_test_case(SeatBookingStep.SEARCH_RESTAURANT, case_index=2)


if __name__ == "__main__":
    main()