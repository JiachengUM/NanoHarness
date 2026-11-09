import anyio
import json
from pathlib import Path
from typing import Any

from rich import print

from aicore.agents.plan.core import PlanSpec, create_plan
from aicore.agents.plan.experiment.plan_schema_v0 import plan_spec_v0
from aicore.agents.plan.experiment.plan_schema_v1 import plan_spec_v1
from aicore.agents.plan.experiment.plan_schema_v2 import plan_spec_v2
from aicore.models.credentials import ModelName
from aicore.models.model_api import create_model_api
from projects.mind.toolset.dag import WebsearchTool, poi_search_tool, SGMPoiWorker
from projects.mind.toolset.dag.car_control import CarControlTool
from projects.mind.toolset.dag.media import MediaTool
from projects.mind.toolset.dag.navigate import NavigateTool
from projects.mind.toolset.dag.music_search import (
    qq_music_album_search_tool,
    qq_music_playlist_search_tool,
    qq_music_song_search_tool,
)


# model = ModelName.SEED_2_0_MINI_260428   # 无法输出多个 step
# model = ModelName.SEED_1_8_251228        # 能输出多个 step，但不稳定
model = ModelName.SEED_1_6_251015          # 能输出多个 step，但不稳定
# model = ModelName.SEED_2_0_PRO_260215

model_api = create_model_api(model=model, backend="responses")

QUERIES = [
    "先查一下北京明天的气温和天气状况，另外再看看我附近的停车场，如果最低气温小于21度并且500内有地面停车场，就导航到评分最高那个，否则就导航到北京三里屯",
    # "先找一下广州市天河区人均消费50元以下的便利店，并告诉我详细地址，然后导航过去，路上顺便放一首轻音乐",
    # "先查一下北京明天的气温和天气状况，如果气温低于10度就把车内空调调到暖风26度，高于30度就调到冷风22度，否则就关闭空调开窗",
    # "我想听华语流行音乐，先搜索一下，然后从第一条开始播放并自动续播，音量调到50，顺便告诉我每条歌曲的标题和演唱者",
    # "先查一下南宁今天的天气，如果气温超过30度就把空调调到22度制冷，再找一下南宁市区评分最高的螺蛳粉店，告诉我人均消费和地址，然后导航过去",
    # "先找一下合肥蜀山区评分最高的徽菜馆，告诉我人均消费和地址，再查一下周边的停车场收费标准，顺便找一下附近的充电站，最后规划一条经济路线过去",
    # "我想先查一下上海虹桥机场T2航站楼附近有没有空余车位的停车场，再查一下虹桥机场到浦东机场之间驾车的预计通行时间，顺便查一下G4京港澳高速的拥堵指数，如果拥堵指数高于8就建议换一条路线，最后导航到虹桥机场T2",
    # "我想去全聚德和平门店吃烤鸭，出发前先看看那边附近有没有评分高的加油站加满油，再查一下今天的天气会不会下雨，顺便确认一下京藏高速现在堵不堵，对了顺便告诉我那家店的人均消费大概多少钱，最后规划最快路线过去",
]

chat_id = "User"
tools = [
    CarControlTool(chat_id=chat_id),
    MediaTool(chat_id=chat_id),
    NavigateTool(chat_id=chat_id),
    qq_music_song_search_tool(),
    qq_music_playlist_search_tool(),
    qq_music_album_search_tool(),
    poi_search_tool(SGMPoiWorker()),
    WebsearchTool(),
]

# 待测 spec：每个自包含、互不继承，加一行即可横向对比。
SPECS: list[PlanSpec[Any]] = [
    plan_spec_v0,
    plan_spec_v1,
    plan_spec_v2,
]


def _error_payload(error: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error_type": type(error).__name__,
        "error_message": str(error),
    }
    if hasattr(error, "errors"):
        payload["errors"] = error.errors()  # type: ignore[attr-defined]
    return payload


async def process_query(spec: PlanSpec[Any], query: str, index: int) -> dict[str, Any]:
    result: dict[str, Any] = {"spec": spec.name, "index": index, "query": query}

    try:
        plan, _ = await create_plan(query, model_api=model_api, tools=tools, spec=spec)
        result["success"] = True
        result["plan"] = plan.model_dump()
        print(f"[{spec.name}] query {index} ok")
    except Exception as error:
        result["success"] = False
        result["error"] = _error_payload(error)
        print(f"[{spec.name}] query {index} failed: {type(error).__name__}")

    return result


async def test_create_plan():
    results: list[dict[str, Any]] = []

    async with anyio.create_task_group() as tg:
        async def execute(spec: PlanSpec[Any], index: int, query: str):
            results.append(await process_query(spec, query, index))

        for spec in SPECS:
            for index, query in enumerate(QUERIES):
                tg.start_soon(execute, spec, index, query)

    results.sort(key=lambda item: (item["spec"], item["index"]))

    model_label = getattr(model, "value", str(model)).replace("/", "_")

    print("\n=== raw spec results ===")
    for spec in SPECS:
        rows = [row for row in results if row["spec"] == spec.name]
        success = sum(1 for row in rows if row["success"])

        output_file = Path(f"plan_results_{model_label}_{spec.name}.json")
        output_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"  {spec.name}: {success}/{len(rows)} parsed -> {output_file}")


async def main():
    await test_create_plan()


if __name__ == "__main__":
    anyio.run(main, backend="asyncio")
