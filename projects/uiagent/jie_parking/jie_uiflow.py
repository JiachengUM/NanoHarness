import re
import traceback
from enum import Enum
from typing import Any, Final, List

from openai import AsyncOpenAI
from pydantic import Field, field_validator, BaseModel

from nanoai.utils.data_concept import JudgeResult
from nanoai.utils.nl_repr import nl_repr
from projects.uiagent.core import Action
from projects.uiagent.core.action import ClickAction, AskAction, FinishedAction, Button, norm_actions
from projects.uiagent.core.uiflow import UIFlowBase, UIFlowState
from projects.uiagent.core.uistep import UIStepBase, UITask
from projects.uiagent.jie_parking.data_define import PlateNumber, ParkingSteps, UserMeaning, JieParkingReplyContents, \
    CheckKnowingStatus, KnowingStatus, PayOrNot, ConfirmPayKnowingStatus
from projects.uiagent.core.flow_data import (
    Page,
    _END_STEP,
    EUIAction,
    UIStepStatus,
    MiddleInfoType, StepType,
    WorkflowStatus, UIResult,
)
from projects.uiagent.jie_parking.new_workflow import (
    JieParkingSelectCarButtons,
    thought_instruction_for_button_name_generating, JieParkingConfirmPayButtons
)
from projects.uiagent.jie_parking.rpa.AndroidXmlParser import TextElementLocator
from projects.uiagent.jie_parking.rpa.rpa import bounds_to_center, plate_province_input, plate_letter_num_input
from projects.uiagent.utils.image_utils import get_image_dimensions


class JieFlowState(UIFlowState):

    """捷停车工作流状态"""
    # TODO: 是否应该存在于state。目前没问题。
    default_user_plate: PlateNumber | None = Field(
        default=None, title="用户的本车车牌", description="用户的本车车牌"
    )
    # TODO rpa无法对state进行修改
    # previous_actions_and_targets: list[ActionTarget] = Field(
    #     default_factory=list,
    #     title="之前进行过的操作和目标",
    #     description="之前进行过的操作和目标，每个元素是一个元组，第一个元素是操作，第二个元素是目标",
    # )
    clicked_refresh_order: bool = Field(
        default=False,
        title="是否点击了刷新订单按钮",
        description="是否点击了刷新订单按钮",
    )

    present_plate_number: PlateNumber | None = Field(
        default=None,
        title="当前各环节正在处理的车牌",
        description="当前各环节正在处理的车牌，因为用户可能经常切换车牌，而切换车牌发生在不同的step中，所以需要在这里记录当前正在处理的车牌。",
    )

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

class PageSelectCarButton(Enum):
    SWITCH_CAR = Button(name=JieParkingSelectCarButtons.SWITCH_CAR, description="是页面左上角的车牌号，是一个可以点击的按钮也就是该按钮，用来唤起切换或添加车辆车牌号")
    QUICK_PLATE = Button(name=JieParkingSelectCarButtons.QUICK_PLATE, description="左上角有弹出小窗且里面有多个车牌号时，如果有目标车牌，可以直接点击也就是该按钮进行切换")
    OTHER_CARS = Button(name=JieParkingSelectCarButtons.OTHER_CARS, description="左上角弹出小窗且里面有多个车牌号时，如果没有目标车牌号，需要点击其他车辆也就是该按钮进行新增车牌")
    REFRESH_ORDER = Button(name=JieParkingSelectCarButtons.REFRESH_ORDER, description="当当前车牌号未查询到停车信息时出现")
    VIEW_AMOUNT = Button(name=JieParkingSelectCarButtons.VIEW_AMOUNT, description="当金额过大时出现")
    RENEW_FEE = Button(name=JieParkingSelectCarButtons.RENEW_FEE, description="月卡用户时出现")
    VIEW_FEE_DETAILS = Button(name=JieParkingSelectCarButtons.VIEW_FEE_DETAILS, description="有普通小额停车订单时出现")
    INPUT_PLATE_PAY = Button(name=JieParkingSelectCarButtons.INPUT_PLATE_PAY, description="从头新增车牌时出现")
    LOCATION_AUTHORIZATION = Button(name=JieParkingSelectCarButtons.LOCATION_AUTHORIZATION, description="弹出定位授权窗口时，点击授权定位按钮")
    PAY_FEE = Button(name=JieParkingSelectCarButtons.PAY_FEE, description="如果你看到中间有个缴费信息确认弹窗时才有这个按钮")


class PageConfirmPayButton(Enum):

    CONFIRM_FEE = Button(name=JieParkingConfirmPayButtons.CONFIRM_FEE, description="确认订单按钮")
    CANCEL_AD = Button(name=JieParkingConfirmPayButtons.CANCEL_AD, description="取消广告按钮")
    CORRECT_AND_CONTINUE_PAYING = Button(name=JieParkingConfirmPayButtons.CORRECT_AND_CONTINUE_PAYING, description="费用正确并去缴费按钮")
    GO_TO_PAY = Button(name=JieParkingConfirmPayButtons.GO_TO_PAY, description="去支付XX金额按钮")


class PagePaymentButton(Enum):

    DIRECT_SCAN = Button(name="二维码支付", description="二维码支付按钮")


PAGES: dict[str, Page] = {
        ParkingSteps.SELECT_CAR: Page(
            name="捷停车首页",
            description=(
                f"捷停车首页，涉及3个页面，包括从头新增车牌、停车信息查看确认与车牌更换、以及大额订单下的缴费确认但是不包括输入车牌页面！"
                f"可以根据页面情况和用户需求更换车牌、刷新订单，查看金额，去续费、去缴费、地理位置授权、自动跳过广告、默认跳过欠费提示等。"
            ),
            ui_elements=[member.value for member in PageSelectCarButton]
        ),
        ParkingSteps.INPUT_PLATE_PROVINCE:  Page(
            name="车牌省份输入页面",
            description="下方有键盘，可以输入车牌号的省份。"
        ),
        ParkingSteps.INPUT_PLATE_LETTER_NUM:   Page(
            name="车牌字母数字输入页面",
            description="下方有键盘，可以输入车牌号的字母数字部分"
        ),
        ParkingSteps.CONFIRM_PAY:  Page(
            name="订单确认与支付确认页面",
            description="有订单确认及支付确认的按钮的页面，有时会弹出优惠券促销弹窗，有时会弹出距离过远需要用户确认",
            ui_elements=[member.value for member in PageConfirmPayButton]
        ),
        ParkingSteps.PAYMENT:  Page(
            name="支付页面",
            description="有支付方式选择和展示的页面",
            ui_elements=[member.value for member in PagePaymentButton]
        ),
}


class UIStepSelectCar[S](UIStepBase):
    '''最简单的ui step实现，只需要一个中间信息，校验也很简单。'''
    def __init__(self):
        super().__init__(
            step=ParkingSteps.SELECT_CAR,
            ui_task=UITask(
                page=PAGES[ParkingSteps.SELECT_CAR],
                note=[
                    "仔细阅读并严格执行下述指引，否则干死你。",
                    "无论何时，如果你并不知道当前用户正在希望进行缴费的车辆车牌信息，那么用ask_human来向用户询问。否则你无法进行下面的任务。",
                    "任何时候，遇到下面没有提到的情况，都请记住：一切围绕尽快帮用户完成停车缴费进行。",
                    "任何时候，如果你看到有弹窗了，那么忽略弹窗之外的内容！只关注弹窗内的内容并操作！",
                    "如果你在当前页面上没有看到任何车辆信息，并且看到让你添加车辆，输车牌缴费，那么点击输车牌缴费；",
                    "如果你看到当前页面左上角没有小弹窗，直接有一个车牌信息，那么首先和用户当前最新表达的意思里的当前用户正在希望进行缴费的车辆车牌号对比，确认是否是当前用户正在希望进行缴费的车辆，如果不是，那么直接点击左上角的车牌号；",
                    "如果你看到当前页面在左上角弹出了一个小弹窗，里面有一个或多个车牌信息，以及其他车辆和绑定车辆选项，\
                    那么首先比对确认是否存在当前用户的车辆牌照号，如果有，那么直接点击之，如果没有，那么点击其他车辆选项；",
                    "当你看到并最终确认当前页面左上角无弹窗且直接有一个和用户当前最新表达的意思里的用户车牌号相同的车牌号时，那么你会看到当前用户车辆的在该停车场的订单状况。"
                    "此时，你需要根据你看到的不同当前视野下的页面情况进行不同的操作，仔细看下面的指引进行操作：",
                    "   - 如果你看到按钮名称显示无感支付已开启，那么直接用finished动作结束任务并在其content里告诉用户你可以直接开出去了因为你已开通无感支付。",
                    f"   - 如果是当前用户希望缴费的车辆不存在订单的情况，那么尝试点击{JieParkingSelectCarButtons.REFRESH_ORDER}按钮。",
                    f"   - 如果你看到弹出了授权定位弹窗，此时你集中注意力在这个弹窗之中并忽略其他部分，然后用askhuman告诉用户：{JieParkingReplyContents.ASK_LOCATION_PERMITION}；",
                    f"   - 如果你看到当前页面上显示“金额过大，缴费前请确认”，且用户当前最新表达的意思里并没有明确表达用户是否希望查看金额或费用明细或去缴费，那么你需要用ask_human来向用户回复：{JieParkingReplyContents.ASK_CHECK_BIG_FEE_OR_NOT}。如果用户当前最新表达的意思里明确表示他希望查看金额或费用明细或去缴费，那么你需要点击{JieParkingSelectCarButtons.VIEW_AMOUNT}按钮，而如果用户当前最新表达的意思里明确表示他并不想查看金额或费用明细或去缴费，那么那么直接用finished动作结束任务并在其content里告诉用户：{JieParkingReplyContents.FINISHED_USER_ABORT}",
                    f"   - 如果你看到当前页面上显示“查看费用明细”，且用户当前最新表达的意思里并没有明确表达用户是否希望查看金额或费用明细或去缴费，那么你需要用ask_human来向用户回复：当前订单车牌号为xxx（当前用户正在希望进行缴费的车辆车牌），停车时长为xxx（具体取决于你看到的弹窗里的停车时长），金额为多少多少元（具体取决于你看到的数额），{JieParkingReplyContents.ASK_CONFIRM_FEE}。如果用户当前最新表达的意思里明确表示了他希望查看金额或费用明细或去缴费，那么你需要点击{JieParkingSelectCarButtons.VIEW_FEE_DETAILS}按钮，而如果用户当前最新表达的意思里明确表示了当前金额是不对的错误的，那么那么直接用finished动作结束任务并在其content里告诉用户：{JieParkingReplyContents.FINISHED_USER_ABORT}",
                    f"   - 如果你看到当前页面上显示“缴费信息确认”的弹窗，那么这里已经是大额金额确认环节了，此时你集中注意力在这个弹窗之中并忽略其他部分。如果用户当前最新表达的意思里并没有明确表达用户是否确认大额费用是否正确，那么你需要用ask_human来向用户回复：当前大额订单车牌号为xxx（当前用户正在希望进行缴费的车辆车牌），停车时长为xxx（具体取决于你看到的弹窗里的停车时长），金额为多少多少元（具体取决于你看到的数额），{JieParkingReplyContents.ASK_CONFIRM_FEE}。如果用户当前最新表达的意思里明确表示了大额费用是正确的，那么你需要点击{JieParkingSelectCarButtons.PAY_FEE}按钮，而如果用户当前最新表达的意思里明确表示了大额费用是不对的错误的，那么那么直接用finished动作结束任务并在其content里告诉用户：{JieParkingReplyContents.FINISHED_USER_ABORT}",
                    f"   - 如果你看到当前页面上显示“无需缴费”，那么直接用finished动作结束任务并在其content里告诉用户：当前订单车牌号为xxx（当前用户正在希望进行缴费的车辆车牌），{JieParkingReplyContents.FINISHED_NO_NEED_TO_PAY}。",
                    f"   - 如果你看到当前页面上显示“请前往人工收费缴费”，那么直接用finished动作结束任务并在其content里告诉用户：当前订单车牌号为xxx（当前用户正在希望进行缴费的车辆车牌），{JieParkingReplyContents.FINISHED_MANUALY_REPLY}。",
                    f"   - 如果你看到当前页面上显示“月卡用户”，那么直接用finished动作结束任务并在其content里告诉用户：当前订单车牌号为xxx（当前用户正在希望进行缴费的车辆车牌），{JieParkingReplyContents.FINISHED_MONTHLY_PASS}。",
                    f"   - 如果你看到当前页面上显示“补缴欠费”弹窗，此时你集中注意力在这个弹窗之中并忽略其他部分。那么直接用finished动作结束任务并在其content里告诉用户：当前订单车牌号为xxx（当前用户正在希望进行缴费的车辆车牌），{JieParkingReplyContents.FINISHED_DEBT_PAY}。",
                    "   -如果你看到任何图片验证弹窗，那么发挥你最大的想象力，正确地理解该弹窗里给你的任务并执行正确的操作，目的是成功通过验证。",
                    "   - 任何时候用户在最新表达的意思里明确表示他希望退出，那么直接用finished动作结束任务并在其content里告诉用户：好的，退出当前任务。",
                    "   - 绝对不要自己编造任何动作空间不存在的动作，以及不存在的动作参数，参数一定要按照动作空间规定的填写，不要乱填。",
                    "   - 每一次只进行一个Action动作，绝对不可以多个。",
                    thought_instruction_for_button_name_generating,
                    "   - 好好遵循上面的指引，否则干死你。"
                ],
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.FINISHED],
            ),
            task_gen=lambda info: (
                "你是个非常强大的非常聪明的智能助手，非常擅长使用动作操作来解决问题。"
                "请根据下述用户当前最新表达的意思（特别是当前用户正在希望进行缴费的车辆车牌，"
                "一切待缴费对象以这个车牌为准，如果这个缺失要向用户询问而不要擅自从图像中理解和提取。），"
                f"来进行接下来的操作。相关车牌和确认信息记录如下：\n{nl_repr(next(iter(info.values())))}。"
            ),
            action_map=self._action_map,
            middle_info_define=UserMeaning,  # TODO 需要有一个能很好说明该字段意义的key，使用默认的会是一个id,不够直观。也许可以使用basemodel的各个字段的title来记录？
            rpa_handler=self._rpa_handler,
        )

    async def _run_ui_task(
            self,
            image: str,
            image_format: str,
            xml: str | None,
            middle_info: MiddleInfoType,
            /,
            *,
            state: S,
            model: str,
            client: AsyncOpenAI,
    ) -> UIResult:
        '''TODO: '''

        # TODO: 如果有rpa_handler，但xml为None，应该有个warning
        if self.rpa_handler and xml is not None:
            try:
                actions = self.rpa_handler(xml, middle_info, state)
                # TODO: 应该传入ui task的page，并通过其action_set检查actions是否合法
                width, height = get_image_dimensions(image)
                actions = norm_actions(actions, width, height)

                # TODO: 这里包了一个无意义的UITaskResult。应该支持返回list[Action]么？不确定。
                result = UIResult(raw_prompt="", thought="", action_content="", actions=actions, source="rpa")
                return result
            except Exception as e:
                print(f"rpa处理失败:{traceback.format_exc()}")

        if self.task_gen:
            result, prompt = await self.ui_task.arun(image, image_format, task=self.task_gen(middle_info),
                                                     model=model, client=client)
        else:
            result, prompt = await self.ui_task.arun(image, image_format, model=model, client=client)
        if isinstance(result, UIResult):
            actions = result.actions
            if actions:
                action = actions[0]
                if isinstance(action, ClickAction):
                    button_name = action.target_ui_element.name if action.target_ui_element else None
                    if button_name == JieParkingSelectCarButtons.REFRESH_ORDER:
                        if state.clicked_refresh_order:
                            state.clicked_refresh_order = False
                            result.actions = [AskAction(content=JieParkingReplyContents.ASK_NO_ORDER)]
                        else:
                            state.clicked_refresh_order = True
        return result

    def _action_map(self, actions: list[Action]) -> tuple[StepType, UIStepStatus]:
        """
        Callable[[list[Action]], tuple[StepType, UIStepStatus]]
        """
        assert len(actions) <= 1, f'仅支持返回一个动作'
        action = actions[0]
        if isinstance(action, ClickAction):
            button_name = action.target_ui_element.name if action.target_ui_element else None
            match button_name:
                # 如果result点击了快捷车牌号，切换车辆，查看金额，刷新订单按钮下一步继续SELECT_CAR
                case (JieParkingSelectCarButtons.SWITCH_CAR
                    | JieParkingSelectCarButtons.QUICK_PLATE
                    | JieParkingSelectCarButtons.VIEW_AMOUNT):
                    return ParkingSteps.SELECT_CAR, UIStepStatus.WAIT_FOR_IMAGE
                case JieParkingSelectCarButtons.REFRESH_ORDER.value:
                    return ParkingSteps.SELECT_CAR, UIStepStatus.WAIT_FOR_IMAGE
                case (JieParkingSelectCarButtons.OTHER_CARS | JieParkingSelectCarButtons.INPUT_PLATE_PAY):
                    return ParkingSteps.INPUT_PLATE_PROVINCE, UIStepStatus.WAIT_FOR_IMAGE
                case (JieParkingSelectCarButtons.VIEW_FEE_DETAILS | JieParkingSelectCarButtons.PAY_FEE):
                    return ParkingSteps.CONFIRM_PAY, UIStepStatus.WAIT_FOR_IMAGE
                case _:
                    return ParkingSteps.SELECT_CAR, UIStepStatus.WAIT_FOR_IMAGE
        elif isinstance(action, FinishedAction):
            return ParkingSteps.END, UIStepStatus.RUNNING
        elif isinstance(action, AskAction):
            return ParkingSteps.SELECT_CAR, UIStepStatus.WAIT_FOR_INFO
        else:
            return ParkingSteps.SELECT_CAR, UIStepStatus.WAIT_FOR_IMAGE

    def _rpa_handler(self, xml: str, info: MiddleInfoType, state: S) -> list[Action]:
        """
        Callable[[str, MiddleInfoType], list[Action]]
        """
        info = next(iter(info.values()))
        if '普通车牌' in xml:
            # todo 错误传了键盘输入页面 可以放在router中？
            raise ValueError(f"select car can't handle inputting plate page")
        if isinstance(info, UserMeaning):
            if isinstance(info.plate_number, PlateNumber):
                user_wanted_plate_num = info.plate_number.plate_number
            else:
                user_wanted_plate_num = info.plate_number
        else:
            user_wanted_plate_num = info

        if not user_wanted_plate_num:
            current_step = ParkingSteps.SELECT_CAR
            # TODO 和产品保持一致 避免HARD CODE
            action = AskAction(
                content=JieParkingReplyContents.NEED_PLATE_NUMBER)
            return [action]

        xml_parser = TextElementLocator(xml)
        # 新增车牌第一位
        if "添加车辆缴费免排队、免找零" in xml and "请输入车牌授权定位，提高查费准确性" not in xml:
            # 页面判断
            # 页面1： 输车牌缴费 3005
            ele = xml_parser.get_first_element_by_text("添加车辆缴费免排队、免找零")
            # 状态仍然是选择车牌 TODO 坐标硬编码 mark
            # TODO硬编码
            action = ClickAction(
                x=ele["center"][0], y=ele["center"][1] + 75,  #TODO硬编码
                target_ui_element=PageSelectCarButton.INPUT_PLATE_PAY.value
            )  # 该元素下方才是点击添加车牌
            current_step = ParkingSteps.INPUT_PLATE_PROVINCE

            return [action]
        # 从后往前判断
        # 去缴费页面
        if "去缴费" in xml:
            # 判断用户是否确认缴费
            fee_check_or_not: KnowingStatus = info.fee_correct_or_not
            if fee_check_or_not == KnowingStatus.NO:
                #　state.status = WorkflowStatus.USER_ABORT # TODO 理论上不能操作
                action = FinishedAction(content=JieParkingReplyContents.FINISHED_CONFIRM_FEE_NOT_CORRECT)
                return [action]
            elif fee_check_or_not == KnowingStatus.YES:
                ele = xml_parser.get_first_element_by_text("去缴费")
                action = ClickAction(x=ele["center"][0], y=ele["center"][1], target_ui_element=PageSelectCarButton.PAY_FEE.value)
                return [action]
            else:
                #　缴费信息确认　"1860.00元"
                fee_pattern = re.compile(r'缴费信息确认.*?text="(?P<fee>[\d\.元]+)"', re.DOTALL)
                fee_match = fee_pattern.search(xml)
                fee = fee_match.groupdict()['fee'] if fee_match else ''
                if fee:
                    feedback = f"请问{fee}金额是否正确？正确的话请回复正确或去缴费，我将为您展示订单明细。"
                else:
                    feedback = JieParkingReplyContents.ASK_BIG_FEE_DETAIL_OR_NOT
                action = AskAction(content=feedback)
                return [action]
        # 车牌判断，用户车牌和显示的车牌是否一致
        plate_pattern = r'<node[^>]*?text="([京津冀晋蒙辽吉黑沪苏浙皖闽赣鲁豫鄂湘粤桂琼渝川黔云藏陕甘青宁新][A-Z][A-Z0-9]{5,6})"[^>]*?bounds="([^"]+)"'
        plate_match = re.search(plate_pattern, xml)
        # 是否是输入车牌号+查询缴费页面
        assert plate_match, "添加车牌号后，页面上一定有车牌"
        # 获取页面上的车牌并与用户输入的车牌匹配
        matches = len(re.findall(plate_pattern, xml))
        assert matches >= 1, "添加车牌号后，页面上一定有车牌"
        if matches == 1:
            visible_plate_number = plate_match.group(1)
            if "其他车辆" in xml:
                ele = xml_parser.get_first_element_by_text("其他车辆")
                current_step = ParkingSteps.INPUT_PLATE_PROVINCE
                action = ClickAction(x=ele["center"][0], y=ele["center"][1], target_ui_element=PageSelectCarButton.OTHER_CARS.value)
                # 状态仍然是选择车牌
                return [action]
            elif visible_plate_number != user_wanted_plate_num and user_wanted_plate_num:
                assert visible_plate_number in xml
                ele = xml_parser.get_first_element_by_text(visible_plate_number)
                current_step = ParkingSteps.SELECT_CAR
                action = ClickAction(x=ele["center"][0], y=ele["center"][1], target_ui_element=PageSelectCarButton.SWITCH_CAR.value)
                # 状态仍然是选择车牌
                return [action]
            else:  # visible_plate_number == user_wanted_plate_num or not user_wanted_plate_num
                if "未查询到停车信息" in xml:  # 刷新订单
                    if state.clicked_refresh_order:
                        state.clicked_refresh_order = False
                        action = AskAction(content=JieParkingReplyContents.ASK_NO_ORDER.value)
                        current_step = ParkingSteps.SELECT_CAR
                        return [action]
                    else:
                        ele = xml_parser.get_first_element_by_text("刷新订单")
                        action = ClickAction(x=ele["center"][0], y=ele["center"][1], target_ui_element=PageSelectCarButton.REFRESH_ORDER.value)
                        state.clicked_refresh_order = True
                        return [action]
                elif "月卡用户" in xml or "月卡剩余" in xml:
                    current_step = ParkingSteps.SELECT_CAR  # TODO END STEP
                    action = AskAction(content=JieParkingReplyContents.FINISHED_MONTHLY_PASS)
                    return [action]
                elif "人工收费" in xml:
                    current_step = ParkingSteps.SELECT_CAR
                    action = AskAction(content=JieParkingReplyContents.FINISHED_MANUALY_REPLY)
                    return [action]
                elif "无需缴费" in xml:
                    current_step = ParkingSteps.SELECT_CAR
                    action = AskAction(content=JieParkingReplyContents.FINISHED_NO_NEED_TO_PAY)
                    return [action]
                # TODO 路由补缴欠费页面
                elif "补缴欠费" in xml:
                    # TODO 欠费提醒是否需要用户确认
                    action = AskAction(content=JieParkingReplyContents.FINISHED_DEBT_PAY)
                    current_step = ParkingSteps.SELECT_CAR
                    return [action]
                elif "金额过大，缴费前请确认" in xml:
                    big_fee_check_or_not: CheckKnowingStatus = info.fee_check_or_not
                    if big_fee_check_or_not == CheckKnowingStatus.NO:
                        # state.status = WorkflowStatus.USER_ABORT
                        action = FinishedAction(content=JieParkingReplyContents.FINISHED_USER_ABORT)
                        return [action]
                    elif big_fee_check_or_not == CheckKnowingStatus.YES:
                        ele = xml_parser.get_first_element_by_text("查看金额")
                        action = ClickAction(x=ele["center"][0], y=ele["center"][1], target_ui_element=PageSelectCarButton.VIEW_AMOUNT.value)
                        return [action]
                    else:
                        park_time_pattern = re.compile(r'text="已停[：:](?P<park_time>[^"]*)"')
                        park_time_match = park_time_pattern.search(xml)
                        park_time = park_time_match.groupdict()['park_time'] if park_time_match else ''
                        if park_time:
                            prefix = f"当前车牌号{visible_plate_number}，停车{park_time}，"
                        else:
                            prefix = ""
                        action = AskAction(content=prefix + JieParkingReplyContents.ASK_CHECK_BIG_FEE_OR_NOT)
                        return [action]
                elif "查看费用明细" in xml:
                    fee_check_or_not: CheckKnowingStatus = info.fee_check_or_not
                    if fee_check_or_not == CheckKnowingStatus.NO:
                        state.status = WorkflowStatus.USER_ABORT
                        action = FinishedAction(content=JieParkingReplyContents.FINISHED_CONFIRM_FEE_NOT_CORRECT)
                        return [action]
                    elif fee_check_or_not == CheckKnowingStatus.YES:
                        ele = xml_parser.get_first_element_by_text("查看费用明细")
                        action = ClickAction(x=ele["center"][0], y=ele["center"][1], target_ui_element=PageSelectCarButton.VIEW_FEE_DETAILS.value)
                        return [action]
                    else:
                        fee_pattern = re.compile(r'￥.*?text="(?P<fee>[\d\.]+)"', re.DOTALL)
                        fee_match = fee_pattern.search(xml)
                        fee = fee_match.groupdict()['fee'] if fee_match else ''
                        park_time_pattern = re.compile(r'text="已停[：:](?P<park_time>[^"]*)"')
                        park_time_match = park_time_pattern.search(xml)
                        park_time = park_time_match.groupdict()['park_time'] if park_time_match else ''
                        if fee and park_time:
                            prefix = f"当前车牌号{visible_plate_number}，订单金额{fee}元，停车{park_time}，"
                        elif fee:
                            prefix = f"当前车牌号{visible_plate_number}，订单金额{fee}元，"
                        elif park_time:
                            prefix = f"当前车牌号{visible_plate_number}，停车{park_time}，"
                        else:
                            prefix = ""
                        action = AskAction(content=prefix + JieParkingReplyContents.ASK_CONFIRM_FEE)
                        return [action]
                else:
                    raise Exception(f"xml无效，无rpa可识别的关键信息")

        else:
            # 此时应处于其他车辆页面，绑定的车牌中可能有目标车牌
            assert "其他车辆" in xml, "其他车辆按钮页面未找到"  # TODO 尝试放到ui validator中
            # 点击目标车牌进行更换，不用再输入车牌
            if user_wanted_plate_num and (ele := xml_parser.get_first_element_by_text(user_wanted_plate_num)):
                current_step = ParkingSteps.SELECT_CAR
                action = ClickAction(x=ele["center"][0], y=ele["center"][1], target_ui_element=PageSelectCarButton.QUICK_PLATE.value)
                return [action]
            # 如果页面显示的多个车牌中，没有目标车牌，需要点击其他车辆进行新增，并输入车牌
            ele = xml_parser.get_first_element_by_text("其他车辆")
            action = ClickAction(x=ele["center"][0], y=ele["center"][1], target_ui_element=PageSelectCarButton.OTHER_CARS.value)
            current_step = ParkingSteps.INPUT_PLATE_PROVINCE
            return [action]

    def _validate_info(self, info: MiddleInfoType) -> JudgeResult:

        self._validate_info_type(info)
        info = next(iter(info.values()))
        if not info:
            # 第一步先传了图片，此时info为 None
            return JudgeResult(judgment=True, reason="")
        elif isinstance(info, UserMeaning):
            if info.plate_number:
                if PlateNumber.validator(info.plate_number).judgment:
                    return JudgeResult(judgment=True, reason="")
                else:
                    return JudgeResult(judgment=False, reason=JieParkingReplyContents.ASK_ILLEGAL_PLATE_NUMBER.value)
            else:
                return JudgeResult(judgment=True, reason="")
        else:
            return JudgeResult(judgment=True, reason="")


class UIStepInputPlateProvince[S](UIStepBase):

    keyboard = Button(name="keyboard", description="键盘目标省份按钮")
    input_box = Button(name="input_box", description="省份输入框")

    def __init__(self):
        super().__init__(
            ParkingSteps.INPUT_PLATE_PROVINCE,
            UITask(
                page=PAGES[ParkingSteps.INPUT_PLATE_PROVINCE],
                task="输入车牌号的省份",
                action_set=[EUIAction.CLICK]
            ),
            middle_info_define=PlateNumber,
            rpa_handler=self._rpa_handler,
            action_map=self._action_map,
        )

    def _action_map(self, actions: list[Action]) -> tuple[StepType, UIStepStatus]:
        if len(actions) == 1:
            if isinstance(actions[0], ClickAction):
                if actions[0].target_ui_element.name == self.keyboard.name:
                    return ParkingSteps.INPUT_PLATE_LETTER_NUM, UIStepStatus.WAIT_FOR_IMAGE
            if isinstance(actions[0], AskAction):
                return ParkingSteps.INPUT_PLATE_PROVINCE, UIStepStatus.WAIT_FOR_INFO
        return  ParkingSteps.INPUT_PLATE_PROVINCE, UIStepStatus.WAIT_FOR_IMAGE

    def _rpa_handler(self, xml: str, info: MiddleInfoType) -> List[Action]:
        info = next(iter(info.values()))
        plate_number = info.plate_number if isinstance(info, PlateNumber) else info
        if not plate_number:
            return [AskAction(content=JieParkingReplyContents.NEED_PLATE_NUMBER)]
        xml_parser = TextElementLocator(xml)
        pattern = re.compile(r'特殊车牌.*?index="0".*?text="([^"]?)".*?bounds="([^"]+)', re.DOTALL)
        match = pattern.search(xml)
        assert match, "rpa处理失败，未从xml中找到省份输入框"
        province = match.group(1)
        province_bounds = match.group(2)
        x, y = bounds_to_center(province_bounds)
        # 有键盘
        if all(
                [len(x) >= 1 for x in (xml_parser.get_all_elements_by_text(p) for p in "京津沪渝")]
        ):
            # 省份输入框为空
            if province == "":  # 旧的情况
                action = plate_province_input(plate_number, xml)
                assert action
                action.target_ui_element = self.keyboard
                current_step = ParkingSteps.INPUT_PLATE_LETTER_NUM
                return [action]
            # 省份输入框部位空
            else:  # 有省份， 页面就不会是省份键盘
                # 已有的车牌号输入不对，需要重新更换
                action1 = ClickAction(x=x, y=y, target_ui_element=self.input_box)  # 点击已有的错误省份 默认键盘能被唤起
                action2 = plate_province_input(plate_number, xml)
                assert action2
                action2.target_ui_element = self.keyboard
                current_step = ParkingSteps.INPUT_PLATE_LETTER_NUM
                return [action1, action2]
        else:
            # 键盘未加载，点击第一个省份输入框唤起
            action = ClickAction(x=x, y=y, target_ui_element=self.input_box)
            current_step = ParkingSteps.INPUT_PLATE_PROVINCE
            return [action]


class UIStepInputPlateLetterNum[S](UIStepBase):
    keyboard = Button(name="keyboard", description="键盘目标省份按钮")
    input_box = Button(name="input_box", description="省份输入框")

    def __init__(self):
        super().__init__(
            ParkingSteps.INPUT_PLATE_LETTER_NUM,
            UITask(
                page=PAGES[ParkingSteps.INPUT_PLATE_LETTER_NUM],
                task="输入车牌号的非省份部分",
                action_set=[EUIAction.CLICK]
            ),
            middle_info_define=PlateNumber,
            rpa_handler=self._rpa_handler,
            action_map=self._action_map,
        )

    def _action_map(self, actions: list[Action]) -> tuple[StepType, UIStepStatus]:
        if len(actions) == 1:
            return ParkingSteps.INPUT_PLATE_PROVINCE, UIStepStatus.WAIT_FOR_IMAGE
        return ParkingSteps.SELECT_CAR, UIStepStatus.WAIT_FOR_IMAGE

    def _rpa_handler(self, xml: str, info: MiddleInfoType) -> List[Action]:
        info = next(iter(info.values()))
        plate_number = info.plate_number if isinstance(info, PlateNumber) else info
        assert plate_number, "进入车牌号输入rpa前，必须提供车牌号"

        # 省份判断，如果省份都未输入，则应该重新去输入省份
        pattern = re.compile(r'特殊车牌.*?index="0".*?text="([^"]?)".*?bounds="([^"]+)', re.DOTALL)
        match = pattern.search(xml)
        assert match, "rpa处理失败，未从xml中找到省份输入框"
        province = match.group(1)
        province_bounds = match.group(2)
        x, y = bounds_to_center(province_bounds)
        if not province or province != plate_number[0]:
            # 省份都没有，需要重新去输入省份
            action = ClickAction(x=x, y=y)
            current_step = ParkingSteps.INPUT_PLATE_PROVINCE
            return [action]
        # 只有确认好了车牌号，可以查询缴费，才走到下一步
        actions = plate_letter_num_input(plate_number, xml)
        assert actions, f"键盘加载完毕+有有效车牌，必定有actions"
        # current_step = ParkingSteps.SELECT_CAR
        current_step = ParkingSteps.SELECT_CAR
        return actions



class UIStepConfirmPay[S](UIStepBase):

    def __init__(self):
        super().__init__(
            ParkingSteps.CONFIRM_PAY,
            UITask(
                page=PAGES[ParkingSteps.CONFIRM_PAY],
                task="确认订单并点击支付，有广告页面|优惠券时优先关闭，有费用确认页面优先自动确认费用为正确。",
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.FINISHED],
                note=[
                    "如果你看到弹窗说你当前位置距离太远，需要确认订单是否有误时，你直接点击正确，继续缴费按钮即可；",
                    "如果你看到任何其他和支付无关的弹窗，统统点击关闭或拒绝等按钮以便继续进行支付任务。",
                ]
            ),
            middle_info_define=PayOrNot,
            task_gen=lambda info: f"用户回答的是否确认支付的信息如下：\n{nl_repr(next(iter(info.values())))}。如果用户表示确认支付，那么点击确认订单按钮。",
            rpa_handler=self._rpa_handler,
            action_map=self._action_map,
        )

    def _action_map(self, actions: list[Action]) -> tuple[StepType, UIStepStatus]:
        assert len(actions) == 1
        the_action = actions[0]
        if isinstance(the_action, AskAction):
            return ParkingSteps.CONFIRM_PAY, UIStepStatus.WAIT_FOR_INFO
        if isinstance(the_action, FinishedAction):
            return ParkingSteps.END, UIStepStatus.RUNNING
        if isinstance(the_action, ClickAction):
            if (
                    the_action.target_ui_element.name == JieParkingConfirmPayButtons.GO_TO_PAY
                or JieParkingConfirmPayButtons.GO_TO_PAY.value in the_action.target_ui_element.name
            ):
                return ParkingSteps.PAYMENT, UIStepStatus.WAIT_FOR_IMAGE
        return ParkingSteps.CONFIRM_PAY, UIStepStatus.WAIT_FOR_IMAGE

    def _rpa_handler(self, xml: str, info: MiddleInfoType) -> List[Action]:
        info = next(iter(info.values()))
        xml_parser = TextElementLocator(xml)
        if ele := xml_parser.get_first_element_by_text("取消购买确认购买"):
            # TODO 此处-150为硬编码，需要考虑APP像素变化
            current_step = ParkingSteps.CONFIRM_PAY
            width = ele['width']
            x_bias = width / 4
            action = ClickAction(x=ele["center"][0] - x_bias, y=ele["center"][1], target_ui_element=PageConfirmPayButton.CANCEL_AD.value)
            return [action]
        if ele := xml_parser.get_first_element_by_text("正确，继续缴费"):
            current_step = ParkingSteps.CONFIRM_PAY
            action = ClickAction(x=ele["center"][0], y=ele["center"][1], target_ui_element=PageConfirmPayButton.CORRECT_AND_CONTINUE_PAYING.value)
            return [action]

        pay_or_not: ConfirmPayKnowingStatus = info.pay_or_not if isinstance(info, PayOrNot) else info
        assert pay_or_not in [ConfirmPayKnowingStatus.YES, ConfirmPayKnowingStatus.NO]
        if pay_or_not == ConfirmPayKnowingStatus.NO:
            return [FinishedAction(content=JieParkingReplyContents.FINISHED_USER_ABORT)]

        if "入场时间" in xml and (ele := xml_parser.get_first_element_by_text("确认订单")):
            action = ClickAction(x=ele["center"][0], y=ele["center"][1], target_ui_element=PageConfirmPayButton.CONFIRM_FEE.value)
            current_step = ParkingSteps.CONFIRM_PAY
            return [action]
        # 去支付按钮
        if ele := xml_parser.get_first_element_by_pattern(re.compile("去支付.+")):
            action = ClickAction(x=ele["center"][0], y=ele["center"][1], target_ui_element=PageConfirmPayButton.GO_TO_PAY.value)
            current_step = ParkingSteps.PAYMENT
            return [action]
        raise Exception("rpa处理失败，未从xml中获取'确认订单'或'去支付'按钮")


class UIStepPayment[S](UIStepBase):

    def __init__(self):
        super().__init__(
            ParkingSteps.PAYMENT,
            UITask(
                page=PAGES[ParkingSteps.PAYMENT],
                task="缴费，如果看到下面有去支付按钮，那么点击去支付，如果是二维码，那么用finished结束任务并在其content内告知用户扫码付款。",
                note=[
                    "如果你看到点击微信支付的勾选框（如果勾选着了就不用点了），那么直接点击下方的去支付按钮。",
                    "如果你看到中间一个弹窗里的下方有二维码支付几个字，那么点击二维码支付。",
                    "如果你看到了二维码，那么用finished结束任务并在其content内告知用户扫码付款。",
                    "如果你看到任何其他和支付无关的弹窗，统统点击关闭或拒绝等按钮以便继续进行支付任务。",
                ],
                action_set=[EUIAction.CLICK, EUIAction.FINISHED],
            ),
            rpa_handler=self._rpa_handler,
            action_map=self._action_map,
        )

    def _action_map(self, actions: list[Action]) -> tuple[StepType, UIStepStatus]:
        assert len(actions) == 1
        the_action = actions[0]
        if isinstance(the_action, FinishedAction):
            return _END_STEP, UIStepStatus.IDLE
        return ParkingSteps.PAYMENT, UIStepStatus.WAIT_FOR_IMAGE

    def _rpa_handler(self, xml: str, info: MiddleInfoType | None) -> List[Action]:
        xml_parser = TextElementLocator(xml)
        # 默认选择二维码支付
        if ele := xml_parser.get_first_element_by_text("二维码支付"):
            current_step = ParkingSteps.PAYMENT
            action = ClickAction(x=ele["center"][0], y=ele["center"][1])
            return [action]
        elif "请使用微信扫码支付" in xml:
            current_step = ParkingSteps.END  # END
            return [FinishedAction(content=JieParkingReplyContents.FINISH_SCAN)]
        raise Exception("rpa支付环节处理失败，非选择二维码支付及弹出二维码页面")

jie_parking_intent_categories = [
        ("Relevant", "任何与停车缴费可能相关的意图，包括但不限于说个车牌号，支付与否，正确与否等等。"),
        ("Abort", '用户希望退出，终止，取消当前工作的意图。'),
        ("Irrelevant", "其他任何与停车缴费无关的意图统统属于这个。"),
    ]

class JieUIFlow(UIFlowBase[JieFlowState]):
    def __init__(self) -> None:
        super().__init__(
            "你正在与用户进行沟通并尝试协助用户使用捷停车替他对车辆进行停车缴费。",
            ParkingSteps.SELECT_CAR,
            {
                ParkingSteps.SELECT_CAR: UIStepSelectCar[JieFlowState](),
                ParkingSteps.INPUT_PLATE_PROVINCE: UIStepInputPlateProvince[JieFlowState](),
                ParkingSteps.INPUT_PLATE_LETTER_NUM: UIStepInputPlateLetterNum[JieFlowState](),
                ParkingSteps.CONFIRM_PAY: UIStepConfirmPay[JieFlowState](),
                ParkingSteps.PAYMENT: UIStepPayment[JieFlowState](),
            },
            debug_mode=True,
            intent_categories=jie_parking_intent_categories,
            state_cls=JieFlowState,
            )
        self.state.clicked_refresh_order = False # 默认就是False, 可以不用设置

