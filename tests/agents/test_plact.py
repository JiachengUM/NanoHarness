"""E2E test: astream_plact (plan → execute → answer).

Run directly:
    uv run python tests/agents/test_plact.py
"""

import time

import anyio
from rich import print

from aicore.agents.plan.core import astream_plact, PlActFinishEvent
from aicore.agents.plan.events import PlanCreatedEvent, PlanStepDoneEvent
from aicore.agents.plan.experiment.plan_schema_v1 import plan_spec_v1
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

# model = ModelName.SEED_1_6_251015
# model = ModelName.SEED_2_1_TURBO_260628
model = ModelName.SEED_1_6_251015
model_api = create_model_api(model=model, backend="responses")

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

QUERIES = [
    # "先查一下北京明天的气温和天气状况，另外再看看我附近的停车场，如果最低气温小于21度并且500内有地面停车场，就导航到评分最高那个，否则就导航到北京三里屯",
    # "先找一下广州市天河区人均消费50元以下的便利店，并告诉我详细地址，然后导航过去，路上顺便放一首轻音乐",
    # "先查一下北京明天的气温和天气状况，如果气温低于10度就把车内空调调到暖风26度，高于30度就调到冷风22度，否则就关闭空调开窗",
    # "我想听华语流行音乐，先搜索一下，然后从第一条开始播放并自动续播，音量调到50，顺便告诉我每条歌曲的标题和演唱者",
    # "先查一下南宁今天的天气，如果气温超过30度就把空调调到22度制冷，再找一下南宁市区评分最高的螺蛳粉店，告诉我人均消费和地址，然后导航过去",
    # "先找一下合肥蜀山区评分最高的徽菜馆，告诉我人均消费和地址，再查一下周边的停车场收费标准，顺便找一下附近的充电站，最后规划一条经济路线过去",
    # "我想先查一下上海虹桥机场T2航站楼附近有没有空余车位的停车场，再查一下虹桥机场到浦东机场之间驾车的预计通行时间，顺便查一下G4京港澳高速的拥堵指数，如果拥堵指数高于8就建议换一条路线，最后导航到虹桥机场T2",
    # "周六下午我带一个喜欢周杰伦的朋友在上海玩，先帮我查《晴天》对应的专辑和曲风；再看上海周六下午天气和交通，如果不适合户外，就优先找附近评分高、今天营业、停车方便的 KTV、LiveHouse 或唱片店，最好氛围跟这首歌/专辑风格接近；找到第一个合适地点后，再查它周六的停车收费、近期活动和排队情况；最后根据刚才查到的曲风和这个地点的氛围，找一张适合路上听的华语流行歌单。",
    # "我想比较下北京和上海的爵士酒吧，看看哪个城市的爵士氛围更浓。先各找几家评分高的爵士酒吧，再看看两边周末天气和交通，先选一个城市，然后从选中的城市里挑出两三家串成一条酒吧路线，每个酒吧都看看停车，路上放爵士歌单。",
    # "下午想带爸妈去听个京剧或者传统音乐，老人家走不动也不能太折腾。先看看现在路上堵不堵，要是堵就找近点的室内场馆，不堵可以去远点但是有名的地方。每个地方都帮我看看有没有电梯无障碍设施，最后挑一个最合适的，再配点适合老人听的舒缓国风音乐。",
    "这个周末我在南京和苏州之间二选一，想做一趟音乐主题小旅行，帮我看天气、路况和现场演出，选一个更稳的城市，再排下午到晚上的路线。"
    # "我想去和平门附近吃烤鸭，出发前先看看那边附近有没有评分高的加油站加满油，再查一下今天的天气会不会下雨，顺便确认一下京藏高速现在堵不堵，对了顺便告诉我那家店的人均消费大概多少钱，最后规划最快路线过去",
    # "周六下午我带一个喜欢周杰伦的朋友在上海玩，先帮我查《晴天》对应的专辑和曲风；然后找我附近评分高、今天营业、停车方便的 KTV、LiveHouse 或唱片店，最好氛围跟这首歌/专辑风格接近；找到第一个合适地点后，再查它周六的停车收费、近期活动和排队情况；最后根据刚才查到的曲风和这个地点的氛围，找一张适合路上听的华语流行歌单"
    # "这个周末我在南京和苏州之间二选一，想做一趟音乐主题小旅行，帮我看天气、路况和现场演出，选一个更稳的城市，再排下午到晚上的路线。"
    # "我现在要把《晴天》加入播放列表自动播放，之后帮我搜一下周杰伦唱的《晴天》相关的歌曲，再帮我找5首适合开车听的轻音乐，要歌词里有晴天相关内容的" # 没查到周杰伦的晴天, 后续怎么处理
    # "我在北京，下午想带爸妈去听个京剧或者传统音乐，老人家走不动也不能太折腾。先看看现在路上堵不堵，要是堵就找近点的室内场馆，不堵可以去远点但是有名的地方。每个地方都帮我看看有没有电梯无障碍设施，最后挑一个最合适的，再配点适合老人听的舒缓国风音乐。"
]


async def run_query(query: str) -> None:
    print(f"\n=== query ===\n{query}")

    timing: list[tuple[str, float]] = []  # (label, elapsed_since_prev)
    t0 = t_prev = time.perf_counter()

    state = model_api.initial_state(
        system_prompt="你是一个友好的车载助手, 回答问题尽量使用口语, 方便语音播报。"
    )
    async for event in astream_plact(
        query,
        model_api=model_api,
        state=state,
        tools=tools,  # type: ignore[arg-type]
        spec=plan_spec_v1,
    ):
        now = time.perf_counter()
        if isinstance(event, PlanCreatedEvent):
            timing.append(("plan", now - t_prev))
            t_prev = now
        elif isinstance(event, PlanStepDoneEvent):
            timing.append((f"step {event.step_id} ({event.step_goal})", now - t_prev))
            t_prev = now

        if isinstance(event, PlActFinishEvent) and isinstance(event.response, str):
            timing.append(("answer", now - t_prev))
            print(event.model_dump(exclude={"response"}))
            print(event.response)
        else:
            print(event)

    total = time.perf_counter() - t0
    print("\n=== timing ===")
    for label, dt in timing:
        print(f"  {label}: {dt:.2f}s")
    print(f"  total: {total:.2f}s")


async def main() -> None:
    for query in QUERIES:
        await run_query(query)


if __name__ == "__main__":
    anyio.run(main, backend="asyncio")
