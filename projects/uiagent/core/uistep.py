from typing import Self, Callable,Union,List
from abc import ABCMeta, abstractmethod
from pydantic import BaseModel, Field, model_validator
import inspect
from nanoai.utils.nl_repr import nl_repr
from nanoai.model.config import AsyncOpenAI
from nanoai.model.vlm import avlm, avlm_output_by_schema
from nanoai.utils.data_concept import JudgeResult

from projects.uiagent.utils.image_utils import get_image_dimensions
from projects.uiagent.core.action import parse_action, norm_actions
from projects.uiagent.utils.utils import parse_thought_and_action_content
from projects.uiagent.core.flow_data import (
    Action,
    EUIAction,
    ACTION_OUTPUT_PROMPT_PLAIN,
    Page,
    StepType,
    MiddleInfoDefineType,
    MiddleInfoType,
    get_class_id,
    UIStepStatus,
    UIResult,
)
from projects.uiagent.core.error import UIAgentInfoInvalidError


ALL_ACTIONS = [EUIAction.CLICK, EUIAction.TYPE, EUIAction.SCROLL, EUIAction.ASK]

class UITask(BaseModel):
    """
    UITask定义了单步UI任务。通常调用vlm完成。它需要两类输入数据：
    - 页面：这是vlm的image输入。它来自workflow的state.image，更源头来自于run_ui的输入。
    - 数据参数：这是vlm的prompt输入，如车牌号，店名，时间，人数等。它来自于workflow state的各种数据成员，更源头来自于InfoTask。
    它输出action_set中的一个或多个动作。
    workflow run_ui只能按照设计好的顺序执行当前UI任务。多个UI任务不能并行。这是它和InfoTask的本质区别。
    TODO: 用RPA和xml来执行的也算UITask。它也需要这里的部分字段: info_task, action_set, 没准还有page。暂时共同UITask。
    将来也许需要提取出 RPATask （作为UITask的base），单独供rpa handler使用。
    TODO: UITask的实现非常通用。挪到flow_data中？
    """

    page: Page = Field(title="应用程序当前页面描述", description="当前应用页面的描述")
    """同时支持string和Page类型。是否有必要统一约束为Page类型, 取决于Page的实现是否有必要足够复杂。TODO。"""

    task: str = Field(default="", title="任务描述", description="任务描述")
    """简单情况下, task初始化一次就够了。更多的实际情况下, task需要根据middle info的情况动态生成, 通过arun传入。"""

    action_set: list[str] = Field(title="动作空间", description="动作空间")
    """通常需要定制化。虽然可以有缺省值ALL_ACTIONS, 但还是不要用缺省值。"""

    note: list[str] | None = Field(default=None, title="注意事项", description="注意事项")
    """这个字段非必要不要使用。重要信息尽量放到上面的字段中。"""

    async def arun(
        self, 
        image: str, 
        image_format: str, 
        *,
        task: str | None = None,
        output_prompt: str = ACTION_OUTPUT_PROMPT_PLAIN,
        model: str,
        client: AsyncOpenAI,
        ) -> tuple[UIResult, str]:
        '''
        task: 任务描述。如果为空, 则使用self.task。否则, 用task覆盖self.task。
        '''
        if task is None:
            assert self.task != "", "task must not be empty when task is None"
        else:
            assert isinstance(task, str), f"task must be str, but got {type(task)}"
            self.task = task

        prompt = f"""你是一个手机应用的GUI agent. 给定当前手机应用页面的screenshot, 你需要在页面上执行相应的动作来完成用户任务. 以下是详细描述。
{nl_repr(self)}

{output_prompt}
"""
        
        response = await avlm(prompt, image, image_format, client=client, model=model)
        print("&"*100)
        print(response)
        print("&"*100)
        thought, action_content = parse_thought_and_action_content(response)
        # 这里从大模型出来的动作如果有Target，那么至此还只有target_name且有可能是个错的。
        # 还需要根据target_name到page中去查找并且设置成为action的target属性结构体。如果找不到，那么就报错。
        # 要把page的ui_element_name_to_ui_element送到parse_action里去搞。
        actions = parse_action(action_content, self.page.ui_element_name_to_ui_element)

        # TODO: 应该没有必要。删掉。
        width, height = get_image_dimensions(image)
        actions = norm_actions(actions, width, height)

        result = UIResult(
            raw_prompt=prompt,
            thought=thought,
            action_content=action_content,
            actions=actions,
            source="ui-tars"
        )
        
        return result, prompt


# 定制化的生成task description。现在可额外接受把actions_record也作为输入。让模型可以参考到之前它执行过的动作。
TaskGen = Union[
    Callable[[str, MiddleInfoType, List[Action]], str],
    Callable[[MiddleInfoType], str]
]

# input: xml, output: actions
# TODO: 有可能需要和 RPATask 关联起来。例如，通过其中的page来定制化实现，通过info_task拿到输入，通过其action_set来检验输出的actions。
RPAHandler = Callable[[str, MiddleInfoType], list[Action]]

# input: actions, output: 根据action的状态跳转
ActionStepMap = Callable[[list[Action]], tuple[StepType, UIStepStatus]]

class UIStepBase[S](metaclass=ABCMeta):
    ''''''

    def __init__(
        self, 
        step: StepType,
        ui_task: UITask, 
        action_map: ActionStepMap,
        *,
        middle_info_define: MiddleInfoDefineType | type[BaseModel] | None = None,
        task_gen: TaskGen | None = None,
        rpa_handler: RPAHandler | None = None, 
        enable_reflect: bool = False,
        ):
        '''
        middle_info_define允许类型为BaseModel, 为了兼容最简单的情况。
        TODO: 支持 set[BaseModel]
        '''
        self.step = step
        self.ui_task = ui_task
        self.action_map = action_map
        self.task_gen = task_gen

        if isinstance(middle_info_define, type) and issubclass(middle_info_define, BaseModel):
            middle_info_define = {get_class_id(middle_info_define) : middle_info_define}

        self.middle_info_define = middle_info_define or {}
        for k, v in self.middle_info_define.items():
            assert isinstance(v, type), f"middle_info_define 中字段 {k} 的类型为 {type(v)}，而不是 type"

        self.rpa_handler = rpa_handler
        if self.rpa_handler:
            assert callable(self.rpa_handler), f"rpa_handler 必须是可调用对象，而不是 {type(self.rpa_handler)}"

        self.enable_reflect = enable_reflect


    def middle_info_def(self) -> MiddleInfoDefineType:
        '''缺省不依赖于任何信息'''
        return self.middle_info_define


    def _validate_info_type(self, middle_info: MiddleInfoType) -> None:
        '''校验middle_info的类型是否符合定义。仅用于debug, 实际中没用'''
        assert isinstance(middle_info, dict), f"middle_info must be a dict, but got type {type(middle_info)}"

        for k, v in middle_info.items():
            if k not in self.middle_info_define:
                raise UIAgentInfoInvalidError((k, v), f"middle info的字段{k}未被包括在middle_info_define中")

            # 下面的检查非常严格，不允许str的输入，调试时不方便
            #if not isinstance(v, self.middle_info_define[k]):
            #    raise UIAgentInfoInvalidError((k, v), f"middle_info 中字段 {k} 的类型为 {type(v)}，而不是 {self.middle_info_define[k]}")

        # 验证middle_info_define中定义的字段是否都在middle_info中
        for k in self.middle_info_define.keys():
            if k not in middle_info:
                raise UIAgentInfoInvalidError((k, None), f"middle info define的字段{k}未被包括在middle_info中")


    def _validate_info(self, middle_info: MiddleInfoType) -> JudgeResult:
        '''校验信息可以很最复杂。架构还不清楚，先采用最灵活的方式，允许重载。
        缺省实现十分简单, 仅校验middle_info的类型是否符合定义。
        '''
        self._validate_info_type(middle_info)

        return JudgeResult(judgment=True, reason="缺省情况下认为middle info有效.")


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
                actions = self.rpa_handler(xml, middle_info)
                # TODO: 应该传入ui task的page，并通过其action_set检查actions是否合法
                width, height = get_image_dimensions(image)
                actions = norm_actions(actions, width, height)

                # TODO: 这里包了一个无意义的UITaskResult。应该支持返回list[Action]么？不确定。
                result = UIResult(raw_prompt="", thought="", action_content="", actions=actions, source="rpa")
                return result
            except Exception as e:
                print(f"rpa处理失败:{e}")
        if self.task_gen:
            # 判断task_gen是否支持actions_record，2个参数的就支持
            if isinstance(self.task_gen, Callable) and len(inspect.signature(self.task_gen).parameters) == 3:
                result, prompt = await self.ui_task.arun(image, image_format, task=self.task_gen(state.background_info, middle_info, state.actions_record), model=model, client=client)
            else:
                result, prompt = await self.ui_task.arun(image, image_format, task=self.task_gen(middle_info), model=model, client=client)
        else:
            result, prompt = await self.ui_task.arun(image, image_format, model=model, client=client)
        return result


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
        client: AsyncOpenAI,
        ) -> tuple[UIResult | str, StepType, UIStepStatus]:
        """执行该Step的UI任务。必须和PUIStep的保持一致。
        
        TODO: 这里的实现相当通用，是否需要禁止继承？似乎定制化_run_ui_task就足够了
        """

        step_status = UIStepStatus.WAIT_FOR_INFO

        is_info_valid = self._validate_info(middle_info)
        if not is_info_valid.judgment:
            # TODO: 这里的情况很微妙。info为None时，有可能用缺省值（例如缺省的车牌号）或者其它方式（例如走memory）。
            # TODO: 类似于run_nl中的情况。需要以说话的口吻回复用户，需要用llm。
            assistant_reply = is_info_valid.reason if isinstance(is_info_valid.reason, str) else "需要更多信息才能继续当前UI任务。"
            # TODO: 这句话确实应该进入消息历史，但此时并没有有效的nl_query, 只能单独增加一条assistant message。是否可行，需要验证。
            # self.state.update_nl_messages(assistant_reply)  
            return assistant_reply, self.step, UIStepStatus.WAIT_FOR_INFO

        step_status = UIStepStatus.RUNNING

        # TODO: 这里需要处理异常？
        result = await self._run_ui_task(image, image_format, xml, middle_info, state=state, model=model, client=client)        

        step, step_status = self.action_map(result.actions)

        # TODO: 增加eval 部分

        return result, step, step_status
