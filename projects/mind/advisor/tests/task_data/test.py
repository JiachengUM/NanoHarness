from nanoai.utils.nl_repr import nl_repr

from projects.mind.advisor.task_data import (
    UserBase, 
    Preference, 
    VehicleState, 
    VisualExterior, 
    VisualInterior,
    AdvisorContext,
    AdvisorInput,
)

def test_context():

    user = UserBase(
            name="小黄",
            age=30,
            gender="男",
            preferences=[
                Preference(desc="喜欢凉快"),
                Preference(desc="喜欢美食"),
            ],
        )

    vehicle_state = VehicleState(air_condition="空调关闭着")

    visual_ext = VisualExterior(weather = "天气炎热，32摄氏度")

    context = AdvisorContext(
        user=user,
        vehicle_state=vehicle_state,
        visual_exterior=visual_ext,
    )

    print(nl_repr(context))


if __name__ == "__main__":
    test_context()
