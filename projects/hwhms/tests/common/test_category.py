from nanoai.utils.nl_repr import nl_repr
from projects.hwhms.common.category import Category


car_control_category = Category(
        name="车控",
        description="和汽车的各种操作和功能进行交互，包括设备控制、系统设置等。语气为命令或执行，而非询问或探讨。",
        examples=[
            "打开空调",
            "设置空调温度为26度",
            "暂停音乐",
            "切换到收音机频道",
        ],
        notices=[
            "提问如何操作（如怎么打开空调）的不属于车控领域。",
        ]
    )

if __name__ == "__main__":
    print(nl_repr(car_control_category))
