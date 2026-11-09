import asyncio
import os
import traceback
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from nanoai.model.vlm import image_from_path
from nanoai.utils.nl_repr import nl_repr
from projects.uiagent.core import WorkflowResult, WorkflowStatus, UITaskResult, UIStepStatus
from projects.uiagent.core.action import FinishedAction
from projects.uiagent.core.test_utils import run_ui_step
from projects.uiagent.core.visualize import draw_step_result
from projects.uiagent.jie_parking.data_define import CheckKnowingStatus
from projects.uiagent.jie_parking.datasets import DATASET_ROOT
from projects.uiagent.jie_parking.new_workflow import JieParkingWorkflow, ParkingSteps, PlateNumber, \
    KnowingStatus, PayOrNot, ConfirmPayKnowingStatus
from projects.uiagent.jie_parking.rpa.AndroidXmlParser import TextElementLocator
from projects.uiagent.utils.image_utils import get_image_dimensions, base64_to_temp_file

WORKFLOW_DATASET_IMAGE_ROOT = DATASET_ROOT / "jie_parking_with_xml" / "images"
WORKFLOW_DATASET_XML_ROOT = DATASET_ROOT / "jie_parking_with_xml" / "xmls"


ORDER1_PAGES = [
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "新增车牌.png"), str(WORKFLOW_DATASET_XML_ROOT / "新增车牌.xml")), # 新增车牌
    "帮鄂a12456缴纳一下停车费",
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "输入车牌省份_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "输入车牌省份_001.xml")), # 输入号码
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "输入车牌号码_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "输入车牌号码_001.xml")), # 输入号码
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "查看金额_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "查看金额_001.xml")), # 查看金额 # rpa内部路由步骤, 是否能有动作
    "查看金额",
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "缴费确认_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "缴费确认_001.xml")), # 关闭广告 step判断
    "去缴费",
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "确认订单_广告_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "确认订单_广告_001.xml")), # 关闭广告 step判断
    "确认支付订单",
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "确认订单_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "确认订单_001.xml")), # 确认订单
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "去支付_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "去支付_001.xml")), # 确认支付
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "去支付_方式选择_002.png"), str(WORKFLOW_DATASET_XML_ROOT / "去支付_方式选择_002.xml")), # 支付方式选择，默认选二维码
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "去支付_二维码_004.png"), str(WORKFLOW_DATASET_XML_ROOT / "去支付_二维码_004.xml")), # 弹出二维码，任务成功
]

ORDER2_PAGES = [
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "新增车牌.png"), str(WORKFLOW_DATASET_XML_ROOT / "新增车牌.xml")), # 新增车牌
    "帮鄂a12456缴纳一下停车费",
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "输入车牌省份_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "输入车牌省份_001.xml")), # 输入号码
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "输入车牌号码_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "输入车牌号码_001.xml")), # 输入号码
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "查看金额_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "查看金额_001.xml")), # 查看金额 # rpa内部路由步骤, 是否能有动作
    "查看金额",
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "缴费确认_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "缴费确认_001.xml")), # 关闭广告 step判断
    "去缴费",
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "确认订单_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "确认订单_001.xml")), # 确认订单
    "确认支付",
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "去支付_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "去支付_001.xml")), # 确认支付
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "去支付_方式选择_002.png"), str(WORKFLOW_DATASET_XML_ROOT / "去支付_方式选择_002.xml")), # 支付方式选择，默认选二维码
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "去支付_二维码_004.png"), str(WORKFLOW_DATASET_XML_ROOT / "去支付_二维码_004.xml")), # 弹出二维码，任务成功
]


ORDER3_PAGES = [
    "帮鄂a12456缴纳一下停车费",
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "新增车牌.png"), str(WORKFLOW_DATASET_XML_ROOT / "新增车牌.xml")), # 新增车牌
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "输入车牌省份_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "输入车牌省份_001.xml")), # 输入号码
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "输入车牌号码_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "输入车牌号码_001.xml")), # 输入号码
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "查看金额_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "查看金额_001.xml")), # 查看金额 # rpa内部路由步骤, 是否能有动作
    "查看金额",
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "缴费确认_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "缴费确认_001.xml")), # 关闭广告 step判断
    "去缴费",
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "确认订单_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "确认订单_001.xml")), # 确认订单
    "确认支付订单",
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "去支付_001.png"), str(WORKFLOW_DATASET_XML_ROOT / "去支付_001.xml")), # 确认支付
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "去支付_方式选择_002.png"), str(WORKFLOW_DATASET_XML_ROOT / "去支付_方式选择_002.xml")), # 支付方式选择，默认选二维码
    (str(WORKFLOW_DATASET_IMAGE_ROOT / "去支付_二维码_004.png"), str(WORKFLOW_DATASET_XML_ROOT / "去支付_二维码_004.xml")), # 弹出二维码，任务成功
]

ORDER4_WORKFLOW_DATASET_IMAGE_ROOT = DATASET_ROOT / "bad_case_with_xml" / "26ca7a28c44c40eea0149c9f39369592" / "images"
ORDER4_WORKFLOW_DATASET_XML_ROOT = DATASET_ROOT / "bad_case_with_xml" / "26ca7a28c44c40eea0149c9f39369592" / "xmls"

ORDER4_PAGES = [
    "帮我交一下停车费",
    (str(ORDER4_WORKFLOW_DATASET_IMAGE_ROOT / "1_1c6cf434-7471-4aad-a0c5-07b11a2c1e51.png"), str(ORDER4_WORKFLOW_DATASET_XML_ROOT / "1_1c6cf434-7471-4aad-a0c5-07b11a2c1e51.xml")),
    "给鄂A12456交一下停车费",
    (str(ORDER4_WORKFLOW_DATASET_IMAGE_ROOT / "2_c35aad4e-e451-4102-834f-978587aed6ff.png"), str(ORDER4_WORKFLOW_DATASET_XML_ROOT / "2_c35aad4e-e451-4102-834f-978587aed6ff.xml")),
    (str(ORDER4_WORKFLOW_DATASET_IMAGE_ROOT / "4_20004cdd-0715-48e7-ba51-982b7c22ee7f.png"), str(ORDER4_WORKFLOW_DATASET_XML_ROOT / "4_20004cdd-0715-48e7-ba51-982b7c22ee7f.xml")),
    (str(ORDER4_WORKFLOW_DATASET_IMAGE_ROOT / "5_d8a28fa2-f541-43cc-b27a-8c4b14000550.png"), str(ORDER4_WORKFLOW_DATASET_XML_ROOT / "5_d8a28fa2-f541-43cc-b27a-8c4b14000550.xml")),
    "确认查看金额",
    (str(ORDER4_WORKFLOW_DATASET_IMAGE_ROOT / "7_e29272b8-1605-43a9-aeb6-2deaa88c8d59.png"), str(ORDER4_WORKFLOW_DATASET_XML_ROOT / "7_e29272b8-1605-43a9-aeb6-2deaa88c8d59.xml")),
    "金额正确并继续缴费",
    (str(ORDER4_WORKFLOW_DATASET_IMAGE_ROOT / "9_0be96a2a-cc84-4d31-82ac-0830911cab52.png"), str(ORDER4_WORKFLOW_DATASET_XML_ROOT / "9_0be96a2a-cc84-4d31-82ac-0830911cab52.xml")),
    "确认订单",
    (str(ORDER4_WORKFLOW_DATASET_IMAGE_ROOT / "11_23098fc2-7bd4-40fb-b008-cc4dbf1a1b36.png"), str(ORDER4_WORKFLOW_DATASET_XML_ROOT / "11_23098fc2-7bd4-40fb-b008-cc4dbf1a1b36.xml")),
    (str(ORDER4_WORKFLOW_DATASET_IMAGE_ROOT / "9_0be96a2a-cc84-4d31-82ac-0830911cab52.png"), str(ORDER4_WORKFLOW_DATASET_XML_ROOT / "9_0be96a2a-cc84-4d31-82ac-0830911cab52.xml")),
    (str(ORDER4_WORKFLOW_DATASET_IMAGE_ROOT / "13_13130616-f86b-49f3-8d8a-5271b3065570.png"), str(ORDER4_WORKFLOW_DATASET_XML_ROOT / "13_13130616-f86b-49f3-8d8a-5271b3065570.xml")),
    (str(ORDER4_WORKFLOW_DATASET_IMAGE_ROOT / "去支付_方式选择_002.png"), str(ORDER4_WORKFLOW_DATASET_XML_ROOT / "去支付_方式选择_002.xml")),  # 支付方式选择，默认选二维码
    (str(ORDER4_WORKFLOW_DATASET_IMAGE_ROOT / "去支付_二维码_004.png"), str(ORDER4_WORKFLOW_DATASET_XML_ROOT / "去支付_二维码_004.xml")),  # 弹出二维码，任务成功

]

ORDER5_WORKFLOW_DATASET_IMAGE_ROOT = DATASET_ROOT / "bad_case_with_xml" / "0ca0e361e84348518bf2ffd5cd02991c" / "images"
ORDER5_WORKFLOW_DATASET_XML_ROOT = DATASET_ROOT / "bad_case_with_xml" / "0ca0e361e84348518bf2ffd5cd02991c" / "xmls"

ORDER5_PAGES = [
    "给沪E12345缴费",
    (str(ORDER5_WORKFLOW_DATASET_IMAGE_ROOT / "1_253840c9-7646-41df-a93b-7ec5840ce630.png"), str(ORDER5_WORKFLOW_DATASET_XML_ROOT / "1_253840c9-7646-41df-a93b-7ec5840ce630.xml")),
    (str(ORDER5_WORKFLOW_DATASET_IMAGE_ROOT / "4_df452126-b838-473a-a07f-1265851ae873.png"), str(ORDER5_WORKFLOW_DATASET_XML_ROOT / "4_df452126-b838-473a-a07f-1265851ae873.xml")),
]

ORDER6_WORKFLOW_DATASET_IMAGE_ROOT = DATASET_ROOT / "bad_case_with_xml" / "f2c387a56c5e43279a06b5af9efe12b8" / "images"
ORDER6_WORKFLOW_DATASET_XML_ROOT = DATASET_ROOT / "bad_case_with_xml" / "f2c387a56c5e43279a06b5af9efe12b8" / "xmls"

ORDER6_PAGES = [
    "帮我给鄂A123456停车缴费",
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "1_ed8ea0de-098f-453c-ae9c-7367d58ef210.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "1_ed8ea0de-098f-453c-ae9c-7367d58ef210.xml")),
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "2_eb200d7d-6ae9-45b5-ab38-87b83319a7b0.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "2_eb200d7d-6ae9-45b5-ab38-87b83319a7b0.xml")),
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "3_1a2fa1fc-0087-4e82-82b8-5c6d0c761d74.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "3_1a2fa1fc-0087-4e82-82b8-5c6d0c761d74.xml")),
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "4_61c2436e-5468-4687-b222-7e147ed3e57b.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "4_61c2436e-5468-4687-b222-7e147ed3e57b.xml")),
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "5_d6080473-64e6-44d7-ab67-d1494c9257c9.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "5_d6080473-64e6-44d7-ab67-d1494c9257c9.xml")),
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "6_a2f992a1-4307-4233-8bee-c426a0cf9860.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "6_a2f992a1-4307-4233-8bee-c426a0cf9860.xml")),
    "查看金额",
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "7_69fcb77d-d9da-458b-88ec-34a786c1e71b.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "7_69fcb77d-d9da-458b-88ec-34a786c1e71b.xml")),
    "确认订单",
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "去支付_001.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "去支付_001.xml")),
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "去支付_方式选择_002.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "去支付_方式选择_002.xml")),
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "去支付_二维码_004.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "去支付_二维码_004.xml")),
]

ORDER7_PAGES = [
    "帮我给鄂A123456停车缴费",
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "1_ed8ea0de-098f-453c-ae9c-7367d58ef210.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "1_ed8ea0de-098f-453c-ae9c-7367d58ef210.xml")),
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "2_eb200d7d-6ae9-45b5-ab38-87b83319a7b0.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "2_eb200d7d-6ae9-45b5-ab38-87b83319a7b0.xml")),
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "3_1a2fa1fc-0087-4e82-82b8-5c6d0c761d74.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "3_1a2fa1fc-0087-4e82-82b8-5c6d0c761d74.xml")),
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "4_61c2436e-5468-4687-b222-7e147ed3e57b.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "4_61c2436e-5468-4687-b222-7e147ed3e57b.xml")),
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "5_d6080473-64e6-44d7-ab67-d1494c9257c9.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "5_d6080473-64e6-44d7-ab67-d1494c9257c9.xml")),
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "6_a2f992a1-4307-4233-8bee-c426a0cf9860.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "6_a2f992a1-4307-4233-8bee-c426a0cf9860.xml")),
    "更换为皖A123456",
    (str(ORDER6_WORKFLOW_DATASET_IMAGE_ROOT / "8_其他车辆.png"), str(ORDER6_WORKFLOW_DATASET_XML_ROOT / "8_其他车辆.xml")),
]

ORDER8_WORKFLOW_DATASET_IMAGE_ROOT = DATASET_ROOT / "bad_case_with_xml" / "1fe07d33b10a4ab8bd185b9f2dd01c88" / "images"
ORDER8_WORKFLOW_DATASET_XML_ROOT = DATASET_ROOT / "bad_case_with_xml" / "1fe07d33b10a4ab8bd185b9f2dd01c88" / "xmls"

ORDER8_PAGES = [
    "给沪AAJ0635停车缴费",
    (str(ORDER8_WORKFLOW_DATASET_IMAGE_ROOT / "1_aa0160d6-d904-4a1f-83de-0ced8522c971.png"), str(ORDER8_WORKFLOW_DATASET_XML_ROOT / "1_aa0160d6-d904-4a1f-83de-0ced8522c971.xml")),
    (str(ORDER8_WORKFLOW_DATASET_IMAGE_ROOT / "2_e29c8dc1-96e1-4428-b0c7-94893e5dcd41.png"), str(ORDER8_WORKFLOW_DATASET_XML_ROOT / "2_e29c8dc1-96e1-4428-b0c7-94893e5dcd41.xml")),
    (str(ORDER8_WORKFLOW_DATASET_IMAGE_ROOT / "3_7f2be960-0dce-47a5-9ba2-30fa31bc0185.png"), str(ORDER8_WORKFLOW_DATASET_XML_ROOT / "3_7f2be960-0dce-47a5-9ba2-30fa31bc0185.xml")),
    (str(ORDER8_WORKFLOW_DATASET_IMAGE_ROOT / "4_e799b767-c878-4ac3-8f31-abe6dd30cf6a.png"), str(ORDER8_WORKFLOW_DATASET_XML_ROOT / "4_e799b767-c878-4ac3-8f31-abe6dd30cf6a.xml")),
    (str(ORDER8_WORKFLOW_DATASET_IMAGE_ROOT / "5_aa5d10f4-b3e8-4ec2-b4d5-99d2353b31cb.png"), str(ORDER8_WORKFLOW_DATASET_XML_ROOT / "5_aa5d10f4-b3e8-4ec2-b4d5-99d2353b31cb.xml")),
    "换成沪A123456",
    (str(ORDER8_WORKFLOW_DATASET_IMAGE_ROOT / "9_c2bccaa4-69b5-46cb-824d-68af6e5ab8ed.png"), str(ORDER8_WORKFLOW_DATASET_XML_ROOT / "9_c2bccaa4-69b5-46cb-824d-68af6e5ab8ed.xml")),
    (str(ORDER8_WORKFLOW_DATASET_IMAGE_ROOT / "10_唤起键盘.png"), str(ORDER8_WORKFLOW_DATASET_XML_ROOT / "10_唤起键盘.xml")),
    (str(ORDER8_WORKFLOW_DATASET_IMAGE_ROOT / "11_输入省份.png"), str(ORDER8_WORKFLOW_DATASET_XML_ROOT / "11_输入省份.xml")),
    (str(ORDER8_WORKFLOW_DATASET_IMAGE_ROOT / "12_输入号码.png"), str(ORDER8_WORKFLOW_DATASET_XML_ROOT / "12_输入号码.xml")),
]

async def test_workflow(pages, success_condiction=None):
    # assert isinstance(pages[0], tuple), f"workflow第一步必须是图片，因为状态是WAIT_FOR_IMAGE"
    workflow = JieParkingWorkflow()
    date_time = datetime.now().strftime("%Y%m%d%H%M%S")
    output_dir = str(DATASET_ROOT / "workflow_results" / f"{date_time}")
    current_step = workflow.state.current_step
    print(f'========' * 10)
    print(f'{current_step}-{pages[0]}')
    print(f'========' * 10)
    if isinstance(pages[0], str):
        res = await workflow.run_nl(pages[0])
    else:
        image, image_format = image_from_path(pages[0][0])
        xml = Path(pages[0][1]).read_text(encoding="utf-8")
        res = await workflow.run_ui(image, image_format, xml)
    print(f"\n{nl_repr(res)}")

    history: list[WorkflowResult] = [res]

    for idx, path_or_query_or_info in enumerate(pages[1:]):
        current_step = workflow.state.current_step
        current_status = workflow.state.step_status[current_step]
        print(f'========' * 10)
        print(f'{current_step}-{path_or_query_or_info}')
        print(f'========' * 10)

        # if isinstance(path_or_query_or_info, BaseModel) or isinstance(path_or_query_or_info, str):
        #     assert current_status == UIStepStatus.WAIT_FOR_INFO
        # if isinstance(path_or_query_or_info, tuple):
        #     assert current_status in [UIStepStatus.WAIT_FOR_IMAGE, UIStepStatus.ERROR_UI_INVALID]
        if isinstance(path_or_query_or_info, str):
            res = await workflow.run_nl(path_or_query_or_info)
            image = workflow.state.image
            image_format = workflow.state.image_format
            xml = workflow.state.xml
        elif isinstance(path_or_query_or_info, BaseModel):
            image = workflow.state.image
            image_format = workflow.state.image_format
            xml = workflow.state.xml
            res = await workflow.run_ui(
                image,
                image_format,
                xml,
                current_step,
                path_or_query_or_info
            )
        else:
            image, image_format = image_from_path(path_or_query_or_info[0])
            xml = Path(path_or_query_or_info[1]).read_text(encoding="utf-8")
            res = await workflow.run_ui(image, image_format, xml)
        history.append(res)
        query= res.state.nl_query
        print(f"\n{nl_repr(res)}")

        if output_dir is not None and image:
            current_time = datetime.now().strftime("%Y%m%d%H%M%S")
            # TODO: draw_step_result传入image，而不是image_path
            draw_step_result(
                image_path=base64_to_temp_file(image),
                query=query,
                runresult=res.results,
                judge=res.state.eval_res,
                output_dir=output_dir,
                sample_id=f"{idx}_{current_step}_{current_time}_test"
            )

    print(f'========' * 10)
    print(f'{current_step}-{path_or_query_or_info}')
    print(f'========' * 10)
    print(f"\n{nl_repr(res)}")
    if not success_condiction:
        assert res and (res.state.status == WorkflowStatus.SUCCESS or isinstance(res.results[0].actions[0], FinishedAction)), f"status must be SUCCESS or action finished, but got {res.state.status} and {res.results}"
    else:
        assert eval(success_condiction)
    print(f'========' * 10)
    print(f'workflow执行成功')
    print(f'========' * 10)
    return history

def extract_number_from_filename(filename):
    """从文件名中提取数字部分用于排序"""
    basename = os.path.basename(filename)
    # 提取文件名中第一个下划线前的数字部分
    parts = basename.split('_', 1)
    if parts and parts[0].isdigit():
        return int(parts[0])
    return 0  # 如果没有数字前缀，默认返回0


async def fast_test(case_dir: str |Path, success_condiction='True'):
    if isinstance(case_dir, str):
        case_dir = Path(case_dir)
    images_dir = case_dir / "images"
    xmls = case_dir / "xmls"
    images_paths = sorted([str(p) for p in images_dir.glob("*.*")], key=lambda x: extract_number_from_filename(x))
    xmls_paths = sorted([str(p) for p in xmls.glob("*.*")], key=lambda x: extract_number_from_filename(x))
    pages = [
        (image_path, xml_path) if not image_path.endswith(".txt") else Path(image_path).read_text(encoding="utf-8") for image_path, xml_path in zip(images_paths, xmls_paths)
    ]
    history = await test_workflow(pages, success_condiction=success_condiction)
    return history



async def test_workflow_ui_step_async(
        step: str,
        image_path,
        xml_path,
        info: BaseModel | str | None,
        assert_info: str | None = None,
        query: str | None = None
) -> dict:
    """异步版本的测试函数"""
    try:
        print(f"\ntest_workflow_ui_step: step: {step} info: {info}")

        output_dir = str(DATASET_ROOT / "step_results")
        output_filename = f"{step}_{os.path.basename(image_path).split('.')[0]}.jpg"
        if not query:
            result: WorkflowResult = await run_ui_step(
                JieParkingWorkflow,
                image_path,
                step,
                info=info,
                xml_path=xml_path,
                output_dir=output_dir,
                output_filename=output_filename,
            )

        else: # TODO 改造成 run_nl_step
            # image = self.state.image
            # image_format = self.state.image_format
            workflow = JieParkingWorkflow()
            image, image_format = image_from_path(image_path)
            xml = Path(xml_path).read_text(encoding="utf-8") if xml_path else None
            info = info
            # workflow.set_state(**info, current_step=step, image=image, image_format=image_format, xml=xml)
            nl_result: WorkflowResult = await workflow.run_nl(query)
            result: WorkflowResult = await workflow.run_ui(image, image_format, xml, step=step, info=info)

        draw_step_result(
            image_path=image_path,
            query=nl_repr(info) if info is not None else "",
            runresult=result.results,
            judge=result.state.eval_res,
            output_dir=output_dir,
            sample_id=output_filename)
        print(f"\nresult\n{nl_repr(result)}")

        assert result.state.status != WorkflowStatus.ERROR, f'{image_path}执行错误：{result.state.error_details}'
        if assert_info:
            try:
                if_pass = eval(assert_info)
                if not if_pass:
                    f"通过条件 {assert_info} 未通过"
            except:
                print(f'error assert info: {assert_info}')
                traceback.print_exc()

        return {
            "success": True,
            "step": step,
            "result": result,
            "error": None
        }
    except Exception as e:
        print(f"测试执行出错: {e}")
        return {
            "success": False,
            "step": step,
            "result": None,
            "error": str(e)
        }


async def run_all_tests_concurrently(step_info):
    """并发执行所有测试"""
    # 创建所有测试任务
    tasks = []
    for i, step_data in enumerate(step_info):
        task = test_workflow_ui_step_async(*step_data)
        tasks.append(task)

    # 并发执行所有测试
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 统计结果
    passed = 0
    failed = 0

    print(f"\n{'=' * 50}")
    print("测试报告")
    print(f"{'=' * 50}")

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"✗ 测试 {i + 1} 发生异常: {result}")
            failed += 1
        elif isinstance(result, dict):
            if result["success"]:
                print(f"✓ 测试 {i + 1} 成功")
                passed += 1
            else:
                print(f"✗ 测试 {i + 1} 失败: {result['error']}")
                failed += 1

    print(f"\n总计: {len(results)} 通过: {passed} 失败: {failed}")
    return results


def main_step(step_info) -> None:
    """并发测试主函数"""
    try:
        asyncio.run(run_all_tests_concurrently(step_info))
    except KeyboardInterrupt:
        print("\n用户中断测试执行")
    except Exception as e:
        print(f"测试执行出错: {e}")

NONE_QUERY = NONE_INFO = NONE_ASSERT= None

bad_case_step_info = [
    (
        ParkingSteps.SELECT_CAR,
        str(DATASET_ROOT / "bad_case_with_xml" / "images" / "7fd35a31-da40-42cc-bdd3-9c262cedcdf0.png"),
        str(DATASET_ROOT / "bad_case_with_xml" / "xmls" / "7fd35a31-da40-42cc-bdd3-9c262cedcdf0.xml"),
        PlateNumber(plate_number="鄂A123456"),
        "result.state.status == WorkflowStatus.ERROR_UI_INVALID",
        NONE_QUERY,
    ), (
        ParkingSteps.SELECT_CAR,
        str(DATASET_ROOT / "bad_case_with_xml" / "images" / "223f6800-a362-4ec2-be2d-0c02fa4c7410.png"),
        str(DATASET_ROOT / "bad_case_with_xml" / "xmls" / "223f6800-a362-4ec2-be2d-0c02fa4c7410.xml"),
        PlateNumber(plate_number="沪e12345"),
        NONE_ASSERT,
        NONE_QUERY,
    ), (
        ParkingSteps.SELECT_CAR,
        str(DATASET_ROOT / "bad_case_with_xml" / "images" / "65a2f609-c5a0-4358-94b8-da1b52dd493f.png"),
        str(DATASET_ROOT / "bad_case_with_xml" / "xmls" / "65a2f609-c5a0-4358-94b8-da1b52dd493f.xml"),
        PlateNumber(plate_number="湘ADU5667"),
        NONE_ASSERT,
        NONE_QUERY,
    ), (
        ParkingSteps.CONFIRM_PAY,  # 回答对
        str(DATASET_ROOT / "bad_case_with_xml" / "images" / "5807ecad-91c8-4207-b2ce-21d3d654b962.png"),
        str(DATASET_ROOT / "bad_case_with_xml" / "xmls" / "5807ecad-91c8-4207-b2ce-21d3d654b962.xml"),
        PayOrNot(pay_or_not=ConfirmPayKnowingStatus.YES),
        (
            "TextElementLocator.is_in("
            "result.result.actions[0].x, "
            "result.result.actions[0].y,"
            "TextElementLocator(result.state.xml).get_first_element_by_text('确认订单'), "
            "get_image_dimensions(result.state.image)[0], "
            "get_image_dimensions(result.state.image)[1]"
            ")"
        ),
        NONE_QUERY,
    ),
][:]

normal_case_step_info = [
    (
        ParkingSteps.SELECT_CAR,
        str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "新增车牌.png"),
        str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "新增车牌.xml"),
        PlateNumber(plate_number="鄂a123456"),
        NONE_ASSERT,
        NONE_INFO,
    ), (
        ParkingSteps.SELECT_CAR,
        str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "选择其他车辆_001.png"),
        str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "选择其他车辆_001.xml"),
        PlateNumber(plate_number="鄂A123456"),
        NONE_ASSERT,
        NONE_INFO,
    ), (
        ParkingSteps.SELECT_CAR,
        str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "查看金额_001.png"),
        str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "查看金额_001.xml"),
        PlateNumber(plate_number="鄂A123456"),
        NONE_ASSERT,
        NONE_INFO,
    ), (
        ParkingSteps.SELECT_CAR,
        str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "查看金额_001.png"),
        str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "查看金额_001.xml"),
        PlateNumber(plate_number="鄂A12456"), # 车牌号不同，决策不同
        NONE_ASSERT,
        NONE_INFO,
    ), (
        ParkingSteps.INPUT_PLATE_PROVINCE,
        str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "输入车牌省份_001.png"),
        str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "输入车牌省份_001.xml"),
        PlateNumber(plate_number="鄂A123456"),
        NONE_ASSERT,
        NONE_INFO,
    ), (
        ParkingSteps.INPUT_PLATE_LETTER_NUM,
        str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "输入车牌号码_001.png"),
        str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "输入车牌号码_001.xml"),
        PlateNumber(plate_number="鄂A123456"),
        NONE_ASSERT,
        NONE_INFO,
    ),(
        ParkingSteps.CONFIRM_PAY,
        str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "确认订单_001.png"),
        str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "确认订单_001.xml"),
        PayOrNot(pay_or_not=ConfirmPayKnowingStatus.YES),
        NONE_ASSERT,
        NONE_INFO,
    ), (
        ParkingSteps.CONFIRM_PAY,
        str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "确认订单_广告_001.png"),
        str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "确认订单_广告_001.xml"),
        PayOrNot(pay_or_not=ConfirmPayKnowingStatus.YES),
        NONE_ASSERT,
        NONE_INFO,
    ),
    (
        ParkingSteps.CONFIRM_PAY,
        str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "去支付_001.png"),
        str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "去支付_001.xml"),
        PayOrNot(pay_or_not=ConfirmPayKnowingStatus.YES),
        NONE_ASSERT,
        NONE_INFO,
    ), (
        ParkingSteps.PAYMENT,
        str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "去支付_方式选择_002.png"),
        str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "去支付_方式选择_002.xml"),
        NONE_INFO,
        NONE_ASSERT,
        NONE_INFO,
    ), (
        ParkingSteps.PAYMENT,
        str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "去支付_二维码_004.png"),
        str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "去支付_二维码_004.xml"),
        NONE_INFO,
        NONE_ASSERT,
        NONE_INFO,
    ),
][:]


def main_workflow():
    # asyncio.run(test_workflow(ORDER1_PAGES))
    # asyncio.run(test_workflow(ORDER2_PAGES))
    # asyncio.run(test_workflow(ORDER3_PAGES))
    # asyncio.run(test_workflow(ORDER4_PAGES))
    # asyncio.run(test_workflow(ORDER5_PAGES, success_condiction='"其他车辆" in xml'))
    # asyncio.run(test_workflow(ORDER6_PAGES))
    # asyncio.run(test_workflow(ORDER7_PAGES, success_condiction='"其他车辆" in xml'))
    # asyncio.run(test_workflow(ORDER8_PAGES, success_condiction='"沪" in xml'))
    # asyncio.run(fast_test(r'D:\Projects\nanoai\projects\uiagent\jie_parking\datasets\bad_case_with_xml\6051be33efa84a59983846a852d3b3b7'))
    # asyncio.run(fast_test(r'D:\Projects\nanoai\projects\uiagent\jie_parking\datasets\bad_case_with_xml\9928b74d2932446688e0c22bba4a5af7'))
    asyncio.run(fast_test(r'D:\Projects\nanoai\projects\uiagent\jie_parking\datasets\bad_case_with_xml\433b267a3a844061ad0fe62ae4734468'))
    return

if __name__ == "__main__":
    # main(bad_case_step_info[:])
    # main_step(normal_case_step_info[:])
    main_workflow()