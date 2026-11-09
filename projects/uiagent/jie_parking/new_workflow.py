from enum import StrEnum
import logging
import re
from typing import Any, Final

from pydantic import Field, field_validator

from nanoai.utils.nl_repr import nl_repr
from projects.uiagent.core import (
    EUIAction,
    InfoExecMode,
    InfoTask,
    Page,
    RPAHandler,
    StepType,
    UIHandler,
    UIRouter,
    UIStepStatus,
    UITask,
    UITaskResult,
    WorkflowBase,
    WorkflowState,
    WorkflowStatus,
)
from projects.uiagent.core.action import Action, AskAction, ClickAction, FinishedAction
from projects.uiagent.jie_parking.data_define import (
    KnowingStatus,
    ParkingSteps,
    PayOrNot,
    PlateNumber,
    JieParkingReplyContents,
    UserMeaning,
    CheckKnowingStatus,
    ConfirmPayKnowingStatus
)
from projects.uiagent.jie_parking.rpa import rpa
from projects.uiagent.jie_parking.rpa.AndroidXmlParser import TextElementLocator


# def select_car_normal_order_exist_or_not_router(
#     image: str, xml: str | None
# ) -> ClsResult:
#     assert xml is not None
#     if "查看费用明细" in xml or "查看订单明细" in xml: # todo 实际没有查看订单明细，只有费用明细
#         return ClsResult(
#             category=ParkingSteps.CONFIRM_FEE,
#             reason="页面有查看订单明细按钮",
#         )
#     elif "查看金额" in xml:
#         return ClsResult(
#             category=ParkingSteps.BIG_FEE_CHECK,
#             reason="页面有大额缴费的点击查看金额后的弹窗里有去缴费按钮。",
#         )
#     elif '"月卡"' in xml: #月卡要比首页更精确， 月卡出现后，说明页面加载完全了 首页不够
#         return ClsResult(category=ParkingSteps.SELECT_CAR, reason="页面为其他首页。")
#     else:
#         return ClsResult(
#             category="unknown", reason="页面没有首页或查看订单明细。无法判断。"
#         )


class JieParkingState(WorkflowState):
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


class JieParkingSelectCarButtons(StrEnum):
    """捷停车页面可点击按钮枚举"""

    SWITCH_CAR = "切换车辆"  # 左上角的车牌号
    QUICK_PLATE = "快捷车牌号"  # 左上角弹出小窗且里面有多个车牌号时
    OTHER_CARS = "其他车辆"  # 左上角弹出小窗且里面有多个车牌号时，点击其他车辆
    LOCATION_AUTHORIZATION = "授权定位"  # 弹出定位授权窗口时，点击授权定位按钮
    REFRESH_ORDER = "刷新订单"
    VIEW_AMOUNT = "查看金额"
    RENEW_FEE = "去续费"
    VIEW_FEE_DETAILS = (
        "查看费用明细"  # 根据页面情况变化，位于画面上方中间最大的蓝色按钮
    )
    INPUT_PLATE_PAY = "输车牌缴费"  # 有时在中偏上方出现
    PAY_FEE = "去缴费"
    AMOUNT_EXCEPTION = "金额异常"


class JieParkingConfirmPayButtons(StrEnum):
    """确认费用页面可点击按钮枚举"""

    CONFIRM_FEE = "确认订单"
    CANCEL_AD = "取消购买"
    CORRECT_AND_CONTINUE_PAYING = "正确，继续缴费"
    GO_TO_PAY = "去支付"

class JieParkingInputPlateButtons(StrEnum):
    """输入车牌页面可点击按钮枚举"""

    CHECK_PAYMENT = "查询缴费"
    FAST_NUMBER_INPUT = "快捷车牌"
    OTHERS = "包括键盘按钮，空格子，完成按钮在内的其他按钮"

logger = logging.getLogger(__name__)


# 创建FileHandler（文件处理器）
file_handler = logging.FileHandler(
    "projects/uiagent/jie_parking/uiagent.log", mode="a", encoding="utf-8"
)


# 将处理器添加到Logger
logger.addHandler(file_handler)
logger.info("uiagent log file created")


def extract_click_button_name(content: str) -> str:
    """
    非常蠢非常临时但非常靠谱的措施（几百次试验中没有出一次错），content（现在暂时来自thought）里会有《》包裹起来的按钮名称信息，需要提取出来
    """
    pattern = r"《(.*?)》"
    match = re.search(pattern, content)
    # 检查是否有形如 其他车辆(xxxx)，用正则去掉“(xxxx)”的部分
    # 去掉按钮名里“其他车辆(xxx)”这种括号及内部文字，只保留“其他车辆”
    if not match:
        # TODO 先用vlm action parse error统一
        raise SystemError(f"button name not found in thought: {content}")  # type: ignore
    cleaned_button_name = re.sub(r"[(（][^）)]*[)）]", "", match.group(1)).strip()
    if cleaned_button_name not in JieParkingSelectCarButtons.__members__.values():
        # raise SystemError(
        #     f"extract button name failed.select car click action button name {cleaned_button_name} not in {JieParkingSelectCarButtons.__members__.values()}"
        # )  # 点击如验证码时，不应该再抛错了
        logger.warning(
            f"extract button name failed.select car click action button name {cleaned_button_name} not in {JieParkingSelectCarButtons.__members__.values()}"
        )
    elif cleaned_button_name not in JieParkingInputPlateButtons.__members__.values():
        logger.warning(
            f"extract button name failed.input plate click action button name {cleaned_button_name} not in {JieParkingInputPlateButtons.__members__.values()}"
        )
    return cleaned_button_name


# 可复用的专门鞭策大模型在thought里按格式输出按钮名称的指令
thought_instruction_for_button_name_generating = f"""在输出Thought时，你必须要严格遵循并执行以下规则！否则干死你！
                        - 如果你的下一步动作决定了是一个点击动作，那么，一定！必须！要在Thought里一定要提及你要点击的按钮名称！并且一定要用书名号《》包裹起来你要点击的按钮名称！\
                    但按钮名称只能从{JieParkingSelectCarButtons.__members__.values()}选择一个！不可包括其他任何字符！这些按钮的位置和简述在之前可点击的按钮有：后面提到过。\
                    （如《快捷车牌号》）。
                         - 接上条，再三切记！一定要用书名号《》括住你点击动作的按钮名称！一定要从{JieParkingSelectCarButtons.__members__.values()}选择一个！\
                        不可包括其他任何字符！不要自己凭空创造按钮名称！"""

thought_instruction_for_button_name_generating_input_plate = f"""在输出Thought时，你必须要严格遵循并执行以下规则！否则干死你！
                        - 如果你的下一步动作决定了是一个点击动作，那么，一定！必须！要在Thought里一定要提及你要点击的按钮名称！并且一定要用书名号《》包裹起来你要点击的按钮名称！\
                    但按钮名称只能从{JieParkingInputPlateButtons.__members__.values()}选择一个！不可包括其他任何字符！这些按钮的位置和简述在之前可点击的按钮有：后面提到过。\
                    （如《快捷车牌号》）。
                         - 接上条，再三切记！一定要用书名号《》括住你点击动作的按钮名称！一定要从{JieParkingInputPlateButtons.__members__.values()}选择一个！\
                        不可包括其他任何字符！不要自己凭空创造按钮名称！
"""

tend_to_click_switch_car_button = f"""
    如果用户表达了要换个车牌并且给你了一个车牌信息，那么点击{JieParkingSelectCarButtons.SWITCH_CAR.value}按钮（左上角的车牌号是个可以点击的按钮，如果你要点击这个按钮，这个按钮叫做{JieParkingSelectCarButtons.SWITCH_CAR.value}）按钮。
"""
jie_parking_intent_categories = [
        ("Relevant", "任何与停车缴费可能相关的意图，包括但不限于说个车牌号，支付与否，正确与否等等。"),
        ("Abort", '用户希望退出，终止，取消当前工作的意图。'),
        ("Irrelevant", "其他任何与停车缴费无关的意图统统属于这个。"),
    ]



class JieParkingWorkflow(WorkflowBase[JieParkingState]):
    # enable_reflect除了eval脚本，其他时候不要动
    def __init__(
        self,
        start_step=ParkingSteps.SELECT_CAR,
        intent_categories = jie_parking_intent_categories,
        enable_reflect: bool = False,
        debug_mode=False,
    ) -> None:

        plate_input_page = Page(  # 1
                name="车牌输入页面",
                description=f"""在下方可能会看到一个输入键盘，键盘上都是省份名称简写或数字和大写字母。此外可点击的按钮还有：上面的空格子（用于选中你想输入的车牌号部分），完成按钮,{JieParkingInputPlateButtons.CHECK_PAYMENT.value}（查询缴费按钮），{JieParkingInputPlateButtons.FAST_NUMBER_INPUT.value}（不一定出现，有时以多个带 x标记的车牌号形式出现在{JieParkingInputPlateButtons.CHECK_PAYMENT.value}上方，需要点击这个的话，这个按钮的名称统一叫做{JieParkingInputPlateButtons.FAST_NUMBER_INPUT.value}，并且你要点击车牌号部分，千万不要点到x）。""",
            )
        simple_plate_input_page = Page(  # 1
                name="简单车牌输入页面描述",
                description=f"""这就是一个捷停车App的输入车牌查询对应的车牌订单的页面。""",
            )

        self.pages: Final[list[Page]] = [
            Page(  # 0
                name="捷停车首页",
                description=f"""
    捷停车首页，特征是左下角首页处于蓝色选中状态，包括左上角弹出选择车辆车牌小窗的页面的状态，以及缴费信息确认弹窗的页面，但是不包括输入车牌页面！\
    可点击的按钮有：{JieParkingSelectCarButtons.SWITCH_CAR.value}（左上角的车牌号是个可以点击的按钮，如果你要点击这个按钮，这个按钮叫做{JieParkingSelectCarButtons.SWITCH_CAR.value}），{JieParkingSelectCarButtons.QUICK_PLATE.value}（左上角有弹出小窗且里面有多个车牌号时），\
    {JieParkingSelectCarButtons.OTHER_CARS.value}(左上角有弹出小窗时),{JieParkingSelectCarButtons.REFRESH_ORDER.value}（当当前车牌号不存在订单时出现），{JieParkingSelectCarButtons.VIEW_AMOUNT.value}（当金额过大时出现）\
    {JieParkingSelectCarButtons.RENEW_FEE.value}（月卡用户），{JieParkingSelectCarButtons.VIEW_FEE_DETAILS.value}（有普通小额停车订单时出现）。\
    根据页面情况有所变化，但刷新订单，查看金额，去续费按钮均有时会出现于画面上方中间最大的那个蓝色按钮），\
    {JieParkingSelectCarButtons.INPUT_PLATE_PAY.value}（有时也在中偏上方出现）\
    {JieParkingSelectCarButtons.LOCATION_AUTHORIZATION.value}（弹出定位授权窗口时，点击授权定位按钮）\
    {JieParkingSelectCarButtons.PAY_FEE.value}（如果你看到中间有个缴费信息确认弹窗时才有这个按钮）\
    除了上面的按钮外，你可能会遇到验证码弹窗，里面的图片是你需要点击的。以及其他的一些为了完成任务所必须点击的按钮。
    """,
            ),
            plate_input_page,
            plate_input_page,
            Page(  # 3
                name="有订单页面",
                description=f"""可以在上方看到车牌信息，停车时长和订单金额。
                可点击的按钮名称如下：
                    - {JieParkingSelectCarButtons.VIEW_FEE_DETAILS.value}（查看订单费用明细按钮）；
                    - {JieParkingSelectCarButtons.SWITCH_CAR.value}（左上角的车牌号是个可以点击的按钮，如果你要点击这个按钮，这个按钮叫做{JieParkingSelectCarButtons.SWITCH_CAR.value}）；
                    - {JieParkingSelectCarButtons.PAY_FEE.value}（如果你看到中间有个缴费信息确认弹窗时才有这个按钮）；
                有时会弹出订单信息确认窗口，那么需要让用户确认订单金额后再点击正确无误继续缴费，否则取消缴费并点击左上角返回按钮返回选择车牌页面。""",
            ),
            Page(  # 4
                name="缴费信息确认页面",
                description="""可以看到缴费信息确认的提示。需要根据用户反馈，点击'去缴费'或'金额异常'""",
            ),
            Page(  # 5
                name="订单详情页面",
                description=f"""可以看到停车场信息，车牌信息和入场时间信息。
                可点击的按钮名称如下：{JieParkingConfirmPayButtons.CONFIRM_FEE.value}（订单没问题的话点击后进入后一步支付），{JieParkingConfirmPayButtons.CORRECT_AND_CONTINUE_PAYING.value}（只在中间存在温馨提示弹窗时出现）。
                有时会弹出订单信息确认窗口，那么需要让用户确认订单金额后再点击正确无误继续缴费，否则取消缴费并点击左上角返回按钮返回选择车牌页面。""",
            ),
            Page(  # 6
                name="缴费页面",
                description="如果你看到下面有个去支付按钮，那么点击去支付按钮即可，如果你看到画面正中央中出现一个付款二维码，\
                那么你在下一步就进行finished动作并且在其content内告诉用户直接扫码支付即可。",
            ),
            Page(  # 7
                name="大额金额页面",
                description=f"""可以看到中上方有金额过大，缴费前请确认几个字。
                可点击的按钮名称如下：
                    - {JieParkingSelectCarButtons.VIEW_AMOUNT.value}（查看金额按钮）；
                    - {JieParkingSelectCarButtons.SWITCH_CAR.value}（左上角的车牌号是个可以点击的按钮，如果你要点击这个按钮，这个按钮叫做{JieParkingSelectCarButtons.SWITCH_CAR.value}）；
                """,
            ),
            Page(  # 8
                name="大额金额确认费用弹窗页面",
                description=f"""可以看到中上方有缴费信息确认几个字。
                可点击的按钮名称如下：
                    - {JieParkingSelectCarButtons.PAY_FEE.value}（去缴费按钮）；
                """,
            ),
            Page(  # 9
                name="确定订单下的广告页面，可能不出现",
                description="""可以看到提示购买优惠等促销活动的广告弹窗""",
            ),
        ]

        car_plate_info_task = InfoTask(
            brief="询问给哪辆车缴费",
            info_type=PlateNumber,
            validator=PlateNumber.validator,
            exec_mode=InfoExecMode.NL_ANY,
        )

        user_meaning = InfoTask(
            brief="""根据最新的用户对话记录，提取和总结用户最新的表达意思的小结。""",
            info_type=UserMeaning,
            validator=UserMeaning.validator,
            exec_mode=InfoExecMode.NL_ANY,
        )
        
        plate_input_note = [
                    "你现在是特别擅长输入信息的打字员。把你的注意力专注于下面车牌号输入的部分，不要关注其他无关部分。然后严格按照以下指示行事，否则干死你。",
                    "   - 首先如果你看到当前视野上方已经填好了你想输入的车牌号，那么此时查询缴费按钮应该会变成深一些的蓝色，那么此时你需要点击查询缴费按钮。但如果你发现你需要点击它但是找不到它了，那么很可能是下方键盘遮住了它，那么你先点击完成按钮；",
                    "   - 看一下你想输入的车牌号的省份是否输入了，如果没有的话，尝试输入之。",
                    "   - 继续比对你想输入的车牌号与当前页面上的待填内容，缺哪些你就顺次填写即可；",
                    "   - 遵循一个技巧，你在下方会看到一个输入键盘，你直接点击哪个字母数字，那个字母数字就会直接填入上方从左往右第一个空白格子里；",
                    f"   - 此外当上方你想输入的车牌号还没输入完成时，你还可以看一下是否在{JieParkingInputPlateButtons.CHECK_PAYMENT.value}（查询缴费按钮）上方有{JieParkingInputPlateButtons.FAST_NUMBER_INPUT.value}出现。如果出现了{JieParkingInputPlateButtons.FAST_NUMBER_INPUT.value}且有和你想输入的车牌号一致的,且当前视野内上方待输入车牌部分还没有输入完成你想输入的车牌号时，那么直接点击它。而如果你想输入的车牌号已经输入好了，那直接点击{JieParkingInputPlateButtons.CHECK_PAYMENT.value}（查询缴费按钮）。",
                    "   - 任何时候如果你想输入车牌号的字符但下面没有看到输入键盘，那么你就先尝试点击上面你要输入的空的格子。",
                    "最后，你一定要遵循以下规则，否则干死你！：",
                    "   - 每一次只进行一个Action动作，绝对不可以多个。",
                    "   - 再三确认你接下来要点击的按钮的位置，不要点错了！",
                    f"   - “当且仅当”你想输入的车牌号被“正确”地在“视野上方的格子里“完整”地输入进去后，才尝试去点{JieParkingInputPlateButtons.CHECK_PAYMENT.value}（查询缴费按钮）！！！除此之外不要去尝试点击{JieParkingInputPlateButtons.CHECK_PAYMENT.value}（查询缴费按钮）！！！",
                    "   - "+thought_instruction_for_button_name_generating_input_plate
                ]

        plate_input_new_note = [
                    "你现在变身成为一个特别擅长用手机干各种事情的手机沉迷者。现在你需要严格按照以下指示行事，否则干死你。",
                    "   - 记住你最初的目的，好好结合看到的画面，仔细分析接下来该点击什么，最后达成目的即可。"
                    "   - 每一次只进行一个Action动作，绝对不可以多个。",
                    "   - "+thought_instruction_for_button_name_generating_input_plate
        ]

        plate_input_ui_task = UITask(
                page=self.pages[1],
                info_task=car_plate_info_task,
                task_template="用点击动作输入后面这个你想输入的车牌号: {info}",
                action_set=[EUIAction.CLICK],
                note=plate_input_note,
            )

        select_car_note = [
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
                    f"   - 如果是当前用户希望缴费的车辆不存在订单的情况，那么尝试点击{JieParkingSelectCarButtons.REFRESH_ORDER.value}按钮。",
                    f"   - 如果你看到弹出了授权定位弹窗，此时你集中注意力在这个弹窗之中并忽略其他部分，然后用askhuman告诉用户：{JieParkingReplyContents.ASK_LOCATION_PERMITION.value}；",
                    f"   - 如果你看到当前页面上显示“金额过大，缴费前请确认”，且用户当前最新表达的意思里并没有明确表达用户是否希望查看金额或费用明细或去缴费，那么你需要用ask_human来向用户回复：{JieParkingReplyContents.ASK_CHECK_BIG_FEE_OR_NOT.value}。如果用户当前最新表达的意思里明确表示他希望查看金额或费用明细或去缴费，那么你需要点击{JieParkingSelectCarButtons.VIEW_AMOUNT.value}按钮，而如果用户当前最新表达的意思里明确表示他并不想查看金额或费用明细或去缴费，那么那么直接用finished动作结束任务并在其content里告诉用户：{JieParkingReplyContents.FINISHED_USER_ABORT.value}",
                    f"   - 如果你看到当前页面上显示“查看费用明细”，且用户当前最新表达的意思里并没有明确表达用户是否希望查看金额或费用明细或去缴费，那么你需要用ask_human来向用户回复：当前订单车牌号为xxx（当前用户正在希望进行缴费的车辆车牌），停车时长为xxx（具体取决于你看到的弹窗里的停车时长），金额为多少多少元（具体取决于你看到的数额），{JieParkingReplyContents.ASK_CONFIRM_FEE.value}。如果用户当前最新表达的意思里明确表示了他希望查看金额或费用明细或去缴费，那么你需要点击{JieParkingSelectCarButtons.VIEW_FEE_DETAILS.value}按钮，而如果用户当前最新表达的意思里明确表示了当前金额是不对的错误的，那么那么直接用finished动作结束任务并在其content里告诉用户：{JieParkingReplyContents.FINISHED_USER_ABORT.value}",
                    f"   - 如果你看到当前页面上显示“缴费信息确认”的弹窗，那么这里已经是大额金额确认环节了，此时你集中注意力在这个弹窗之中并忽略其他部分。如果用户当前最新表达的意思里并没有明确表达用户是否确认大额费用是否正确，那么你需要用ask_human来向用户回复：当前大额订单车牌号为xxx（当前用户正在希望进行缴费的车辆车牌），停车时长为xxx（具体取决于你看到的弹窗里的停车时长），金额为多少多少元（具体取决于你看到的数额），{JieParkingReplyContents.ASK_CONFIRM_FEE.value}。如果用户当前最新表达的意思里明确表示了大额费用是正确的，那么你需要点击{JieParkingSelectCarButtons.PAY_FEE.value}按钮，而如果用户当前最新表达的意思里明确表示了大额费用是不对的错误的，那么那么直接用finished动作结束任务并在其content里告诉用户：{JieParkingReplyContents.FINISHED_USER_ABORT.value}",
                    f"   - 如果你看到当前页面上显示“无需缴费”，那么直接用finished动作结束任务并在其content里告诉用户：当前订单车牌号为xxx（当前用户正在希望进行缴费的车辆车牌），{JieParkingReplyContents.FINISHED_NO_NEED_TO_PAY.value}。",
                    f"   - 如果你看到当前页面上显示“请前往人工收费缴费”，那么直接用finished动作结束任务并在其content里告诉用户：当前订单车牌号为xxx（当前用户正在希望进行缴费的车辆车牌），{JieParkingReplyContents.FINISHED_MANUALY_REPLY.value}。",
                    f"   - 如果你看到当前页面上显示“月卡用户”，那么直接用finished动作结束任务并在其content里告诉用户：当前订单车牌号为xxx（当前用户正在希望进行缴费的车辆车牌），{JieParkingReplyContents.FINISHED_MONTHLY_PASS.value}。",
                    f"   - 如果你看到当前页面上显示“补缴欠费”弹窗，此时你集中注意力在这个弹窗之中并忽略其他部分。那么直接用finished动作结束任务并在其content里告诉用户：当前订单车牌号为xxx（当前用户正在希望进行缴费的车辆车牌），{JieParkingReplyContents.FINISHED_DEBT_PAY.value}。",
                    "   -如果你看到任何图片验证弹窗，那么发挥你最大的想象力，正确地理解该弹窗里给你的任务并执行正确的操作，目的是成功通过验证。",
                    "   - 任何时候用户在最新表达的意思里明确表示他希望退出，那么直接用finished动作结束任务并在其content里告诉用户：好的，退出当前任务。",
                    "   - 绝对不要自己编造任何动作空间不存在的动作，以及不存在的动作参数，参数一定要按照动作空间规定的填写，不要乱填。",
                    "   - 每一次只进行一个Action动作，绝对不可以多个。",
                    thought_instruction_for_button_name_generating,
                    "   - 好好遵循上面的指引，否则干死你。"
                ]

        simple_select_car_note = [
            "有问题及时向用户确认。",
            "每一次只进行一个Action动作，绝对不可以多个。",
            "仔细阅读和理解动作空间那边的说明，不要乱填。比如click的point那边的x1 y1必须都是坐标！",
            "好好遵循上面的这些指引，否则干死你。",
            thought_instruction_for_button_name_generating
        ]

        ui_tasks: dict[StepType, UITask] = {
            ParkingSteps.SELECT_CAR: UITask(
                page=self.pages[0],
                # 注意，在选择车辆阶段就会有很多情况可以直接结束任务，因此要有FINISHED动作。详情请查看note。
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.FINISHED],
                info_task=user_meaning,
                task_template="你是个非常强大的非常聪明的智能助手，非常擅长使用动作操作来解决问题。请根据下述用户当前最新表达的意思（特别是当前用户正在希望进行缴费的车辆车牌，一切待缴费对象以这个车牌为准，如果这个缺失要向用户询问而不要擅自从图像中理解和提取。），来进行接下来的操作: {info}。",
                note=select_car_note,
            ),
            # 现阶段调用RPA快速输入。但是可以考虑先保留下面这个task（实际上并不调用），因为之前的实验中以下task描述非常work；可以用于其他项目的参考；
            ParkingSteps.INPUT_PLATE_PROVINCE: plate_input_ui_task,
            ParkingSteps.INPUT_PLATE_LETTER_NUM: plate_input_ui_task,
            ParkingSteps.CONFIRM_PAY: UITask(
                page=self.pages[6],
                # 确认订单详情，可能要反问用户确认金额，或者直接点击确认缴费按钮。
                info_task=InfoTask(
                    brief="询问用户是否继续支付或是否确认订单。",
                    info_type=PayOrNot,
                    validator=PayOrNot.validator,
                    exec_mode=InfoExecMode.NEED_UI_IMAGE,
                ),
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.FINISHED],
                task_template="用户回答的是否确认支付的信息如下：{info}。如果用户表示确认支付，那么点击确认订单按钮。",
                note=[
                    "如果你看到弹窗说你当前位置距离太远，需要确认订单是否有误时，你直接点击《正确，继续缴费》按钮即可；",
                    "如果你看到任何其他和支付无关的弹窗，统统点击关闭或拒绝等按钮以便继续进行支付任务。",
                    thought_instruction_for_button_name_generating,
                ],
            ),
            ParkingSteps.PAYMENT: UITask(
                page=self.pages[7],
                # 缴费页面，见到二维码形式的话就finished
                action_set=[
                    EUIAction.CLICK,
                    EUIAction.FINISHED,
                ],  # TODO 询问用户是二维码支付还是发送到手机进行支付 构造info_task
                task="缴费，如果看到下面有去支付按钮，那么点击去支付，如果是二维码，那么用finished结束任务并在其content内告知用户扫码付款。",
                note=[
                    "如果你看到点击微信支付的勾选框（如果勾选着了就不用点了），那么直接点击下方的去支付按钮。",
                    "如果你看到中间一个弹窗里的下方有二维码支付几个字，那么点击二维码支付。",
                    "如果你看到了二维码，那么用finished结束任务并在其content内告知用户扫码付款。",
                    "如果你看到任何其他和支付无关的弹窗，统统点击关闭或拒绝等按钮以便继续进行支付任务。",
                ],
            ),
            ParkingSteps.END: UITask(
                page=self.pages[6],
                task="任务结束，什么都不用做。",
                action_set=[EUIAction.FINISHED],
            ),
        }

        ui_task_handlers: dict[StepType, UIHandler] = {
            ParkingSteps.SELECT_CAR: self._select_car,
            ParkingSteps.INPUT_PLATE_PROVINCE: self._input_plate_num,
            ParkingSteps.INPUT_PLATE_LETTER_NUM: self._input_plate_num,
            ParkingSteps.CONFIRM_PAY: self._confirm_pay,
            ParkingSteps.PAYMENT: self._payment,
            ParkingSteps.END: self._end,
        }

        rpa_handlers: dict[StepType, RPAHandler] = {
            ParkingSteps.SELECT_CAR: self._rpa_select_car,
            ParkingSteps.INPUT_PLATE_PROVINCE: rpa.rpa_input_province_plate,
            ParkingSteps.INPUT_PLATE_LETTER_NUM: rpa.rpa_input_letter_num_plate,
            ParkingSteps.CONFIRM_PAY: rpa.rpa_confirm_pay,
            ParkingSteps.PAYMENT: rpa.rpa_payment,
        }
        ui_routers: dict[StepType, UIRouter] = {
            ParkingSteps.SELECT_CAR: UIRouter(
                categories=[
                    (ParkingSteps.SELECT_CAR, self.pages[0]),
                ],
                router=rpa.val_select_car,
            ),
            ParkingSteps.INPUT_PLATE_PROVINCE: UIRouter(
                categories=[
                    (ParkingSteps.INPUT_PLATE_PROVINCE, self.pages[1]),
                ],
                router=rpa.val_input_province_plate,
            ),
            ParkingSteps.INPUT_PLATE_LETTER_NUM: UIRouter(
                categories=[
                    (ParkingSteps.INPUT_PLATE_LETTER_NUM, self.pages[2]),
                ],
                router=rpa.val_input_letter_num_plate,
            ),
            ParkingSteps.CONFIRM_PAY: UIRouter(
                categories=[
                    (ParkingSteps.CONFIRM_PAY, self.pages[6]),
                ],
                router=rpa.val_confirm_pay,
            ),
            ParkingSteps.PAYMENT: UIRouter(
                categories=[
                    (ParkingSteps.PAYMENT, self.pages[7]),
                ],
                router=rpa.val_payment,
            ),
        }
        super().__init__(
            "你正在与用户进行沟通并尝试协助用户使用捷停车替他对车辆进行停车缴费。",
            start_step,
            ui_tasks,
            ui_task_handlers,
            intent_categories=intent_categories,
            rpa_handlers=rpa_handlers,
            ui_routers=ui_routers,
            state_cls=JieParkingState,
            enable_reflect=enable_reflect,
            debug_mode=debug_mode,
        )

    async def _end(self, base64_image: str, image_format: str) -> UITaskResult:
        self.state.status = WorkflowStatus.SUCCESS
        action = FinishedAction(content=JieParkingReplyContents.FINISH_SCAN)
        return UITaskResult(raw_prompt="",thought="",action_content="",actions=[action])

    async def _select_car(self, base64_image: str, image_format: str) -> UITaskResult:
        assert self.state.current_step == ParkingSteps.SELECT_CAR, ("current step must be SELECT_CAR")  # type: ignore
        task = self.ui_tasks[self.state.current_step]
        assert task.info_task is not None, "task.info_task must be not None"
        result = await self._run_ui_step_by_model(base64_image, image_format)
        logger.debug("select car result: %s", nl_repr(result))
        # 取出第0个Action，这样优雅很多
        assert len(result.actions) == 1, ("select car must and only have exactly one action")  # type: ignore
        the_action = result.actions[0]
        # TODO: 需要做结果和错误检查
        # TODO assert这里一定是action
        assert isinstance(the_action, Action), ("select car must and only have exactly one action")  # type: ignore
        if isinstance(the_action, AskAction):
            # TODO: 这里需要走通用的意图识别，而不是判断是否AskAction
            self.state.set_step(ParkingSteps.SELECT_CAR, UIStepStatus.WAIT_FOR_INFO)
            return result
        # 如果是点击动作，通过判断点击了什么决定接下来进入哪个步骤
        elif isinstance(the_action, ClickAction):
            button_name = extract_click_button_name(result.thought)
            # 更新最新的动作信息，只有click才有
            match button_name:
                # 如果result点击了快捷车牌号，切换车辆，查看金额，刷新订单按钮下一步继续SELECT_CAR
                case (JieParkingSelectCarButtons.SWITCH_CAR.value
                    | JieParkingSelectCarButtons.QUICK_PLATE.value
                    | JieParkingSelectCarButtons.VIEW_AMOUNT.value):
                    self.state.set_step(ParkingSteps.SELECT_CAR)
                    return result
                # 重要，如果模型想点击刷新订单
                case JieParkingSelectCarButtons.REFRESH_ORDER.value:
                    # 那么先看一下之前的动作是否是点击了刷新订单按钮
                    # TODO 尝试直接搞一个是否点了刷新订单按钮flag进state先。
                    if self.state.clicked_refresh_order:
                        self.state.set_step(ParkingSteps.SELECT_CAR, UIStepStatus.WAIT_FOR_INFO)
                        self.state.clicked_refresh_order = False
                        return UITaskResult(raw_prompt="",thought="",action_content="",actions=[AskAction(content=JieParkingReplyContents.ASK_NO_ORDER.value)],)
                    else:
                        self.state.set_step(ParkingSteps.SELECT_CAR)
                        self.state.clicked_refresh_order = True
                        return result
                # 如果result点击了左上角悬浮弹窗里的其他车辆或者输入车牌缴费，那么下一步是INPUT_PLATE
                case (JieParkingSelectCarButtons.OTHER_CARS.value
                    | JieParkingSelectCarButtons.INPUT_PLATE_PAY.value):
                    self.state.set_step(ParkingSteps.INPUT_PLATE_PROVINCE)
                    return result
                case (JieParkingSelectCarButtons.VIEW_FEE_DETAILS.value | JieParkingSelectCarButtons.PAY_FEE.value):
                    self.state.set_step(ParkingSteps.CONFIRM_PAY)
                    return result
                case _:
                    # 如果返回到router，也要先把现在的状态设为等图，因为router回来会重新喂图
                    self.state.set_step(ParkingSteps.SELECT_CAR)
                    return result
        # select car时有很多结束出口，包括月卡，找人工，无需缴费，补缴欠费
        elif isinstance(the_action, FinishedAction):
            self.state.status = WorkflowStatus.SUCCESS
            return result
        else:
            raise SystemError("select car must have exactly one action")  # type: ignore

    # async def _input_province(self, base64_image: str, image_format: str) -> UITaskResult:
    #     assert self.state.current_step == ParkingSteps.INPUT_PLATE_PROVINCE, ("current step must be INPUT_PLATE_PROVINCE")  # type: ignore
    #     task = self.ui_tasks[self.state.current_step]
    #     assert task.info_task is not None, "task.info_task must be not None"
    #     result = await self._run_ui_step_by_model(base64_image, image_format)
    #     logger.debug("input province result: %s", nl_repr(result))
    #     # 取出第0个Action，这样优雅很多
    #     assert len(result.actions) == 1, ("input province must and only have exactly one action")  # type: ignore
    #     # assert这里一定是Click action
    #     assert isinstance(result.actions[0], ClickAction), ("input province must and only have exactly one action")  # type: ignore
    #     button_name = extract_click_button_name(result.thought)
    #     if button_name == JieParkingInputPlateButtons.CHECK_PAYMENT.value:
    #         self.state.set_step(ParkingSteps.SELECT_CAR)
    #         return result
    #     else:
    #         self.state.set_step(ParkingSteps.INPUT_PLATE_LETTER_NUM)
    #         return result

    async def _input_plate_num(self, base64_image: str, image_format: str) -> UITaskResult:
        task = self.ui_tasks[self.state.current_step]
        assert task.info_task is not None, "task.info_task must be not None"
        result = await self._run_ui_step_by_model(base64_image, image_format)
        logger.debug("input letter num result: %s", nl_repr(result))
        # 取出第0个Action，这样优雅很多
        assert len(result.actions) == 1, ("input letter num must and only have exactly one action")  # type: ignore
        button_name = extract_click_button_name(result.thought)
        match button_name:
            case JieParkingInputPlateButtons.CHECK_PAYMENT.value:
                self.state.set_step(ParkingSteps.SELECT_CAR)
                return result
            case _:
                self.state.set_step(ParkingSteps.INPUT_PLATE_PROVINCE)
                return result
        

    def _rpa_select_car(self, info: UserMeaning | str | None, xml: str) -> tuple[list[Action], StepType, UIStepStatus | None]:
        if '普通车牌' in xml:
            # todo 错误传了键盘输入页面
            pass
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
            return [action], current_step, UIStepStatus.WAIT_FOR_INFO

        xml_parser = TextElementLocator(xml)
        # 新增车牌第一位
        if "添加车辆缴费免排队、免找零" in xml and "请输入车牌授权定位，提高查费准确性" not in xml:
            # 页面判断
            # 页面1： 输车牌缴费 3005
            ele = xml_parser.get_first_element_by_text("添加车辆缴费免排队、免找零")
            # 状态仍然是选择车牌 TODO 坐标硬编码 mark
            # TODO硬编码
            action = ClickAction(
                x=ele["center"][0], y=ele["center"][1] + 75  #TODO硬编码
            )  # 该元素下方才是点击添加车牌
            current_step = ParkingSteps.INPUT_PLATE_PROVINCE

            return [action], current_step, None
        # 从后往前判断
        # 去缴费页面
        if "去缴费" in xml:
            # 判断用户是否确认缴费
            fee_check_or_not: KnowingStatus = info.fee_correct_or_not
            if fee_check_or_not == KnowingStatus.NO:
                self.state.status = WorkflowStatus.USER_ABORT
                action = FinishedAction(content=JieParkingReplyContents.FINISHED_CONFIRM_FEE_NOT_CORRECT)
                return [action], ParkingSteps.END, None
            elif fee_check_or_not == KnowingStatus.YES:
                ele = xml_parser.get_first_element_by_text("去缴费")
                action = ClickAction(x=ele["center"][0], y=ele["center"][1])
                return [action], ParkingSteps.CONFIRM_PAY, None
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
                return [action], ParkingSteps.SELECT_CAR, UIStepStatus.WAIT_FOR_INFO
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
                action = ClickAction(x=ele["center"][0], y=ele["center"][1])
                # 状态仍然是选择车牌
                return [action], current_step, None
            elif visible_plate_number != user_wanted_plate_num and user_wanted_plate_num:
                assert visible_plate_number in xml
                ele = xml_parser.get_first_element_by_text(visible_plate_number)
                current_step = ParkingSteps.SELECT_CAR
                action = ClickAction(x=ele["center"][0], y=ele["center"][1])
                # 状态仍然是选择车牌
                return [action], current_step, None
            else:  # visible_plate_number == user_wanted_plate_num or not user_wanted_plate_num
                if "未查询到停车信息" in xml:  # 刷新订单
                    if self.state.clicked_refresh_order:
                        self.state.set_step(ParkingSteps.SELECT_CAR, UIStepStatus.WAIT_FOR_INFO)
                        self.state.clicked_refresh_order = False
                        action = AskAction(content=JieParkingReplyContents.ASK_NO_ORDER.value)
                        current_step = ParkingSteps.SELECT_CAR
                        return [action], current_step, UIStepStatus.WAIT_FOR_INFO
                    else:
                        ele = xml_parser.get_first_element_by_text("刷新订单")
                        action = ClickAction(x=ele["center"][0], y=ele["center"][1])
                        self.state.clicked_refresh_order = True
                        return [action], ParkingSteps.SELECT_CAR, None
                elif "月卡用户" in xml or "月卡剩余" in xml:
                    current_step = ParkingSteps.SELECT_CAR  # TODO END STEP
                    action = AskAction(content=JieParkingReplyContents.FINISHED_MONTHLY_PASS)
                    return [action], current_step, UIStepStatus.WAIT_FOR_INFO
                elif "人工收费" in xml:
                    current_step = ParkingSteps.SELECT_CAR
                    action = AskAction(content=JieParkingReplyContents.FINISHED_MANUALY_REPLY)
                    return [action], current_step, UIStepStatus.WAIT_FOR_INFO
                elif "无需缴费" in xml:
                    current_step = ParkingSteps.SELECT_CAR
                    action = AskAction(content=JieParkingReplyContents.FINISHED_NO_NEED_TO_PAY)
                    return [action], current_step, UIStepStatus.WAIT_FOR_INFO
                # TODO 路由补缴欠费页面
                elif "补缴欠费" in xml:
                    # TODO 欠费提醒是否需要用户确认
                    action = AskAction(content=JieParkingReplyContents.FINISHED_DEBT_PAY)
                    current_step = ParkingSteps.SELECT_CAR
                    return [action], current_step, UIStepStatus.WAIT_FOR_INFO
                elif "金额过大，缴费前请确认" in xml:
                    big_fee_check_or_not: CheckKnowingStatus = info.fee_check_or_not
                    if big_fee_check_or_not == CheckKnowingStatus.NO:
                        self.state.status = WorkflowStatus.USER_ABORT
                        action = FinishedAction(content=JieParkingReplyContents.FINISHED_USER_ABORT)
                        return [action], ParkingSteps.END, None
                    elif big_fee_check_or_not == CheckKnowingStatus.YES:
                        ele = xml_parser.get_first_element_by_text("查看金额")
                        action = ClickAction(x=ele["center"][0], y=ele["center"][1])
                        return [action], ParkingSteps.SELECT_CAR, None
                    else:
                        park_time_pattern = re.compile(r'text="已停[：:](?P<park_time>[^"]*)"')
                        park_time_match = park_time_pattern.search(xml)
                        park_time = park_time_match.groupdict()['park_time'] if park_time_match else ''
                        if park_time:
                            prefix = f"当前车牌号{visible_plate_number}，停车{park_time}，"
                        else:
                            prefix = ""
                        action = AskAction(content=prefix + JieParkingReplyContents.ASK_CHECK_BIG_FEE_OR_NOT)
                        return [action], ParkingSteps.SELECT_CAR, UIStepStatus.WAIT_FOR_INFO
                elif "查看费用明细" in xml:
                    fee_check_or_not: CheckKnowingStatus = info.fee_check_or_not
                    if fee_check_or_not == CheckKnowingStatus.NO:
                        self.state.status = WorkflowStatus.USER_ABORT
                        action = FinishedAction(content=JieParkingReplyContents.FINISHED_CONFIRM_FEE_NOT_CORRECT)
                        return [action], ParkingSteps.END, None
                    elif fee_check_or_not == CheckKnowingStatus.YES:
                        ele = xml_parser.get_first_element_by_text("查看费用明细")
                        action = ClickAction(x=ele["center"][0], y=ele["center"][1])
                        return [action], ParkingSteps.CONFIRM_PAY, None
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
                        return [action], ParkingSteps.SELECT_CAR, UIStepStatus.WAIT_FOR_INFO
                else:
                    raise Exception(f"xml无效，无rpa可识别的关键信息")

        else:
            # 此时应处于其他车辆页面，绑定的车牌中可能有目标车牌
            assert "其他车辆" in xml, "其他车辆按钮页面未找到"  # TODO 尝试放到ui validator中
            # 点击目标车牌进行更换，不用再输入车牌
            if user_wanted_plate_num and (ele := xml_parser.get_first_element_by_text(user_wanted_plate_num)):
                current_step = ParkingSteps.SELECT_CAR
                action = ClickAction(x=ele["center"][0], y=ele["center"][1])
                return [action], current_step, None
            # 如果页面显示的多个车牌中，没有目标车牌，需要点击其他车辆进行新增，并输入车牌
            ele = xml_parser.get_first_element_by_text("其他车辆")
            action = ClickAction(x=ele["center"][0], y=ele["center"][1])
            current_step = ParkingSteps.INPUT_PLATE_PROVINCE
            return [action], current_step, None

    async def _confirm_pay(self, base64_image: str, image_format: str) -> UITaskResult:
        # 如果费用确认为空，则还未确认
        assert self.state.current_step == ParkingSteps.CONFIRM_PAY, (
            "current step must be CONFIRM_PAY"
        )
        task = self.ui_tasks[self.state.current_step]
        assert task.info_task is not None, "task.info_task must be not None"
        info: PayOrNot = self.state.middle_info[task.info_task.brief]
        # 其他非NO的情况已经在info task处理
        if info.pay_or_not == ConfirmPayKnowingStatus.NO:
            self.state.status = WorkflowStatus.USER_ABORT
            return UITaskResult(raw_prompt="",thought="",action_content="",actions=[FinishedAction(content=JieParkingReplyContents.FINISHED_USER_ABORT.value)],)
        try:
            result = await self._run_ui_step_by_model(base64_image, image_format)
            logger.debug("select car result: %s", nl_repr(result))
        except Exception as e:
            logger.debug("select car error: %s", nl_repr(e))
            self.state.status = WorkflowStatus.ERROR
            raise e
        the_action = result.actions[0]
        if isinstance(the_action, ClickAction):
            # 按确认订单，进入支付
            self.state.set_step(ParkingSteps.PAYMENT)
            return result
        elif isinstance(the_action, AskAction):
            # 出现意外问题需要询问用户，如距离过远订单是否支付
            self.state.step_status[self.state.current_step] = UIStepStatus.WAIT_FOR_INFO
            return result
        else:
            raise ValueError(f"出现未知动作: {the_action}")

    async def _payment(self, base64_image: str, image_format: str) -> UITaskResult:
        assert self.state.current_step == ParkingSteps.PAYMENT, ("current step must be PAYMENT")

        result = await self._run_ui_step_by_model(base64_image, image_format)
        if result.actions:
            assert len(result.actions) == 1, ("payment step must and only have exactly one action")
            the_action = result.actions[0]
            if isinstance(the_action, FinishedAction):
                self.state.status = WorkflowStatus.SUCCESS
            elif isinstance(the_action, ClickAction):
                self.state.set_step(ParkingSteps.PAYMENT)
            else:
                self.state.status = WorkflowStatus.ERROR
        return result
