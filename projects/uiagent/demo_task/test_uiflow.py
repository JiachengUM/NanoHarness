from pathlib import Path
from typing import Final

import asyncio
from rich import print

from nanoai.utils.nl_repr import nl_repr

from projects.uiagent.core.uiflow import MiddleInfoType, run_ui_step

from projects.uiagent.demo_task.uiflow import (
    EPage, 
    EUIStep,
    SeatBookingUserInfoStep,
    RestaurantName,
    SeatBookingDetails,
    UserInfo,
    SeatBookingRemark,
    UIFlowDemo,
)

from projects.uiagent.core.test_utils import Environment


DATASET_ROOT: Final[Path] = Path(".") / "projects" / "uiagent" / "demo_task" / "datasets"
image_root = DATASET_ROOT


ENV: Final[Environment] = Environment({
        EPage.SELECT_RESTAURANT: str(image_root / "001.jpg"),
        EPage.START_SEAT_BOOKING: str(image_root / "002.jpg"),
        EPage.CONFIRM_SEAT_BOOKING_DETAILS: str(image_root / "003.jpg"),
        EPage.CONFIRM_SEAT_BOOKING_PERSON_INFO: str(image_root / "004.jpg"),
    })


# 这里的info字段可以是结构化类型（内部会检查语义约束），也可以是str（内部不做检查）
# 怎么用取决于测试的目的。
step_info = [
    (EUIStep.SELECT_RESTAURANT, RestaurantName(name="潮界火锅")),
    (EUIStep.SELECT_RESTAURANT, None),   # 无效middle_info
    (EUIStep.START_SEAT_BOOKING, None),
    (EUIStep.CONFIRM_SEAT_BOOKING_DETAILS, SeatBookingDetails(number_of_people=2, time="明晚8点", seat_type="大厅")),
    (EUIStep.CONFIRM_SEAT_BOOKING_DETAILS, SeatBookingDetails(number_of_people=0)),  # 无效info
    (EUIStep.CONFIRM_SEAT_BOOKING_PERSON_INFO, {SeatBookingUserInfoStep.EInfo.USER_INFO: "小明, 电话13800138000, 性别男"}),  # 支持str
    (EUIStep.CONFIRM_SEAT_BOOKING_PERSON_INFO, {
        SeatBookingUserInfoStep.EInfo.DEFAULT_USER_INFO: "小途, 电话13866666666, 性别女",
        SeatBookingUserInfoStep.EInfo.REMARK: SeatBookingRemark(remark="靠窗")
        }),  # 更加复杂的info和task
    (EUIStep.CONFIRM_SEAT_BOOKING_DETAILS, None), # 无效info
]


async def test_workflow_ui_step(step: EUIStep, info: MiddleInfoType | None) -> None:
    print(f"\n==============test_workflow_ui_step: step: {step} info: {info}=====================")

    result = await run_ui_step(
        UIFlowDemo, 
        str(ENV.page_images[step]), 
        step, 
        info=info, 
        )

    #print(f"\nresult\n{nl_repr(result)}")
    print(f"\n{result}")   # 用rich.print即可


def main() -> None:
    #asyncio.run(test_workflow_ui_step(*step_info[-3]))
    #return

    for step in step_info[:]:
         asyncio.run(test_workflow_ui_step(*step))
    return

    # asyncio.run(test_workflow_auto_full())
    # return


if __name__ == "__main__":
    main()
