import asyncio
import time
import traceback
from enum import StrEnum
from pathlib import Path
import os
from PIL import Image

from new_workflow import JieParkingWorkflow, ParkingSteps, JieParkingSelectCarButtons, jie_parking_intent_categories
from pydantic import BaseModel, Field

from nanoai.model.vlm import image_from_path
from projects.uiagent.core.action import Action, ActionType, FinishedAction
from projects.uiagent.core.flow_data import UIResult
from projects.uiagent.core.visualize import draw_workflow_result, draw_step_result
from projects.uiagent.core import UITaskResult
from projects.uiagent.jie_parking.datasets import DATASET_ROOT
from projects.uiagent.jie_parking.jie_uiflow import JieUIFlow
from projects.uiagent.jie_parking.workflow_eval import load_workflow_dataset
from projects.uiagent.utils.image_utils import base64_to_temp_file

root_path = DATASET_ROOT / "jie_parking"

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
    datas: list[dict]

class AssertAction(BaseModel): # 更精确地校验，
    action_type: ActionType = Field(title="动作类型名称", description="名称"
    )
    target: str = Field(default="", title="目标", description="目标，只有部分click有目标，看step里是否明确提取出按钮名")

# 从首页无订单，到询问用户车牌，输入车牌，金额确认，支付确认，到最后二维码结束的一个最全最标准workflow case。
full_workflow_test_data = [
    {
        "comment": "端到端case id:1 上一步ask_human是否给其他车缴费，这一步给了一个明确车牌的query，当前图对应粤C58921无订单，预期输出click左上角的车牌处尝试切换车牌",
        "query": "",
        "image_path": str(root_path / "images" / "订单查询_001.jpg"),
        "xml_path": str(root_path / "xmls" / "普通首页.xml"),
        "expected_result": "点左上角的车牌处尝试切换车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:1 上一步ask_human是否给其他车缴费，这一步给了一个明确车牌的query，当前图对应粤C58921无订单，预期输出click左上角的车牌处尝试切换车牌",
        "query": "鄂A12456",
        "image_path": str(root_path / "images" / "订单查询_001.jpg"),
        "xml_path": str(root_path / "xmls" / "普通首页.xml"),
        "expected_result": "点左上角的车牌处尝试切换车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    # {
    #     "comment": "端到端case id:1 选择车辆界面因为用户默认车牌无订单，且没提供新的车牌，反问用户是否给其他车辆缴费",
    #     "query": "",
    #     "image_path": str(root_path / "images" / "订单查询_001.jpg"),
    #     "xml_path": str(root_path / "xmls" / "普通首页.xml"),
    #     "expected_result": "问：是否给其他车辆缴费",
    #     "expect_next_step": ParkingSteps.SELECT_CAR,
    #     "task_type": TaskType.UI,
    # },
    {
        "comment": "端到端case id:1 车牌信息与用户希望缴费的车牌号粤C58921不符，根据规则，应点击《其他车辆》选项。",
        "query": "",
        "image_path": str(root_path / "images" / "选择其他车辆_010.jpg"),
        "xml_path": str(root_path / "xmls" / "普通首页.xml"), # 需要使用 '"月卡"'字样的
        "expected_result": "选择其他车辆页面运行预期click《其他车辆》",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:1 上一步点击了其他车辆按钮，这一步尝试使用RPA输入省份",
        "query": "",  
        "image_path": str(root_path / "images" / "车牌输入省份键盘.png"),
        "xml_path": str(root_path / "xmls" / "输入省份.xml"),
        "expected_result": "RPA,输入省份运行预期click",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:1 上一步RPA输入省份，这一步尝试RPA输入号码部分",
        "query": "",
        "image_path": str(root_path / "images" / "输入车牌_001.jpg"),
        "xml_path": str(root_path / "xmls" / "输入号码.xml"),
        "expected_result": "RPA输入号码运行预期click",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:1 上一步RPA输入鄂A12456号码部分，这一步应该回到选择车辆页面(当前有费用信息，预期反问用户金额是否正确)",
        "query": "",
        "image_path": str(root_path / "images" / "订单查询_008.jpg"),
        "xml_path": str(root_path / "xmls" / "查看订单明细.xml"),
        "expected_result": "回到选择车辆页面后因为有订单所以预期询问费用是否正确。",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:1 上一步向用户寻求确认金额是否正确，这一步预计用户回答正确并点击查看费用明细并进入订单详情)",
        "query": "正确",  
        "image_path": str(root_path / "images" / "订单查询_008.jpg"),
        "xml_path": str(root_path / "xmls" / "查看订单明细.xml"),
        "expected_result": "预期跳转到支付并询问是否支付。",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.NL,
    },
    {
        "comment": "端到端case id:1 上一步点击进入了订单详情，这一步预计向用户询问是否支付)",
        "query": "",  
        "image_path": str(root_path / "images" / "订单缴费_008.jpg"),
        "xml_path": "",
        "expected_result": "预期反问用户是否支付",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:1 上一步询问了用户是否立即支付，这一步用户回答立即支付，预期点击确认订单)",
        "query": "立即支付",  
        "image_path": str(root_path / "images" / "订单缴费_008.jpg"),
        "xml_path": "",
        "expected_result": "预期跳转到PAYMENT。",
        "expect_next_step": ParkingSteps.PAYMENT,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步用户回答支付，这一步进入去支付）",
        "query": "",
        "image_path": str(root_path / "images" / "支付去支付.jpg"),
        "xml_path": "",
        "expected_result": "预期点击去支付",
        "expect_next_step": ParkingSteps.PAYMENT,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点击了去支付，这一步进入了支付订单支付弹窗页面，预期点击二维码支付那个超链接文字",
        "query": "",
        "image_path": str(root_path / "images" / "支付订单支付弹窗.png"),
        "xml_path": "",
        "expected_result": "预期点击超链接文字：二维码支付",
        "expect_next_step": ParkingSteps.PAYMENT,
        "task_type": TaskType.UI,
    },
    {
        "comment": "测试二维码页面是否能正常结束（当前页无info_task，预期finished）",
        "query": "",
        "image_path": str(root_path / "images" / "1017(二维码).png"),
        "xml_path": "",
        "expected_result": "预期finished动作并告知用户直接扫码支付",
        "expect_next_step": "END",
        "task_type": TaskType.UI,
    },
]
the_full_workflow_test_data = WorkflowDatas(
    name="捷停车全流程工作流用例",
    description="从首页无订单，到询问用户车牌，输入车牌，金额确认，支付确认，到最后二维码结束的一个最全最标准workflow case。",
    datas=full_workflow_test_data,
)
# 从首页无订单，到询问用户车牌，输入车牌，依然无订单，第一次尝试点击刷新订单，第二次尝试反问用户是否给其他车缴费，用户说了一个车牌号，然后转向给新的车牌号缴费
no_order_test_data = [
    {
        "comment": "端到端case id:3 上一步问用户车牌，这一步用户给了一个车牌，尝试点击左上角按钮点切换车牌",
        "query": "给沪A12345缴费",  
        "image_path": str(root_path / "images" / "订单查询_001.jpg"),
        "xml_path": str(root_path / "xmls" / "普通首页.xml"),
        "expected_result": "预期点击左上角切换车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "端到端case id:3 选择车辆界面因为用户默认车牌无订单，且没提供新的车牌，反问用户是否给其他车辆缴费",
        "query": "",  
        "image_path": str(root_path / "images" / "订单查询_001.jpg"),
        "xml_path": str(root_path / "xmls" / "普通首页.xml"),
        "expected_result": "预期问用户要车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 快捷车牌信息与用户希望缴费的车牌号沪A12345不符，应点击《其他车辆》选项去输入车牌。",
        "query": "",
        "image_path": str(root_path / "images" / "选择其他车辆_010.jpg"),
        "xml_path": str(root_path / "xmls" / "普通首页.xml"),
        "expected_result": "选择其他车辆页面运行预期click《其他车辆》",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步点击了其他车辆按钮，这一步尝试使用RPA输入省份",
        "query": "",  
        "image_path": str(root_path / "images" / "车牌输入省份键盘.png"),
        "xml_path": str(root_path / "xmls" / "输入省份.xml"),
        "expected_result": "RPA,输入省份运行预期click",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步RPA输入省份，这一步尝试RPA输入号码部分",
        "query": "",
        "image_path": str(root_path / "images" / "输入车牌_001.jpg"),
        "xml_path": str(root_path / "xmls" / "输入号码.xml"),
        "expected_result": "RPA输入号码运行预期click",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步RPA输入沪A12345号码部分，这一步应该回到沪A12345的首页，该车依然无订单，所以尝试点击一次刷新订单按钮",
        "query": "",
        "image_path": str(root_path / "images" / "订单查询_002.jpg"),
        "xml_path": str(root_path / "xmls" / "普通首页.xml"),
        "expected_result": "预期尝试点击一次刷新订单按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步因为无订单，尝试点击一次刷新订单按钮了，这次就询问用户是否给其他车缴费",
        "query": "",
        "image_path": str(root_path / "images" / "订单查询_002.jpg"),
        "xml_path": str(root_path / "xmls" / "普通首页.xml"),
        "expected_result": "预期询问用户是否给其他车缴费",
        "expected_result_detail": AssertAction(action_type=ActionType.ASK, target="当前车辆沪A12345没有订单，是否需要给其他车缴费？"),
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步询问用户是否给其他车缴费，这一步用户说给鄂A12456缴费，开始尝试点击切换车辆",
        "query": "那给鄂A12456缴费吧",
        "image_path": str(root_path / "images" / "订单查询_002.jpg"),
        "xml_path": str(root_path / "xmls" / "普通首页.xml"),
        "expected_result": "预期再次点击切换车辆按钮",
        "expected_result_detail": AssertAction(action_type=ActionType.CLICK, target=""),
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]
the_no_order_test_data = WorkflowDatas(
    name="捷停车无订单工作流用例",
    description="从首页无订单，到询问用户车牌，输入车牌，依然无订单，第一次尝试点击刷新订单，第二次尝试反问用户是否给其他车缴费，用户说了一个车牌号，然后转向给新的车牌号缴费。",
    datas=no_order_test_data,
)

big_fee_start_data = [
    {
        "comment": "端到端case id:6 首页直接大额订单",
        "query": "",
        "image_path": str(root_path / "images" / "订单查询_004.jpg"),
        "xml_path": str(root_path / "xmls" / "普通首页.xml"),
        "expected_result": "预期询问用户是否查看金额",
        "expected_result_detail": AssertAction(action_type=ActionType.ASK, target="请确认是否查看大额费用？"),
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:6 首页直接大额订单",
        "query": "帮我停车缴费沪E12345",
        "image_path": str(root_path / "images" / "订单查询_004.jpg"),
        "xml_path": str(root_path / "xmls" / "普通首页.xml"),
        "expected_result": "预期询问用户是否给其他车缴费",
        "expected_result_detail": AssertAction(action_type=ActionType.CLICK, target=JieParkingSelectCarButtons.VIEW_AMOUNT.value),
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

legal_select_car_xml = "首页月卡"
async def test_normal_workflow(datas: WorkflowDatas, debug=False,output_dir=root_path / "outputs"):
    t0 = time.time()
    try:
        # new_intent_categories = jie_parking_intent_categories
        # workflow = JieParkingWorkflow(intent_categories=new_intent_categories)
        workflow = JieUIFlow()
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
            # 读取xml文件
            xml = (
                Path(item["xml_path"]).read_text(encoding="utf-8") if item["xml_path"] != "" else legal_select_car_xml
            )
            if item["expected_result"] == "预期再次点击切换车辆按钮":
                print(1)
            elif item["expected_result"] == "预期询问用户是否给其他车缴费":
                print(2)
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

if __name__ == "__main__":
    # test_normal_workflow(the_full_workflow_test_data,debug=True) # 2025.12.3 pass
    # test_normal_workflow(the_no_order_test_data,debug=True) # 2025.12.3 pass
    pass
