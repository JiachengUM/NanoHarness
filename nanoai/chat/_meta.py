from nanoai.model.llm import llm_output
from nanoai.task.define import Task
from nanoai.task.engine import LMWorker
from nanoai.utils._concept_meta import Concept

from .define import ChatAgentProfile, ChatTask

__all__ = [
    "generate_chat_agent_profile",
    "generate_chat_task",
    "UserProfileConceptGenerator",
]


def generate_chat_agent_profile(role: str, /, **kwargs) -> ChatAgentProfile:
    prompt = f"""根据如下信息
{role}

请生成一个对话智能体的角色描述。以结构化json的形式输出。所有字段尽量全面详细。"""

    res = llm_output(prompt, output_type=ChatAgentProfile, **kwargs)
    return res.output
    

def generate_chat_task(
    brief: str,
    /,
    **kwargs,
) -> ChatTask:
    """根据对话任务的简要描述生成对话任务。"""
 
    prompt = f"""根据下面的对话任务的简要描述:

{brief}

生成一个对话任务的实例，以结构化json的形式输出。所有字段尽量全面详细, 使得这个对话任务是明确的，可执行的。
    """

    res = llm_output(prompt, output_type=ChatTask, **kwargs)
    return res.output


class UserProfileConceptGenerator(LMWorker[Concept]):
    """生成针对某个给定任务的用户画像。注意这里的内容是通用的str，不仅限于ChatTask。原则上它可以是任何跟用户相关的描述。
    用LMWorker而不是llm API来实现，是因为可能能用到Task的output_criteria。
    TODO: 这个理由不太充分。可能还是需要使用llm API。和Task彻底解耦。
    """

    def __init__(self, /, **kwargs):
        super().__init__(
            Task(
                brief="根据输入的要求生成用户画像的定义。",
                output_criteria=[
                    "以结构化的方式描述用户的各种属性。",
                    "生成尽可能多的属性。将属性用处的说明放在其description字段中。",
                    "必须包括下述基本属性: 姓名、年龄、性别、职业、教育背景。它们都是必填的。",
                ],
            ),
            Concept,
            **kwargs,
        )

    def _prepare_input(self, task: str, /) -> str:
        assert isinstance(task, str), f"task must be str, but got {type(task)}"
        return f"""下面是一个任务的说明:
{task}

请生成这个任务所面向的用户的画像。"""
