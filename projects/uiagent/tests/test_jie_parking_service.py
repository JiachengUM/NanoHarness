import uuid

import requests

from nanoai.model.vlm import image_from_path
from nanoai.utils.nl_repr import nl_repr
from projects.uiagent.jie_parking.datasets import DATASET_ROOT

# START_REQUEST_URL = "http://127.0.0.1:9001/api/start"
# NL_ONLY_REQUEST_URL = "http://127.0.0.1:9001/api/gui_nl_only"
# IMAGE_ONLY_REQUEST_URL = "http://127.0.0.1:9001/api/gui_image_only"

START_REQUEST_URL = "http://127.0.0.1:9001/api/start_test"
NL_ONLY_REQUEST_URL = "http://127.0.0.1:9001/api/gui_nl_only_test"
IMAGE_ONLY_REQUEST_URL = "http://127.0.0.1:9001/api/gui_image_only_test"
# 公网地址，慢
# START_REQUEST_URL = "http://120.26.237.96/volc-llm-nanoai-agent-dev/api/start"
# NL_ONLY_REQUEST_URL = "http://120.26.237.96/volc-llm-nanoai-agent-dev/api/gui_nl_only"
# IMAGE_ONLY_REQUEST_URL = "http://120.26.237.96/volc-llm-nanoai-agent-dev/api/gui_image_only"
# 内网地址，快一点volc-llm-nanoai-agent-dev-svc-vm4jf:9001
# START_REQUEST_URL = "http://volc-llm-nanoai-agent-dev-svc-vm4jf:9001/api/start"
# NL_ONLY_REQUEST_URL = "http://volc-llm-nanoai-agent-dev-svc-vm4jf:9001/api/gui_nl_only"
# IMAGE_ONLY_REQUEST_URL = "http://volc-llm-nanoai-agent-dev-svc-vm4jf:9001/api/gui_image_only"


def generate_32_uuid():
    return str(uuid.uuid4()).replace("-", "")


def build_start_payload(
    query: str,
    image_base64: str,
    image_format: str,
    xml: str,
    chat_id: str,
    default_user_plate: str,
):
    return {
        "query": query,
        "image_base64": image_base64,
        "image_format": image_format,
        "xml": xml,
        "default_user_plate": default_user_plate,
        "chat_id": chat_id,
    }


def build_nl_only_payload(query: str, chat_id: str):
    return {"query": query, "chat_id": chat_id}


def build_image_only_payload(image_base64: str, image_format: str, xml: str, chat_id: str):
    return {
        "image_base64": image_base64,
        "image_format": image_format,
        "xml": xml,
        "chat_id": chat_id,
    }


def call_jie_parking_agent_start(
    query: str, image_path: str, chat_id: str, xml: str, default_user_plate: str
):
    """
    调用捷停车智能体start接口
    """
    image_base64, image_format = image_from_path(image_path)
    payload = build_start_payload(
        query=query,
        image_base64=image_base64,
        image_format=image_format,
        xml=xml,
        chat_id=chat_id,
        default_user_plate=default_user_plate,
    )
    # 发送POST请求
    response = requests.post(
        START_REQUEST_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    return response


def call_jie_parking_agent_nl_only(query: str, chat_id: str):
    """
    调用捷停车智能体nl_only接口
    """
    payload = build_nl_only_payload(query=query, chat_id=chat_id)
    # 发送POST请求
    response = requests.post(
        NL_ONLY_REQUEST_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    return response


def call_jie_parking_agent_image_only(image_path: str, chat_id: str, xml: str):
    """
    调用捷停车智能体image_only接口
    """
    image_base64, image_format = image_from_path(image_path)
    payload = build_image_only_payload(
        image_base64=image_base64, image_format=image_format, xml=xml, chat_id=chat_id
    )
    # 发送POST请求
    response = requests.post(
        IMAGE_ONLY_REQUEST_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    return response


def jie_parking_agent1():
    """
    测试场景一：从无订单首页start接口开始->询问是否缴费其他车辆gui_nl_only接口->点击首页车牌gui_image_only接口
    """
    chat_id = generate_32_uuid()
    default_user_plate = "粤C58921"
    xml = """
    <root>
        <user_plate>鄂A12456</user_plate>
    </root>
    """
    image_path = str(DATASET_ROOT / "jie_parking" / "images" / "订单查询_001.jpg")
    # 测试场景一：从无订单首页->询问是否缴费其他车辆->点击首页车牌
    original_query = "帮我缴费"
    result = call_jie_parking_agent_start(
        original_query, image_path, chat_id, xml, default_user_plate
    )
    print(result.json())
    print("+" * 50)
    assert isinstance(result.json()["datas"]["answer"], str)
    print(
        "测试START接口选择车辆因为用户默认车牌无订单，成功反问用户是否给其他车辆缴费: "
        + result.json()["datas"]["answer"]
    )
    print("agent_res:" + nl_repr(result.json()))
    print("=" * 50)

    new_query = "那给鄂A12456缴费吧"
    result = call_jie_parking_agent_nl_only(new_query, chat_id)
    print(result.json())
    print("+" * 50)
    assert result.json()["datas"]["actions"][0]["name"] == "click"
    print("成功运行预期click动作的case成功")
    print("agent_res:" + nl_repr(result.json()))
    print("=" * 50)

    """上一步点击了左上角车牌处，这一步尝试观察是否有其他车辆按钮可点击"""
    """测试gui_image_only接口"""
    image_path = str(DATASET_ROOT / "jie_parking" / "images" / "选择其他车辆_010.jpg")
    result = call_jie_parking_agent_image_only(image_path, chat_id, xml)
    print(result.json())
    print("+" * 50)
    assert result.json()["datas"]["actions"][0]["name"] == "click"
    print("测试其他车辆按钮点击预期click的case成功")
    print("agent_res:" + nl_repr(result.json()))
    print("=" * 50)

    """上一步点击了其他车辆处，这一步尝试RPA输入省份"""
    """测试gui_image_only接口"""
    image_path = str(DATASET_ROOT / "jie_parking" / "images" / "车牌输入省份键盘.png")
    xml_file = str(DATASET_ROOT / "jie_parking" / "xmls" / "window_dump_1.xml")
    with open(xml_file, "r", encoding="utf-8") as f:
        xml = f.read()
    result = call_jie_parking_agent_image_only(image_path, chat_id, xml)
    print(result.json())
    print("+" * 50)
    assert result.json()["datas"]["actions"][0]["name"] == "click"
    print("测试RPA输入省份运行预期click的case成功")
    print("agent_res:" + nl_repr(result.json()))
    print("=" * 50)

    """上一步RPA输入省份，这一步尝试RPA输入号码部分"""
    """测试gui_image_only接口"""
    image_path = str(DATASET_ROOT / "jie_parking" / "images" / "输入车牌_001.jpg")
    xml_file = str(DATASET_ROOT / "jie_parking" / "xmls" / "window_dump_2.xml")
    with open(xml_file, "r", encoding="utf-8") as f:
        xml = f.read()
    result = call_jie_parking_agent_image_only(image_path, chat_id, xml)
    print(result.json())
    print("+" * 50)
    assert result.json()["datas"]["actions"][0]["name"] == "click"
    print("测试RPA输入号码部分click的case成功")
    print("agent_res:" + nl_repr(result.json()))
    print("=" * 50)

    """上一步RPA输入号码部分，这一步应该回到选择车辆页面了并点击查看订单明细"""
    """测试gui_image_only接口"""
    image_path = str(DATASET_ROOT / "jie_parking" / "images" / "订单查询_008.jpg")

    result = call_jie_parking_agent_image_only(image_path, chat_id, xml)
    print(result.json())
    print("+" * 50)
    assert result.json()["datas"]["actions"][0]["name"] == "click"
    print("测试点击查看订单明细预期click的case成功")
    print("agent_res:" + nl_repr(result.json()))
    print("=" * 50)
    exit()
    """上一步看到了订单明细，这一步应该问用户确认金额是否正确"""
    """测试gui_image_only接口"""
    image_path = str(DATASET_ROOT / "jie_parking" / "images" / "订单缴费_008.jpg")
    result = call_jie_parking_agent_image_only(image_path, chat_id, xml)
    print(result.json())
    print("+" * 50)
    assert isinstance(result.json()["datas"]["answer"], str)
    print("测试在订单详情界面，成功反问用户确认金额是否正确: " + result.json()["datas"]["answer"])
    print("agent_res:" + nl_repr(result.json()))
    print("=" * 50)
    # print(call_jie_parking_agent("鄂A12456", str(DATASET_ROOT / "jie_parking" / "images" / "缴费流程_14.png"), chat_id, "任务执行中", "鄂A12456"))


def jie_parking_agent2():
    """
    测试场景二：主要验证从一个有车牌但无缴费信息首页->绑车牌(后续流程同上未重复验证)
    结论(251110):pass;返回询问用户是否需要更换其他车牌，然后一步步点击至绑车牌页面
    """
    chat_id = generate_32_uuid()
    # print(call_jie_parking_agent("帮我缴一下停车费", str(DATASET_ROOT / "jie_parking" / "images" / "缴费流程2_1.png"), chat_id, "任务执行中", "鄂A12456"))
    # print(call_jie_parking_agent("帮我换成鄂A12456", str(DATASET_ROOT / "jie_parking" / "images" / "缴费流程2_1.png"), chat_id, "任务执行中", "鄂A12456"))
    # print(call_jie_parking_agent("帮我换成鄂A12456", str(DATASET_ROOT / "jie_parking" / "images" / "缴费流程2_2.png"), chat_id, "任务执行中", "鄂A12456"))
    print(
        call_jie_parking_agent(
            "帮我换成鄂A12456",
            str(DATASET_ROOT / "jie_parking" / "images" / "缴费流程2_3.png"),
            chat_id,
            "任务执行中",
            "鄂A12456",
        )
    )


def jie_parking_agent3():
    """
    测试场景二：首页有车牌，但当前车辆处于免费时段
    结论(251110):pass;返回finished
    """
    chat_id = generate_32_uuid()
    print(
        call_jie_parking_agent(
            "帮我缴一下停车费",
            str(DATASET_ROOT / "jie_parking" / "images" / "缴费流程3_1.png"),
            chat_id,
            "任务执行中",
            "鄂A12456",
        )
    )


def jie_parking_agent4():
    """
    测试场景二：首页有车牌，但当前车辆为月卡用户
    结论(251110):pass;返回finished
    """
    chat_id = generate_32_uuid()
    print(
        call_jie_parking_agent(
            "帮我缴一下停车费",
            str(DATASET_ROOT / "jie_parking" / "images" / "缴费流程4_1.png"),
            chat_id,
            "任务执行中",
            "鄂A12456",
        )
    )


if __name__ == "__main__":
    jie_parking_agent1()
