from datetime import datetime
from typing import Final

from pydantic import BaseModel, Field

from projects.uiagent.core.flow_data import (
    Page,
    _END_STEP,
    EUIAction,
    UIStepStatus,
    MiddleInfoType, StepType,
    WorkflowStatus, UIResult,
)
from nanoai.utils.nl_repr import nl_repr
from projects.uiagent.core.flow_data import Action
from projects.uiagent.core.uiflow import UIFlowState, UIFlowBase
from projects.uiagent.core.uistep import UIStepBase, UITask
from projects.uiagent.core.action import ClickAction, AskAction, WaitAction, Button, InputBox, TypeAction, FinishedAction
from enum import StrEnum, Enum

class MovieTicketBookingUIFlowState(UIFlowState):
    background_info: str = Field(default=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",title="当前日期时间", description="当前日期时间，格式为YYYY-MM-DD HH:MM:SS")


class MovieTicketBookingStep(StrEnum):
    SELECT_MOVIE = "选择电影"
    SELECT_MOVIE_THEATRE_AND_TIME = "选择电影院和场次"
    SELECT_SEAT = "选择座位"
    CONFIRM_ORDER = "确认订单"
    PAYMENT = "支付"
    END = "结束"

class PageSelectMovieButtonNames(StrEnum):
    SEARCH_BOX_LIKE_BUTTON = "首页的输入栏按钮"
    SEARCH_BOX = "搜索输入栏"
    BUY_TICKET = "购票"

class PageSelectMovieButton(Enum):
    SEARCH_BOX_LIKE_BUTTON = Button(name=PageSelectMovieButtonNames.SEARCH_BOX_LIKE_BUTTON, description="在首页的顶部，注意，这是一个长得像输入栏但实际是个按钮的东西！点击进入到搜索页面才能看到真正的搜索输入栏。")
    SEARCH_BOX = InputBox(name=PageSelectMovieButtonNames.SEARCH_BOX, description="用于搜索电影的输入栏，使用前必须先click点中再Type。", max_length=50)
    BUY_TICKET = Button(name=PageSelectMovieButtonNames.BUY_TICKET, description="这个按钮名称叫“购票”，在电影列表页面中，点击这个按钮进入到电影详情页面。")

class PageSelectMovieTheatreButtonNames(StrEnum):
    SEARCH_SHOP = "搜索按钮"
    SEARCH_BOX = "搜索输入栏"
    MOVIE_THEATRE_BUTTON = "影院按钮"

class PageSelectMovieTheatreButton(Enum):
    SEARCH_SHOP = Button(name=PageSelectMovieTheatreButtonNames.SEARCH_SHOP, description="一个放大镜的按钮，点击这个按钮进入到搜索页面。")
    SEARCH_BOX = InputBox(name=PageSelectMovieTheatreButtonNames.SEARCH_BOX, description="用于搜索电影院的输入栏，使用前必须先click点中再Type。", max_length=50)
    MOVIE_THEATRE_BUTTON = Button(name=PageSelectMovieTheatreButtonNames.MOVIE_THEATRE_BUTTON, description="影院按钮，点击这个按钮选择这个电影院。")

class PageSelectTimeButtonNames(StrEnum):
    BUY_TICKET = "购票"
    SPECIAL_OFFER = "特惠"

class PageSelectTimeButton(Enum):
    BUY_TICKET = Button(name=PageSelectTimeButtonNames.BUY_TICKET, description="这个按钮名称有时叫“购票”，有时叫“特惠”，在电影场次列表页面中，点击这个按钮进入到选座页面。")

class PageSelectSeatButtonNames(StrEnum):
    RECOMMEND_SEAT = "推荐座位"
    CONFIRM_SEAT = "确认选座"

class PageSelectSeatButton(Enum):
    RECOMMEND_SEAT = Button(name=PageSelectSeatButtonNames.RECOMMEND_SEAT, description="推荐座位后面的人数可以点击，用户需求是几个人就点击几个人")
    CONFIRM_SEAT = Button(name=PageSelectSeatButtonNames.CONFIRM_SEAT, description="选择完座位后页面下方会出现一个确认选座按钮，点击这个按钮进入到确认订单页面。")

class PageConfirmOrderButtonNames(StrEnum):
    CONFIRM_ORDER = "确认支付"

class PageConfirmOrderButton(Enum):
    CONFIRM_ORDER = Button(name=PageConfirmOrderButtonNames.CONFIRM_ORDER, description="这个按钮名称叫“确认支付”，点击进入支付。")

class PagePaymentButtonNames(StrEnum):
    CONFIRM_PAYMENT = "确认支付"
    DIRECT_SCAN = "二维码支付"

class PagePaymentButton(Enum):
    CONFIRM_PAYMENT = Button(name=PagePaymentButtonNames.CONFIRM_PAYMENT, description="这个按钮名称叫“确认支付”，点击进入支付。")
    DIRECT_SCAN = Button(name=PagePaymentButtonNames.DIRECT_SCAN, description="二维码支付按钮")

PAGES: Final[dict[str, Page]] = {
    MovieTicketBookingStep.SELECT_MOVIE: Page(
        name="搜索电影的所有页面",
        # description="猫眼电影首页会展示一部分近期热门电影，电影搜索页可以根据关键词搜索电影。",
        description=(
            "搜索电影的页面涉及3个页面，包括猫眼电影首页、电影搜索页、电影搜索展示页。"
            "猫眼电影首页会展示一部分近期热门电影，如果热门电影列表中有用户想看的电影，那么就不必从搜索栏搜索，直接从首页点击该电影的“购票”按钮，不需要询问用户。首页上方的输入栏只是长得像输入栏，按钮名称就叫首页电影搜索输入栏。"
            "电影搜索页，在尝试输入关键字前，你一定要先看一下上文中提到的你之前执行过的操作动作记录，当且仅当前“2步”最新的动作是“点击”首页的“电影搜索输入栏”的动作和“点击”电影搜索页的“电影搜索输入栏”后，你才能进行影院搜索的Type输入操作(注意：必须是两个点击动作后才可以给输入动作，少一个都不行哦！)。"
            "电影搜索展示页会展示搜索到的电影，只需要关注带有“购票”按钮的电影，如果有可以购票的电影那么直接点击购票无需询问，如果有多个可以购票的电影需要询问用户选择哪一个，如果没有可以购票的电影那么就结束流程。"
            # "`猫眼电影首页`的输入栏按钮和`电影搜索页`的输入栏是两个不同的页面下的要素，都需要在输入前分别点击之后才能输入！"
        ),
        ui_elements=[member.value for member in PageSelectMovieButton],
    ),
    MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME: Page(
        name="选择电影院和观影时间的所有页面",
        # description="你会看到这个页面的形态非常多。包括影院列表展示页会展示该电影排片的影院，影院搜索页可以根据关键词搜索电影院，观影日期和场次选择页是确定了电影院后可以进行观影日期和时间场次选择。特别注意的是：日期(左右滑动展示)、场次(上下滑动展示)，电影播放场次列表右侧有“购票”或“特惠”或者其他名称的按钮，点击这个按钮进入到选座页面。",
        # description="你会看到这个页面的形态非常多。包括影院列表展示页会展示该电影排片的影院，影院搜索页可以根据关键词搜索电影院(需要注意的是：选择影院时，因为用户说的某某影院可能有多个不同的门店，所以一般情况下选择用户想要去的影院需要在影片详情页点击影院列表右上方的那个搜索按钮(一个放大镜图标的按钮)进行搜索；只有在影片详情页影院列表个数有限且存在用户想去的影院时，才可以直接点击列表中的影院选择。)，观影日期和场次选择页是确定了电影院后可以进行观影日期和时间场次选择。特别注意的是：日期(左右滑动展示)、场次(上下滑动展示)，电影播放场次列表右侧有“购票”或“特惠”或者其他名称的按钮，点击这个按钮进入到选座页面。",
        description=(
            "选择电影院和观影时间的页面涉及4个页面，包括影院列表展示页、影院搜索页、影院搜索结果页、影片场次选择页。"
            "影院列表展示页会显示这个电影排片的影院，因为用户说的某某影院可能有多个不同的门店，所以选择影院只能在影片详情页点击影院列表右上方的那个搜索按钮(一个放大镜图标的按钮)进行搜索，另外观影日期也不可以在这个页面询问和选择。"
            "影院搜索页，在尝试输入关键字前，你一定要先看一下上文中提到的你之前执行过的操作动作记录，当且仅当前“1步”最新的动作是“点击”“影院搜索输入栏”(注意：不是放大镜图标按钮哦！)的动作后，你才能进行影院搜索的Type输入操作。"
            "影院搜索结果页会展示搜索到的影院，如果有多个结果，需要询问用户选择哪一个。"
            "影片场次选择页展示了该电影在这个影院可选择的观影日期和场次时间。"
        ),
        ui_elements=[member.value for member in PageSelectMovieTheatreButton],
    ),
    # MovieTicketBookingStep.SELECT_TIME: Page(
    #     name="选择时间页面",
    #     description="页面为电影详情页，包括日期(左右滑动展示)、场次(上下滑动展示)，电影播放场次列表右侧有“购票”或“特惠”或者其他名称的按钮，点击这个按钮进入到选座页面。",
    #     ui_elements=[member.value for member in PageSelectTimeButton],
    # ),
    MovieTicketBookingStep.SELECT_SEAT: Page(
        name="选择座位页面",
        description="页面为选座页面，包括座位图、推荐座位、选座，点击“确认选座”进入确认订单页面。",
        ui_elements=[member.value for member in PageSelectSeatButton],
    ),
    MovieTicketBookingStep.CONFIRM_ORDER: Page(
        name="确认订单页面",
        description="订单详情页，这个页面可能会出现“退改签规定协议”弹窗，如果弹窗出现，请点击“我已阅读并同意以上协议”前面的勾选按钮(注意：没有勾选是灰色的，勾选完成后是绿色的)，然后点击“继续购票”才能关闭弹窗进入确认订单页面。",
        ui_elements=[member.value for member in PageConfirmOrderButton],
    ),
    MovieTicketBookingStep.PAYMENT: Page(
        name="支付页面",
        description="有支付方式选择和展示的页面",
        ui_elements=[member.value for member in PagePaymentButton],
    ),
}

class SearchMovieInfo(BaseModel):
    name: str = Field(default="", title="电影名称", description="用户看的电影名称。")
    scratchpad: str = Field(
        default="", title="草稿纸",
        description="在搜寻电影的过程中，在对话记录里可能会有一些你曾经针对一些突发，异常状况进行的发问，用户临时的想法，要求或注意事项等等各种信息需要你记下来以便帮助你在之后更好地帮用户找到他想要看的电影。你可以从对话记录中总结和提取出来记录在这里供后续使用。"
    )

# class SelectMovieTheatreInfo(BaseModel):
#     name: str = Field(default="", title="电影院名称", description="用户要去哪个电影院观影")
#     scratchpad: str = Field(
#         default="", title="草稿纸",
#         description="在寻找电影院的过程中，在对话记录里可能会有一些你曾经针对一些突发，异常状况进行的发问，用户临时的想法，要求或注意事项等等各种信息需要你记下来以便帮助你在之后更好地帮用户找到他想要去的电影院。你可以从对话记录中总结和提取出来记录在这里供后续使用。"
#     )

class SelectTheatreAndTimeInfo(BaseModel):
    name: str = Field(default="", title="电影院名称", description="用户要去哪个电影院观影")
    date: str = Field(default="", title="观影日期", description="用户想要看电影的日期")
    time: str = Field(default="", title="观影时间", description="用户想要看电影的场次时间")
    scratchpad: str = Field(
        default="", title="草稿纸",
        description="在预订电影票的过程中，在对话记录里可能会有一些你曾经针对一些突发，异常状况进行的发问，用户临时的想法，要求或注意事项等等各种信息需要你记下来以便帮助你在之后更好地帮用户确定订票信息。你可以从对话记录中总结和提取出来记录在这里供后续使用。"
    )

class SelectSeatInfo(BaseModel):
    number_of_people: int | None = Field(
        default=None, title="影票张数", description="需要购买的影票张数")
    scratchpad: str = Field(
        default="", title="草稿纸",
        description="在确定影票张数的过程中，在对话记录里可能会有一些你曾经针对一些突发，异常状况进行的发问，用户临时的想法，要求或注意事项等等各种信息需要你记下来以便帮助你在之后更好地帮用户选择座位。你可以从对话记录中总结和提取出来记录在这里供后续使用。"
    )

class ConfirmPayKnowingStatus(StrEnum):
    YES = "是，确认支付"
    NO = "否，取消支付"
    UNKNOWN = "不知道"

class ConfirmOrderInfo(BaseModel):
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

class UIStepSelectMovie(UIStepBase):
    def __init__(self):
        super().__init__(
            step=MovieTicketBookingStep.SELECT_MOVIE,
            ui_task=UITask(
                page=PAGES[MovieTicketBookingStep.SELECT_MOVIE],
                task=MovieTicketBookingStep.SELECT_MOVIE,
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.TYPE, EUIAction.SCROLL, EUIAction.WAIT],
                note=[
                    # "建议一：尽量高效简短地和用户沟通的同时，一定要明确你沟通的最终目的是搞清楚用户想看哪个电影（特别是如果同类的电影很多，你要问清楚具体是哪个电影，或者读一下列表里的候选电影让用户选择。），用比较高效的方式向用户询问你关心的问题。"
                    # "如果首页的热门电影列表中有用户想看的电影，那么就不必从搜索栏搜索，直接从首页点击该电影的“购票”按钮，不需要询问用户。",
                    "click 中一定要有target_ui_element字段，可以为空字符串，并且按钮名称要是页面上按钮显示的内容，不可以自行加上其他无关内容。比如：“购票”按钮，就直接展示购票就行，不需要加上电影名。",
                    "首页可能会出现电影宣传的弹窗，并且弹窗下有倒计时，2s、1s等等，这种弹窗会自己关闭，所以不能用click，只能用wait。"
                    #TODO 约束没起作用
                    # "如果你当前是在影片搜索页面的话，那么此时需要特别特别注意，一定要按照后面我说的来操作：在尝试输入关键字前，你一定要先看一下上文中提到的你之前执行过的操作动作记录，当且仅当前“2步”最新的动作是“点击”“首页的输入栏按钮”的动作时和“点击”“影片搜索输入栏”的动作后，你才能进行影片搜索的Type输入操作。如果操作记录没有记录任何内容，那么应该先点击搜索输入栏。",
                    # "`首页`的输入栏按钮和`影片搜索`的输入栏是两个不同的页面下的要素，都需要在输入前分别点击之后才能输入！",
                ]
            ),
            action_map=self._action_map,
            middle_info_define=SearchMovieInfo,
            task_gen=lambda back_ground_info, info, actions_record: f"你同时是电影院里非常擅长并负责操作微信小程序界面帮助用户订电影票的主理人，你需要通过和用户认真交流，帮助他选择他想看的电影。以下是一些你在这个过程中可能需要用到的供你参考用的信息：\n当前时间是:{back_ground_info}\n{nl_repr(next(iter(info.values())))}\n\n你之前执行过的操作动作记录（自上而下由旧到新）如下：[\n{"\n".join([str(action) for action in actions_record])}\n]",
        )

    def _action_map(self, actions: list[Action]) -> tuple[StepType, UIStepStatus]:
        assert len(actions) == 1
        the_action = actions[0]
        if isinstance(the_action, ClickAction):
            if the_action.target_ui_element and the_action.target_ui_element.name == PageSelectMovieButtonNames.BUY_TICKET:
                return MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME, UIStepStatus.WAIT_FOR_IMAGE
            else:
                return MovieTicketBookingStep.SELECT_MOVIE, UIStepStatus.WAIT_FOR_IMAGE
        elif isinstance(the_action, AskAction):
            return MovieTicketBookingStep.SELECT_MOVIE, UIStepStatus.WAIT_FOR_INFO
        elif isinstance(the_action, WaitAction):
            return MovieTicketBookingStep.SELECT_MOVIE, UIStepStatus.WAIT_FOR_IMAGE
        elif isinstance(the_action, TypeAction):
            return MovieTicketBookingStep.SELECT_MOVIE, UIStepStatus.WAIT_FOR_IMAGE
        else:
            return MovieTicketBookingStep.SELECT_MOVIE, UIStepStatus.WAIT_FOR_IMAGE

class UIStepSelectMovieTheatreAndTime(UIStepBase):
    def __init__(self):
        super().__init__(
            step=MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME,
            ui_task=UITask(
                page=PAGES[MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME],
                task=MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME,
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.TYPE, EUIAction.SCROLL, EUIAction.WAIT],
                note=[
                    "尽量高效简短地和用户沟通的同时，一定要明确你沟通的最终目的是搞清楚用户购买电影票的所有信息，用比较高效的方式向用户询问你关心的问题。不要一次性提出所有的问题，而是要根据页面信息逐步地提出当前关心的问题，这样用户才能有选择性地回答。",
                    "多多关注草稿纸上的内容，那边记录着一些你之前自己记录的要点问题或者答案。",
                    # "不管页面上有没有用户想要去的影院，一律点击搜索按钮(一个放大镜图标的按钮)进行影院搜索。",
                    # "选择影院时，因为用户说的某某影院可能有多个不同的门店，所以一般情况下选择用户想要去的影院需要在影片详情页点击影院列表右上方的那个搜索按钮(一个放大镜图标的按钮)进行搜索；只有在影片详情页影院列表个数有限且存在用户想去的影院时，才可以直接点击列表中的影院选择。",
                    # "如果你当前是在影院搜索页面的话，那么此时需要特别特别注意，一定要按照后面我说的来操作：在尝试输入关键字前，你一定要先看一下上文中提到的你之前执行过的操作动作记录，当且仅当前“1步”最新的动作是“点击”“影院搜索输入栏”的动作后，你才能进行影院搜索的Type输入操作。",
                    "如果用户所需观影日期不可见时，自行尝试左右拖拽，而不是直接跳过！如若实在没有则告知用户，是否修改观影日期。",
                    "如果用户没有明确他的观影时间，一定要询问用户；如果用户的观影时间在当前页面不可见时，自行尝试上下拖拽而不是直接跳过！特别要注意的是：影片场次是按时间顺序从上到下顺序排列的，所以你要结合页面展示的时间信息和用户所输入的观影时间来判断是否应该进行拖拽，如果很明显用户输入的观影时间该影院就没有这个场次，那么你应该用ask_human来询问用户：当前该影院有xx场次，请问你要选择哪个场次观看？",
                ]
            ),
            action_map=self._action_map,
            middle_info_define=SelectTheatreAndTimeInfo,
            task_gen=lambda back_ground_info, info, actions_record: f"你同时是电影院里非常擅长并负责操作微信小程序界面帮助用户订电影票的主理人，你需要通过和用户认真交流，帮助他选择他想要去的影院以及观影的日期和时间。以下是一些你在这个过程中可能需要用到的供你参考用的信息：\n当前时间是:{back_ground_info}\n{nl_repr(next(iter(info.values())))}\n\n你之前执行过的操作动作记录（自上而下由旧到新）如下：[\n{"\n".join([str(action) for action in actions_record])}\n]",
        )
    def _action_map(self, actions: list[Action]) -> tuple[StepType, UIStepStatus]:
        assert len(actions) == 1
        the_action = actions[0]
        if isinstance(the_action, ClickAction):
            if the_action.target_ui_element and (PageSelectTimeButtonNames.BUY_TICKET in the_action.target_ui_element.name or PageSelectTimeButtonNames.SPECIAL_OFFER in the_action.target_ui_element.name):
                return MovieTicketBookingStep.SELECT_SEAT, UIStepStatus.WAIT_FOR_IMAGE
            else:
                return MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME, UIStepStatus.WAIT_FOR_IMAGE
        elif isinstance(the_action, AskAction):
            return MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME, UIStepStatus.WAIT_FOR_INFO
        elif isinstance(the_action, WaitAction):
            return MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME, UIStepStatus.WAIT_FOR_IMAGE
        elif isinstance(the_action, TypeAction):
            return MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME, UIStepStatus.WAIT_FOR_IMAGE
        else:
            return MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME, UIStepStatus.WAIT_FOR_IMAGE

class UIStepSelectSeat(UIStepBase):
    def __init__(self):
        super().__init__(
            step=MovieTicketBookingStep.SELECT_SEAT,
            ui_task=UITask(
                page=PAGES[MovieTicketBookingStep.SELECT_SEAT],
                task=MovieTicketBookingStep.SELECT_SEAT,
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.TYPE, EUIAction.SCROLL, EUIAction.WAIT],
                note=[
                    # "如果用户没有明确观影人数，需要询问用户。如果已经明确了观影人数，那就不需要重复向用户确认了。"
                    "如果页面上有推荐座位的按钮，则按人数点击推荐座位按钮。",
                    "如果页面上没有推荐座位的按钮，请你自行帮用户选择座位。", #TODO 怎么选择待产品确定
                    "如果页面上已经选中了对应观影人数的座位，那么就可以点击确认订座了。",
                    "如果页面上显示没有座位可售，那么直接用finished动作结束任务并在其content里告诉用户：当前影院场次电影没有座位可售，我先退下了。",
                ]
            ),
            action_map=self._action_map,
            middle_info_define=SelectSeatInfo,
            task_gen=lambda back_ground_info, info, actions_record: f"你同时是电影院里非常擅长并负责操作微信小程序界面帮助用户订电影票的主理人，你需要通过和用户认真交流，帮助他选择座位。以下是一些你在这个过程中可能需要用到的供你参考用的信息：\n当前时间是:{back_ground_info}\n{nl_repr(next(iter(info.values())))}\n\n你之前执行过的操作动作记录（自上而下由旧到新）如下：[\n{"\n".join([str(action) for action in actions_record])}\n]",
        )

    def _action_map(self, actions: list[Action]) -> tuple[StepType, UIStepStatus]:
        assert len(actions) == 1
        the_action = actions[0]
        if isinstance(the_action, ClickAction):
            if the_action.target_ui_element and PageSelectSeatButtonNames.CONFIRM_SEAT in the_action.target_ui_element.name:
                return MovieTicketBookingStep.CONFIRM_ORDER, UIStepStatus.WAIT_FOR_IMAGE
            else:
                return MovieTicketBookingStep.SELECT_SEAT, UIStepStatus.WAIT_FOR_IMAGE
        elif isinstance(the_action, AskAction):
            return MovieTicketBookingStep.SELECT_SEAT, UIStepStatus.WAIT_FOR_INFO
        elif isinstance(the_action, WaitAction):
            return MovieTicketBookingStep.SELECT_SEAT, UIStepStatus.WAIT_FOR_IMAGE
        elif isinstance(the_action, TypeAction):
            return MovieTicketBookingStep.SELECT_SEAT, UIStepStatus.WAIT_FOR_IMAGE
        else:
            return MovieTicketBookingStep.SELECT_SEAT, UIStepStatus.WAIT_FOR_IMAGE

class UIStepConfirmOrder(UIStepBase):
    def __init__(self):
        super().__init__(
            step=MovieTicketBookingStep.CONFIRM_ORDER,
            ui_task=UITask(
                page=PAGES[MovieTicketBookingStep.CONFIRM_ORDER],
                task=MovieTicketBookingStep.CONFIRM_ORDER,
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.FINISHED, EUIAction.WAIT],
                note=[
                    "如果用户当前最新表达的意思里并没有明确表达确认支付，那么你需要用ask_human来向用户回复：请确认xx影院，xx电影，xx日期xx场次，几个人，xx金额，是否支付？",
                    f"如果用户当前最新表达的意思里明确表示了他希望支付该订单，那么你需要点击{PageConfirmOrderButtonNames.CONFIRM_ORDER}按钮。",
                    "如果用户表达的意思是不想支付该订单，那么直接用finished动作结束任务并在其content里告诉用户：我先退下啦，有事可以再来找我。",
                    # "如果页面上出现协议弹窗，那么你需要先勾选同意协议，然后再点击继续购票。"
                ]
            ),
            action_map=self._action_map,
            middle_info_define=ConfirmOrderInfo,
            task_gen=lambda info: f"用户回答的是否确认支付的信息如下：\n{nl_repr(next(iter(info.values())))}。如果用户表示确认支付，那么点击确认订单按钮。",
        )

    def _action_map(self, actions: list[Action]) -> tuple[StepType, UIStepStatus]:
        assert len(actions) == 1
        the_action = actions[0]
        if isinstance(the_action, ClickAction):
            if the_action.target_ui_element and the_action.target_ui_element.name == PageConfirmOrderButtonNames.CONFIRM_ORDER:
                return MovieTicketBookingStep.PAYMENT, UIStepStatus.WAIT_FOR_IMAGE
            else:
                return MovieTicketBookingStep.CONFIRM_ORDER, UIStepStatus.WAIT_FOR_IMAGE
        elif isinstance(the_action, AskAction):
            return MovieTicketBookingStep.CONFIRM_ORDER, UIStepStatus.WAIT_FOR_INFO
        elif isinstance(the_action, WaitAction):
            return MovieTicketBookingStep.CONFIRM_ORDER, UIStepStatus.WAIT_FOR_IMAGE
        elif isinstance(the_action, TypeAction):
            return MovieTicketBookingStep.CONFIRM_ORDER, UIStepStatus.WAIT_FOR_IMAGE
        else:
            return MovieTicketBookingStep.CONFIRM_ORDER, UIStepStatus.WAIT_FOR_IMAGE

class UIStepPayment(UIStepBase):
    def __init__(self):
        super().__init__(
            step=MovieTicketBookingStep.PAYMENT,
            ui_task=UITask(
                page=PAGES[MovieTicketBookingStep.PAYMENT],
                task=MovieTicketBookingStep.PAYMENT,
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.FINISHED, EUIAction.WAIT],
                note=[
                    "如果你看到了确认支付按钮，那么点击确认支付。"
                    "如果你看到点击微信支付的勾选框（如果勾选着了就不用点了），那么直接点击下方的去支付按钮。",
                    "如果你看到中间一个弹窗里的下方有二维码支付几个字，那么点击二维码支付。",
                    "如果你看到了二维码，那么用finished结束任务并在其content内告知用户扫码付款。",
                    "如果你看到任何其他和支付无关的弹窗，统统点击关闭或拒绝等按钮以便继续进行支付任务。",
                ]
            ),
            action_map=self._action_map,
        )

    def _action_map(self, actions: list[Action]) -> tuple[StepType, UIStepStatus]:
        assert len(actions) == 1
        the_action = actions[0]
        if isinstance(the_action, FinishedAction):
            return _END_STEP, UIStepStatus.IDLE
        else:
            return MovieTicketBookingStep.PAYMENT, UIStepStatus.WAIT_FOR_IMAGE

movie_ticket_booking_intent_categories = [
        ("Relevant", "任何与购买电影票可能相关的意图，包括但不限于说个电影名、电影院名称，支付与否，几个人等等。"),
        ("Abort", '用户希望退出，终止，取消当前工作的意图。'),
        ("Irrelevant", "其他任何与购买电影票无关的意图统统属于这个。"),
    ]

class MovieTicketBookingUiFlow(UIFlowBase):
    def __init__(self):
        super().__init__(
            "猫眼购票",
            MovieTicketBookingStep.SELECT_MOVIE,
            {
                MovieTicketBookingStep.SELECT_MOVIE: UIStepSelectMovie(),
                MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME: UIStepSelectMovieTheatreAndTime(),
                MovieTicketBookingStep.SELECT_SEAT: UIStepSelectSeat(),
                MovieTicketBookingStep.CONFIRM_ORDER: UIStepConfirmOrder(),
                MovieTicketBookingStep.PAYMENT: UIStepPayment(),
            },
            debug_mode=True,
            intent_categories=movie_ticket_booking_intent_categories,
            state_cls=MovieTicketBookingUIFlowState,
        )

if __name__ == '__main__':
    print(PageSelectMovieButtonNames.BUY_TICKET.value)