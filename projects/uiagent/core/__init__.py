import copy
import traceback
import asyncio
from enum import Enum, StrEnum
from functools import cached_property
from typing import Any, Awaitable, Callable, Self, final

from pydantic import BaseModel, Field, model_validator, ConfigDict

from nanoai.model.config import AsyncOpenAI, ModelName, create_client
from nanoai.model.llm import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    allm_output,
)
from nanoai.model.vlm import avlm
from nanoai.utils.data_concept import JudgeResult
from nanoai.utils.nl_repr import nl_repr

from projects.uiagent.core.action import Action, norm_actions, parse_action
from projects.uiagent.core.error import UIAgentError, UIAgentIntentError, UIAgentInfoTaskError
from projects.uiagent.core.flow_data import (
    EUIAction,
    ACTION_OUTPUT_PROMPT_PLAIN,
    WorkflowStatus, 
    StepType,
    Page,
    UIStepStatus,
    UIRouter,
    ui_task_eval,
)

from projects.uiagent.utils.chat_agent import ChatAgentProfile
from projects.uiagent.utils.common_task import IntentClsResult
from projects.uiagent.utils.image_utils import get_image_dimensions
from projects.uiagent.utils.utils import parse_thought_and_action_content

__all__ = [
    "UITask",
    "UITaskResult",
    "WorkflowBase",
    "WorkflowStatus",
    "WorkflowState",
    "InfoTask",
    "UIHandler",
    "RPAHandler",
]


# 默认的 LLM 参数配置，禁用 thinking 模式
DEFAULT_LLM_PARAMS: dict[str, Any] = {
    "extra_body": {
        "thinking": {
            "type": "disabled",
        }
    },
}


class IntentCategory(Enum):
    RELEVANT = ("Relevant", "用户输入和对话任务明显相关，意图清楚。")
    IRRELEVANT = ("Irrelevant", "用户输入和对话任务明显无关, 或者十分含糊。")
    ABORT = ("Abort", '用户明确表示想放弃任务, 例如"请退出"、"再见"等。')


class ActionSource(StrEnum):
    RPA = "rpa"
    UI = "ui-tars"

# class Page(BaseModel):
#     """一个UI页面的信息描述。
#     目前的name和description字段只能用于生成prompt。

#     TODO: 更加结构化之后，可以用于记录页面标注数据。
#     TODO: 如果足够详细, 例如, 包括了所有重要的ui元素,甚至可以取代page image?
#     TODO: Page这个名字很可能过于general。将来可能要改的更具体。

#     TODO: 这是个重要概念。是写graph的基础。目前还想不清楚怎么写。
#     page和step的语义不同但密切相关。page是静态的内容描述（不太可能完全静态）, step是动态的执行任务步骤, 基于page的内容。
#     同一个page上可能有多个step。它们可能是动态决定的。例如, 订座页面上各种“选人数”、“选时间”的动作会被click, scroll等穿插执行, 无法事先定义。
#     """

#     name: str = Field(description="页面名称")

#     description: str = Field(description="页面描述")
#     """除了用于生成完成任务的prompt, 还可以用于检查某个UI image是否符合页面描述。"""

#     def __nl_repr__(self) -> str:
#         return f"{self.name}. {self.description}"

def _replace_sys_prompt(
    messages: list[ChatCompletionMessageParam], sys_prompt: str
) -> list[ChatCompletionMessageParam]:
    """替换消息历史中的第一条sys_prompt并返回。"""

    assert messages[0]["role"] == "system", "messages的第一个消息必须是system消息"
    if len(messages) > 1:
        messages = copy.deepcopy(messages[1:])  # 去掉sys_prompt
    else:
        messages = []

    messages.insert(0, ChatCompletionSystemMessageParam(role="system", content=sys_prompt))

    return messages


async def intent_classify(
    input: str,
    messages: list[ChatCompletionMessageParam],
    categories: list[tuple[str, str]] = [intent.value for intent in IntentCategory],
    /,
    *,
    task: Any,
    model: str,
    client: AsyncOpenAI,
    timeout: float | None = None,
    **kwargs,
) -> IntentClsResult:
    """
    不会直接修改messages。内部会改写sys prompt并复制messages。
    TODO: 应该可以和intent_classify中的intent_classify统一, 但不着急
    """

    sys_prompt = f"""你是一个UIAgent对话助手。你需要判断用户的意图。
当前任务为: {nl_repr(task)}

各种用户意图类别的名称和描述如下:
{"\n".join([f"{name}: {description}" for name, description in categories])}

{IntentClsResult.output_prompt()}
"""
    messages = _replace_sys_prompt(messages, sys_prompt)

    # 合并默认参数和用户传入的参数
    merged_kwargs = {**DEFAULT_LLM_PARAMS, **kwargs}

    res = await allm_output(
        input,
        messages,
        output_type=IntentClsResult,
        client=client,
        model=model,
        timeout=timeout,
        **merged_kwargs,
    )

    category = res.output.category

    assert category in [cat[0] for cat in categories], f"意图分类结果:{category}, 不在类别列表中:{categories}"

    return res.output


# TODO: 有个关于架构的大问题。
# 如果要一个llm call同时输出intent, reason和info type, 那么info type必须动态确定。这很难写, 似乎必须引入Concept。不清楚怎么做。
# 另外一种方式是, 将intent cls任务和info任务分开, 并行执行。这样更简单。准确的说, 如果只有一个global intent cls任务, 会很简单。
# 但如果每个InfoTask都需要自己单独的intent cls, 还是很麻烦。这是有可能的。例如, 用户已经进入了选品页面, 又说“要回去选店”。
# 目前先采取最简单的, 一个global intent cls任务的写法。

# input: middle info, output: whether it is valid
InfoValidator = Callable[[BaseModel | str | None], JudgeResult]


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
    """InfoTask定义了单步信息提取任务。
    它调用llm(_output)完成。它输入str，输出结构化的数据进入workflow state。
    同一个workflow run_nl可以并行调用多个InfoTask。
    TODO: 现在的写法还不支持nl_repr的用法。
    """

    brief: str = Field(title="任务描述", description="任务描述")
    """TODO: 暂时还没真的用上。以后应该有用。"""

    info_type: type[BaseModel] = Field(title="信息类型", description="信息类型")

    validator: InfoValidator | None = Field(default=None, title="信息验证器", description="验证信息是否符合要求")

    exec_mode: InfoExecMode = Field(default=InfoExecMode.NL_ANY, title="执行模式", description="执行模式", repr=False)
    """repr=False, 不进入prompt。"""

    # frozen时，BaseModel会自动处理哈希和相等性
    model_config = {"frozen": True}

    @property
    def _sys_prompt(self) -> str:
        """可以继承InfoTask并重载_sys_prompt。很可能需要"""

        return f"""你是一个UIAgent信息搜集助手。
请从对话信息中提取以下信息:
{nl_repr(self.info_type)}
请以json格式返回。
"""

    # def _is_all_basemodel_fields(self) -> dict[str, type[BaseModel]] | None:
    #     """检查 info_type 的所有字段是否都是 BaseModel 类型。是则返回字段映射，否则返回 None。"""
    #     import inspect
    #     field_types: dict[str, type[BaseModel]] = {}
    #     for field_name, field_info in self.info_type.model_fields.items():
    #         field_type = field_info.annotation
    #         if not (inspect.isclass(field_type) and issubclass(field_type, BaseModel)):
    #             return None
    #         field_types[field_name] = field_type
    #     return field_types if field_types else None

    # 目前的逻辑是通用的, 不允许重载。
    @final
    async def arun(
        self,
        query: str,
        messages: list[ChatCompletionMessageParam],
        /,
        *,
        model: str,
        client: AsyncOpenAI,
        **kwargs,
    ) -> BaseModel:
        """
        messages: 来自于workflow的nl_messages。包括sys_prompt。
        如果 info_type 的所有字段都是 BaseModel，则自动并行提取以降低延迟。
        **kwargs: 额外的参数，会传递给 allm_output，例如 extra_body 用于控制 thinking 模式。
        """
        #field_types = self._is_all_basemodel_fields()

#         # 字段全是 BaseModel → 并行提取
#         if field_types:
#             async def extract_field(field_name: str, field_type: type[BaseModel]) -> tuple[str, BaseModel]:
#                 sys_prompt = f"""你是一个UIAgent信息搜集助手。
# 请从对话信息中仅提取以下信息:
# {nl_repr(field_type)}
# 请以json格式返回。"""
#                 field_messages = _replace_sys_prompt(messages, sys_prompt)
#                 result = await allm_output(query, field_messages, output_type=field_type, model=model, client=client, **kwargs)
#                 return field_name, result.output

#             coros = [extract_field(name, ftype) for name, ftype in field_types.items()]
#             results = await asyncio.gather(*coros, return_exceptions=True)

#             field_values: dict[str, BaseModel] = {}
#             for result in results:
#                 if isinstance(result, Exception):
#                     raise UIAgentInfoTaskError(self.brief, query, f"并行提取失败: {result}")
#                 field_name, value = result
#                 field_values[field_name] = value

#             return self.info_type(**field_values)
#         # 否则 → 原来的串行方式
#         else:
        messages = _replace_sys_prompt(messages, self._sys_prompt)
        # 合并默认参数和用户传入的参数
        merged_kwargs = {**DEFAULT_LLM_PARAMS, **kwargs}
        result = await allm_output(query, messages, output_type=self.info_type, model=model, client=client, **merged_kwargs)
        return result.output


class UITaskResult(BaseModel):
    '''UITask的执行结果。'''

    raw_prompt: str = Field(title="原始提示", description="送给vlm模型的原始prompt", repr=False)

    thought: str = Field(title="思考", description="如何完成用户任务的思考")

    action_content: str = Field(title="动作描述", description="如何完成用户任务的动作描述")
    
    actions: list[Action] = Field(title="动作", description="如何完成用户任务的动作列表")

    source:  ActionSource = Field(default=ActionSource.UI, title="动作产生来源", description="表明actions产生的来源")

class UITask(BaseModel):
    """
    UITask定义了单步UI任务。通常调用vlm完成。它需要两类输入数据：
    - 页面：这是vlm的image输入。它来自workflow的state.image，更源头来自于run_ui的输入。
    - 数据参数：这是vlm的prompt输入，如车牌号，店名，时间，人数等。它来自于workflow state的各种数据成员，更源头来自于InfoTask。
    它输出action_set中的一个或多个动作。
    workflow run_ui只能按照设计好的顺序执行当前UI任务。多个UI任务不能并行。这是它和InfoTask的本质区别。
    TODO: 用RPA和xml来执行的也算UITask。它也需要这里的部分字段: info_task, action_set, 没准还有page。暂时共同UITask。
    将来也许需要提取出 RPATask （作为UITask的base），单独供rpa handler使用。
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

    @model_validator(mode="after")
    def validate_task(self) -> Self:
        """task和task_template只能取其一。"""
        if self.task_template is not None:
            assert self.task == "", "task must be empty when info_task is not None"
            assert self.info_task is not None
        else:
            assert self.info_task is None, "info_task must be None when task_template is None"
            assert self.task != "", "task must not be empty when template_task is None"

        return self

    def as_prompt(
        self, info: BaseModel | str | None = None, format_instruction: str = ACTION_OUTPUT_PROMPT_PLAIN
    ) -> str:
        """info没必要一定是BaseModel。str有时候更方便。
        TODO: format_instruction需要结构化。
        """

        if info is not None:
            assert isinstance(info, (BaseModel, str)), "info must be a BaseModel or str"
            assert self.info_task is not None, "info_task must not be None when info is not None"
            assert (
                self.task_template is not None
            ), "task_template must not be None when info is not None"
            self.task = self.task_template.format(info=nl_repr(info))
        else:
            assert self.info_task is None, "info_task must be None when info is None"
            assert self.task_template is None, "task_template must be None when info is None"
            assert self.task != "", "task must not be empty when info is None"

        # 虽然task和task_template只能二选一，但这里的nl_repr并没有问题。永远是task在起作用。
        return f"""你是一个手机应用的GUI agent. 给定当前手机应用页面的screenshot, 你需要在页面上执行相应的动作来完成用户任务. 以下是详细描述。
{nl_repr(self)}

{format_instruction}
"""

    async def arun(
        self, 
        image: str, 
        image_format: str, 
        info: BaseModel | str | None = None,
        *,
        model: str,
        client: AsyncOpenAI,
        ) -> tuple[UITaskResult, str]:

        prompt = self.as_prompt(info)
        # 使用默认参数禁用 thinking 模式
        response = await avlm(prompt, image, image_format, client=client, model=model, **DEFAULT_LLM_PARAMS)
        thought, action_content = parse_thought_and_action_content(response)
        actions = parse_action(action_content)
        

        # TODO: 应该没有必要。删掉。
        width, height = get_image_dimensions(image)
        actions = norm_actions(actions, width, height)

        result = UITaskResult(
            raw_prompt=prompt,
            thought=thought,
            action_content=action_content,
            actions=actions,
        )
        
        return result, prompt


class WorkflowState(BaseModel):
    """工作流的状态。
    TODO: 由于初始化十分困难，目前几乎所有字段都有缺省值。
    真正的构造发生在workflow.__init__()。
    """

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
    TODO: 不允许显式的赋值。
    '''

    def set_step(self, step: StepType, step_status: UIStepStatus | None = UIStepStatus.WAIT_FOR_IMAGE) -> None:
        self.current_step = step
        self.step_status[step] = step_status if step_status else UIStepStatus.WAIT_FOR_IMAGE

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

    nl_messages: list[ChatCompletionMessageParam] = Field(default_factory=list, title="消息历史", description="消息历史", init=False)
    """用于run_nl的对话历史。不为空。第一条永远是sys prompt."""

    intent_cls_res: IntentClsResult | None = Field(default=None, title="用户意图分类结果", description="用户意图分类结果")
    """意图分类结果。None表示分类失败。
    TODO: 还不确定要放在State中还是WorkflowResult。似乎State更合适。
    """

    def update_nl_sys_prompt(self, sys_prompt: str) -> None:
        """更新nl_messages的第一个消息为system消息。供workflow状态改变时调用"""
        assert len(self.nl_messages) > 0, "nl_messages不能为空"
        assert self.nl_messages[0]["role"] == "system", "result的第一个消息必须是system消息"
        self.nl_messages[0] = {"role": "system", "content": sys_prompt}

    def update_nl_messages(self, assistant_content: str) -> None:
        """记录一轮对话"""
        assert isinstance(self.nl_query, str), "nl_query必须是str"
        self.nl_messages.append({"role": "user", "content": self.nl_query})
        self.nl_messages.append({"role": "assistant", "content": assistant_content})
        self.nl_query = None  # 已经处理过了，语义上不再存在


    # TODO: 增加ui_messages字段，用于run_ui的对话历史。它和nl_messages的关系还没想清楚。

    # TODO: 需要统一管理MiddleInfo数据。它们是InfoTask的输出，UITask的输入。
    middle_info: dict[str, BaseModel | str | None] = Field(default_factory=dict, title="中间信息", description="中间信息")
    """可能是state里最重要的字段。初始化时可以传入。没有必要init=False。
    key: InfoTask name。注意这和StepType不同。不同的UIStep可能共享同样的InfoTask。
    value: InfoTask提取得到的信息。type可以是BaseModel也可以是nl str。
    前者在run_nl中做提槽时方便一些，但语义上其实就是个str。无需提槽时可以直接用str，例如：1）测试时送入的query都是事先写好的。
    如果允许info为str, 那就无法做基于hard code的检查。但还是可以用vlm做动态的检查, 并返回ask human。
    TODO: 真的需要这种灵活性么？不确定。架构上先支持吧。
    TODO: key一旦初始化后，不能修改。如何确保？目前在workflow._check_state()中检查。
    TODO: 如何管理这些数据，还有很多不清楚的地方。
    TODO: 可能需要引入缺省值的概念（middle_info_default）。例如，停车时的缺省车牌号。这个有可能太复杂了。
    """

    eval_res: JudgeResult | None = Field(default=None, title="评估结果", description="评估结果")
    """enable_reflect为True时有值。
    TODO: 应该挪到WorkflowResult中。目前还不方便，因为要通过_run_ui_step_by_model返回，改动太大。
    """


    def _check(self) -> None:
        """检查state的合法性。有些约束是无法在对象创建时检查的。"""
        assert len(self.nl_messages) > 0, "nl_messages不能为空"

        assert self.nl_messages[0]["role"] == "system", "nl_messages的第一个消息必须是system消息"


class WorkflowResult[S: WorkflowState](BaseModel):
    '''这是智能体对外的输出。除了state, 其它成员都有缺省值。'''

    model_config = ConfigDict(arbitrary_types_allowed=True)  # 为了支持Exception

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

    @model_validator(mode="after")
    def validate(self) -> Self:

        if self.results is not None:
            assert self.error is None, "results和error有且只有一个有值"
        else:
            assert self.error is not None, "results和error有且只有一个有值"
            # assert self.eval_res is None, "results为None时, eval_res必须为None"

        return self


# TODO: input: image and image format, 需要扩充返回值，支持ask human
UIHandler = Callable[[str, str], Awaitable[UITaskResult]]

# input: xml, output: actions
# TODO: 有可能需要和 RPATask 关联起来。例如，通过其中的page来定制化实现，通过info_task拿到输入，通过其action_set来检验输出的actions。
# TODO: 增加InfoType = BaseModel | str | None
RPAHandler = Callable[[BaseModel | str | None, str], tuple[list[Action], StepType, UIStepStatus | None]]

class WorkflowBase[S: WorkflowState]:
    """
    WorkflowBase是所有workflow的基类, 功能说明如下:
    S: 状态类型。必须是WorkflowState的子类。

    TODO: pages: 所有的页面描述。
    ui_tasks: 所有的单步UI任务。注意它和page不是一一对应的。一个page可能对应多个ui task，但必须顺序执行。
    架构设计参见 https://pq3b44yw2t9.feishu.cn/wiki/FiI6w6Zu0iHdCikzQRGciC5tnyh
    """

    def __init__(
        self,
        task: str,
        start_step: StepType,
        ui_tasks: dict[StepType, UITask],
        ui_handlers: dict[StepType, UIHandler],
        /,
        *,
        intent_categories: list[tuple[str, str]] = [intent.value for intent in IntentCategory],
        rpa_handlers: dict[StepType, RPAHandler] | None = None,
        ui_routers: dict[StepType, UIRouter] | None = None,
        enable_reflect: bool = False,
        state_cls: type[S] = WorkflowState,
        agent_name: str = "UI Agent对话助手",
        debug_mode: bool = False,
    ):
        '''
        最简单情况下, rpa_handlers和ui_routers都不是必须的。
        TODO: ui_handlers也可以消灭。然后就成为了通用的workflow。
        '''
        # workflow graph
        # TODO: ui_tasks跟ui_handlers, rpa_handlers可以写在一起:
        # dict[StepType, tuple[UITask, UIHandler | None, RPAHandler | None]]

        assert isinstance(ui_tasks, dict), f"ui_tasks must be a dict, but got {type(ui_tasks)}"
        self.ui_tasks = ui_tasks

        assert isinstance(ui_handlers, dict), f"ui_handlers must be a dict, but got {type(ui_handlers)}"
        self.ui_handlers = ui_handlers

        assert (isinstance(rpa_handlers, dict) or rpa_handlers is None), f"rpa_handlers must be a dict or None, but got {type(rpa_handlers)}"
        self.rpa_handlers = rpa_handlers or {}

        assert isinstance(ui_routers, dict) or ui_routers is None, f"ui_routers must be a dict or None, but got {type(ui_routers)}"
        self.ui_routers = ui_routers or {}
        # TODO: 检查ui_routers的输出都在ui_tasks的step中。

        assert start_step in self.ui_tasks.keys() or start_step in self.ui_routers.keys(), f"start_step {start_step} 不在 ui_tasks 或 ui_routers 中"

        # 算法参数
        self.client, self.model = create_client(ModelName.DOUBAO_1_5_UI_TARS_250428, AsyncOpenAI)

        self.model_vision = ModelName.DOUBAO_SEED_1_6_VISION_250815

        self.model_llm = ModelName.DOUBAO_SEED_1_6_FLASH_250828  # 缺省的语言模型

        self.enable_reflect = enable_reflect

        self.debug_mode = debug_mode

        self.intent_categories = intent_categories

        # chat部分
        self.chat_agent_profile = ChatAgentProfile(name=agent_name)

        # 状态
        assert issubclass(state_cls, WorkflowState), f"state_cls must be WorkflowState的子类, but got {type(state_cls)}"
        self.state_cls = state_cls

        # 初始化middle_info为空。它依赖于ui_tasks。不能外部传入。
        middle_info = {task.info_task.brief: None for task in self.ui_tasks.values() if task.info_task is not None}
        
        # 初始化所有UITask的status 为 IDLE
        step_status = { step: UIStepStatus.IDLE for step in self.ui_tasks.keys()}
        step_status.update({ step: UIStepStatus.IDLE for step in self.ui_routers.keys()})
        self._state = self.state_cls(
            task=task,
            current_step=start_step,
            # dict为Invariant, 因此实参None无法兼容形参BaseModel | str | None，将dict改为Mapping可以修正这个error，但又会引入其它type error.
            middle_info=middle_info,  # type: ignore
            step_status=step_status,
        )
        self._state.set_step(start_step)  # 初始化状态

        # 初始化sys_prompt。由于这个步骤，在派生类中, WorkflowBase.__init__()必须在最后被调用。
        assert len(self.state.nl_messages) == 0, "nl_messages必须为空"
        self._state.nl_messages.append(ChatCompletionSystemMessageParam(role="system", content=self._nl_sys_prompt))

        self._check_state()

    @property
    def state(self) -> S:
        """没什么大用处, 仅仅为了类型安全"""
        return self._state

    def _check_state(self) -> None:
        """检查state的合法性。"""

        self.state._check()

        # 依赖于外部数据的state check
        for task in self.ui_tasks.values():
            if task.info_task is not None:
                # 用brief作为index key很奇怪。但暂时没啥问题。
                assert (task.info_task.brief in self.state.middle_info), f"info_task: {task.info_task.brief} 必须在middle_info中"


    # TODO: 需要增加从缓存load状态的函数，例如load_state。

    @property
    def _nl_sys_prompt(self) -> str:
        """需要动态生成。必须私有。"""

        prompt = f"""你是一个UIAgent对话助手。你的角色描述如下：
{nl_repr(self.chat_agent_profile)}

你的任务如下:
{nl_repr(self.state.task)}
"""

        
        #         if self.state.user is not None:
        #             prompt += f"""\n和你对话的用户的信息如下:
        # {nl_repr(self.state.user)}

        # 请参考上述信息, 针对性地回复用户。
        # """

        return prompt

    @cached_property
    def info_tasks(self) -> set[InfoTask]:
        """获取所有非空的InfoTask实例集合。
        返回：
            set[InfoTask]: 去重后的InfoTask实例集合
        """
        # type checker有info_task不可hash的错误，但实际上InfoTask的基类BaseModel是可hash的。
        return {task.info_task for task in self.ui_tasks.values() if task.info_task is not None} # type: ignore


    @final
    async def run_nl(self, query: str) -> WorkflowResult[S]:
        """外部接口。可以连续调用run_nl, 因为要允许用户随便说话。这和run_ui非常不同。
        实现难度较大, 由wei yichen维护。不能重载。
        TODO: 可能触发一系列动作: 意图判断, 信息提取, ui task。需要支持流式返回。这样的话需要重写架构。
        """
        self.state.nl_query = query

        try:
            nl_result = await self._run_intent_and_info_fast()
            # TODO: 替换为_run_intent_and_info_fast()
        except UIAgentIntentError as e:
            # 意图识别错误
            self.state.status = WorkflowStatus.ERROR_INTENT
            # TODO: 下面的处理显然是粗糙的。有这么几种情况
            # 如果该错误被认为致命，那么前端app应该报告错误信息并直接退出。这里不应该记录对话。
            # 但通常来说，这里应该有些重试机制。取决于该机制，记录消息历史的方式可能不同。细节不再展开。
            # assistant_reply = "抱歉, 由于未知技术问题，我目前无法处理您的请求"
            # self.state.update_nl_messages(assistant_reply)
            return WorkflowResult[S](error = e, state=self.state)
        except Exception as e:
            # 其它错误
            if self.debug_mode:
                raise e
            self.state.status = WorkflowStatus.ERROR
            error = UIAgentError(traceback.format_exc(), "意图识别和信息搜集发生错误，具体原因未知")
            # TODO: 消息历史如何处理，和上面类似
            return WorkflowResult[S](error = error, state=self.state)

        assert self.state.intent_cls_res is not None, "意图识别结果不能为空"

        category = self.state.intent_cls_res.category
        # TODO: 硬编码比较危险。还想不清楚。
        # TODO: abort和irrelevant情况下可以直接返回。目前的实现比较土，直接在intent_classify中生成回复
        if category == IntentCategory.ABORT.value[0]:
            self.state.status = WorkflowStatus.USER_ABORT
            response = self.state.intent_cls_res.response
            self.state.update_nl_messages(response)
            return WorkflowResult[S](results = [response], state=self.state)
        elif category == IntentCategory.IRRELEVANT.value[0]:
            response = self.state.intent_cls_res.response
            # TODO: 这里是否应该直接丢弃本轮对话？想不清楚。先记下来。
            self.state.update_nl_messages(response)
            return WorkflowResult[S](results = [response], state=self.state)
        else:
            # 其它情况可以继续走
            pass

        # current step如果不为ui task，则返回。
        if self.state.current_step not in self.ui_tasks.keys():
            # TODO: 需要根据nl_result（意图以及info）的情况具体地回复。例如：好的，明天中午2个人，xxx饭店订座。智能体正在为您执行。
            assistant_reply = "\n".join(
                part for part in [f"意图分类: {category}", nl_result, f"当前步骤 {self.state.current_step} 不是UI任务，等待UI输入。"] if part
            )
            self.state.update_nl_messages(assistant_reply)
            # 返回简洁的用户回复，不包含详细的信息提取内容
            # user_reply = f"当前步骤 {self.state.current_step} 不是UI任务，等待UI输入。"
            user_reply = f"正在处理中，请稍等。"
            return WorkflowResult[S](results=[user_reply], state=self.state)
        
        # 是ui task，但只有状态是WAIT_FOR_INFO时才继续。
        if self.state.step_status[self.state.current_step] != UIStepStatus.WAIT_FOR_INFO:
            # TODO: 类似的问题
            extra = f"当前步骤 {self.state.current_step} 状态为 {self.state.step_status[self.state.current_step].name}，继续等待。"
            assistant_reply = "\n".join(part for part in [f"意图分类: {category}", nl_result, extra] if part)
            self.state.update_nl_messages(assistant_reply)
            # 返回简洁的用户回复，不包含详细的信息提取内容
            # user_reply = extra
            user_reply = f"正在处理中，请稍等。"
            return WorkflowResult[S](results=[user_reply], state=self.state)

        # 确保不会raise
        is_info_valid = self._validate_info()

        if not is_info_valid.judgment:
            # TODO: 这里的情况很微妙。info为None时，有可能用缺省值（例如缺省的车牌号）或者其它方式（例如走memory）。
            # TODO: 需要根据nl_result以及invalid reason具体地回复。例如：好的，明天中午2个人，xxx饭店订座。请问订几点的呢？
            assistant_reply = "\n".join(part for part in [f"意图分类: {category}", nl_result, is_info_valid.reason] if part)
            self.state.update_nl_messages(assistant_reply)
            # 返回验证失败的原因（通常是询问用户的信息），不包含详细的信息提取内容
            return WorkflowResult[S](results=[is_info_valid.reason], state=self.state)

        try:
            result = await self._run_ui_task()
            # TODO: 需要根据nl_result以及这里result中可能的ask human具体地回复, 例如：好的，正在为您付停车费，费用为xxx元，请确认，是否支付？
            # 需要把result中的ask human部分拿出来，跟nl_result合并在一起，才能生成好的回复。
            extra = f"UI任务 {self.state.current_step} 思考: {result.thought}" if result.thought else f"UI任务 {self.state.current_step} 已计划。"
            assistant_reply = "\n".join(part for part in [f"意图分类: {category}", nl_result, extra] if part)
            self.state.update_nl_messages(assistant_reply)
            # 返回UI任务结果，不包含详细的信息提取内容
            return WorkflowResult[S](results=[result], state=self.state)
        except Exception as e:
            if self.debug_mode:
                raise e

            self.state.status = WorkflowStatus.ERROR
            error = UIAgentError(traceback.format_exc(), "执行ui agent发生错误，具体原因未知")
            self.state.update_nl_messages(error.reason)
            return WorkflowResult[S](error = error, state=self.state)


    @final
    async def _run_intent_and_info_fast(self) -> str:
        '''和_run_intent_and_info功能相同的快速实现, 通过多个llm任务并发等手段。'''
        assert isinstance(self.state.nl_query, str), "nl_query must be a string"
        messages = copy.deepcopy(self.state.nl_messages)  # 检查self.state.nl_messages不被改变

        # 运行所有的info task
        curr_info_task = None
        # 如果current step是ui task且状态为wait_for_info, 那么就找到了blocking info task
        if self.state.current_step in self.ui_tasks.keys() and self.state.step_status[self.state.current_step] == UIStepStatus.WAIT_FOR_INFO:
            curr_info_task = self.ui_tasks[self.state.current_step].info_task

        # 摘出来需要执行的 InfoTask
        tasks_to_run = [task for task in self.info_tasks if task.exec_mode == InfoExecMode.NL_ANY or task == curr_info_task]

        # 初始化一个空列表，用于存储待并发执行的任务元组（这里并非单纯的协程对象！而是意图分类任务和InfoTask的元组）
        coroutines: list[tuple[Awaitable[Any], InfoTask | None]] = []

        # 添加意图分类任务
        intent_coro = intent_classify(
            self.state.nl_query,
            self.state.nl_messages,
            self.intent_categories,
            task=self.state.task,
            model=self.model_llm.value,
            client=self.client,
        )
        coroutines.append((intent_coro, None))

        # 添加所有需要执行的 InfoTask
        for task in tasks_to_run:
            info_coro = task.arun(
                self.state.nl_query,
                self.state.nl_messages,
                model=self.model_llm.value,
                client=self.client,
            )
            coroutines.append((info_coro, task))

        # 并发执行所有任务，使用 return_exceptions=True 来捕获异常
        results = await asyncio.gather(*[coro for coro, _ in coroutines], return_exceptions=True)

        # 处理意图分类结果（第一个任务），这个是第一个结果。它一定存在。
        intent_result = results[0]
        if isinstance(intent_result, Exception):
            self.state.intent_cls_res = None
            raise UIAgentIntentError(self.state.nl_query, f"意图分类失败 for query: {self.state.nl_query}: {intent_result}")
        else:
            assert isinstance(intent_result, IntentClsResult), "intent_result must be an IntentClsResult"
            self.state.intent_cls_res = intent_result

        # 处理 InfoTask 结果（从第二个任务开始）
        nl_responses: list[str] = []
        for (_, task), result in zip(coroutines[1:], results[1:]):
            assert isinstance(task, InfoTask), "task must be an InfoTask"

            if isinstance(result, Exception):
                self.state.middle_info[task.brief] = None
                print(f"InfoTask {task.brief} 执行失败 for query: {self.state.nl_query}: {result}")
                raise UIAgentInfoTaskError(task.brief, self.state.nl_query, str(result))
            else:
                assert isinstance(result, BaseModel), "info must be a BaseModel"
                self.state.middle_info[task.brief] = result
                nl_responses.append(f"对于下述任务 {task.brief} 提取了信息如下: {nl_repr(result)}")

        assert messages == self.state.nl_messages, "messages must be the same as nl_messages"
        return f"针对query: {self.state.nl_query}，更新了所有InfoTask: \n" + "\n".join(nl_responses)


    @final
    async def _run_intent_and_info(self) -> str:
        '''意图识别和info提取, 返回nl response(可以理解为调用llm模型之前的thinking)，供后续的llm处理并生成回复'''
        assert isinstance(self.state.nl_query, str), "nl_query must be a string" 
        messages = copy.deepcopy(self.state.nl_messages)  # 检查self.state.nl_messages不被改变

        try:
            self.state.intent_cls_res = await intent_classify(
                self.state.nl_query,
                self.state.nl_messages,
                self.intent_categories,
                task=self.state.task,
                model=self.model_llm.value,
                client=self.client,
            )
        except Exception as e:
            self.state.intent_cls_res = None
            raise UIAgentIntentError(self.state.nl_query, f"意图分类失败 for query: {self.state.nl_query}: {e}")

        # 运行所有的info task
        curr_info_task = None
        # 如果current step是ui task且状态为wait_for_info, 那么就找到了blocking info task
        if self.state.current_step in self.ui_tasks.keys() and self.state.step_status[self.state.current_step] == UIStepStatus.WAIT_FOR_INFO:
            curr_info_task = self.ui_tasks[self.state.current_step].info_task
            
        nl_responses: list[str] = []
        for task in self.info_tasks:
            # 不是NL_ANY mode, 也不是blocking info task, 则不需要执行
            if task.exec_mode != InfoExecMode.NL_ANY and task != curr_info_task:
                continue

            try:
                info = await task.arun(
                    self.state.nl_query,
                    self.state.nl_messages,
                    model=self.model_llm.value,
                    client=self.client,
                )
                assert isinstance(info, BaseModel), "info must be a BaseModel"
                self.state.middle_info[task.brief] = info
                # TODO: 目前的描述过于简单。需要更加自然准确，例如：订座人数为3，时间为中午12点。
                nl_responses.append(f"对于下述任务 {task.brief} 提取了信息如下: {nl_repr(info)}")
            except Exception as e:
                self.state.middle_info[task.brief] = None
                print(f"信息提取任务 {task.brief} 执行失败 for query: {self.state.nl_query}: {e}")
                raise UIAgentInfoTaskError(task.brief, self.state.nl_query, str(e))

        assert messages == self.state.nl_messages, "messages must be the same as nl_messages"
        return f"针对query: {self.state.nl_query}，更新了所有InfoTask: \n" + "\n".join(nl_responses)


    @final
    async def run_ui(
        self,
        image: str,
        image_format: str,
        xml: str | None = None,
        /,
        step: StepType | None = None,
        info: BaseModel | str | None = None,
    ) -> WorkflowResult[S]:
        """外部接口, 在ui发生变化时调用。包含顶层逻辑, 比较复杂, 不能重载。必须由wei yichen维护。
        这是唯一能传入image和xml的地方, 因为要对其做验证。直接给state的image赋值是不允许的, 但目前无法保证这一点。
        step, info: 仅用于单步测试和debug。实际运行中, 这些参数是内部维护的, 不能从外部传入。
        """
        assert isinstance(image, str), "image must be a string"
        assert isinstance(image_format, str), "image_format must be a string"
        assert isinstance(xml, str) or xml is None, "xml must be a string or None"
        self.state.image = image
        self.state.image_format = image_format
        self.state.xml = xml

        # 单步测试时，强制赋值
        if step is not None:
            assert isinstance(step, StepType), f"step must be StepType, but is {type(step)}"
            assert step in self.ui_tasks.keys() or step in self.ui_routers.keys(), f"step {step} must be in either ui_tasks or ui_routers"
            self.state.set_step(step)   # 更新当前step，后续使用
            if info is not None:
                assert step in self.ui_tasks.keys()  # 仅UITask需要info
                task = self.ui_tasks[step]
                assert task.info_task is not None, "task.info_task must not be None"

                # 实际运行时info必须是info_type(BaseModel)，这里不强制, 允许为str会方便测试。
                assert isinstance(info, (task.info_task.info_type, str)), f"info type must be {task.info_task.info_type} or str, but is {type(info)}"
                self.state.middle_info[task.info_task.brief] = info  # 更新ui_task所需要的middle info

        # TODO: 从其它状态恢复，但似乎是多余的？
        self.state.status = WorkflowStatus.RUNNING
        
        # 尝试走ui router
        ui_router = self.ui_routers.get(self.state.current_step, None)
        if ui_router:
            # 对于router而言，可能的状态有多种
            assert (
                self.state.step_status[self.state.current_step] == UIStepStatus.WAIT_FOR_IMAGE or
                self.state.step_status[self.state.current_step] == UIStepStatus.ERROR_UI_INVALID
            ), f"ui step {self.state.current_step} status must be WAIT_FOR_IMAGE"

            cls_result, status = ui_router.run(self.state.image, self.state.xml)
            self.state.step_status[self.state.current_step] = status

            if status == UIStepStatus.ERROR_UI_INVALID:
                # TODO: 下面的回复显然不是很好懂。也未必应该告诉用户这些细节。怎么处理还不清楚。
                assistant_reply = f"我不太认识现在的界面图像: {cls_result.reason}"
                # 不应该进入对话历史
                return WorkflowResult[S](results = [assistant_reply], state=self.state)
            else:
                assert status == UIStepStatus.RUNNING, f"ui router status {status} must be RUNNING"
                assert cls_result.category in self.ui_tasks.keys(), f"category {cls_result.category} from ui router must be in ui_steps"
                # print(f"通过router从step {self.state.step} 切换到step {cls_result.category}")
                self.state.current_step = cls_result.category
                # 从router切换到ui task时, 不用set_step, 因为状态会变为WAIT_FOR_INFO
        else:
            #如果没有router, 那么current_step必须是UITask, 且状态为WAIT_FOR_IMAGE
            assert self.state.current_step in self.ui_tasks.keys(), f"step {self.state.current_step} must be in ui_tasks when no router"
            assert (
                self.state.step_status[self.state.current_step] == UIStepStatus.WAIT_FOR_IMAGE
            ), f"ui step {self.state.current_step} status must be WAIT_FOR_IMAGE"

        # 无论有没有经过ui router, 当前ui task的image都ready了，下面检验info
        self.state.step_status[self.state.current_step] = UIStepStatus.WAIT_FOR_INFO

        is_info_valid = self._validate_info()
        if not is_info_valid.judgment:
            # TODO: 这里的情况很微妙。info为None时，有可能用缺省值（例如缺省的车牌号）或者其它方式（例如走memory）。
            # TODO: 类似于run_nl中的情况。需要以说话的口吻回复用户，需要用llm。
            assistant_reply = is_info_valid.reason if isinstance(is_info_valid.reason, str) else "需要更多信息才能继续当前UI任务。"
            # TODO: 这句话确实应该进入消息历史，但此时并没有有效的nl_query, 只能单独增加一条assistant message。是否可行，需要验证。
            # self.state.update_nl_messages(assistant_reply)  
            return WorkflowResult[S](results=[assistant_reply], state=self.state)

        try:
            result = await self._run_ui_task()
            assistant_reply = f"UI任务 {self.state.current_step} 思考: {result.thought}\n动作: {result.action_content}" if isinstance(result.action_content, str) else f"UI任务 {self.state.current_step} 已生成动作。"
            # TODO: 不应该进入nl_messages，而是另外一套 ui_messages。完全不着急。
            return WorkflowResult[S](results=[result], state=self.state)
        except Exception as e:
            # debug模式下直接暴露错误，更容易发现问题
            if self.debug_mode:
                raise e

            self.state.status = WorkflowStatus.ERROR
            error = UIAgentError(traceback.format_exc(), "执行ui agent发生错误，具体原因未知")
            return WorkflowResult[S](error = error, state=self.state)


    @property
    def _middle_info(self) -> BaseModel | str | None:
        """helper function, 获取当前step的middle info。简化代码而已, 没什么大用。目前也没有被使用。"""
        assert self.state.current_step in self.ui_tasks.keys(), f"step {self.state.current_step} must be in ui_tasks"
        task = self.ui_tasks[self.state.current_step]
        assert task.info_task is not None, "task.info_task must be not None"
        return self.state.middle_info[task.info_task.brief]


    def _validate_info(self) -> JudgeResult:
        '''它是_run_ui_task的前序步骤。按说可以合并。但由于其返回的nl内容在run_nl和run_ui中的处理方式不一样, 因此需要拆出来'''

        assert self.state.current_step in self.ui_tasks.keys(), f"step {self.state.current_step} must be in ui_tasks"
        # 确认处于验证info状态
        assert self.state.step_status[self.state.current_step] == UIStepStatus.WAIT_FOR_INFO

        task = self.ui_tasks[self.state.current_step].info_task
        
        if task is None:
            return JudgeResult(judgment=True, reason="没有info, 无需校验")

        if task.validator is None:
            return JudgeResult(judgment=True, reason="没有info validator, 无需校验")

        assert callable(task.validator), f"validator for info task {nl_repr(task)} must be callable"
        return task.validator(self.state.middle_info[task.brief])


    @final
    async def _run_ui_task(self) -> UITaskResult:
        '''image准备好了, ui router判断这正确了, info也ready了, 开始执行ui task。足够复杂和通用。不能再重载了。
        TODO: 整体抽象为一个UIStep, 可以替换。这是以后能自由开发新架构，创新的地方。
        '''
        assert self.state.current_step in self.ui_tasks.keys(), f"step {self.state.current_step} must be in ui_tasks"

        # TODO: 可以简化为 _middle_info
        task = self.ui_tasks[self.state.current_step]
        info = self.state.middle_info[task.info_task.brief] if task.info_task is not None else None
    
        self.state.step_status[self.state.current_step] = UIStepStatus.RUNNING

        rpa_handler = self.rpa_handlers.get(self.state.current_step, None)
        if rpa_handler:
            assert callable(rpa_handler), "rpa handler for step {self.state.current_step} must be callable"

            if self.state.xml is not None:
                # TODO: 这里应该try and catch, 接着走ui_handler，如果有的话
                try:
                    actions, current_step, current_step_status = rpa_handler(info, self.state.xml)
                    # TODO: 应该传入ui task，通过其page实现算法，通过其action_set检查actions是否合法
                    width, height = get_image_dimensions(self.state.image)
                    actions = norm_actions(actions, width, height)

                    assert isinstance(current_step, StepType), "rpa handler return step type must be type 'StepType'"
                    self.state.set_step(current_step, current_step_status)

                    # TODO: 这里包了一个无意义的UITaskResult。应该支持返回list[Action]么？不确定。
                    return UITaskResult(raw_prompt="", thought="", action_content="", actions=actions, source=ActionSource.RPA)
                except:
                    error_details = traceback.format_exc()
                    print(f"rpa处理失败:{error_details}")
            else:
                # TODO: 应该有个warning，rpa_handler有效但xml无效
                pass

        # 必须有handler，不存在兜底实现. 因为无法提前知道如何跳转
        assert self.state.current_step in self.ui_handlers.keys(), f"step {self.state.current_step} must be in ui_handlers"
        handler = self.ui_handlers[self.state.current_step]
        assert callable(handler), f"handler for step {self.state.current_step} must be callable"
        assert isinstance(self.state.image, str), "image must be a string"
        assert isinstance(self.state.image_format, str), "image_format must be a string"
        # TODO: 写法应该仿照rpa_handler，传入info, 返回next step
        # TODO: 其实就是 UITask.arun, 然后根据actions跳转next step。写成普通function，传入ui task即可。
        # ui_task_eval放在后面即可。
        result = await handler(self.state.image, self.state.image_format)

        return result


    @final
    async def _run_ui_step_by_model(self, image: str, image_format: str) -> UITaskResult:
        ''' 这个函数已经简化到几乎可以删除的程度了。 '''
        task = self.ui_tasks[self.state.current_step]

        if isinstance(task.info_task, InfoTask):
            # 有info task时尝试取info
            info = self.state.middle_info[task.info_task.brief]
            # TODO: 注意有可能允许这里的info为None，然后取缺省值
        else:
            info = None

        result, prompt = await task.arun(image, image_format, info, model=self.model, client=self.client)
        
        # TODO: reflect 应该放在什么地方，还没想清楚
        # 放在这里的坏处是：慢，可能raise，自身破坏算法逻辑。
        if self.enable_reflect: 
            # eval必须使用model_vision， 做结构化输出
            try:
                # 使用默认参数禁用 thinking 模式
                self.state.eval_res = await ui_task_eval(
                    prompt,
                    image,
                    image_format,
                    result.thought,
                    result.action_content,
                    client=self.client,
                    model=self.model_vision,
                    **DEFAULT_LLM_PARAMS,
                )
            except Exception as e:
                self.state.eval_res = None
        else:
            self.state.eval_res = None        

        return result
