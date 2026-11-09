'''基于__init__中的WorkflowBase, 重构的新一版架构。
重点是将UIStep彻底的抽象和分离出来, 从而可以更灵活地扩展和定制, 而不是受限于已有的实现。
'''
from pathlib import Path
from nanoai.model.vlm import image_from_path
import asyncio
import copy
from datetime import datetime
from enum import Enum, StrEnum
from typing import final, Self, Callable, Type, Any, Awaitable
from nanoai.utils.nl_repr import nl_repr
from pydantic import BaseModel, Field, ConfigDict, model_validator
from functools import cached_property
import traceback
from nanoai.model.config import AsyncOpenAI, ModelName, create_client
from projects.uiagent.core.error import UIAgentError, UIAgentInfoTaskError, UIAgentIntentError
from projects.uiagent.core.flow_data import (
    WorkflowStatus,
    StepType,
    _END_STEP,
    UIRouter,
    UIStepStatus,
    UIResult,
    MiddleInfoType,
    get_class_id,
    PUIStep,
)
from nanoai.utils.data_concept import JudgeResult
from projects.uiagent.utils.common_task import IntentClsResult
from projects.uiagent.core.chat import InfoTask, InfoExecMode, intent_classify, IntentCategory
from projects.uiagent.core.action import Action,AskAction,WaitAction
from nanoai.model.llm import ChatCompletionMessageParam



class ActionSource(StrEnum):
    RPA = "rpa"
    UI = "ui-tars"


class UIFlowState(BaseModel):
    """工作流的状态。
    TODO: 由于初始化十分困难，目前几乎所有字段都有缺省值。
    真正的构造发生在workflow.__init__()。
    """

    task: str = Field(title="工作流任务", description="工作流任务的整体描述")
    """这是对话功能的基础。例如, 帮助用户选择餐厅和订座，需要询问相关信息并确认。没有缺省值。
    TODO: 应该会有很多需要定制化的地方。怎么写还不清楚。"""

    status: WorkflowStatus = Field(
        default=WorkflowStatus.RUNNING, title="工作流的状态", description="工作流的状态")
    """粗粒度的status, 和step_status[step]共同描述整体的状态。"""

    @property
    def terminated(self) -> bool:
        return self.status != WorkflowStatus.RUNNING

    step: StepType = Field(title="当前UI步骤", description="当前UI步骤")
    '''不能有缺省值。
    TODO: 不允许显式的赋值。
    '''

    step_status: dict[StepType, UIStepStatus] = Field(
        default_factory=dict, title="所有UI步骤的状态", description="所有UI步骤的状态")
    ''' 任意时刻, 只有一个UIStep是active的。这是最简单的state, 在UIFlow中维护。UIStep无法修改。
    必须由UIStep自定义和维护的状态，只能将整个state传进去。
    '''

    image: str | None = Field(
        default=None, title="当前页面截图", description="当前页面截图", repr=False)

    image_format: str | None = Field(
        default=None, title="当前页面截图格式", description="当前页面截图格式", repr=False)

    xml: str | None = Field(default=None, title="当前页面XML",
                            description="当前页面XML", repr=False)
    """它们共同描述了当前UI页面。xml不总是有值。如果有，尝试用rpa方案，而不是vlm方案。"""

    nl_query: str | None = Field(
        default=None, title="当前NL查询", description="当前NL查询")
    """用户最近的query, 因为可能用于多个nl task, 需要缓存在这里共享, 供_run_nl使用。
    TODO: 现在的写法肯定是有问题的。因为这个query必须以某种方式进入nl_messages，才能持续调用run_nl()。目前还做不到。
    """

    # TODO: 需要统一管理MiddleInfo数据。它们是InfoTask的输出，UIStep的输入。
    middle_info: MiddleInfoType = Field(
        default_factory=dict, title="中间信息", description="中间信息")
    """非常重要的字段。初始化时可以传入。没有必要init=False。
    key: InfoTask name, value: InfoTask提取得到的信息。value type可以是BaseModel也可以是nl str。
    前者在run_nl中做提槽时方便一些，但语义上其实就是个str。无需提槽时可以直接用str，例如：1）测试时送入的query都是事先写好的。
    如果允许info为str, 那就无法做基于hard code的检查。但还是可以用vlm做动态的检查, 并返回ask human。
    TODO: 真的需要这种灵活性么？不确定。架构上先支持吧。
    TODO: key一旦初始化后，不能修改。如何确保？目前在workflow._check_state()中检查。
    TODO: 如何管理这些数据，还有很多不清楚的地方。
    TODO: 可能需要引入缺省值的概念（middle_info_default）。例如，停车时的缺省车牌号。这个有可能太复杂了。
    """
    nl_messages: list[ChatCompletionMessageParam] = Field(
        default_factory=list, title="消息历史", description="消息历史", init=False)
    """用于run_nl的对话历史。不为空。第一条永远是sys prompt."""

    actions_record: list[Action] = Field(
        default_factory=list, title="动作记录", description="过往你执行过的所有动作。", init=False)

    intent_cls_res: IntentClsResult | None = Field(
        default=None, title="用户意图分类结果", description="用户意图分类结果")
    """意图分类结果。None表示分类失败。
    TODO: 还不确定要放在State中还是WorkflowResult。似乎State更合适。
    """
    
    background_info: str = Field(default=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",title="当前日期时间", description="当前日期时间，格式为YYYY-MM-DD HH:MM:SS")
    
    def update_nl_sys_prompt(self, sys_prompt: str) -> None:
        """更新nl_messages的第一个消息为system消息。供workflow状态改变时调用"""
        assert len(self.nl_messages) > 0, "nl_messages不能为空"
        assert self.nl_messages[0]["role"] == "system", "result的第一个消息必须是system消息"
        self.nl_messages[0] = {"role": "system", "content": sys_prompt}

    def update_nl_messages(self, assistant_content: str) -> None:
        """记录一轮对话"""
        assert isinstance(self.nl_query, str), "nl_query必须是str"
        self.nl_messages.append({"role": "user", "content": self.nl_query})
        self.nl_messages.append(
            {"role": "assistant", "content": assistant_content})
        self.nl_query = None  # 已经处理过了，语义上不再存在
    
    def add_an_assistant_message(self, assistant_content: str) -> None:
        """记录一轮对话"""
        self.nl_messages.append({"role": "assistant", "content": assistant_content})
    
    def add_a_user_message(self, user_content: str) -> None:
        """记录一轮对话"""
        self.nl_messages.append({"role": "user", "content": user_content})

    eval_res: JudgeResult | None = Field(
        default=None, title="评估结果", description="评估结果")
    """enable_reflect为True时有值。
    TODO: 应该挪到WorkflowResult中。目前还不方便，因为要通过_run_ui_step_by_model返回，改动太大。
    """

    def _check(self) -> None:
        """检查state的合法性。有些约束是无法在对象创建时检查的。"""
        assert len(self.nl_messages) > 0, "messages不能为空"

        assert self.nl_messages[0]["role"] == "system", "messages的第一个消息必须是system消息"


class UIFlowResult[S: UIFlowState](BaseModel):
    '''这是智能体对外的输出。除了state, 其它成员都有缺省值。'''

    model_config = ConfigDict(arbitrary_types_allowed=True)  # 为了支持Exception

    results: list[UIResult | str] | None = Field(
        default=None, title="workflow执行结果", description="workflow执行结果")
    """UIRunResult表示执行UI动作, str表示给用户的回复, 可能是需要他的回复（ask human），也可能只是告诉他发生了什么（这是个产品体验设计的问题）。
    None表示执行失败，没有结果。在正常情况下（排除无法处理的情况，参见run_nl, run_ui中的异常处理部分），不允许为空，也就是，哪怕ui task无法执行，也需要告诉用户发生了什么。
    虽然是list，但最多只包括一个UITaskResult，一个str。前端依次执行即可。
    TODO: 将来可能扩充为能输出多个str，非常取决于具体情况。
    """

    error: UIAgentError | None = Field(
        default=None, title="错误信息", description="错误信息", exclude=True)
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


class UIFlowBase[S: UIFlowState]:
    """UI工作流的基类。
    S: 状态类型。必须是UIFlowState的子类。
    """

    def __init__(
        self,
        task: str,
        start_step: StepType,
        ui_steps: dict[StepType, PUIStep[S]],
        ui_routers: dict[StepType, UIRouter] | None = None,

        /,
        *,
        intent_categories: list[tuple[str, str]] = [intent.value for intent in IntentCategory],
        state_cls: type[S] = UIFlowState,
        debug_mode: bool = False,
    ):
        self.ui_steps = ui_steps
        self.ui_routers = ui_routers or {}

        # 算法参数
        # vlm没有结构化能力
        # self.client, self.vlm = create_client(
        #     ModelName.DOUBAO_SEED_1_8_PREVIEW, AsyncOpenAI)

        self.client, self.vlm = create_client(
            ModelName.DOUBAO_1_5_UI_TARS_250428, AsyncOpenAI)

        self.vlm_aux = ModelName.DOUBAO_SEED_1_6_VISION_250815  # 具有结构化能力

        self.llm = ModelName.DOUBAO_SEED_1_6_FLASH_250828  # 缺省的语言模型

        self.debug_mode = debug_mode

        self.intent_categories = intent_categories
        # 状态
        assert issubclass(
            state_cls, UIFlowState), f"state_cls must be UIFlowState的子类, but got {type(state_cls)}"
        self.state_cls = state_cls

        # 所有ui_steps的middle_info都初始化为空。
        middle_info = {}
        for _, step_obj in self.ui_steps.items():
            # 这里隐含地做了去重。key同样的middle_info_def()只会保留一个。
            middle_info.update({k: None for k in step_obj.middle_info_def()})

        # 初始化所有UITask的status 为 IDLE
        step_status = {
            step: UIStepStatus.IDLE for step in self.ui_steps.keys()}
        step_status.update(
            {step: UIStepStatus.IDLE for step in self.ui_routers.keys()})

        self._state = self.state_cls(
            task=task,
            step=start_step,
            # dict为Invariant, 因此实参None无法兼容形参BaseModel | str | None，将dict改为Mapping可以修正这个error，但又会引入其它type error.
            middle_info=middle_info,
            step_status=step_status,
        )
        self._state.step = start_step  # 初始化状态
        self._state.step_status[start_step] = UIStepStatus.WAIT_FOR_IMAGE

    @property
    def state(self) -> S:
        """没什么大用处, 仅仅为了类型安全"""
        return self._state

    @cached_property
    def all_steps(self) -> set[StepType]:
        """所有的step, 包括ui_steps和ui_routers。没什么大用处, 方便各种检查。"""
        steps = set[StepType](self.ui_steps.keys())
        steps.update(self.ui_routers.keys())

        return steps

    @cached_property
    def info_type_dict(self) -> dict[str, Type]:
        """获取所有非空的InfoTask实例集合。
        返回：
            dict[str, Type]: 去重后的InfoTask实例集合，key为step的所需middle_info的name，value为所需middle_info的类型
        """
        # type checker有info_task不可hash的错误，但实际上InfoTask的基类BaseModel是可hash的。
        # 遍历所有ui_step，把它们的middle_info_def合并成一个dict
        info_type_dict = {}
        for _, step_obj in self.ui_steps.items():
            info_type_dict.update(step_obj.middle_info_def())
        return info_type_dict

    @final
    async def run_ui(
        self,
        image: str,
        image_format: str,
        xml: str | None = None,
        /,
        step: StepType | None = None,
        info: MiddleInfoType | BaseModel | str | None = None,
    ) -> UIFlowResult[S]:
        """外部接口, 在ui发生变化时调用。包含顶层逻辑, 比较复杂, 不能重载。必须由wei yichen维护。
        这是唯一能传入image和xml的地方。不允许直接给state的image赋值。

        step, info: 仅用于单步测试和debug。实际运行中, 这些参数是内部维护的, 不能从外部传入。
        info的类型允许为BaseModel或者str是为了支持简单情况。很脏的实现。
        """
        assert isinstance(image, str), "image must be a string"
        assert isinstance(image_format, str), "image_format must be a string"
        assert isinstance(
            xml, str) or xml is None, "xml must be a string or None"
        self.state.image = image
        self.state.image_format = image_format
        self.state.xml = xml

        # 单步测试时，强制赋值
        if step is not None:
            assert isinstance(
                step, StepType), f"step must be StepType, but is {type(step)}"
            assert step in self.all_steps, f"step {step} is invalid"
            self.state.step = step
            self.state.step_status[step] = UIStepStatus.WAIT_FOR_IMAGE  # 一定得是

            if info is not None:
                assert step in self.ui_steps.keys()  # 仅UITask需要info
                ui_step = self.ui_steps[step]

                if isinstance(info, BaseModel):
                    # 很脏的实现。假设UIStep的middle_info_def()也是这么实现的。
                    info = {get_class_id(info.__class__): info}
                elif isinstance(info, str):
                    # 很脏的实现。假设UIStep的middle_info_def()只有一个key。
                    keys = ui_step.middle_info_def().keys()
                    assert len(
                        keys) == 1, f"ui_step {step} must have only one key in middle_info_def when info is str"
                    info = {next(iter(keys)): info}

                # TODO: 这里的assert不能直接使用MiddleInfoType, 因为它是个generic type。需要借助于typing模块的get_origin()来判断是否为dict。
                assert isinstance(
                    info, dict), f"info must be dict, but is {type(info)}"
                # 给info赋值
                for k, v in info.items():
                    assert k in ui_step.middle_info_def(
                    ), f"info key {k} must be in ui step middle info def {ui_step.middle_info_def()}"
                    assert k in self.state.middle_info, f"info key {k} must be in state middle info {self.state.middle_info}"
                    self.state.middle_info[k] = v

        # 尝试走ui router
        ui_router = self.ui_routers.get(self.state.step, None)
        if ui_router:
            # router的合法状态有两种
            # TODO 现在有Wait动作告诉端侧图有问题，维持WAIT_FOR_IMAGE并等待等下重新截图了，这块之后可以考虑优化掉ERROR_UI_INVALID相关逻辑。
            assert (
                self.state.step_status[self.state.step] == UIStepStatus.WAIT_FOR_IMAGE or
                self.state.step_status[self.state.step] == UIStepStatus.ERROR_UI_INVALID
            ), f"ui router status {self.state.step_status[self.state.step]} must be WAIT_FOR_IMAGE or ERROR_UI_INVALID"

            cls_result, status = ui_router.run(
                self.state.image, self.state.xml)
            self.state.step_status[self.state.step] = status

            if status == UIStepStatus.ERROR_UI_INVALID:
                # TODO: 下面的回复显然不是很好懂。也未必应该告诉用户这些细节。怎么处理还不清楚。
                assistant_reply = f"我不太认识现在的界面图像: {cls_result.reason}"
                # 不应该进入对话历史
                return UIFlowResult[S](results=[assistant_reply], state=self.state)
            else:
                assert status == UIStepStatus.RUNNING, f"ui router status {status} must be RUNNING"
                assert cls_result.category in self.ui_steps.keys(
                ), f"category {cls_result.category} from ui router must be in ui_steps"
                # print(f"通过router从step {self.state.step} 切换到step {cls_result.category}")
                self.state.step = cls_result.category
                # 从router切换到ui task时, 不用set_step, 因为状态会变为WAIT_FOR_INFO
        else:
            # 如果没有router, 那么step必须是UITask, 且状态为WAIT_FOR_IMAGE
            assert self.state.step in self.ui_steps.keys(
            ), f"step {self.state.step} must be in ui_steps when no router"
            assert (
                self.state.step_status[self.state.step] == UIStepStatus.WAIT_FOR_IMAGE
            ), f"ui step {self.state.step} status must be WAIT_FOR_IMAGE"

        # TODO 如美团订座场景，有时会看到从未见过的选项需要记下来并且询问用户，这个问题就转化为了即使是ui执行，也需要随机应变地从图像里提取一些Info
        # try:
        #     # run_ui时，最新query已经在messages里最后一条了，反而需要先去掉，然后在_run_info_fast里重新从nl_query添加
        #     nl_result = await self._run_info_fast(self.state.nl_messages[:-1])
        # except Exception as e:
        #     # 其它错误
        #     if self.debug_mode:
        #         raise e
        #     self.state.status = WorkflowStatus.ERROR
        #     error = UIAgentError(traceback.format_exc(),
        #                          "意图识别和信息搜集发生错误，具体原因未知")
        #     # TODO: 消息历史如何处理，和上面类似
        #     return UIFlowResult[S](error=error, state=self.state)
        # 无论有没有经过ui router, 当前ui step的image都ready了，可以run了
        try:
            ui_step = self.ui_steps[self.state.step]
            # 从state中拿到middle_info
            middle_info = {k: self.state.middle_info[k]
                           for k in ui_step.middle_info_def()}

            # TODO: 这里的返回值应该不够, 有可能同时修改当前step和next step
            result, step, step_status = await ui_step.arun(
                self.state.image,
                self.state.image_format,
                self.state.xml,
                middle_info,
                state=self.state,
                model=self.vlm,
                client=self.client,
            )

            if isinstance(result, UIResult) and len(result.actions) == 1:
                if isinstance(result.actions[0], AskAction):
                    self.state.add_an_assistant_message(result.actions[0].content)
                    self.state.actions_record.append(result.actions[0])
                else:
                    self.state.actions_record.append(result.actions[0])
            # 这里是出口, 一种特殊的Step
            if step == _END_STEP:
                self.state.status = WorkflowStatus.SUCCESS

            self.state.step = step
            self.state.step_status[step] = step_status

            # TODO: 这里需要log
            # print(f"状态跳转到: {step} with status {step_status}")

            return UIFlowResult[S](results=[result], state=self.state)
        except Exception as e:
            # debug模式下直接暴露错误，更容易发现问题
            if self.debug_mode:
                raise e

            self.state.status = WorkflowStatus.ERROR
            error = UIAgentError(e, "执行ui agent发生错误，具体原因未知")
            return UIFlowResult[S](error=error, state=self.state)

    @final
    async def run_nl(self, query: str) -> UIFlowResult[S]:
        """外部接口。可以连续调用run_nl, 因为要允许用户随便说话。这和run_ui非常不同。
        实现难度较大, 由wei yichen维护。不能重载。
        TODO: 可能触发一系列动作: 信息提取, ui step。需要支持流式返回。这样的话需要重写架构。
        """
        self.state.nl_query = query
        self.state.add_a_user_message(query)
        try:
            nl_result = await self._run_intent_and_info_fast(self.state.nl_messages)
        except UIAgentIntentError as e:
            # 意图识别错误
            self.state.status = WorkflowStatus.ERROR_INTENT
            # TODO: 下面的处理显然是粗糙的。有这么几种情况
            # 如果该错误被认为致命，那么前端app应该报告错误信息并直接退出。这里不应该记录对话。
            # 但通常来说，这里应该有些重试机制。取决于该机制，记录消息历史的方式可能不同。细节不再展开。
            # assistant_reply = "抱歉, 由于未知技术问题，我目前无法处理您的请求"
            # self.state.update_nl_messages(assistant_reply)
            return UIFlowResult[S](error = e, state=self.state)
        except Exception as e:
            # 其它错误
            if self.debug_mode:
                raise e
            self.state.status = WorkflowStatus.ERROR
            error = UIAgentError(traceback.format_exc(),
                                 "意图识别和信息搜集发生错误，具体原因未知")
            # TODO: 消息历史如何处理，和上面类似
            return UIFlowResult[S](error=error, state=self.state)

        assert self.state.intent_cls_res is not None, "意图识别结果不能为空"
        
        category = self.state.intent_cls_res.category
        # TODO: 硬编码比较危险。还想不清楚。
        # TODO: abort和irrelevant情况下可以直接返回。目前的实现比较土，直接在intent_classify中生成回复
        if category == IntentCategory.ABORT.value[0]:
            self.state.status = WorkflowStatus.USER_ABORT
            response = self.state.intent_cls_res.response
            self.state.update_nl_messages(response)
            return UIFlowResult[S](results = [response], state=self.state)
        elif category == IntentCategory.IRRELEVANT.value[0]:
            response = self.state.intent_cls_res.response
            # TODO: 这里是否应该直接丢弃本轮对话？想不清楚。先记下来。
            self.state.update_nl_messages(response)
            return UIFlowResult[S](results = [response], state=self.state)
        else:
            # 其它情况可以继续走
            pass
        # current step如果不为ui_step，则返回。
        if self.state.step not in self.ui_steps.keys():
            # TODO: 需要根据nl_result（意图以及info）的情况具体地回复。例如：好的，明天中午2个人，xxx饭店订座。智能体正在为您执行。
            assistant_reply = "\n".join(
                part for part in [nl_result, f"当前步骤 {self.state.step} 不是UI任务，等待UI输入。"] if part
            )
            # self.state.update_nl_messages(assistant_reply)
            # 返回简洁的用户回复，不包含详细的信息提取内容
            # user_reply = f"当前步骤 {self.state.step} 不是UI任务，等待UI输入。"
            user_reply = f"正在处理中，请稍等。"
            self.state.add_an_assistant_message(user_reply)
            return UIFlowResult[S](results=[user_reply], state=self.state)

        # 是ui_step，但只有状态是WAIT_FOR_INFO时才继续。
        if self.state.step_status[self.state.step] != UIStepStatus.WAIT_FOR_INFO:
            # TODO: 类似的问题
            extra = f"当前步骤 {self.state.step} 状态为 {self.state.step_status[self.state.step].name}，继续等待。"
            assistant_reply = "\n".join(
                part for part in [nl_result, extra] if part)
            # 返回简洁的用户回复，不包含详细的信息提取内容
            # user_reply = extra
            user_reply = f"正在处理中，请稍等。"
            self.state.add_an_assistant_message(user_reply)
            return UIFlowResult[S](results=[user_reply], state=self.state)

        try:
            ui_step = self.ui_steps[self.state.step]
            # 从state中拿到middle_info
            middle_info = {k: self.state.middle_info[k]
                           for k in ui_step.middle_info_def()}
            assert self.state.image and self.state.image_format, "image, image_format不能为空"

            # TODO: 这里的返回值应该不够, 有可能同时修改当前step和next step
            result, step, step_status = await ui_step.arun(
                self.state.image,
                self.state.image_format,
                self.state.xml,
                middle_info,
                state=self.state,
                model=self.vlm,
                client=self.client,
            )
            # 如果result里的actions有且仅有一个动作，且该动作为AskHuman，那么加一条assistant message
            self.state.add_a_user_message(self.state.nl_query) # 之前一直没有存储用户的query，因为_run_info_fast里的info_task.run需要最新query单独存在未合并到nl_messages中
            if isinstance(result, UIResult) and len(result.actions) == 1:
                if isinstance(result.actions[0], AskAction):
                    self.state.update_nl_messages(result.actions[0].content)
                    self.state.actions_record.append(result.actions[0])
                elif not isinstance(result.actions[0], WaitAction):
                    self.state.actions_record.append(result.actions[0])
            # 这里是出口, 一种特殊的Step
            self.state.step = step
            self.state.step_status[step] = step_status

            # TODO: 这里需要log
            # print(f"状态跳转到: {step} with status {step_status}")

            return UIFlowResult[S](results=[result], state=self.state)
        except Exception as e:
            # debug模式下直接暴露错误，更容易发现问题
            if self.debug_mode:
                raise e

            self.state.status = WorkflowStatus.ERROR
            error = UIAgentError(e, "执行ui agent发生错误，具体原因未知")
            return UIFlowResult[S](error=error, state=self.state)

    @final
    async def _run_intent_and_info_fast(self, messages: list[ChatCompletionMessageParam]) -> str:
        '''和_run_intent_and_info功能相同的快速实现, 通过多个llm任务并发等手段。'''
        assert isinstance(self.state.nl_query,
                          str), "nl_query must be a string"
        # 检查self.state.nl_messages不被改变
        the_messages = copy.deepcopy(messages)
        
        """后面步骤也需要使用之前的对话提取信息，干脆就都执行了。"""
        # current_needed_info_names = None
        # # 如果current step是ui task且状态为wait_for_info, 那么就找到了blocking info task
        # # 现在默认所有Info提取都是随时提取的，any_time
        # if self.state.step in self.ui_steps.keys():
        #     keys_step_need = self.ui_steps[self.state.step].middle_info_def(
        #     ).keys()
        #     current_needed_info_names = keys_step_need
        # if not current_needed_info_names:
        #     return f"当前步骤 {self.state.step} 不需要提取信息。"
        # 摘出来需要提取的Info结构体，用一个标准Info task提取一下。

        def standard_info_task_gen(brief: str, info_type: type[BaseModel]) -> str:
            return f""""你是一个非常专业的万能的接线员，负责与用户进行沟通并总结和记录下来关键信息。"
                    现在，阅读最下方你与一位用户的对话记录，从对话记录中，总结和提取出下方的关键信息:
                    {nl_repr(info_type)}
                    你还需用到的一些背景信息如下:
                    {self.state.background_info}
                    在这个过程中，如果你看到上面的关键信息有scratchpad，既草稿纸的话，你就特别需要灵活运用草稿纸来临时记录一些细节，总结，或者你的想法等。
                    不要漏掉任何细节，你是非常无微不至的，有任何可能需要向用户确认的细节问题都先记载在草稿纸上。
                    同时，类似的细节如果可以得到答案，那么你也要细细记录在草稿纸上以防你忘记了各种细节要求。
                    你非常聪明仔细，对话记录里提到了的信息就一定要提取和总结出来到关键信息里！
                    请以json格式返回。
                    """
        tasks_to_run = []
        
        for info_class_name,info_type in self.info_type_dict.items():
            standard_info_task = InfoTask(
                brief=info_class_name, info_type=info_type, exec_mode=InfoExecMode.NL_ANY, info_gen=standard_info_task_gen)
            tasks_to_run.append(standard_info_task)

        # 初始化一个空列表，用于存储待并发执行的任务元组
        coroutines: list[tuple[Awaitable[Any], str | None]] = []

        # 添加意图分类任务
        intent_coro = intent_classify(
            self.state.nl_query,
            self.state.nl_messages,
            self.intent_categories,
            task=self.state.task,
            model=self.llm.value,
            client=self.client,
        )
        coroutines.append((intent_coro, None))

        # 添加所有需要执行的 InfoTask
        for task in tasks_to_run:
            info_coro = task.arun(
                self.state.nl_query,
                the_messages,
                model=self.llm.value,
                client=self.client,
            )
            coroutines.append((info_coro, task.brief))

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
        for (_, info_name), result in zip(coroutines[1:], results[1:]):
            assert info_name is not None, "info_name must not be None"
            if isinstance(result, Exception):
                self.state.middle_info[info_name] = None
                print(
                    f"InfoTask {info_name} 执行失败 for query: {self.state.nl_query}: {result}")
                raise UIAgentInfoTaskError(
                    info_name, self.state.nl_query, str(result))
            else:
                assert isinstance(
                    result, BaseModel), "info must be a BaseModel"
                # 这里上边用info type的名称做brief了，所以可以直接对应到位
                self.state.middle_info[info_name] = result
                nl_responses.append(
                    f"对于下述任务 {info_name} 提取了信息如下: {nl_repr(result)}")

        assert messages == self.state.nl_messages, "messages must be the same as nl_messages"
        return f"针对query: {self.state.nl_query}，更新了所有InfoTask: \n" + "\n".join(nl_responses)


async def run_ui_step(
    uiflow_creator: type[UIFlowBase] | Callable[[], UIFlowBase],
    image_path: str,
    step: StepType,
    /,
    xml_path: str | None = None,
    info: MiddleInfoType | None = None,
) -> UIFlowResult:
    '''执行单步UI任务。'''

    uiflow = uiflow_creator()  # type: ignore
    # from openai import AsyncOpenAI
    # from nanoai.model.config import DMX_API_KEY, DMX_BASE_URL, DMX_MODEL_CLAUDE_OPUS_4_5,DMX_MODEL_GPT5_2,DMX_MODEL_GEMINI
    # headers = {}
    # uiflow.client = AsyncOpenAI(
    #     base_url=DMX_BASE_URL,
    #     api_key=DMX_API_KEY,
    #     default_headers=headers
    # )
    # uiflow.vlm = DMX_MODEL_GPT5_2
    image, image_format = image_from_path(image_path)
    xml = Path(xml_path).read_text(encoding="utf-8") if xml_path else None
    result = await uiflow.run_ui(image, image_format, xml, step=step, info=info)

    return result
