'''UIAgent的基础数据结构。不同的workflow实现可以共享。'''

from enum import IntEnum, StrEnum
from typing import Callable, Final, Literal, Protocol

from pydantic import BaseModel, Field

from nanoai.model.vlm import AsyncOpenAI
from nanoai.model.vlm import avlm_output_by_schema
from nanoai.utils.data_concept import ClsResult, JudgeResult
from projects.uiagent.core.action import Action, UiElement

__all__ = [
    "EUIAction",
    "Page",
    "StepType",
    "UIRouter",
    "UIStepStatus",
    "UIResult",
    "WorkflowStatus",
]


class EUIAction(StrEnum):
    CLICK = "click(point='<point>x1 y1</point>', target_ui_element='') # 注意：x1,y1是0-1000取值范围的相对坐标。此外在填写target_ui_element时，如果你想点击的ui元素就是上文页面描述中直接提到的ui元素的名字，那么你要直接填写那边的ui元素的名字而不要自己编。如果你要点的ui元素没有特别提到从而让你不确定要点击的ui元素的名字，那么按照你自己的理解填一个名字。注意只是一个单纯的名字！不要填写写其他的无关的内容。"
    TYPE = "type(content='')"
    SCROLL = "scroll(point='<point>x1 y1</point>', direction='down or up or right or left') # 注意：x1,y1是0-1000取值范围的相对坐标。此外如果你不确定坐标的话，坐标默认x1=500, y1=500。"
    DRAG = "drag(start_point='<point>x1 y1</point>', end_point='<point>x2 y2</point>', target_ui_element='') # 注意：x1,y1,x2,y2是0-1000取值范围的相对坐标。此外在填写target_ui_element时，如果你想拖动的ui元素就是上文页面描述中直接提到的ui元素的名字，那么你要直接填写那边的ui元素的名字而不要自己编。如果你拖动的ui元素没有特别提到从而让你不确定要拖动的ui元素的名字，那么按照你自己的理解填一个名字。注意只是一个单纯的名字！不要填写写其他的无关的内容。"
    WAIT = "wait() # 注意：只有当前视野内你关心的程序处于加载中，未加载出来，空白等异常情况时才使用这个动作。"
    ASK = "ask_human(content='')"
    FINISHED = "finished(content='')"

NEW_ACTION_OUTPUT_INSTRUCTIONS = """
今天的日期是：{{date}}

你是 GUI Agent 的“执行决策器”。你将基于：用户任务 + 操作历史 + 当前屏幕状态（截图/结构化描述），输出“下一步唯一动作”。

【输出要求（AGP/1.0，最高优先级）】
你必须且只能输出 1 行结构化文本，禁止输出任何额外内容（包括空行、解释、注释、代码块标记）。
输出的第一个字符必须是 'A'，最后一个字符必须是可见字符（不能是空格/换行）。
在输出前，请在内部确认：该行可以被解析器严格解析。

【协议格式（单行）】
当下一步需要执行动作时（TYPE=do）：
AGP/1.0|TYPE=do|REASON=<string>|NAME=<action_name>|PARAMS=<params>

当任务结束时（TYPE=finish）：
AGP/1.0|TYPE=finish|REASON=<string>|STATUS=<success|partial|fail>|MESSAGE=<string>

【字段约束】
- TYPE：只能是 do 或 finish
- REASON：
  - 不超过 50 字
  - 只说明“当前动作的直接原因”
  - 不得复述规则，不得描述未来计划
- NAME：仅当 TYPE=do 时存在
- PARAMS：仅当 TYPE=do 时存在
- STATUS/MESSAGE：仅当 TYPE=finish 时存在

【NAME 取值（仅当 TYPE=do）】
launch|tap|input|swipe|long_press|wait|back|home|clarify|handoff|approve

【PARAMS 严格模板（由 NAME 唯一决定，禁止任何变体）】
你必须严格使用以下模板之一，禁止缺失字段、禁止新增字段、禁止替换分隔符、禁止输出 JSON。

1) launch
PARAMS=app=<string>

2) input
PARAMS=text=<string>

3) wait
PARAMS=duration_ms=<int>

4) clarify
PARAMS=question=<string>

5) approve
PARAMS=content=<string>

6) back
PARAMS=[]

7) home
PARAMS=[]

8) handoff
PARAMS=[]

【坐标类动作：一律使用数组位置参数（强约束）】
- 只允许标准数组形式：[...]
- 数组内只允许整数与逗号（禁止空值、禁止分号、禁止键值对）

9) tap
PARAMS=[x,y]
- 必须恰好 2 个整数
- x,y 范围：0-999
- 严禁输出：x=810;82、PARAMS=x=810;82、PARAMS={"x":...}、PARAMS=[810]、PARAMS=[810,] 等

10) swipe
PARAMS=[start_x,start_y,end_x,end_y]
- 必须恰好 4 个整数
- 坐标范围：0-999

11) long_press
PARAMS=[x,y,duration_ms]
- 必须恰好 3 个整数
- x,y 范围：0-999
- duration_ms：正整数（建议 300-1500）

【核心决策规则（按优先级）】
1) 若当前不在目标 App → 输出 launch
2) 页面明显未加载完成或无内容 → 输出 wait（800–1500ms）
3) 同一页面连续 wait ≥3 次无变化 → 输出 back
4) tap / swipe 连续无变化 ≥3 次 → 输出 back
5) 多候选且无法确定用户意图 → 输出 clarify（不得猜）
6) 涉及支付、发消息、下单、隐私、删除等不可逆或影响他人的操作 → 必须先输出 approve
7) 任务完成 → 输出 finish；若因页面不响应跳过步骤，STATUS=partial 并说明原因

【坐标选择要求】
- tap / long_press：点击可交互控件中心区域
- swipe 默认滚动：从 (500,800) 到 (500,200)；反向则交换起终点
- 避免连续点击同一坐标；若无效需小幅调整再试

【非法输出退化规则（必须遵守）】
- 若你无法 100% 保证本次输出能严格满足“单行协议格式 + NAME 对应 PARAMS 模板 + 数组长度/整数约束”：
  - 不得输出 tap/swipe/long_press 等坐标类动作
  - 必须改为输出 clarify / wait / back
- 宁可退化，不得输出不可解析或模板不匹配的内容

【输出前强制自检（必须执行）】
- 是否只输出 1 行（无任何多余字符）
- 是否以 "AGP/1.0|" 开头
- TYPE=do：是否同时包含 NAME 与 PARAMS
- TYPE=finish：是否同时包含 STATUS 与 MESSAGE
- 若 NAME=tap：PARAMS 是否严格为 [x,y] 且恰好 2 个整数
- 是否完全没有 JSON、没有分号参数串、没有缺 key/多 key

现在输出下一步动作对应的唯一一行协议。
"""

ACTION_OUTPUT_PROMPT_PLAIN = """
请严格按照以下格式回复:

Thought: ...
Action: $一个动作空间里的动作


同时，好好遵循以下指引，否则干死你。
   - 绝对不要自己编造任何动作空间不存在的动作，以及不存在的动作参数，参数一定要按照动作空间规定的格式填写，不要乱填；
   - 每一次只进行一个Action动作，绝对不可以多个；
   - 别去点右上角上角的刷新按钮，没加载好的话你就wait；
   - 你在需要使用坐标的操作图形界面的动作时，首先好好观察当前视野图像，然后精密计算出来你的动作执行的相对坐标（取值范围为0-1000的相对坐标。举例来说值为500时，相当于在某个维度的50.00%，即正中间处，<point>500 500</point>代表一个画面上位于横向从左往右50.00%，纵向从下往上50.00%处的点，此即相对坐标）；
   - 任何有坐标参数的动作，其坐标都给我统一成0-1000取值范围的相对坐标！!别让我在坐标参数里看到小数！！！
   - 回复的内容不要罗里吧嗦的，特别是Action: 后面的内容，必须是一个符合动作空间里的动作格式的内容！
   - 不要在Action: 后面填写任何非动作空间里的规定的动作内容以外的其他内容！！
"""

ACTION_OUTPUT_PROMPT_STRUCTURED = """请以json格式返回thought和action。"""


class Page(BaseModel):
    """一个UI页面的信息描述。不一定是一个页面对应一个Page，在很多时候可以实际上多个相似的页面对应一个Page。
    目前的name和description字段只能用于生成prompt。

    TODO: 更加结构化之后，可以用于记录页面标注数据。
    TODO: 如果足够详细, 例如, 包括了所有重要的ui元素,甚至可以取代page image?
    TODO: Page这个名字很可能过于general。将来可能要改的更具体。

    TODO: 这是个重要概念。是写graph的基础。目前还想不清楚怎么写。
    page和step的语义不同但密切相关。page是静态的内容描述（不太可能完全静态）, step是动态的执行任务步骤, 基于page的内容。
    同一个page上可能有多个step。它们可能是动态决定的。例如, 订座页面上各种“选人数”、“选时间”的动作会被click, scroll等穿插执行, 无法事先定义。
    """

    name: str = Field(description="页面名称")

    description: str = Field(description="页面描述")
    """除了用于生成完成任务的prompt, 还可以用于检查某个UI image是否符合页面描述。"""

    ui_elements: list[UiElement] = Field(
        default_factory=list, title="页面里可能有如下可操作的目标元素你可能用到：", description="页面上的目标元素列表")
    """ui_elements可以不提供为空。"""

    @property
    def ui_element_name_to_ui_element(self) -> dict[str, UiElement]:
        """将ui_elements列表转换为一个字典, 键为UiElement.name, 值为UiElement本身。用来parse action时使用以及其他场合使用。"""
        if len(self.ui_elements) > 0:
            return {UiElement.name: UiElement for UiElement in self.ui_elements}
        else:
            return {}

    def __nl_repr__(self) -> str:
        # if len(self.ui_elements) > 0:
        #     return f"{self.name}. {self.description}\n这个网页里可能有如下可操作的目标元素你可能用到:\n```\n{'\n\n'.join([nl_repr(UiElement) for UiElement in self.ui_elements])}\n```"
        # else:
        return f"{self.name}. {self.description}"


# StepType = NewType("StepType", str)  # 会导致大量不必要的从str或者StrEnum的类型转换。
StepType = str    # ui step有两种情况：UIRouter和UITask
# from enum import StrEnum
# StepType = StrEnum
# 特殊的终止步骤
_END_STEP: Final[StepType] = "uiflow end step"


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


class UIResult(BaseModel):
    '''基本等同于之前的UITaskResult。改名的好处, 除了保持命名一致之外, 数据格式和之前确实也有区别。'''
    raw_prompt: str = Field(
        title="原始提示", description="送给vlm模型的原始prompt", repr=False)

    thought: str = Field(title="思考", description="如何完成用户任务的思考")

    action_content: str = Field(title="动作描述", description="如何完成用户任务的动作描述")

    actions: list[Action] = Field(title="动作", description="如何完成用户任务的动作列表")

    source: Literal['rpa',
                    'ui-tars'] = Field(title="动作产生来源", description="动作产生来源")


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


MiddleInfoDefineType = dict[str, type[BaseModel]]
'''这里的key str，仅仅用于区分和索引不同的middle info类型。
TODO: 完全可以升级为更加复杂的类型，例如InfoTask。暂时先保持简单。
'''

MiddleInfoType = dict[str, BaseModel | str | None]
'''TODO: 这里的info类型BaseModel显然是过于局限的。需要增加对于动态类型的支持, 例如concept, attribute之类'''


def get_class_id(cls):
    assert isinstance(
        cls, type), f"cls {cls} must be a type, but got {type(cls)}"

    return f"{cls.__module__}.{cls.__qualname__}"


class PUIStep[S](Protocol):
    '''所有UI步骤的协议。
    S: 所有UIStep共享的状态, 目前的实现中, 就是UIFlow的state。
    为了减少耦合, UIStep不应该直接访问S, 而应该通过参数传递和返回, 如同arun的写法。
    将S传入arun是为了让UIStep操纵自定义的字段。因此, 不允许访问和修改UIFlowState中的字段。
    没有必要在代码中强行约束, 需要开发者理解和自觉遵守。
    '''

    def middle_info_def(self) -> MiddleInfoDefineType:
        """该Step所需要的中间信息。
        TODO: 用函数声明和返回不清楚好不好。
        """
        ...

    async def arun(
        self,
        image: str,
        image_format: str,
        xml: str | None,
        middle_info: MiddleInfoType,
        /,
        *,
        state: S,
        model: str,
        client: AsyncOpenAI
    ) -> tuple[UIResult | str, StepType, UIStepStatus]:
        """执行该Step的UI任务。"""
        ...


class UIRouter(BaseModel):
    """UIRouter根据当前UI页面image and xml, 判断其属于哪个step。"""

    categories: list[tuple[StepType, Page]] = Field(
        default_factory=list, title="页面名称和说明", description="待分类页面名称和说明")
    '''第一个元素是step, 用其对应到UITask, 第二个元素是页面说明, 用于理解以及基于vlm分类的prompt。'''

    router: Callable[[str, str | None], ClsResult] = Field(
        title="路由函数", description="根据image and xml, 确定其类别以及UITask。")

    def is_valid(self, cat: str) -> bool:
        '''验证上面返回的cls result.category是否在categories中。这也包含了其为unknown的情况。'''
        return cat in [c[0] for c in self.categories]

    def run(self, image: str, xml: str | None) -> tuple[ClsResult, UIStepStatus]:
        '''通用的router实现。
        status: 当前step的状态。
        image: 当前UI页面的image。
        xml: 当前UI页面的xml。
        返回值:
        ClsResult: 分类结果。
        UIStepStatus: rounter执行的状态。
        StepType | None: 成功则返回下一个step, 否则返回None。
        '''
        # TODO: 需要处理exception。
        cls_result = self.router(image, xml)

        if not cls_result.category in [c[0] for c in self.categories]:
            return cls_result, UIStepStatus.ERROR_UI_INVALID
        else:
            return cls_result, UIStepStatus.RUNNING


# TODO: 放在这个模块不合适，但暂时没还有更合适的位置
async def ui_task_eval(
    ui_task: str, image: str, image_format: str, thought: str, action: str, **kwargs
) -> JudgeResult:

    prompt = f"""你是一个手机应用的GUI agent评估专家. 
    
给定当前手机应用页面和用户任务, 详细描述如下,

{ui_task}

另外一个agent输出了如何完成任务的思考和动作, 如下, 

Thought: {thought}
Action: {action}

你需要判断上述的思考和动作是否能正确完成用户任务, 并给出理由和建议。 

请以json格式返回判断结果, 判断理由和建议。
"""

    res = await avlm_output_by_schema(prompt, image, image_format, output_type=JudgeResult, **kwargs)

    return res
