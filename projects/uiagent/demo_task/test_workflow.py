from pathlib import Path
from typing import Final

import copy
import time
import asyncio

from pydantic import BaseModel

from nanoai.utils.nl_repr import nl_repr

from projects.uiagent.demo_task.workflow import (
    EPage, 
    EUIStep,
    RestaurantName,
    SeatBookingDetails,
    SeatBookingPersonInfo,
    WorkflowDemo,
)

from projects.uiagent.core.test_utils import Environment, run_ui_step, run_workflow

DATASET_ROOT: Final[Path] = Path(".") / "projects" / "uiagent" / "demo_task" / "datasets"
image_root = DATASET_ROOT


def test_workflow_basic() -> None:
    workflow = WorkflowDemo()

    # state是可以copy的
    state = copy.deepcopy(workflow.state)

    # 但workflow不行
    # wf_cp = copy.deepcopy(workflow)

    # 不允许
    # workflow.set_state(image="")

async def test_run_nl_intent_and_info() -> None:
    '''比较和验证_run_intent_and_info_fast的效果, 目前人为地修改了run_nl的实现, 将_run_intent_and_info替换为_run_intent_and_info_fast
    耗时少很多，之后可以改为debug mode'''
    start_time = time.perf_counter()

    workflow = WorkflowDemo()
    result = await workflow.run_nl("你好呀")  # 意图： 不相关
    print(f"\n{nl_repr(result)}")
    print(nl_repr(workflow.state))

    workflow = WorkflowDemo()
    result = await workflow.run_nl("请退出。") # 意图： 退出
    print(f"\n{nl_repr(result)}")
    print(nl_repr(workflow.state))

    workflow = WorkflowDemo()
    result = await workflow.run_nl("帮我在潮界火锅订个座, 2个人, 明天中午12点, 大厅")  # 意图： 相关
    print(f"\n{nl_repr(result)}")
    print(nl_repr(workflow.state))

    total_elapsed = (time.perf_counter() - start_time) * 1000
    print(f"\n三次 run_nl 总耗时: {total_elapsed:.2f} ms")

async def test_run_nl() -> None:
    workflow = WorkflowDemo()
    result = await workflow.run_nl("你好呀")  # 意图： 不相关
    print(f"\n{nl_repr(result)}")

    workflow = WorkflowDemo()
    result = await workflow.run_nl("请退出。") # 意图： 退出
    print(f"\n{nl_repr(result)}")

    workflow = WorkflowDemo()
    result = await workflow.run_nl("帮我在潮界火锅订个座, 2个人, 明天中午12点, 大厅")  # 意图： 相关
    print(f"\n{nl_repr(result)}")


async def test_run_nl_multi_turn() -> None:
    """测试同一个workflow实例在多轮对话里如何累计nl_messages。"""
    queries = [
        "你好，我想订潮界火锅",
        "需要2个人，明天中午12点",
        "位置靠窗就好，还要大厅",
    ]

    workflow = WorkflowDemo()

    for idx, query in enumerate(queries, start=1):
        result = await workflow.run_nl(query)
        print(f"\n[第{idx}轮] query: {query}")
        print(nl_repr(result))

    print("\n多轮结束后的nl_messages:")
    for message in workflow.state.nl_messages:
        print(message)


ENV: Final[Environment] = Environment({
        EPage.SELECT_RESTAURANT: str(image_root / "001.jpg"),
        EPage.START_SEAT_BOOKING: str(image_root / "002.jpg"),
        EPage.CONFIRM_SEAT_BOOKING_DETAILS: str(image_root / "003.jpg"),
        EPage.CONFIRM_SEAT_BOOKING_PERSON_INFO: str(image_root / "004.jpg"),
    })


# 这里的info字段可以是结构化类型（内部会检查语义约束），也可以是str（内部不做检查）
# 怎么用取决于测试的目的。
step_info = [
    (EUIStep.SELECT_RESTAURANT, RestaurantName(name="潮界火锅")),
    (EUIStep.SELECT_RESTAURANT, None),   # 无效middle_info
    (EUIStep.START_SEAT_BOOKING, None),
    (EUIStep.CONFIRM_SEAT_BOOKING_DETAILS, SeatBookingDetails(number_of_people=2, time="明晚8点", seat_type="大厅")),
    (EUIStep.CONFIRM_SEAT_BOOKING_DETAILS, None),
    (EUIStep.CONFIRM_SEAT_BOOKING_PERSON_INFO, "姓名小明, 手机号13800138000, 性别男, 备注无"),
]


async def test_workflow_ui_step(step: EUIStep, info: BaseModel | str | None) -> None:
    print(f"\ntest_workflow_ui_step: step: {step} info: {info}")

    output_dir = str(DATASET_ROOT / "step_results")
    # output_dir = None

    result = await run_ui_step(
        WorkflowDemo, 
        str(ENV.page_images[step]), 
        step, 
        info=info, 
        output_dir=output_dir,
        output_filename=f"{step}",
        )

    print(f"\nresult\n{nl_repr(result)}")


async def test_workflow_auto_full() -> None:
    '''自动执行workflow，直到完成。
    这是Workflow level的端到端测试函数。这是写fast api以及前端的基础。
    麻雀虽小，五脏俱全。以后会越来越全。
    '''

    query = "帮我在潮界火锅订个座, 2个人, 明天中午12点, 大厅。姓名小明, 手机号13800138000, 性别男, 备注为尽量靠窗"

    await run_workflow(WorkflowDemo, ENV, query)


def main() -> None:
    #test_workflow_basic()
    #return

    # asyncio.run(test_run_nl_intent_and_info())
    # return

    #asyncio.run(test_run_nl())
    asyncio.run(test_run_nl_multi_turn())
    return

    # for step in step_info[:]:
    #     asyncio.run(test_workflow_ui_step(*step))
    # return

    # asyncio.run(test_workflow_auto_full())
    # return


if __name__ == "__main__":
    main()