import asyncio
from enum import StrEnum
from typing import Final

import pytest
from pydantic import BaseModel, Field

from nanoai.model.config import ModelName, create_client, AsyncOpenAI
from nanoai.model.vlm import avlm, image_from_path
from nanoai.utils.nl_repr import nl_repr
from nanoai.utils.data_concept import ClsResult

from projects.uiagent.utils.utils import parse_thought_and_action_content
from projects.uiagent.core.error import UIAgentError
from projects.uiagent.core import (
    InfoTask, 
    UITask, 
    UIRouter,
    ui_task_eval, 
    UITaskResult,
    WorkflowState,
    WorkflowResult,
    WorkflowBase,
    Page,
    WorkflowStatus,
)


class SeatBookingInfo(BaseModel):
    num_people: int = Field(description="人数")
    time: str = Field(description="时间")
    type: str = Field(description="订座类型")


def test_basic():
    state = WorkflowState(task="test_task", current_step="start")
    print(f"state: {state}")

    result = WorkflowResult(error = UIAgentError("error info", "error reason"), state=state)

    print(f"result: {result}")


def test_ui_task():
    task = UITask(
        page="美团订座页面",
        info_task=InfoTask(
            brief="提取如下信息: 人数，时间，订座类型",
            info_type=SeatBookingInfo,
        ),
        task_template="请根据下述信息选择人数, 时间, 日期, 订座类型: {info}",
    )

    prompt = task.as_prompt("预订4人的座位, 明天12:00, 包间")

    print(prompt)

    # model_name = ModelName.DOUBAO_1_5_UI_TARS_250428
    model_name = ModelName.DOUBAO_SEED_1_6_VISION_250815

    client, model = create_client(model_name, AsyncOpenAI)

    image_path = "tests/images/hehuiyan_seat_info.png"
    base64_image, image_format = image_from_path(image_path)
    response = asyncio.run(avlm(prompt, base64_image, image_format, client=client, model=model))

    print(f"query: {prompt}\nresponse:\n{response}")

    thought, action_content = parse_thought_and_action_content(response)

    eval_res = asyncio.run(
        ui_task_eval(
            prompt,
            base64_image,
            image_format,
            thought,
            action_content,
            client=client,
            model=model,
        )
    )
    print(f"eval result:\n{eval_res}")


class EPage(StrEnum):
    BOOKING_DETAIL = "booking_detail"
    SUBMIT = "submit"


PAGES: Final[list[Page]] = [
        Page(name=EPage.BOOKING_DETAIL, description="页面有详细订座信息, 包括人数, 时间, 订座类型."),
        Page(name=EPage.SUBMIT, description="页面有提交按钮。"),
        ]
 
class UIStep(StrEnum):
    VAL_BOOKING_OR_SUBMIT_PAGE = "validate_booking_or_submit_page"  # 有两种可能page
    SELECT_BOOKING_DETAIL = "select_booking_detail"
    VAL_SUBMIT_PAGE = "validate_submit_page"    # 只有一种可能
    SUBMIT_BOOKING = "submit_booking"


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

class WorkflowDummy(WorkflowBase):
    def __init__(self):
        booking_detail_info_task = InfoTask(
            brief="提取如下信息: 人数，时间，订座类型",
            info_type=SeatBookingInfo,
        )

        super().__init__(
            "订座",
            UIStep.VAL_BOOKING_OR_SUBMIT_PAGE,
            {
                UIStep.SELECT_BOOKING_DETAIL: UITask(
                    page="订座页面",
                    info_task=booking_detail_info_task,
                    task_template="请根据下述信息选择人数, 时间, 日期, 订座类型: {info}"
                ),
                UIStep.SUBMIT_BOOKING: UITask(
                    page="提交页面",
                    info_task=booking_detail_info_task,
                    task_template="请提交订单, 确认信息: {info}"
                ),
            },
            {
                UIStep.SELECT_BOOKING_DETAIL: self._select_booking_detail,
                UIStep.SUBMIT_BOOKING: self._submit_booking,    
            },
            ui_routers={
                UIStep.VAL_BOOKING_OR_SUBMIT_PAGE: UIRouter(
                    categories=[(UIStep.SELECT_BOOKING_DETAIL, PAGES[0]), (UIStep.SUBMIT_BOOKING, PAGES[1])],
                    router = booking_or_submit_router,
                ),
                UIStep.VAL_SUBMIT_PAGE: UIRouter(
                    categories=[(UIStep.SUBMIT_BOOKING, PAGES[1])],
                    router = submit_router,
                ),
            },
            debug_mode=True,
        )


    async def _select_booking_detail(self, image: str, image_format: str) -> UITaskResult:
        # return "还缺信息"

        self.state.set_step(UIStep.VAL_SUBMIT_PAGE)
        print(f"状态跳转到: {self.state.current_step}")
        return UITaskResult(raw_prompt="", thought="", action_content="", actions=[])


    async def _submit_booking(self, image: str, image_format: str) -> UITaskResult:
        # return "订单已提交"

        self.state.status = WorkflowStatus.SUCCESS

        print(f"状态跳转到: 任务执行成功")
        return UITaskResult(raw_prompt="", thought="", action_content="", actions=[])


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
        workflow = WorkflowDummy()
    
        print(f"================run ui with xml: {xml_error}====================")
        res = asyncio.run(workflow.run_ui(image, image_format, xml_error))
        print(nl_repr(res))

    def one_step_finish():
        workflow = WorkflowDummy()
    
        print(f"================run ui with xml: {xml_submit}====================")
        res = asyncio.run(workflow.run_ui(image, image_format, xml_submit))
        print(nl_repr(res))

    def two_step_finish():
        workflow = WorkflowDummy()
    
        print(f"================run ui with xml: {xml_detail}====================")
        res = asyncio.run(workflow.run_ui(image, image_format, xml_detail))
        print(nl_repr(res))

        print(f"================run ui with xml: {xml_submit}====================")
        res = asyncio.run(workflow.run_ui(image, image_format, xml_submit))
        print(nl_repr(res))

    one_step_error()
    one_step_finish()
    two_step_finish()

if __name__ == "__main__":
    if RUN_PYTEST:
        pytest.main([__file__, "-v", "-s"])
    else:
        main()
