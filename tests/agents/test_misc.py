from typing import Any

from rich import print

from pydantic import BaseModel, Field

from aicore.tools.experiments.weather import create_weather_search_tool, _weather_dummy
from aicore.tools.experiments.poi_search import create_poi_search_tool, _poi_search_dummy_stream
from aicore.tools.experiments.music_search import _music_search_dummy, music_search_tool
from aicore.tools import TaskToolTypeGeneral

from aicore.models.credentials import ModelName
from aicore.models.model_api import ModelParams

from aicore.agents import ContextBase

WEATHER_TOOL = create_weather_search_tool(_weather_dummy, with_clarify=True)
POI_STREAM_TOOL = create_poi_search_tool(_poi_search_dummy_stream, with_clarify=True)
MUSIC_TOOL = music_search_tool(worker=_music_search_dummy)

TOOLS = [WEATHER_TOOL, POI_STREAM_TOOL, MUSIC_TOOL]

#AgentContext = ContextBase[TaskToolTypeGeneral]

class AgentContext(ContextBase[TaskToolTypeGeneral]):
    pass

def test_context_with_tools():
    model_params = ModelParams(model=ModelName.SEED_1_8_251228)

    print(f"type of original tools: {type(TOOLS[0])}")
    
    context = AgentContext(                                             # 这样写就不对。神奇的错误。
    # 归因分析
    # - 让
    #context = ContextBase(   # 这样写就正确
        system_prompt=None,
        model_params=model_params,
        tools=TOOLS,
    )

    print(f"type of context tools: {type(context.tools[0])}")


class MockTaskTool[IT](BaseModel):
    pass

class MockTaskToolWithClarify[IT](MockTaskTool[IT]):
    pass


class MockContextBase[TT](BaseModel):
    tools: list[TT] | None = Field(default=None, description="工具列表", exclude=True)


# 复现“tool类型退化到BaseTool”的最小条件。
# 1. base在derived的前面
# 2. 必须带泛型参数
#type ToolTypeGeneral = MockTaskTool[Any] | MockTaskToolWithClarify[Any]
# 这应该可以理解，在union类型中的子类型有泛型参数时，实例化顺序的bug。
# 修正方式，derived放在base前面
type ToolTypeGeneral = MockTaskToolWithClarify[Any] | MockTaskTool[Any]

class MockContextDerived(MockContextBase[ToolTypeGeneral]):
    pass


def test_tool_type_mock():
    tool = MockTaskToolWithClarify()

    print(f"type of tool: {type(tool)}")

    context = MockContextDerived(tools=[tool])

    print(f"type of context tools: {type(context.tools[0])}")


if __name__ == "__main__":
    test_context_with_tools()
    #test_tool_type_mock()
