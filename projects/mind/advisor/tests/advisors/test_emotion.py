import asyncio

from rich import print

from projects.mind.advisor.task_data import EventBase, UserBase, VehicleState, VisualExterior, VisualInterior, AdvisorContext, AdvisorInput
from projects.mind.advisor.advisors.emotion import EmotionAdviser


def test_emotion_basic():
    event = EventBase(event="用户上车了")

    user = UserBase(
        name="小苏",
        age=25,
        gender="女",
    )

    vehicle_state = VehicleState(
        air_condition="空调开启着",
    )

    visual_int = VisualInterior(
        general="用户看起来有点难过",
    )

    advisor = EmotionAdviser()

    output, run_res = asyncio.run(advisor.run(
        AdvisorInput(
            event=event,
            context=AdvisorContext(
                user=user,
                vehicle_state=vehicle_state,
                visual_interior=visual_int,
            ),
        ),
    ))

    print(output)

    print(run_res)

if __name__ == "__main__":
    test_emotion_basic()