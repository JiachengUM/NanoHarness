from typing import Literal, Annotated, Union

from rich import print

from pydantic import Field, TypeAdapter

from aicore.core.event import EventBase

class UserLoginEvent(EventBase):
    # 1. Literal 用于 Discriminated Union 识别
    # 2. default 用于自动赋值
    # 3. init=False 用于禁止用户传参篡改
    type: Literal["user_login"] = Field(default="user_login", init=False)
    
    username: str

class UserLogoutEvent(EventBase):
    type: Literal["user_logout"] = Field(default="user_logout", init=False)
    user_id: int


EventType = Annotated[Union[UserLoginEvent, UserLogoutEvent], Field(discriminator='type')]


def test_basic():
    # ✅ 1. 正常创建，type 自动填充
    event = UserLoginEvent(username="alice")
    print(f"类型: {event.type}") # 输出: user_login

    # ❌ 2. 用户试图篡改 type -> 报错 (因为 init=False)
    try:
        UserLoginEvent(username="bob", type="hacker")  # type: ignore
    except Exception as e:
        print("篡改失败:", e)

    # ❌ 3. 用户试图注入其他字段 -> 报错 (因为 extra='forbid')
    try:
        UserLoginEvent(username="charlie", is_admin=True)  # type: ignore
    except Exception as e:
        print("注入失败:", e)


def test_discriminated_union():
    adapter = TypeAdapter(EventType)
    parsed = adapter.validate_python({"type": "user_logout", "user_id": 101})
    print(f"解析类型: {type(parsed).__name__}") # 输出: UserLogoutEvent
    print(parsed)

    parsed = adapter.validate_python({"type": "user_login", "username": "alice"})
    print(f"解析类型: {type(parsed).__name__}") # 输出: UserLoginEvent
    print(parsed)

    # 错误的输入
    try:
        adapter.validate_python({"type": "hacker", "user_id": 101})
    except Exception as e:
        print("错误的输入:", e)


def main():
    test_basic()
    test_discriminated_union()


if __name__ == "__main__":
    main()