import asyncio
import datetime
from pathlib import Path
from typing import Final

import pytest
from rich import print

from openai import AsyncOpenAI
from pydantic import BaseModel

from nanoai.model.config import create_client, ModelName
from nanoai.model.vlm import image_from_path
from projects.uiagent.core.action import ClickAction, FinishedAction
from projects.uiagent.core.flow_data import MiddleInfoType, get_class_id, UIResult, UIStepStatus, _END_STEP
from projects.uiagent.core.uistep import UIStepBase
from projects.uiagent.core.visualize import draw_step_result
from projects.uiagent.jie_parking.data_define import UserMeaning, PlateNumber, KnowingStatus, CheckKnowingStatus, \
    JieParkingReplyContents, PayOrNot, ParkingSteps, ConfirmPayKnowingStatus
from projects.uiagent.jie_parking.jie_uiflow import UIStepSelectCar, PageSelectCarButton, JieFlowState, \
    UIStepInputPlateProvince, UIStepInputPlateLetterNum, UIStepConfirmPay, PageConfirmPayButton, UIStepPayment
from projects.uiagent.jie_parking.new_workflow import JieParkingConfirmPayButtons


async def get_and_draw_action(
        step: UIStepBase,
        image_path: str,
        state=None,
        xml_path: str | None = None,
        middle_info: BaseModel | MiddleInfoType =None,
        output_dir=None,
        test_rpa=True,
):
    if isinstance(middle_info, BaseModel):
        middle_info = {get_class_id(middle_info.__class__): middle_info}
    if xml_path:
        xml = Path(xml_path).read_text(encoding='utf8')
    else:
        xml = None
    client, vlm = create_client(ModelName.DOUBAO_1_5_UI_TARS_250428, AsyncOpenAI)
    # client, vlm = create_client(ModelName.DOUBAO_SEED_1_8_PREVIEW, AsyncOpenAI)
    image, image_format = image_from_path(image_path)
    if not test_rpa:
        step.rpa_handler = None
    result, step, status = await step.arun(
        image,
        image_format,
        xml,
        middle_info,
        state=state,
        model=vlm,
        client=client,
    )
    if output_dir:
        current_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        draw_step_result(
            image_path=image_path,
            query="",
            runresult=[result],
            judge="",
            output_dir=output_dir,
            sample_id=f"{current_time}_test"
        )
    print(f'====image_path====\n: {image_path}\n====result====\n:{result}\n====step====\n:{step}\nstatus:{status}\n')
    return result, step, status


DATASET_ROOT: Final[Path] = Path(".") / "projects" / "uiagent" / "jie_parking" / "datasets" / "jie_parking_with_xml"

test_rpa = True

@pytest.mark.asyncio
async def test_ui_step_select_car_1():
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "新增车牌.png"),
        state=None,
        xml_path=str(DATASET_ROOT  / "xmls" / "新增车牌.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=PlateNumber(plate_number="沪A123456"),
            fee_correct_or_not=KnowingStatus.UNKNOWN,
            fee_check_or_not=CheckKnowingStatus.UNKNOWN
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert result.actions[0].target_ui_element == PageSelectCarButton.INPUT_PLATE_PAY.value


@pytest.mark.asyncio
async def test_ui_step_select_car_2():
    #　测试缺车牌号
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "新增车牌.png"),
        state=None,
        xml_path=str(DATASET_ROOT  / "xmls" / "新增车牌.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=None,
            fee_correct_or_not=KnowingStatus.UNKNOWN,
            fee_check_or_not=CheckKnowingStatus.UNKNOWN
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    if test_rpa:
        assert result.actions[0].content == JieParkingReplyContents.NEED_PLATE_NUMBER
    else:
        assert result.actions[0].target_ui_element == PageSelectCarButton.INPUT_PLATE_PAY.value or result == JieParkingReplyContents.NEED_PLATE_NUMBER


@pytest.mark.asyncio
async def test_ui_step_select_car_3():
    #　测试车牌号错误
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "新增车牌.png"),
        state=None,
        xml_path=str(DATASET_ROOT  / "xmls" / "新增车牌.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=PlateNumber(plate_number="沪A12"),
            fee_correct_or_not=KnowingStatus.UNKNOWN,
            fee_check_or_not=CheckKnowingStatus.UNKNOWN
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert (result.actions[0].content if isinstance(result, UIResult) else result) == JieParkingReplyContents.ASK_ILLEGAL_PLATE_NUMBER


@pytest.mark.asyncio
async def test_ui_step_select_car_4():
    #　车牌不同时，有其他车辆选择其他车辆
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "选择其他车辆_001.png"),
        state=None,
        xml_path=str(DATASET_ROOT  / "xmls" / "选择其他车辆_001.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=PlateNumber(plate_number="皖AF25588"),
            fee_correct_or_not=KnowingStatus.UNKNOWN,
            fee_check_or_not=CheckKnowingStatus.UNKNOWN
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert result.actions[0].target_ui_element == PageSelectCarButton.OTHER_CARS.value


@pytest.mark.asyncio
async def test_ui_step_select_car_5():
    #　车牌相同时，且确认缴费，则点击查看按钮
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "查看金额_001.png"),
        state=None,
        xml_path=str(DATASET_ROOT  / "xmls" / "查看金额_001.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=PlateNumber(plate_number="鄂A12456"),
            fee_correct_or_not=KnowingStatus.UNKNOWN,
            fee_check_or_not=CheckKnowingStatus.YES
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert result.actions[0].target_ui_element == PageSelectCarButton.VIEW_AMOUNT.value


@pytest.mark.asyncio
async def test_ui_step_select_car_6():
    #　车牌不相同时，且确认缴费，则点击切换车辆
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "查看金额_001.png"),
        state=None,
        xml_path=str(DATASET_ROOT  / "xmls" / "查看金额_001.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=PlateNumber(plate_number="皖A12456"),
            fee_correct_or_not=KnowingStatus.UNKNOWN,
            fee_check_or_not=CheckKnowingStatus.YES
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    # TODO UI NAME 提取的不准，需要有校验环节？ # Button(name='鄂A12456', description='鄂A12456') != Button(name='切换车辆', description='是页面左上角的车牌号，是一个可以点击的按钮也就是该按钮，用来唤起切换或添加车辆车牌号')
    assert result.actions[0].target_ui_element == PageSelectCarButton.SWITCH_CAR.value


@pytest.mark.asyncio
async def test_ui_step_select_car_7():
    #　车牌相同时，未确认缴费，则询问
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "查看金额_001.png"),
        state=None,
        xml_path=str(DATASET_ROOT  / "xmls" / "查看金额_001.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=PlateNumber(plate_number="鄂A12456"),
            fee_correct_or_not=KnowingStatus.UNKNOWN,
            fee_check_or_not=CheckKnowingStatus.UNKNOWN
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert JieParkingReplyContents.ASK_CHECK_BIG_FEE_OR_NOT in result.actions[0].content


@pytest.mark.asyncio
async def test_ui_step_select_car_8():
    #　车牌相同时，查看费用明细
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "02_小额订单_查看费用明细_沪A12345.png"),
        state=None,
        xml_path=str(DATASET_ROOT  / "xmls" / "02_小额订单_查看费用明细_沪A12345.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=PlateNumber(plate_number="沪A12345"),
            fee_correct_or_not=KnowingStatus.UNKNOWN,
            fee_check_or_not=CheckKnowingStatus.YES
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert result.actions[0].target_ui_element == PageSelectCarButton.VIEW_FEE_DETAILS.value


@pytest.mark.asyncio
async def test_ui_step_select_car_9():
    #　未刷新时， 刷新一次按钮
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "00_刷新订单_浙A4R568.png"),
        state=JieFlowState(clicked_refresh_order=False, task='', step=''),
        xml_path=str(DATASET_ROOT  / "xmls" / "00_刷新订单_浙A4R568.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=PlateNumber(plate_number="浙A4R568"),
            fee_correct_or_not=KnowingStatus.UNKNOWN,
            fee_check_or_not=CheckKnowingStatus.UNKNOWN
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert result.actions[0].target_ui_element == PageSelectCarButton.REFRESH_ORDER.value


@pytest.mark.asyncio
async def test_ui_step_select_car_10():
    #　刷新过时， 询问是否更换车牌等
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "00_刷新订单_浙A4R568.png"),
        state=JieFlowState(clicked_refresh_order=True, task='', step=''),
        xml_path=str(DATASET_ROOT  / "xmls" / "00_刷新订单_浙A4R568.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=PlateNumber(plate_number="浙A4R568"),
            fee_correct_or_not=KnowingStatus.UNKNOWN,
            fee_check_or_not=CheckKnowingStatus.UNKNOWN
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert result.actions[0].content == JieParkingReplyContents.ASK_NO_ORDER
    # TODO 提取button不准，多了书名号
    # ClickAction(x=0.498, y=0.303, target_ui_element=Button(name='《刷新订单》', description='《刷新订单》'))


@pytest.mark.asyncio
async def test_ui_step_select_car_11():
    #　短时无需缴费
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "03_查看金额_短时无需缴费_鄂A123456.jpg"),
        state=JieFlowState(clicked_refresh_order=True, task='', step=''),
        xml_path=str(DATASET_ROOT  / "xmls" / "03_查看金额_短时无需缴费_鄂A123456.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=PlateNumber(plate_number="鄂A123456"),
            fee_correct_or_not=KnowingStatus.UNKNOWN,
            fee_check_or_not=CheckKnowingStatus.UNKNOWN
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert JieParkingReplyContents.FINISHED_NO_NEED_TO_PAY in result.actions[0].content


@pytest.mark.asyncio
async def test_ui_step_select_car_12():
    #　人工通道
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "04_查看金额_人工_苏A12345.jpg"),
        state=JieFlowState(clicked_refresh_order=True, task='', step=''),
        xml_path=str(DATASET_ROOT  / "xmls" / "04_查看金额_人工_苏A12345.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=PlateNumber(plate_number="苏A12345"),
            fee_correct_or_not=KnowingStatus.UNKNOWN,
            fee_check_or_not=CheckKnowingStatus.UNKNOWN
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert JieParkingReplyContents.FINISHED_MANUALY_REPLY in result.actions[0].content


@pytest.mark.asyncio
async def test_ui_step_select_car_13():
    #　月卡
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "05_查看金额_月卡_沪AAJ0635.jpg"),
        state=JieFlowState(clicked_refresh_order=True, task='', step=''),
        xml_path=str(DATASET_ROOT  / "xmls" / "05_查看金额_月卡_沪AAJ0635.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=PlateNumber(plate_number="沪AAJ0635"),
            fee_correct_or_not=KnowingStatus.UNKNOWN,
            fee_check_or_not=CheckKnowingStatus.UNKNOWN
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert JieParkingReplyContents.FINISHED_MONTHLY_PASS in result.actions[0].content


@pytest.mark.asyncio
async def test_ui_step_select_car_14():
    #　大额弹窗去缴费
    result, step, status = await get_and_draw_action(
        step=UIStepSelectCar(),
        image_path=str(DATASET_ROOT / "images" / "07_大额确认页_鄂A12456.png"),
        state=JieFlowState(clicked_refresh_order=True, task='', step=''),
        xml_path=str(DATASET_ROOT  / "xmls" / "07_大额确认页_鄂A12456.xml"),
        output_dir='.',
        middle_info=UserMeaning(
            plate_number=PlateNumber(plate_number="鄂A12456"),
            fee_correct_or_not=KnowingStatus.YES,
            fee_check_or_not=CheckKnowingStatus.YES
        ),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert result.actions[0].target_ui_element == PageSelectCarButton.PAY_FEE.value


@pytest.mark.asyncio
async def test_ui_step_input_province():
    #　输入车牌省份-有键盘 纯rpa todo 无车盘需唤起的测试case缺失
    test_rpa = True
    result, step, status = await get_and_draw_action(
        step=UIStepInputPlateProvince(),
        image_path=str(DATASET_ROOT / "images" / "01_1_输入车牌省份_001.png"),
        state=JieFlowState(clicked_refresh_order=True, task='', step=''),
        xml_path=str(DATASET_ROOT  / "xmls" / "01_1_输入车牌省份_001.xml"),
        output_dir='.',
        middle_info=PlateNumber(plate_number="鄂A12456"),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    action = result.actions[0]
    assert isinstance(action, ClickAction) and 0.78 <=action.x <= 0.80 and 0.69 <= action.y <= 0.71


@pytest.mark.asyncio
async def test_ui_step_input_letter_num():
    #　输入车牌字母数字部分-有键盘
    test_rpa = True
    result, step, status = await get_and_draw_action(
        step=UIStepInputPlateLetterNum(),
        image_path=str(DATASET_ROOT / "images" / "01_3_输入车牌号码_001鄂.png"),
        state=JieFlowState(clicked_refresh_order=True, task='', step=''),
        xml_path=str(DATASET_ROOT  / "xmls" / "01_3_输入车牌号码_001鄂.xml"),
        output_dir='.',
        middle_info=PlateNumber(plate_number="鄂A12456"),
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert len(result.actions) == 8


@pytest.mark.asyncio
async def test_ui_step_confirmpay_1():
    #　去支付
    result, step, status = await get_and_draw_action(
        step=UIStepConfirmPay(),
        image_path=str(DATASET_ROOT / "images" / "确认订单坐标正确.png"),
        state=JieFlowState(clicked_refresh_order=True, task='', step=''),
        xml_path=str(DATASET_ROOT  / "xmls" / "确认订单坐标正确.xml"),
        output_dir='.',
        middle_info=PayOrNot(
            pay_or_not=ConfirmPayKnowingStatus.YES
        ),
        test_rpa=test_rpa,
    )
    # ParkingSteps.CONFIRM_PAY, UIStepStatus.WAIT_FOR_IMAGE
    print(f'result: {result}')
    assert result.actions[0].target_ui_element == PageConfirmPayButton.CONFIRM_FEE.value and step == ParkingSteps.CONFIRM_PAY and status == UIStepStatus.WAIT_FOR_IMAGE


@pytest.mark.asyncio
async def test_ui_step_confirmpay_2():
    #　去支付
    result, step, status = await get_and_draw_action(
        step=UIStepConfirmPay(),
        image_path=str(DATASET_ROOT / "images" / "08_确认订单_广告_001.png"),
        state=JieFlowState(clicked_refresh_order=True, task='', step=''),
        xml_path=str(DATASET_ROOT  / "xmls" / "08_确认订单_广告_001.xml"),
        output_dir='.',
        middle_info=PayOrNot(
            pay_or_not=ConfirmPayKnowingStatus.YES
        ),
        test_rpa=test_rpa,
    )
    # ParkingSteps.CONFIRM_PAY, UIStepStatus.WAIT_FOR_IMAGE
    print(f'result: {result}')
    assert result.actions[0].target_ui_element == PageConfirmPayButton.CANCEL_AD.value and step == ParkingSteps.CONFIRM_PAY and status == UIStepStatus.WAIT_FOR_IMAGE


@pytest.mark.asyncio
async def test_ui_step_confirmpay_3():
    #　去支付
    result, step, status = await get_and_draw_action(
        step=UIStepConfirmPay(),
        image_path=str(DATASET_ROOT / "images" / "10_去支付_001.png"),
        state=JieFlowState(clicked_refresh_order=True, task='', step=''),
        xml_path=str(DATASET_ROOT  / "xmls" / "10_去支付_001.xml"),
        output_dir='.',
        middle_info=PayOrNot(
            pay_or_not=ConfirmPayKnowingStatus.YES
        ),
        test_rpa=test_rpa,
    )
    # ParkingSteps.CONFIRM_PAY, UIStepStatus.WAIT_FOR_IMAGE
    print(f'result: {result}')
    assert (
                (
                        result.actions[0].target_ui_element == PageConfirmPayButton.GO_TO_PAY.value
                    or JieParkingConfirmPayButtons.GO_TO_PAY.value in result.actions[0].target_ui_element.name
                )
            and step == ParkingSteps.PAYMENT
            and status == UIStepStatus.WAIT_FOR_IMAGE
    )


@pytest.mark.asyncio
async def test_ui_step_payment_1():
    #　去支付
    result, step, status = await get_and_draw_action(
        step=UIStepPayment(),
        image_path=str(DATASET_ROOT / "images" / "11_去支付_方式选择_002.png"),
        state=JieFlowState(clicked_refresh_order=True, task='', step=''),
        xml_path=str(DATASET_ROOT  / "xmls" / "11_去支付_方式选择_002.xml"),
        middle_info={},
        output_dir='.',
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert isinstance(result.actions[0], ClickAction) and step == ParkingSteps.PAYMENT and status == UIStepStatus.WAIT_FOR_IMAGE


@pytest.mark.asyncio
async def test_ui_step_payment_2():
    #　去支付
    result, step, status = await get_and_draw_action(
        step=UIStepPayment(),
        image_path=str(DATASET_ROOT / "images" / "12_去支付_二维码_004.png"),
        state=JieFlowState(clicked_refresh_order=True, task='', step=''),
        xml_path=str(DATASET_ROOT  / "xmls" / "12_去支付_二维码_004.xml"),
        middle_info={},
        output_dir='.',
        test_rpa=test_rpa,
    )
    print(f'result: {result}')
    assert isinstance(result.actions[0], FinishedAction) and step == _END_STEP and status == UIStepStatus.IDLE

