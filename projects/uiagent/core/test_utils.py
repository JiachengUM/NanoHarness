import asyncio
from typing import Iterable, Any, Callable
from pathlib import Path
from functools import cached_property
import datetime
import pandas as pd
from pydantic import BaseModel, Field

from nanoai.model.vlm import image_from_path
from nanoai.utils.text_utils import df_to_html
from nanoai.utils.nl_repr import nl_repr
from nanoai.utils.async_utils import amap, with_param_parse_async


from projects.uiagent.core import (
    JudgeResult,
    UITaskResult,
    WorkflowStatus,
    WorkflowBase,
    WorkflowResult,
    WorkflowState,
    StepType, UIStepStatus,
)
from projects.uiagent.core.action import FinishedAction
from projects.uiagent.core.visualize import draw_step_result


__all__ = [
    "Environment",
    "run_ui_step",
    "StepEvalResult",
    "StepData",
    "load_step_dataset",
    "eval_step_batch",
    "WorkflowEvalResult",
    "run_workflow",
    "WorkflowData",
    "eval_workflow_batch",
]

from projects.uiagent.utils.image_utils import base64_to_temp_file


class Environment:
    '''和智能体交互，为其提供反馈的模拟environment。'''
    def __init__(self, page_images: dict[str, tuple[str] | str | None] | str) -> None:
        '''page_images是页面名称到页面图片路径的映射。
        '''
        assert isinstance(page_images, dict), f"page_images must be a dict, but got {type(page_images)}"

        assert all(
            (Path(value).exists() if isinstance(value, str) else Path(value[0]).exists()) for value in page_images.values()
        ), "page_images must be a dict of existing file paths"

        self.page_images = page_images

    def get_image(self, page: str) -> tuple[str, str, None]:
        '''return (image, image_format, xml)'''
        if isinstance(self.page_images[page], str):
            image, image_format = image_from_path(self.page_images[page])
            return image, image_format, None
        image, image_format = image_from_path(self.page_images[page][0])
        if self.page_images[page][1]:
            if (file :=Path(self.page_images[page][1])).exists():
                xml = file.read_text(encoding="utf-8")
                return image, image_format, xml
            raise Exception(f"xml file {file} not exists")
        return image, image_format, None


async def run_ui_step(
    workflow_creator: type[WorkflowBase] | Callable[[], WorkflowBase], 
    image_path: str,
    step: StepType,
    /,
    info: BaseModel | str | None = None,
    xml_path: str | None = None,
    output_dir: str | None = None,
    output_filename: str | None = None,
    ) -> WorkflowResult:
    '''执行单步UI任务。'''

    workflow = workflow_creator()  # type: ignore

    # 开启反思
    workflow.enable_reflect = True
    image, image_format = image_from_path(image_path)
    # 读取xml文件
    xml = Path(xml_path).read_text(encoding="utf-8") if xml_path else None
    result = await workflow.run_ui(image, image_format, xml, step=step, info=info)

    if output_dir is not None:        
        draw_step_result(
            image_path=image_path, 
            query=nl_repr(info) if info is not None else "", 
            runresult=result.results, 
            judge=result.state.eval_res, 
            output_dir=output_dir, 
            sample_id=output_filename)
    
    return result

class TagEvalStats(BaseModel):
    """按标签分组的统计结果"""
    tag: str
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
        """打印该标签的统计信息"""
        print(f"  标签 {self.tag}: 正确率 {self.correct_rate:.2f}% ({self.correct_count}/{self.total_count}), "
              f"失败率 {self.failed_rate:.2f}% ({self.failed_count}/{self.total_count})")

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
    # 加入按标签分组的统计结果
    tags_stats: dict[str, TagEvalStats] = Field(default_factory=dict)

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
        # 标签的统计
        if self.tags_stats:
            print("\n单步骤按标签统计:\n")
            for tag in sorted(self.tags_stats.keys()):
                self.tags_stats[tag].print()


class StepDataMeta(BaseModel):
    id: int | str # 用于唯一标识一个步骤样本，可构建图片文件名。
    priority: int = Field(default=1, description="优先级, 0, 1, 2, 3, etc.")
    tags: list[str] = Field(default=[], description="标签，用于分类和筛选。")


class StepData(StepDataMeta):
    step: int | None = None
    xml_path: str | None = None
    image_path: str
    query: str = Field(default="", description="查询信息") # 与info是一个东西。可能被info取代。
    info: BaseModel | str | None = None #人为构建的数据集中没有info，可能要在加载函数处进行处理。


def run_step_batch(
    steps: Iterable[StepData], # 单步样本的可迭代对象
    workflow_creator: type[WorkflowBase[WorkflowState]] | Callable[[], WorkflowBase[WorkflowState]],
    /,
    *,
    save_image_root: str | None = None,
    state_params: dict[str, Any] | None = None) -> list[WorkflowResult[WorkflowState] | Exception]:
        # 为了后续复制图片文件到对应目录，需要保存数据列表
    # 复制一份steps，因为steps是可迭代对象，只能遍历一次
    steps = list(steps)
    if save_image_root:
        # 仅约定输出目录
        output_dir = Path(save_image_root) / "steps_eval_outputs"
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        params = [
            (workflow_creator, step_data.image_path, step_data.step, step_data.info, step_data.xml_path, str(output_dir), f"{step_data.id}_test", state_params) 
            for step_data in steps
        ]
    else:
        params = [
            (workflow_creator, step_data.image_path, step_data.step, step_data.info, step_data.xml_path, None, f"{step_data.id}_test", state_params) 
            for step_data in steps
        ]
    results, stats = asyncio.run(amap(with_param_parse_async(run_ui_step), params, progress=True))
    
    stats.print()
    return results


def eval_step_batch(
    results: list[WorkflowResult[WorkflowState]], steps: list[StepData] | list[StepDataMeta],
    save_image_root: str | None = None,
    tags:dict[str, list[str]] | None = None
    ) -> StepEvalResult:
    
    """批量评估单步样本，默认支持整体正确率、优先级（非tags中的）正确率、失败率。

    参数：
        results: 运行结果列表
        steps: 步骤数据列表
        save_image_root: 若提供，会进行图片移动操作
        tags: 标签字典，用于分类和筛选。

    返回：StepEvalResult
    """
    assert len(results) == len(steps), "results and steps must have the same length"
    total_count = len(results)
    correct_count = 0
    failed_count = 0
    # 按tags统计，键和值都当做统计对象
    if tags:
        tags_stats_dict: dict[str, dict[str, int]] = {}
        
        for _, value in tags.items():
            # tags_stats_dict[key] = {"total": 0, "correct": 0, "failed": 0}
            for tag in value:
                tags_stats_dict[tag] = {"total": 0, "correct": 0, "failed": 0}
    # 按优先级统计
    priority_stats_dict: dict[int, dict[str, int]] = {}
    # step中会有tags字段，为一个列表，有多个值，出现过的都要计数，直接去tags_stats_dict中找
    
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
            if tags:
                step_tags = step_data.tags
                for tag_key in tags_stats_dict.keys():
                    if tag_key in step_tags:
                        tags_stats_dict[tag_key]["total"] += 1
                        tags_stats_dict[tag_key]["failed"] += 1
            continue  # 跳过后续的图片复制逻辑
        else:
            judge_result = res.state.eval_res
            # 或许需要针对str类型的结果进行处理。
            run_result = res.results
            assert isinstance(judge_result, JudgeResult) or judge_result is None
            if isinstance(run_result, str) or judge_result is None or bool(judge_result):
                correct_count += 1
                priority_stats_dict[priority]["correct"] += 1
                is_correct = True
            else:
                failed_count += 1
                priority_stats_dict[priority]["failed"] += 1
        # 更新 tags 统计
        if tags:
            step_tags = step_data.tags
            for tag_key in tags_stats_dict.keys():
                if tag_key in step_tags:
                    tags_stats_dict[tag_key]["total"] += 1
                    if is_correct:
                        tags_stats_dict[tag_key]["correct"] += 1
                    else:
                        tags_stats_dict[tag_key]["failed"] += 1
        
        # 复制图片到对应目录
        if save_image_root:
            # 原始图片路径
            # 与run_step_batch的output_dir一致
            output_dir = Path(save_image_root) / "steps_eval_outputs"
            original_image_path = output_dir / f"{step_data.id}_test_step_eval_result.png"
            
            if original_image_path.exists():
                # 目标目录：p{priority}/正确 或 p{priority}/错误
                status_dir = "正确" if is_correct else "错误"
                target_dir = Path(output_dir) / f"p{priority}" / status_dir
                target_dir.mkdir(parents=True, exist_ok=True)
                
                # 移动文件
                import shutil
                target_path = target_dir / f"{step_data.id}_test_step_eval_result.png"
                shutil.move(original_image_path, target_path)
    
    # 构建优先级统计对象
    priority_stats: dict[int, PriorityEvalStats] = {}
    priority_stats_rows: list[dict[str, Any]] = []
    for priority, stats_data in priority_stats_dict.items():
        priority_stats[priority] = PriorityEvalStats(
            priority=priority,
            total_count=stats_data["total"],
            correct_count=stats_data["correct"],
            failed_count=stats_data["failed"]
        )
        # 用于生成报告
        priority_stats_rows.append({
            "标签": priority,
            "总数": stats_data["total"],
            "正确数": stats_data["correct"],
            "错误数": stats_data["failed"],
            "正确率": (f"{stats_data['correct'] / stats_data['total'] * 100:.2f}%") if stats_data["total"] else 0.0,
            "错误率": (f"{stats_data['failed'] / stats_data['total'] * 100:.2f}%") if stats_data["total"] else 0.0,
        })
    priority_stats_df = pd.DataFrame(priority_stats_rows)

    # 构建标签统计对象
    tags_stats: dict[str, TagEvalStats] = {}
    tags_stats_rows: list[dict[str, Any]] = []
    if tags:
        for tag, stats_data in tags_stats_dict.items():
            tags_stats[tag] = TagEvalStats(
                tag=tag,
                total_count=stats_data["total"],
                correct_count=stats_data["correct"],
                failed_count=stats_data["failed"]
            )
            # 用于生成报告
            tags_stats_rows.append({
                "标签": tag,
                "总数": stats_data["total"],
                "正确数": stats_data["correct"],
                "错误数": stats_data["failed"],
                "正确率": (f"{stats_data['correct'] / stats_data['total'] * 100:.2f}%") if stats_data["total"] else 0.0,
                "错误率": (f"{stats_data['failed'] / stats_data['total'] * 100:.2f}%") if stats_data["total"] else 0.0,
            })

        tags_stats_df = pd.DataFrame(tags_stats_rows)
        combined_stats_df = pd.concat([tags_stats_df, priority_stats_df], ignore_index=True)
        if save_image_root:
            
            filename = str(Path(save_image_root) / "all_stats_df.html")
            df_to_html(
                combined_stats_df,
                filename,
                title="各标签指标统计",
                summary_info={
                    "列数": str(len(combined_stats_df.columns)),
                    "行数": str(len(combined_stats_df)),
                },
            )
            print(f"标签统计报告已生成: {filename}")
    else:
        if save_image_root:
            filename = str(Path(save_image_root) / "priority_stats_df.html")
            df_to_html(
                priority_stats_df,
                filename,
                title="各优先级指标统计",
                summary_info={
                    "列数": str(len(priority_stats_df.columns)),
                    "行数": str(len(priority_stats_df)),
                },
            )
            print(f"优先级统计报告已生成: {filename}")
            
    return StepEvalResult(
        total_step_count=total_count,
        step_correct_count=correct_count,
        step_failed_count=failed_count,
        priority_stats=priority_stats,
        tags_stats=tags_stats,
    )


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


async def run_workflow(
    workflow_creator: type[WorkflowBase] | WorkflowBase,
    env: Environment, 
    query: str,
    allow_nl_interactive: bool = True,
    output_dir: str | None = None,
    state_params: dict[str, Any] | None = None,
    limit: int | None = None,
    ) -> list[WorkflowResult]:
    '''自动执行workflow，直到完成，并返回每一次调用的完整结果序列。
    这是Workflow level的端到端测试函数。这是写fast api以及前端的基础。
    麻雀虽小，五脏俱全。以后会越来越全。
    TODO: 需要增加**state_params
    allow_nl_interactive: 是否交互式执行，如果为True，则需要输入用户回复，否则直接执行。
    '''

    # fast api初始化。初始化workflow。
    if isinstance(workflow_creator, WorkflowBase):
        workflow = workflow_creator
    else:
        workflow = workflow_creator()  # type: ignore
    
    # 初始化：前端在确认落域到该workflow对应的app之后，启动app，得到首页，类似于下面的image_from_path
    # 前端需要将截止到目前为止的所有的user message统一成一个query。
    
    # 第一次调用run_nl和第一次调用run_ui的顺序无所谓。互相都会block住
    history: list[WorkflowResult] = []
    res: WorkflowResult = await workflow.run_nl(query)
    assert isinstance(res.results[0], str), "第一次run_nl结果必须为str，还没有初始化image"
    history.append(res)
    # 这里的res需要在fast api的地方被包一下。分成两种api：
    # 1. 对于真实的产品前端，简化：扔掉对于前端无用的state中的内部细节。
    # 2. 对于内部的测试前端，保留所有细节。

    # 前端需要重新实现ENV
 # 前端会从fast api拿到res，需要检查res的状态，做相应的处理：
    # terminated -> exit app, nl -> 发一个语音出去, ui action -> 执行ui动作
    history = []
    count = 0
    while res.state.status in [WorkflowStatus.RUNNING]:
        current_step = workflow.state.current_step
        print("=" * 100)
        print(f"current_step: {current_step}")
        print("=" * 100)
        print(f"\n{nl_repr(res)}")  # 前端自己处理，和上面类似。
        assert res.state.step_status[current_step] != UIStepStatus.IDLE, f"workflow current_step [{current_step}] 状态不能为IDLE"
        count += 1
        if res.state.step_status[current_step] == UIStepStatus.WAIT_FOR_INFO:
            if allow_nl_interactive:
                query = input(f"{res.results}\n")
                res = await workflow.run_nl(query)  # fast api包成res，返回给前端
            else:
                raise Exception("allow_nl_interactive： False")
        else:
            res = await workflow.run_ui(*env.get_image(current_step))
        history.append(res)
        # if output_dir is not None:
        #     current_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        #     draw_step_result(
        #         image_path=base64_to_temp_file(*env.get_image(current_step)[:2]),
        #         query=query,
        #         runresult=res.results,
        #         judge=res.state.eval_res,
        #         output_dir=output_dir,
        #         sample_id=f"{current_step}_{current_time}_test"
        #         )
        if limit and count >= limit:
            break
    current_step = workflow.state.current_step
    print("=" * 100)
    print(f"current_step: {current_step}")
    print("=" * 100)
    print(f"\n{nl_repr(res)}")

    def is_finished(results: list[str, UITaskResult]):
        for result in results:
            if isinstance(result, str):
                continue
            for action in result.actions:
                if isinstance(action, FinishedAction):
                    return True
        return False
    assert res.state.status == WorkflowStatus.SUCCESS or is_finished(res.results), f"WORKFLOW最终状态不是SUCCESS[GOT {res.state.status}]或action不是FINISHED ACTION"
    print("=" * 100)
    print(f"workflow成功执行完毕")
    print("=" * 100)
    return history

def load_step_dataset[T: StepData](dataset_path: Path, step_data_cls: type[T]) -> Iterable[T]:
    """加载单步数据集"""
    assert issubclass(step_data_cls, StepData)

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
            if hasattr(data, 'xml_path') and data.xml_path is not None and data.xml_path != "":
                xmls_dir = dataset_path / "xmls"
                assert xmls_dir.exists(), f"xml目录不存在: {xmls_dir}"

                data.xml_path = str(xmls_dir / data.xml_path)
            # 由于人为构建的数据集中没有info，可能要在加载函数处进行处理。
            if not data.info and data.query:
                data.info = data.query
            steps.append(data)

    return steps


class WorkflowData(BaseModel):
    id: int
    steps: list[StepData]
    priority: int = Field(default=1, description="优先级, 0, 1, 2, 3, etc.")
    query: str = Field(default="", description="查询信息")
    comment: str = Field(default="", description="备注, 用于记录该case的任意信息，给人读, 给人用的。")


def eval_workflow_batch[S: WorkflowState](
    workflow_datas: Iterable[WorkflowData],
    workflow_cls: type[WorkflowBase[S]], 
    /,
    *,
    save_image_root: str | None = None) -> WorkflowEvalResult:
    '''批量执行工作流。'''
    workflow_datas = list(workflow_datas)

    params = []
    
    for workflow_data in workflow_datas:
        # 将各个workflow的图片分开存储
        assert save_image_root is not None
        output_dir = str(Path(save_image_root) / f"workflow_{workflow_data.id}")
        env = Environment({str(step.step): str(step.image_path) for step in workflow_data.steps})
        params.append((workflow_cls, env, workflow_data.query, False, output_dir))

    results, stats = asyncio.run(amap(with_param_parse_async(run_workflow), params, progress=True))
    stats.print()

    # 处理结果，str，跳过记录
    processed_results = []
    skipped_indices = set()  # 记录被跳过的 workflow 索引
    for i, result in enumerate(results):
        # result 是 list[WorkflowResult]
        if isinstance(result, Exception):
            skipped_indices.add(i)
            print(f"工作流 {i+1} 运行失败: {result}")
            continue
        processed_results.append(result)

    # 为了数总的step数，必须从输入当中去数，因为workflow运行挂了就只会有一个exception，从而不知道里面有几个step
    results = processed_results
    total_step_count = 0
    for i, workflow_data in enumerate(workflow_datas):
        if i in skipped_indices:
            continue  # 跳过 ask human 的 workflow
        total_step_count += len(workflow_data.steps)
    print(f"总step数: {total_step_count}")

    total_workflow_count = len(results)  # 这个已经是过滤后的数量了
    step_correct_count = 0
    step_failed_count = 0
    wf_correct_count = 0
    wf_failed_count = 0

    # 按优先级统计（工作流级别和步骤级别）
    wf_priority_stats_dict: dict[int, dict[str, int]] = {}
    step_priority_stats_dict: dict[int, dict[str, int]] = {}
    
    for i, wf_result in enumerate(results):
        if i in skipped_indices:
            continue  # 跳过 str 的情况的 workflow
        workflow_data = workflow_datas[i]
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
            if isinstance(step_result, str):
                step_failed_count += 1
                print(f"步骤 {step_idx} 运行失败: {step_result}")
                step_priority_stats_dict[step_priority]["failed"] += 1
                wf_correct = False
                continue
            
            judge_result = step_result.state.eval_res
            assert isinstance(judge_result, JudgeResult) or judge_result is None
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