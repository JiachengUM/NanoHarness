from projects.uiagent.jie_parking.datasets import DATASET_ROOT
from new_workflow import  ParkingSteps
from test_workflow import TaskType
from test_workflow import test_normal_workflow, WorkflowDatas

id_1_data =[
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌",
        "query": "帮我给沪A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "获取车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "车牌不一致，点击切换车辆按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_5_输入车牌号码_001沪.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_5_输入车牌号码_001沪.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，询问用户是否确认金额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "问：是否确认金额，看费用对不对",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否确认金额，用户确认费用是正确的",
        "query": "查看明细",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "点击查看明细",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了查看明细，这一步询问用户是否支付",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "09_确认订单_002.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "09_确认订单_002.xml"),
        "expected_result": "询问是否支付",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否支付，用户确认支付",
        "query": "确认支付",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "09_确认订单_002.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "09_确认订单_002.xml"),
        "expected_result": "点击确认订单按钮",
        "expect_next_step": ParkingSteps.PAYMENT,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了确认订单按钮，这一步去支付，不需要用户确认",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "10_去支付_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "10_去支付_001.xml"),
        "expected_result": "点击《去支付》按钮",
        "expect_next_step": ParkingSteps.PAYMENT,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点了去支付，进行方式选择，此时会自动执行，不需要用户信息",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "11_去支付_方式选择_002.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "11_去支付_方式选择_002.xml"),
        "expected_result": "点击《二维码支付》按钮",
        "expect_next_step": ParkingSteps.PAYMENT,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点击了二维码支付，这一步显示二维码，结束任务",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "12_去支付_二维码_004.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "12_去支付_二维码_004.xml"),
        "expected_result": "结束任务，并告知用户直接扫码支付",
        "expect_next_step": "END",
        "task_type": TaskType.UI,
    },

]
ID_1 = WorkflowDatas(
    name="CASE_1，全流程用例",
    description="车牌不匹配，询问车牌，提供车牌，点击切换车辆，输入车牌，确认金额，确认支付，点击确认订单按钮，点击去支付按钮，点击二维码支付按钮，显示二维码，结束任务，并告知用户直接扫码支付",
    datas=id_1_data,
)

id_2_data =[

    {
        "comment": "缴费意图",
        "query": "帮我缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "提取不到信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "询问车牌信息",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，车牌一致，尝试刷新",
        "query": "帮我给浙A4R568停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "刷新订单(rpa没有刷新动作)",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },

]

ID_2 = WorkflowDatas(
    name="CASE_2，起始query无车牌，询问车牌信息，提供车牌，相同则刷新订单",
    description="找用户提供车牌信息",
    datas=id_2_data,
)

id_3_data = [
    {
        "comment": "端到端case id:3 上一步问用户车牌，这一步用户给了一个车牌，尝试点击左上角按钮点切换车牌",
        "query": "给沪A12345缴费",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "提取到车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "端到端case id:3 选择车辆界面因为用户默认车牌无订单，且没提供新的车牌，反问用户是否给其他车辆缴费",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击左上角切换车辆按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 快捷车牌信息与用户希望缴费的车牌号沪A12345不符，应点击《其他车辆》选项去输入车牌。",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "选择其他车辆页面运行预期click《其他车辆》",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步点击了其他车辆按钮，这一步尝试使用RPA输入省份",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "RPA,输入省份运行预期click",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步RPA输入省份，这一步尝试RPA输入号码部分",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_2_输入车牌号码_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_2_输入车牌号码_001.xml"),
        "expected_result": "RPA输入号码运行预期click",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步RPA输入沪A12345号码部分，这一步应该回到沪A12345的首页，该车依然无订单，所以尝试点击一次刷新订单按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单2_沪A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单2_沪A12345.xml"),
        "expected_result": "预期尝试点击一次刷新订单按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步因为无订单，尝试点击一次刷新订单按钮了，这次就询问用户是否给其他车缴费",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单2_沪A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单2_沪A12345.xml"),
        "expected_result": "预期询问用户是否给其他车缴费",
        # "expected_result_detail": AssertAction(action_type=ActionType.ASK, target="当前车辆沪A12345没有订单，是否需要给其他车缴费？"),
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步询问用户是否给其他车缴费，这一步用户说给鄂A12456缴费，开始尝试点击切换车辆",
        "query": "那给鄂A12456缴费吧",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单2_沪A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单2_沪A12345.xml"),
        "expected_result": "预期再次点击切换车辆按钮",
        # "expected_result_detail": AssertAction(action_type=ActionType.CLICK, target=""),
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_3 = WorkflowDatas(
    name="CASE_3，起始提供车牌信息，无订单，刷新，提供新车牌..",
    description="找用户提供车牌信息",
    datas=id_3_data,
)

id_19_data =[
    {
        "comment": "浙A4R568，无订单，",
        "query": "帮我缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "无信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供错误车牌",
        "query": "帮我给沪A123停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]
ID_19 = WorkflowDatas(
    name="CASE_19，query自带车牌信息",
    description="query自带车牌信息",
    datas=id_19_data,
)



id_5_data =[
    {
        "comment": "用户说一个无关意图话",
        "query": "wwww 去去去",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "找用户提供车牌信息",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "找用户提供车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
]
ID_5 = WorkflowDatas(
    name="CASE_5，用户说一个无关意图话，找用户提供车牌信息",
    description="找用户提供车牌信息",
    datas=id_5_data,
)

id_27_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我交停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "回复好的收到之类的，目前是更新了所有infotask",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "没有车牌",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供车牌",
        "query": "帮我给沪A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "下一步找用户确认金额，问：是否查看费用明细，看费用对不对",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问用户是否确认金额，用户确认费用是正确的",
        "query": "金额正确",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "点击查看明细",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]
ID_27 = WorkflowDatas(
    name="CASE_27，相同车牌，不给车牌拉起服务，提供车牌，有费用，用户确认费用不正确，终止",
    description="相同车牌，先拉起服务，提供车牌，有费用，用户确认费用不正确，终止",
    datas=id_27_data,
)

id_32_data = [
    {
        "comment": "浙A4R568，无订单，",
        "query": "帮我停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "提取不到信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我给浙A4R5停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供车牌",
        "query": "啊，最后漏了两个数字68",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "预计刷新订单",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },

]
ID_32 = WorkflowDatas(
    name="CASE_32，多轮对话，补充车牌号码",
    description="多轮对话，补充车牌号码",
    datas=id_32_data,
)

id_25_data =[
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌",
        "query": "帮我停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "获取车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "车牌不一致，点击切换车辆按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌",
        "query": "帮我给沪A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "获取车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "车牌不一致，点击切换车辆按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_2_输入车牌号码_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_2_输入车牌号码_001.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "此时有费用信息，询问用户是否确认金额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "问：是否确认金额，看费用对不对",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否确认金额，用户确认费用是正确的",
        "query": "查看",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "点击查看明细",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了查看明细，这一步询问用户是否支付",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "09_确认订单_002.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "09_确认订单_002.xml"),
        "expected_result": "询问是否支付",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否支付，用户取消支付",
        "query": "取消",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "09_确认订单_002.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "09_确认订单_002.xml"),
        "expected_result": "点击确认订单按钮",
        "expect_next_step": ParkingSteps.PAYMENT,
        "task_type": TaskType.NL,
    },
   

]
ID_25 = WorkflowDatas(
    name="CASE_25，支付环节用户取消支付，终止",
    description="query不提供车牌，询问车牌信息，提供车牌，点击切换车辆，发现不存在列表中，需点击<其他车辆>按钮，输入车牌省份，输入车牌号码，选择车辆，有费用信息，询问用户是否确认金额，用户确认费用是正确的，点击查看明细，询问用户是否支付，用户取消支付，终止",
    datas=id_25_data,
)

id_20_data = [
    {
        "comment": "第三步，有费用信息，预期让用户确认金额",
        "query": "给我鄂A12456缴费",
        "image_path": str(DATASET_ROOT /"jie_parking" / "images" / "订单查询_008.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking" / "xmls" / "查看订单明细.xml"),
        "expected_result": "跳转到验证有费用步骤",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "第三步，有费用信息，预期让用户确认金额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking" / "images" / "订单查询_008.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking" / "xmls" / "查看订单明细.xml"),
        "expected_result": "问：是否确认金额",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "第三步，用户不确定",
        "query": "不确定金额",
        "image_path": str(DATASET_ROOT /"jie_parking" / "images" / "订单查询_008.jpg"),
        "xml_path": "",
        "expected_result": "切换为确认订单步骤并询问用户是否确认订单",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    }
]
ID_20 = WorkflowDatas(
    name="CASE_20，换车牌，费用不正确，终止",
    description="换车牌，费用不正确，终止",
    datas=id_20_data,
)

id_39_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我交停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供车牌",
        "query": "帮我给沪A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "下一步找用户确认金额",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，询问用户是否确认金额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "问：是否确认金额，看费用对不对",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否确认金额，用户确认费用是正确的",
        "query": "算了我要换一个车牌鄂A12345",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "点击左上角换车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_39 = WorkflowDatas(
    name="CASE_39，预期再次点击切换车牌并继续进行缴费任务",
    description="缴费，提供车牌，确认费用，再换车牌，放弃缴费",
    datas=id_39_data,
)


id_42_data =[
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，点击切换车辆，",
        "query": "帮我缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "初始化",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "这一步提供车牌，",
        "query": "帮我给沪A12345缴停车费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "左上角切换车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_2_输入车牌号码_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_2_输入车牌号码_001.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "此时有费用信息，询问用户是否确认金额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "问：是否确认金额，看费用对不对",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否确认金额，用户确认费用是正确的",
        "query": "查看",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "点击查看明细",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了查看明细，这一步询问用户是否支付",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "09_确认订单_002.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "09_确认订单_002.xml"),
        "expected_result": "询问是否支付",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否支付，用户取消支付",
        "query": "什么破玩意儿",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "09_确认订单_002.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "09_确认订单_002.xml"),
        "expected_result": "无关意图，再次询问",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.NL,
    }, 

]
ID_42 = WorkflowDatas(
    name="CASE_42，支付环节无关意图，再次询问",
    description="query不提供车牌，询问车牌信息，提供车牌，点击切换车辆，发现不存在列表中，需点击<其他车辆>按钮，输入车牌省份，输入车牌号码，选择车辆，有费用信息，询问用户是否确认金额，用户确认费用是正确的，点击查看明细，询问用户是否支付，无关意图，重复",
    datas=id_42_data,
)

id_6_data = [
    {
        "comment": "用户query提取用户提供车牌号",
        "query": "帮我停车缴费鄂A12456",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "06_查看金额_大额订单_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "06_查看金额_大额订单_鄂A12456.xml"),
        "expected_result": "提取到车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "提取到车牌，与页面显示车牌比较发现一致，因为大额页面，所以先反问用户是否查看金额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "06_查看金额_大额订单_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "06_查看金额_大额订单_鄂A12456.xml"),
        "expected_result": "反问用户是否查看金额",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步问是否查看金额，这一步要回答",
        "query": "查看金额",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "06_查看金额_大额订单_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "06_查看金额_大额订单_鄂A12456.xml"),
        "expected_result": "点击查看金额",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击查看金额按钮，弹出新页面，询问用户是否确认金额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "07_大额确认页_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "07_大额确认页_鄂A12456.xml"),
        "expected_result": "金额是否正确，是否去缴费",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "用户确认金额正常, 确认缴费",
        "query": "去缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "07_大额确认页_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "07_大额确认页_鄂A12456.xml"),
        "expected_result": "点击去缴费, 跳转确认订单界面",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.NL,
    },
   
]

ID_6 = WorkflowDatas(
    name="CASE_6，提供车牌，有订单，大额查看",
    description="提供车牌，有订单，大额查看",
    datas=id_6_data,
)
id_11_data = [
    {
        "comment": "浙A4R568，无订单，",
        "query": "帮我停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "提取不到信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，点击切换车辆，",
        "query": "帮我换成给沪AAJ0635车牌缴停车费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_2_输入车牌号码_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_2_输入车牌号码_001.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，是月卡用户",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "05_查看金额_月卡_沪AAJ0635.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "05_查看金额_月卡_沪AAJ0635.xml"), # TODO 使用正确的XML, 目前里面车牌号与图片不一致，且坐标错误
        "expected_result": "月卡用户无需缴费可直接开出去，执行finished",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
]

ID_11 = WorkflowDatas(
    name="CASE_11，月卡用户，无需缴费可直接开出去",
    description="query不提供车牌，询问车牌信息，提供车牌，点击切换车辆，发现不存在列表中，需点击<其他车辆>按钮，输入车牌省份，输入车牌号码，选择车辆，有费用信息，月卡用户.",
    datas=id_11_data,
)

id_14_data = [
    {
        "comment": "浙A4R568，无订单，",
        "query": "帮我停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "提取不到信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，点击切换车辆，",
        "query": "帮我换成给鄂A123456停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_3_输入车牌号码_001鄂.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_3_输入车牌号码_001鄂.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，短时无需缴费。",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "03_查看金额_短时无需缴费_鄂A123456.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "03_查看金额_短时无需缴费_鄂A123456.xml"),
        "expected_result": "短时无需缴费可直接开出去，执行finished",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
]

ID_14 = WorkflowDatas(
    name="CASE_14，短时无需缴费可直接开出去",
    description="query不提供车牌，询问车牌信息，提供车牌，点击切换车辆，发现不存在列表中，需点击<其他车辆>按钮，输入车牌省份，输入车牌号码，选择车辆，有费用信息，短时无需缴费可直接开出去.",
    datas=id_14_data,
)

id_28_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我交停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供车牌",
        "query": "帮我给沪A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "下一步找用户确认金额",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，询问用户是否确认金额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "问：是否确认金额，看费用对不对",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否确认金额，有换车牌的意图，但是query不提供具体车牌",
        "query": "算了我要给另一个车牌缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "找用户提供车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_28 = WorkflowDatas(
    name="CASE_28，缴费，提供车牌，确认费用，再换车牌，",
    description="缴费，提供车牌，确认费用，再换车牌（不提供），找用户提供车牌",
    datas=id_28_data,
)

id_40_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我交停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供车牌",
        "query": "帮我给沪A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "下一步找用户确认金额",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，询问用户是否确认金额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "问：是否确认金额，看费用对不对",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否确认金额，有换车牌的意图，但是query提供错误车牌",
        "query": "算了我要给沪E123缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "非法车牌，继续询问",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_40 = WorkflowDatas(
    name="CASE_40，预期因车牌非法继续询问车牌",
    description="缴费，提供车牌，确认费用，提供错误车牌，找用户提供车牌",
    datas=id_40_data,
)


id_36_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我给沪ACR3095停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_定位授权_mocked.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_定位授权_mocked.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供车牌",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_定位授权_mocked.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_定位授权_mocked.xml"),
        "expected_result": "询问用户是否同意捷停车地理位置授权",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否同意捷停车地理位置授权，用户同意",
        "query": "同意",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_定位授权_mocked.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_定位授权_mocked.xml"),
        "expected_result": "点击《同意授权》并继续",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]
ID_36 = WorkflowDatas(
    name="CASE_36，缴费，弹窗授权定位，用户同意授权",
    description="缴费，弹窗授权定位，用户同意授权",
    datas=id_36_data,
)

id_37_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我给沪ACR3095停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_定位授权_mocked.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_定位授权_mocked.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供车牌",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_定位授权_mocked.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_定位授权_mocked.xml"),
        "expected_result": "询问用户是否同意捷停车地理位置授权",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否同意捷停车地理位置授权，用户不同意授权",
        "query": "不同意授权",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_定位授权_mocked.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_定位授权_mocked.xml"),
        "expected_result": "退出小程序",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]
ID_37 = WorkflowDatas(
    name="CASE_37，缴费，弹窗授权定位，用户不同意授权，（直达，rpa和模型都有小问题），xml是mocked的，不确定里面有什么内容",
    description="缴费，弹窗授权定位，用户不同意授权",
    datas=id_37_data,
)

id_43_data = [
    {
        "comment": "这一步用户给了同一个车牌，无订单信息",
        "query": "给浙A4R568缴费",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "预期提取到车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "这一步因为用户默认车牌无订单，有车牌需要点击刷新订单按钮",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击刷新订单按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "刷新后还没有订单，询问用户是否给其他车缴费",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问用户是否给其他车缴费",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步询问用户是否给其他车缴费，这一步用户给错误车牌",
        "query": "那给鄂A124缴费吧",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "错误车牌，继续询问",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_43 = WorkflowDatas(
    name="CASE_43，确认刷新后无订单，询问用户是否给其他车缴费",
    description="有车牌A无信息，query提供车牌A无订单，尝试点击刷新，后无订单，询问用户是否给其他车缴费",
    datas=id_43_data,
)

id_16_data = [
    {
        "comment": "这一步用户给了同一个车牌，无订单信息",
        "query": "给浙A4R568缴费",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "预期提取到车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "这一步因为用户默认车牌无订单，有车牌需要点击刷新订单按钮",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击刷新订单按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "刷新后还没有订单，询问用户是否给其他车缴费",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问用户是否给其他车缴费",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步询问用户是否给其他车缴费，这一步用户终止的意图",
        "query": "好吧那不用了",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "终止的意图，执行finished",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_16 = WorkflowDatas(
    name="CASE_16，确认刷新后无订单，询问用户是否给其他车缴费，用户终止的意图，执行finished",
    description="有车牌A无信息，query提供车牌A无订单，尝试点击刷新，后无订单，询问用户是否给其他车缴费，用户终止的意图，执行finished",
    datas=id_16_data,
)

id_44_data = [
    {
        "comment": "用户query提取用户提供车牌号",
        "query": "帮我停车缴费鄂A12456",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "06_查看金额_大额订单_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "06_查看金额_大额订单_鄂A12456.xml"),
        "expected_result": "提取到车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "提取到车牌，识别到是大额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "06_查看金额_大额订单_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "06_查看金额_大额订单_鄂A12456.xml"),
        "expected_result": "识别到是大额，问用户是否查看",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "用户确认金额正常, 确认查看金额",
        "query": "算了不看了",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "06_查看金额_大额订单_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "06_查看金额_大额订单_鄂A12456.xml"),
        "expected_result": "点击查看查看按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_44 = WorkflowDatas(
    name="CASE_44，提供车牌，有订单，大额查看，用户确认不查看金额",
    description="提供车牌，有订单，大额查看",
    datas=id_44_data,
)

id_45_data = [
    {
        "comment": "用户query提取用户提供车牌号",
        "query": "帮我停车缴费鄂A12456",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "06_查看金额_大额订单_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "06_查看金额_大额订单_鄂A12456.xml"),
        "expected_result": "提取到车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "提取到车牌，识别到是大额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "06_查看金额_大额订单_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "06_查看金额_大额订单_鄂A12456.xml"),
        "expected_result": "识别到是大额，问用户是否查看",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "用户确认金额正常, 确认查看金额",
        "query": "查看",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "06_查看金额_大额订单_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "06_查看金额_大额订单_鄂A12456.xml"),
        "expected_result": "点击查看查看按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "弹窗界面，告知用户当前费用",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "07_大额确认页_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "07_大额确认页_鄂A12456.xml"),
        "expected_result": "告知用户当前费用",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "弹窗界面，用户说当前费用不对",
        "query": "不对这个金额",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "07_大额确认页_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "07_大额确认页_鄂A12456.xml"),
        "expected_result": "点击去缴费, 跳转确认订单界面，询问用户是否确认金额",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_45 = WorkflowDatas(
    name="CASE_45，提供车牌，有订单，大额查看，用户确认不查看金额",
    description="提供车牌，有订单，大额查看",
    datas=id_45_data,
)

id_47_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我交停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "回复好的收到之类的，目前是更新了所有infotask",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，点击切换车辆，",
        "query": "帮我换成给沪AAJ0635停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_2_输入车牌号码_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_2_输入车牌号码_001.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，是月卡用户",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "05_查看金额_月卡_沪AAJ0635.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "05_查看金额_月卡_沪AAJ0635.xml"), # TODO 使用正确的XML, 目前里面车牌号与图片不一致，且坐标错误
        "expected_result": "月卡用户无需缴费可直接开出去，执行finished",
        "expect_next_step": ParkingSteps.END,
        "task_type": TaskType.UI,
    },
    {
        "comment": "提取到新车牌",
        "query": "帮我换成给沪AA4567停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "05_查看金额_月卡_沪AAJ0635.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "05_查看金额_月卡_沪AAJ0635.xml"), # TODO 使用正确的XML, 目前里面车牌号与图片不一致，且坐标错误
        "expected_result": "提取到新车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "准备换车牌",
        "query": "帮我换成给沪AA4567停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "05_查看金额_月卡_沪AAJ0635.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "05_查看金额_月卡_沪AAJ0635.xml"), # TODO 使用正确的XML, 目前里面车牌号与图片不一致，且坐标错误
        "expected_result": "准备换车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },

]

ID_47 = WorkflowDatas(
    name="CASE_47，月卡用户，但是用户需要换车牌",
    description="query不提供车牌，询问车牌信息，提供车牌，点击切换车辆，发现不存在列表中，需点击<其他车辆>按钮，输入车牌省份，输入车牌号码，选择车辆，有费用信息，月卡用户，换车牌.",
    datas=id_47_data,
)

id_48_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我交停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "回复好的收到之类的，目前是更新了所有infotask",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，点击切换车辆，",
        "query": "帮我换成给沪AAJ0635停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_2_输入车牌号码_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_2_输入车牌号码_001.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，是月卡用户",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "05_查看金额_月卡_沪AAJ0635.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "05_查看金额_月卡_沪AAJ0635.xml"), # TODO 使用正确的XML, 目前里面车牌号与图片不一致，且坐标错误
        "expected_result": "月卡用户无需缴费可直接开出去，执行finished",
        "expect_next_step": ParkingSteps.END,
        "task_type": TaskType.UI,
    },
    {
        "comment": "用户终止的意图，预期退出",
        "query": "算了不缴费了",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "05_查看金额_月卡_沪AAJ0635.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "05_查看金额_月卡_沪AAJ0635.xml"), # TODO 使用正确的XML, 目前里面车牌号与图片不一致，且坐标错误
        "expected_result": "预期退出",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },

]

ID_48 = WorkflowDatas(
    name="CASE_48，月卡用户，但是用户需要换车牌，用户终止的意图，",
    description="query不提供车牌，询问车牌信息，提供车牌，点击切换车辆，发现不存在列表中，需点击<其他车辆>按钮，输入车牌省份，输入车牌号码，选择车辆，有费用信息，月卡用户,用户终止的意图，预期退出.",
    datas=id_48_data,
)


id_17_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我交停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "回复好的收到之类的，目前是更新了所有infotask",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，点击切换车辆，",
        "query": "帮我换成给苏A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_4_输入车牌号码_001苏.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_4_输入车牌号码_001苏.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，但要人工处理",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "04_查看金额_人工_苏A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "04_查看金额_人工_苏A12345.xml"),
        "expected_result": "人工收费，需要前往人工",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
]

ID_17 = WorkflowDatas(
    name="CASE_17，用户车辆无法在线缴费，需要前往人工",
    description="query不提供车牌，询问车牌信息，提供车牌，点击切换车辆，发现不存在列表中，需点击<其他车辆>按钮，输入车牌省份，输入车牌号码，选择车辆，有费用信息，用户车辆无法在线缴费，需要前往人工.",
    datas=id_17_data,
)

id_49_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我交停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "回复好的收到之类的，目前是更新了所有infotask",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，点击切换车辆，",
        "query": "帮我换成给苏A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_4_输入车牌号码_001苏.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_4_输入车牌号码_001苏.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，但要人工处理",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "04_查看金额_人工_苏A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "04_查看金额_人工_苏A12345.xml"),
        "expected_result": "人工收费，需要前往人工",
        "expect_next_step": ParkingSteps.END,
        "task_type": TaskType.UI,
    },
    {
        "comment": "提取到新车牌",
        "query": "帮我换成给沪AA4567停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "04_查看金额_人工_苏A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "04_查看金额_人工_苏A12345.xml"),
        "expected_result": "提取到新车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "准备换车牌",
        "query": "帮我换成给沪AA4567停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "04_查看金额_人工_苏A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "04_查看金额_人工_苏A12345.xml"),
        "expected_result": "准备换车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },

]

ID_49 = WorkflowDatas(
    name="CASE_49，用户车辆无法在线缴费，需要前往人工,用户换个车牌",
    description="query不提供车牌，询问车牌信息，提供车牌，点击切换车辆，发现不存在列表中，需点击<其他车辆>按钮，输入车牌省份，输入车牌号码，选择车辆，有费用信息，用户车辆无法在线缴费，需要前往人工，用户再换车牌.",
    datas=id_49_data,
)

id_50_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我交停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "回复好的收到之类的，目前是更新了所有infotask",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，点击切换车辆，",
        "query": "帮我换成给苏A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_4_输入车牌号码_001苏.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_4_输入车牌号码_001苏.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，但要人工处理",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "04_查看金额_人工_苏A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "04_查看金额_人工_苏A12345.xml"),
        "expected_result": "人工收费，需要前往人工",
        "expect_next_step": ParkingSteps.END,
        "task_type": TaskType.UI,
    },
    {
        "comment": "终止缴费意图",
        "query": "好吧算了吧",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "04_查看金额_人工_苏A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "04_查看金额_人工_苏A12345.xml"),
        "expected_result": "预期退出",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },

]

ID_50 = WorkflowDatas(
    name="CASE_50，用户车辆无法在线缴费，需要前往人工,用户终止的意图，预期退出",
    description="query不提供车牌，询问车牌信息，提供车牌，点击切换车辆，发现不存在列表中，需点击<其他车辆>按钮，输入车牌省份，输入车牌号码，选择车辆，有费用信息，用户车辆无法在线缴费，需要前往人工，用户终止缴费意图.",
    datas=id_50_data,
)
id_51_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我交停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "回复好的收到之类的，目前是更新了所有infotask",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，点击切换车辆，",
        "query": "帮我换成给鄂A123456停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_3_输入车牌号码_001鄂.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_3_输入车牌号码_001鄂.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时短时无需缴费",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "03_查看金额_短时无需缴费_鄂A123456.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "03_查看金额_短时无需缴费_鄂A123456.xml"),
        "expected_result": "短时无需缴费",
        "expect_next_step": ParkingSteps.END,
        "task_type": TaskType.UI,
    },
    {
        "comment": "终止缴费意图",
        "query": "换成给沪AA4567停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "03_查看金额_短时无需缴费_鄂A123456.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "03_查看金额_短时无需缴费_鄂A123456.xml"),
        "expected_result": "提取到新车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步有新车牌，准备换车牌",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "03_查看金额_短时无需缴费_鄂A123456.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "03_查看金额_短时无需缴费_鄂A123456.xml"),
        "expected_result": "点击左上角换车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
]

ID_51 = WorkflowDatas(
    name="CASE_51，用户车辆短时无需缴费，用户说换车牌，",
    description="query不提供车牌，询问车牌信息，提供车牌，点击切换车辆，发现不存在列表中，需点击<其他车辆>按钮，输入车牌省份，输入车牌号码，选择车辆，有费用信息，短时无需缴费，用户说换车牌",
    datas=id_51_data,
)


id_52_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我交停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "回复好的收到之类的，目前是更新了所有infotask",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，点击切换车辆，",
        "query": "帮我换成给鄂A123456停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_3_输入车牌号码_001鄂.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_3_输入车牌号码_001鄂.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时短时无需缴费",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "03_查看金额_短时无需缴费_鄂A123456.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "03_查看金额_短时无需缴费_鄂A123456.xml"),
        "expected_result": "短时无需缴费",
        "expect_next_step": ParkingSteps.END,
        "task_type": TaskType.UI,
    },
    {
        "comment": "终止缴费意图",
        "query": "好吧算了吧",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "03_查看金额_短时无需缴费_鄂A123456.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "03_查看金额_短时无需缴费_鄂A123456.xml"),
        "expected_result": "预期退出",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },

]

ID_52 = WorkflowDatas(
    name="CASE_52，用户车辆短时无需缴费，用户终止的意图，预期退出",
    description="query不提供车牌，询问车牌信息，提供车牌，点击切换车辆，发现不存在列表中，需点击<其他车辆>按钮，输入车牌省份，输入车牌号码，选择车辆，有费用信息，短时无需缴费，用户终止缴费意图.",
    datas=id_52_data,
)



id_53_data = [
    {
        "comment": "浙A4R568，无订单，",
        "query": "帮我交停车费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，点击切换车辆，",
        "query": "帮我换成给粤A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_5_输入车牌号码_001粤.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_5_输入车牌号码_001粤.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时用户欠费",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "13_补缴欠费_粤A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "13_补缴欠费_粤A12345.xml"),
        "expected_result": "用户欠费",
        "expect_next_step": ParkingSteps.END,
        "task_type": TaskType.UI,
    },
    {
        "comment": "终止缴费意图",
        "query": "退出吧",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "13_补缴欠费_粤A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "13_补缴欠费_粤A12345.xml"),
        "expected_result": "预期退出",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },

]

ID_53 = WorkflowDatas(
    name="CASE_53，用户车辆欠费，用户终止的意图，预期退出",
    description="query不提供车牌，询问车牌信息，提供车牌，点击切换车辆，发现不存在列表中，需点击<其他车辆>按钮，输入车牌省份，输入车牌号码，选择车辆，欠费，用户终止缴费意图，预期退出.",
    datas=id_53_data,
)

id_31_data = [
    {
        "comment": "这一步用户给了方言讲的车牌，背景是用户无订单信息",
        "query": "给沪A幺两三456交一下停车费",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单2_沪A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单2_沪A12345.xml"),
        "expected_result": "正常提取到新车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "这一步因为与用户提供车牌不一致，需要点击左上角切换车辆按钮",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单2_沪A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单2_沪A12345.xml"),
        "expected_result": "点击左上角切换车辆按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
]

ID_31 = WorkflowDatas(
    name="CASE_31，语言部分，方言讲车牌，正常提取到新车牌，点击左上角切换车辆按钮",
    description="语言部分，方言讲错车牌，正常提取到新车牌，点击左上角切换车辆按钮",
    datas=id_31_data,
)

id_82_data = [
    {
        "comment": "这一步用户给了口齿不清的话，未提及车牌，背景是用户无订单信息",
        "query": "帮我呃给啊啊啊那个啊呃交一下呃，呃停停停车费",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单2_沪A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单2_沪A12345.xml"),
        "expected_result": "未提取到车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "由于刚刚无车牌，需要问询用户车牌信息",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单2_沪A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单2_沪A12345.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
]

ID_82 = WorkflowDatas(
    name="CASE_82，语言部分，模拟用户口齿不清或语音转文本不准确",
    description="语言部分，模拟用户口齿不清或语音转文本不准确",
    datas=id_82_data,
)


id_83_data = [
    {
        "comment": "这一步用户给了口齿不清的话，提及车牌，背景是用户无订单信息",
        "query": "给那个啥，鄂，鄂，A那啥，幺两嗯三四呃五六交一下，交交一下停车费。",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单2_沪A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单2_沪A12345.xml"),
        "expected_result": "预计能够提取到车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "这一步因为与用户提供车牌不一致，需要点击左上角切换车辆按钮",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单2_沪A12345.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单2_沪A12345.xml"),
        "expected_result": "点击左上角切换车辆按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
]

ID_83 = WorkflowDatas(
    name="CASE_83，语言部分，模拟用户口齿不清或语音转文本不准确",
    description="语言部分，模拟用户口齿不清或语音转文本不准确",
    datas=id_83_data,
)

id_7_9_data =[
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌",
        "query": "帮我给沪A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "获取车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "车牌不一致，点击切换车辆按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_2_输入车牌号码_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_2_输入车牌号码_001.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，询问用户是否确认金额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "问：是否确认金额，看费用对不对",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否确认金额，用户确认费用是正确的",
        "query": "查看明细",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "点击查看明细",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.NL,
    },
]

ID_7= WorkflowDatas(
    name="CASE_7，rpa输车牌，后有费用。",
    description="rpa输车牌，后有费用。",
    datas=id_7_9_data,
)

ID_9= WorkflowDatas(
    name="CASE_9，进入订单确认环节，用户说对的，有反馈",
    description="进入订单确认环节，用户说对的，有反馈",
    datas=id_7_9_data,
)

id_10_data =[
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌",
        "query": "帮我给沪A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "获取车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "车牌不一致，点击切换车辆按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_2_输入车牌号码_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_2_输入车牌号码_001.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，询问用户是否确认金额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "问：是否确认金额，看费用对不对",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
]

ID_10= WorkflowDatas(
    name="CASE_10，进行订单状态信息播报，停车多长时间，金额，是否需要查看费用明细",
    description="进行订单状态信息播报，停车多长时间，金额，是否需要查看费用明细",
    datas=id_10_data,
)

id_15_data = [
    {
        "comment": "这一步用户给了同一个车牌，无订单信息",
        "query": "给浙A4R568缴费",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "预期提取到车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "这一步因为用户默认车牌无订单，有车牌需要点击刷新订单按钮",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击刷新订单按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "刷新后还没有订单，询问用户是否给其他车缴费",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问用户是否给其他车缴费",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步询问用户是否给其他车缴费，这一步用户给新的车牌",
        "query": "那给鄂A12456缴费吧",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击切换车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_15 = WorkflowDatas(
    name="CASE_15，确认刷新后无订单，询问用户是否给其他车缴费，用户给新的车牌",
    description="有车牌A无信息，query提供车牌A无订单，尝试点击刷新，后无订单，询问用户是否给其他车缴费，用户给新的车牌",
    datas=id_15_data,
)

id_21_data = [
    {
        "comment": "这一步用户给了同一个车牌，无订单信息",
        "query": "给浙A4R568缴费",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "预期提取到车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "这一步因为用户默认车牌无订单，有车牌需要点击刷新订单按钮",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击刷新订单按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "刷新后还没有订单，询问用户是否给其他车缴费",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问用户是否给其他车缴费",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步询问用户是否给其他车缴费，这一步用户终止缴费意图",
        "query": "退下",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "预期退出",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_21 = WorkflowDatas(
    name="CASE_21，确认刷新后无订单，询问用户是否给其他车缴费，用户终止缴费意图，预期退出",
    description="有车牌A无信息，query提供车牌A无订单，尝试点击刷新，后无订单，询问用户是否给其他车缴费，用户终止缴费意图，预期退出",
    datas=id_21_data,
)

id_22_data = [
    {
        "comment": "这一步同时提到缴费和终止缴费意图",
        "query": "交一下停车，哎，算了",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "直接结束任务，告知用户 我随时都在",
        "expect_next_step": ParkingSteps.END,
        "task_type": TaskType.NL,
    },
]

ID_22 = WorkflowDatas(
    name="CASE_22，同时提到缴费和终止缴费意图，直接结束任务，告知用户 我随时都在",
    description="同时提到缴费和终止缴费意图，直接结束任务，告知用户 我随时都在",
    datas=id_22_data,
)


id_23_data = [
    {
        "comment": "这一步模拟有较多干扰信息加入，预期还是可以正常缴费",
        "query": "行行行，嗯。给浙A4R568交一下停车费。啊？好的好的好的。",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "预期提取到车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "这一步因为用户默认车牌无订单，有车牌需要点击刷新订单按钮",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击刷新订单按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "刷新后还没有订单，询问用户是否给其他车缴费",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问用户是否给其他车缴费",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步询问用户是否给其他车缴费，这一步用户终止缴费意图",
        "query": "退下",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "预期退出",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_23 = WorkflowDatas(
    name="CASE_23，这一步模拟有较多干扰信息加入，预期还是可以走正常缴费流程",
    description="这一步模拟有较多干扰信息加入，预期还是可以走正常缴费流程",
    datas=id_23_data,
)

id_24_data = [
    {
        "comment": "这一步用户没提供车牌",
        "query": "交停车费",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "预期提取到车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "询问用户车牌信息",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问用户车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步询问用户是否给其他车缴费，这一步用户终止缴费意图",
        "query": "算了不交了",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "预期退出",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_24 = WorkflowDatas(
    name="CASE_24，用户没提供车牌，询问用户车牌信息，预期退出",
    description="用户没提供车牌，询问用户车牌信息，预期退出",
    datas=id_24_data,
)


id_26_data = [
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我交停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "回复好的收到之类的，目前是更新了所有infotask",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供车牌",
        "query": "帮我给沪A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "下一步找用户确认金额",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，询问用户是否查看费用明细",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "问：是否查看费用明细，看费用对不对",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否确认金额，用户不确定是否正确",
        "query": "不知道哎",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "预计返回首页",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]
ID_26 = WorkflowDatas(
    name="CASE_26，相同车牌，不给车牌拉起服务，提供车牌，有费用，用户不确定是否正确，预计返回首页",
    description="相同车牌，先拉起服务，提供车牌，有费用，用户不确定是否正确，预计返回首页",
    datas=id_26_data,
)

id_29_data = [
    {
        "comment": "这一步用户没提供车牌",
        "query": "交停车费",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "03_查看金额_短时无需缴费_鄂A123456.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "03_查看金额_短时无需缴费_鄂A123456.xml"),
        "expected_result": "未提取到车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "询问用户车牌信息",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "03_查看金额_短时无需缴费_鄂A123456.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "03_查看金额_短时无需缴费_鄂A123456.xml"),
        "expected_result": "询问用户车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步询问用户是否给其他车缴费，这一步用户提供车牌",
        "query": "鄂A123456",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "03_查看金额_短时无需缴费_鄂A123456.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "03_查看金额_短时无需缴费_鄂A123456.xml"),
        "expected_result": "提取到车牌,识别为短时无需缴费，finished",
        "expect_next_step": ParkingSteps.END,
        "task_type": TaskType.NL,
    },
    {
        "comment": "端到端case id:3 上一步询问用户是否给其他车缴费，这一步用户提供车牌",
        "query": "那就给沪A12345缴费吧",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "03_查看金额_短时无需缴费_鄂A123456.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "03_查看金额_短时无需缴费_鄂A123456.xml"),
        "expected_result": "新一轮，换车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]
ID_29 = WorkflowDatas(
    name="CASE_29，用户没提供车牌，询问用户车牌信息，提供车牌，识别为短时无需缴费，新一轮换车牌",
    description="用户没提供车牌，询问用户车牌信息，提供车牌，识别为短时无需缴费，新一轮换车牌",
    datas=id_29_data,
)


id_30_data = [
    {
        "comment": "这一步用户没提供车牌",
        "query": "交停车费",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "未提取到车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "询问用户车牌信息",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "询问用户车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步询问用户是否给其他车缴费，这一步用户提供车牌",
        "query": "沪A12345",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "提取到车牌,识别为小额订单，询问是否查看明细，金额是否正确",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "查看明细",
        "query": "，好的，金额是对的，好的，金额是对的，好的，金额是对的",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "点击查看明细",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.NL,
    },
    {
        "comment": "询问用户是否支付",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "09_确认订单_002.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "09_确认订单_002.xml"),
        "expected_result": "询问是否支付，支付请说立即支付",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.UI,
    },
    {
        "comment": "用户确认支付或换车牌",
        "query": "还是给鄂A123456缴费吧",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "09_确认订单_002.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "09_确认订单_002.xml"),
        "expected_result": "回复：不好意思，当前只能处理缴费...",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.NL,
    },
]
ID_30 = WorkflowDatas(
    name="CASE_30，询问是否支付，用户确认支付或换车牌，回复：不好意思，当前只能处理缴费...",
    description="用户没提供车牌，询问用户车牌信息，提供车牌，识别为小额订单，询问是否查看明细，金额是否正确，询问是否支付，用户确认支付或换车牌，回复：不好意思，当前只能处理缴费...",
    datas=id_30_data,
)

id_38_data = [
    {
        "comment": "浙A4R568，无订单，",
        "query": "帮我停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "提取不到信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "这一步query不提供车牌",
        "query": "帮我给沪A123停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供车牌",
        "query": "啊，最后漏了两个数字45",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "播报当前费用，询问是否查看明细",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },

]
ID_38 = WorkflowDatas(
    name="CASE_38，错误车牌，询问车牌信息，提供车牌，播报费用，询问是否查看明细",
    description="错误车牌，询问车牌信息，提供车牌，播报费用，询问是否查看明细",
    datas=id_38_data,
)

id_41_data = [
    {
        "comment": "这一步用户没提供车牌",
        "query": "交停车费",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "未提取到车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "询问用户车牌信息",
        "query": "",  
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "询问用户车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "端到端case id:3 上一步询问用户是否给其他车缴费，这一步用户提供车牌",
        "query": "沪A12345",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "提取到车牌,识别为小额订单，播报金额询问是否查看明细，金额是否正确",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "询问用户是否查看明细",
        "query": "烦死了还要确认",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "保持现状并回复，告知当前只能处理缴费...",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.NL,
    },
]
ID_41 = WorkflowDatas(
    name="CASE_41，无关意图，保持现状并回复，告知当前只能处理缴费...",
    description="无关意图，保持现状并回复，告知当前只能处理缴费...",
    datas=id_41_data,
)


id_46_data = [
    {
        "comment": "浙A4R568，无订单，",
        "query": "帮我停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "提取不到信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "这一步query提供车牌，尝试刷新订单",
        "query": "帮我给浙A4R568停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击刷新订单按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供车牌",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "确认当前车牌无订单，询问新车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },

]
ID_46 = WorkflowDatas(
    name="CASE_46，二次确认当前车牌无订单",
    description="二次确认当前车牌，确认当前车牌是否正确",
    datas=id_46_data,
)

id_54_data = [
    {
        "comment": "浙A4R568，无订单，",
        "query": "帮我交停车费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，点击切换车辆，",
        "query": "帮我换成给粤A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_5_输入车牌号码_001粤.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_5_输入车牌号码_001粤.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时用户欠费",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "13_补缴欠费_粤A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "13_补缴欠费_粤A12345.xml"),
        "expected_result": "告知用户欠费",
        "expect_next_step": ParkingSteps.END,
        "task_type": TaskType.UI,
    },
    {
        "comment": "终止缴费意图",
        "query": "那换成鄂A123456吧。",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "13_补缴欠费_粤A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "13_补缴欠费_粤A12345.xml"),
        "expected_result": "点击左上角换车牌",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },

]

ID_54 = WorkflowDatas(
    name="CASE_54，用户车辆欠费，用户换车牌，点击左上角换车牌",
    description="用户车辆欠费，用户换车牌，点击左上角换车牌",
    datas=id_54_data,
)

id_55_data =[
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌",
        "query": "帮我给沪A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "获取车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "车牌不一致，点击切换车辆按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_2_输入车牌号码_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_2_输入车牌号码_001.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，询问用户是否确认金额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "问：是否确认金额，看费用对不对",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否确认金额，用户确认费用是正确的",
        "query": "查看明细",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "点击查看明细",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了查看明细，这一步询问用户是否支付",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "09_确认订单_002.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "09_确认订单_002.xml"),
        "expected_result": "询问是否支付",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否支付，用户取消支付",
        "query": "不支付了，退出",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "09_确认订单_002.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "09_确认订单_002.xml"),
        "expected_result": "终止缴费意图，预期退出",
        "expect_next_step": ParkingSteps.PAYMENT,
        "task_type": TaskType.NL,
    }
]
ID_55 = WorkflowDatas(
    name="CASE_55，支付环节用户取消支付，终止",
    description="支付环节用户取消支付，终止",
    datas=id_55_data,
)

id_56_data =[
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌",
        "query": "帮我给沪A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "获取车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "车牌不一致，点击切换车辆按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌省份",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_1_输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "rpa点击省份按钮，下一步输入数字",
        "expect_next_step": ParkingSteps.INPUT_PLATE_LETTER_NUM,
        "task_type": TaskType.UI,
    },
    {
        "comment": "rpa输入车牌号码",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_2_输入车牌号码_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_2_输入车牌号码_001.xml"),
        "expected_result": "rpa点击号码按钮，下一步选择车辆",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "进入新车牌的页面，此时有费用信息，询问用户是否确认金额",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "问：是否确认金额，看费用对不对",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否确认金额，用户确认费用是正确的",
        "query": "查看明细",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "点击查看明细",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击了查看明细，这一步跳转至广告页面，询问用户是否支付",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "08_确认订单_广告_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "08_确认订单_广告_001.xml"),
        "expected_result": "询问",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问用户是否支付，用户确认支付",
        "query": "立即支付",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "08_确认订单_广告_001.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "08_确认订单_广告_001.xml"),
        "expected_result": "点击取消购买，进入正常页面",
        "expect_next_step": ParkingSteps.CONFIRM_PAY,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步点击掉了广告，这一步跳转至正常页面",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "09_确认订单_002.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "09_确认订单_002.xml"),
        "expected_result": "点击确认订单",
        "expect_next_step": ParkingSteps.PAYMENT,
        "task_type": TaskType.UI,
    },
]
ID_56 = WorkflowDatas(
    name="CASE_56，支付环节有广告，询问用户是否支付，用户确认支付，点击取消购买，进入正常页面",
    description="支付环节有广告，询问用户是否支付，用户确认支付，点击取消购买，进入正常页面",
    datas=id_56_data,
)

# 公共前置步骤数据
_common_prefix_86 = [
    {
        "comment": "浙A4R568，无订单，",
        "query": "帮我缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "无信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
]

id_86_data = _common_prefix_86 + [
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供错误车牌，第一位字母要大写",
        "query": "帮我给沪a34567停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息（但是好像已经进行了转写，此时点击左上角换车牌。）",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_86 = WorkflowDatas(
    name="CASE_86，非法车牌的第一位字母要大写",
    description="不提供车牌，询问车牌信息，提供各种错误车牌，继续询问车牌信息",
    datas=id_86_data,
)

id_87_data = _common_prefix_86 + [
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，警车",
        "query": "帮我给沪A9567警的车牌停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "此时点击左上角换车牌。",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_87 = WorkflowDatas(
    name="CASE_87，特殊车牌，警车",
    description="不提供车牌，询问车牌信息，提供各种错误车牌，继续询问车牌信息",
    datas=id_87_data,
)

id_88_data = _common_prefix_86 + [
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌，驾校教练车",
        "query": "帮我给教练车车牌沪A5678学停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "此时点击左上角换车牌。",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_88 = WorkflowDatas(
    name="CASE_88，特殊车牌，驾校教练车",
    description="不提供车牌，询问车牌信息，提供各种错误车牌，继续询问车牌信息",
    datas=id_88_data,
)


id_89_data = _common_prefix_86 + [
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供错误车牌，含禁用字母I/O",
        "query": "帮我给沪AI2345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_89 = WorkflowDatas(
    name="CASE_89，非法车牌号，IO字母",
    description="不提供车牌，询问车牌信息，提供各种错误车牌，继续询问车牌信息",
    datas=id_89_data,
)

id_90_data = _common_prefix_86 + [
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供错误车牌，含禁用字母I/O",
        "query": "帮我给沪AO2345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_90 = WorkflowDatas(
    name="CASE_90，非法车牌号，IO字母",
    description="不提供车牌，询问车牌信息，提供各种错误车牌，继续询问车牌信息",
    datas=id_90_data,
)

id_91_data = _common_prefix_86 + [
    {
        "comment": "上一步询问车牌信息，这一步提供错误车牌，不合理行政区",
        "query": "帮我给江A12345停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_91 = WorkflowDatas(
    name="CASE_91，非法车牌号，IO字母",
    description="不提供车牌，询问车牌信息，提供各种错误车牌，继续询问车牌信息",
    datas=id_91_data,
)

id_92_data = _common_prefix_86 + [
    {
        "comment": "上一步询问车牌信息，这一步提供错误车牌，临时车牌",
        "query": "帮我给临时车牌粤临 B78901停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_92 = WorkflowDatas(
    name="CASE_92，非法车牌号，临时车牌",
    description="不提供车牌，询问车牌信息，提供各种错误车牌，继续询问车牌信息",
    datas=id_92_data,
)

id_93_data = _common_prefix_86 + [
    {
        "comment": "上一步询问车牌信息，这一步提供错误车牌，使馆车牌非法（前 6 位非全数字）：123A56 使（前 6 位含字母 A，不符合全数字要求）,捷停车中将`使`放在第一位",
        "query": "帮我的使馆车牌123A56使，停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_93 = WorkflowDatas(
    name="CASE_93，非法车牌号，使馆车牌非法（前 6 位非全数字）",
    description="不提供车牌，询问车牌信息，提供各种错误车牌，继续询问车牌信息",
    datas=id_93_data,
)

id_94_data = _common_prefix_86 + [
    {
        "comment": "上一步询问车牌信息，这一步提供错误车牌，领馆车牌非法（非 “省份 + 5 位数字”）：沪 1234 领（仅 4 位数字，缺少 1 位，格式违规）",
        "query": "帮我领馆车牌沪1234领，停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_94 = WorkflowDatas(
    name="CASE_94，非法车牌号，领馆车牌非法（非 “省份 + 5 位数字”）",
    description="不提供车牌，询问车牌信息，提供各种错误车牌，继续询问车牌信息",
    datas=id_94_data,
)


id_95_data =[
    {
        "comment": "浙A4R568，无订单，",
        "query": "帮我缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "无信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "浙A4R568，无订单，",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供错误车牌，境外车牌-台湾",
        "query": "帮我给台湾车牌，台 A・7890停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供错误车牌，境外车牌-韩国",
        "query": "帮我给韩国车牌，31 私車 7890停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供错误车牌，境外车牌-日本",
        "query": "帮我给日本车牌，大阪 203 み 45-6停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供错误车牌，境外车牌-德国",
        "query": "帮我给德国车牌，D-BE 5678停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "上一步询问车牌信息，这一步提供错误车牌，境外车牌-美国",
        "query": "帮我给美国车牌，NY 456 CD停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        "expected_result": "车牌错误，继续询问车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
]

ID_95 = WorkflowDatas(
    name="CASE_95，各种错误车牌的校验-境外车牌",
    description="不提供车牌，询问车牌信息，提供各种境外车牌，继续询问车牌信息",
    datas=id_95_data,
)

id_96_data =[
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌",
        "query": "帮我给京W12222停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "获取车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "车牌不一致，点击切换车辆按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "输入车牌，存在于界面中，可直接快捷点击",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "14_0_快捷点击界面车牌前_京W12222.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "直接点击已有车牌，下一步点击查询缴费",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "14_1_输完车牌查询缴费_京W12222.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_2_输入车牌号码_001.xml"),
        "expected_result": "点击查询缴费按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
]
ID_1_UITARS_INPUT_PLATE = WorkflowDatas(
    name="uitars输车牌",
    description="不提供车牌，询问车牌信息uitars输入车牌",
    datas=id_96_data,
)

id_97_data =[
    {
        "comment": "上一步无车牌，询问车牌信息，这一步提供车牌",
        "query": "帮我给京W12223停车缴费",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "获取车牌信息",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.NL,
    },
    {
        "comment": "车牌不一致，点击切换车辆按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "00_刷新订单_浙A4R568.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "00_刷新订单_浙A4R568.xml"),
        "expected_result": "点击<切换车辆>按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
    {
        "comment": "上一步点击了切换车辆按钮，这一步发现不存在列表中，需点击<其他车辆>按钮",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "01_0_选择其他车辆_鄂A12456.png"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_0_选择其他车辆_鄂A12456.xml"),
        "expected_result": "点击<其他车辆>按钮",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "输入车牌，不存在于界面中，且键盘没弹出",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "14_0_快捷点击界面车牌前_京W12222.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "点击第一个框框，弹出键盘",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "整体目标京W12223，输入第一个省份，京",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "14_2_界面键盘_输省份_京W12222.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "点击车牌对应的省份",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },    
    {
        "comment": "整体目标京W12223，输入字母，W",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "14_3_界面键盘_输W_京W12222.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "省份后的第一个字母，点击,W",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },    
    {
        "comment": "整体目标京W12223，输入第一位数字，1",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "14_4_界面键盘_输第一位数字1_京W12222.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "第一位数字，点击,1",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },    
    {
        "comment": "整体目标京W12223，输入第二位数字2",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "14_5_界面键盘_输第二位数字2_京W12222.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "第二位数字，点击,2",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },    
    {
        "comment": "整体目标京W12223，输入第三位数字2",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "14_6_界面键盘_输第三位数字2_京W12222.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "第三位数字，点击,2",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },    
    {
        "comment": "整体目标京W12223，输入第四位数字2",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "14_7_界面键盘_输第四位数字2京W12222.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "第四位数字，点击,2",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },    
    {
        "comment": "整体目标京W12223，输入最后一位数字3",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "14_8_界面键盘_输第五位数字_京W12222.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_1_输入车牌省份_001.xml"),
        "expected_result": "最后一位数字，点击,3",
        "expect_next_step": ParkingSteps.INPUT_PLATE_PROVINCE,
        "task_type": TaskType.UI,
    },
    {
        "comment": "完成输入",
        "query": "",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "14_9_界面键盘_输入完成_京W12223.jpg"),
        "xml_path": str(DATASET_ROOT /"jie_parking_with_xml" / "xmls" / "01_2_输入车牌号码_001.xml"),
        "expected_result": "点击查询缴费按钮",
        "expect_next_step": ParkingSteps.SELECT_CAR,
        "task_type": TaskType.UI,
    },
]
ID_2_UITARS_INPUT_PLATE = WorkflowDatas(
    name="uitars输车牌，省份，数字等",
    description="不提供车牌，询问车牌信息uitars输入车牌，包含字母数字",
    datas=id_97_data,
)

if __name__ == "__main__":
    from nanoai.utils.async_utils import amap
    import asyncio
    # (P0) 1,19,2，27，25,42，3，6，11，14,32 # 2025年12月3日必须跑通
    # (P1) 5 , 39,28,40,36,37,43,16,44,45,47,48,17,49,50,51,52,20, | 语言 任务 31,82,83  # 2025年12月4日晚上必须跑通
    # (P2) badcase 中其他case
    # 不可复现：case 4 需要默认缓存车牌; case 8 、18需要未登录状态;case 33、34、35拉起服务;case 57 无法复现; case 84 落域问题
    P0 = [ID_1, ID_2, ID_3, ID_6, ID_11, ID_14, ID_19, ID_25, ID_27, ID_32, ID_42]
    P1 = [ID_5, ID_16, ID_17, ID_20, ID_28, ID_36, ID_37, ID_39, ID_40, ID_43, ID_44, ID_45, ID_47, ID_48, ID_49, ID_50, ID_51, ID_52]
    P2 = [ID_7, ID_9, ID_10, ID_15, ID_21, ID_22, ID_23, ID_24, ID_26, ID_29, ID_30, ID_38, ID_41, ID_46, ID_53, ID_54, ID_55, ID_56]
    # 欠费步骤、短时、无需缴费、人工、定位授权的 xml均为mocked
    Test = [ID_1]

    for workflow_case in Test:
        asyncio.run(test_normal_workflow(workflow_case, debug=True))

    # result = asyncio.run(amap(
    #     test_normal_workflow,
    #     P1,
    #     progress=True,
    # ))