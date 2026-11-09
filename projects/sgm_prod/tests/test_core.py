from __future__ import annotations

import asyncio
import sys
import uuid

from aicore.agents.experiments.user_profile import SINGLE_CAREER_WOMAN

from projects.sgm_prod.core import AgentDoStreamRequest, CarInfo, LngLat, SGMAgent


def _make_req(query: str, chat_id: str, car_info: CarInfo | str | None = None) -> AgentDoStreamRequest:
    return AgentDoStreamRequest(
        chat_id=chat_id,
        question_id=chat_id,
        query=query,
        intent_type="复杂推理",
        car_info=car_info,
    )


def _build_demo_car_info() -> CarInfo:
    return CarInfo(
        mainEngine="sgm",
        vehicleId="demo_vehicle_001",
        vehicleType="NDBEV_MY27",
        vehicle_name="别克君越",
        sound_zone="主驾",
        province="上海市",
        city="上海市",
        district="浦东新区",
        town="张江镇",
        longitude=121.473701,
        latitude=31.230416,
        audio_name="晴天",
        audio_producer="周杰伦",
        video_name="无",
        video_episodes=0,
        tts_language="mandarin",
        current_location="浦东新区世纪大道",
        target_location="上海虹桥火车站",
        home_location="浦东新区花木路",
        home_lng_lat=LngLat(longitude=121.548303, latitude=31.226136),
        company_location="浦东新区张江高科",
        company_lng_lat=LngLat(longitude=121.601534, latitude=31.202252),
        nav_dest_name="虹桥火车站",
        nav_dest_address="闵行区申虹路",
        nav_dest_lng_lat=LngLat(longitude=121.327436, latitude=31.200195),
        nav_waypoint="",
        nav_remain_distance="16公里",
        nav_remain_cost="35分钟",
        nav_road_congestion="畅通",
        fatigue=0,
        battery=76,
        rain_sensor=0,
        car_heading=90,
    )


async def run_base(query: str) -> None:
    """基础：无 user_profile、无 car_info。"""
    chat_id = f"sgm_test_{uuid.uuid4().hex[:8]}"
    agent = SGMAgent.build(chat_id=chat_id)
    req = _make_req(query, chat_id)

    print(f"\n=== [base] {query} ===")
    async for chunk in agent.astream_chunks(req):
        print(chunk.model_dump(exclude_none=True))


async def run_with_user_profile(query: str) -> None:
    """传入 user_profile：agent 的 system_prompt 会自动追加用户画像。"""
    chat_id = f"sgm_test_{uuid.uuid4().hex[:8]}"
    agent = SGMAgent.build(chat_id=chat_id, user_profile=SINGLE_CAREER_WOMAN)
    req = _make_req(query, chat_id)

    print(f"\n=== [user_profile={SINGLE_CAREER_WOMAN.user_type}] {query} ===")
    async for chunk in agent.astream_chunks(req):
        print(chunk.model_dump(exclude_none=True))


async def run_with_car_info(query: str) -> None:
    """传入 car_info：每次请求时通过 Jinja2 模板渲染注入 system_prompt。"""
    chat_id = f"sgm_test_{uuid.uuid4().hex[:8]}"
    agent = SGMAgent.build(chat_id=chat_id)
    car_info = _build_demo_car_info()
    req = _make_req(query, chat_id, car_info=car_info)

    print(f"\n=== [car_info] {query} ===")
    async for chunk in agent.astream_chunks(req):
        print(chunk.model_dump(exclude_none=True))


async def run_with_both(query: str) -> None:
    """同时传入 user_profile 和 car_info。"""
    chat_id = f"sgm_test_{uuid.uuid4().hex[:8]}"
    agent = SGMAgent.build(chat_id=chat_id, user_profile=SINGLE_CAREER_WOMAN)
    car_info = _build_demo_car_info()
    req = _make_req(query, chat_id, car_info=car_info)

    print(f"\n=== [user_profile + car_info] {query} ===")
    async for chunk in agent.astream_chunks(req):
        print(chunk.model_dump(exclude_none=True))


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "周杰伦有什么歌，帮我搜一下并播放"

    asyncio.run(run_base(query))
    # asyncio.run(run_with_user_profile(query))
    # asyncio.run(run_with_car_info("后排车窗现在是什么状态"))
    # asyncio.run(run_with_both("根据我的喜好推荐一首歌，然后开一下空调"))


if __name__ == "__main__":
    main()
