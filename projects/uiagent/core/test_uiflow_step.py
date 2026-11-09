import asyncio
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, Field
from rich import print

from nanoai.utils.nl_repr import nl_repr
from nanoai.utils.data_concept import ClsResult

from projects.uiagent.core.flow_data import (
    Action,
    EUIAction,
    Page,
    MiddleInfoType,
    StepType,
    _END_STEP,
    UIResult,
    UIStepStatus,
    UIRouter,
)
from projects.uiagent.core.action import (
    ClickAction,Button
)
from projects.uiagent.core.uiflow import UIFlowState, UIFlowBase
from projects.uiagent.core.uistep import AsyncOpenAI, UITask, UIStepBase


class SeatBookingInfo(BaseModel):
    num_people: int = Field(description="人数")
    time: str = Field(description="时间")
    type: str = Field(description="订座类型")


class EPage(StrEnum):
    BOOKING_DETAIL = "booking_detail"
    SUBMIT = "submit"

"""构造订座信息页面我们关心的按钮，只有一个下一步按钮"""
booking_page_buttons = []
next_step_button = Button(name="下一步", description="点击订座信息页面的下一步按钮的话，那么将跳转到填写订座人信息的页面。")
booking_page_buttons.append(next_step_button)
"""构造订座信息页面"""
booking_page = Page(name=EPage.BOOKING_DETAIL, description="页面有详细订座信息, 包括人数, 时间, 订座类型.",ui_elements=booking_page_buttons)

"""构造填写订座人信息页面我们关心的按钮，只有一个确认订座按钮"""
confirm_booking_buttons = []
confirm_booking_button = Button(name="确认订座", description="点击填写订座人信息页面的确认订座按钮的话，那么将提交订座信息。")
confirm_booking_buttons.append(confirm_booking_button)
"""构造填写订座人信息页面"""
confirm_booking_page = Page(name=EPage.SUBMIT, description="填写订座人信息的页面，页面有确认订座按钮。",ui_elements=confirm_booking_buttons)

PAGES: Final[list[Page]] = [
        # Page(name=EPage.BOOKING_DETAIL, description="页面有详细订座信息, 包括人数, 时间, 订座类型."),
        booking_page,
        # Page(name=EPage.SUBMIT, description="页面有提交按钮。"),
        confirm_booking_page
        ]
 
class UIStep(StrEnum):
    VAL_BOOKING_OR_SUBMIT_PAGE = "validate_booking_or_submit_page"  # 有两种可能page
    SELECT_BOOKING_DETAIL = "select_booking_detail"
    VAL_SUBMIT_PAGE = "validate_submit_page"    # 只有一种可能
    SUBMIT_BOOKING = "submit_booking"
    # 特殊的终止步骤
    END_STEP = _END_STEP


def submit_router(image: str, xml: str | None) -> ClsResult:
    assert xml is not None

    if "submit" in xml:
        return ClsResult(category=UIStep.SUBMIT_BOOKING, reason="页面有submit按钮.")
    else:
        return ClsResult(category="unknown", reason="页面没有submit按钮。无法判断")


def booking_or_submit_router(image: str, xml: str | None) -> ClsResult:
    assert xml is not None

    if "detail" in xml:
        return ClsResult(category=UIStep.SELECT_BOOKING_DETAIL, reason="页面有detail.")
    elif "submit" in xml:
        return ClsResult(category=UIStep.SUBMIT_BOOKING, reason="页面有submit按钮.")
    else:
        return ClsResult(category="unknown", reason="页面没有detail和submit按钮。无法判断")


class UIStepDummy(UIStepBase[UIFlowState]):
    '''仅提供一个dummy的实现'''

    async def _run_ui_task(
        self, 
        image: str, 
        image_format: str, 
        xml: str | None, 
        middle_info: MiddleInfoType,
        /,
        *,
        state: UIFlowState,
        model: str,
        client: AsyncOpenAI,
        ) -> UIResult:

            return UIResult(raw_prompt="", thought="", action_content="", actions=[], source="rpa")


def _next_step_action_map(actions: list[Action]) -> tuple[StepType, UIStepStatus]:
    assert len(actions) == 1
    the_action = actions[0]
    if isinstance(the_action, ClickAction):
        if the_action.target_ui_element and the_action.target_ui_element.name == next_step_button.name:
            return UIStep.SUBMIT_BOOKING, UIStepStatus.WAIT_FOR_IMAGE
        else:
            return UIStep.SELECT_BOOKING_DETAIL, UIStepStatus.WAIT_FOR_IMAGE
    else:
        return UIStep.SELECT_BOOKING_DETAIL, UIStepStatus.WAIT_FOR_IMAGE

def _submit_booking_action_map(actions: list[Action]) -> tuple[StepType, UIStepStatus]:
    assert len(actions) == 1
    the_action = actions[0]
    if isinstance(the_action, ClickAction):
        if the_action.target_ui_element and the_action.target_ui_element.name == confirm_booking_button.name:
            return UIStep.END_STEP, UIStepStatus.IDLE
        else:
            return UIStep.SUBMIT_BOOKING, UIStepStatus.WAIT_FOR_IMAGE
    else:
        return UIStep.SUBMIT_BOOKING, UIStepStatus.WAIT_FOR_IMAGE

def _dummy_submit_booking_action_map(actions: list[Action]) -> tuple[StepType, UIStepStatus]:
    return UIStep.END_STEP, UIStepStatus.IDLE

class UIFlowDummy(UIFlowBase):
    def __init__(self):
        super().__init__(
            "订座",
            UIStep.VAL_BOOKING_OR_SUBMIT_PAGE,
            {
                UIStep.SELECT_BOOKING_DETAIL: UIStepDummy(
                    UIStep.SELECT_BOOKING_DETAIL,
                    UITask(page=PAGES[0], action_set=[EUIAction.CLICK, EUIAction.ASK]),
                    action_map = lambda x: (UIStep.VAL_SUBMIT_PAGE, UIStepStatus.WAIT_FOR_IMAGE),
                    middle_info_define = SeatBookingInfo,
                    task_gen=lambda info: f"请根据下述信息选择人数, 时间, 日期, 订座类型: {nl_repr(next(iter(info.values())))}",
                ),

                UIStep.SUBMIT_BOOKING: UIStepDummy(
                    UIStep.SUBMIT_BOOKING,
                    UITask(page=PAGES[1], action_set=[EUIAction.CLICK, EUIAction.ASK]),
                    action_map = _dummy_submit_booking_action_map,
                    middle_info_define = SeatBookingInfo,
                    task_gen=lambda info: f"请提交订单, 确认信息: {nl_repr(next(iter(info.values())))}",
                ),
            },
            
            {
                UIStep.VAL_BOOKING_OR_SUBMIT_PAGE: UIRouter(
                    categories=[(UIStep.SELECT_BOOKING_DETAIL, PAGES[0]), (UIStep.SUBMIT_BOOKING, PAGES[1])],
                    router = booking_or_submit_router,
                ),
                UIStep.VAL_SUBMIT_PAGE: UIRouter(
                    categories=[(UIStep.SUBMIT_BOOKING, PAGES[1])],
                    router = submit_router,
                ),
            },
            debug_mode = True,
        )

class UIFlowSimpleSample(UIFlowBase):
    def __init__(self):
        super().__init__(
            "订座",
            UIStep.VAL_BOOKING_OR_SUBMIT_PAGE,
            {
                UIStep.SELECT_BOOKING_DETAIL: UIStepBase(
                    UIStep.SELECT_BOOKING_DETAIL,
                    UITask(page=PAGES[0], action_set=[EUIAction.CLICK, EUIAction.ASK]),
                    action_map = _next_step_action_map,
                    middle_info_define = SeatBookingInfo,
                    task_gen=lambda info: f"无视后面这堆信息，直接点击{next_step_button.name}按钮: {str(info)}",
                ),

                UIStep.SUBMIT_BOOKING: UIStepBase(
                    UIStep.SUBMIT_BOOKING,
                    UITask(page=PAGES[1], action_set=[EUIAction.CLICK, EUIAction.ASK]),
                    action_map = _submit_booking_action_map,
                    middle_info_define = SeatBookingInfo,
                    task_gen=lambda info: f"无视后面这堆信息，直接点击{confirm_booking_button.name}按钮: {str(info)}",
                ),
            },
            
            {
                UIStep.VAL_BOOKING_OR_SUBMIT_PAGE: UIRouter(
                    categories=[(UIStep.SELECT_BOOKING_DETAIL, PAGES[0]), (UIStep.SUBMIT_BOOKING, PAGES[1])],
                    router = booking_or_submit_router,
                ),
                UIStep.VAL_SUBMIT_PAGE: UIRouter(
                    categories=[(UIStep.SUBMIT_BOOKING, PAGES[1])],
                    router = submit_router,
                ),
            },
            debug_mode = True,
        )

RUN_PYTEST = False

def main():
    #test_basic()
    #return

    #test_ui_task()
    #return

    # print(workflow.info_tasks)

    image = ""
    image_format = ""
    xml_detail = "detail"
    xml_submit = "submit"
    xml_error = "wrong xml"

    def one_step_error():
        uiflow = UIFlowDummy()
    
        print(f"================ step 1 error with xml: {xml_error}====================")
        res = asyncio.run(uiflow.run_ui(image, image_format, xml_error))
        print(res)

    def one_step_finish():
        uiflow = UIFlowDummy()
    
        print(f"================ step 1 finish with xml: {xml_submit}====================")
        res = asyncio.run(uiflow.run_ui(image, image_format, xml_submit))
        print(res)

    def two_step_finish():
        uiflow = UIFlowDummy()
    
        print(f"================ step 1 with xml: {xml_detail}====================")
        res = asyncio.run(uiflow.run_ui(image, image_format, xml_detail))
        print(res)
        
        print(f"================ step 2 finish with xml: {xml_submit}====================")
        res = asyncio.run(uiflow.run_ui(image, image_format, xml_submit))
        print(res)

    one_step_error()
    
    one_step_finish()
    
    two_step_finish()

def test_uiflow_use_model():
    from nanoai.model.vlm import image_from_path
    from projects.uiagent.seat_booking_mini.datasets import DATASET_ROOT
    image_path = str(DATASET_ROOT / "meituan2" / "images" /"page_2_订座_001.jpg")
    image, image_format = image_from_path(image_path)
    image_path_2 = str(DATASET_ROOT / "meituan2" / "images" /"page_3_信息登记_001.jpg")
    image2, image_format2 = image_from_path(image_path_2)
    xml_detail = "detail"
    xml_submit = "submit"
    uiflow = UIFlowSimpleSample()
    print(f"================ step 1 with xml: {xml_detail}====================")
    res = asyncio.run(uiflow.run_ui(image, image_format, xml_detail))
    print(res)
    print(f"================ step 2 with xml: {xml_submit}====================")
    res = asyncio.run(uiflow.run_ui(image2, image_format2, xml_submit))
    print(res)

if __name__ == "__main__":
    main()
    test_uiflow_use_model()
