from __future__ import annotations
from enum import StrEnum
from datetime import datetime
from pydantic import BaseModel, Field
import re

from nanoai.utils.nl_repr import nl_repr # type: ignore
from nanoai.task import JudgeResult
from projects.uiagent.core.action import Button, ClickAction, AskAction, WaitAction, InputBox, FinishedAction
from projects.uiagent.core.flow_data import (
    Action,
    EUIAction,
    Page,
    StepType,
    UIStepStatus,
    MiddleInfoType, 
    _END_STEP, # type: ignore
)
from projects.uiagent.core.uiflow import UIFlowBase, UIFlowState
from projects.uiagent.core.uistep import UIStepBase, UITask

class GeneralParkingPaymentUIFlowState(UIFlowState):
    background_info: str = Field(default=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",title="当前日期时间", description="当前日期时间，格式为YYYY-MM-DD HH:MM:SS")


class ParkingSteps(StrEnum):
    GENERAL_PARKING_PAYMENT = "通用停车缴费步骤"  # 可以理解为只有一个步骤，不做限制。

    
class PlateNumber(BaseModel):
    # 暂时先这么写，很快会有复杂车牌区分会加入更多属性
    plate_number: str = Field(
        title="车牌号", description="用户的车牌号，必须为合法车牌号，否则无法进行缴费。"
    )
    scratchpad: str | None = Field(
        default=None,
        title="草稿纸",
        description="在停车缴费的过程中，可以记录所有用户说过的话，以及用户的行为，以便后续使用。"
    )
    
    @staticmethod
    def validator(info: PlateNumber) -> JudgeResult:
        plate_number = info.plate_number
        plate_number = plate_number.upper().replace(" ","")
        pattern = re.compile(
            # 普通5位车牌
            r"^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-HJ-NP-Z][A-HJ-NP-Z0-9]{4}[A-HJ-NP-Z0-9挂学警港澳]$"
            # 新能源车牌
            r"|[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-HJ-NP-Z][A-HJ-NP-Z0-9]{6}$"
        )
        if not pattern.match(plate_number):
            return JudgeResult(
                judgment=False,
                reason="错误车牌，请重新告诉我准确的车牌号码。",
            )
        else:
            return JudgeResult(judgment=True, reason="车牌号有效")


PAGES: dict[str, Page] = {
        ParkingSteps.GENERAL_PARKING_PAYMENT: Page(
            name="通用停车缴费首页",
            description=(
                "停车缴费页面，涉及多种页面，包括但不限于新增车牌、刷新订单，查看金额，去续费、去缴费、地理位置授权、自动跳过广告、各种弹窗等。"
            ),
        ),
}


class UIStepGeneral(UIStepBase[GeneralParkingPaymentUIFlowState]):
    '''最简单的ui step实现，只需要一个中间信息，校验也很简单。'''

    @staticmethod
    def general_parking_payment_task(back_ground_info: str, info: MiddleInfoType, actions_record: list[Action]) -> str:
        '''任务生成函数。'''
        task = f"""你同时是一个资深停车缴费博主，特别擅长操作停车缴费小程序帮用户完成缴费操作。
以下是一些你在这个过程中可能需要用到的供你参考用的信息：
当前时间是:{back_ground_info}
所需信息:{nl_repr(next(iter(info.values()))) if info else "无"}

你之前执行过的操作动作记录（自上而下由旧到新）如下：
[
{"\n".join([str(action) for action in actions_record])}
]
"""
        return task

    def __init__(self):
        super().__init__(
            step=ParkingSteps.GENERAL_PARKING_PAYMENT,
            ui_task=UITask(
                page=PAGES[ParkingSteps.GENERAL_PARKING_PAYMENT],
                note=[
                    "仔细阅读并严格执行下述指引，否则干死你。",
                    "无论何时，如果你并不知道当前用户正在希望进行缴费的车辆车牌信息，那么用ask_human来向用户询问。否则你无法进行下面的任务。",
                    "任何时候，遇到下面没有提到的情况，都请记住：一切围绕尽快帮用户完成停车缴费进行。",
                    "任何时候，如果你看到有弹窗了，那么忽略弹窗之外的内容！只关注弹窗内的内容并操作！",
                    "如果你在当前页面上没有看到任何车辆信息，并且看到让你添加车辆，输车牌缴费，那么点击输车牌缴费；",
                    "如果你看到当前页面提示未查询到车辆信息等字样，那么直接连带当前车牌用ask_human播报出来。",
                ],
                # 暂时去掉 EUIAction.TYPE
                action_set=[EUIAction.CLICK,  EUIAction.FINISHED, EUIAction.WAIT, EUIAction.ASK,],
            ),
            task_gen=UIStepGeneral.general_parking_payment_task,
            action_map=self._action_map,
            middle_info_define=PlateNumber,  
        )

    def _action_map(self, actions: list[Action]) -> tuple[StepType, UIStepStatus]:
        """
        Callable[[list[Action]], tuple[StepType, UIStepStatus]]
        """
        assert len(actions) <= 1, f'仅支持返回一个动作'
        action = actions[0]
        if isinstance(action, ClickAction):
            # 先不做处理
            return ParkingSteps.GENERAL_PARKING_PAYMENT, UIStepStatus.WAIT_FOR_IMAGE
        elif isinstance(action, FinishedAction):
            return _END_STEP, UIStepStatus.IDLE
        elif isinstance(action, AskAction):
            return ParkingSteps.GENERAL_PARKING_PAYMENT, UIStepStatus.WAIT_FOR_INFO
        else:
            return ParkingSteps.GENERAL_PARKING_PAYMENT, UIStepStatus.WAIT_FOR_IMAGE


general_parking_payment_intent_categories = [
        ("Relevant", "任何与停车缴费可能相关的意图，包括但不限于说个车牌号，支付与否，正确与否等等。"),
        ("Abort", '用户希望退出，终止，取消当前工作的意图。'),
        ("Irrelevant", "其他任何与停车缴费无关的意图统统属于这个。"),
    ]

class GeneralParkingPaymentUIFlow(UIFlowBase[GeneralParkingPaymentUIFlowState]):
    def __init__(self) -> None:
        super().__init__(
            "你正在与用户进行沟通并尝试协助用户使用捷停车替他对车辆进行停车缴费。",
            ParkingSteps.GENERAL_PARKING_PAYMENT,
            {
                ParkingSteps.GENERAL_PARKING_PAYMENT:UIStepGeneral(),
            },
            debug_mode=True,
            intent_categories=general_parking_payment_intent_categories,
            state_cls=GeneralParkingPaymentUIFlowState,
            )
