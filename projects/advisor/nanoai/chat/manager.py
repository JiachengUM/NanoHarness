"""聊天管理器模块，提供多Worker对话管理的核心功能。"""

# NOTE: 这个模块只是一个实验性的example，因为还没有足够的case用以抽象。实际使用的时候参照这里的写法即可。
import contextlib
import functools
from typing import Any, Callable, Final, Generator, Sequence, final

from nanoai.chat.define import ChatTask
from nanoai.chat.worker import ChatWorker, TaskStatus
from nanoai.model.llm import RunResultStream
from nanoai.model.messages import QAList

__all__ = [
    "MultiWorkerClsResult",
    "ChatManager",
]


def record_conversation(func: Callable) -> Callable:
    """
    装饰器：记录对话历史

    自动记录用户输入和助手输出到 _messages 中。
    适用于 execute 方法。
    """

    @functools.wraps(func)
    def wrapper(self: "ChatManager", input: str, *args, **kwargs):
        # 调用原始方法
        result = func(self, input, *args, **kwargs)

        # 记录对话历史
        assert hasattr(self, "_messages") and isinstance(self._messages, QAList)
        assert isinstance(input, str)
        assert isinstance(result, str)
        self._messages.append((input, result))
        return result

    return wrapper


def record_stream_conversation(func: Callable) -> Callable:
    """
    # TODO：test need to be done
    装饰器：记录流式对话历史

    专门用于 execute_stream 方法，在流式处理完成后记录完整的输出。
    """

    @functools.wraps(func)
    def wrapper(self: "ChatManager", input: str, *args, **kwargs):
        # 调用原始方法
        result = func(self, input, *args, **kwargs)

        # 对于流式输出，我们需要在生成器完成后记录
        assert hasattr(result, "__iter__")
        # 创建一个包装器来收集完整的输出
        collected_output = []

        def stream_wrapper():
            try:
                for item in result:
                    if hasattr(item, "output"):
                        collected_output.append(item.output)
                    yield item
            finally:
                # 在流式处理完成后记录对话历史
                if hasattr(self, "_messages") and isinstance(self._messages, QAList):
                    complete_output = "".join(collected_output)
                    if complete_output:  # 只有当有输出时才记录
                        self._messages.append((input, complete_output))

        return stream_wrapper()

    return wrapper


@final
class ChatManager:
    """
    常见的agent编排模式。请参见自身的任务说明。
    和ChatWorker的API基本一致, 代码也有重复。但没有必要继承ChatWorker。
    还处于实验阶段, 不能直接在生产环境中使用。
    因为其内部会尝试多种方式的实现, 方便对比效果。
    1. 和ChatWorker一样, 使用UserInputCls进行意图分类。
    2. 使用自身的结构化输出能力进行意图分类。
    """

    def __init__(self, workers: Sequence[ChatWorker], /):
        """workers: 多个对话Worker。负责不同的任务。
        由于这里的多个对话任务是动态决定的，无法再使用类型参数和作静态类型检查。必须假设所有worker的输出类型都是str。
        """

        self.current_worker: ChatWorker | None = None

        self.workers = workers
        # TODO: 一些必要的检查
        # 1. 所有worker的result_type都是str
        # 2. 所有worker的task没有overlap

        self.name_to_worker = {worker.name: worker for worker in self.workers}

        self.root_worker = ChatWorker(
            ChatTask(
                brief=f"""你负责管理多个对话智能体和用户的对话过程。你的职责如下:
- 充分理解这些专家的任务。
- 理解用户输入的意图, 将其输入转交给合适的专家处理。
- 用户意图不清楚或者超出专家的对话内容范围, 无法找到合适的专家时, 负责和用户对话。

{self._get_expert_briefs()}

请按照给定的json格式输出三个字段(用户意图的类别, 原因, 回复)。有如下几种情况:
1. 如果能明确判断用户输入和某个专家的任务相关, 请输出(相关, 判断的原因, 专家的角色描述)。
2. 如果用户的输入跟所有专家都不相关, 请输出(不相关， 不相关的原因，提醒用户回到和这些专家相关的任务上来)。
3. 如果用户明确表示想结束对话，请输出(结束， 判断退出的原因， 礼貌的告别)。
4. 如果用户的输入和各个专家的任务有些关系但模糊不清, 请输出(模糊, 难以判断的原因， 提醒用户重新描述清楚自己的问题)。""",
                agent_profile="对话管理员",
            ),
        )
        self.user_input_cls_res = None
        self.output_type: Final = str
        self._status = TaskStatus.RUNNING
        self._status_desc = "对话中"
        self._messages = QAList()

    @property
    def name(self) -> str:
        return self.root_worker.name

    @property
    def status_full(self) -> str:
        return self.root_worker.status_full

    @property
    def task(self) -> ChatTask:
        return self.root_worker.task

    def _get_expert_briefs(self) -> str:
        return f'''以下是所有专家的(编号, 角色描述, 任务说明)：
{'\n'.join(f'({i}, {worker.name}, {worker.task.brief})' for i, worker in enumerate(self.workers, 1))}'''

    def intro(self) -> str:
        """
        返回一个简短的自我介绍。一个helper方法。
        """
        return f"""您好, 自我介绍一下。我是一个智能体对话管理员, 能协助您和以下智能体专家进行对话：
{self._get_expert_briefs()}

        请开始和我对话吧。"""

    @record_conversation
    def execute(self, input: str) -> str:
        if self.current_worker is None:
            # NOTE：当前的实现下，专家never done，所以对话永远不会结束，导致意图无法切换。
            # 由管理员进行意图分类以及相应处理
            self.user_input_cls_res = self.root_worker.execute(input)

            if isinstance(self.user_input_cls_res, str):
                return self.user_input_cls_res


            match self.user_input_cls_res.category:
                case InputTaskRelevance.RELEVANT:
                    expert_name = self.user_input_cls_res.response
                    self.current_worker = self.name_to_worker.get(expert_name, None)
                    if self.current_worker is None:
                        raise ValueError(f"无法找到专家: {expert_name}")

                    self.current_worker._status_desc = f"当前专家: {expert_name} 承接对话"
                    res = self.current_worker.execute(input)
                    # check that res是被正常处理的
                    assert (
                        self.current_worker.status == TaskStatus.RUNNING
                    ), f"专家{expert_name}处理失败, with status: {self.current_worker.status_full}"
                    return res

                case InputTaskRelevance.IRRELEVANT:
                    self._status, self._status_desc = (
                        TaskStatus.RUNNING,
                        f"用户输入不相关: {self.user_input_cls_res.reason}",
                    )
                    return self.user_input_cls_res.response

                case InputTaskRelevance.AMBIGUOUS:
                    self._status, self._status_desc = (
                        TaskStatus.RUNNING,
                        f"用户输入模糊: {self.user_input_cls_res.reason}",
                    )
                    return self.user_input_cls_res.response

                case InputTaskRelevance.QUIT_TASK:
                    self._status, self._status_desc = (
                        TaskStatus.ABORTED,
                        f"用户表示放弃任务: {self.user_input_cls_res.reason}",
                    )
                    return self.user_input_cls_res.response

                case _:
                    raise ValueError(f"用户意图分类结果未被处理: {self.user_input_cls_res.category}")
        else:
            res = self.current_worker.execute(input)

            if self.current_worker.terminated():
                self._status_desc = f"对话由{self.current_worker.name}转交给管理员"
                self.current_worker = None

            return res

    @final
    @contextlib.contextmanager
    @record_stream_conversation
    def execute_stream(self, input: str, delta: bool) -> Generator[RunResultStream, None, None]:
        raise NotImplementedError("ChatManager不支持stream")

    def terminated(self) -> bool:
        return self.root_worker.terminated()

    def details(self) -> list[str]:
        res = [self._get_expert_briefs()]
        return res

    def save_state(self) -> dict[str, Any]:
        return {
            "current_worker": self.current_worker,
            "root_worker": self.root_worker.save_state(),
            "user_input_cls_res": self.user_input_cls_res,
            "_status": self._status,
            "_status_desc": self._status_desc,
            "workers": {name: worker.save_state() for name, worker in self.name_to_worker.items()},
            "_messages": self._messages,
        }

    def load_state(self, state: dict[str, Any]):
        self.current_worker = state["current_worker"]
        self.root_worker = self.root_worker.load_state(state["root_worker"])
        self.user_input_cls_res = state["user_input_cls_res"]
        self._status = state["_status"]
        self._status_desc = state["_status_desc"]
        self.workers = [self.name_to_worker[name].load_state(worker) for name, worker in state["workers"].items()]
        self._messages = state["_messages"]
