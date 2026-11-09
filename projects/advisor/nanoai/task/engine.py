"""
任务执行引擎模块 (Task Execution Engine)

这个模块提供了任务执行的核心功能，包括单个任务执行、批量任务执行和Worker框架。

主要功能：
1. 任务执行：提供execute/aexecute函数执行单个任务
2. 批量执行：支持execute_batch/aexecute_batch批量处理多个任务
3. Worker框架：提供LMWorker类作为构建agentic system的基础组件
4. 结果处理：提供batch_results_to_df将批量结果转换为DataFrame

核心组件：
- execute/aexecute: 单个任务执行函数，支持同步和异步
- execute_batch/aexecute_batch: 批量任务执行，支持进度条显示
- LMWorker: 基于语言模型的Worker实现
- batch_results_to_df: 批量结果转换为DataFrame的工具函数

设计理念：
- Worker是构建agentic system的基础，与Task配合使用
- Task是function declaration，Worker是function implementation
- Worker位于业务层，语义层级高于Model
- 支持灵活的Worker实现：基于Model、硬编码、或组合方式

架构层次：
- Model: LLM底层API封装，输入输出为message和response
- Worker: 通用任务执行器，输入输出为任意类型
- Workflow: Worker和硬编码的任意组合
- Agent: 可以使用Worker作为tools

使用示例：
    # 单个任务执行
    result = execute("分析这段文本", task, output_type=str)
    
    # 批量任务执行
    results = execute_batch(
        inputs=["文本1", "文本2"],
        task_outputs=[(task1, str), (task2, dict)],
        progress_desc="批量处理"
    )
    
    # Worker使用
    worker = LMWorker(task, output_type=str)
    result = worker.execute("输入文本")
    
    # 结果转换为DataFrame
    df = batch_results_to_df(inputs, tasks, results)

特点：
- 支持同步和异步执行
- 内置错误处理和超时机制
- 支持进度条显示
- 灵活的输出类型支持
- 可扩展的Worker框架
"""

import traceback
from typing import Any, Callable, Iterable, Sequence, Type

import pandas as pd
from openai import APITimeoutError
from tqdm import tqdm

from nanoai.model.llm import (
    llm,
    allm,
    llm_output,
    allm_output,
    OpenAI,
    AsyncOpenAI,
)
from nanoai.task.common import JudgeResult
from nanoai.task.define import Task
from nanoai.utils.async_utils import map, amap, with_param_parse, with_param_parse_async
from nanoai.utils.nl_repr import nl_repr

# 默认超时时间（秒）
DEFAULT_TIMEOUT: float = 10.0

__all__ = [
    "TaskInputError",
    "DEFAULT_TIMEOUT",
    "execute",
    "aexecute",
    "execute_batch",
    "aexecute_batch",
    "batch_results_to_df",
    "LMWorker",
]


class TaskInputError(Exception):
    """任务输入错误。"""

    def __init__(self, input: Any, reason: str):
        self.input = input
        self.reason = reason
        super().__init__(f"输入'{input}'不符合要求，理由: {reason}")


def execute[OT](
    input: str,
    task: Task | str,
    output_type: Type[OT] = str,
    /,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    **kwargs,
) -> OT:
    """
    执行单个任务的通用API，是底层模型的轻量级封装。

    Args:
        input: 输入数据，可以是字符串或其他可迭代对象（如列表、字典等）。
        task: 任务定义，可以是 Task 实例或字符串（推荐使用 Task）。
        output_type: 期望的输出类型，默认为 str。可以是 str 或结构化类型。
        timeout: 超时时间（秒），默认{DEFAULT_TIMEOUT}秒。
        **kwargs: 其他传递给底层模型的参数。

    Returns:
        output_type 类型的结果。

    Raises:
        AssertionError: 输入类型不符合要求时抛出。
        Exception: 底层模型执行失败时抛出。

    设计说明:
        - 隔离业务层与底层模型细节，便于未来扩展和维护。
        - 可扩展输入/输出校验、格式化、结果存储等功能。
    """
    # 确保timeout参数优先级高于kwargs中的timeout
    if 'timeout' in kwargs:
        del kwargs['timeout']
    
    sys_prompt = f"请完成下述任务：{nl_repr(task)}"
    if output_type is str:
        res = llm(
            input,
            sys_prompt,
            timeout=timeout,
            **kwargs,
        )
    else:
        res = llm_output(
            input,
            sys_prompt,
            output_type=output_type,
            timeout=timeout,
            **kwargs,
        )
    return res.output  # type: ignore


async def aexecute[OT](
    input: str,
    task: Task | str,
    output_type: Type[OT] = str,
    /,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    **kwargs,
) -> OT:
    """
    异步版本。
    
    Args:
        input: 输入数据，可以是字符串或其他可迭代对象（如列表、字典等）。
        task: 任务定义，可以是 Task 实例或字符串（推荐使用 Task）。
        output_type: 期望的输出类型，默认为 str。可以是 str 或结构化类型。
        timeout: 超时时间（秒），默认{DEFAULT_TIMEOUT}秒。
        **kwargs: 其他传递给底层模型的参数。
    """
    # 确保timeout参数优先级高于kwargs中的timeout
    if 'timeout' in kwargs:
        del kwargs['timeout']
    
    sys_prompt = f"请完成下述任务：{nl_repr(task)}"
    if output_type is str:
        res = await allm(
            input,
            sys_prompt,
            timeout=timeout,
            **kwargs,
        )
    else:
        res = await allm_output(
            input,
            sys_prompt,
            output_type=output_type,
            timeout=timeout,
            **kwargs,
        )
    return res.output  # type: ignore


def _generate_batch_params(
    inputs: Iterable[str],
    task_outputs: Sequence[tuple[Task | str, Type[Any]]],
    timeout: float,
    **kwargs,
) -> Iterable[tuple[tuple[Any, ...], dict[str, Any]]]:
    for input in inputs:
        for task, output_type in task_outputs:
            yield (
                (input, task, output_type),  # position 参数
                {"timeout": timeout, **kwargs}  # keyword 参数
            )


def execute_batch(
    inputs: Iterable[str],
    task_outputs: Sequence[tuple[Task | str, Type[Any]]],
    /,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    progress_desc: str | None = None,
    progress_unit: str = "it",
    progress_disable: bool = False,
    **kwargs,
) -> list[list[Any | Exception]]:
    """
    批量执行多个输入和多个任务，支持同步和异步模式。

    Args:
        inputs: 输入数据集。
        task_outputs: 任务集，每个元素是 (task, output_type) 的元组。
        timeout: 每个任务的超时时间（秒），默认{DEFAULT_TIMEOUT}秒。
        progress_desc: 进度条描述（可选）。
        progress_unit: 进度条单位（可选）。
        progress_disable: 是否禁用进度条（可选）。
        **kwargs: 其他传递给底层模型的参数。

    Returns:
        list[list[Any | Exception]]: 每个输入在每个任务下的输出结果，若任务执行失败则为异常对象。
    """
    # 确保timeout参数优先级高于kwargs中的timeout
    if 'timeout' in kwargs:
        del kwargs['timeout']
    
    try:
        total = len(inputs) * len(task_outputs)
    except:
        total = None
    pbar = tqdm(
            total=total, 
            desc=progress_desc or f"批量执行{len(task_outputs)}个任务", 
            unit=progress_unit, 
            disable=progress_disable)
    
    results_flat, stats = map(
        with_param_parse(execute),
        _generate_batch_params(inputs, task_outputs, timeout, **kwargs),
        progress=pbar
    )
    
    pbar.close()
    
    # 重新组织为二维结构
    all_results = []
    tasks_count = len(task_outputs)
    for i in range(0, len(results_flat), tasks_count):
        all_results.append(results_flat[i : i + tasks_count])
    
    return all_results


async def aexecute_batch(
    inputs: Iterable[str],
    task_outputs: Sequence[tuple[Task | str, Type[Any]]],
    /,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    progress_desc: str | None = None,
    progress_unit: str = "it",
    progress_disable: bool = False,
    **kwargs,
) -> list[list[Any | Exception]]:
    """
    异步版本。
    
    Args:
        inputs: 输入数据集。
        task_outputs: 任务集，每个元素是 (task, output_type) 的元组。
        timeout: 每个任务的超时时间（秒），默认{DEFAULT_TIMEOUT}秒。
        progress_desc: 进度条描述（可选）。
        progress_unit: 进度条单位（可选）。
        progress_disable: 是否禁用进度条（可选）。
        **kwargs: 其他传递给底层模型的参数。
    """
    # 确保timeout参数优先级高于kwargs中的timeout
    if 'timeout' in kwargs:
        del kwargs['timeout']

    try:
        total = len(inputs) * len(task_outputs)
    except:
        total = None

    pbar = tqdm(
        total=total, 
        desc=progress_desc or f"批量执行{len(task_outputs)}个任务", 
        unit=progress_unit, 
        disable=progress_disable)

    results_flat, stats = await amap(
        with_param_parse_async(aexecute),
        _generate_batch_params(inputs, task_outputs, timeout, **kwargs),
        progress=pbar
    )
    
    pbar.close()

    # 重新组织为二维结构
    all_results = []
    tasks_count = len(task_outputs)
    for i in range(0, len(results_flat), tasks_count):
        all_results.append(results_flat[i : i + tasks_count])

    return all_results


def batch_results_to_df(
    inputs: list[Any], tasks: list[Task | str], results: list[list[Any | Exception]]
) -> pd.DataFrame:
    """
    将批量任务的输入、任务和结果组织为DataFrame，便于展示和分析。

    Args:
        inputs: 输入数据列表。
        tasks: 任务列表（Task或str）。
        results: 每个输入和任务的结果，支持正常值或异常对象。

    Returns:
        pd.DataFrame: 结果表格，第一列为输入，后续列为各任务的自然语言结果。
    """
    df_data = []

    assert len(inputs) == len(results), f"inputs和results的长度不一致: {len(inputs)} != {len(results)}"

    for i, input in enumerate(inputs):
        row = [input]  # 第一列是输入
        for j, _ in enumerate(tasks):
            row.append(nl_repr(results[i][j]))  # 逐一向list添加每个task的结果
        df_data.append(row)

    # 构建列名：第一列是"输入"，后续列是task的描述
    columns = ["输入"] + [f"{nl_repr(task)}" for task in tasks]

    return pd.DataFrame(df_data, columns=columns)


class LMWorker[OT]:
    """
    使用language model完成原子任务的Worker。提供以下功能：
    - 基本的错误处理框架。可以扩充。
    - _prepare_input方法, 支持"任意形式的task输入"。这就意味着只能作单轮对话, 因为多轮对话只能输入str。

    它只做单轮对话，不需要交互，也就没有状态。因此，几乎等同于execute的绑定了input之外所有参数的partial版本。区别是额外提供了_prepare_input。
    目前的实现非常简单。允许派生类重载和扩充。
    它的派生类可以有状态，用于控制task, _prepare_input的行为。因此，在复杂情况下它比execute更方便。但语义的本质相同。

    由于通用的"任意输入和输出"的接口和简单实现（单轮、无状态）, 这类worker粒度小，数量大，用途十分广泛。它们是构造agentic system的基本单位。
    """

    def __init__(
        self,
        task: Task | str,
        output_type: Type[OT],
        /,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        input_criterion: Callable[[str], JudgeResult] | None = None,
        model: str | None = None,
        client: OpenAI | None = None,
        async_client: AsyncOpenAI | None = None,
        **llm_params,
    ):
        """output_type这个参数解耦放在Worker而不是Task中，有如下好处:
        - 同样的Task语义可以有不同的输出格式。例如，结构化输出失败时，改为str输出。

        output_type参数是position only，因为其太重要，将来可能被修改。例如，其语义扩充为“Task的实现方式”。这就不仅仅包括output_type这个字段了。

        """
        assert isinstance(task, (Task, str)), f"task必须是Task或str, 不能是{type(task)}"

        # 确保timeout参数优先级高于llm_params中的timeout
        if 'timeout' in llm_params:
            del llm_params['timeout']

        self.task = task
        self.output_type = output_type
        self.input_criterion = input_criterion
        self.timeout = timeout

        self.model = model
        self.client = client
        self.async_client = async_client

        self.llm_params = llm_params


    @property
    def sys_prompt(self) -> str:
        """动态生成sys_prompt, 因为task可能在运行时变化。可以重载。"""
        return f"请完成下述任务：{nl_repr(self.task)}"


    def _prepare_input(self, input: str) -> str:
        """将execute的输入参数转换为给LLM的str输入。默认输入str。什么也不做。
        所有非"输入一个str"的Worker都需要重载这个方法。
        """

        assert isinstance(input, str), f"input必须是str, 不能是{type(input)}"

        if len(input) == 0:
            raise TaskInputError(input, "是空字符串。")

        if self.input_criterion:
            res = self.input_criterion(input)
            assert isinstance(res, JudgeResult), f"criterion的返回值必须是JudgeResult, 不能是{type(res)}"
            if not res:
                raise TaskInputError(input, res.reason)

        return input


    def execute(self, *args, **kwargs) -> OT:
        """TODO: 错误处理十分简单。还没想清楚。能处理的error情况处理掉，无法处理的再raise？"""
        try:
            # TODO: _prepare_input中作输入检查并raise。不太好处理。继续raise？
            input = self._prepare_input(*args, **kwargs)

            # 单轮对话。不维护对话历史。
            return execute(input, self.task, self.output_type, timeout=self.timeout, model=self.model, client=self.client, **self.llm_params)
        except APITimeoutError as e:
            # 专门处理超时异常
            self._status_desc = f"任务执行超时（{self.timeout}秒）: {str(e)}"
            raise e
        except Exception as e:
            # 处理其他异常
            self._status_desc = f"执行出错: {str(e)} \n {traceback.format_exc()}"
            raise e


    async def aexecute(self, *args, **kwargs) -> OT:
        """异步版本。"""
        try:
            # TODO: _prepare_input中作输入检查并raise。不太好处理。继续raise？
            input = self._prepare_input(*args, **kwargs)
            # 单轮对话。不维护对话历史。
            return await aexecute(input, self.task, self.output_type, timeout=self.timeout, model=self.model, client=self.async_client, **self.llm_params)
        except APITimeoutError as e:
            # 专门处理超时异常
            self._status_desc = f"任务执行超时（{self.timeout}秒）: {str(e)}"
            raise e
        except Exception as e:
            # 处理其他异常
            self._status_desc = f"执行出错: {str(e)} \n {traceback.format_exc()}"
            raise e
