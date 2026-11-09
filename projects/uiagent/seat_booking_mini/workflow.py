from __future__ import annotations
from enum import StrEnum
from typing import Final
from datetime import datetime
from pydantic import BaseModel, Field

from nanoai.model.llm import ChatCompletionMessageParam
from nanoai.utils.nl_repr import nl_repr
from projects.uiagent.core.action import Button,ClickAction,AskAction,WaitAction,FinishedAction,TypeAction, InputBox, UiElement
from projects.uiagent.core.flow_data import (
    Action,
    EUIAction,
    Page,
    StepType,
    UIStepStatus,
    _END_STEP,
)
from projects.uiagent.core.uiflow import UIFlowBase, UIFlowState
from projects.uiagent.core.uistep import UIStepBase, UITask

class SeatBookingMiniUIFlowState(UIFlowState):
    background_info: str = Field(default=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",title="当前日期时间", description="当前日期时间，格式为YYYY-MM-DD HH:MM:SS")

class EPage(StrEnum):
    SELECT_RESTAURANT = "搜索饭店的所有页面"
    CONFIRM_SEAT_BOOKING_DETAILS = "订座详情页"
    CONFIRM_SEAT_BOOKING_PERSON_INFO = "订座确认页"


"""返回按钮，除了首页所有页面都有"""
return_button = Button(
    name="返回", description="这个按钮名称叫：“返回”，点击返回按钮的话，那么将返回上一页。这个按钮几乎都是在页面的左上角，是一个类似“<”的图标按钮。")

"""构造搜索饭店的所有页面我们关心的按钮"""
booking_button = Button(
    name="订座", description="这个按钮名称叫：“订座”，只有在单个餐厅的详情页出现，点击后会进入到确认订座信息页面开始进行订座。如果你见到的是形如`订座（已定x万+）`的按钮，那么这个按钮一定只能是'订座'按钮!不能名为'订座（已定x万+）'!")
search_box_like_button = Button(name="美食页面的输入栏按钮", description="注意，这是一个长得像输入栏但实际是个按钮的东西！只在当前最上方栏目名为“美食”时出现！点击后进入到美食搜索页面才能看到真正的搜索输入栏。")
true_search_box = InputBox(name="美食搜索输入栏", description="只在当前最上方栏目名为“美食搜索”时出现！用于搜索美食的输入栏，使用前必须先click点中再Type。", max_length=50)
search_restaurant_page_buttons: list[UiElement] = [
    booking_button, return_button, search_box_like_button, true_search_box]

"""构造订座信息页面我们关心的按钮"""
next_step_button = Button(
    name="下一步，填写预订信息", description="这个按钮名称叫：“下一步，填写预订信息”，点击订座信息页面的下一步按钮的话，那么将跳转到填写订座人信息的页面。")
seat_booking_details_buttons = [next_step_button, return_button]

"""构造填写订座人信息页面我们关心的元素"""
confirm_booking_button = Button(
    name="确认订座", description="这个按钮名称叫：“确认订座”，点击填写订座人信息页面的确认订座按钮的话，那么将提交订座信息。")
comment_box = InputBox(name="备注输入框", description="订座人留给餐厅的备注信息", max_length=25)
confirm_booking_buttons = [confirm_booking_button, return_button, comment_box]

PAGES: Final[list[Page]] = [
    Page(name=EPage.SELECT_RESTAURANT, description="你会看到这个页面形态非常多，但都是从美团的首页到店铺列表页到搜索页到店铺详情页在内的一系列页面。特别的是如果是首页，我们只关心美食栏目。而如果是店铺的详情页，我们只关注是否可订座。如果你见到了店铺列表页，你需要知道点击筛选那边的话，可以筛选价位（可以用拖拽设置），营业时间，用餐人数，用餐场景，餐厅品质（如黑珍珠，必吃榜，高分餐厅，连锁餐厅，新店等），餐厅服务（特别是筛选在线订座），设施和特色（如保健，宝宝椅，空调，情侣约会，无烟等等）。",
         ui_elements=search_restaurant_page_buttons),
    Page(name=EPage.CONFIRM_SEAT_BOOKING_DETAILS,
         description="页面为订座信息详情页，包括日期，时间，人数，座位类型等信息的订座选项（单个选项左右滑动展示），最下方为选定的信息及下一步按钮。", ui_elements=seat_booking_details_buttons),
    Page(name=EPage.CONFIRM_SEAT_BOOKING_PERSON_INFO,
         description="页面预定人信息页，包括姓名，性别，电话，备注等信息，最下方为确认订座按钮。", ui_elements=confirm_booking_buttons),
]


class SeatBookingStep(StrEnum):
    SEARCH_RESTAURANT = "搜索饭店"
    CONFIRM_SEAT_BOOKING_DETAILS = "确定订座信息"
    CONFIRM_SEAT_BOOKING_PERSON_INFO = "确定订座人信息"


class SearchRestaurantInfo(BaseModel):
    '''只有一个str成员，所以这个class仅仅为了结构化输出方便，本质上并没有用处。'''
    name: str = Field(default="", title="饭店名称",
                             description="用户想要订座的饭店名称")
    scratchpad: str = Field(
        default="", title="草稿纸", description="在搜寻饭店的过程中，在对话记录里可能会有一些你曾经针对一些突发，异常状况进行的发问，用户临时的想法，要求或注意事项等等各种信息需要你记下来以便帮助你在之后更好地帮用户找到他想要的店。你可以从对话记录中总结和提取出来记录在这里供后续使用。")


class SeatBookingDetails(BaseModel):
    '''订座详情
    TODO: 所有字段都有各种约束检查。如何实现还不清楚。
    '''
    number_of_people: int | None = Field(
        default=None, title="人数", description="订座人数")
    date: str = Field(default="", title="日期", description="订座日期")
    time: str = Field(default="", title="时间", description="订座时间")
    seat_type: str = Field(
        default="", title="座位类型", description="座位类型")
    scratchpad: str = Field(
        default="", title="草稿纸", description="在确认订座信息的过程中，在对话记录里可能会有一些你曾经针对一些突发，异常状况进行的发问，用户临时的想法，要求或注意事项，或额外的订座信息等等各种信息需要你记下来以便帮助你在之后更好地帮用户确定订座信息。你可以从对话记录中总结和提取出来记录在这里供后续使用。")


class SeatBookingPersonInfo(BaseModel):
    """订座人信息详情"""
    name: str = Field(default="", title="姓名", description="订座人的姓名")
    country_number: str = Field(default="+86", title="国家编号",
                                description="订座人的电话的国家编号，除非你觉得订座人提供的的电话号码明显不是中国的电话号码，否则无需过问。")
    phone_number: str = Field(
        default="", title="电话号码", description="订座人的电话号码")
    remark: str = Field(
        default="", title="备注", description="订座备注，注意，如果上面告诉过你这个备注栏的最大长度，那么你一定不要超过最大长度规定的字符数。")
    sex: str = Field(default="", title="性别", description="订座人性别")
    scratchpad: str = Field(
        default="", title="草稿纸", description="在确认订座人信息的过程中，在对话记录里可能会有一些你曾经针对一些突发，异常状况进行的发问，用户临时的想法，要求或注意事项，或额外的信息或者选项等等各种信息需要你记下来以便帮助你在之后更好地帮用户确定订座人及订座信息。你可以从对话记录中总结和提取出来记录在这里供后续使用。")


def _start_seatbookinng_map(actions: list[Action]) -> tuple[StepType, UIStepStatus]:
    assert len(actions) == 1
    the_action = actions[0]
    if isinstance(the_action, ClickAction):
        if the_action.target_ui_element and the_action.target_ui_element.name == booking_button.name:
            return SeatBookingStep.CONFIRM_SEAT_BOOKING_DETAILS, UIStepStatus.WAIT_FOR_IMAGE
        else:
            return SeatBookingStep.SEARCH_RESTAURANT, UIStepStatus.WAIT_FOR_IMAGE
    elif isinstance(the_action, AskAction):
        return SeatBookingStep.SEARCH_RESTAURANT, UIStepStatus.WAIT_FOR_INFO
    elif isinstance(the_action, WaitAction):
        return SeatBookingStep.SEARCH_RESTAURANT, UIStepStatus.WAIT_FOR_IMAGE
    elif isinstance(the_action, TypeAction):
        return SeatBookingStep.SEARCH_RESTAURANT, UIStepStatus.WAIT_FOR_IMAGE
    else:
        return SeatBookingStep.SEARCH_RESTAURANT, UIStepStatus.WAIT_FOR_IMAGE


def _next_step_action_map(actions: list[Action]) -> tuple[StepType, UIStepStatus]:
    assert len(actions) == 1
    the_action = actions[0]
    if isinstance(the_action, ClickAction):
        if the_action.target_ui_element:
            match the_action.target_ui_element.name:
                case next_step_button.name:
                    return SeatBookingStep.CONFIRM_SEAT_BOOKING_PERSON_INFO, UIStepStatus.WAIT_FOR_IMAGE
                case return_button.name:
                    return SeatBookingStep.SEARCH_RESTAURANT, UIStepStatus.WAIT_FOR_IMAGE
                case _:
                    return SeatBookingStep.CONFIRM_SEAT_BOOKING_DETAILS, UIStepStatus.WAIT_FOR_IMAGE
        else:
            return SeatBookingStep.CONFIRM_SEAT_BOOKING_DETAILS, UIStepStatus.WAIT_FOR_IMAGE
    elif isinstance(the_action, AskAction):
        return SeatBookingStep.CONFIRM_SEAT_BOOKING_DETAILS, UIStepStatus.WAIT_FOR_INFO
    elif isinstance(the_action, WaitAction):
        return SeatBookingStep.CONFIRM_SEAT_BOOKING_DETAILS, UIStepStatus.WAIT_FOR_IMAGE
    else:
        return SeatBookingStep.CONFIRM_SEAT_BOOKING_DETAILS, UIStepStatus.WAIT_FOR_IMAGE


def _submit_booking_action_map(actions: list[Action]) -> tuple[StepType, UIStepStatus]:
    assert len(actions) == 1
    the_action = actions[0]
    if isinstance(the_action, ClickAction):
        if the_action.target_ui_element:
            match the_action.target_ui_element.name:
                case confirm_booking_button.name:
                    # return _END_STEP, UIStepStatus.IDLE
                    return SeatBookingStep.CONFIRM_SEAT_BOOKING_PERSON_INFO, UIStepStatus.WAIT_FOR_IMAGE
                case return_button.name:
                    return SeatBookingStep.CONFIRM_SEAT_BOOKING_DETAILS, UIStepStatus.WAIT_FOR_IMAGE
                case _:
                    return SeatBookingStep.CONFIRM_SEAT_BOOKING_PERSON_INFO, UIStepStatus.WAIT_FOR_IMAGE
        else:
            return SeatBookingStep.CONFIRM_SEAT_BOOKING_PERSON_INFO, UIStepStatus.WAIT_FOR_IMAGE
    elif isinstance(the_action, AskAction):
        return SeatBookingStep.CONFIRM_SEAT_BOOKING_PERSON_INFO, UIStepStatus.WAIT_FOR_INFO
    elif isinstance(the_action, WaitAction):
        return SeatBookingStep.CONFIRM_SEAT_BOOKING_PERSON_INFO, UIStepStatus.WAIT_FOR_IMAGE
    elif isinstance(the_action, FinishedAction):
        return _END_STEP, UIStepStatus.IDLE
    else:
        return SeatBookingStep.CONFIRM_SEAT_BOOKING_PERSON_INFO, UIStepStatus.WAIT_FOR_IMAGE



class SeatBookingMiniUiFlow(UIFlowBase):
    def __init__(self):
        super().__init__(
            "订座",
            SeatBookingStep.SEARCH_RESTAURANT,
            {
                SeatBookingStep.SEARCH_RESTAURANT: UIStepBase(
                    SeatBookingStep.SEARCH_RESTAURANT,
                    UITask(page=PAGES[0], action_set=[EUIAction.CLICK, EUIAction.TYPE, EUIAction.SCROLL, EUIAction.ASK, EUIAction.DRAG, EUIAction.WAIT],
                           note=[
                        "建议1：如无必要，一般直接去美食频道里用里面的搜索来搜要订的餐厅，并且在搜索后去筛选一下在线订座。如果你看到筛选在线订座之后依然没有用户想订的餐厅那么说明这个餐厅不可在线订座。",
                        "建议2：尽量高效简短地和用户沟通的同时，一定要明确你沟通的最终目的是搞清楚用户想订哪个餐厅（特别是如果是连锁店或者同类的店很多，你要问清楚具体是哪个店，或者读一下列表里的候选餐厅让用户选择。），用比较高效的方式向用户询问你关心的问题。",
                        "建议3：多多关注草稿纸上的内容，那边记录着一些你之前自己记录的要点问题或者答案。",
                        "建议4：如果你看到当前视野里页面最上方栏目名是“美食搜索”的话，那么此时需要特别特别注意，一定要按照后面我说的来操作：在尝试输入关键字前，你一定要先看一下上文中提到的你之前执行过的操作动作记录，当且仅当前“2步”最新的动作是“点击”“美食页面的输入栏按钮”的动作和时，“点击”“美食搜索输入栏”的动作后，你才能进行美食搜索的Type输入操作。",
                        # "建议4：你不知道用户吃什么的时候，先问用户他大概想吃什么，然后再进行操作。",
                        "建议5：`美食页面`的输入栏按钮和`美食搜索`的输入栏是两个不同的页面下的要素，都需要在输入前分别点击之后才能输入！",
                        # 针对1.5模型的特殊建议：
                        "在`美食搜索页`输入餐厅名称后所展示的搜索结果列表可以忽略，此时不应该进行选店，而是去点击搜索按钮，进入搜索结果页面。",
                        "click 和drag中一定要有target_ui_element字段，可以为空字符串",
                    ]),
                    action_map=_start_seatbookinng_map,
                    middle_info_define=SearchRestaurantInfo,
                    task_gen=lambda back_ground_info, info, actions_record: f"你同时是一个资深美团探店博主，特别擅长操作美团小程序帮用户找到理想的餐厅进行订座。以下是一些你在这个过程中可能需要用到的供你参考用的信息：\n当前时间是:{back_ground_info}\n{nl_repr(next(iter(info.values())))}\n\n你之前执行过的操作动作记录（自上而下由旧到新）如下：[\n{"\n".join([str(action) for action in actions_record])}\n]",
                ),

                SeatBookingStep.CONFIRM_SEAT_BOOKING_DETAILS: UIStepBase(
                    SeatBookingStep.CONFIRM_SEAT_BOOKING_DETAILS,
                    UITask(page=PAGES[1], action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.DRAG, EUIAction.WAIT],
                           note=[
                        "建议1：尽量高效简短地和用户沟通的同时，一定要明确你沟通的最终目的是搞清楚用户订座该餐厅所需的所有信息，用比较高效的方式向用户询问你关心的问题。",
                        "建议2：多多关注草稿纸上的内容，那边记录着一些你之前自己记录的要点问题或者答案。",
                        "建议3：你真正关心的是用户表述的订座信息是否正确地被填写了，如果没有正确填写那么就直接去进行填写，如果不清楚或者有可能有问题那么就询问用户，但不要在你可以直接行动的时候还去麻烦人家用户，只在你需要的时候去询问用户。",
                        # 针对1.5模型的特殊建议：
                        "订座信息页，以用户表述的订座信息为主，没有时需要询问。按序去执行，先日期，时间，人数，座位类型。严格不能跳过任何一个步骤。若信息不可见时，自行尝试左右拖拽，而不是直接跳过！如若实在没有则告知用户，是否修改订座信息。",
                        "click 和drag中一定要有target_ui_element字段，可以为空字符串",
                    ]),
                    action_map=_next_step_action_map,
                    middle_info_define=SeatBookingDetails,
                    task_gen=lambda back_ground_info, info, actions_record: f"你同时是高级餐厅里非常擅长并负责操作美团订座界面帮助用户订座的主理人。你需要通过和用户认真交流，帮助他进行订座操作。以下是一些你在这个过程中可能需要用到的供你参考用的信息：\n当前时间是:{back_ground_info}\n你需要订座的信息是:{nl_repr(next(iter(info.values())))}\n\n你之前执行过的操作动作记录（自上而下由旧到新）如下：[\n{"\n".join([str(action) for action in actions_record])}\n]",
                ),
                SeatBookingStep.CONFIRM_SEAT_BOOKING_PERSON_INFO: UIStepBase(
                    SeatBookingStep.CONFIRM_SEAT_BOOKING_PERSON_INFO,
                    UITask(page=PAGES[2], action_set=[EUIAction.CLICK, EUIAction.TYPE, EUIAction.ASK, EUIAction.WAIT, EUIAction.FINISHED],
                           note=[
                            "建议1：尽量高效简短地和用户沟通的同时，一定要明确你沟通的最终目的是搞清楚用户订座该餐厅的订座人信息以及订座备注等任何你在画面中见到的其他与订座相关的信息，用比较高效的方式向用户询问你关心的问题。",
                            "建议2：多多关注草稿纸上的内容，那边记录着一些你之前自己记录的要点问题或者答案。",
                            "建议3：你真正关心的是用户表述的订座人和订座信息是否正确地被填写了，如果没有那么就直接去做，如果不清楚或者有可能有问题那么就询问用户，但不要在你可以直接行动的时候还去麻烦人家用户，只在你需要的时候去询问用户。",
                            "建议4：输入前你一定要检查之前的操作记录，确保前一个动作点击了你想要输入的输入框，再进行输入操作。",
                            # 针对1.5模型的特殊建议：
                            "click 中一定要有target_ui_element字段，可以为空字符串",
                    ]),
                    action_map=_submit_booking_action_map,
                    middle_info_define=SeatBookingPersonInfo,
                    task_gen=lambda back_ground_info, info, actions_record: f"你同时是高级餐厅里非常擅长并负责操作美团订座界面帮助用户订座的主理人。你需要通过和用户认真交流，帮助他进行填写订座人信息的操作，直到最后看到预订成功或需要预交定金则用Finished结束任务让用户接手进一步的操作。以下是一些你可能需要用到的信息：\n当前时间是:{back_ground_info}\n{nl_repr(next(iter(info.values())))}\n\n你之前执行过的操作动作记录（自上而下由旧到新）如下：[\n{"\n".join([str(action) for action in actions_record])}\n]",
                ),
            },
            state_cls=SeatBookingMiniUIFlowState,
            debug_mode=True,
        )


def test_uiflow_use_model():
    from nanoai.model.vlm import image_from_path
    from projects.uiagent.seat_booking_mini.datasets import DATASET_ROOT
    import asyncio

    image_path0 = str(DATASET_ROOT / "meituan2" /
                     "images" / "page_1_3_1_店铺名称_001.jpg")
    image0, image_format0 = image_from_path(image_path0)

    image_path = str(DATASET_ROOT / "meituan2" /
                     "images" / "page_2_订座_001.jpg")
    image, image_format = image_from_path(image_path)

    image_path_2 = str(DATASET_ROOT / "meituan2" /
                       "images" / "page_3_信息登记_001.jpg")
    image2, image_format2 = image_from_path(image_path_2)
    xml_detail = "detail"
    xml_submit = "submit"
    uiflow = SeatBookingMiniUiFlow()
    result = asyncio.run(uiflow.run_nl("帮我订个今天20点，8人大厅的海底捞的座位。"))
    print(result)
    print("+" * 100)
    result = asyncio.run(uiflow.run_ui(image0, image_format0))
    print(result)
    print("+" * 100)
    result = asyncio.run(uiflow.run_ui(image, image_format))
    print(result)
    print("+" * 100)
    result = asyncio.run(uiflow.run_ui(image2, image_format2))
    print(result)
    print("+" * 100)


if __name__ == "__main__":
    test_uiflow_use_model()
