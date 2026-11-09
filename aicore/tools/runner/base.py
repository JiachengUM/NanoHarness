from typing import AsyncGenerator

from abc import ABC, abstractmethod

from pydantic import BaseModel

from aicore.tools import ToolProtocol


class ToolRunnerBase[TT: ToolProtocol[BaseModel], E](ABC):
    def __init__(self):
        pass

    # 调用方需要确保 arguments 是符合对应 tool args_schema 要求的实例
    @abstractmethod
    def add_tool(self, tool: TT, arguments: BaseModel): ...

    @abstractmethod
    async def run(self) -> AsyncGenerator[E, None]:
        raise NotImplementedError()
        yield None  # 必须有yield，run才能被type checker识别为AsyncGenerator

    @property
    @abstractmethod
    def tool_results(self) -> list[str]: ...
