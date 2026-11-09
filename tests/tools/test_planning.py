import anyio

from rich import print

from aicore.tools import BaseTool
from aicore.tools.experiments.planning import is_tool_relevant, ToolRelevanceType

from aicore.models.credentials import ModelName
from aicore.models.model_api import (
    ModelCallParams,
    ModelParams,
    create_model_api,
)

from tests.tools.test_base_tool import (
    get_weather,
    NavigationTool,
)


model_params = ModelParams(
    # model = ModelName.SEED_1_8_251228
    model=ModelName.SEED_1_6_251015,
    params=ModelCallParams(),
)

CASES: list[tuple[str, BaseTool, ToolRelevanceType]] = [
    # for weather tool
    ("查询北京天气", get_weather, ToolRelevanceType.EXACT),
    ("看下天气", get_weather, ToolRelevanceType.PARTIAL),
    ("你好", get_weather, ToolRelevanceType.IRRELEVANT),
    # for navigation tool
    ("查询北京到上海的路线", NavigationTool(), ToolRelevanceType.EXACT),
    ("查询路线, 到上海", NavigationTool(), ToolRelevanceType.PARTIAL),
    ("哪里好玩", NavigationTool(), ToolRelevanceType.IRRELEVANT),
]


async def test_is_tool_relevant():
    model_api = create_model_api(
        backend="chat",
        model=model_params.model,
    )
    for case in CASES:
        res = await is_tool_relevant(
            case[0],
            case[1],
            model_api=model_api,
            state=model_api.initial_state(),
        )
        print(f"user query: {case[0]}")
        print(res)
        if res.relevance_type != case[2]:
            print(f"WRONG! relevance_type: {res.relevance_type}, expected: {case[2]}")


if __name__ == "__main__":
    anyio.run(test_is_tool_relevant)
