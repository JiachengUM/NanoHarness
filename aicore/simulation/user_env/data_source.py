from typing import AsyncGenerator

import asyncio

class UserDataSourceBase:
    async def __call__(self) -> AsyncGenerator[str, None]:
        raise NotImplementedError("UserDataSourceProtocol must be implemented")
        yield "you never see this"   # 虽然不会运行,但需要有个yield, 否则会报错：async for requires an object with __aiter__ method


class UserDataMocked(UserDataSourceBase):
    """
    TODO: 
    """

    def __init__(self, data_source: list[str]):
        self.data_source = data_source

    async def __call__(self) -> AsyncGenerator[str, None]:
        for data in self.data_source:
            yield data


async def test_user_data_source():
    user_data_source = UserDataMocked(["你好", "请介绍自己", "再见"])
    async for data in user_data_source():
        print(data)


if __name__ == "__main__":
    asyncio.run(test_user_data_source())