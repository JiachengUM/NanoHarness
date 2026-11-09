from typing import Any, Iterable, Sequence

import pandas as pd
from pydantic import BaseModel, Field
from tqdm import tqdm

from nanoai.task.common import JudgeResult
from nanoai.task.define import Task, TaskCase
from nanoai.task.engine import execute
from nanoai.utils.metric import DatumCriterion, is_async_function
from nanoai.utils.nl_repr import nl_repr

__all__ = [
    "TaskCaseGT",
    "CaseCriterion",
    "TaskEvalResult",
    "AccuracyStats",
    "evaluate_task_output",
    "evaluate_dataset",
    "aevaluate_dataset",
    "evaluation_results_to_df",
]


class TaskCaseGT[IT, OT](TaskCase[IT, OT]):
    """具有ground truth的测试用例数据。"""

    gt: OT | None = Field(default=None, description="任务的正确输出。如果为None，则不进行评估。")

    @property
    def description(self) -> str:
        """测试用例的自然语言描述。"""
        desc = f"输入: {self.input}\n输出: {self.output}"

        if self.comment is not None:
            desc += f"\n说明: {self.comment}"

        if self.gt is not None:
            desc += f"\n正确输出: {self.gt}"

        return desc


class CaseCriterion[IT, OT, MT](DatumCriterion[TaskCaseGT[IT, OT], MT]):
    """一个测试用例的评估标准。继承自DatumCriterion，固定数据类型为TaskCaseGT。"""

    # 继承自 DatumCriterion[TaskCaseGT[IT, OT], MT]，自动获得：
    # - description: str
    # - metric: Callable[[TaskCaseGT[IT, OT]], MT | Awaitable[MT]]
    # - params: dict[str, Any]
    # - run() 和 arun() 方法


class TaskEvalResult(BaseModel):
    """通用的任务评估的结果数据类型。"""

    output: str = Field(..., description="被直接复制的任务输出结果，不要做任何修改。")

    is_valid: bool = Field(..., description="输出结果是否符合该任务的要求")
    # TODO: 可以扩充为float score

    reasons: list[str] = Field(..., description="逐条列举出输出不符合任务要求的现象")

    def __str__(self) -> str:
        if self.is_valid:
            return f"输出结果'{self.output}'符合要求。"

        return f"输出结果'{self.output}'不符合要求。\n原因: {'\n'.join(self.reasons)}"


class AccuracyStats(BaseModel):
    """准确率统计信息"""

    accuracy: float
    correct: int
    total: int

    def __str__(self) -> str:
        return f"{self.accuracy:.2%} ({self.correct}/{self.total})"


def evaluate_task_output(
    output: str, input: str, task: Task, /, **kwargs
) -> TaskEvalResult:
    """评估任务执行结果的质量好坏。
    TODO: 还未经过充分测试，暂时不可用。

    Args:
        output: 任务的输出结果
        input: 任务的输入
        task: 要评估的任务定义
        model: 使用的模型名称
        client: OpenAI客户端
        **llm_params: 传递给LLM的其他参数

    Returns:
        TaskEvalResult: 评估结果
    """

    # assert output_type == str, f"task.output_type must be str, but got {type(task.output_type)}"

    # 创建评估任务
    eval_task = Task(
        brief=f"""你负责评估任务执行结果的质量好坏。这个任务的详细说明如下:
{nl_repr(task)}

请根据任务的输入、输出结果和关于输出结果的要求，逐条检查结果是否符合要求。
""",
        output_criteria=[
            "以json格式返回结构化的数据。",
        ],
    )

    eval_input = f"任务的输入为: {input}\n任务的输出结果为: {output}"

    result = execute(eval_input, eval_task, TaskEvalResult, **kwargs)

    return result


def _collect_case_info(dataset: Iterable[TaskCaseGT]) -> list[dict]:
    """收集case的基本信息"""
    case_info = []
    for case in dataset:
        case_info.append({
            "input": case.input,
            "output": case.output,
            "gt": case.gt,
            "comment": case.comment
        })
    return case_info


def _process_evaluation_results(
    all_results: list[list[Any]],
    case_info: list[dict],
    gt_criterion_results: list[Any | None],
    criteria: Sequence[DatumCriterion | CaseCriterion],
    gt_criterion: CaseCriterion | None = None,
) -> list[Any | AccuracyStats]:
    """处理评估结果，计算统计行"""
    stats_row: list[Any] = [f"正确率统计: {len(case_info)}个case", ""]  # 前两列（input, output）

    has_gt = any(info["gt"] is not None for info in case_info)
    has_comment = any(info["comment"] is not None for info in case_info)
    if has_gt:
        stats_row.append("")
    if has_comment:
        stats_row.append("")

    # gt_criterion正确率
    has_gt_criterion = gt_criterion is not None and has_gt
    if has_gt_criterion:
        gt_stats = _calc_accuracy(gt_criterion_results)
        stats_row.append(gt_stats)

    # 每个criterion的正确率
    for i, criterion in enumerate(criteria):
        criterion_results = [row[i] for row in all_results]
        criterion_stats = _calc_accuracy(criterion_results)
        stats_row.append(criterion_stats)

    return stats_row


def evaluate_dataset(
    dataset: Iterable[TaskCaseGT],
    criteria: Sequence[DatumCriterion | CaseCriterion],
    gt_criterion: CaseCriterion | None = None,
    /,
    *,
    progress_desc: str | None = None,
    progress_unit: str = "it",
    progress_disable: bool = False,
) -> tuple[list[list[Any]], list[dict], list[Any | None], list[Any | AccuracyStats]]:
    """评估数据集，返回原始评估结果和统计信息。

    Args:
        dataset: 包含测试用例的迭代器
        criteria: 评估标准列表
        gt_criterion: 与ground truth对比的评估标准
        progress_desc: 进度条描述（可选）
        progress_unit: 进度条单位（可选）
        progress_disable: 是否禁用进度条（可选）

    Returns:
        tuple: (评估结果矩阵, case信息列表, gt评估结果列表, 统计行)
            - 评估结果矩阵: list[list[Any]]，每个case在每个criterion下的评估结果
            - case信息列表: list[dict]，每个case的基本信息
            - gt评估结果列表: list[Any | None]，每个case的gt评估结果
            - 统计行: list[Any | AccuracyStats]，包含正确率等统计信息的数据行
    """
    # 默认描述
    if progress_desc is None:
        progress_desc = f"评估{len(criteria)}个标准"

    all_results = []  # 存储所有case的评估结果
    case_list = list(dataset)  # 转换为列表以便多次遍历

    # 计算总数用于进度条
    try:
        total_cases = len(case_list) * len(criteria)  # type: ignore
    except TypeError:
        total_cases = None

    with tqdm(total=total_cases, desc=progress_desc, unit=progress_unit, disable=progress_disable) as pbar:
        for case in case_list:
            case_results = []  # 当前case在所有criterion下的评估结果

            # 对每个criterion进行评估
            for criterion in criteria:
                try:
                    if isinstance(criterion, CaseCriterion):
                        # CaseCriterion评估整个case
                        result = criterion.run(case)
                    else:
                        # DatumCriterion只评估输出
                        result = criterion.run(case.output)
                except Exception as e:
                    result = e
                case_results.append(result)
                pbar.update(1)  # 更新进度条

            all_results.append(case_results)

    # 收集case信息
    case_info = _collect_case_info(case_list)

    # 处理GT criterion
    gt_criterion_results = []
    for case in case_list:
        if gt_criterion is not None and case.gt is not None:
            gt_result = gt_criterion.run(case)
        else:
            gt_result = None
        gt_criterion_results.append(gt_result)

    # 计算统计行
    stats_row = _process_evaluation_results(all_results, case_info, gt_criterion_results, criteria, gt_criterion)

    return all_results, case_info, gt_criterion_results, stats_row


async def aevaluate_dataset(
    dataset: Iterable[TaskCaseGT],
    criteria: Sequence[DatumCriterion | CaseCriterion],
    gt_criterion: CaseCriterion | None = None,
    /,
    *,
    progress_desc: str | None = None,
    progress_unit: str = "it",
    progress_disable: bool = False,
) -> tuple[list[list[Any]], list[dict], list[Any | None], list[Any | AccuracyStats]]:
    """异步版本"""
    import asyncio

    # 默认描述
    if progress_desc is None:
        progress_desc = f"评估{len(criteria)}个标准"

    async_tasks = []
    completed = 0
    total = 0
    case_list = list(dataset)  # 转换为列表以便多次遍历

    # 计算总数：包括所有评估标准和gt_criterion
    for case in case_list:
        for criterion in criteria:
            total += 1
        # 如果有gt_criterion且case有gt，也要计算
        if gt_criterion is not None and case.gt is not None:
            total += 1

    # 创建进度条
    pbar = tqdm(total=total, desc=progress_desc, unit=progress_unit, disable=progress_disable)

    async def evaluate_with_progress(case, criterion):
        nonlocal completed
        try:
            if isinstance(criterion, CaseCriterion):
                if is_async_function(criterion.metric):
                    result = await criterion.arun(case)
                else:
                    result = criterion.run(case)
            else:
                # DatumCriterion
                if is_async_function(criterion.metric):
                    result = await criterion.arun(case.output)
                else:
                    result = criterion.run(case.output)
        except Exception as e:
            result = e
        completed += 1
        pbar.update(1)
        return result

    # 创建所有评估标准的异步任务
    for case in case_list:
        for criterion in criteria:
            async_tasks.append(evaluate_with_progress(case, criterion))

    # 创建gt_criterion的异步任务
    gt_tasks = []
    gt_case_indices = []
    for i, case in enumerate(case_list):
        if gt_criterion is not None and case.gt is not None:
            gt_tasks.append(evaluate_with_progress(case, gt_criterion))
            gt_case_indices.append(i)

    # 执行所有任务（评估标准 + gt_criterion）
    all_tasks = async_tasks + gt_tasks
    all_results_flat = await asyncio.gather(*all_tasks, return_exceptions=True)
    pbar.close()

    # 分离评估结果和gt结果
    eval_results_flat = all_results_flat[: len(async_tasks)]
    gt_results_flat = all_results_flat[len(async_tasks) :]

    # 重新组织评估结果为二维结构
    all_results = []
    criteria_count = len(criteria)
    for i in range(0, len(eval_results_flat), criteria_count):
        all_results.append(eval_results_flat[i : i + criteria_count])

    # 收集case信息
    case_info = _collect_case_info(case_list)

    # 组织gt结果
    gt_criterion_results: list[Any | None] = [None] * len(case_list)  # 初始化为None
    for i, gt_result in zip(gt_case_indices, gt_results_flat):
        gt_criterion_results[i] = gt_result

    # 计算统计行
    stats_row = _process_evaluation_results(all_results, case_info, gt_criterion_results, criteria, gt_criterion)

    return all_results, case_info, gt_criterion_results, stats_row


def _calc_accuracy(results: list[Any]) -> AccuracyStats:
    """统计正确率、正确数、总数"""
    correct = 0
    total = 0
    for r in results:
        if r is not None:
            total += 1
            if isinstance(r, bool):
                if r:
                    correct += 1
            elif isinstance(r, JudgeResult):
                if r.judgment is True:
                    correct += 1
    accuracy = correct / total if total > 0 else 0.0
    return AccuracyStats(accuracy=accuracy, correct=correct, total=total)


def evaluation_results_to_df(  # noqa: C901
    case_info: list[dict],
    criteria: Sequence[DatumCriterion | CaseCriterion],
    eval_results: list[list[Any]],
    gt_results: list[Any | None],
    stats_row: list[Any],
    gt_criterion: CaseCriterion | None = None,
) -> pd.DataFrame:
    """将评估结果转换为DataFrame格式。

    Args:
        case_info: case信息列表
        criteria: 评估标准列表
        eval_results: 评估结果矩阵
        gt_results: gt评估结果列表
        stats_row: 统计行数据
        gt_criterion: 与ground truth对比的评估标准

    Returns:
        pd.DataFrame: 格式化的评估结果表格
    """
    # 构建完整的列顺序：case信息列 + gt_criterion列 + 评估标准列
    final_columns = ["input", "output"]  # 基础信息列

    # 条件性添加gt列：只有当至少有一个case有gt值时才添加
    has_gt = any(info["gt"] is not None for info in case_info)
    if has_gt:
        final_columns.append("gt")

    # 条件性添加comment列：只有当至少有一个case有comment时才添加
    has_comment = any(info["comment"] is not None for info in case_info)
    if has_comment:
        final_columns.append("comment")

    # 条件性添加gt_criterion列：只有当task有gt_criterion且至少有一个case有gt时才添加
    has_gt_criterion = gt_criterion is not None and has_gt
    if has_gt_criterion:
        final_columns.append("和gt对比")

    # 准备评估标准的列名
    column_names = [f"指标{i+1}:{nl_repr(c)}" for i, c in enumerate(criteria)]
    final_columns.extend(column_names)

    # 构建最终数据
    final_data = []
    for i, case in enumerate(case_info):
        row = [case["input"], case["output"]]

        # 条件性添加gt和comment
        if has_gt:
            row.append(case["gt"])
        if has_comment:
            row.append(case["comment"])

        # 条件性添加gt_criterion结果
        if has_gt_criterion:
            gt_result = gt_results[i] if i < len(gt_results) else None
            row.append(gt_result)

        # 添加评估结果
        for j, criterion in enumerate(criteria):
            result = eval_results[i][j] if i < len(eval_results) and j < len(eval_results[i]) else None
            row.append(result)

        final_data.append(row)

    # 添加统计行
    stats_data = []
    for cell in stats_row:
        if isinstance(cell, AccuracyStats):
            stats_data.append(str(cell))
        else:
            stats_data.append(cell)
    final_data.append(stats_data)

    # 创建最终的DataFrame
    final_df = pd.DataFrame(final_data, columns=final_columns)

    # 将统计行移动到第二行
    stats_row_data = final_df.iloc[-1].copy()  # 获取统计行数据
    final_df = final_df.iloc[:-1]  # 移除最后一行（统计行）

    # 插入到第二行位置
    final_df.loc[-1] = stats_row_data  # 添加到索引-1
    final_df.index = final_df.index + 1  # 所有索引加1
    final_df = final_df.sort_index()  # 重新排序，使统计行在第二行

    return final_df
