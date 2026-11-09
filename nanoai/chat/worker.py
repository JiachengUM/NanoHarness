"""聊天Worker模块，提供对话任务执行的核心功能。"""

import contextlib
from enum import Enum, StrEnum
from typing import (
    Any,
    Generator,
    AsyncGenerator,
    final,
)

import warnings

from pydantic import BaseModel, Field

from nanoai.chat.define import ChatAgentProfile, ChatTask
from nanoai.model.messages import ChatCompletionMessageParam, QAList
from nanoai.model.llm import (
    OpenAI,
    AsyncOpenAI,
    llm,
    allm,
    llm_stream,
    allm_stream,
    llm_output,
    allm_output,
    RunResult,
    RunResultStream,
    RunResultStreamAsync,
    ChatCompletionSystemMessageParam,
)
from nanoai.utils.nl_repr import nl_repr

__all__ = [
    "TaskStatus",
    "ChatWorker",
    "IntentCategory",
    "IntentClsResult",
    "intent_classify",
    "aintent_classify",
    "SimulatedChatUser",
]


class TaskStatus(StrEnum):
    """这里提供最常见的状态定义。它们如何处理和转移取决于智能体的设计。没有统一通用的标准。"""

    RUNNING = "running"
    """最常见的状态。通常有多种子状态，并对应于不同的action。细致的定义由智能体自行决定。"""

    DONE = "done"
    """完成任务。结束对话。"""

    ERROR = "error"
    """执行任务时发生错误。通常有多种子状态。细致的定义由智能体自行决定。"""

    ABORTED = "aborted"
    """任务中止(例如用户取消)。"""

class IntentCategory(Enum):
    RELEVANT = ("相关", "用户输入和对话任务明显相关，意图清楚。")
    IRRELEVANT = ("不相关", "用户输入和对话任务明显无关, 或者十分含糊。")
    ABORT = ("放弃", "用户明确表示想放弃任务, 例如\"我要走了\"、\"再见\"等。")


class IntentClsResult(BaseModel):
    """对于用户输入的意图分类结果。"""

    category: str = Field(..., description="用户意图的类别。")
    """可以用于业务逻辑。"""

    reason: str = Field(..., description="判断属于该类别的原因。")
    """目前只用于debug/log，帮助人理解模型的想法，还不能用于业务逻辑。"""
    
    thinking: str = Field(..., description="如何回复用户的内心思考。注意，不是回复的内容。")
    """可以用于后续回复的prompt，还可以用于debug/log，帮助人理解模型的想法。"""


def _intent_classify_prompt(
        input: str, 
        categories: list[tuple[str, str]], 
        task: ChatTask | str, 
        messages: list[ChatCompletionMessageParam] | None = None) -> str:
    """生成意图分类的prompt。"""
    assert isinstance(categories, list), f"categories must be list, but got {type(categories)}"

    if messages is None or len(messages) == 0:
        msg_str = "无历史对话信息。"
    else:
        msg_str = "历史对话信息如下:\n" + QAList.from_messages(messages).format()

    prompt = f"""你是一个对话任务的用户输入意图分类器。对话任务的说明如下：
{nl_repr(task)}

{msg_str}

用户的当前输入为:
{input}。
            
请对于用户的输入意图作分类, 给出判断原因, 并思考应该如何回复用户(注意，不是回复的内容)。

以下是各种类别的名称和描述:
{"\n".join([f"{name}: {description}" for name, description in categories])}
"""

    return prompt


def intent_classify(
        input: str, 
        categories: list[tuple[str, str]], 
        task: ChatTask | str, 
        messages: list[ChatCompletionMessageParam] | None = None, 
        /, 
        *, 
        timeout: float | None = None, 
        **kwargs) -> IntentClsResult:
    """对用户输入进行意图分类。完全通用的函数，甚至和这里的ChatWorker类无关。
    
    这个函数使用LLM来分析用户的输入，判断其与当前对话任务的相关性和意图。
    它是ChatWorker中意图识别功能的核心实现。
    
    Args:
        input: 用户的输入文本，需要被分类的原始输入
        categories: 意图类别列表，每个元素为(类别名称, 类别描述)的元组
                   例如：[("相关", "用户输入和对话任务明显相关"), ("不相关", "用户输入和对话任务明显无关")]
        task: 当前对话任务的定义，包含任务描述、输出标准等信息
        messages: 历史对话消息列表，用于提供上下文信息。如果为None或空，则无历史对话
        timeout: LLM调用的超时时间（秒），如果为None则使用默认超时
        **kwargs: 传递给LLM的其他参数，如model、temperature等
    
    Returns:
        IntentClsResult: 意图分类结果
    """
    prompt = _intent_classify_prompt(input, categories, task, messages)
    
    res = llm_output(prompt, output_type=IntentClsResult, timeout=timeout, **kwargs)

    # TODO: 这里需要验证res.output的category是否在categories中。如果不在，则需要给出错误信息。
    
    return res.output


async def aintent_classify(
        input: str, 
        categories: list[tuple[str, str]], 
        task: ChatTask | str, 
        messages: list[ChatCompletionMessageParam] | None = None, 
        /, 
        *, 
        timeout: float | None = None, 
        **kwargs) -> IntentClsResult:
    """异步版本"""
    prompt = _intent_classify_prompt(input, categories, task, messages)
    
    res = await allm_output(prompt, output_type=IntentClsResult, timeout=timeout, **kwargs)

    # TODO: 这里需要验证res.output的category是否在categories中。如果不在，则需要给出错误信息。
    
    return res.output

class ChatWorker[U]:
    """
    ChatWorker使用单个lmm完成多轮对话任务。通常是一个目标单一的任务。
    因此，它是构建复杂对话应用的基本组件。
    它提供以下功能:
    - 状态管理: 任务的状态，对话历史等。
    - 用户画像理解，memory等。
    - 用户意图识别。
    - 基本的错误处理框架。

    这个class的定位如下: 
    - 简单通用，和业务细节无关。因此，可作为通用chat bot用于要求不太高的业务场景。
    - 对于需要更强功能和定制化需求的业务场景。可以继承它，也可以参照其实现，
    
    因此，对于该class的代码质量要求会非常高。除了可用，还需要易读，易扩展。

    泛型参数U：用户画像（user profile）类型。是更为通用的上下文类型的其中（也许最重要的）一种。
    注意它和相关概念的联系和区别：
    - Task是全局静态的，而C的实例可以在每次对话session开始时动态创建。
    - 和worker的状态state（如对话历史）类似，在对话进行时，用户画像是可以被修改的。
    - 这里的用户画像会进入system prompt。因此只应该保存最重要和通用的信息。
    
    user profile的实现和具体应用是高度相关的。因此必须是泛型。
    选择把它放在基类中是因为，它会影响sys promot和消息历史。
    派生类可以自由地实现user profile，但需要了解基类的实现细节。
    不能假设基类了解派生类的实现，因此其实现需要非常通用才行，尽量少做假设。
    """

    def __init__(
        self,
        task: ChatTask | str,
        /,
        *,
        user: U | None = None,
        model: str | None = None,
        client: OpenAI | None = None,
        async_client: AsyncOpenAI | None = None,
    ):
        '''
        TODO: 增加timeout参数
        '''

        if isinstance(task, str):
            # 这种情况非常少见。通常都是直接传入ChatTask。
            # 有必要在这里生成ChatTask吗？感觉太复杂了。生成质量也不能保证。没必要。
            self.task = ChatTask(
                agent_profile=ChatAgentProfile(name='小娜', role='智能体对话助手', language_style='亲切友好'), 
                brief=task)
        else:
            self.task = task

        self._user = user
        '''必须是私有变量，因为会影响sys prompt。'''

        self.model = model
        self.client = client
        self.async_client = async_client

        self.llm_params = {}

        self.intent_cls_res: IntentClsResult | None = None
        """用户意图分类结果。注意它是通用的。"""

        self.augment_input_with_thinking: bool = True
        """是否在生成回复前，先思考一下。"""

        self._status: str = TaskStatus.RUNNING
        """任务执行过程中的状态。
        理论上, 状态的种类可以无穷多, action也是(虽然目前只有execute)。
        这是复杂问题。难以统一，也无必要。
        我们的原则是“自下而上, 保持简单”。警惕过度设计和过早抽象。不轻易增加复杂性。
        内部管理, 外部不可写。"""

        self._result: RunResult[str] | None = None
        self._result_stream: RunResultStream | None = None
        self._result_stream_async: RunResultStreamAsync | None = None
        """非流式和流式模式下的输出结果。实现很粗糙，还没想清楚。
        派生类不可访问。为None意味着任务还没有开始执行。这是RUNNING的初始状态, 也是一种子状态。
        TODO: 这里有个明显的设计问题。_result(_stream)中包括messages。这是内部状态，跟_result的语义其实是不符合的。
        它应该被显式地解耦出来，放到类似于state之类的结构中。目前不太紧要，待到需要更多内部状态时再考虑重构。
        涉及到对于整个llm模块输出做重构，比较麻烦。
        state被解耦出来之后，可能需要在类似于start_session的函数中初始化。
        """


    @property
    def name(self) -> str:
        return self.task.agent_profile.name

    @property
    def _sys_prompt(self) -> str:
        """sys promot需要动态生成。
        TODO: 目前的实现还不能做到真正的动态。因为_sys_prompt发生变化时，并未更新messages。
        增加一个函数_update_sys_prompt应该就可以了。
        """

        prompt = f"""你是一个对话智能体。对于你的要求如下：
{nl_repr(self.task)}
"""
        if self._user is not None:
            prompt += f"""\n和你对话的用户的信息如下:
{nl_repr(self._user)}

请参考上述信息, 针对性地回复用户。
"""
            
        # 类似于下面这样的prompt应该很重要，但怎么加入需要想清楚。直接加在这里很难维护。
        # "可以给予用户的信息做合理的推测，但切勿虚构没有任何事实依据的信息。例如，虚构用户的名字。"
        # 感觉需要在ChatTask中以某种结构化的方法来维护。

        return prompt
    

    @final
    def _update_sys_prompt(self) -> None:
        '''任何影响_sys_prompt的变量（如task, user）变化时，都需要调用这个函数。
        该函数的实现和内部细节深度耦合, 因此，不能被重载。
        很重要。支持高级功能的派生类通常都需要调用该函数。
        例如，user core memory发生变化时。
        '''

        # 得到最新的sys prompt
        prompt = self._sys_prompt

        # 更新消息历史中的第一条消息，其为sys prompt。
        # TODO: 这样就和llm模块的实现严重耦合。如何重构还不清楚。
        # _result和_result_stream的messages应该是共享的。待重构。

        if self._result is not None:
            assert self._result.messages[0]['role'] == "system", "result的第一个消息必须是system消息"
            self._result.messages[0] = ChatCompletionSystemMessageParam(role="system", content=prompt)

        if self._result_stream is not None:
            assert self._result_stream.messages[0]['role'] == "system", "result的第一个消息必须是system消息"
            self._result_stream.messages[0] = ChatCompletionSystemMessageParam(role="system", content=prompt)

        if self._result_stream_async is not None:
            assert self._result_stream_async.messages[0]['role'] == "system", "result的第一个消息必须是system消息"
            self._result_stream_async.messages[0] = ChatCompletionSystemMessageParam(role="system", content=prompt)


    def update_user(self, user: U) -> None:
        '''这个API是否真的有用还不清楚。但值得尝试。
        它是典型的需要调用_update_sys_prompt的场景。'''
        self._user = user
        self._update_sys_prompt()


    def intro(self) -> str:
        '''在对话session刚开始时的欢迎语。这个方法不太重要。'''
        return f"""您好, 我是{self.name}, 能完成如下任务：
{self.task.brief}。
请开始和我对话吧。"""


    @property
    def status_full(self) -> str:
        """返回当前状态的详细描述。用于外部观测内部状态。很重要的API。
        派生类通常需要重载。
        """
        if self.intent_cls_res is None:
            return f"{self._status}, 意图未分类。"
        else:
            return f"{self._status}, {nl_repr(self.intent_cls_res)}"
        

    def details(self) -> list[str]:
        """不太重要，随便写的。"""
        s = [f"{self.__class__.__name__}, sys prompt: {self._sys_prompt}, 状态:{self.status_full}"]

        return s
    
    def terminated(self) -> bool:
        """_status可能发生改变的地方:
        -: _think_post_process
        """
        return self._status in [TaskStatus.DONE, TaskStatus.ERROR, TaskStatus.ABORTED]


    def save_state(self) -> dict[str, Any]:
        '''运行时的状态准备落盘。很重要。目前的实现很随意。
        TODO: 将来需要单独抽象出state对象。IO也需要解耦出去。
        '''
        state_dict = dict()

        state_dict["_status"] = self._status
        state_dict["_intent_cls_res"] = self.intent_cls_res.model_dump() if self.intent_cls_res is not None else None
        
        state_dict["_user"] = self._user if self._user is not None else None
        '''TODO: 假设_user可以json化。比较危险。'''

        state_dict["_result"] = self._result.model_dump() if self._result is not None else None
        state_dict["_result_stream"] = self._result_stream.model_dump() if self._result_stream is not None else None
        state_dict["_result_stream_async"] = self._result_stream_async.model_dump() if self._result_stream_async is not None else None

        return state_dict
    

    def load_state(self, state: dict[str, Any]):
        '''恢复运行时的状态。继续。
        创建ChatWorker有两步。
        一是创建task, model, client等。这一步通常用代码或者config实现。
        二是load_state。这一步需要数据库或者文件。
        因此, 这个函数是有用的。'''
        self._status = TaskStatus(state["_status"])
        self.intent_cls_res = IntentClsResult.model_validate(state["_intent_cls_res"]) if state["_intent_cls_res"] is not None else None
        self._user = state["_user"] if state["_user"] is not None else None
        self._result = RunResult.model_validate(state["_result"]) if state["_result"] is not None else None
        self._result_stream = (
            RunResultStream.model_validate(state["_result_stream"]) if state["_result_stream"] is not None else None
        )
        self._result_stream_async = (
            RunResultStreamAsync.model_validate(state["_result_stream_async"]) if state["_result_stream_async"] is not None else None
        )


    def _think_post_process(self, input: str) -> str:
        assert isinstance(self.intent_cls_res, IntentClsResult), "意图分类结果不能为None"

        if self.intent_cls_res.category == IntentCategory.ABORT.value[0]:
            self._status = TaskStatus.ABORTED

        if self.augment_input_with_thinking:
            input = f"""用户的输入为: 
{input}

你的内心思考活动如下，请根据其生成给用户的回复:
{self.intent_cls_res.thinking}"""

        return input
    

    def _think(self, input: str) -> str:
        '''在执行execute生成回复前，先思考一下。
        可能会改写input并返回。例如作意图分类，rag，等等。
        非常重要的方法。派生类可以重载和定制化。
        '''
        try:
            self.intent_cls_res = intent_classify(
                input, 
                [intent.value for intent in IntentCategory], 
                self.task, 
                self._result.messages if self._result else None, 
                timeout=5, 
                **self.llm_params)
        except Exception as e:
            print(f"意图分类失败: {e}")
            return input
        
        return self._think_post_process(input)

    
    async def _athink(self, input: str) -> str:
        """异步版本"""
        try:
            self.intent_cls_res = await aintent_classify(
                input, 
                [intent.value for intent in IntentCategory], 
                self.task, 
                self._result.messages if self._result else None, 
                timeout=5, 
                **self.llm_params)
        except Exception as e:
            print(f"意图分类失败: {e}")
            return input
        
        return self._think_post_process(input)


    @final
    def execute(self, input: str, /) -> str:
        assert self._status == TaskStatus.RUNNING, f"任务处于{self._status}状态, 而不是running, 不能chat"

        # TODO: input guardrail

        input = self._think(input)

        try:
            self._result = llm(
                input,
                self._sys_prompt if self._result is None else self._result.messages, 
                model=self.model, 
                client=self.client, 
                **self.llm_params
            )
        except Exception as e:
            # 能返回的异常类型是确定的, 因此可以在这里枚举并且用不同的handler处理。这些handler可以被重载。
            # TODO: 这里的异常处理过于简单。可以写成error handler并重载。
            self._status = TaskStatus.ERROR

            # TODO: 这里可以选择不要raise，而是return错误信息。此时返回类型也要改为str。比较麻烦。先这样吧。
            # anyway总有可能要raise。没有必要内部处理错误。留给外部吧。
            raise e
        
        output = self._result.output
        return output
    
    @final
    async def aexecute(self, input: str, /) -> str:
        """异步版本"""
        assert self._status == TaskStatus.RUNNING, f"任务处于{self._status}状态, 而不是running, 不能chat"

        # TODO: input guardrail

        input = await self._athink(input)

        try:
            self._result = await allm(
                input,
                self._sys_prompt if self._result is None else self._result.messages, 
                model=self.model, 
                client=self.async_client, 
                **self.llm_params
            )
        except Exception as e:
            # 能返回的异常类型是确定的, 因此可以在这里枚举并且用不同的handler处理。这些handler可以被重载。
            # TODO: 这里的异常处理过于简单。可以写成error handler并重载。
            self._status = TaskStatus.ERROR

            # TODO: 这里可以选择不要raise，而是return错误信息。此时返回类型也要改为str。比较麻烦。先这样吧。
            # anyway总有可能要raise。没有必要内部处理错误。留给外部吧。
            raise e
        
        output = self._result.output
        return output


    @final
    @contextlib.contextmanager
    def execute_stream(self, input: str, delta: bool) -> Generator[RunResultStream, None, None]:
        """流式输出的版本"""

        input = self._think(input)
        
        try:
            self._result_stream = llm_stream(
                input,
                self._sys_prompt if self._result_stream is None else self._result_stream.messages,
                delta=delta,
                model=self.model,
                client=self.client,
                **self.llm_params,
            )
            yield self._result_stream

            # 注意，此处之后的代码在外面的with语句的__exit__()中才会执行，因为必须在with语句结束后才能访问self对象。
            output = self._result_stream.output
        except Exception as e:
            # 能返回的异常类型是确定的, 因此可以在这里枚举并且用不同的handler处理。这些handler可以被重载。
            # TODO: 这里的异常处理过于简单。可以写成error handler并重载。
            self._status = TaskStatus.ERROR
            raise e
        
    @final
    @contextlib.asynccontextmanager
    async def aexecute_stream(self, input: str, delta: bool) -> AsyncGenerator[RunResultStreamAsync, None]:
        """异步版本"""

        input = await self._athink(input)
        
        try:
            self._result_stream_async = await allm_stream(
                input,
                self._sys_prompt if self._result_stream_async is None else self._result_stream_async.messages,
                delta=delta,
                model=self.model,
                client=self.async_client,
                **self.llm_params,
            )
            yield self._result_stream_async

            # 注意，此处之后的代码在外面的with语句的__exit__()中才会执行，因为必须在with语句结束后才能访问self对象。
            output = self._result_stream_async.output
        except Exception as e:
            # 能返回的异常类型是确定的, 因此可以在这里枚举并且用不同的handler处理。这些handler可以被重载。
            # TODO: 这里的异常处理过于简单。可以写成error handler并重载。
            self._status = TaskStatus.ERROR
            raise e


from nanoai.chat._meta import UserProfileConceptGenerator, generate_chat_task
from nanoai.task.common_exp import ConceptInstanceGenerator
from nanoai.utils._concept_meta import Concept

class SimulatedChatUser(ChatWorker):
    """针对通用任务对话的虚拟用户。"""

    def __init__(self, desc: str, schema: list | str | None = None, /, *, topic: str):
        '''
        它基本就是一个ChatWorker。增加的几个参数都是和用户相关的。

        Args:
            desc: 用户信息。用自然语言描述。对于使用者很方便。
            schema: 是否创建用户。如果为True，则通过desc生成更加详细的用户画像。如果为False，则直接使用desc。
                缺省为True是为了提升对话质量。
            topic: 对话主题。对话是由用户主导的，而不是AI助手。

        TODO: topic参数可以随时set。此时需要_update_sys_prompt。
        TODO: schema的类型改为Concept | None。其实现拿到外面，和这个class解耦。如果为Concept，则将desc转换成其对应的BaseModel instance。
        '''

        if schema is not None:
            # TODO: 支持自定义的用户画像。
            warnings.warn("user schema is not implemented yet")
            pass
            # try:
            #     self.user_profile = UserProfileConceptGenerator(timeout=30).execute(
            #         f"""给定下述对话智能体的自我介绍:{chat_agent.intro()}\n生成这个对话任务所面向的用户画像"""
            # )

            #     assert isinstance(self.user_profile, Concept), f"user_profile必须为Concept, 而不是{type(self.user_profile)}"

            #     self.user_info = ConceptInstanceGenerator(self.user_profile).execute(
            #         user_simulated.user_info if user_simulated.user_info is not None else "请随机生成一个用户实例"
            #     )
            # except Exception as e:
            #     print(f"生成用户画像失败: {e}")
            #     self.user_info = user_simulated.user_info

        try:
            name = f"{getattr(desc, "name")}(虚拟用户)"
        except Exception:
            name = "虚拟用户"

        super().__init__(
            ChatTask(
                brief=f"""扮演虚拟角色，和另一个智能体助手对话。你想要对话的主题如下:\n{topic}""",
                guidelines=[
                    "你说的话需要严格忠实于你的角色。不要虚构任何信息。",
                    "你需要配合和你对话的智能体助手, 让对话顺利流畅的进行。",
                ],
                agent_profile=ChatAgentProfile(
                    name=name,
                    role="虚拟用户",
                    description=nl_repr(desc),
                ),
            ),
        )

