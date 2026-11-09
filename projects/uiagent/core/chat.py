import copy
from enum import StrEnum, Enum
from typing import Any, Callable, final

from pydantic import BaseModel, Field

from nanoai.model.config import AsyncOpenAI
from nanoai.model.llm import ChatCompletionMessageParam,allm_output
from nanoai.model.vlm import avlm_output_by_schema
from nanoai.model.llm import ChatCompletionSystemMessageParam
from nanoai.utils.data_concept import JudgeResult
from nanoai.utils.nl_repr import nl_repr
from projects.uiagent.utils.common_task import IntentClsResult

InfoValidator = Callable[[BaseModel | str | None], JudgeResult]

DEFAULT_LLM_PARAMS: dict[str, Any] = {
    "extra_body": {"thinking": {"type": "disabled", }}, }

def _replace_sys_prompt(
    messages: list[ChatCompletionMessageParam], sys_prompt: str
) -> list[ChatCompletionMessageParam]:
    """替换消息历史中的第一条sys_prompt并返回。"""
    the_copy_messages = copy.deepcopy(messages)
    if len(the_copy_messages) > 1:
        # assert the_copy_messages[0]["role"] == "system", "messages的第一个消息必须是system消息"
        if the_copy_messages[0]["role"] == "system":
            the_copy_messages = copy.deepcopy(the_copy_messages[1:])  # 去掉sys_prompt
    else:
        the_copy_messages = []
    the_copy_messages.insert(0, ChatCompletionSystemMessageParam(
        role="system", content=sys_prompt))
    return the_copy_messages

class IntentCategory(Enum):
    RELEVANT = ("Relevant", "用户输入和对话任务明显相关，意图清楚。")
    IRRELEVANT = ("Irrelevant", "用户输入和对话任务明显无关, 或者十分含糊。")
    ABORT = ("Abort", '用户明确表示想放弃任务, 例如"请退出"、"再见"等。')

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


def _default_info_gen(brief: str, info_type: type[BaseModel]) -> str:
    return f"""你是一个UIAgent信息搜集助手。
你正在进行如下信息提取任务：
{brief}
在仔细理解上述任务后，请从对话信息中提取以下信息:
{nl_repr(info_type)}
请以json格式返回。
"""


InfoGen = Callable[[str, type[BaseModel]], str]


class InfoTask(BaseModel):
    """InfoTask定义了单步信息提取任务。
    它调用llm(_output)完成。它输入str，输出结构化的数据进入workflow state。
    同一个workflow run_nl可以并行调用多个InfoTask。
    TODO: 现在的写法还不支持nl_repr的用法。
    """

    brief: str = Field(title="任务描述", description="任务描述")
    """TODO: 暂时还没真的用上。以后应该有用。"""

    info_type: type[BaseModel] = Field(title="信息类型", description="信息类型")

    validator: InfoValidator | None = Field(
        default=None, title="信息验证器", description="验证信息是否符合要求")

    exec_mode: InfoExecMode = Field(
        default=InfoExecMode.NL_ANY, title="执行模式", description="执行模式", repr=False)
    """repr=False, 不进入prompt。"""

    # frozen时，BaseModel会自动处理哈希和相等性
    model_config = {"frozen": True}

    info_gen: InfoGen = Field(
        default=_default_info_gen, title="信息提取器", description="信息提取器")

    """多模态模型提取信息"""
    @final
    async def arun_vlm(
        self,
        query: str,
        image: str,
        image_format: str,
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
        messages = _replace_sys_prompt(
            messages, self.info_gen(self.brief, self.info_type))
        # 合并默认参数和用户传入的参数
        merged_kwargs = {**DEFAULT_LLM_PARAMS, **kwargs}
        # result = await allm_output(query, messages, output_type=self.info_type, model=model, client=client, **merged_kwargs)
        result = await avlm_output_by_schema(query,image,image_format,messages,output_type=self.info_type,model=model,client=client,**merged_kwargs,)
        return result

    """语言模型提取信息"""
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
        the_messages = _replace_sys_prompt(
            messages, self.info_gen(self.brief, self.info_type))
        # 合并默认参数和用户传入的参数
        merged_kwargs = {**DEFAULT_LLM_PARAMS, **kwargs}
        # result = await allm_output(query, messages, output_type=self.info_type, model=model, client=client, **merged_kwargs)
        result = await allm_output(query,the_messages,output_type=self.info_type,model=model,client=client,**merged_kwargs,)
        return result.output
