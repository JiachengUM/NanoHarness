from projects.uiagent.jie_parking.workflow_eval import test_jie_parking_step_batch
from projects.uiagent.jie_parking.datasets import DATASET_ROOT
import asyncio

BAD_CASES = [
    {
        "comment": "1_rpa_case_01 测试数据校验，query不提供信息。",
        "query": "",
        "image_path": str(DATASET_ROOT / "bad_case_with_xml" / "images" / "65a2f609-c5a0-4358-94b8-da1b52dd493f.png"),
        "xml_path": str(DATASET_ROOT / "bad_case_with_xml" / "xmls" / "65a2f609-c5a0-4358-94b8-da1b52dd493f.xml"),
        "step": 0,
        "state_params_info": "湘ADU5667",
        "expected_result": "需要提供车牌信息",
        "type": "ui",
    },
    {
        "comment": "2_rpa_case_02 测试数据校验，query提供信息，但车牌信息与页面不符。",
        "query": "鄂A123456",
        "image_path": str(DATASET_ROOT / "bad_case_with_xml" / "images" / "65a2f609-c5a0-4358-94b8-da1b52dd493f.png"),
        "xml_path": str(DATASET_ROOT / "bad_case_with_xml" / "xmls" / "65a2f609-c5a0-4358-94b8-da1b52dd493f.xml"),
        "step": 0,
        "state_params_info": "湘ADU5667",
        "expected_result": "点左上角的车牌处尝试切换车牌",
        "type": "ui",
    },
    {
        "comment": "3_rpa_case_03 query提供信息，且车牌信息与页面相符，但是页面没有费用信息。",
        "query": "湘ADU5667",
        "image_path": str(DATASET_ROOT / "bad_case_with_xml" / "images" / "65a2f609-c5a0-4358-94b8-da1b52dd493f.png"),
        "xml_path": str(DATASET_ROOT / "bad_case_with_xml" / "xmls" / "无刷新订单_抛错.xml"),
        "step": 0,
        "state_params_info": "湘ADU5667",
        "expected_result": "无查看费用按钮, 直接抛错！",
        "type": "ui",
    },
    {
        "comment": "4_rpa_case_04 query提供信息，且车牌信息与页面相符，但是页面有费用信息，预期输出查看费用。",
        "query": "沪AB91710",
        "image_path": str(DATASET_ROOT /"dataset" / "images" / "车牌订单查询结果_21.png"),
        "xml_path": str(DATASET_ROOT / "bad_case_with_xml" / "xmls" / "65a2f609-c5a0-4358-94b8-da1b52dd493f.xml"),
        "step": 0,
        "state_params_info": "沪AB91710",
        "expected_result": "查看费用！",
        "type": "ui",
    },
    {
        "comment": "5_rpa_case_05 query提供信息，且车牌信息与页面不相符，需要去换车牌。",
        "query": "沪AB91710",
        "image_path": str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "选择其他车辆_001.png"),
        "xml_path": str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "选择其他车辆_001.xml"),
        "step": 0,
        "state_params_info": "沪AB91710",
        "expected_result": "车牌不一致，选择其他车辆。",
        "type": "ui",
    },
    {
        "comment": "6_rpa_case_06 选择其他车辆后，输入省份。当前xml 未加载完毕，无京津沪渝，卡在校验环节",
        "query": "沪AB91710",
        "image_path": str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "输入车牌省份_001.png"),
        "xml_path": str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "输入车牌省份_001.xml"),
        "step": 1,
        "state_params_info": "沪AB91710",
        "expected_result": "ui data is invalid: 键盘信息未加载完毕",
        "type": "ui",
    },
    {
        "comment": "7_rpa_case_07 测试数据校验，query提供部分车牌信息",
        "query": "鄂A1236",
        "image_path": str(DATASET_ROOT / "bad_case_with_xml" / "images" / "65a2f609-c5a0-4358-94b8-da1b52dd493f.png"),
        "xml_path": str(DATASET_ROOT / "bad_case_with_xml" / "xmls" / "65a2f609-c5a0-4358-94b8-da1b52dd493f.xml"),
        "step": 0,
        "state_params_info": "湘ADU5667",
        "expected_result": "点左上角的车牌处尝试切换车牌",
        "type": "ui",
    },
    {
        "comment": "8_rpa_case_08 query提供信息，xml中无月卡，卡在校验环节",
        "query": "沪AB91710",
        "image_path": str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "选择其他车辆_001.png"),
        "xml_path": str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "无月卡字样_卡校验.xml"),
        "step": 0,
        "state_params_info": "沪AB91710",
        "expected_result": "ui data is invalid: 当前页面无'月卡'字样，表明未加载完毕，需等待加载",
        "type": "ui",
    },
    {
        "comment": "9_rpa_case_09 query提供信息，且车牌信息与页面相符，但是页面没有其他匹配信息。",
        "query": "湘ADU5667",
        "image_path": str(DATASET_ROOT / "bad_case_with_xml" / "images" / "65a2f609-c5a0-4358-94b8-da1b52dd493f.png"),
        "xml_path": str(DATASET_ROOT / "bad_case_with_xml" / "xmls" / "65a2f609-c5a0-4358-94b8-da1b52dd493f.xml"),
        "step": 0,
        "state_params_info": "湘ADU5667",
        "expected_result": "self.state.status = WorkflowStatus.SUCCESS,边缘情形，返回[]",
        "type": "ui",
    },
    # 待测试
    {
        "comment": "10_rpa_case_10 query提供信息，新增车牌",
        "query": "鄂A123456",
        "image_path": str(DATASET_ROOT / "bad_case_with_xml" / "images" / "新增车牌.png"),
        "xml_path": str(DATASET_ROOT / "bad_case_with_xml" / "xmls" / "新增车牌.xml"),
        "step": 0,
        "state_params_info": "鄂A123456",
        "expected_result": "首页点击新增车牌，下一步输入车牌省份",
        "type": "ui",
    },
    {
        "comment": "11_rpa_case_11 query提供信息，且车牌信息与页面相符，但是页面有费用信息，预期输出查看金额。",
        "query": "鄂A12456",
        "image_path": str(DATASET_ROOT /"jie_parking_with_xml" / "images" / "查看金额_001.png"),
        "xml_path": str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "查看金额_001.xml"),
        "step": 0,
        "state_params_info": "鄂A12456",
        "expected_result": "查看金额！下一步确认费用。",
        "type": "ui",
    },

    {
        "comment": "12_rpa_case_12 确认订单_广告_001 用户确认订单",
        "query": "",
        "image_path": str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "确认订单_广告_001.png"),
        "xml_path": str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "确认订单_广告_001.xml"),
        "step": 5,
        "state_params_info": "鄂A123456",
        "expected_result": "确认订单",
        "type": "ui",
    },
    {
        "comment": "13_rpa_case_13 去支付_001 用户确认支付",
        "query": "",
        "image_path": str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "去支付_001.png"),
        "xml_path": str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "去支付_001.xml"),
        "step": 6,
        "state_params_info": "鄂A123456",
        "expected_result": "询问用户是否确认支付",
        "type": "ui",
    },
    {
        "comment": "14_rpa_case_14 去支付_方式选择_002 支付方式选择",
        "query": "",
        "image_path": str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "去支付_方式选择_002.png"),
        "xml_path": str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "去支付_方式选择_002.xml"),
        "step": 4,
        "state_params_info": "鄂A123456",
        "expected_result": "点击二维码支付方式，下一步支付",
        "type": "ui",
    },
    {
        "comment": "15_rpa_case_15 去支付_二维码_004 支付二维码",
        "query": "",
        "image_path": str(DATASET_ROOT / "jie_parking_with_xml" / "images" / "去支付_二维码_004.png"),
        "xml_path": str(DATASET_ROOT / "jie_parking_with_xml" / "xmls" / "去支付_二维码_004.xml"),
        "step": 4,
        "state_params_info": "鄂A123456",
        "expected_result": "显示支付二维码，Finished",
        "type": "ui",
    },
]


def main():

    cases = BAD_CASES[:]
    asyncio.run(test_jie_parking_step_batch(cases))
    return


if __name__ == "__main__":
    main()

