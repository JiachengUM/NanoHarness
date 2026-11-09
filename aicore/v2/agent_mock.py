from typing import AsyncGenerator, Any

import anyio

from aicore.events.agent import (
    AgentOutTextStartEvent,
    AgentOutTextDeltaEvent,
    AgentOutTextDoneEvent,
    TaskCreatedEvent,
)

from aicore.v2.agent_model import AgentBase, AgentInputEvent, AgentOutEvent, TaskSuccess, TaskSuccessEvent, TaskAStreamWorkerGeneral

def weather_tool_factory(location: str) -> TaskAStreamWorkerGeneral:
    async def weather_tool():
        print(f"调用天气工具, 位置: {location}")
        await anyio.sleep(1)
        yield TaskSuccess(result="天气晴朗")

    return weather_tool


class AgentMocked(AgentBase):

    async def astream(self, input: AgentInputEvent, /, **kwargs: Any) -> AsyncGenerator[AgentOutEvent, None]:

        if isinstance(input, str):
            print(f"收到用户输入: {input}")
            if "天气" in input:
                yield TaskCreatedEvent(task_id="天气查询", name="weather_tool", arguments={"location": "北京"})
                return

            # 不调用任何工具生成任务，直接返回答案
            yield AgentOutTextStartEvent()
            yield AgentOutTextDeltaEvent(delta=f"answer for: {input}")
            yield AgentOutTextDoneEvent()

            return

        assert isinstance(input, TaskSuccessEvent)
        print(f"收到任务完成结果: {input}")
        yield AgentOutTextStartEvent()
        yield AgentOutTextDeltaEvent(delta=f"收到任务{input.task_id}的完成结果{input.result}, 生成回复")
        yield AgentOutTextDoneEvent()
        

    def get_task_factory(self, task_name: str, arguments: dict[str, Any]) -> TaskAStreamWorkerGeneral:
        if task_name == "weather_tool":
            return weather_tool_factory(**arguments)
        
        raise NotImplementedError