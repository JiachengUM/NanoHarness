from rich import print

import asyncio

from pydantic import BaseModel, Field

from aicore.agents.experiments.base import SystemPrompt, AgentBase, ResponseParams, RunParams
from aicore.events.react import ReActEventPrinter
from aicore.models.credentials import create_client, AsyncArk, ModelName

from aicore.agents.experiments.user_profile import (
    UserProfile,
    SINGLE_CAREER_WOMAN,
    RETIRED_SENIOR,
    STARTUP_YOUTH,
    FULL_TIME_MOM,
    BUSINESS_ELITE,
)


QUERIES = [
    "简单讲述下我的个人重要信息，不超过3句话。",
    "下班了，准备回家。",
    "你认为我这个时间段适合哪项运动呢",
]


async def test_agent_with_user_profile(agent: AgentBase, queries: list[str]):
    for i, query in enumerate(queries):
        print("\n" + "="*80)
        print(f"[blue]测试流式输出 #{i+1}: {query}")
        print("="*80)
        async for _ in agent.astream(query, event_listeners=[ReActEventPrinter()]):
            pass
        print("="*80)

class CustomUserProfile(BaseModel):
    """自定义用户画像"""
    model_config = {"extra": "allow"}
    user_type: str = Field(..., description="用户类型")
    user_name: str = Field(..., description="用户姓名")
    age: str = Field(..., description="用户年龄")
    preferences: list[str] = Field(..., description="用户各种偏好")

# 自定义用户画像测试
test_profile = UserProfile(
    user_type="单身职场男性",
    residence="上海闵行平金中心1号楼",
    interests_hobbies=[
        "球类：乒乓球、羽毛球",
        "音乐人：许嵩、周杰伦、周传雄",
        "最近爱听：《清明雨上》、《青花》、《青花瓷》",
    ],
)

# 基于basemodel 定义的画像
custom_user_profile = CustomUserProfile(
    user_type="单身职场男性,测试",
    user_name="张三",
    age="30",
    preferences = [
    "夏季车载空调固定22℃，4级风量，面部+腿部出风，开启制冷外循环",
    "冬季座椅加热2档，空调28℃仅脚部出风，方向盘加热常开启",
    "驾驶位座椅固定为靠背105°、高度降2格、头枕抬1格的位置",
    "导航音量20%，音乐15%，始终开启导航语音优先打断",
    "午休时座椅放倒120°，空调26℃低风量，主驾车窗留1指缝",
    "上车蓝牙自动连常用耳机，播放收藏的轻音乐歌单",
    "周末喜欢到城市周边绿道骑行，返程恢复座椅通勤位置",
    "长途驾驶每小时开座椅腰部按摩，中档强度持续10分钟",
    "春秋季空调自动25℃，仅开通风，座椅通风低档运行",
    "热衷研究车载智能设备，调试后保存至车辆第3档记忆模式"
    "经常晚上导航到上海闵行平金中心1号楼，估计是家庭所在位置"
]
)

def main():
    # 测试agent对话中记忆生成
    _, model = create_client(ModelName.SEED_1_8_251228, AsyncArk)
    run_params = RunParams(
        model=model,
        params=ResponseParams(thinking={"type": "disabled"}),
    )
    system_prompt = SystemPrompt(
        role="你是车载助手，回复用户时保持极简极简极简极简。今天是2026年3月20日18时。",
        guidelines=[
            "周边搜索必须提供地址",
            "有明确导航意图并且有目的地时直接导航",
            "歌曲播放支持单首，歌单包含多首歌曲",
            "当用户询问歌单时，将歌曲整理成歌单",
            "最新歌曲或榜单指的是最近public_time",
            "联网检索时不做模糊POI检索、垂直领域（电商、本地生活攻略）",
            "打算调用工具前，请首先简要地回复用户打算做什么，再执行工具调用。",
            "打算调用工具前，请仔细思考用户是否提供了足够调用工具的信息。如缺失，请礼貌地询问用户。询问要简短，不要罗列工具细节",
        ],
    )
    # 真实用户画像测试
    for user_profile in [SINGLE_CAREER_WOMAN, RETIRED_SENIOR, STARTUP_YOUTH, FULL_TIME_MOM, BUSINESS_ELITE, custom_user_profile, test_profile]:
        print("\n" + "="*80)
        print(f"[red]测试画像: {user_profile.user_type}")
        agent_user_profile = AgentBase(system_prompt, run_params=run_params, tools=[], user_profile=user_profile)

        asyncio.run(test_agent_with_user_profile(agent_user_profile, QUERIES))


if __name__ == "__main__":
    main()