# 简要说明：
# 本文件用于 SeatBooking 场景的评估与可视化：
# - 加载单步/工作流数据集
# - 运行工作流各步骤
# - 绘制动作与评审信息，便于对齐与回溯

from typing import Iterable, cast

from pydantic import field_validator

from projects.uiagent.core import JudgeResult, RunResult, image_from_path
from projects.uiagent.core.eval import (
    StepDataBase,
    WorkflowDataBase,
    eval_step_batch,
    eval_workflow_batch,
    load_step_dataset,
)
from projects.uiagent.core.visualize import draw_step_result, draw_workflow_result
from projects.uiagent.seatbooking.datasets import DATASET_ROOT
from projects.uiagent.seatbooking.workflow import EStep, Workflow

# 将数据集中的整数步骤编号映射到工作流内部的 EStep 枚举（用于解析数据集）
step_mapping = {
    1: EStep.FIND_RESTAURANT,
    2: EStep.START_BOOKING,
    3: EStep.CONFIRM_BOOKING_DETAILS,
    4: EStep.END_BOOKING,
}


class StepData(StepDataBase):
    step: EStep | None = None
    """这里支持None是为了支持工作流数据集的加载"""

    image_path: str | dict[str, str]
    """这里支持dict是为了支持工作流数据集的加载"""

    @field_validator("step", mode="before")
    @classmethod
    def convert_to_estep(cls, v):
        """将int类型的step转换为EStep枚举"""
        if isinstance(v, (int, str)):
            v = int(v)
            if v in step_mapping:
                return step_mapping[v]
            else:
                raise ValueError(f"无效的步骤编号: {v}，支持的编号为 1-4")
        return v


class WorkflowData(WorkflowDataBase):
    """工作流样本，由四个有序步骤组成"""

    id: int
    find_restaurant: StepData  # 查找餐厅
    start_booking: StepData  # 验证订座
    confirm_booking_details: StepData  # 确认预订详情
    end_booking: StepData  # 最终信息确认

    @property
    def steps(self) -> list[StepData]:
        return [
            self.find_restaurant,
            self.start_booking,
            self.confirm_booking_details,
            self.end_booking,
        ]


async def run_step(
    step_data: StepData, output_dir: str | None = None
) -> tuple[RunResult, JudgeResult | None]:
    """执行单步并可选保存渲染图"""
    workflow = Workflow(enable_reflect=True)
    base64_image, image_format = image_from_path(step_data.image_path)
    result, eval_res = await workflow.run(
        step_data.query, base64_image, image_format, current_step=step_data.step
    )
    if output_dir is not None:
        draw_step_result(step_data, result, eval_res, output_dir)

    return result, eval_res


async def run_workflow(
    workflow_data: WorkflowDataBase, output_dir: str | None = None
) -> list[tuple[RunResult, JudgeResult] | Exception]:
    """按顺序执行完整工作流的四个步骤

    返回列表，元素为 (RunResult, JudgeResult) 或 Exception。
    """
    wf = Workflow(enable_reflect=True)
    step_results: list[tuple[RunResult, JudgeResult] | Exception] = []

    for step in workflow_data.steps:
        wf.current_step = step.step
        try:
            base64_image, image_format = image_from_path(step.image_path)
            result, eval_res = await wf.run(step.query, base64_image, image_format)
            assert isinstance(eval_res, JudgeResult)
            step_results.append((result, eval_res))
        except Exception as e:
            step_results.append(e)

    if output_dir is not None:
        # 从step_results中提取RunResult和JudgeResult
        runresults = [r[0] for r in step_results if isinstance(r, tuple)]
        judges = [r[1] for r in step_results if isinstance(r, tuple)]
        # 绘制工作流结果图片
        draw_workflow_result(workflow_data, runresults, judges, output_dir)

    return step_results


def load_workflow_dataset(dataset_name: str) -> Iterable[WorkflowData]:
    """加载工作流数据集

    data.jsonl 的每行包含一个复用 StepData 结构的 JSON：
    - image_path 为 {"step1": path, ..., "step4": path} 的字典
    - 本函数将其拆分为四个 StepData 并组装为 WorkflowData
    """
    # 使用DATASET_ROOT，但确保路径是绝对路径S
    dataset_path = DATASET_ROOT.resolve() / dataset_name
    data_file = dataset_path / "data.jsonl"
    images_dir = dataset_path / "images"

    workflows: list[WorkflowData] = []

    # 读取jsonl文件
    with open(data_file, "r", encoding="utf-8") as f:
        for line in f:
            data = StepData.model_validate_json(line)
            steps: list[StepData] = []

            for i in range(1, 5):
                key = f"step{i}"
                assert isinstance(data.image_path, dict) and key in data.image_path
                data_copy = data.model_copy()
                data_copy.image_path = str(images_dir / data.image_path[key])
                data_copy.step = step_mapping[i]
                steps.append(data_copy)

            workflows.append(
                WorkflowData(
                    id=data.id,
                    find_restaurant=steps[0],
                    start_booking=steps[1],
                    confirm_booking_details=steps[2],
                    end_booking=steps[3],
                )
            )

    return workflows


def test_load_workflow_dataset():
    """测试工作流数据集加载"""
    dataset_name = "meituan_workflow"
    print(f"开始加载工作流数据集: {dataset_name}")
    workflow_gen = load_workflow_dataset(dataset_name)

    for workflow_data in workflow_gen:
        print(f"\n{workflow_data}")


def eval_workflow_run(save_image: bool):
    """命令行入口：运行工作流评估并打印统计"""
    print("\n=== 测试工作流评估 ===")
    dataset_name = "meituan_workflow"

    workflow_dataset = load_workflow_dataset(dataset_name)
    # 减少测试数据
    workflow_dataset = workflow_dataset[:2]

    eval_result = eval_workflow_batch(
        workflow_dataset, run_workflow, save_image_root=str(DATASET_ROOT)
    )
    eval_result.print()


def eval_step_run(save_image: bool):
    """命令行入口：运行单步评估并打印统计"""
    print("=== 单步测试数据集加载 ===")
    dataset_name = "meituan"

    dataset_path = DATASET_ROOT.resolve() / dataset_name

    step_dataset = load_step_dataset(dataset_path, StepData)
    for step_data in step_dataset:
        print(f"\n{step_data}")

    print("\n=== 测试单步评估 ===")
    # 减少测试数据
    step_dataset = step_dataset[:2]

    eval_result = eval_step_batch(
        step_dataset, run_step, save_image_root=str(DATASET_ROOT)
    )
    eval_result.print()


# 确保只有一个主程序入口块
if __name__ == "__main__":

    # test_load_workflow_dataset()
    eval_step_run(True)

    eval_workflow_run(True)
