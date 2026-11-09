from datetime import datetime
from pathlib import Path
from typing import Final

import pytest
from pydantic import BaseModel
from openai import AsyncOpenAI

from projects.uiagent.core.action import ClickAction, InputBox, Button, WaitAction
from projects.uiagent.core.flow_data import MiddleInfoType, get_class_id, EUIAction
from projects.uiagent.core.uistep import UIStepBase
from nanoai.model.config import create_client, ModelName
from nanoai.model.vlm import image_from_path
from projects.uiagent.core.visualize import draw_step_result
from projects.uiagent.movie_ticket_booking.workflow import SearchMovieInfo, UIStepSelectMovie, \
    MovieTicketBookingUIFlowState, MovieTicketBookingStep, PageSelectMovieButton, PageSelectMovieButtonNames, \
    UIStepSelectMovieTheatreAndTime, SelectTheatreAndTimeInfo, UIStepSelectSeat, SelectSeatInfo, UIStepConfirmOrder, \
    ConfirmOrderInfo, ConfirmPayKnowingStatus, UIStepPayment


async def get_and_draw_action(
        step: UIStepBase,
        image_path: str,
        state=None,
        middle_info: BaseModel | MiddleInfoType =None,
        output_dir=None,
):
    if isinstance(middle_info, BaseModel):
        middle_info = {get_class_id(middle_info.__class__): middle_info}

    client, vlm = create_client(ModelName.DOUBAO_1_5_UI_TARS_250428, AsyncOpenAI)
    # client, vlm = create_client(ModelName.DOUBAO_SEED_1_8_PREVIEW, AsyncOpenAI)
    image, image_format = image_from_path(image_path)

    result, step, status = await step.arun(
        image,
        image_format,
        None,
        middle_info,
        state=state,
        model=vlm,
        client=client,
    )
    if output_dir:
        current_time = datetime.now().strftime("%Y%m%d%H%M%S")
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


# DATASET_ROOT: Final[Path] = Path(".") / "projects" / "uiagent" / "movie_ticket_booking" / "datasets" / "movie_ticket_booking"
DATASET_ROOT: Final[Path] = Path(".") / "datasets" / "movie_ticket_booking"

@pytest.mark.asyncio
async def test_ui_step_select_movie_1():
    """
    首页热门电影有，直接点击热门电影列表中的购票按钮
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovie(),
        image_path=str(DATASET_ROOT / "images" / "首页_001.jpg"),
        state=state,
        output_dir='.',
        middle_info=SearchMovieInfo(
            name="阿凡达3",
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]
    assert action.target_ui_element.name == PageSelectMovieButtonNames.BUY_TICKET

@pytest.mark.asyncio
async def test_ui_step_select_movie_2():
    """
    首页热门电影没有，点击搜索框
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovie(),
        image_path=str(DATASET_ROOT / "images" / "首页_001.jpg"),
        state=state,
        output_dir='.',
        middle_info=SearchMovieInfo(
            name="鹿鼎记",
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]
    assert isinstance(action, ClickAction)

@pytest.mark.asyncio
async def test_ui_step_select_movie_3():
    """
    影片搜索页  预期是先点击搜索框
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovie(),
        image_path=str(DATASET_ROOT / "images" / "影片搜索_002.png"),
        state=state,
        output_dir='.',
        middle_info=SearchMovieInfo(
            name="海贼王",
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]
    # assert isinstance(action, ClickAction)

@pytest.mark.asyncio
async def test_ui_step_select_movie_3_1():
    """
    影片搜索页  预期是先点击搜索框
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        actions_record=[
            ClickAction(name='click', x=0.334, y=0.045,target_ui_element=InputBox(name='首页电影搜索输入栏', description='首页电影搜索输入栏', max_length=50)),
            ClickAction(name='click', x=0.334, y=0.045,
                        target_ui_element=Button(name='电影搜索输入栏', description='电影搜索输入栏'))
        ]
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovie(),
        image_path=str(DATASET_ROOT / "images" / "影片搜索_002.png"),
        state=state,
        output_dir='.',
        middle_info=SearchMovieInfo(
            name="海贼王",
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]
    # assert isinstance(action, ClickAction)

@pytest.mark.asyncio
async def test_ui_step_select_movie_4():
    """
    影片搜索结果点击 购票按钮
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovie(),
        image_path=str(DATASET_ROOT / "images" / "影片搜索结果_001.jpg"),
        state=state,
        output_dir='.',
        middle_info=SearchMovieInfo(
            name="阿凡达3",
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]
    # assert isinstance(action, ClickAction)

@pytest.mark.asyncio
async def test_ui_step_select_movie_theatre_and_time_1():
    """
    点击搜索影院按钮
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovieTheatreAndTime(),
        image_path=str(DATASET_ROOT / "images" / "影片确认结果_001.jpg"),
        state=state,
        output_dir='.',
        middle_info=SelectTheatreAndTimeInfo(
            name="沃美影城",
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_select_movie_theatre_and_time_2():
    """
    影院搜索页搜索影院  预期是先点击搜索框
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovieTheatreAndTime(),
        image_path=str(DATASET_ROOT / "images" / "影院搜索_002.png"),
        state=state,
        output_dir='.',
        middle_info=SelectTheatreAndTimeInfo(
            name="沃美影城",
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_select_movie_theatre_and_time_2_1():
    """
    影院搜索页搜索影院  预期是先点击搜索框
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        actions_record=[
            ClickAction(name='click', x=0.284, y=0.045, target_ui_element=Button(name='影院搜索输入栏', description='影院搜索输入栏'))
        ]
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovieTheatreAndTime(),
        image_path=str(DATASET_ROOT / "images" / "影院搜索_002.png"),
        state=state,
        output_dir='.',
        middle_info=SelectTheatreAndTimeInfo(
            name="沃美影城",
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_select_movie_theatre_and_time_3():
    """
    影院搜索结果有多个，ask_huamn 用户选择哪个
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovieTheatreAndTime(),
        image_path=str(DATASET_ROOT / "images" / "影院搜索选择_001.jpg"),
        state=state,
        output_dir='.',
        middle_info=SelectTheatreAndTimeInfo(
            name="沃美影城",
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_select_movie_theatre_and_time_4():
    """
    ask_human询问日期
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovieTheatreAndTime(),
        image_path=str(DATASET_ROOT / "images" / "场次选择_001.jpg"),
        state=state,
        output_dir='.',
        middle_info=SelectTheatreAndTimeInfo(
            name="沃美影城",
            date="",
            time=""
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_select_movie_theatre_and_time_4_1():
    """
    点击日期
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovieTheatreAndTime(),
        image_path=str(DATASET_ROOT / "images" / "场次选择_001.jpg"),
        state=state,
        output_dir='.',
        middle_info=SelectTheatreAndTimeInfo(
            name="沃美影城",
            date="12月30日",
            time=""
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_select_movie_theatre_and_time_5():
    """
    ask_huam询问观影场次
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovieTheatreAndTime(),
        image_path=str(DATASET_ROOT / "images" / "场次选择_001.jpg"),
        state=state,
        output_dir='.',
        middle_info=SelectTheatreAndTimeInfo(
            name="沃美影城",
            date="12月29日",
            time=""
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_select_movie_theatre_and_time_5_1():
    """
    点击16:00场的购票
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE_THEATRE_AND_TIME,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovieTheatreAndTime(),
        image_path=str(DATASET_ROOT / "images" / "场次选择_001.jpg"),
        state=state,
        output_dir='.',
        middle_info=SelectTheatreAndTimeInfo(
            name="沃美影城",
            date="12月29日",
            time="16:00"
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_select_seat_1():
    """
    无人数、返回ask_human询问观影人数
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_SEAT,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectSeat(),
        image_path=str(DATASET_ROOT / "images" / "座位选择_002.jpg"),
        state=state,
        output_dir='.',
        middle_info=SelectSeatInfo(
            number_of_people=None
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_select_seat_2():
    """
    点击推荐座位的人数
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_SEAT,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectSeat(),
        image_path=str(DATASET_ROOT / "images" / "座位选择_002.jpg"),
        state=state,
        output_dir='.',
        middle_info=SelectSeatInfo(
            number_of_people=2
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_select_seat_3():
    """
    选座完成后，点击确认选座
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_SEAT,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectSeat(),
        image_path=str(DATASET_ROOT / "images" / "座位选择结果_001.jpg"),
        state=state,
        output_dir='.',
        middle_info=SelectSeatInfo(
            number_of_people=1
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_confirm_order_1():
    """
    pay_or_not为unknown状态：ask_human询问用户是否确认
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.CONFIRM_ORDER,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepConfirmOrder(),
        image_path=str(DATASET_ROOT / "images" / "订单确认_001.jpg"),
        state=state,
        output_dir='.',
        middle_info=ConfirmOrderInfo(
            pay_or_not=ConfirmPayKnowingStatus.UNKNOWN
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_confirm_order_2():
    """
    pay_or_not为yes状态：点击确认支付
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.CONFIRM_ORDER,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepConfirmOrder(),
        image_path=str(DATASET_ROOT / "images" / "订单确认_001.jpg"),
        state=state,
        output_dir='.',
        middle_info=ConfirmOrderInfo(
            pay_or_not=ConfirmPayKnowingStatus.YES
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_confirm_order_3():
    """
    pay_or_not为no状态：退出
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.CONFIRM_ORDER,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepConfirmOrder(),
        image_path=str(DATASET_ROOT / "images" / "订单确认_001.jpg"),
        state=state,
        output_dir='.',
        middle_info=ConfirmOrderInfo(
            pay_or_not=ConfirmPayKnowingStatus.NO
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_confirm_order_4():
    """
    确认订单弹窗：勾选同意协议
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.CONFIRM_ORDER,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepConfirmOrder(),
        image_path=str(DATASET_ROOT / "images" / "确认订单弹窗.png"),
        state=state,
        output_dir='.',
        middle_info=ConfirmOrderInfo(
            pay_or_not=ConfirmPayKnowingStatus.UNKNOWN
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_confirm_order_5():
    """
    确认订单弹窗已勾选同意协议：点击继续购票
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.CONFIRM_ORDER,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepConfirmOrder(),
        image_path=str(DATASET_ROOT / "images" / "确认订单弹窗已勾选.png"),
        state=state,
        output_dir='.',
        middle_info=ConfirmOrderInfo(
            pay_or_not=ConfirmPayKnowingStatus.UNKNOWN
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_payment_1():
    """
    点击确认支付
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.PAYMENT,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepPayment(),
        image_path=str(DATASET_ROOT / "images" / "支付订单_001.png"),
        state=state,
        output_dir='.',
        middle_info={}
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_payment_2():
    """
    点击二维码支付
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.PAYMENT,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepPayment(),
        image_path=str(DATASET_ROOT / "images" / "订单支付_001.png"),
        state=state,
        output_dir='.',
        middle_info={}
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_payment_3():
    """
    点击二维码支付
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.PAYMENT,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepPayment(),
        image_path=str(DATASET_ROOT / "images" / "支付二维码.png"),
        state=state,
        output_dir='.',
        middle_info={}
    )
    print(f'result: {result}')
    action = result.actions[0]

@pytest.mark.asyncio
async def test_ui_step_select_movie_bad_case_count_down_window():
    """
    bad case 首页倒计时弹窗
    """
    state = MovieTicketBookingUIFlowState(
        task="电影购票",
        step=MovieTicketBookingStep.SELECT_MOVIE,
        background_info=f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    result, step, status = await get_and_draw_action(
        step=UIStepSelectMovie(),
        image_path=str(DATASET_ROOT / "images" / "bad_首页倒计时弹窗.png"),
        state=state,
        output_dir='.',
        middle_info=SearchMovieInfo(
            name="阿凡达3",
        ),
    )
    print(f'result: {result}')
    action = result.actions[0]
    assert isinstance(action, WaitAction)