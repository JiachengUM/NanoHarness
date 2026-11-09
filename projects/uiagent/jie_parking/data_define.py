import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from nanoai.utils.data_concept import JudgeResult


class ParkingSteps(StrEnum):
    SELECT_CAR = "选择车辆"  # 可以理解成不需要缴费的首页
    INPUT_PLATE_PROVINCE = "输入车牌省份"
    INPUT_PLATE_LETTER_NUM = "输入车牌号码"
    CONFIRM_PAY = "确认支付"
    PAYMENT = "支付"
    END = "结束"


class JieParkingReplyContents(StrEnum):
    """捷停车页面可回复内容枚举"""

    NEED_PLATE_NUMBER = "请告诉我车牌号码信息，我为你停车缴费。"
    ASK_UNKNOWN_INTENT = (
        "不好意思，当前只能处理停车缴费任务。"
    )
    ASK_ILLEGAL_PLATE_NUMBER = "错误车牌，请重新告诉我准确的车牌号码。"
    ASK_CONFIRMING_FEE_UNKNOWN_INTENT = (
        "不好意思，当前只能处理停车缴费，请告诉我金额是否正确？"
    )
    ASK_CONFIRM_FEE = "是否查看费用明细，查看的话请回复查看，我将为您展示订单明细。"
    FINISHED_CONFIRM_FEE_NOT_CORRECT = "用户觉得费用不对，退出程序。"
    ASK_LOCATION_PERMITION = "请问是否同意捷停车地理位置授权？告诉我同意还是不同意。"
    FINISHED_USER_ABORT = "我先退下啦，有事可以再来找我"
    ASK_PAY_OR_NOT = "要我帮你交停车费的话，请说立即支付"
    ASK_PAY_OR_NOT_UNKNOWN_INTENT = (
        "不好意思，当前只能处理停车缴费任务，要我帮你交停车费的话，请说立即支付"
    )
    ASK_NO_ORDER = (
        "没查到停车信息。要换其他车牌缴费吗？想换直接告我车牌号；不需要就说退出。"
    )
    ASK_CHECK_BIG_FEE_OR_NOT = "订单金额过大，是否查看金额？如果不需要了请对我说退出。"
    ASK_CHECK_BIG_FEE_UNKNOWN_INTENT = "不好意思，当前只能处理停车缴费任务，请告我是否查看金额？如果不需要了请对我说退出。"
    ASK_BIG_FEE_DETAIL_OR_NOT = "请确认金额是否正确？正确的话请回复正确或去缴费，我将为您展示订单明细。"
    FINISHED_MONTHLY_PASS = "您是月卡用户，无需缴费，可以直接开出去。如果需要给其他车牌缴费，请告诉我另一个车牌信息，或者说退出。"
    FINISHED_MANUALY_REPLY = "您的车辆无法在线缴费，请前往人工收费缴费。如果需要给其他车牌缴费，请告诉我另一个车牌信息，或者说退出。"
    FINISHED_NO_NEED_TO_PAY = "您的车辆现在在免费时段内，无需缴费，请直接开出去就行。如果需要给其他车牌缴费，请告诉我另一个车牌信息，或者说退出。"
    FINISHED_DEBT_PAY = "您有未处理的历史欠费，请您先处理欠费。如果需要给其他车牌缴费，请告诉我另一个车牌信息，或者说退出。"
    FINISH_SCAN = "请扫码支付"





class PlateNumber(BaseModel):
    # 暂时先这么写，很快会有复杂车牌区分会加入更多属性
    plate_number: str = Field(
        title="车牌号", description="用户的车牌号，可以为空字符串"
    )

    @staticmethod
    def validator(info: "PlateNumber | str | None ") -> JudgeResult:
        if not info:
            return JudgeResult(judgment=False, reason=JieParkingReplyContents.NEED_PLATE_NUMBER.value)
        if isinstance(info, PlateNumber):
            plate_number = info.plate_number
        else:
            plate_number = info
        if isinstance(plate_number, str) and plate_number != "":
            plate_number = plate_number.replace(" ","")
            pattern = re.compile(
                # 普通5位车牌
                r"^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-HJ-NP-Z][A-HJ-NP-Z0-9]{4}[A-HJ-NP-Z0-9挂学警港澳]$"
                # 新能源车牌
                r"|[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-HJ-NP-Z][A-HJ-NP-Z0-9]{6}$"
            )
            if not pattern.match(plate_number):
                return JudgeResult(
                    judgment=False,
                    reason=JieParkingReplyContents.ASK_ILLEGAL_PLATE_NUMBER.value,
                )
            else:
                return JudgeResult(judgment=True, reason="")
        else:
            return JudgeResult(
                judgment=True, reason="车牌可以为合法车牌，也可以为空字符串或None"
            )

    @field_validator("plate_number", mode="before")
    @classmethod
    def format_plate_number(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.upper().replace(' ', '')
        return v


class KnowingStatus(StrEnum):

    YES = "是，金额正确，去缴费"
    NO = "否，金额不对"
    UNKNOWN = "不知道"


class CheckKnowingStatus(StrEnum):
    YES = "是，想查看"
    NO = "否，不想看"
    UNKNOWN = "不知道"

class ConfirmPayKnowingStatus(StrEnum):
    YES = "是，确认支付"
    NO = "否，取消支付"
    UNKNOWN = "不知道"

class PayOrNot(BaseModel):
    """确认是否支付"""
    pay_or_not: ConfirmPayKnowingStatus = Field(
        default=ConfirmPayKnowingStatus.UNKNOWN,
        title="确认是否支付或确认订单",
        description=(
            "从历史对话中提取用户是否确认支付。严格规则："
            "1) 只有当历史对话中 assistant 曾明确提过“是否确认支付/是否立即支付”等同义问题时，才允许根据用户回答给出“是，确认支付”或“否，取消支付”；如果未曾提问，则无论用户说了什么，pay_or_not 必须是“不知道”。"
            "2) 在已提问的前提下，用户说“确认订单/确认支付/立即支付”等肯定语义 → “是，确认支付”；"
            "说“取消/不对/不支付/拒绝”等否定语义 → “否，取消支付”；"
            "说“不知道/不清楚/查看/展示”等非确认类或其他无关语义 → “不知道”。"
        ),
    )

    @staticmethod
    def validator(info: "PayOrNot | str | None ") -> JudgeResult:
        pay_or_not = None
        if isinstance(info, PayOrNot):
            pay_or_not = info.pay_or_not
        if not info:
            return JudgeResult(
                judgment=False, reason=JieParkingReplyContents.ASK_PAY_OR_NOT.value
            )
        if pay_or_not == ConfirmPayKnowingStatus.UNKNOWN:
            return JudgeResult(
                judgment=False, reason=JieParkingReplyContents.ASK_PAY_OR_NOT.value
            )
        return JudgeResult(judgment=True, reason="")
class UserMeaningPureString(BaseModel):
    """用户的意思"""
    user_meaning: str | None = Field(default=None,
        title="当前对话记录中最新的用户表达的意思的小结。", description="""用户最新的表达意思的小结。\
        其中包括是否查看大额金额（如果是大额），确认金额是否正确，当前用户正在希望进行缴费的车辆车牌，是否支付等信息\
        注意：在提取用户表达的意思的小结时，你将小结总结成形如下方的格式（还不知道的信息就写不知道）：

            是否查看大额金额（如果是大额）：{查看/不看/不知道}
            确认金额是否正确：{正确/错误/不知道}
            当前用户正在希望进行缴费的车辆车牌：{车牌号码/不知道}

        同时你需要理解以下我给你的提示来正确总结：
            - 在询问用户确认金额是否正确时，如果用户说“去缴费”或者“查看费用明细”以及其他表示类似意思的提法，那么可以认为用户确认金额是正确的。
            - 在询问用户是否支付时，如果用户说“确认订单”以及其他表示类似意思的提法，那么可以认为用户要支付。
        特别注意!
            - 你需要仔细阅读下面的用户对话记录。如果用户最新的表达里切换了车牌号，但是在那之后没有提及这个新车牌号的任何相关金额确认或者是否查看大额的信息。
            那么你一定要重置是否查看大额金额和确认金额是否正确为不知道的状态！因为用户切换了车牌号，所以之前的金额确认和是否查看大额的信息都不再相关了而失效了。
        """
    )



class UserMeaning(BaseModel):
    """用户的意思"""
    # 拆出来4个，4*3 = 12个状态，测能否正确提取所需信息且不遗漏
    fee_correct_or_not: KnowingStatus = Field(
        default=KnowingStatus.UNKNOWN,
        title="确认费用是否正确",
        description="在看到当前页面上显示“缴费信息确认”的弹窗时你所需要的信息。意思是用户认为这个金额是否是正确的：{正确/错误/不知道},在询问用户确认金额是否正确时，用户会说除了说“正确”，“对”等表达金额正确的意思，还会直接说“去缴费”。如果用户说”去缴费“的话，那么也可以认为用户确认这个金额是正确的。记住！！！用户说过”去缴费“的话，fee_correct_or_not就是YES！就是是，金额正确，去缴费！！" #
    )

    fee_check_or_not: CheckKnowingStatus = Field(
        default=CheckKnowingStatus.UNKNOWN,
        title="确认是否查看金额或费用明细",
        description="用户确认是否查看金额或费用明细或去缴费：{查看/不看/不知道}，用户会用其他方式表达查看意图，如“查看”、“看”、“金额正确”等都表达希望查看金额或费用明细。"
    )

    plate_number: PlateNumber | None = Field(
        default=None,
        title="用户希望进行缴费的车牌号",
        description="对话历史中用户正在进行缴费任务所指的车牌号。注意，无论用户说的车牌号是什么形式，你都在这里以标准车牌号的写法记录下来，如（沪E12345），确保字母大写，车牌号中间没有任何空格等非字母数字的字符，不要出现汉字数字。"
    )

    @staticmethod
    def validator(info: "UserMeaning | None ") -> JudgeResult:
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

    @field_validator("plate_number", mode="before")
    @classmethod
    def format_plate_number(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.upper().replace(' ', '')
        return v