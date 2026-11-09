from __future__ import annotations
from typing import Final
from pydantic import Field, BaseModel

from enum import StrEnum

from nanoai.task import JudgeResult
from nanoai.utils.nl_repr import nl_repr

from projects.uiagent.core.flow_data import (
    Page,
    _END_STEP,
    EUIAction,
    UIStepStatus,
    MiddleInfoType, 
)

from projects.uiagent.core.uiflow import UIFlowState, UIFlowBase
from projects.uiagent.core.uistep import AsyncOpenAI, UITask, UIStepBase, UIResult


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
    END = _END_STEP


class UIFlowDemoState(UIFlowState):
    '''订座流程的状态。由于目前还无法在UIFlowBase中合理的初始化。所有字段必须有默认值。'''
    some_extra_var: str = Field(default="", title="额外变量", description="用于存储一些额外的变量。用于演示state的传递。")


class RestaurantName(BaseModel):
    '''只有一个str成员，所以这个class仅仅为了结构化输出方便，本质上并没有用处。
    TODO: 如果结构化输出导致速度慢，需要去掉。'''
    name: str | None = Field(default=None, title="饭店名称", description="用户想要订座的饭店名称")

    @staticmethod
    def validator(info: RestaurantName | str | None) -> JudgeResult:
        if info is None:
            return JudgeResult(judgment=False, reason="饭店名称为空。需要提供饭店名称。")

        # TODO: 这里需要检查饭店名称的合法性。

        return JudgeResult(judgment=True, reason="")


class SelectRestaurantStep(UIStepBase[UIFlowDemoState]):
    '''最简单的ui step实现，只需要一个中间信息，校验也很简单。'''
    def __init__(self):
        super().__init__(
            step=EUIStep.SELECT_RESTAURANT,
            ui_task=UITask(page=PAGES[0], action_set=[EUIAction.CLICK]),
            action_map= lambda actions: (EUIStep.START_SEAT_BOOKING, UIStepStatus.WAIT_FOR_IMAGE),
            middle_info_define=RestaurantName,
            task_gen=lambda info: f"请根据下述信息选择要订座的饭店: {nl_repr(next(iter(info.values())))}",
        )

    def _validate_info(self, middle_info: MiddleInfoType) -> JudgeResult:
        self._validate_info_type(middle_info)

        # 只有一个info时的写法
        restaurant_name = next(iter(middle_info.values()))

        return RestaurantName.validator(restaurant_name)  # type: ignore


class SeatBookingDetails(BaseModel):
    '''订座详情'''

    number_of_people: int | None = Field(default=None, title="人数", description="订座人数")

    date: str | None = Field(default=None, title="日期", description="订座日期")
    
    time: str | None = Field(default=None, title="时间", description="订座时间")
    
    seat_type: str | None = Field(default=None, title="座位类型", description="座位类型")
    '''有如下取值: 大厅，包厢，卡座，散座
    TODO: 如何增加类似于enum的约束还不清楚。
    '''

class SeatBookingDetailsStep(UIStepBase[UIFlowDemoState]):
    '''订座详情页的ui step实现。需要一个中间信息，校验也比较复杂。'''
    def __init__(self):
        super().__init__(
            step=EUIStep.CONFIRM_SEAT_BOOKING_DETAILS,
            ui_task=UITask(page=PAGES[2], action_set=[EUIAction.CLICK, EUIAction.SCROLL, EUIAction.ASK]),
            action_map=lambda actions: (EUIStep.CONFIRM_SEAT_BOOKING_PERSON_INFO, UIStepStatus.WAIT_FOR_IMAGE),
            middle_info_define=SeatBookingDetails,
            task_gen=lambda info: f"根据下述详情信息选择订座选项: {nl_repr(next(iter(info.values())))}",
        )
    
    def _validate_info(self, middle_info: MiddleInfoType) -> JudgeResult:
        self._validate_info_type(middle_info)

        # 只有一个info时的写法
        info = next(iter(middle_info.values()))

        if info is None:
            res = "请告诉我您需要订座的人数, 日期, 时间, 座位类型。"    
            return JudgeResult(judgment=False, reason=res)

        if isinstance(info, str):
            return JudgeResult(judgment=True, reason="str类型的SeatBookingDetails info默认有效")

        assert isinstance(info, SeatBookingDetails)
        # 是结构化类型时才做检查
        err_msg = []
        if info.number_of_people is None or info.number_of_people <= 0:
            err_msg.append("订座人数无效，为空或者为负数。")
        
        if info.date is None:
            err_msg.append("日期为空。")

        if info.time is None:
            err_msg.append("时间为空。")

        if info.seat_type is None:
            err_msg.append("座位类型为空。")

        if err_msg:
            return JudgeResult(judgment=False, reason="\n".join(err_msg))
        else:
            return JudgeResult(judgment=True, reason="")


class UserInfo(BaseModel):
    name: str | None = Field(default=None, title="姓名", description="用户姓名")
    country_number: str = Field(default="+86", title="国家编号", description="用户电话的国家编号")
    phone_number: str | None = Field(default=None, title="电话号码", description="用户电话号码")
    sex: str | None = Field(default=None, title="性别", description="用户性别")

    @staticmethod
    def validator(info: UserInfo | str | None) -> JudgeResult:
        if info is None:
            res = "请告诉我您的姓名，手机号，性别，备注信息。"    
            return JudgeResult(judgment=False, reason=res)

        if isinstance(info, str):
            return JudgeResult(judgment=True, reason="str类型的UserInfo info默认有效")

        assert isinstance(info, UserInfo)
        # 是结构化类型时才做检查
        if info.name is None or info.phone_number is None or info.sex is None:
            res = "缺少用户姓名，手机号，性别。"    
            return JudgeResult(judgment=False, reason=res)

        return JudgeResult(judgment=True, reason="")


class SeatBookingRemark(BaseModel):
    '''TODO: 应该结构化。会有各种字段。而且应该从页面动态生成。'''
    remark: str | None = Field(default=None, title="备注", description="订座的备注, 例如是否靠窗")


class SeatBookingUserInfoStep(UIStepBase[UIFlowDemoState]):
    '''订座人信息页的ui step实现。需要3个中间信息，其中2个类型相同，写法和校验都更加复杂。'''

    class EInfo(StrEnum):
        '''订座人信息页的中间信息字段。'''
        USER_INFO = "user_info"
        DEFAULT_USER_INFO = "default_user_info"
        REMARK = "remark"

    @staticmethod
    def seat_booking_user_info_task(info: MiddleInfoType) -> str:
        '''订座人信息页的任务生成函数。'''
        user_info = info[SeatBookingUserInfoStep.EInfo.USER_INFO]
        if user_info is None:
            user_info = info[SeatBookingUserInfoStep.EInfo.DEFAULT_USER_INFO]

        assert isinstance(user_info, (UserInfo, str)), f"user_info 必须是 UserInfo or str 类型, but got {type(user_info)}"

        task = f"请输入订座人信息如下: {nl_repr(user_info)}"
        
        remark = info[SeatBookingUserInfoStep.EInfo.REMARK]

        if isinstance(remark, (SeatBookingRemark, str)):
            task += f"\n 请输入备注信息如下: {nl_repr(remark)}"

        return task


    def __init__(self):
        super().__init__(
            step=EUIStep.CONFIRM_SEAT_BOOKING_PERSON_INFO,
            ui_task=UITask(page=PAGES[3], action_set=[EUIAction.CLICK, EUIAction.ASK]),
            action_map=lambda actions: (EUIStep.END, UIStepStatus.IDLE),
            middle_info_define={
                SeatBookingUserInfoStep.EInfo.USER_INFO: UserInfo,
                SeatBookingUserInfoStep.EInfo.DEFAULT_USER_INFO: UserInfo,
                SeatBookingUserInfoStep.EInfo.REMARK: SeatBookingRemark,
            },
            task_gen=SeatBookingUserInfoStep.seat_booking_user_info_task,
        )

    def _validate_info(self, middle_info: MiddleInfoType) -> JudgeResult:
        self._validate_info_type(middle_info)

        # 这是标准写法
        user_info = middle_info[SeatBookingUserInfoStep.EInfo.USER_INFO]
        default_user_info = middle_info[SeatBookingUserInfoStep.EInfo.DEFAULT_USER_INFO]
        remark = middle_info[SeatBookingUserInfoStep.EInfo.REMARK]

        # TODO: 可以做各种检查
        if user_info is None:
            if default_user_info is None:
                return JudgeResult(judgment=False, reason="请告诉我您的姓名，手机号，性别")
            else:
                pass

        return JudgeResult(judgment=True, reason="")

    async def _run_ui_task(
        self, 
        image: str, 
        image_format: str, 
        xml: str | None, 
        middle_info: MiddleInfoType,
        /,
        *,
        state: UIFlowDemoState,
        model: str,
        client: AsyncOpenAI,
        ) -> UIResult:

            # 从state中获取额外变量，做一些处理
            extra_var = state.some_extra_var

            return await super()._run_ui_task(
                image, image_format, xml, middle_info, state=state, model=model, client=client
            )


class UIFlowDemo(UIFlowBase[UIFlowDemoState]):
    def __init__(self) -> None:
        super().__init__(
            "帮助用户选择餐厅和订座",
            EUIStep.SELECT_RESTAURANT,
            {
                EUIStep.SELECT_RESTAURANT: SelectRestaurantStep(),
                EUIStep.START_SEAT_BOOKING: UIStepBase[UIFlowDemoState](
                    step=EUIStep.START_SEAT_BOOKING,
                    ui_task=UITask(
                        page=PAGES[1],
                        task="请点击订座按钮",
                        action_set=[EUIAction.CLICK]),
                    action_map= lambda actions: (EUIStep.CONFIRM_SEAT_BOOKING_DETAILS, UIStepStatus.WAIT_FOR_IMAGE),
                ),
                EUIStep.CONFIRM_SEAT_BOOKING_DETAILS: SeatBookingDetailsStep(),
                EUIStep.CONFIRM_SEAT_BOOKING_PERSON_INFO: SeatBookingUserInfoStep(),
            },
            state_cls = UIFlowDemoState,
            debug_mode=True,
            )

        # 基类初始化后，需要专门初始化state。
        self.state.some_extra_var = "some_extra_var"