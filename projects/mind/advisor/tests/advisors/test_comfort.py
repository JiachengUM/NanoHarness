import asyncio

from rich import print

from projects.mind.advisor.task_data import (
    EventBase, UserBase, Preference, VehicleState, VisualExterior, VisualInterior, AdvisorContext, AdvisorInput
)

from projects.mind.advisor.advisors.comfort import ComfortAdviser

def test_comfort_basic():
    event = EventBase(event="用户上车了")

    user = UserBase(
        name="小黄",
        age=30,
        gender="男",
        preferences=[
            Preference(desc="喜欢凉快"),
        ],
    )

    vehicle_state = VehicleState(
        air_condition="空调关闭着",
    )

    visual_ext = VisualExterior(
        weather = "天气炎热，32摄氏度",
    )

    advisor = ComfortAdviser()

    output, run_res = asyncio.run(advisor.run(
        AdvisorInput(
            event=event,
            context=AdvisorContext(user=user, vehicle_state=vehicle_state, visual_exterior=visual_ext),
        ),
    ))

    print(output)
    
    print(run_res)


if __name__ == "__main__":
    test_comfort_basic()
