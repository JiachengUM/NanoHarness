from typing import cast

from pydantic import BaseModel, Field

from nanoai.model.llm import llm_output
from nanoai.task.define import Task, _TaskT
from nanoai.utils.nl_repr import nl_repr

__all__ = [
    "generate_task",
    "validate_task",
    "reverse_criteria",
]


def generate_task(
    input: str,
    output_type_mode: bool = False,
    /,
    **kwargs,
) -> Task | _TaskT:
    """根据输入生成任务。
    当output_type_mode为False时，Task的output_type字段为str。
    当output_type_mode为True时，Task的output_type字段为自动生成的BaseModel。
    TODO: 目前的_TaskBase太复杂，criteria字段无法生成JsonSchema，无法被llm自动生成。
    """

    criteria = "对于input_criteria和output_criteria字段，请生成尽可能多的合理的要求。"
    # TODO: criteria可以作为参数传入。

    prompt = f"""给定任务的简要描述如下:\n{input}\n请生成一个任务的实例对象，以结构化的形式输出。
    对于所有给定的字段，包括detail, input_criteria, output_criteria, input_type, output_type等，都需要生成尽量详细准确的描述。
    """

    prompt += f"\n{criteria}"
    if not output_type_mode:
        res = llm_output(prompt, output_type=Task, **kwargs)
        return res.output
    elif output_type_mode is True:
        # 下面增加的prompt是必要的。否则生成过程会出错。
        prompt += "\n 对于input_type和output_type字段，请生成概念的定义。"
        res = llm_output(prompt, output_type=_TaskT, **kwargs)
        return res.output


class TaskValidateResult(BaseModel):
    """任务验证结果。"""

    is_valid: bool = Field(..., description="任务是否有效。")
    reasons: list[str] = Field(..., description="任务无效的原因。逐条列举原因。")


def validate_task(
    task: Task, /, **kwargs
) -> TaskValidateResult:
    """验证任务是否有效。"""
    assert isinstance(task, Task), f"task必须是Task, 不能是{type(task)}"

    prompt = f"""给定一个任务的简要描述如下:
{nl_repr(task)}

请判断这个任务的定义和各个字段的描述是否合理。不合理的地方请逐条列举。如果全部合理则任务有效，否则无效。以结构化的形式返回结果。"""
    res = llm_output(prompt, output_type=TaskValidateResult, **kwargs)
    
    return res.output


def reverse_criteria(task: Task, /, **kwargs) -> Task:
    """逐条将task的criterion改为相反的意思。返回一个新的task。
    实际业务中的用处应该不大。应该能用于一些测试的场合。
    语言模型的效果可能不稳定。不能无脑使用这个函数。需要人来确认效果。
    TODO: 抽象出一个类似于reverse之类的通用函数，对于任意输入，返回其相反的含义。如果不可行，返回None。
    """

    # 如果prompt仅仅是"将输入的文本改为相反的含义"，不work。
    # TODO: 这就引入了prompt自动优化的问题。
    
    prompt = "输入的文本如下: \n{text}\n请将其改为相反的含义。不要做任何解释和说明，直接返回改写后的文本。"
    opposite_criteria = [
        cast(str, llm_output(prompt.format(text=criterion), output_type=str, **kwargs).output) for criterion in task.output_criteria
    ]

    return Task(brief=task.brief, output_criteria=opposite_criteria)


def _check_task_input(
    input: str, task: Task, /, **kwargs
) -> tuple[bool, str]:
    # TODO: 如何处理多模态输入？
    """判断输入是否符合task的要求。
    这里其实可以增加input_validator参数，用于验证输入是否符合要求。但没有必要。
    这样的操作更轻量，需要定制化，放在task.execute中实现更合理。
    这个函数因为调用llm，更加重量级。
    TODO: 这个函数应该被移除。应该被input_criteria的metric实现代替。
    """
    assert isinstance(task, Task), f"task必须是Task, 不能是{type(task)}"

    assert isinstance(input, str), f"input必须是str, 不能是{type(input)}"
    # TODO: input参数类型扩充为泛型。这才是正确的做法。符合task的语义。

    
    # 下面的实现不work。希望llm能"请根据任务说明，推断合理的输入需要符合什么条件"难度过大。需要显式使用task.input_criteria。
    #     res = llm.run(f"""请判断一个任务的输入是否合理。
    # 该任务的说明如下：
    # {task.brief}
    # 输入为: {input}
    # 请根据任务说明，推断合理的输入需要符合什么条件，以json格式返回二元组
    # (是否符合条件:bool， 判断理由:str)。""")

    # 通过llm来判断输入是否符合要求，相当的不稳定。看下面的这个简单问题。
    # "1+1等于几？这个问题可以用True or False回答么"
    # 缺省model（qwen2.5-72b）的回答并不对：'1+1等于2。如果用True或False来回答"1+1等于2"这个命题，那么答案是True。'
    # DeepSeek V3和qwen3的回答是对的。

    if not task.input_criteria or len(task.input_criteria) == 0:
        return True, "input_criteria is empty, 无法检查输入是否符合要求"

    prompt = f"""
该任务对于输入的要求如下: {nl_repr(task.input_criteria)}

输入为: {input}

请根据任务说明和对于输入的要求，判断输入是否符合要求，以json格式返回二元组
 (是否符合要求:bool， 判断理由:str)。"""

    res = llm_output(prompt, output_type=tuple[bool, str], **kwargs)

    output = res.output

    assert len(output) == 2, f"res.output长度必须为2, 不能是{len(output)}"
    assert isinstance(output[0], bool), f"res.output[0]必须是bool, 不能是{type(output[0])}"
    assert isinstance(output[1], str), f"res.output[1]必须是str, 不能是{type(output[1])}"

    return output[0], output[1]
