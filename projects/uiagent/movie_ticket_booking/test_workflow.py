import time
import traceback
from enum import StrEnum
from pathlib import Path
import os
from typing import Final, Any

import pytest
from PIL import Image
from openai import AsyncOpenAI
from pydantic import BaseModel

from nanoai.model.config import create_client, ModelName
from nanoai.model.vlm import image_from_path
from nanoai.utils.nl_repr import nl_repr
from projects.uiagent.core import UITaskResult, Action
from projects.uiagent.core.action import FinishedAction
from projects.uiagent.core.chat import InfoTask, InfoExecMode
from projects.uiagent.core.flow_data import UIResult
from projects.uiagent.core.test_utils import WorkflowData, StepData
from projects.uiagent.core.visualize import draw_step_result, draw_workflow_result
from projects.uiagent.movie_ticket_booking.workflow import MovieTicketBookingUiFlow, MovieTicketBookingStep, \
    SelectSeatInfo, ConfirmOrderInfo
from projects.uiagent.utils.image_utils import base64_to_temp_file


def load_workflow_dataset(workflow_steps: list[dict[str, Any]]) -> WorkflowData:
    """从 workflow 的 step 列表中构造 WorkflowData，返回迭代器

    Args:
        workflow_steps: workflow 的 step 列表，每个元素是一个字典，包含：
            - query: 查询信息
            - image_path: 图片路径
            - xml_path: xml 路径

    Yields:
        WorkflowData: 构造好的工作流数据
    """
    # 将 workflow_steps 转换为 StepData 列表
    step_datas: list[StepData] = []
    for idx, step_dict in enumerate(workflow_steps, start=1):
        step_data = StepData(
            id=idx,
            priority=1,
            xml_path=step_dict.get("xml_path", None),
            image_path=step_dict["image_path"],
            query=step_dict["query"],
        )
        step_datas.append(step_data)

    # 构造 WorkflowData
    workflow_data = WorkflowData(
        id=0,  # 可以根据需要设置
        steps=step_datas,
        priority=1,
        comment=f"工作流包含 {len(step_datas)} 个步骤",
    )

    return workflow_data

def extract_UITaskResult(result: list[UITaskResult | str]) -> UITaskResult | str| None:
    """从workflow result中提取唯一的UITaskResult"""
    for item in result:
        if isinstance(item, UITaskResult):
            return item
        elif isinstance(item, UIResult):
            return item
        elif isinstance(item, str):
            return item
    return None

class TaskType(StrEnum):
    UI = "ui"
    NL = "nl"

class WorkflowDatas(BaseModel):
    name: str
    description: str
    datas: list[dict[str, Any]]

DATASET_ROOT: Final[Path] = Path(".") / "projects" / "uiagent" / "movie_ticket_booking" / "datasets" / "movie_ticket_booking"
# DATASET_ROOT: Final[Path] = Path(".") / "datasets" / "movie_ticket_booking"

async def normal_workflow1(datas: WorkflowDatas):
    print(datas)


async def test_normal_workflow(datas: WorkflowDatas, debug: bool = False, output_dir: Path = DATASET_ROOT / "outputs"):
    t0 = time.time()
    try:
        workflow = MovieTicketBookingUiFlow()
        output_dir.mkdir(parents=True, exist_ok=True)
        workflow_output_dir = output_dir / datas.name.replace("，","_").replace("：","_").replace(".","_").strip()
        workflow_output_dir.mkdir(parents=True, exist_ok=True)
        workflow_data = load_workflow_dataset(datas.datas)
        runresults = []
        # 必须顺序执行
        all_correct_flag = True
        # for item in datas.datas:
        for i,item in enumerate(datas.datas):
            print(f"\n\n【开始】➡️ 【{i+1}】")
            if hasattr(workflow.state, 'current_step'):
                current_step = workflow.state.current_step
            else:
                current_step = workflow.state.step
            # 从item["image_path"]中提取图片类型
            image_type = item["image_path"].split(".")[-1]
            pil_image = Image.open(item["image_path"])
            image_type = pil_image.format.lower()
            image_output_file_name = f"{i+1}." + image_type
            image_output_file_path = os.path.join(
                workflow_output_dir, image_output_file_name
            )
            print(image_output_file_path)
            text_output_file_name = f"{i+1}_{item['comment'].replace(' ','_')}.txt"
            text_output_file_path = os.path.join(
                workflow_output_dir, text_output_file_name
            )
            image, image_format = image_from_path(item["image_path"])
            # 无xml
            xml = None

            if item["task_type"] == TaskType.UI:
                result = await workflow.run_ui(image, image_format, xml, info=None)
            elif item["task_type"] == TaskType.NL:
                result = await workflow.run_nl(item["query"])
            else:
                raise ValueError(f"Unknown task type: {item['task_type']}")

            try:

                draw_step_result(
                    image_path=base64_to_temp_file(image),
                    query=item["query"] if item["task_type"] == TaskType.NL else "",
                    runresult=result.results,
                    judge=workflow.state.eval_res,
                    output_dir=str(workflow_output_dir),
                    sample_id=f"{i}_{current_step}"
                )
            except:
                pass

            # 处理result.results中的字符串，只保留最后一个\n之后的内容
            if result.results is not None:
                processed_results = []
                for item_result in result.results:
                    if isinstance(item_result, str):
                        # 只保留最后一个\n之后的内容
                        processed_item = item_result.split('\n')[-1] if '\n' in item_result else item_result
                        processed_results.append(processed_item)
                    else:
                        processed_results.append(item_result)
                result.results = processed_results

            if debug:
                print("*"*100)
                print(result.results)
                if not result.results:
                    print(f'error:{result.error}')
                if hasattr(result.state, 'current_step'):
                    current_step = result.state.current_step
                else:
                    current_step = result.state.step
                print(f"当前状态：{current_step}")
                print("*"*100)
            try:
                runresults.append(result.results)
                if isinstance(result.results, str):
                    if result.state.current_step == item["expect_next_step"]:
                        if debug:
                            print(f"预期：{item['expected_result']}")
                            print(f"实际：{result.results}")
                            print(f"测试通过: {item['comment']}")
                            print("-"*50)
                            print(f"意图识别：{workflow.state.intent_cls_res}")
                    else:
                        all_correct_flag = False
                        if debug:
                            print(f"预期：{item['expected_result']}")
                            print(f"实际：{result.results}")
                            print(f"测试失败: {item['comment']}")
                            print("-"*50)
                            print(f"意图识别：{workflow.state.intent_cls_res}")
                elif isinstance(result.results, list):
                    ui_task_result = extract_UITaskResult(result.results)
                    assert ui_task_result is not None
                    if isinstance(ui_task_result, str):
                        # with open(text_output_file_path, "w", encoding="utf-8") as f:
                        #     f.write(ui_task_result)
                        if debug:
                            print(f"预期：{item['expected_result']}")
                            print(f"实际：{result.results}")
                            print(f"测试通过: {item['comment']}")
                            print("-"*50)
                    elif isinstance(ui_task_result, UITaskResult):
                        assert len(ui_task_result.actions) > 0
                        assert isinstance(ui_task_result.actions[0], Action)
                        the_action = ui_task_result.actions[0]
                        # draw_actions(item["image_path"],ui_task_result.actions, output_path=image_output_file_path)
                        if result.state.current_step == item["expect_next_step"] or isinstance(the_action, FinishedAction):
                            if debug:
                                print(f"预期：{item['expected_result']}")
                                print(f"实际：{result.results}")
                                print(f"测试通过: {item['comment']}")
                                print("-"*50)
                        else:
                            all_correct_flag = False
                            if debug:
                                print(f"预期：{item['expected_result']}")
                                print(f"实际：{result.results}")
                                print(f"测试失败: {item['comment']}")
                                print("-"*50)
                                print(f"意图识别：{workflow.state.intent_cls_res}")
                else:
                    all_correct_flag = False
                    if debug:
                        print(f"预期：{item['expected_result']}")
                        print(f"实际：{result.results}")
                        print(f"测试失败: {item['comment']}")
                        print("-"*50)
                        print(f"意图识别：{workflow.state.intent_cls_res}")
            except Exception as e:
                all_correct_flag = False
                if debug:
                    print(f"预期：{item['expected_result']}")
                    print(f"实际：{result.results}")
                    print(f"测试失败: {item['comment']}")
                    print("-"*50)
                    print(f"意图识别：{workflow.state.intent_cls_res}")
                    print(f"异常信息：{e}")
            if debug:
                print("="*100)
        if hasattr(workflow.state, 'current_step'):
            current_step = result.state.current_step
        else:
            current_step = result.state.step

        try:
            draw_step_result(
                image_path=base64_to_temp_file(image),
                query=item["query"] if item["task_type"] == TaskType.NL else "",
                runresult=result.results,
                judge=workflow.state.eval_res,
                output_dir=str(workflow_output_dir),
                sample_id=f"{i}_{current_step}"
            )
        except:
            pass

        if all_correct_flag:
            print(f"名为{datas.name}的workflow所有环节通过")
        else:
            print(f"名为{datas.name}的workflow有环节失败")
        judges = [None] * len(runresults)
        draw_workflow_result(
            workflow_data=workflow_data,
            runresults=runresults,
            judges=judges,
            output_dir=str(workflow_output_dir),
            layout="vertical",
        )
    except:
        traceback.print_exc()
    finally:
        print(f"{datas.name}耗时：{time.time() - t0:.2f}s")


test_data =[
    {
        "comment": "测试理想情况下，用户一口气给出所有信息，用最少的步骤购买电影票",
        "query": "帮我在艺术影城买一张今天晚上八点二十的阿凡达3电影票",
        "image_path": str(DATASET_ROOT / "images" / "01_01_首页_001.png"),
        "xml_path": "",
        "expected_result": "点击购票按钮",
        "expect_next_step": MovieTicketBookingStep.SELECT_MOVIE,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步提取到信息，这一步开始执行",
        "query": "",
        "image_path": str(DATASET_ROOT / "images" / "01_01_首页_001.png"),
        "xml_path": "",
        "expected_result": "点击购票按钮",
        "expect_next_step": MovieTicketBookingStep.SELECT_MOVIE,
        "task_type": TaskType.UI,
    }
]
test_workflow_datas = WorkflowDatas(
    name="测试workflow",
    description="test",
    datas=test_data,
)

@pytest.mark.asyncio
async def test_normal_workflow1():
    await test_normal_workflow(test_workflow_datas, debug=True)

@pytest.mark.asyncio
async def test_info_task_get_select_seat_info():
    from projects.uiagent.jie_parking.data_define import PayOrNot, UserMeaning
    def standard_info_task_gen(brief: str, info_type: type[BaseModel]) -> str:
        return f""""你是一个非常专业的万能的接线员，负责与用户进行沟通并总结和记录下来关键信息。"
                现在，阅读最下方你与一位用户的对话记录，从对话记录中，总结和提取出下方的关键信息:
                {nl_repr(info_type)}
                你还需用到的一些背景信息如下:
                当前时间：2025-12-24 12:00:00
                在这个过程中，如果你看到上面的关键信息有scratchpad，既草稿纸的话，你就特别需要灵活运用草稿纸来临时记录一些细节，总结，或者你的想法等。
                不要漏掉任何细节，你是非常无微不至的，有任何可能需要向用户确认的细节问题都先记载在草稿纸上。
                同时，类似的细节如果可以得到答案，那么你也要细细记录在草稿纸上以防你忘记了各种细节要求。
                你非常聪明仔细，对话记录里提到了的信息就一定要提取和总结出来到关键信息里！

                请以json格式返回。
                """
    the_messages = [
        {'role': 'user', 'content': '帮我在沃美影城买一张1月4号晚上七点四十五的阿凡达3电影票'},
    ]
    # info_task = InfoTask(
    #     brief="pay_000", info_type=PayOrNot, exec_mode=InfoExecMode.NL_ANY, info_gen=standard_info_task_gen)
    info_task = InfoTask(
        brief="user_m_000", info_type=SelectSeatInfo, exec_mode=InfoExecMode.NL_ANY, info_gen=standard_info_task_gen)
    print()
    for i in range(10):
        client, _ = create_client(
            ModelName.DOUBAO_1_5_UI_TARS_250428, AsyncOpenAI)
        res = await info_task.arun(
            "帮我在沃美影城买一张1月4号晚上七点四十五的阿凡达3电影票",
            the_messages,
            model="doubao-seed-1-6-flash-250828",
            # model="doubao-seed-1-6-250615",
            client=client,
        )
        print(f"第 {i + 1} 次调用结果: {res}")

@pytest.mark.asyncio
async def test_info_task_get_confirm_order_info():
    from projects.uiagent.jie_parking.data_define import PayOrNot, UserMeaning
    def standard_info_task_gen(brief: str, info_type: type[BaseModel]) -> str:
        return f""""你是一个非常专业的万能的接线员，负责与用户进行沟通并总结和记录下来关键信息。"
                现在，阅读最下方你与一位用户的对话记录，从对话记录中，总结和提取出下方的关键信息:
                {nl_repr(info_type)}
                你还需用到的一些背景信息如下:
                当前时间：2025-12-24 12:00:00
                在这个过程中，如果你看到上面的关键信息有scratchpad，既草稿纸的话，你就特别需要灵活运用草稿纸来临时记录一些细节，总结，或者你的想法等。
                不要漏掉任何细节，你是非常无微不至的，有任何可能需要向用户确认的细节问题都先记载在草稿纸上。
                同时，类似的细节如果可以得到答案，那么你也要细细记录在草稿纸上以防你忘记了各种细节要求。
                你非常聪明仔细，对话记录里提到了的信息就一定要提取和总结出来到关键信息里！

                请以json格式返回。
                """
    the_messages = [
        {'role': 'user', 'content': '帮我在艺术影城买一张今天晚上八点二十的阿凡达3电影票'},
    ]
    # info_task = InfoTask(
    #     brief="pay_000", info_type=PayOrNot, exec_mode=InfoExecMode.NL_ANY, info_gen=standard_info_task_gen)
    info_task = InfoTask(
        brief="user_m_000", info_type=ConfirmOrderInfo, exec_mode=InfoExecMode.NL_ANY, info_gen=standard_info_task_gen)
    print()
    for i in range(10):
        client, _ = create_client(
            ModelName.DOUBAO_1_5_UI_TARS_250428, AsyncOpenAI)
        res = await info_task.arun(
            "帮我在艺术影城买一张今天晚上八点二十的阿凡达3电影票",
            the_messages,
            model="doubao-seed-1-6-flash-250828",
            # model="doubao-seed-1-6-250615",
            client=client,
        )
        print(f"第 {i + 1} 次调用结果: {res}")

# if __name__ == '__main__':
#     import asyncio
#
#     asyncio.run(test_normal_workflow1(test_workflow_datas))