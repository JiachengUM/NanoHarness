from pathlib import Path
from typing import Final

from rich import print

from projects.uiagent.coffee_purchase.workflow_case import WorkflowDatas, TaskType
from nanoai.model.vlm import image_from_path
from projects.uiagent.core.visualize import draw_workflow_result, draw_step_result
from projects.uiagent.utils.image_utils import base64_to_temp_file
from projects.uiagent.core.flow_data import UIResult
from projects.uiagent.coffee_purchase.datasets import DATASET_ROOT
from projects.uiagent.jie_parking.workflow_eval import load_workflow_dataset
import traceback
from projects.uiagent.core.uiflow import UIFlowBase, UIFlowState

# 默认 XML 字符串
DEFAULT_XML: Final[str] = "默认字符串"

def extract_UIResult(result: UIResult | str) -> UIResult | str| None:
    """从workflow result中提取唯一的UIResult"""
    for item in result:
        if isinstance(item, UIResult):
            return item
        elif isinstance(item, str):
            return item
    return None
    
async def test_normal_workflow(workflow: UIFlowBase[UIFlowState], datas: WorkflowDatas, debug: bool = False, output_dir: Path = DATASET_ROOT / "outputs"):
    """简化的推理函数，只进行数据推理
    
    Args:
        workflow: 工作流实例
        datas: 工作流数据
        debug: 是否输出调试信息
        output_dir: 输出目录
    """
    workflow_data = load_workflow_dataset(datas.datas)
    runresults = []
    result_dir = output_dir / datas.name.replace("，", "_").replace("：", "_").replace(".", "_").strip()
    result_dir.mkdir(parents=True, exist_ok=True)
    
    # 维护总体正确性标志和失败环节列表
    all_correct_flag = True
    failed_steps = []
    
    print("=" * 80)
    print(f"开始执行工作流: {datas.name}")
    print("=" * 80)
    
    for i, item in enumerate(datas.datas, start=1):
        print("\n" + "=" * 80)
        print(f"【步骤 {i}/{len(datas.datas)}】")
        print("=" * 80)
        
        # 加载图片
        image, image_format = image_from_path(item["image_path"])
        
        # 使用默认 XML
        xml = DEFAULT_XML
        current_step = workflow.state.step
        
        try:
            if item["task_type"] == TaskType.UI:
                result = await workflow.run_ui(image, image_format, xml)
            elif item["task_type"] == TaskType.NL:
                result = await workflow.run_nl(item["query"])
            else:
                raise ValueError(f"未知的任务类型: {item['task_type']}")
        except Exception as e:
            print(f"❌ 步骤 {i} 执行推理时发生异常: {e}")
            traceback.print_exc()
            # 标记为失败，补充当前步骤结果，并将后续所有步骤补充为 None
            all_correct_flag = False
            failed_steps.append(i)
            runresults.append(None)
            # 将后续所有步骤的结果补充为 None
            remaining_steps = len(datas.datas) - i
            for _ in range(remaining_steps):
                runresults.append(None)
            print("=" * 80)
            break
        
        # 画图逻辑：在循环中调用 draw_step_result
        try:
            draw_step_result(
                image_path=base64_to_temp_file(image),
                query=item.get("query", "") if item["task_type"] == TaskType.NL else "",
                runresult=[extract_UIResult(result.results)],
                judge=workflow.state.eval_res,
                output_dir=str(result_dir),
                sample_id=f"{i}_{current_step}"
            )
        except:
            traceback.print_exc()
            pass
        
        # 判断下一步step，与预期step是否一致
        step_correct = result.state.step == item["expect_next_step"]
        
        # 如果步骤不正确，标记总体为错误并记录失败环节
        if not step_correct:
            all_correct_flag = False
            failed_steps.append(i)

        # 调试输出
        if debug:
            print("-" * 80)
            print(f"当前处理步骤: {current_step}")
            print(f"结果: {result.results}")
            print(f"预期: {item['expected_result']}")
            print("-" * 80)
            if not step_correct:
                print(f"步骤不正确 ❌ : {result.state.step} != {item['expect_next_step']}")
            else:
                print(f"步骤正确 ✅ : {result.state.step} == {item['expect_next_step']}")
            print("-" * 80)
            print(f"状态: {result.state.status}")
            print(f"步骤: {result.state.step}")
            print(f"步骤状态: {result.state.step_status[result.state.step]}")
            print(f"workflow状态: {result.state.middle_info}")
            print(f"意图识别: {result.state.intent_cls_res}")
            if result.error:
                print(f"错误: {result.error}")
        
        # 维护 runresults 列表
        runresults.append(result.results)
        
        print("=" * 80)
        
    
    # 画图逻辑：最后调用 draw_workflow_result
    print("\n" + "=" * 80)
    print("开始绘制工作流结果图...")
    print("=" * 80)
    judges: list[None] = [None] * len(runresults)
    draw_workflow_result(
        workflow_data=workflow_data,
        runresults=runresults,
        judges=judges,
        output_dir=str(result_dir),
        layout="vertical",
    )
    
    print("\n" + "=" * 80)
    if all_correct_flag:
        print(f"✅ 工作流 '{datas.name}' 所有环节通过")
    else:
        failed_steps_str = ", ".join(map(str, failed_steps))
        print(f"❌ 工作流 '{datas.name}' 有环节失败")
        print(f"   失败环节: 第 {failed_steps_str} 步")
    print("=" * 80)


