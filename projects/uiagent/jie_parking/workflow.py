from typing import Any, Final

from pydantic import BaseModel, Field, field_validator

from projects.uiagent.core import (
    ClsResult,
    EUIAction,
    InfoTask,
    Page,
    RPAHandler,
    StepType,
    UIHandler,
    UITask,
    UITaskResult,
    UIStepStatus,
    WorkflowBase,
    WorkflowState,
    WorkflowStatus,
    InfoExecMode,
    IntentCategory,
    UIRouter,
)

from projects.uiagent.jie_parking.data_define import (
    ParkingSteps, 
    FeeCorrectOrNot, 
    OrderConfirmStatus, 
    PayOrNot,
    PlateNumber, 
    FeeKnowingStatus, 
    KnowingStatus
)

from projects.uiagent.jie_parking.rpa import rpa


class JieParkingState(WorkflowState):
    """捷停车工作流状态"""

    # TODO: 是否应该存在于state。目前没问题。
    default_user_plate: PlateNumber | None = Field(default=None, title="用户的本车车牌", description="用户的本车车牌")


    @field_validator("default_user_plate", mode="before")
    @classmethod
    def validate_default_user_plate(cls, v: Any) -> PlateNumber | None:
        if v is None:
            return None
        if isinstance(v, str):
            return PlateNumber(plate_number=v)
        if isinstance(v, PlateNumber):
            return v
        raise ValueError(f"用户默认车牌数据类型错误，不能是: {type(v)}")

class JieParkingWorkflow(WorkflowBase[JieParkingState]):
    # enable_reflect除了eval脚本，其他时候不要动
    def __init__(
            self,
            intent_categories: list[tuple[str, str]] = [intent.value for intent in IntentCategory],
            enable_reflect: bool = False
    ) -> None:
        self.pages: Final[list[Page]] = [
            Page(
                name="捷停车首页",
                description=f"""捷停车首页，特征是左下角首页处于蓝色选中状态，包括左上角弹出选择车辆车牌小窗的页面的状态，以及缴费信息确认弹窗的页面，但是不包括输入车牌页面！"""
            ),
            Page(
                name="车牌省份输入页面",
                description="在下方会看到一个输入键盘，键盘上都是省份名称简写。",
            ),
            Page(
                name="车牌号码输入页面",
                description="在下方会看到一个输入键盘，键盘上都是数字和大写字母信息。",
            ),
            Page(
                name="有订单页面",
                description="""可以在上方看到车牌信息，停车时长和订单金额，一般来说订单没问题的话就点击右下角确认订单进行下一步支付即可。"""
            ),
            Page(
                name="缴费信息确认页面",
                description="""可以看到缴费信息确认的提示。需要根据用户反馈，点击'去缴费'或'金额异常'"""
            ),
            Page(
                name="订单详情页面",
                description="""可以看到停车场信息，车牌信息和入场时间信息，一般来说订单没问题的话就点击右下角确认订单进行下一步支付即可。
                """,
            ),
            Page(
                name="缴费页面",
                description="如果你看到下面有个去支付按钮，那么点击去支付按钮即可，如果你看到画面正中央中出现一个付款二维码，\
                那么你在下一步就进行finished动作并且在其content内告诉用户直接扫码支付即可。",
            ),
        ]

        car_plate_info_task = InfoTask(brief="询问给哪辆车缴费", info_type=PlateNumber, validator=PlateNumber.validator, exec_mode=InfoExecMode.NEED_UI_IMAGE)
        
        ui_tasks : dict[StepType, UITask] = {
            ParkingSteps.SELECT_CAR: UITask(
                page=self.pages[0],
                # 注意，在选择车辆阶段就会有很多情况可以直接结束任务，因此要有FINISHED动作。详情请查看note。
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.FINISHED],
                info_task=car_plate_info_task,
                task_template="请根据下述用户希望缴费的车辆车牌信息确定点击按钮: {info}。",
                note=[],
            ),
            ParkingSteps.CONFIRM_FEE: UITask(
                page=self.pages[3],
                # 有订单的首页
                info_task=InfoTask(
                    brief="询问用户订单金额对不对,用户可能回答是或否或不知道或其他表示类似信息的语句。",
                    info_type=FeeCorrectOrNot,
                    validator=FeeCorrectOrNot.validator,
                    exec_mode=InfoExecMode.NEED_UI_IMAGE
                ),
                action_set=[EUIAction.CLICK, EUIAction.ASK],
                task_template="用户回答的订单金额是否正确或换车牌的信息如下：{info}。",
                note=[],
            ),

            ParkingSteps.CONFIRM_ORDER: UITask(
                page=self.pages[4],
                # 确认订单详情，可能要反问用户确认金额，或者直接点击确认缴费按钮。
                info_task=InfoTask(
                    brief="询问用户是否去缴费。",
                    info_type=OrderConfirmStatus,
                    validator=OrderConfirmStatus.validator,
                    exec_mode=InfoExecMode.NEED_UI_IMAGE
                ),
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.FINISHED],
                task_template="用户回答的是否去缴费的信息如下：{info}。如果用户表示确认缴费，那么点击去缴费按钮。",
            ),

            ParkingSteps.CONFIRM_PAY: UITask(
                page=self.pages[5],
                # 确认订单详情，可能要反问用户确认金额，或者直接点击确认缴费按钮。
                info_task=InfoTask(
                    brief="询问用户是否继续支付。",
                    info_type=PayOrNot,
                    validator=PayOrNot.validator,
                    exec_mode=InfoExecMode.NEED_UI_IMAGE
                ),
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.FINISHED],
                task_template="用户回答的是否确认支付的信息如下：{info}。如果用户表示确认支付，那么点击确认订单按钮。",
                note=[
                    "如果你看到弹窗说你当前位置距离太远，需要确认订单是否有误时，你需要再次询问用户确认订单是否有误；",
                ],
            ),

            ParkingSteps.PAYMENT: UITask(
                page=self.pages[6],
                # 缴费页面，见到二维码形式的话就finished
                action_set=[
                    EUIAction.CLICK,
                    EUIAction.FINISHED,
                ],  # TODO 询问用户是二维码支付还是发送到手机进行支付 构造info_task
                task="缴费，如果看到下面有去支付按钮，那么点击去支付，如果是二维码，那么用finished结束任务并在其content内告知用户扫码付款，其他情况请按照下面的注意事项进行操作。",
                note=[
                    "点击微信支付的勾选框（如果勾选着了就不用点了），然后直接点击下方的去支付按钮。",
                    "如果你看到中间出现一个叫订单支付的弹窗，在这个弹窗里面的中间靠近下边的地方有“二维码支付”几个字，那么点击二维码支付。",
                    "如果你看到了二维码，那么用finished结束任务并在其content内告知用户扫码付款。",
                    "如果你看到任何其他和支付无关的弹窗，统统点击关闭或拒绝等按钮以便继续进行支付任务。",
                ],
            ),
        }

        ui_task_handlers: dict[StepType, UIHandler] = {
            ParkingSteps.SELECT_CAR: self._select_car,
            ParkingSteps.CONFIRM_FEE: self._confirm_fee,
            ParkingSteps.CONFIRM_PAY: self._confirm_pay,
            ParkingSteps.PAYMENT: self._payment,
        }

        rpa_handlers: dict[StepType, RPAHandler] = {
            ParkingSteps.SELECT_CAR: rpa.rpa_select_car,
            ParkingSteps.INPUT_PLATE_PROVINCE: rpa.rpa_input_province_plate,
            ParkingSteps.INPUT_PLATE_LETTER_NUM: rpa.rpa_input_letter_num_plate,
            ParkingSteps.CONFIRM_FEE: rpa.rpa_confirm_fee,
            ParkingSteps.CONFIRM_ORDER: rpa.rpa_confirm_order,
            ParkingSteps.CONFIRM_PAY: rpa.rpa_confirm_pay,
            ParkingSteps.PAYMENT: rpa.rpa_payment,
        }

        ui_routers: dict[StepType, UIRouter] | None = {
            ParkingSteps.SELECT_CAR: UIRouter(
                categories = [(ParkingSteps.SELECT_CAR, self.pages[0])],
                router = rpa.val_select_car
        ), ParkingSteps.INPUT_PLATE_PROVINCE: UIRouter(
                categories = [(ParkingSteps.INPUT_PLATE_PROVINCE, self.pages[1])],
                router = rpa.val_input_province_plate
        ), ParkingSteps.INPUT_PLATE_LETTER_NUM: UIRouter(
                categories = [(ParkingSteps.INPUT_PLATE_LETTER_NUM, self.pages[2])],
                router = rpa.val_input_letter_num_plate
        ),
        }

        super().__init__(
            "你正在与用户进行沟通并尝试协助用户使用捷停车替他对车辆进行停车缴费。",
            ParkingSteps.SELECT_CAR,
            ui_tasks,
            ui_task_handlers,
            intent_categories=intent_categories,
            rpa_handlers=rpa_handlers,
            ui_routers=ui_routers,
            state_cls=JieParkingState,
            enable_reflect=enable_reflect,
            debug_mode=False
        )