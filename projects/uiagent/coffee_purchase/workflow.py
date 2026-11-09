from __future__ import annotations
from enum import StrEnum
from typing import Final, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

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


class CoffeePurchaseUIFlowState(UIFlowState):
    background_info: str = Field(default=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",title="当前日期时间", description="当前日期时间，格式为YYYY-MM-DD HH:MM:SS")


class CoffeePurchasePage(StrEnum):
    SELECT_TAKEOUT_OR_PICKUP = "首页"
    SELECT_ADDRESS = "选择地址"
    SELECT_PRODUCT = "选择商品名"
    SELECT_SPEC = "选择商品规格"
    CONFIRM_ORDER = "确认订单"


# """返回按钮，除了首页所有页面都有"""
# return_button = Button(name="返回", description="这个按钮名称叫：`返回`，点击返回按钮的话，那么将返回上一页。这个按钮几乎都是在页面的左上角，是一个类似“<”的图标按钮。")

takeout_button = Button(name="到店取", description="`到店取`代表`自提`")
pickup_button = Button(name="幸运送", description="`幸运送`代表`外卖`")

more_store_button = Button(name="更多门店", description="`更多门店`，点击后会跳转到更多门店页面。")

# 地址按钮
address_button = Button(
    name="地址", 
    description="这是一个抽象的按钮，代表任何店铺地址列表或送货上门页面中的`我的收货地址`栏所展示的地址列表，（菜单页左上角`自提|外送`字样下的定位信息按钮不属于该按钮）"
)

location_button = Button(
    name="定位信息入口",
    description="这是一个按钮，当且仅当当前页面是下方有`菜单`时，左上角`自提|外送`字样下的定位信息入口，点击后会跳转到地址选择页面。（自提或外送方式下均有该按钮）"
)
product_button = Button(
    name="商品", 
    description="这是一个抽象的按钮，代表任何商品。当你点击任何具体的商品（如'标准美式'、'拿铁'、'卡布奇诺'等）时，在 target_ui_element 中应该填写'商品'，而不是具体的商品名称。点击商品后，会跳转到商品规格选择页面。"
)
address_search_box = InputBox(name="地址页搜索输入栏", description="只在当前最上方名为“配送方式（门店自提）”时出现！仅用于搜索地址的输入栏，使用前必须先click点中再Type。", max_length=50)
menu_search_box = InputBox(name="菜单页搜索输入栏", description="只在当前最下方栏目名为“菜单”时出现！切记只能用于搜索商品名，只能搜索商品名，不能搜索地址！使用前必须先click点中再Type。", max_length=50)

buy_now_button = Button(name="立即购买", description="`立即购买`，一般为一个商品时，可直接点击，点击将跳转到`确认订单`页面。")
add_to_cart_button = Button(name="加入购物车", description="`加入购物车`，代表有其他商品加购意图，点击将跳转到`商品名`页面。")

confirm_order_button = Button(name="提交订单", description="`去支付or免密支付or提交订单`，付钱的按钮，点击后进入一个弹窗页面，图中间会有`发送到手机微信支付`以及`二维码支付`字样的白色区域。")

qr_code_payment_button = Button(name="二维码支付", description="`二维码支付`，点击去支付后会弹出`订单支付`页面，目前只支持`二维码支付`这种方式支付,不可点关闭（x）和`发送到手机微信支付`按钮。")

PAGES: Final[list[Page]] = [
    Page(
        name=CoffeePurchasePage.SELECT_TAKEOUT_OR_PICKUP, 
        description="首页，通常包含`到店取`以及`幸运送`的按钮。分别对应自取以及外卖。我们只关心`到店取`以及`幸运送`。", 
        ui_elements=[takeout_button, pickup_button, more_store_button]
    ),
    Page(
        name=CoffeePurchasePage.SELECT_ADDRESS, 
        description="""
        用于选择地址，通常包含自提时店铺地址的选择与搜索和外送方式时用户地址的选择与添加。
        **重要：从首页点击后，可能直接跳到菜单页面（若是外送方式，当有默认信息时，可能会跳转这个页面，此时需要点击去校对地址是否正确）。**
        左上角`自提|外送`字样下包含定位信息按钮(注：该按钮非`地址`按钮)，点击后会跳转到地址选择页面。
        如果当前是地址选择页：`门店自提`通常包含店铺地址列表，自提时上方会有搜索框，下方会有个别店铺地址，上方会有`配送方式`字样。`送货上门`时下方会有`新增收货地址`按钮、`我的收货地址`（可能不存在）、`附近地址`两栏。
        如果当前是菜单页：包含商品列表和搜索框，最下方栏目名为"菜单"。
        点击店铺地址或用户地址后，会跳转到菜单页面。
        """, 
        ui_elements=[address_button, address_search_box, menu_search_box, location_button]  # 不包含商品按钮
    ),
    Page(
        name=CoffeePurchasePage.SELECT_PRODUCT, 
        description="""
        菜单页面，用于选择商品。
        这个页面会有很多元素，包括自提时包含定位图标，搜索框等，外卖时包含搜索框等，重点关注搜索框。
        `菜单页搜索输入栏`右侧有`搜索`按钮，往往是输入内容后点击该按钮进行搜索。
        """, 
        ui_elements=[menu_search_box, product_button]
    ),
    Page(
        name=CoffeePurchasePage.SELECT_SPEC, 
        description="用于选择商品的属性，属性会直接展示在图中，不会有折叠以及左右滑动，当前页面可能无法展示全部属性。",
        ui_elements=[buy_now_button]
    ),
    Page(
        name=CoffeePurchasePage.CONFIRM_ORDER, 
        description="""
        用于支付订单，这个页面形态非常多,比如通知弹窗，去支付按钮or免密支付，白底的`订单支付`弹窗页面（注意该页面的区分，该页面是弹窗，有效的区域就是这个白底，有`发送到手机微信支付`以及`二维码支付`字样）等等。
        """,
        ui_elements=[confirm_order_button, qr_code_payment_button]
    ),
]

class CoffeePurchaseStep(StrEnum):
    SELECT_TAKEOUT_OR_PICKUP = "选择用餐方式"
    SELECT_ADDRESS = "选择地址"
    SELECT_PRODUCT = "选择商品名"
    SELECT_SPEC = "选择商品属性"
    CONFIRM_ORDER = "确认订单"


class TakeoutOrPickupInfo(BaseModel):
    '''用餐方式'''
    name: Literal["自提", "外卖"] | None = Field(default=None, title="用餐方式", description="用餐方式支持`自提`和`外卖`.")
    scratchpad: str | None = Field(default=None, title="草稿纸", description="在选择用餐方式的过程中，在对话记录里可能会有一些你曾经针对一些突发，异常状况进行的发问，用户临时的想法，要求或注意事项等等各种信息需要你记下来以便帮助你在之后更好地帮用户找到他想要的用餐方式。你可以从对话记录中总结和提取出来记录在这里供后续使用。")

class AddressInfo(BaseModel):
    '''地址信息，可能是门店地址，也可能是用户地址'''
    name: str | None = Field(default=None, title="地址信息", description="地址信息，可能是门店地址，也可能是用户的收货地址")
    scratchpad: str | None = Field(default=None, title="草稿纸", description="在选择地址信息的过程中，在对话记录里可能会有一些你曾经针对一些突发，异常状况进行的发问，用户临时的想法，要求或注意事项等等各种信息需要你记下来以便帮助你在之后更好地帮用户找到他想要的地址信息。你可以从对话记录中总结和提取出来记录在这里供后续使用。")

class Product_Spec(BaseModel):
    '''不同商品支持不同的属性，属性是动态的，根据商品页面实际显示的属性来填写'''
    model_config = ConfigDict(extra='allow')  # 允许额外字段，支持动态属性
    
    # 常见属性作为可选字段
    temperature: str | None = Field(default=None, title="温度", description="冰、热")
    sugar: str | None = Field(default=None, title="糖", description="标准甜、少甜、少少甜、微甜、不另外加糖等明确表述")
    # cup_size: str | None = Field(default=None, title="杯型", description="杯型")
    quantity: int = Field(default=1, title="数量", description="数量", ge=1)
    
    scratchpad: str | None = Field(
        default=None,
        title="草稿纸",
        description="在选择商品属性的过程中，用户提供可能会有部分属性不存在或者缺失，需要你记录下来，以便后续使用。"
    )

class ConfirmIntent(BaseModel):
    '''用户确认意图'''
    is_confirmed: bool | None = Field(
        default=None,
        title="用户确认意图",
        description="用户是否确认了当前的选择去支付。如果用户回复'好的'、'可以'、'就这样'、'没问题'、'确认'等确认性词语，则为True；否则为False。如果用户没有明确回复，则为None。None代表不重要，可以不需要交互直接去结账。"
    )

class ProductName(BaseModel):
    '''商品名称，支持多个商品,无法测试，先去掉，只支持单个商品，咖啡名不清晰，添加validator，error_reason'''
    name: str = Field(
        default="",
        title="商品名称列表",
        description="商品名称，必须是具体的商品名称，不能是`咖啡`这种不明确的大类表述。例如：'标准美式'、'拿铁'、'卡布奇诺'、'生椰拿铁'等具体商品名。"
    )
    scratchpad: str | None = Field(
        default=None,
        title="草稿纸",
        description="在选择商品的过程中，在对话记录里可能会有一些你曾经针对一些突发，异常状况进行的发问，用户临时的想法，要求或注意事项等等各种信息需要你记下来以便帮助你在之后更好地帮用户找到他想要的商品。你可以从对话记录中总结和提取出来记录在这里供后续使用。"
    )
    #TODO 目前框架暂未支持
    @staticmethod
    def validator(info: ProductName) -> JudgeResult:
        if info.name == "咖啡":
            return JudgeResult(judgment=False, reason="请您提供具体的商品名称。如：标准美式、拿铁、卡布奇诺、生椰拿铁等。")

        return JudgeResult(judgment=True, reason="提取的商品名有效")


def _start_buy_coffee_map(actions: list[Action]) -> tuple[StepType, UIStepStatus]:
    assert len(actions) == 1
    the_action = actions[0]
    if isinstance(the_action, ClickAction):
        if the_action.target_ui_element and the_action.target_ui_element.name in (takeout_button.name, pickup_button.name):
            return CoffeePurchaseStep.SELECT_ADDRESS, UIStepStatus.WAIT_FOR_IMAGE
        else:
            return CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP, UIStepStatus.WAIT_FOR_IMAGE
    elif isinstance(the_action, AskAction):
        return CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP, UIStepStatus.WAIT_FOR_INFO
    elif isinstance(the_action, WaitAction):
        return CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP, UIStepStatus.WAIT_FOR_IMAGE
    else:
        return CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP, UIStepStatus.WAIT_FOR_IMAGE

class SelectTakeoutOrPickupStep(UIStepBase[CoffeePurchaseUIFlowState]):
    '''选择用餐方式步骤，只关注用餐方式信息'''

    def __init__(self):
        super().__init__(
            step=CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP,
            ui_task=UITask(
                page=PAGES[0],  # SELECT_TAKEOUT_OR_PICKUP 页面
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.WAIT, EUIAction.TYPE],
                note=[
                    "建议1：你不知道用户的用餐方式时，必须要先问用户他像如何用餐是自取还是外送。",
                ]
            ),
            action_map=_start_buy_coffee_map,
            middle_info_define=TakeoutOrPickupInfo,
            task_gen=lambda back_ground_info, info, actions_record: f"""你同时是一个资深咖啡博主，特别擅长操作瑞幸咖啡小程序帮用户找到明确的用餐方式来进行点咖啡。

以下是一些你在这个过程中可能需要用到的供你参考用的信息：
当前时间是:{back_ground_info}
{nl_repr(next(iter(info.values())))}

你之前执行过的操作动作记录（自上而下由旧到新）如下：
[
{"\n".join([str(action) for action in actions_record])}
]
""",
        )


def _select_address_map(actions: list[Action]) -> tuple[StepType, UIStepStatus]:
    """地址选择步骤的状态映射"""
    assert len(actions) == 1
    the_action = actions[0]
    
    if isinstance(the_action, ClickAction):
        # 如果点击了菜单搜索框，说明当前实际在菜单页（或地址页跳转到了菜单页），切换到商品选择步骤
        if the_action.target_ui_element and the_action.target_ui_element.name == menu_search_box.name:
            return CoffeePurchaseStep.SELECT_PRODUCT, UIStepStatus.WAIT_FOR_IMAGE
        # 如果点击了地址按钮，说明在地址页，选择地址后可能跳转到菜单页
        elif the_action.target_ui_element and the_action.target_ui_element.name == address_button.name:
            # 选择地址后，通常会跳转到菜单页，但这里先保持在地址步骤，等下次截图确认
            # 如果下次截图是菜单页，VLM 会点击菜单搜索框，然后切换到商品步骤
            return CoffeePurchaseStep.SELECT_PRODUCT, UIStepStatus.WAIT_FOR_IMAGE
        # 其他点击操作，继续在当前步骤
        return CoffeePurchaseStep.SELECT_ADDRESS, UIStepStatus.WAIT_FOR_IMAGE
    elif isinstance(the_action, AskAction):
        return CoffeePurchaseStep.SELECT_ADDRESS, UIStepStatus.WAIT_FOR_INFO
    elif isinstance(the_action, WaitAction):
        return CoffeePurchaseStep.SELECT_ADDRESS, UIStepStatus.WAIT_FOR_IMAGE
    return CoffeePurchaseStep.SELECT_ADDRESS, UIStepStatus.WAIT_FOR_IMAGE


class SelectAddressStep(UIStepBase[CoffeePurchaseUIFlowState]):
    '''选择地址步骤，只关注地址信息'''

    def __init__(self):
        super().__init__(
            step=CoffeePurchaseStep.SELECT_ADDRESS,
            ui_task=UITask(
                page=PAGES[1],  # SELECT_ADDRESS 页面
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.WAIT, EUIAction.TYPE],
                note=[
                    # "**重要：从首页点击后，可能直接跳到菜单页面。如果当前页面是菜单页（有商品列表、最下方栏目名为'菜单'），请点击菜单搜索框来进入商品选择步骤。**",
                    "建议1：首先判断当前页面是地址页还是菜单页。",
                    "建议2：如果是地址页，需要选择地址（自提选店铺地址，外卖选用户地址）。",
                    "建议3：如果是菜单页且是外送方式，需要去核对定位信息是否正确，即需要点击`定位信息入口`去选择地址。",
                    "建议4：一切的搜索框的使用，都是建立在所需信息满足的情况！如果没有信息,需要询问用户！",
                    "建议5：尽可能少的与用户交互，页面没找到地址时，或许可以通过`新增收货地址`新建地址。",
                    f"**重要规则：** 请自己看页面截图，当你点击左上角`自提|外送`字样下包含定位信息按钮时，target_ui_element 务必填写'{location_button.name}'！其他情况具体地址请务必填写'{address_button.name}'！", 
                ]
            ),
            action_map=_select_address_map,
            middle_info_define=AddressInfo,
            task_gen=lambda back_ground_info, info, actions_record: f"""你同时是一个资深咖啡博主，特别擅长操作瑞幸咖啡小程序帮用户选择地址来点咖啡。

以下是一些你在这个过程中可能需要用到的供你参考用的信息：
当前时间是:{back_ground_info}
{nl_repr(next(iter(info.values())))}

你之前执行过的操作动作记录（自上而下由旧到新）如下：
[
{"\n".join([str(action) for action in actions_record])}
]
""",
        )


def _select_product_map(actions: list[Action]) -> tuple[StepType, UIStepStatus]:
    """商品选择步骤的状态映射"""
    assert len(actions) == 1
    the_action = actions[0]
    
    if isinstance(the_action, ClickAction):
        # 如果点击了商品名按钮，进入商品规格选择步骤
        if the_action.target_ui_element and the_action.target_ui_element.name == product_button.name:
            return CoffeePurchaseStep.SELECT_SPEC, UIStepStatus.WAIT_FOR_IMAGE
        # 其他点击操作，继续在当前步骤
        return CoffeePurchaseStep.SELECT_PRODUCT, UIStepStatus.WAIT_FOR_IMAGE
    elif isinstance(the_action, AskAction):
        return CoffeePurchaseStep.SELECT_PRODUCT, UIStepStatus.WAIT_FOR_INFO
    elif isinstance(the_action, WaitAction):
        return CoffeePurchaseStep.SELECT_PRODUCT, UIStepStatus.WAIT_FOR_IMAGE
    return CoffeePurchaseStep.SELECT_PRODUCT, UIStepStatus.WAIT_FOR_IMAGE


class SelectProductStep(UIStepBase[CoffeePurchaseUIFlowState]):
    '''选择商品步骤，只关注商品名称'''

    def __init__(self):
        super().__init__(
            step=CoffeePurchaseStep.SELECT_PRODUCT,
            ui_task=UITask(
                page=PAGES[2],  # SELECT_PRODUCT 页面
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.WAIT, EUIAction.TYPE],
                note=[
                    "建议1：商品的选择优先去走当前页面的搜索框（放大镜形状），尽量不要直接在该页面滑动选品！",
                    "建议2：如果你看到当前视野里页面最下方栏目名是`菜单`的话，那么此时需要特别特别注意，一定要按照后面我说的来操作：在尝试输入关键字前，你一定要先看一下上文中提到的你之前执行过的操作动作记录，当且仅当前`2步`最新的动作是`点击``菜单页面的输入栏按钮`的动作和时，`点击``菜单页面的输入栏按钮`的动作后，你才能进行菜单搜索的Type输入操作。"
                    "建议3：优先使用菜单页面的搜索框来搜索商品名。如果图中直接展示了对应的商品，也可直接点击对应的商品名，而不是去点击搜索框",
                    "建议4：一切的搜索框的使用，都是建立在所需信息满足的情况！如果没有信息,需要询问用户！",
                    f"**重要规则：** 当你点击任何具体的商品（如'标准美式'、'拿铁'等）时，在 target_ui_element 中必须填写'{product_button.name}'，而不是具体的商品名称！这是框架的要求，必须严格遵守！",
                ]
            ),
            action_map=_select_product_map,
            middle_info_define=ProductName,  # 只关注商品名称
            task_gen=lambda back_ground_info, info, actions_record: f"""你同时是一个资深咖啡博主，特别擅长操作瑞幸咖啡小程序帮用户找到明确的商品名来进行点咖啡。

**重要：必须结合页面图像进行推理！**
- 当用户提到"第一个"、"第二个"等相对位置时，查看页面上的商品列表，找到对应位置的商品并直接点击
- 不要纯语言处理，必须基于图像信息操作

以下是一些你在这个过程中可能需要用到的供你参考用的信息：
当前时间是:{back_ground_info}
{nl_repr(next(iter(info.values())))}

你之前执行过的操作动作记录（自上而下由旧到新）如下：
[
{"\n".join([str(action) for action in actions_record])}
]
""",
        )

def _select_spec_map(actions: list[Action]) -> tuple[StepType, UIStepStatus]:
    """商品选择步骤的状态映射"""
    assert len(actions) == 1
    the_action = actions[0]
    
    if isinstance(the_action, ClickAction):
        # 如果点击了立即购买按钮，进入确认订单步骤
        if the_action.target_ui_element and the_action.target_ui_element.name == buy_now_button.name:
            return CoffeePurchaseStep.CONFIRM_ORDER, UIStepStatus.WAIT_FOR_IMAGE
        elif the_action.target_ui_element and the_action.target_ui_element.name == add_to_cart_button.name:
            return CoffeePurchaseStep.SELECT_PRODUCT, UIStepStatus.WAIT_FOR_IMAGE
        # 其他点击操作，继续在当前步骤
        return CoffeePurchaseStep.SELECT_SPEC, UIStepStatus.WAIT_FOR_IMAGE
    elif isinstance(the_action, AskAction):
        return CoffeePurchaseStep.SELECT_SPEC, UIStepStatus.WAIT_FOR_INFO
    elif isinstance(the_action, WaitAction):
        return CoffeePurchaseStep.SELECT_SPEC, UIStepStatus.WAIT_FOR_IMAGE
    return CoffeePurchaseStep.SELECT_SPEC, UIStepStatus.WAIT_FOR_IMAGE

    

class SelectSpecStep(UIStepBase[CoffeePurchaseUIFlowState]):
    '''选择商品属性步骤，只关注商品属性'''
    class EInfo(StrEnum):
        '''选择商品属性步骤的中间信息字段。'''
        CONFIRM_INTENT = "confirm_intent"
        PRODUCT_SPEC = "product_spec"

    @staticmethod
    def select_spec_task(back_ground_info: str, info: MiddleInfoType, actions_record: list[Action]) -> str:
        '''订座人信息页的任务生成函数。'''
        confirm_intent = info.get(SelectSpecStep.EInfo.CONFIRM_INTENT)
        
        # 如果 confirm_intent 为 None，设置默认值
        if confirm_intent is None:
            confirm_intent = ConfirmIntent(is_confirmed=None)
        
        assert isinstance(confirm_intent, (ConfirmIntent, str)), f"confirm_intent 必须是 ConfirmIntent or str 类型, but got {type(confirm_intent)}"
    
        task = f"""你同时是一个资深咖啡博主，特别擅长操作瑞幸咖啡小程序帮用户找到明确的商品属性来进行点咖啡。

以下是一些你在这个过程中可能需要用到的供你参考用的信息：
当前时间是:{back_ground_info}
所需信息:{nl_repr(info)}

你之前执行过的操作动作记录（自上而下由旧到新）如下：
[
{"\n".join([str(action) for action in actions_record])}
]
"""
        
        return task

    def __init__(self):
        super().__init__(
            step=CoffeePurchaseStep.SELECT_SPEC,
            ui_task=UITask(
                page=PAGES[3],  # SELECT_SPEC 页面
                action_set=[EUIAction.CLICK, EUIAction.ASK, EUIAction.WAIT, EUIAction.DRAG],
                note=[
                    "**重要：该页面不能返回！一般进入后且有动作后，不会出现未加载完成的情况！**",
                    "建议0：当前页面可能无法展示全部属性，或许可以通过拖拽一小段距离（不要太多）去查看更多的信息并总结至草稿纸中，确保没有更多信息时再做决策。",
                    "建议1：以页面图像中实际显示的属性选项为主，不要推测不存在的属性。如果用户提到了属性偏好，在页面中找到对应的选项并直接选择即可。最终找用户确认就行了。",
                    "建议2：如果草稿纸中部分属性能满足用户的需求，一定要先满足用户的需求，再询问用户是否需要修改其他属性。",
                    "建议3：如若满足了用户的所有需求，可直接`立即购买`去结账，不需要再交互询问用户是否确认了。",
                    # "建议3：只有在满足用户需求的前提下！才以自然、口语化，像朋友聊天一样告知用户（ask_human）已选择的规格，等待用户确认。例如：'好的，我帮你选了xxxx,你看这样可以吗？'",
                    # "满足用户的需求的之后，请重点关注操作动作记录最后一条是不是ask_human动作，如果用户确认意图为True，则是对该ask_human动作的content进行了确认，若表达的含义是去结账！则直接去结账！如果意图确认False，则需要继续询问确认其他属性信息。"


                ]
            ),
            action_map=_select_spec_map,
            middle_info_define={
                #暂时去掉，因为不确定是否需要确认交互。
                # SelectSpecStep.EInfo.CONFIRM_INTENT: ConfirmIntent, 
                SelectSpecStep.EInfo.PRODUCT_SPEC: Product_Spec,
            },
            task_gen=SelectSpecStep.select_spec_task,
        )


def _confirm_order_map(actions: list[Action]) -> tuple[StepType, UIStepStatus]:
    """确认订单步骤的状态映射"""
    assert len(actions) == 1
    the_action = actions[0]
    
    if isinstance(the_action, ClickAction):
        # 如果点击了确认订单按钮，进入确认订单步骤
        if the_action.target_ui_element and the_action.target_ui_element.name == confirm_order_button.name:
            # return _END_STEP, UIStepStatus.IDLE
            return CoffeePurchaseStep.CONFIRM_ORDER, UIStepStatus.WAIT_FOR_IMAGE
        elif the_action.target_ui_element and the_action.target_ui_element.name == qr_code_payment_button.name:
            return CoffeePurchaseStep.CONFIRM_ORDER, UIStepStatus.WAIT_FOR_IMAGE
            
        # 其他点击操作，继续在当前步骤
        return CoffeePurchaseStep.CONFIRM_ORDER, UIStepStatus.WAIT_FOR_IMAGE
    elif isinstance(the_action, FinishedAction):
        return _END_STEP, UIStepStatus.IDLE
    elif isinstance(the_action, WaitAction):
        return CoffeePurchaseStep.CONFIRM_ORDER, UIStepStatus.WAIT_FOR_IMAGE
    return CoffeePurchaseStep.CONFIRM_ORDER, UIStepStatus.WAIT_FOR_IMAGE


class ConfirmOrderStep(UIStepBase[CoffeePurchaseUIFlowState]):
    '''确认订单步骤，只关注确认订单'''

    @staticmethod
    def confirm_order_task(back_ground_info: str, info: MiddleInfoType, actions_record: list[Action]) -> str:
        '''确认订单页的任务生成函数。'''
        task = f"""你同时是一个资深咖啡博主，特别擅长操作瑞幸咖啡小程序帮用户完成支付操作。
直到最后看到二维码页面则用Finished结束任务让用户接手进一步的操作。
以下是一些你在这个过程中可能需要用到的供你参考用的信息：
当前时间是:{back_ground_info}
所需信息:{nl_repr(info) if info else "无"}

你之前执行过的操作动作记录（自上而下由旧到新）如下：
[
{"\n".join([str(action) for action in actions_record])}
]
"""
        
        return task

    def __init__(self):
        super().__init__(
            step=CoffeePurchaseStep.CONFIRM_ORDER,
            ui_task=UITask(
                page=PAGES[4],  # CONFIRM_ORDER 页面
                action_set=[EUIAction.CLICK, EUIAction.WAIT, EUIAction.FINISHED],
                note=[
                    "建议1：仔细观察页面以及动作记录！如果页面有`发送到手机微信支付`以及`二维码支付`字样的白色区域，则为弹窗，其他位置不可点！",
                    f"建议2：如果动作记录中最后一条为点击`{confirm_order_button.name}`按钮时，后续应重点关注图片中间区域点击`{qr_code_payment_button.name}`按钮，直到最终二维码支付页面出现，告知用户扫码支付",
                ]
            ),
            action_map=_confirm_order_map,
            middle_info_define=None,  # 只关注确认订单
            task_gen=ConfirmOrderStep.confirm_order_task,
        )


class CoffeePurchaseUiFlow(UIFlowBase[CoffeePurchaseUIFlowState]):
    def __init__(self):
        super().__init__(
            "瑞幸咖啡小程序的咖啡预定",
            CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP,
            {
                CoffeePurchaseStep.SELECT_TAKEOUT_OR_PICKUP: SelectTakeoutOrPickupStep(),
                CoffeePurchaseStep.SELECT_ADDRESS: SelectAddressStep(),
                CoffeePurchaseStep.SELECT_PRODUCT: SelectProductStep(),
                CoffeePurchaseStep.SELECT_SPEC: SelectSpecStep(),
                CoffeePurchaseStep.CONFIRM_ORDER: ConfirmOrderStep(),
            },
            state_cls=CoffeePurchaseUIFlowState,
            debug_mode=True,
        )
