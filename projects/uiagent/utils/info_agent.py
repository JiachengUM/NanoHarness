import copy

from pydantic import BaseModel, Field

from nanoai.model.llm import allm_output
from nanoai.utils._concept_meta import Concept, Attribute, AttributeType
from nanoai.utils.nl_repr import nl_repr

from projects.uiagent.utils.chat_agent import (
    ModelName, 
    TaskStatus,
    ChatTask,
    ChatAgentState,
    ChatAgentProfile,
    ChatAgent,
)


# TODO: 定义constraint，检查非法数据

# TODO: 写query_rewrite

# TODO: 增加对话round的实现


class InfoAgentState[IT, U](ChatAgentState[U]):
    '''信息提取助手的状态。'''
    
    info_result: IT | None = Field(default=None, description="信息提取结果")
    info_error_msgs: list[str] = Field(default_factory=list, description="信息提取时发生的错误信息")

    @property
    def is_info_good(self) -> bool:
        return len(self.info_error_msgs) == 0 and self.info_result is not None


class InfoAgent[IT, U](ChatAgent[InfoAgentState[IT, U], U]):
    def __init__(
        self,
        info_type: type[IT],
        /,
        *,
        model: ModelName = ModelName.DOUBAO_SEED_1_6_FLASH_250828,
        **llm_params,
    ):
        '''
        info_type: 可以是Concept的实例或者BaseModel的子类。
        如果是Concept的实例，则将其转换为BaseModel。
        如果是BaseModel的子类，则直接使用。
        '''

        if isinstance(info_type, Concept):
            self.info_type_concept = info_type
            self.info_type = info_type.to_pydantic_model(enforce_none_type=True)
        else:
            assert issubclass(info_type, BaseModel), f"info_type必须是BaseModel的子类, 不能是{type(info_type)}"
            self.info_type_concept = None
            self.info_type = info_type

        
        profile = ChatAgentProfile(name="信息搜集助手")
        task = ChatTask(
            brief=f"从和用户的交谈中获得如下信息。\n {nl_repr(self.info_type)}",
            guidelines=[
                # "你需要主动询问用户相关信息。",
                #"你需要判断用户提供的信息是否准确。",
                #"如果用户不愿意回答，你需要礼貌地询问。",
                ]
        )
        super().__init__(profile, model, state_cls=InfoAgentState[IT, U], task=task, **llm_params)


    def intro(self) -> str:
        return f"""你好，为了帮你完成任务，我需要以下信息，请提供。
{nl_repr(self.info_type)}"""


    @property
    def status_full(self) -> str:
        msg = super().status_full
        msg += f"\ninfo_result: {self.state.info_result}"
        return msg


    async def extract_info(self, input: str) -> None:

        # "严格遵守用户给出的信息。如果用户没有提供某个字段，你也不要提供。"
        # 有意思的是，上面的提示词并没有用。
        # 禁止模型提供“用户未提供的字段”的有效方式是: 让self.info_type中的字段的type是Optional。
        info_sys_prompt = f"""你是一个信息搜集助手。你的任务如下: {self.state.task.brief}.

请以json格式返回你所提取的信息。
"""

        # 信息提取任务是单独的，和对话任务共享消息历史。
        messages = copy.deepcopy(self.state.messages)
        assert self.state.messages[0]['role'] == "system", "result的第一个消息必须是system消息"
        messages[0] = {"role": "system", "content": info_sys_prompt}

        try:
            self.state.info_error_msgs = []
            self.state.info_result = None

            res = await allm_output(
                    input,
                    messages,
                    output_type=self.info_type,
                    model=self.model, 
                    client=self.client, 
                    timeout=self.chat_timeout,
                    **self.llm_params
                )
            self.state.info_result = res.output
            self.check_info_result()

        except Exception as e:
            print(f"提取信息失败: {e}")
            self.state.info_result = None
            

    def check_info_result(self) -> None:
        assert self.state.info_result is not None

        if not isinstance(self.info_type_concept, Concept):
            # raise TypeError("info_type必须是Concept的实例")

            # 对于非Concept的情况不做检查。默认正确。仅仅用于简单情况的测试。
            return

        for attr in self.info_type_concept.attributes:
            value = getattr(self.state.info_result, attr.name)

            if attr.is_required and value is None:
                self.state.info_error_msgs.append(f"必需字段{attr.name}未提供")

    
    async def query_rewrite(self, input: str) -> str:
        # 基于info_error_msgs，改写query。

        if len(self.state.info_error_msgs) > 0:
            input = f"""用户的输入为: 
{input}

信息提取的任务尚未完成。错误信息如下:
{nl_repr(self.state.info_error_msgs)}

请根据上述信息生成给用户的回复:
"""
        return input

    
    async def before_model(self, input: str) -> str:
        await self.extract_info(input)

        if self.state.is_info_good:
            self.state.status = TaskStatus.SUCCESS
            return input
        else:
            return await self.query_rewrite(input)
