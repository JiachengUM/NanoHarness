import asyncio
import json
import os
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field

from nanoai.utils.async_utils import amap
from nanoai.utils.nl_repr import nl_repr
from projects.uiagent.seatbooking.simple_agent import (
    ActionInfo,
    SimpleAgent,
    SimpleInputRequest,
    SimpleOutputResponse,
)

from seatbooking.datasets import DATASET_ROOT

class ResultToSave(BaseModel):
    trace_id: str | int | None = Field(default=None, description="唯一标识一次会话的ID")
    step: str | None = Field(default=None, description="输入图片所处业务步骤数")
    action_info: ActionInfo = Field(description="动作信息")
    query: str = Field(description="query")
    model_input_prompt: str = Field(description="模型输入prompt")
    reflection_result: str | None = Field(default=None, description="反思结果")
    reflection_advice: str | None = Field(default=None, description="反思建议")


async def a_process_simple_agent_inputs(
    simple_input: SimpleInputRequest,
) -> tuple[SimpleOutputResponse, str, str]:
    """
    处理简单智能体输入请求并返回执行结果与反思信息。

    Args:
        simple_input: 简单智能体输入请求，包含以下字段：
            - trace_id: 唯一标识一次会话的ID
            - query: 用户查询
            - view_image_url: 当前视野图片 URL
            - step: 输入图片所处业务步骤数
            - image_cache_path: 图像缓存路径

    Returns:
        tuple[SimpleOutputResponse, str, str]:
            - output: 简单智能体输出响应
            - reflection_result: 反思结果
            - reflection_advice: 反思建议
    """
    trace_id = simple_input.trace_id
    previous_thought = simple_input.query
    view_image_url = simple_input.view_image_url
    step = simple_input.step
    agent_input = SimpleInputRequest(
        trace_id=trace_id,
        query=previous_thought,
        view_image_url=view_image_url,
        step=step,
        image_cache_path=simple_input.image_cache_path,  # 不使用
    )
    # 初始化时使用simple_input.image_cache_path，内部不使用
    agent = SimpleAgent(image_cache_path=simple_input.image_cache_path)
    output = await agent.a_action_decide(simple_input=agent_input)
    reflection_result, reflection_advice = await agent.a_reflect(agent_output=output)
    return output, reflection_result, reflection_advice


def quick_evaluate(
    dataset_file_path: str, evaluate_result_path: str, image_cache_path: str
) -> None:
    """评估智能体在数据集上的表现"""
    result_file_name = Path(dataset_file_path).stem + "_result.json"
    result_file_path = os.path.join(evaluate_result_path, result_file_name)
    ai_report_file_name = Path(dataset_file_path).stem + "_ai_report.txt"
    ai_report_file_path = os.path.join(evaluate_result_path, ai_report_file_name)

    with open(dataset_file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        result_list = []
        simple_agent_inputs = []
        # 批量处理所有case
        # 批量下载所有的图片到image_cache_path，否则难以批量读取处理
        for line in lines:
            data = json.loads(line)
            view_image_url = data["image_path"]
            trace_id = data["id"]
            step = data["step"]
            query = data["query"]
            simple_agent_inputs.append(
                SimpleInputRequest(
                    image_cache_path=image_cache_path,
                    trace_id=trace_id,
                    query=query,
                    view_image_url=view_image_url,
                    step=step,
                )
            )
        task_results, _ = asyncio.run(
            amap(
                a_process_simple_agent_inputs,
                simple_agent_inputs,
                max_concurrent=3,
                progress=True,
            )
        )
        total_num = 0
        correct_num = 0
        failed_num = 0
        for result in task_results:
            # 检查结果是否为异常对象
            total_num += 1
            if isinstance(result, Exception):
                # 跳过当前结果，继续处理下一个
                failed_num += 1
                print(f"处理失败，出现异常: {result}")
                continue
            output, reflection_result, reflection_advice = result
            if reflection_result == "right":
                correct_num += 1
            # 将 output 中的字段拆出放入 result_item
            result_item = ResultToSave(
                trace_id=output.trace_id,
                step=output.step,
                action_info=output.action_info,
                query=output.query,
                model_input_prompt=output.model_input_prompt,
                reflection_result=reflection_result,
                reflection_advice=reflection_advice,
            )
            result_list.append(result_item)
        correct_rate = f"{float(correct_num / total_num) * 100:.2f}%"
        failed_rate = f"{float(failed_num / total_num) * 100:.2f}%"

    with open(result_file_path, "a", encoding="utf-8") as of:
        for an_item in result_list:
            of.write(json.dumps(an_item.model_dump(), ensure_ascii=False) + "\n")

    # 大模型解读结果
    ai_read_report = nl_repr(result_list)
    with open(ai_report_file_path, "w", encoding="utf-8") as wf:
        wf.write("correct rate is " + correct_rate + "\n")
        wf.write("failed num is " + str(failed_num) + "\n")
        wf.write("failed rate is " + failed_rate + "\n\n")
        wf.write(ai_read_report)


if __name__ == "__main__":
    dataset_file_path = DATASET_ROOT / "seatbooking" / "references" / "output.jsonl"
    test_dataset_file_path = (
        DATASET_ROOT / "seatbooking" / "references" / "output2.jsonl"
    )
    problem_file_path = (
        DATASET_ROOT / "seatbooking" / "references" / "problem_cases.jsonl"
    )

    quick_evaluate(
        image_cache_path=str(DATASET_ROOT / "seatbooking" / "cache" / "image_cache"),
        dataset_file_path=str(dataset_file_path),
        evaluate_result_path=str(DATASET_ROOT / "seatbooking" / "tests" / "output"),
    )
