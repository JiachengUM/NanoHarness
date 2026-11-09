import asyncio
import json
from functools import partial
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from nanoai.utils.async_utils import amap, with_param_parse_async
from nanoai.utils.nl_repr import nl_repr
from projects.uiagent.core import JudgeResult, WorkflowResult
from projects.uiagent.core.test_utils import (
    StepData,
    StepEvalResult,
    eval_step_batch,
    load_step_dataset,
    run_step_batch,
    run_ui_step,
)
from projects.uiagent.jie_parking.datasets import DATASET_ROOT
from projects.uiagent.jie_parking.new_workflow import (
    JieParkingState,
    JieParkingWorkflow,
    ParkingSteps,
    PlateNumber,
)

step_mapping = {
    0: ParkingSteps.SELECT_CAR,
    1: ParkingSteps.INPUT_PLATE_PROVINCE,
    2: ParkingSteps.INPUT_PLATE_LETTER_NUM,
    # 3: ParkingSteps.CONFIRM_FEE,
    4: ParkingSteps.PAYMENT,
    # 5: ParkingSteps.CLOSE_ORDER_AD,
    6: ParkingSteps.CONFIRM_PAY,
}


class StepDataJieParking(StepData):
    step: ParkingSteps | None = None
    """这里支持None是为了支持工作流数据集的加载"""

    image_path: str | dict[str, str]
    """这里支持dict是为了支持工作流数据集的加载"""

    comment: str = Field(
        default="", description="备注, 用于记录该case的任意信息，给人读, 给人用的。"
    )

    @field_validator("step", mode="before")
    @classmethod
    def convert_to_estep(cls, v):
        if isinstance(v, ParkingSteps):
            return v
        v = int(v)
        zero_based = v  # data 文件 0~4 -> 程序 0~4
        if zero_based in step_mapping:
            return step_mapping[zero_based]
        raise ValueError(f"无效的步骤编号: {v}，支持的编号为 1-5")

    # 对xml_path进行处理，如果xml_path为''，则设置为None
    @field_validator("xml_path", mode="before")
    @classmethod
    def convert_to_xml_path(cls, v):
        if v == "":
            return None
        return str(v)


def test_batch_eval() -> None:
    """测试单步评估"""
    root_path = DATASET_ROOT / "dataset"
    steps = load_step_dataset(root_path, StepDataJieParking)[:10]
    for step in steps:
        print(f"step: {step}")
    output_dir = str(DATASET_ROOT / "new_workflow_results")
    # 读取profile，用于按标签统计。以及默认信息，如车牌
    with open(root_path / "datasetProfile.json", "r", encoding="utf-8") as f:
        profile = json.load(f)
    # workflow，需要这个信息
    plate_number = profile["default_user_plate"]
    # 需要将workflow的reflect设置为True，否则全算为错了。
    results = run_step_batch(
        steps,
        JieParkingWorkflow,
        save_image_root=output_dir,
        state_params={"default_user_plate": plate_number},
    )
    # 传入tags，用于按标签统计。
    eval_result = eval_step_batch(
        results, steps, save_image_root=output_dir, tags=profile["total_tags"]
    )
    eval_result.print()


def test_run_ui_step():
    """测试单步评估"""
    root_path = DATASET_ROOT / "dataset"
    # id 3 7 失败,需要调试
    steps = load_step_dataset(root_path, StepDataJieParking)[0]
    plate_number = "湘AAU5667"
    result = asyncio.run(
        run_ui_step(
            JieParkingWorkflow,
            steps.image_path,
            steps.step,
            steps.info,
            steps.xml_path,
            output_dir=str(DATASET_ROOT / "new_workflow_results"),
            state_params={"default_user_plate": plate_number},
        )
    )
    print(result)


################################################################
#  上述eval的代码不适合badcase测试，下面是badcase测试的代码
################################################################

root_path = DATASET_ROOT / "jie_parking"
BAD_CASES = [
    {
        "comment": "端到端case id:3 选择车辆界面因为用户默认车牌无订单，且没提供新的车牌，反问用户是否给其他车辆缴费",
        "query": "",
        "image_path": str(root_path / "images" / "订单查询_001.jpg"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "粤C58921",
        "expected_result": "是否给其他车辆缴费",
        "type": "ui",
    },
    {
        "comment": "端到端case id:3 上一步ask_human是否给其他车缴费，这一步给了一个明确车牌的query，当前图对应粤C58921无订单，预期输出click左上角的车牌处尝试切换车牌",
        "query": "鄂A12456",
        "image_path": str(root_path / "images" / "订单查询_001.jpg"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "粤C58921",
        "expected_result": "点左上角的车牌处尝试切换车牌",
        "type": "ui",
    },
    {
        "comment": "端到端case id:3 车牌信息与用户希望缴费的车牌号粤C58921不符，根据规则，应点击《其他车辆》选项。",
        "query": "",
        "image_path": str(root_path / "images" / "选择其他车辆_010.jpg"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "粤C58921",
        "expected_result": "选择其他车辆页面运行预期click《其他车辆》",
        "type": "ui",
    },
    {
        "comment": "端到端case id:3 上一步点击了其他车辆按钮，这一步尝试使用RPA输入省份",
        "query": "鄂A12456",  # rpa需要，绘制的坐标渲染有问题！
        "image_path": str(root_path / "images" / "车牌输入省份键盘.png"),
        "xml_path": str(root_path / "xmls" / "输入省份.xml"),
        "step": 1,
        "state_params_info": "",
        "expected_result": "RPA,输入省份运行预期click",
        "type": "ui",
    },
    {
        "comment": "端到端case id:3 上一步RPA输入省份，这一步尝试RPA输入号码部分",
        "query": "鄂A12456",  # rpa需要，绘制的坐标渲染有问题！
        "image_path": str(root_path / "images" / "输入车牌_001.jpg"),
        "xml_path": str(root_path / "xmls" / "输入号码.xml"),
        "step": 2,
        "state_params_info": "",
        "expected_result": "RPA输入号码运行预期click",
        "type": "ui",
    },
    {
        "comment": "端到端case id:3 上一步RPA输入鄂A12456号码部分，这一步应该回到选择车辆页面(当前有费用信息，预期点击《查看费用明细》)",
        "query": "",  # rpa需要，绘制的坐标渲染有问题！
        "image_path": str(root_path / "images" / "订单查询_008.jpg"),
        "xml_path": "",
        "step": 3,
        "state_params_info": "鄂A12456",
        "expected_result": "回到选择车辆页面后因为有订单所以预期询问费用是否正确。",
        "type": "ui",
    },
    {
        "comment": "端到端case id:3 点击了查看费用明细，这一步进入了订单详情)",
        "query": "",  # rpa需要，绘制的坐标渲染有问题！
        "image_path": str(root_path / "images" / "订单查询_008.jpg"),
        "xml_path": "",
        "step": 3,
        "state_params_info": "鄂A12456",
        "expected_result": "预期询问是否支付，是的话跳转到PAYMENT。",
        "type": "ui",
    },
    # 以下为针对选择车辆界面复杂条件判断的测试,line 929
    {
        "comment": "测试短时间所以无需缴费情况,使用默认车牌鄂A123456",
        "query": "",
        "image_path": str(root_path / "images" / "订单查询_006.jpg"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "鄂A123456",
        "expected_result": "应该直接Finished并告诉用户直接开走",
        "type": "ui",
    },
    {
        "comment": "测试找人工直接结束情况，使用默认车牌苏A12345",
        "query": "",
        "image_path": str(root_path / "images" / "订单查询_007.jpg"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "苏A12345",
        "expected_result": "找人工情况，应该直接Finished",
        "type": "ui",
    },
    {
        "comment": "测试月卡无需缴费直接开走情况",
        "query": "",
        "image_path": str(root_path / "images" / "订单查询_005.jpg"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "沪AAJ0635",
        "expected_result": "月卡用户无需缴费可直接开出去，执行finished",
        "type": "ui",
    },
    {
        "comment": "测试金额过大情况",
        "query": "",
        "image_path": str(root_path / "images" / "订单查询_004.jpg"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "沪E12345",
        "expected_result": "测试START金额过大，点击页面中间的《查看金额》按钮，以确认缴费金额",
        "type": "ui",
    },
    {
        "comment": "上一步点击了金额过大时的查看金额按钮，这一步尝试点击去缴费按钮",
        "query": "",
        "image_path": str(root_path / "images" / "1014(首页金额过大弹窗).png"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "苏A23459",
        "expected_result": "应点击该按钮《去缴费》按钮。",
        "type": "ui",
    },
    # line 929  图错误？
    {
        "comment": "测试大金额订单依然询问费用正确与否",
        "query": "",
        "image_path": str(root_path / "images" / "订单缴费_004.jpg"),
        "xml_path": "",
        "step": 4,
        "state_params_info": "沪E12345",
        "expected_result": "测试大金额订单明细询问是否支付",
        "type": "ui",
    },
    {
        "comment": "测试无车牌，首页直接点击输入车牌",
        "query": "",
        "image_path": str(root_path / "images" / "1006(无车牌首页).png"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "鄂A12456",
        "expected_result": "点击《输车牌缴费》进入输入车牌",
        "type": "ui",
    },
    # 以下为测试二维码结束任务部分 969-998
    {
        "comment": "测试二维码页面是否能正常结束（当前页无info_task，预期finished）",
        "query": "",
        "image_path": str(root_path / "images" / "1017(二维码).png"),
        "xml_path": "",
        "step": 4,
        "state_params_info": "湘AAU5667",
        "expected_result": "行finished动作并告知用户直接扫码支付",
        "type": "ui",
    },
    # 测试RPA号码经常失败的case任务部分
    {
        "comment": "用户给了一个有明确车牌的query，预期输出click动作，应该点左上角的车牌处尝试切换车牌",
        "query": "沪E12345",
        "image_path": str(root_path / "images" / "订单查询_001.jpg"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "湘AAU5667",
        "expected_result": "切换车牌",
        "type": "ui",
    },
    {
        "comment": "上一步点击了左上角车牌处，这一步尝试观察是否有其他车辆按钮可点击",
        "query": "",
        "image_path": str(root_path / "images" / "选择其他车辆_010.jpg"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "湘AAU5667",
        "expected_result": "选择其他车辆页面运行预期click",
        "type": "ui",
    },
    {
        "comment": "上一步点击了其他车辆按钮，这一步尝试使用RPA输入省份",
        "query": "湘AAU5667",
        "image_path": str(root_path / "images" / "车牌输入省份键盘.png"),
        "xml_path": str(DATASET_ROOT / "jie_parking" / "xmls" / "输入省份.xml"),
        "step": 1,
        "state_params_info": "湘AAU5667",
        "expected_result": "RPA输入省份运行预期click",
        "type": "ui",
    },
    {
        "comment": "上一步RPA输入省份，这一步尝试RPA输入号码部分",
        "query": "湘AAU5667",
        "image_path": str(root_path / "images" / "输入车牌_001.jpg"),
        "xml_path": str(DATASET_ROOT / "jie_parking" / "xmls" / "输入号码.xml"),
        "step": 2,
        "state_params_info": "湘AAU5667",
        "expected_result": "RPA输入号码运行预期多个click",
        "type": "ui",
    },
    {
        "comment": "上一步RPA输入号码部分，这一步应该回到选择车辆页面",
        "query": "",
        "image_path": str(root_path / "images" / "订单查询_008.jpg"),
        "xml_path": "",
        "step": 3,
        "state_params_info": "鄂A12456",
        "expected_result": "询问确认费用是否正确",
        "type": "ui",
    },
    {
        "comment": "以下为测试query包含非法车牌号的case且没有默认车牌的任务部分，当前有数据校验，被过滤",
        "query": "沪E123",
        "image_path": str(root_path / "images" / "订单查询_001.jpg"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "",
        "expected_result": "这里是非法车牌当做没提取到，找用户要",
        "type": "ui",
    },
    {
        "comment": "测试补缴欠费任务",
        "query": "粤A12345",
        "image_path": str(root_path / "images" / "补缴欠费.png"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "湘AAU5667",
        "expected_result": "预期让用户自己处理一下补缴欠费，Finished",
        "type": "ui",
    },
    {
        "comment": "测试位置授权弹窗任务",
        "query": "粤A12345",
        "image_path": str(root_path / "images" / "位置授权弹窗.png"),
        "xml_path": "",
        "step": 0,
        "state_params_info": "湘AAU5667",
        "expected_result": "预期让用户自己处理一下位置授权弹窗，Finished",
        "type": "ui",
    },
]


class Bad_case_info(StepData):
    # 继承的字段：id, priority, tags, step, xml_path, image_path, query, info

    # 新增字段
    comment: str = Field(
        default="", description="备注, 用于记录该case的任意信息，给人读, 给人用的。"
    )
    state_params_info: str = Field(default="", description="车牌信息，给workflow设置初始状态时使用")
    expected_result: str = Field(default="", description="预期结果，给人读, 给人用的。")
    type: Literal["nl", "ui"] = Field(default="ui", description="类型，nl或ui")
    query: str | None = Field(default=None, description="查询，给workflow使用")
    id: int | str = Field(default="", description="继承StepData的id字段，此处可能不需要")
    step: ParkingSteps | int = Field(default=ParkingSteps.SELECT_CAR, description="步骤")

    @field_validator("step", mode="before")
    @classmethod
    def convert_to_estep(cls, v):
        if isinstance(v, ParkingSteps):
            return v
        v = int(v)
        zero_based = v  # data 文件 0~4 -> 程序 0~4
        if zero_based in step_mapping:
            return step_mapping[zero_based]
        raise ValueError(f"无效的步骤编号: {v}，支持的编号为 1-5")
    # 处理 xml_path：空字符串转为 None
    @field_validator("xml_path", mode="before")
    @classmethod
    def convert_xml_path(cls, v):
        if v == "":
            return None
        return str(v) if v else None

    # 处理 query：空字符串转为 None
    @field_validator("query", mode="before")
    @classmethod
    def convert_query(cls, v):
        if v == "":
            return None
        return str(v) if v else None


def workflow_creator(plate_number: str) -> JieParkingWorkflow:
    new_intent_categories = [
        ("尝试停车缴费工作", "任何与停车缴费可能相关的意图"),
        ("无关意图", "其他任何与停车缴费无关的意图"),
        ("Abort", "用户希望退出，终止，取消当前工作的意图"),
    ]
    workflow = JieParkingWorkflow(intent_categories=new_intent_categories)

    workflow.state.default_user_plate = PlateNumber(plate_number=plate_number)

    return workflow


async def test_jie_parking_step_batch(cases: list[dict[str, str | int]]) -> None:
    """并发版本的测试函数"""
    # 加载数据并用 BaseModel 验证
    # 将字典转换为 Bad_case_info 对象（BaseModel 验证）
    case_objects: list[Bad_case_info] = [Bad_case_info(**case) for case in cases]

    import datetime

    current_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

    params = []
    for case in case_objects:
        params.append(
            (
                (
                    partial(
                        workflow_creator,
                        case.state_params_info,
                    ),
                    case.image_path,
                    case.step,
                ),
                {
                    "info": case.query,
                    "xml_path": case.xml_path,
                    "output_dir": str(DATASET_ROOT / "new_workflow_results_ui"),
                    "output_filename": f"{current_time}_{case.comment[:10]}",
                },
            )
        )

    results, stats = await amap(
        with_param_parse_async(run_ui_step),
        params,
        progress=True,
    )

    for case, result in zip(case_objects, results):
        if isinstance(result, Exception):
            print(f"{case.comment} 执行失败: {result}")
            continue
        print(f"[{case.type.upper()}] {case.comment} 执行成功")
        if result.results is not None:
            print(f"预期结果：{case.expected_result}\n实际结果：{result.results}")
        else:
            print(f"预期结果：{case.expected_result}\n实际结果：{result.state}")
        print("=" * 50)

    step_eval = eval_step_batch(results, case_objects)
    step_eval.print()


def example_bug(data=BAD_CASES[-1]):

    try:
        result = asyncio.run(
            run_ui_step(
                partial(workflow_creator, data["state_params_info"]),
                data["image_path"],
                data["step"],
                data["query"],
                data["xml_path"],
                output_dir=str(DATASET_ROOT / "new_workflow_results"),
            )
        )
        print(nl_repr(result))

    except Exception as exc:
        print("== 缺 task 的调用 ==")
        print(exc)
        print("=" * 50)


from projects.uiagent.core.visualize import draw_workflow_result
from projects.uiagent.core.test_utils import WorkflowData, StepData
from typing import Any
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
    for idx, step_dict in enumerate(workflow_steps,start=1):
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

def test_workflow_draw():
    """测试工作流绘制"""
    from projects.uiagent.jie_parking.workflow_case import id_1_data
    
    # 使用 id_1_data 作为示例
    workflow_data = load_workflow_dataset(id_1_data)
    # 构造模拟的 runresults 和 judges（实际使用时应该从真实执行结果获取）
    # 这里只是示例，实际需要根据真实执行结果填充
    runresults = [["测试str"]] * len(id_1_data)
    judges: list[JudgeResult | None] = [None] * len(id_1_data)
    
    output_dir = str(DATASET_ROOT / "workflow_results_1203")
    draw_workflow_result(
        workflow_data=workflow_data,
        runresults=runresults,
        judges=judges,
        output_dir=output_dir,
        layout="vertical",
    )

def main():
    # data = {
    #     "comment": "测试位置授权弹窗任务",
    #     "query": "粤A12345",
    #     "image_path": str(root_path / "images" / "位置授权弹窗.png"),
    #     "xml_path": "",
    #     "step": 0,
    #     "state_params_info": "湘AAU5667",
    #     "expected_result": "预期让用户自己处理一下位置授权弹窗，Finished",
    #     "type": "ui",
    # }
    # example_bug(data)
    # return
    test_workflow_draw()
    return

    asyncio.run(test_jie_parking_step_batch(BAD_CASES))
    return
    # test_batch_eval()

    # test_run_ui_step()


if __name__ == "__main__":
    main()
