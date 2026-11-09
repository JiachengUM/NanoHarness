"""
任务通用功能模块 (Task Common Functions)

这个模块提供了任务执行中的通用功能，包括分类、判断和比较等基础操作。

主要功能：
1. 文本分类：提供classify/aclassify函数对文本进行分类
2. 条件判断：提供judge/ajudge函数判断文本是否符合某个条件
3. 比较判断：提供compare_judge/acompare_judge函数比较两个文本
4. 结果处理：提供ClsResult和JudgeResult等结构化结果类型

核心函数：
- classify/aclassify: 文本分类，支持列表和枚举类型
- judge/ajudge: 条件判断，支持True/False/None三种结果
- compare_judge/acompare_judge: 文本比较，判断两个文本是否相同

设计特点：
- 支持同步和异步操作
- 提供结构化的返回结果
- 支持多种分类方式（列表、枚举）
- 内置错误处理和结果验证
- 可扩展的prompt构建机制

使用示例：
    # 文本分类
    categories = [("正面", "积极评价"), ("负面", "消极评价")]
    result = classify("这个产品很好", categories)
    print(result.category)  # "正面"
    
    # 条件判断
    result = judge("今天天气很好", "天气晴朗")
    print(result.judgment)  # True/False/None
    
    # 文本比较
    result = compare_judge("文本1", "文本2", "判断是否相同")
    print(result.judgment)  # True/False/None
    
    # 使用枚举分类
    class Sentiment(StrEnum):
        POSITIVE = "positive"
        NEGATIVE = "negative"
    
    result = classify("很好", Sentiment)
    print(result.category)  # Sentiment.POSITIVE

应用场景：
- 情感分析：判断文本的情感倾向
- 内容分类：将文本分类到不同类别
- 质量评估：判断文本是否符合特定标准
- 相似性检测：比较两个文本的相似性
- 条件验证：验证输入是否满足特定条件
"""

from enum import StrEnum
from typing import Type, cast

from nanoai.model.llm import llm_output, allm_output
from nanoai.utils.data_concept import ClsResult, JudgeResult

__all__ = [
    "classify",
    "aclassify",
    "judge",
    "ajudge",
    "compare_judge",
    "acompare_judge",
]


def _build_classify_prompt(
    input: str, categories: list[tuple[str, str]] | Type[StrEnum], cls_action: str
) -> tuple[str, bool]:
    """构建分类prompt的通用逻辑。返回(prompt, is_category_enum)"""
    is_category_enum = False

    if isinstance(categories, list):
        categories_str = "每个类别由二元组(name, description)表示:\n" + "\n".join(
            [f"{name}: {description}" for name, description in categories]
        )
    elif issubclass(categories, StrEnum):
        is_category_enum = True
        categories_str = "类别包括(" + ",".join([f"{name.value}" for name in categories]) + ")"
    else:
        raise ValueError(f"categories must be list[tuple[str, str]] or Type[StrEnum], but got {type(categories)}")

    prompt = f"""输入的文本如下:
{input}

请{cls_action}。类别的说明如下:
{categories_str}

请以json形式返回分类结果和分类原因。
"""
    return prompt, is_category_enum


def _process_classify_result(
    output: ClsResult, categories: list[tuple[str, str]] | Type[StrEnum], is_category_enum: bool
) -> ClsResult:
    """处理分类结果的通用逻辑"""
    if is_category_enum:
        categories_enum = cast(Type[StrEnum], categories)
        output.category = categories_enum(output.category)
    return output


def classify(
    input: str,
    categories: list[tuple[str, str]] | Type[StrEnum],
    cls_action: str = "对其分类",
    /,
    **llm_params,
) -> ClsResult:
    """对于输入的文本input分类，类别由categories描述。其为类别二元组(name, description)列表或者枚举类型。
    返回值是BaseModel，不是tuple (分类结果, 分类理由)。后者太脆弱。
    这个函数是很多高级函数的基础。目前的实现虽然简单，应该有很大的改进和扩充空间。
    """
    prompt, is_category_enum = _build_classify_prompt(input, categories, cls_action)
    res = llm_output(prompt, output_type=ClsResult, **llm_params)
    return _process_classify_result(res.output, categories, is_category_enum)


async def aclassify(
    input: str,
    categories: list[tuple[str, str]] | Type[StrEnum],
    cls_action: str = "对其分类",
    /,
    **llm_params,
) -> ClsResult:
    """异步版本的classify函数。"""
    prompt, is_category_enum = _build_classify_prompt(input, categories, cls_action)
    res = await allm_output(prompt, output_type=ClsResult, **llm_params)
    return _process_classify_result(res.output, categories, is_category_enum)


def _build_judge_prompt(input: str, predicate: str) -> str:
    """构建判断prompt的通用逻辑"""
    action = f"判断输入是否{predicate}, 并给出判断理由。"
    return f"""输入的文本如下:
{input}

请{action}。

请以json格式返回判断结果和判断理由。
"""


def _build_judge_categories() -> list[tuple[str, str]]:
    """构建判断分类的通用逻辑"""
    return [
        ("True", "输入可以用True来判断或者回答"),
        ("False", "输入可以用False来判断或者回答"),
        ("None", "输入无法用True or False来判断或者回答"),
    ]


def _process_judge_classify_result(res: ClsResult) -> JudgeResult:
    """处理判断分类结果的通用逻辑"""
    if res.category == "True":
        return JudgeResult(judgment=True, reason=res.reason)
    elif res.category == "False":
        return JudgeResult(judgment=False, reason=res.reason)
    else:
        assert res.category == "None", f"Unexpected output: {res.category}"
        return JudgeResult(judgment=None, reason=res.reason)


def judge(input: str, predicate="正确", /, *, use_classify=False, **kwargs) -> JudgeResult:
    """判断输入的文本描述是否符合某个predicate，并给出理由。
    input: 输入的文本描述。
    TODO: 输入的类型可以扩充为任意类型。内部使用nl_repr来处理。有必要么? 还是在外面做更好？

    predicate: 判断的谓词。需要是"input的某种属性"。
    TODO: 这个参数的语义非常重要。保持其为positional only。注意此时partial绑定会失败，会绑定到kwargs中。

    这个函数是否鲁棒并为经过充分测试，更多是为了演示"不同的写法"。业务中使用时请谨慎测试。
    当use_classify为True时，会调用classify间接实现。代码更通用。
    当use_classify为False时，会直接调用llm。代码更灵活。
    尽管这两种写法很相似，在测试中能看到结果仍然有差异。
    说明语言模型对prompt很敏感，并不稳定。即使问题是非常简单的"是否能用True or False回答"。
    （default qwen2.5-72b）语言模型的逻辑并不够好。
    """
    if use_classify:
        categories = _build_judge_categories()
        action = f"判断输入是否{predicate}, 并给出判断理由。"
        res = classify(input, categories, action, **kwargs)
        return _process_judge_classify_result(res)
    else:
        prompt = _build_judge_prompt(input, predicate)
        res = llm_output(prompt, output_type=JudgeResult, **kwargs)
        return res.output


async def ajudge(input: str, predicate="正确", /, *, use_classify=False, **kwargs) -> JudgeResult:
    """异步版本的judge函数。"""
    if use_classify:
        categories = _build_judge_categories()
        action = f"判断输入是否{predicate}, 并给出判断理由。"
        res = await aclassify(input, categories, action, **kwargs)
        return _process_judge_classify_result(res)
    else:
        prompt = _build_judge_prompt(input, predicate)
        res = await allm_output(prompt, output_type=JudgeResult, **kwargs)
        return res.output


def _build_compare_judge_prompt(input1: str, input2: str, cmp_action: str) -> str:
    """构建比较判断prompt的通用逻辑"""
    return f"""输入的两段文本如下:
文本1: {input1}
文本2: {input2}

请{cmp_action}。

请以json格式返回判断结果和判断理由。
"""


def compare_judge(
    input1: str,
    input2: str,
    cmp_action: str = "判断两者是否相同",
    /,
    **llm_params,
) -> JudgeResult:
    """判断两个输入的文本描述是否相同，并给出理由。
    input0/input1: 输入的文本描述。
    cmp_action: 比较的动作描述。
    """
    prompt = _build_compare_judge_prompt(input1, input2, cmp_action)
    res = llm_output(prompt, output_type=JudgeResult, **llm_params)
    return res.output


async def acompare_judge(
    input1: str,
    input2: str,
    cmp_action: str = "判断两者是否相同",
    /,
    **llm_params,
) -> JudgeResult:
    """异步版本的compare_judge函数。"""
    prompt = _build_compare_judge_prompt(input1, input2, cmp_action)
    res = await allm_output(prompt, output_type=JudgeResult, **llm_params)
    return res.output
