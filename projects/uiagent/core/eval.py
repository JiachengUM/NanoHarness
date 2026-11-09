"""通用评估器（Core Eval）

本模块提供与具体业务无关的评估通用逻辑：
- 定义评估结果数据结构（单步与工作流）
- 提供批量运行评估的工具函数（承接外部的 `run_step`/`run_workflow`）

设计目标：
- 与领域代码解耦：通过可调用对象 `run_step`、`run_workflow` 注入运行逻辑
- 简洁可复用：入参为可迭代数据集，返回标准化统计结果
- 便于集成：可选传入 `save_image_root`，由下游渲染函数自行处理图片输出
"""

import asyncio
from functools import cached_property
from pathlib import Path
from typing import Awaitable, Iterable, Protocol, overload

from pydantic import BaseModel, Field
import shutil

from nanoai.utils.async_utils import amap, with_param_parse_async
from projects.uiagent.core import JudgeResult, UITaskResult


__all__ = [
    # 评估结果数据结构
    "StepEvalResult", 
    "WorkflowEvalResult", 
    # 批量评估工具函数
    "eval_step_batch", 
    "eval_workflow_batch",
]


class PriorityEvalStats(BaseModel):
    """按优先级分组的统计结果"""
    priority: int
    total_count: int
    correct_count: int
    failed_count: int
    
    @cached_property
    def correct_rate(self) -> float:
        return self.correct_count / self.total_count * 100 if self.total_count > 0 else 0.0
    
    @cached_property
    def failed_rate(self) -> float:
        return self.failed_count / self.total_count * 100 if self.total_count > 0 else 0.0
    
    def print(self):
        """打印该优先级的统计信息"""
        print(f"  优先级 {self.priority}: 正确率 {self.correct_rate:.2f}% ({self.correct_count}/{self.total_count}), "
              f"失败率 {self.failed_rate:.2f}% ({self.failed_count}/{self.total_count})")


class StepEvalResult(BaseModel):
    """单步评估统计结果

    Attributes:
        total_step_count: 评估的总样本数
        step_correct_count: 判定正确的样本数
        step_failed_count: 运行失败/异常的样本数
    """
    total_step_count: int
    step_correct_count: int
    step_failed_count: int
    # 加入按优先级分组的统计结果
    priority_stats: dict[int, PriorityEvalStats] = Field(default_factory=dict)

    @cached_property
    def step_correct_rate(self) -> float:
        return self.step_correct_count / self.total_step_count * 100
    
    @cached_property
    def step_failed_rate(self) -> float:
        return self.step_failed_count / self.total_step_count * 100

    def print(self):
        """以易读格式打印单步统计"""
        print(f"单步骤正确率: {self.step_correct_rate:.2f}({self.step_correct_count}/{self.total_step_count})%")
        print(f"单步骤失败率: {self.step_failed_rate:.2f}({self.step_failed_count}/{self.total_step_count})%")
        
        # 优先级的统计
        if self.priority_stats:
            print("\n单步骤按优先级统计:\n")
            for priority in sorted(self.priority_stats.keys()):
                self.priority_stats[priority].print()


class WorkflowEvalResult(StepEvalResult):
    """工作流评估统计结果容器

    在单步统计基础上，增加工作流维度的正确/失败计数与比率。
    口径：一个工作流正确，需其所有步骤均判定为正确。
    """
    total_workflow_count: int
    wf_correct_count: int
    wf_failed_count: int

    wf_priority_stats: dict[int, PriorityEvalStats] = Field(default_factory=dict)
    @cached_property
    def wf_correct_rate(self) -> float:
        return self.wf_correct_count / self.total_workflow_count * 100
    
    @cached_property
    def wf_failed_rate(self) -> float:
        return self.wf_failed_count / self.total_workflow_count * 100

    def print(self) -> None:
        """以易读格式打印单步与工作流统计"""
        super().print()
        print(f"工作流正确率: {self.wf_correct_rate:.2f}({self.wf_correct_count}/{self.total_workflow_count})%")
        print(f"工作流失败率: {self.wf_failed_rate:.2f}({self.wf_failed_count}/{self.total_workflow_count})%")

        # 打印工作流按优先级的统计
        if self.wf_priority_stats:
            print("\n工作流按优先级统计:")
            for priority in sorted(self.wf_priority_stats.keys()):
                self.wf_priority_stats[priority].print()

class StepDataBase(BaseModel):
    """单步样本数据基类"""
    id: int

    priority: int = Field(default=1, description="优先级, 0, 1, 2, 3, etc.")

    comment: str = Field(default="", description="备注, 用于记录该case的任意信息，给人读, 给人用的。")
    
    step: str
    '''在具体任务中可以是StrEnum。'''
    
    query: str
    
    image_path: str


class WorkflowDataBase(BaseModel):
    """工作流样本数据基类

    子类需实现 `steps` 属性，返回有序步骤列表。
    """

    priority: int = Field(default=1, description="优先级, 0, 1, 2, 3, etc.")

    comment: str = Field(default="", description="备注, 用于记录该case的任意信息，给人读, 给人用的。")

    @property
    def steps(self) -> list[StepDataBase]:
        raise NotImplementedError("子类必须实现steps属性")

class PRunStep(Protocol):
    '''运行单步的可调用对象.
    结合 with_param_parse_async 的打包形式，可以接受一个参数或两个参数。
    一个参数时，直接运行单步。
    两个参数时，第一个参数是单步数据，第二个参数是图片输出目录。
    返回值是 tuple[UIRunResult, JudgeResult | None]。
    '''
    @overload
    def __call__(self, step_data: StepDataBase) -> Awaitable[tuple[UITaskResult, JudgeResult | None]]: ...
    
    @overload
    def __call__(self, step_data: StepDataBase, output_dir: str) -> Awaitable[tuple[UITaskResult, JudgeResult | None]]: ...
    def __call__(self, step_data: StepDataBase, output_dir: str | None = ...) -> Awaitable[tuple[UITaskResult, JudgeResult | None]]: ...


def eval_step_batch(
    steps: Iterable[StepDataBase], 
    run_step: PRunStep, 
    /,
    *,
    save_image_root: str | None = None) -> StepEvalResult:
    """批量评估单步样本

    参数：
        steps: 单步样本的可迭代对象
        run_step: 运行单步的可调用对象
        save_image_root: 若提供，将在该目录下创建并传递图片输出目录给 `run_step`

    返回：StepEvalResult
    """
    # 为了后续复制图片文件到对应目录，需要保存数据列表
    # 复制一份steps，因为steps是可迭代对象，只能遍历一次
    steps = list(steps)
    if save_image_root:
        # 由调用方的 run_step 处理实际渲染逻辑，这里仅约定输出目录
        output_dir = Path(save_image_root) / "steps_eval_outputs"
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        # 把output_dir作为参数传递给run_step

        params = [(step, output_dir) for step in steps]
        results, stats = asyncio.run(amap(with_param_parse_async(run_step), params, progress=True))
    else:  
        results, stats = asyncio.run(amap(run_step, steps, progress=True))
    
    stats.print()

    total_count = len(results)
    correct_count = 0
    failed_count = 0

    # 按优先级统计
    priority_stats_dict: dict[int, dict[str, int]] = {}

    # 遍历结果，统计并复制图片到对应目录
    for i, res in enumerate(results):
        step_data = steps[i]
        priority = step_data.priority
        
        # 初始化优先级统计
        if priority not in priority_stats_dict:
            priority_stats_dict[priority] = {"total": 0, "correct": 0, "failed": 0}
        priority_stats_dict[priority]["total"] += 1
        
        # 判断结果
        is_correct = False
        is_exception = isinstance(res, Exception)
        
        if is_exception:
            failed_count += 1
            priority_stats_dict[priority]["failed"] += 1
            continue  # 跳过后续的图片复制逻辑
        else:
            run_result, judge_result = res
            assert isinstance(judge_result, JudgeResult) or judge_result is None
            if judge_result is not None and judge_result:
                correct_count += 1
                priority_stats_dict[priority]["correct"] += 1
                is_correct = True
            else:
                failed_count += 1
                priority_stats_dict[priority]["failed"] += 1
        
        # 复制图片到对应目录
        if save_image_root:
            # 原始图片路径
            original_image_path = output_dir / f"{step_data.id}_step_eval_result.png"
            
            if original_image_path.exists():
                # 目标目录：p{priority}/正确 或 p{priority}/错误
                status_dir = "正确" if is_correct else "错误"
                target_dir = Path(output_dir) / f"p{priority}" / status_dir
                target_dir.mkdir(parents=True, exist_ok=True)
                
                # 移动文件
                target_path = target_dir / f"{step_data.id}_step_eval_result.png"
                shutil.move(original_image_path, target_path)
    
    # 构建优先级统计对象
    priority_stats: dict[int, PriorityEvalStats] = {}
    for priority, stats_data in priority_stats_dict.items():
        priority_stats[priority] = PriorityEvalStats(
            priority=priority,
            total_count=stats_data["total"],
            correct_count=stats_data["correct"],
            failed_count=stats_data["failed"]
        )

    return StepEvalResult(
        total_step_count=total_count,
        step_correct_count=correct_count,
        step_failed_count=failed_count,
        priority_stats=priority_stats,
    )


class PRunWorkflow(Protocol):
    '''运行完整工作流的可调用对象.
    结合 with_param_parse_async 的打包形式，可以接受一个参数或两个参数。
    一个参数时，直接运行完整工作流。
    两个参数时，第一个参数是工作流数据，第二个参数是图片输出目录。
    返回值是 list[tuple[UIRunResult, JudgeResult] | Exception]。
    '''
    @overload
    def __call__(self, workflow_data: WorkflowDataBase) -> Awaitable[list[tuple[UITaskResult, JudgeResult] | Exception]]: ...

    @overload
    def __call__(self, workflow_data: WorkflowDataBase, output_dir: str) -> Awaitable[list[tuple[UITaskResult, JudgeResult] | Exception]]: ...
    def __call__(self, workflow_data: WorkflowDataBase, output_dir: str | None = ...) -> Awaitable[list[tuple[UITaskResult, JudgeResult] | Exception]]: ...


def eval_workflow_batch(
    dataset: Iterable[WorkflowDataBase], 
    run_workflow: PRunWorkflow, 
    /,
    *,
    save_image_root: str | None = None) -> WorkflowEvalResult:
    """批量评估完整工作流

    参数：
        dataset: 工作流样本的可迭代对象
        run_workflow: 运行完整工作流的可调用对象，返回每一步的 (UIRunResult, JudgeResult) 或 Exception
        save_image_root: 若提供，将在该目录下创建并传递图片输出目录给 `run_workflow`

    统计口径：
    - 工作流正确：其四个步骤均通过评审
    - 步骤正确：判定结果为真

    返回：WorkflowEvalResult
    """
    # 为了后续复制图片文件到对应目录，需要保存数据列表    
    # # 复制一份dataset，因为dataset是可迭代对象，只能遍历一次
    dataset = list(dataset)
    if save_image_root:
        # 由调用方的 run_workflow 处理实际渲染逻辑，这里仅约定输出目录
        output_dir = Path(save_image_root) / "workflow_eval_outputs"
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        params = [(flow, output_dir) for flow in dataset]
        results, stats = asyncio.run(amap(with_param_parse_async(run_workflow), params, progress=True))
    else:
        results, stats = asyncio.run(amap(run_workflow, dataset))

    stats.print()

    # 为了数总的step数，必须从输入当中去数，因为workflow运行挂了就只会有一个exception，从而不知道里面有几个step

    total_step_count = 0
    for a_work_flow_steps in dataset:
        total_step_count += len(a_work_flow_steps.steps)
    print(f"总step数: {total_step_count}")
    
    total_workflow_count = len(results)
    step_correct_count = 0
    step_failed_count = 0
    wf_correct_count = 0
    wf_failed_count = 0

    # 按优先级统计（工作流级别和步骤级别）
    wf_priority_stats_dict: dict[int, dict[str, int]] = {}
    step_priority_stats_dict: dict[int, dict[str, int]] = {}

    for i, wf_result in enumerate(results):
        workflow_data = dataset[i]
        workflow_priority = workflow_data.priority
        
        # 初始化工作流优先级统计
        if workflow_priority not in wf_priority_stats_dict:
            wf_priority_stats_dict[workflow_priority] = {"total": 0, "correct": 0, "failed": 0}
        wf_priority_stats_dict[workflow_priority]["total"] += 1
        
        # 判断整个工作流是否异常
        if isinstance(wf_result, Exception):
            print(f"工作流运行失败: {wf_result}")
            wf_failed_count += 1
            wf_priority_stats_dict[workflow_priority]["failed"] += 1
            # 异常时不会生成图片，直接跳过
            continue

        # 标记单个工作流是否全对（所有步骤均通过）
        wf_correct: bool = True
        
        # 遍历工作流的每个步骤
        for step_idx, step_result in enumerate(wf_result):
            step_data = workflow_data.steps[step_idx]
            step_priority = step_data.priority
            
            # 初始化步骤优先级统计
            if step_priority not in step_priority_stats_dict:
                step_priority_stats_dict[step_priority] = {"total": 0, "correct": 0, "failed": 0}
            step_priority_stats_dict[step_priority]["total"] += 1
            
            if isinstance(step_result, Exception):
                step_failed_count += 1
                print(f"步骤 {step_idx} 运行失败: {step_result}")
                step_priority_stats_dict[step_priority]["failed"] += 1
                wf_correct = False
                continue

            _, judge_result = step_result
            if judge_result:
                step_correct_count += 1
                step_priority_stats_dict[step_priority]["correct"] += 1
            else:
                step_failed_count += 1
                step_priority_stats_dict[step_priority]["failed"] += 1
                wf_correct = False

        # 判断工作流是否正确
        if wf_correct:
            wf_correct_count += 1
            wf_priority_stats_dict[workflow_priority]["correct"] += 1
        else:
            wf_failed_count += 1
            wf_priority_stats_dict[workflow_priority]["failed"] += 1
        
        # 复制工作流图片到对应目录
        if save_image_root:
            # 原始图片路径：workflow_{id}.png
            original_image_path = output_dir / f"workflow_{workflow_data.id}.png"
            
            if original_image_path.exists():
                # 目标目录：p{priority}/正确 或 p{priority}/错误
                status_dir = "正确" if wf_correct else "错误"
                target_dir = output_dir / f"p{workflow_priority}" / status_dir
                target_dir.mkdir(parents=True, exist_ok=True)
                
                # 移动文件
                target_path = target_dir / f"workflow_{workflow_data.id}.png"
                shutil.move(original_image_path, target_path)
    
    # 构建步骤优先级统计对象
    step_priority_stats: dict[int, PriorityEvalStats] = {}
    for priority, stats_data in step_priority_stats_dict.items():
        step_priority_stats[priority] = PriorityEvalStats(
            priority=priority,
            total_count=stats_data["total"],
            correct_count=stats_data["correct"],
            failed_count=stats_data["failed"]
        )
    
    # 构建工作流优先级统计对象
    wf_priority_stats: dict[int, PriorityEvalStats] = {}
    for priority, stats_data in wf_priority_stats_dict.items():
        wf_priority_stats[priority] = PriorityEvalStats(
            priority=priority,
            total_count=stats_data["total"],
            correct_count=stats_data["correct"],
            failed_count=stats_data["failed"]
        )

    return WorkflowEvalResult(
        total_step_count=total_step_count,
        step_correct_count=step_correct_count,
        step_failed_count=step_failed_count,
        priority_stats=step_priority_stats,  # 步骤级别的优先级统计
        total_workflow_count=total_workflow_count,
        wf_correct_count=wf_correct_count,
        wf_failed_count=wf_failed_count,
        wf_priority_stats=wf_priority_stats,  # 工作流级别的优先级统计
    )

def load_step_dataset[T: StepDataBase](dataset_path: Path, step_data_cls: type[T]) -> Iterable[T]:
    """加载单步数据集"""
    assert issubclass(step_data_cls, StepDataBase)

    assert dataset_path.exists(), f"数据集目录不存在: {dataset_path}"

    data_file = dataset_path / "data.jsonl"
    assert data_file.exists(), f"数据文件不存在: {data_file}"

    images_dir = dataset_path / "images"
    assert images_dir.exists(), f"图片目录不存在: {images_dir}"

    steps: list[T] = []

    with open(data_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = step_data_cls.model_validate_json(line)
            except Exception as e:
                print(f"load step data failed: {line}, error: {e}")
                continue

            data.image_path = str(images_dir / data.image_path)
            steps.append(data)

    return steps