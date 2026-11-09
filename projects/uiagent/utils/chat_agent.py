import contextlib
from enum import StrEnum
from typing import (
    Any,
    AsyncGenerator,
    final,
    Literal,
)

from pydantic import BaseModel, Field

from nanoai.model.config import ModelName, create_client
from nanoai.model.llm import (
    ChatCompletionMessageParam,
    AsyncOpenAI,
    allm,
    allm_stream,
    RunResult,
    RunResultStreamAsync,
    ChatCompletionSystemMessageParam,
)
from nanoai.utils.nl_repr import nl_repr
from nanoai.chat.define import ChatAgentProfile

from projects.uiagent.utils.common_task import IntentRelevanceCategory, IntentClsResult, intent_classify

__all__ = [
    "TaskStatus",
    "ChatTask",
    "ChatAgentState",
    "ChatAgent",
]


class TaskStatus(StrEnum):
    """这里提供最常见的状态定义。它们如何处理和转移取决于智能体的设计。没有统一通用的标准。"""

    RUNNING = "任务执行中"
    """最常见的状态。通常有多种子状态，并对应于不同的action。细致的定义由智能体自行决定。"""

    SUCCESS = "任务完成"
    """成功完成任务。结束对话。"""

    FAIL = "任务执行失败"
    """任务失败(例如超过预设对话轮数)。结束对话。"""

    ERROR = "任务执行发生错误"
    """执行任务时发生错误。通常有多种子状态。细致的定义由智能体自行决定。"""

    ABORTED = "任务中止"
    """任务中止(例如用户取消)。"""


class ChatTask(BaseModel):
    """对话任务的通用定义。它和ChatAgentProfile之所以区分开，是因为同一个AgentProfile可以复用到不同的任务。"""
    brief: str = Field(
        ...,
        title="对话任务",
        description="对话任务的简述。要明确体现出需要帮助用户达成什么目标。不包括'怎么做'。不要过于详细，不要换行。",
    )

    guidelines: list[str] = Field(
        default_factory=list,
        title="关于对话的要求(共{len_list}条)",
        description="关于智能体如何进行对话的要求。列表中的每一条要求需要清晰，独立，其效果可以被量化。",
    )
    """这是开发者需要说明的重点。对于Worker, Evaluator等功能有用，是其prompt的一部分。"""

    detail: str | None = Field(
        default=None,
        title="任务详述",
        description="关于各种任务细节的描述。其它字段不能描述的内容都可以放在这里。",
    )
    """这个字段用于做各种任务描述的定制化。例如，一步一步怎么做的详细说明。
    TODO: 足够通用重要的内容可以放在新的字段中。例如，"怎么做"可以变为how_to字段，将来用于子任务的拆解和连接。
    """


class ChatAgentState[U](BaseModel):
    ''' agent的运行时状态。'''

    status: str = Field(default=TaskStatus.RUNNING, description="任务执行过程中的状态。")
    '''状态的描述。str最通用。TODO: 是否值得局限为StrEnum? 感觉可行。目前还没必要。'''

    task : ChatTask
    user : U | None = Field(default = None)
    '''必须是私有变量, 因为会影响sys prompt。'''

    intent_cls_res: IntentClsResult | str | None = Field(default=None, description="用户意图分类结果")
    """意图分类结果。可以是IntentClsResult（结构化输出）或 str（简单字符串）。None表示未分类或者分类失败。"""

    messages: list[ChatCompletionMessageParam] = Field(default_factory=list, description="消息历史")

    @property
    def terminated(self) -> bool:
        '''任务是否结束。
        TODO: 简化为不是RUNNING就是结束。
        '''
        return self.status in [TaskStatus.SUCCESS, TaskStatus.FAIL, TaskStatus.ERROR, TaskStatus.ABORTED]


class ChatAgent[S, U]:
    """
    ChatAgent使用单个lmm完成多轮对话任务。通常是一个目标单一的任务。它是构建复杂对话应用的基本组件。
    S: 状态类型。必须是ChatAgentState的子类。
    它提供以下功能:
    - 状态管理: 任务的状态，对话历史等。
    - 用户画像理解，memory等。
    - 用户意图识别。

    泛型参数U：用户画像（user profile）类型。是更为通用的上下文类型的其中（也许最重要的）一种。
    C的实例可以在每次对话session开始时动态创建。在对话进行时可以被修改。
    用户画像会进入system prompt。因此只应该保存最重要和通用的信息。

    TODO: 这里的两个泛型参数是有问题的。U应该被耦合在S内部，但现在是分开的。
    """

    def __init__(
        self,
        agent_profile: ChatAgentProfile,
        model: ModelName,
        /,
        *,
        state_cls: type[S] = ChatAgentState,
        task: ChatTask | str = "协助用户完成任务",
        user: U | None = None,
        intent_cls_strategy: Literal["heavy", "light", "none"] = "heavy",
        **llm_params: Any,
    ):
        assert issubclass(state_cls, ChatAgentState), f"state_cls must be ChatAgentState的子类, but got {type(state_cls)}"
        assert isinstance(agent_profile, ChatAgentProfile), f"agent_profile must be ChatAgentProfile, but got {type(agent_profile)}"
        assert isinstance(task, (ChatTask, str)), f"task must be ChatTask or str, but got {type(task)}"

        # agent的算法参数。
        self.agent_profile = agent_profile
        self.client, self.model = create_client(model, AsyncOpenAI)
        self.llm_params: dict[str, Any] = llm_params

        assert intent_cls_strategy in ["heavy", "light", "none"], f"intent_cls_strategy must be 'heavy', 'light' or 'none', but got {intent_cls_strategy}"
        self.intent_cls_strategy = intent_cls_strategy
        self.augment_input_with_thinking: bool = True
        """是否在生成回复前，先思考一下。"""
        
        self.intent_timeout: float | None = 5.0
        self.chat_timeout: float | None = None
        

        # agent的状态。这部分将来可以解耦出去。
        if isinstance(task, str):
            task = ChatTask(brief=task)

        self.state_cls = state_cls
        self.state = self.state_cls(task=task, user=user)

        # 初始化sys_prompt
        self._update_sys_prompt()


    @property
    def name(self) -> str:
        return self.agent_profile.name

    @property
    def _sys_prompt(self) -> str:
        """需要动态生成。必须私有。"""

        prompt = f"""你是一个对话智能体。你的角色描述如下：
{nl_repr(self.agent_profile)}

你的任务如下:
{nl_repr(self.state.task)}
"""
        if self.state.user is not None:
            prompt += f"""\n和你对话的用户的信息如下:
{nl_repr(self.state.user)}

请参考上述信息, 针对性地回复用户。
"""

        return prompt
    

    @final
    def _update_sys_prompt(self) -> None:
        '''任何影响_sys_prompt的变量（如task, user）变化时，都需要调用这个函数。
        该函数的实现和内部细节深度耦合, 因此，不能被重载。
        例如，user core memory发生变化时。
        TODO: 这个函数可以进入state中, 传入_sys_prompt作为参数即可。参照core.WorkflowState。
        '''
        sys_prompt = ChatCompletionSystemMessageParam(role="system", content=self._sys_prompt)
         
        if self.state.messages:
            assert self.state.messages[0]['role'] == "system", "result的第一个消息必须是system消息"
            self.state.messages[0] = sys_prompt
        else:
            self.state.messages.append(sys_prompt)


    def update_user(self, user: U) -> None:
        '''这个API是否有用还不清楚。先这么设计。'''
        self.state.user = user
        self._update_sys_prompt()

    def update_task(self, task: ChatTask) -> None:
        '''这个API是否有用还不清楚。先这么设计。'''
        self.state.task = task
        self._update_sys_prompt()


    def intro(self) -> str:
        '''对话session刚开始时的欢迎语。这个方法仅仅是为了初始化自动对话, 不太重要。'''
        # TODO: 这里如果加入self.state.task.brief，会迷惑SimulatedChatUser。
        return f"""您好, 我是{self.name}。请开始和我对话吧。"""


    @property
    def status_full(self) -> str:
        """返回当前状态的详细描述。用于外部观测内部状态。很重要的API。
        TODO: 应该进入state中。目前还放在这里是为了兼容旧的ChatWorker。
        """
        if self.state.intent_cls_res is None:
            return f"{self.state.status}, 意图未分类。"
        else:
            return f"{self.state.status}, {nl_repr(self.state.intent_cls_res)}。"
        

    def details(self) -> list[str]:
        """不重要。仅仅为了兼容旧的ChatWorker。应该删掉"""
        s = [f"{self.__class__.__name__}\nsys prompt: {self._sys_prompt}\n状态:{self.status_full}"]

        return s
    

    def terminated(self) -> bool:
        """这个函数是多余的。目前还没有删掉仅仅为了兼容旧的ChatWorker"""
        return self.state.terminated


    def save_state(self) -> dict[str, Any]:
        '''这个函数基本就是多余的。目前还存在仅仅因为state放在哪儿还没想清楚'''
        return self.state.model_dump()
    

    def load_state(self, state: dict[str, Any]):
        '''这个函数基本就是多余的。目前还存在仅仅因为state放在哪儿还没想清楚'''
        self.state = ChatAgentState[U].model_validate(state)


    @final
    async def intent_cls(self, input: str) -> None:
        '''大量实现细节和其它函数耦合。不能被重载。'''

        if self.intent_cls_strategy == "none":
            return

        if self.intent_cls_strategy == "heavy":
            intent_cls_output_type = None
        else:
            assert self.intent_cls_strategy == "light", f"intent_cls_strategy must be 'heavy' or 'light', but got {self.intent_cls_strategy}"
            intent_cls_output_type = str

        try:
            self.state.intent_cls_res = await intent_classify(
                input,  
                task=self.state.task, 
                history=self.state.messages, 
                output_type=intent_cls_output_type,
                model=self.model,
                client=self.client,
                timeout=self.intent_timeout, 
                **self.llm_params
            )

            if intent_cls_output_type is str:
                category = self.state.intent_cls_res
            else:
                category = self.state.intent_cls_res.category

            # TODO: 还没想清楚在这里赋值_status是否合理。
            if category == IntentRelevanceCategory.ABORT.value[0]:
                self.state.status = TaskStatus.ABORTED

        except Exception as e:
            # TODO: 目前只是print，但需要处理。
            print(f"意图分类失败: {e}")
            self.state.intent_cls_res = None


    async def query_rewrite(self, input: str) -> str:
        '''
        非常重要的需要被重载的函数: 各种RAG, context增强，在这里补充。
        这里基类的实现跟intent_cls强耦合, 其实意思不大。
        '''
        if self.augment_input_with_thinking and isinstance(self.state.intent_cls_res, IntentClsResult):
            input = f"""用户的输入为: 
{input}

你的内心思考如下，请根据其生成给用户的回复:
{self.state.intent_cls_res.thinking}"""

        return input

    
    async def before_model(self, input: str) -> str:
        '''在执行模型之前调用。非常重要的需要定制化的函数。
        默认会改写input。
        '''
        await self.intent_cls(input)

        return await self.query_rewrite(input)


    @final
    async def aexecute(self, input: str, /) -> str:
        """执行对话任务的入口。会有大量的细致逻辑，应该不允许重载。
        TODO: 返回str是非常粗糙的。应该写入state，并返回。
        """
        assert self.state.status == TaskStatus.RUNNING, f"任务处于{self.state.status}状态, 而不是running, 不能chat"

        # TODO: input guardrail

        input = await self.before_model(input)

        # 这里的实现很简单粗暴，但似乎没问题。遗憾还不能和aexecute_stream统一，无法真的使用。
        # TODO: 这就引入了一个很本质的问题: 对话过程中如何确定结束条件并退出？
        if self.terminated():
            # status自身就是str message
            return self.state.status

        try:
            result = await allm(
                input,
                self.state.messages, 
                model=self.model, 
                client=self.client, 
                timeout=self.chat_timeout,
                **self.llm_params
            )

            self.state.messages = result.messages
            # 由于result是局部变量，这里无需deepcopy。

            return result.output

        except Exception as e:
            # 能返回的异常类型是确定的, 因此可以在这里枚举并且用不同的handler处理。这些handler可以被重载。
            # TODO: 这里的异常处理过于简单。可以写成error handler并重载。
            self.state.status = TaskStatus.ERROR

            # TODO: 这里可以选择不要raise，而是return错误信息。此时返回类型也要改为str。比较麻烦。先这样吧。
            # anyway总有可能要raise。没有必要内部处理错误。留给外部吧。
            raise e

        
    @final
    @contextlib.asynccontextmanager
    async def aexecute_stream(self, input: str, delta: bool) -> AsyncGenerator[RunResultStreamAsync, None]:
        """流式版本"""

        input = await self.before_model(input)

        # TODO: 非常尴尬。和aexecute不同，这里不能简单返回str，因为必须返回AsyncGenerator。怎么统一并不清楚。
        # 因此，目前还无法以统一的方式在execute中能优雅退出。
        # TODO: 有个很奇怪的想法。通过raise退出可以么？这似乎可以统一外部的处理方式。过于怪异。先放一放。
        #if self.terminated():
        #    return self.state.status_msg
        
        try:
            result_stream = await allm_stream(
                input,
                self.state.messages,
                delta=delta,
                model=self.model,
                client=self.client,
                timeout=self.chat_timeout,
                **self.llm_params,
            )
            yield result_stream

            # 注意，此处之后的代码在外面的with语句的__exit__()中才会执行，因为必须在with语句结束后才能访问self对象。

            self.state.messages = result_stream.messages
            # 由于result是局部变量，这里无需deepcopy。

            output = result_stream.output
            # 这个赋值是有意义的，外部可以通过result_stream.output获取最终结果。

        except Exception as e:
            # 能返回的异常类型是确定的, 因此可以在这里枚举并且用不同的handler处理。这些handler可以被重载。
            # TODO: 这里的异常处理过于简单。可以写成error handler并重载。
            self.state.status = TaskStatus.ERROR
            raise e
    

class SimulatedChatUser(ChatAgent[ChatAgentState, None]):
    """针对通用任务对话的虚拟用户。"""

    def __init__(
        self, 
        user_name: str, 
        desc: str, 
        /, 
        *, 
        topic: str | None = None, 
        model: ModelName = ModelName.DOUBAO_SEED_1_6_FLASH_250828,
        intent_cls_strategy: Literal["heavy", "light", "none"] = "heavy",
        **llm_params: Any,
        ):
        '''
        它基本就是一个ChatAgent。增加的参数都和虚拟用户相关。

        Args:
            desc: 用户信息。用自然语言描述。对于使用者很方便。
            topic: 对话主题。对话是由用户主导的，而不是AI助手。

        TODO: topic参数可以随时set。此时需要_update_sys_prompt。
        '''

        brief = f"""扮演{user_name}和对方对话。"""
        if topic is not None:
            brief += f"\n你想要对话的主题如下:\n{topic}"

        super().__init__(
            ChatAgentProfile(
                    name=user_name,
                    description=nl_repr(desc),
                ),
            model,
            task = ChatTask(
                brief=brief,
                guidelines=[
                    "你说的话需要严格忠实于你扮演的角色。不要虚构任何信息。",
                    "你需要配合对方完成对话任务, 让对话顺利流畅的进行。",
                ],
            ),
            intent_cls_strategy=intent_cls_strategy,
            **llm_params,
        )
