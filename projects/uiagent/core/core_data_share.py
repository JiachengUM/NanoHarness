from enum import StrEnum, IntEnum
from typing import Callable

from pydantic import BaseModel, Field


class ActionType(StrEnum):
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    ASK = "ask_human"
    FINISHED = "finished"


class ClickAction(BaseModel):
    name: ActionType = Field(
        default=ActionType.CLICK, title="动作类型名称", description="名称"
    )

    x: float = Field(
        title="x坐标", description="x坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )
    y: float = Field(
        title="y坐标", description="y坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )


class TypeAction(BaseModel):
    name: ActionType = Field(
        default=ActionType.TYPE, title="动作类型名称", description="名称"
    )

    content: str = Field(title="内容", description="内容")


class ScrollAction(BaseModel):
    name: ActionType = Field(
        default=ActionType.SCROLL, title="动作类型名称", description="名称"
    )

    x: float = Field(
        title="x坐标", description="x坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )
    y: float = Field(
        title="y坐标", description="y坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )
    dir: str = Field(title="方向", description="方向,可选值:down,up,right,left")


class AskAction(BaseModel):
    name: ActionType = Field(
        default=ActionType.ASK, title="动作类型名称", description="名称"
    )

    content: str = Field(title="智能体反问用户或向用户反馈的信息。", description="内容")


class FinishedAction(BaseModel):
    name: ActionType = Field(
        default=ActionType.FINISHED, title="动作类型名称", description="名称"
    )
    content: str = Field(title="完成任务时需要反馈给用户的信息。", description="内容")


Action = ClickAction | TypeAction | ScrollAction | AskAction | FinishedAction


class EUIAction(StrEnum):
    CLICK = "click(point='<point>x1 y1</point>')"
    TYPE = "type(content='')"
    SCROLL = "scroll(point='<point>x1 y1</point>', direction='down or up or right or left')"
    ASK = "ask_human(content='')"
    FINISHED = "finished(content='xxx')"


class Page(BaseModel):
    """一个UI页面的信息描述。
    目前的name和description字段只能用于生成prompt。

    TODO: 这是个重要概念。是写graph的基础。目前还想不清楚怎么写。
    page和step的语义不同但密切相关。page是静态的内容描述（不太可能完全静态）, step是动态的执行任务步骤, 基于page的内容。
    同一个page上可能有多个step。它们可能是动态决定的。例如, 订座页面上各种“选人数”、“选时间”的动作会被click, scroll等穿插执行, 无法事先定义。
    """

    name: str = Field(description="页面名称")

    description: str = Field(description="页面描述")
    """除了用于生成完成任务的prompt, 还可以用于检查某个UI image是否符合页面描述。"""


InfoValidator = Callable[[BaseModel | str | None], bool]

class InfoExecMode(StrEnum):
    """信息提取任务的执行模式。"""

    NL_ANY = "通过nl随时提取"
    """用户可以随时提供的信息, 如：几个人订座，缴费的车牌号等。
    本质上, 这是“静态全局”信息提取任务。 InfoTask自身就可以向用户请求信息和提问, 不需要更多上下文。
    """

    NEED_UI_IMAGE = "基于特定的UI页面才能提取"
    """例如, 缴费页面显示出缴费金额，智能体问用户 请确认金额并缴费。
    本质上, 这是"动态局部"信息提取任务。InfoTask自身无法向用户提问, 需要UI图像才知道怎么提问。
    TODO: 需要调用vlm, 还没实现，但应该简单。
    """


class InfoTask(BaseModel):
    """InfoTask定义了单步信息提取任务。"""

    brief: str = Field(title="任务描述", description="任务描述")

    info_type: type[BaseModel] = Field(title="信息类型", description="信息类型")


    exec_mode: InfoExecMode = Field(default=InfoExecMode.NL_ANY, title="执行模式", description="执行模式", repr=False)
    """repr=False, 不进入prompt。"""


class UIStepStatus(IntEnum):
    '''关于UIRouter和UITask共享的状态定义.
    初始时为IDLE。
    
    被设置为当前step时成为WAIT_FOR_IMAGE状态。

    UIRounter执行时进入RUNNING状态。执行成功后, 跳转到的UITask状态为WAIT_FOR_INFO, 而不是WAIT_FOR_IMAGE。
    
    UITask如果依赖于middle info, 执行中会检查, 如果不满足, 处于WAIT_FOR_INFO状态。
    
    检查通过后进入RUNNING状态。 
    
    TODO: 是否需要FAIL, ERROR等状态还不清楚。
    '''
    IDLE = 0
    '''初始状态。相当于inactive, sleep'''

    WAIT_FOR_IMAGE = 100
    '''等待UI Image。从router跳转到ui task时，不应该是wait for image，而是wait for info'''

    ERROR_UI_INVALID = 101
    """输入的ui image/xml不正确。只对于UIRouter有效。"""

    WAIT_FOR_INFO = 200
    '''等待Middle Info。只对于UITask有效'''

    RUNNING = 300
    '''等待Middle Info。'''


class UITaskResult(BaseModel):
    '''UITask的vlm执行结果。    '''

    raw_prompt: str = Field(title="原始提示", description="送给vlm模型的原始prompt", repr=False)

    thought: str = Field(title="思考", description="如何完成用户任务的思考")

    action_content: str = Field(title="动作描述", description="如何完成用户任务的动作描述")
    
    actions: list[Action] = Field(title="动作", description="如何完成用户任务的动作列表")


class UITask(BaseModel):
    """
    UITask定义了单步UI任务。通常调用vlm完成。它需要两类输入数据：
    - 页面：这是vlm的image输入。它来自workflow的state.image，更源头来自于run_ui的输入。
    - 数据参数：这是vlm的prompt输入，如车牌号，店名，时间，人数等。它来自于workflow state的各种数据成员，更源头来自于InfoTask。
    它输出action_set中的一个或多个动作。
    workflow run_ui只能按照设计好的顺序执行当前UI任务。多个UI任务不能并行。这是它和InfoTask的本质区别。
    """

    page: str | Page = Field(title="应用程序当前页面描述", description="当前应用页面的描述")
    """同时支持string和Page类型。是否有必要统一约束为Page类型, 取决于Page的实现是否有必要足够复杂。TODO。"""

    info_task: InfoTask | None = Field(default=None, title="信息提取任务", description="信息提取任务", repr=False)
    """该信息提取任务的输出作为UITask的输入。注意它并不进入prompt, repr=False。
    TODO: 有可能需要多个info_task.
    """

    task_template: str | None = Field(default=None, title="任务描述模板", description="任务描述模板", repr=False)
    """如果info_task不为None，则task_template需要被一个info param来format，并生成task。参见as_prompt的实现。
    注意task_template并不进入prompt, repr=False。
    """

    task: str = Field(default="", title="任务描述", description="任务描述")
    """如果info_task不为None，则task需要被task_template来实例化。初始必须为空。
    注意task和task_template并不对称。最终进入prompt的永远是task。
    """

    action_set: list[str] = Field(
        default=[EUIAction.CLICK, EUIAction.TYPE, EUIAction.SCROLL, EUIAction.ASK],
        title="动作空间",
        description="动作空间",
    )
    """通常需要根据不同的Page定制化。参见demo_task/workflow.py中的实现。"""

    note: list[str] | None = Field(default=None, title="注意事项", description="注意事项")
    """这个字段非必要不要使用。重要信息尽量放到上面的字段中。"""


class WorkflowStatus(IntEnum):
    """UIAgent工作流的粗粒度的状态定义。
    TODO: 是否够用还不是很确定，也许还需要增加START, WAIT_FOR_UI, WAIT_FOR_NL等状态。
    """

    SUCCESS = 0
    """成功完成任务。结束对话。"""

    RUNNING = 1000
    """任务执行中。初始状态。它的子状态就是current ui task的状态。也需要对外部返回"""

    ERROR = 2000
    """执行任务时发生错误。通常有多种错误状态。细致的定义由智能体自行决定。"""

    ERROR_INTENT = 2001
    """意图识别失败。"""

    FAIL = 3000
    """任务失败(例如超过预设对话轮数)。结束对话。"""

    USER_ABORT = 3001
    """用户主动退出任务。失败的一种特殊情况。"""

StepType = str

class WorkflowState(BaseModel):
    """工作流的状态。    """

    task: str = Field(title="工作流任务", description="工作流任务的整体描述")
    """这是对话功能的基础。例如, 帮助用户选择餐厅和订座，需要询问相关信息并确认。没有缺省值。
    TODO: 应该会有很多需要定制化的地方。怎么写还不清楚。"""

    status: WorkflowStatus = Field(default=WorkflowStatus.RUNNING, title="工作流的状态", description="工作流的状态")
    """粗粒度的status"""

    @property
    def terminated(self) -> bool:
        return self.status != WorkflowStatus.RUNNING

    current_step: StepType = Field(title="当前UI步骤", description="当前UI步骤")
    '''不能有缺省值, 赋值时必须给step_status设为WAIT_FOR_IMAGE。step可能是UIRouter或者UITask。
    '''

    step_status: dict[StepType, UIStepStatus] = Field(default_factory=dict, title="UIRouter和UITask的状态", description="UIRouter和UITask的状态")
    ''' 任意时刻, 要么只有一个rounter or ui task为WAIT_FOR_IMAGE, 要么只有一个ui task为WAIT_FOR_INFO（此时没有WAIT_FOR_IMAGE）。 
    TODO: 检查有效性'''

    image: str | None = Field(default=None, title="当前页面截图", description="当前页面截图", repr=False)

    image_format: str | None = Field(default=None, title="当前页面截图格式", description="当前页面截图格式", repr=False)
    
    xml: str | None = Field(default=None, title="当前页面XML", description="当前页面XML", repr=False)
    """它们共同描述了当前UI页面。xml不总是有值。如果有，尝试用rpa方案，而不是vlm方案。"""

    nl_query: str | None = Field(default=None, title="当前NL查询", description="当前NL查询")
    """用户最近的query, 因为可能用于多个nl task, 需要缓存在这里共享, 供_run_nl使用。
    TODO: 现在的写法肯定是有问题的。因为这个query必须以某种方式进入nl_messages，才能持续调用run_nl()。目前还做不到。
    """

    nl_messages: list = Field(default_factory=list, description="消息历史", init=False)
    """用于run_nl的对话历史。"""

    # TODO: 需要统一管理MiddleInfo数据。它们是InfoTask的输出，UITask的输入。
    middle_info: dict[str, BaseModel | str | None] = Field(default_factory=dict, title="中间信息", description="中间信息")
    """可能是state里最重要的字段。初始化时可以传入。没有必要init=False。
    key: InfoTask name, value: InfoTask提取得到的信息。value type可以是BaseModel也可以是nl str。
    前者在run_nl中做提槽时方便一些，但语义上其实就是个str。无需提槽时可以直接用str，例如：1）测试时送入的query都是事先写好的。
    如果允许info为str, 那就无法做基于hard code的检查。但还是可以用vlm做动态的检查, 并返回ask human。
    """

class UIAgentError(Exception):
    pass


class WorkflowResult[S: WorkflowState](BaseModel):
    '''这是智能体对外的输出。除了state, 其它成员都有缺省值。'''

    results: list[UITaskResult | str] | None = Field(default=None, title="workflow执行结果", description="workflow执行结果")
    """UIRunResult表示执行UI动作, str表示给用户的回复, 可能是需要他的回复（ask human），也可能只是告诉他发生了什么（这是个产品体验设计的问题）。
    None表示执行失败，没有结果。在正常情况下（排除无法处理的情况，参见run_nl, run_ui中的异常处理部分），不允许为空，也就是，哪怕ui task无法执行，也需要告诉用户发生了什么。
    虽然是list，但最多只包括一个UITaskResult，一个str。前端依次执行即可。
    TODO: 将来可能扩充为能输出多个str，非常取决于具体情况。
    """

    error: UIAgentError | None = Field(default=None, title="错误信息", description="错误信息", exclude=True)
    """执行失败时才有值。无法序列化, 因此exclude=True"""
    
    state: S = Field(..., title="workflow状态", description="workflow状态")
    """智能体的内部状态。没有必要完全对外暴露，但对于前端debug很重要。怎么用取决于前端。"""
