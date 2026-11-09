import asyncio
import yaml

from projects.mind.advisor.domain_data import UserBase, Preference, VehicleState, VisualExterior, VisualInterior, \
    ComfortPrinciplesBase, ComfortDimensionsBase, EventBase
from projects.mind.advisor.advisors.comfort import ComfortAdviser


user = UserBase(
    name="苏苏",
    age=30,
    gender="男",
    preferences=[
        Preference(desc="喜欢凉快"),
    ],
)

path = "vehicle_state.json"
with open(path, "r", encoding='utf-8') as file:
    vehicle_state = yaml.safe_load(file.read())
vehicle_state = VehicleState(**vehicle_state)

visual_ext = VisualExterior(
    weather="天气炎热，32摄氏度",
)

comfort_principles = ComfortPrinciplesBase(
    holistic_coordination="各维度舒适性需协调统一，避免单方面过度优化影响其他方面",
    personalized_customization="根据乘客偏好、生理特征和使用场景个性化调节",
    dynamic_adaptation="根据时间、环境、行程阶段动态调整舒适性设置",
    proactive_prevention="提前预测舒适性需求并主动调节，而非被动响应",
    health_priority="在提升舒适性的同时确保健康和安全"
)
comfort_dims = ComfortDimensionsBase(
    temperature_comfort="确保车内温度保持在人体最适宜的范围内，避免过冷或过热造成不适。包括调节空调温度、风量、出风模式等，同时考虑座椅加热/通风功能对局部体感的影响。",
    air_quality_comfort="保持车内空气清新、无异味，控制污染物浓度，提供适宜的湿度和氧气含量。包括空气净化、内外循环管理、香氛系统等。",
    lighting_comfort="调节车内光照强度、色温和分布，避免眩光、强光直射，提供适宜的氛围照明和阅读照明。",
    acoustic_comfort="控制车内声音环境的舒适度，包括降低噪音、调节音量和音质、提供适宜的背景音乐或白噪声等。",
    seating_comfort="确保座椅的支撑性、包裹性和调节灵活性，减少长时间乘坐的疲劳感，提供按摩、通风等舒适功能。",
    spatial_comfort="优化车内空间布局和利用效率，保证足够的头部、腿部和肘部空间，合理布置储物空间，避免拥挤感。",
    other_comfort="包括触觉、嗅觉、心理感受等其他影响舒适性的因素，如内饰材质、操作便利性、隐私保护、娱乐系统等。"
)

# event = EventBase(event="车辆启动了空调系统")
# event = EventBase(event="苏苏作为乘客正在看书")
event = EventBase(event="主驾上车了")
# event = EventBase(event="苏苏作为乘客在擤鼻涕")


def generator(advisor):
    return asyncio.run(advisor.run(user=user, vehicle_state=vehicle_state, visual_ext=visual_ext, dimension=comfort_dims, principle=comfort_principles, event=event))

def discriminator(advisor, res):
    return asyncio.run(advisor.validator(res, user=user, vehicle_state=vehicle_state, visual_ext=visual_ext, principle=comfort_principles, event=event))


if __name__ == "__main__":
    advisor = ComfortAdviser()
    res = generator(advisor)
    process = discriminator(advisor, res)
    print(f"1. analysis_process: {process.analysis_process}")
    print(f"2. correlation_details: {process.correlation_details}")
    print(f"3. causal_details: {process.causal_details}")
    print(f"4. car_status_details: {process.car_status_details}")

