from __future__ import annotations
from typing import Final
from pydantic import Field, BaseModel

from enum import StrEnum

from nanoai.task import JudgeResult
from projects.uiagent.core import (
    Action,
    Page,
    StepType,
    UITask, 
    InfoTask,
    WorkflowBase, 
    EUIAction,
    UITaskResult,
    UIStepStatus, 
    WorkflowStatus,
    WorkflowState,
    UIHandler,
    RPAHandler,
)

class EPage(StrEnum):
    SELECT_RESTAURANT = "饭店选择页"
    START_SEAT_BOOKING = "饭店主页"
    CONFIRM_SEAT_BOOKING_DETAILS = "订座详情页"
    CONFIRM_SEAT_BOOKING_PERSON_INFO = "订座确认页"


PAGES: Final[list[Page]] = [
        Page(name=EPage.SELECT_RESTAURANT, description="页面左边为饭店列表，右边为地图。"),
        Page(name=EPage.START_SEAT_BOOKING, description="页面左边为饭店主页，右边为地图。"),
        Page(name=EPage.CONFIRM_SEAT_BOOKING_DETAILS, description="页面左边包括人数，日期，时间，座位类型等订座选项，右边为地图。"),
        Page(name=EPage.CONFIRM_SEAT_BOOKING_PERSON_INFO, description="页面左边为姓名，手机号，备注等信息，右边为地图。"),
    ]

class EUIStep(StrEnum):
    '''目前没有区分UITask和Page。因此需要保持一摸一样。否则Environment不work。'''
    SELECT_RESTAURANT = EPage.SELECT_RESTAURANT
    START_SEAT_BOOKING = EPage.START_SEAT_BOOKING
    CONFIRM_SEAT_BOOKING_DETAILS = EPage.CONFIRM_SEAT_BOOKING_DETAILS
    CONFIRM_SEAT_BOOKING_PERSON_INFO = EPage.CONFIRM_SEAT_BOOKING_PERSON_INFO
    END = "end"


class RestaurantName(BaseModel):
    '''只有一个str成员，所以这个class仅仅为了结构化输出方便，本质上并没有用处。
    TODO: 如果结构化输出导致速度慢，需要去掉。'''
    name: str | None = Field(default=None, title="饭店名称", description="用户想要订座的饭店名称")

    @staticmethod
    def validator(info: RestaurantName | str | None) -> JudgeResult:
        if info is None:
            return JudgeResult(judgment=False, reason="您想在什么饭店订座？")

        return JudgeResult(judgment=True, reason="")

class SeatBookingDetails(BaseModel):
    '''订座详情
    TODO: 所有字段都有各种约束检查。如何实现还不清楚。
    '''

    number_of_people: int | None = Field(default=None, title="人数", description="订座人数")

    date: str | None = Field(default=None, title="日期", description="订座日期")
    
    time: str | None = Field(default=None, title="时间", description="订座时间")
    
    seat_type: str | None = Field(default=None, title="座位类型", description="座位类型")
    '''有如下取值: 大厅，包厢，卡座，散座
    TODO: 如何增加类似于enum的约束还不清楚。
    '''

    @staticmethod
    def validator(info: RestaurantName | str | None) -> JudgeResult:
        if info is None:
            res = "请告诉我您需要订座的人数, 日期, 时间, 座位类型。"    
            return JudgeResult(judgment=False, reason=res)

        if isinstance(info, SeatBookingDetails):
            # 是结构化类型时才做检查
            if info.number_of_people is None or info.date is None or info.time is None or info.seat_type is None:
                res = "缺失一些字段。请告诉我您需要订座的人数, 日期, 时间, 座位类型。"    
                return JudgeResult(judgment=False, reason=res)

        return JudgeResult(judgment=True, reason="")

class SeatBookingPersonInfo(BaseModel):
    name: str | None = Field(default=None, title="姓名", description="用户选择的姓名")
    country_number: str = Field(default="+86", title="国家编号", description="电话的国家编号")
    phone_number: str | None = Field(default=None, title="电话号码", description="用户输入的电话号码")
    remark: str | None = Field(default=None, title="备注", description="用户选择的备注")
    sex: str | None = Field(default=None, title="性别", description="用户选择的性别")

    @staticmethod
    def validator(info: RestaurantName | str | None) -> JudgeResult:
        if info is None:
            res = "请告诉我您的姓名，手机号，性别，备注信息。"    
            return JudgeResult(judgment=False, reason=res)

        if isinstance(info, SeatBookingPersonInfo):
            # 是结构化类型时才做检查
            if info.name is None or info.phone_number is None or info.sex is None or info.remark is None:
                res = "请告诉我您的姓名，手机号，性别，备注信息。"    
                return JudgeResult(judgment=False, reason=res)

        return JudgeResult(judgment=True, reason="")
    

class SeatBookingState(WorkflowState):
    '''订座智能体的状态'''
    pass


class WorkflowDemo(WorkflowBase[SeatBookingState]):
    def __init__(self) -> None:
        ui_tasks: dict[StepType, UITask] = {
            EUIStep.SELECT_RESTAURANT: UITask(
                page=PAGES[0],
                info_task=InfoTask(brief="询问饭店", info_type=RestaurantName, validator=RestaurantName.validator),  # type: ignore
                task_template="请根据下述信息选择要订座的饭店: {info}",
                action_set=[EUIAction.CLICK]),

            EUIStep.START_SEAT_BOOKING: UITask(
                # 没有InfoTask，因为不需要询问信息。
                page=PAGES[1],
                task="请点击订座按钮",
                action_set=[EUIAction.CLICK]),

            EUIStep.CONFIRM_SEAT_BOOKING_DETAILS: UITask(
                page=PAGES[2],
                info_task=InfoTask(brief="询问订座详情", info_type=SeatBookingDetails, validator=SeatBookingDetails.validator),  # type: ignore
                task_template="根据下述详情信息选择订座选项: {info}",
                action_set=[EUIAction.CLICK, EUIAction.SCROLL, EUIAction.ASK]),

            EUIStep.CONFIRM_SEAT_BOOKING_PERSON_INFO: UITask(
                page=PAGES[3],
                info_task=InfoTask(brief="询问订座人信息", info_type=SeatBookingPersonInfo, validator=SeatBookingPersonInfo.validator),  # type: ignore
                task_template="根据下述信息输入订座人信息: {info}",
                action_set=[EUIAction.CLICK, EUIAction.ASK]),
        }

        ui_task_handlers: dict[StepType, UIHandler] = {
            EUIStep.SELECT_RESTAURANT.value: self._select_restaurant,
            EUIStep.START_SEAT_BOOKING.value: self._start_seat_booking,
            EUIStep.CONFIRM_SEAT_BOOKING_DETAILS.value: self._select_seat_booking_details,
            EUIStep.CONFIRM_SEAT_BOOKING_PERSON_INFO.value: self._submit_seat_booking_person_info,
        }

        rpa_handlers : dict[StepType, RPAHandler] = {
                EUIStep.START_SEAT_BOOKING: self._start_seat_booking_rpa
                }

        super().__init__(
            "帮助用户选择餐厅和订座",
            EUIStep.SELECT_RESTAURANT,
            ui_tasks,
            ui_task_handlers,
            rpa_handlers = rpa_handlers,
            state_cls=SeatBookingState,
            enable_reflect=True,
            agent_name="小途",
            debug_mode=True,
        )


    async def _select_restaurant(self, image: str, image_format: str) -> UITaskResult:
        assert self.state.current_step == EUIStep.SELECT_RESTAURANT, "current_step must be SELECT_RESTAURANT"

        result = await self._run_ui_step_by_model(image, image_format)

        # TODO: 需要做结果和错误检查
        self.state.set_step(EUIStep.START_SEAT_BOOKING)
        
        return result


    async def _start_seat_booking(self, image: str, image_format: str) -> UITaskResult:
        result = await self._run_ui_step_by_model(image, image_format)
        self.state.set_step(EUIStep.CONFIRM_SEAT_BOOKING_DETAILS)
        return result


    def _start_seat_booking_rpa(self, info: BaseModel | str | None, xml: str) -> tuple[list[Action], EUIStep, None]:
        # just an example of rpa, mock the result
        return [], EUIStep.CONFIRM_SEAT_BOOKING_DETAILS, None


    async def _select_seat_booking_details(self, image: str, image_format: str) -> UITaskResult:
        assert self.state.current_step == EUIStep.CONFIRM_SEAT_BOOKING_DETAILS, "current_step must be CONFIRM_SEAT_BOOKING_DETAILS"
        
        result = await self._run_ui_step_by_model(image, image_format)
        self.state.set_step(EUIStep.CONFIRM_SEAT_BOOKING_PERSON_INFO)

        return result

            
    async def _submit_seat_booking_person_info(self, image: str, image_format: str) -> UITaskResult:
        assert self.state.current_step == EUIStep.CONFIRM_SEAT_BOOKING_PERSON_INFO, "current_step must be CONFIRM_SEAT_BOOKING_PERSON_INFO"

        self.state.step_status[self.state.current_step] = UIStepStatus.RUNNING
        result = await self._run_ui_step_by_model(image, image_format)

        self.state.status = WorkflowStatus.SUCCESS

        return result
