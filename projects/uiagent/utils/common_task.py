from enum import Enum
from pydantic import BaseModel, Field
from typing import Any
from nanoai.model.messages import ChatCompletionMessageParam
from nanoai.utils.nl_repr import nl_repr
from nanoai.model.llm import allm,allm_output
from nanoai.model.messages import QAList
from nanoai.model.config import AsyncOpenAI


__all__ = [
    "IntentRelevanceCategory",
    "IntentClsResult",
    "intent_classify",
]

class IntentRelevanceCategory(Enum):
    RELEVANT = ("Relevant", "用户输入和对话任务明显相关，意图清楚。")
    IRRELEVANT = ("Irrelevant", "用户输入和对话任务明显无关, 或者十分含糊。")
    ABORT = ("Abort", "用户明确表示想放弃任务, 例如\"我要走了\"、\"再见\"等。")


class IntentClsResult(BaseModel):
    """对于用户输入的意图分类结果。"""

    category: str = Field(..., description="用户意图的类别。")
    """可以用于业务逻辑。"""

    reason: str = Field(..., description="判断属于该类别的原因。")
    """目前只用于debug/log，帮助人理解模型的想法，还不能用于业务逻辑。"""
    
    thinking: str = Field(..., description="如何回复用户的内心思考。注意，不是回复的内容。")
    """可以用于后续回复的prompt，还可以用于debug/log，帮助人理解模型的想法。"""

    response: str = Field(..., description="回复用户的内容。")
    """用于直接回复用户。在某些cateogry下是直接可用的, 例如ABORT。"""

    @staticmethod
    def output_prompt() -> str:
        """用于提示模型输出该类型的prompt。"""
        return "请以json格式返回类别名称, 判断原因, 如何回复用户的思考, 以及回复用户的内容。"


async def intent_classify(
        input: str,
        categories: list[tuple[str, str]] = [intent.value for intent in IntentRelevanceCategory],  
        /, 
        *,
        task: Any = None, 
        history: list[ChatCompletionMessageParam] | None = None, 
        output_type: type[str] | None = None,
        model: str,
        client: AsyncOpenAI,
        timeout: float | None = None, 
        **kwargs) -> str | IntentClsResult:
    """对用户输入进行意图分类。
    
    Args:
        input: 用户的输入文本，需要被分类的原始输入
        categories: 意图类别列表，每个元素为(类别名称, 类别描述)的元组。缺省为IntentCategory。
        task: 任务的定义
        history: 历史对话消息列表，用于提供上下文信息。如果为None或空，则无历史对话。
        TODO: 这里的history不包括sys prompt。实现也并没有sys prompt, 而是直接写入user prompt。这样啰嗦,也不干净。应该改成正常对话历史的使用方式。
        output_type: 输出类型，支持 str（简单字符串） 或者结构化输出。缺省为None，表示IntentClsResult。
        timeout: LLM调用的超时时间（秒），如果为None则使用默认超时
        **kwargs: 传递给LLM的其他参数，如model、temperature等

    还不够通用。TODO:
    拓宽categories的类型
    拓宽history的类型
    output_type支持任意结构化类型输出
    
    Returns:
        IntentClsResult: 意图分类结果
    """
    assert isinstance(categories, list), f"categories must be list, but got {type(categories)}"

    if task is None:
        task_str = "对话任务为闲聊。无特别目的。"
    else:
        task_str = "对话任务的说明如下:\n" + nl_repr(task)

    if history is None or len(history) == 0:
        msg_str = "无历史对话信息。"
    else:
        msg_str = "历史对话信息如下:\n" + QAList.from_messages(history).format()

    assert output_type is str or output_type is None, f"output_type must be str or None, but got {type(output_type)}"
    if output_type is str:
        output_prompt = "请仅仅返回类别名称。"
    else:
        output_prompt = IntentClsResult.output_prompt()

    prompt = f"""你需要判断对话任务中的用户意图。

{task_str}

{msg_str}

用户的当前输入为:
{input}。

请对于用户输入的意图作分类。类别的名称和描述如下:
{"\n".join([f"{name}: {description}" for name, description in categories])}

{output_prompt}
"""

    if output_type is str:
        res = await allm(prompt, client=client, model=model, timeout=timeout, **kwargs)
        category = res.output
    else:
        res = await allm_output(prompt, output_type=IntentClsResult, client=client, model=model, timeout=timeout, **kwargs)
        category = res.output.category

    assert category in [cat[0] for cat in categories], f"意图分类结果的类别{category}不在类别列表{categories}中"
    
    return res.output
