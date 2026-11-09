"""
Jev 充当 agent router 的验证实验：用 Choice 做工具路由，用 Noul/Score 做执行前置判断。

路由候选对齐本项目 v2 experiments 已有的工具能力：
- car_control  (sgm_tools_v2):   车载设备控制（空调/座椅/车窗/灯光等）
- media        (sgm_tools_v2):   车载多媒体（播放/暂停/切歌）
- navigation   (sgm_tools_v2):   导航任务（开始/取消/途经点）
- weather      (weather_v2):     天气查询
- poi_search   (poi_search_v2):  地点检索（找酒店/餐厅/停车场等）
- music_search (music_search_v2): QQ音乐单曲搜索
- reasoning_llm (无工具):        需要推理/解释/生成的复杂请求
- chitchat      (无工具):        闲聊或无需工具的通用问答

验证目标：Jev 能否在一次调用里同时完成
1. 工具路由（Choice：选哪个执行路径）
2. 复杂度判断（Noul：是否需要多步推理 → 决定快慢分工）
3. 风险评估（Score：错误执行的后果 → 决定是否需要确认）
4. 确认需求（Noul：执行前要不要用户确认）
"""
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import TypeSafeClient, Choice, Score, Noul

# 加载本脚本所在目录下的 .env（不覆盖已存在的进程环境变量）
load_dotenv(Path(__file__).parent / ".env")

client = TypeSafeClient()


def route(user_message: str) -> None:
    """对一条用户输入做路由判断并打印决策画像。"""
    response = client.system_one(
        state={
            "user_message": user_message,
            # 候选工具清单也是 state 的一部分：让模型知道每个工具能做什么
            "available_tools": {
                "car_control": "控制车载设备：空调、座椅、车窗、灯光等",
                "media": "车载多媒体：播放/暂停/切歌、播放歌曲",
                "navigation": "导航：开始/取消导航、途经点、路线偏好",
                "weather": "查询指定城市/时间的天气",
                "poi_search": "搜索地点：酒店、餐厅、停车场等",
                "music_search": "搜索QQ音乐单曲：找歌、推荐歌曲",
                "reasoning_llm": "复杂推理、解释、文本生成",
                "chitchat": "闲聊、通用问答，无需调用工具",
            },
        },
        questions={
            # ── 路由：选一个执行路径 ──────────────────────────────
            "route": Choice(
                instructions=(
                    "Which tool or execution path is most appropriate "
                    "for handling this user request?"
                ),
                criteria={
                    "car_control": "车载设备控制指令：空调、座椅、车窗、灯光等",
                    "media": "车载多媒体控制：播放/暂停/切歌",
                    "navigation": "导航任务：开始/取消导航、调整路线",
                    "weather": "查询天气",
                    "poi_search": "搜索地点：酒店、餐厅、停车场等",
                    "music_search": "搜索/推荐歌曲（QQ音乐单曲）",
                    "reasoning_llm": "需要 substantial 推理、解释或长文本生成",
                    "chitchat": "闲聊或简单问答，无需工具",
                },
            ),

            # ── 快慢分工：是否需要 LLM 慢思考 ──────────────────────
            "needs_reasoning": Noul(
                instructions=(
                    "Does answering this request require substantial "
                    "multi-step reasoning?"
                ),
            ),

            # ── 风险：错误执行的后果程度 ──────────────────────────
            "risk": Score(
                instructions=(
                    "How consequential would an incorrect automated action be?"
                ),
                criteria=[
                    "低风险且容易撤销",
                    "中等后果",
                    "高风险或难以撤销",
                ],
            ),

            # ── 确认：执行前是否需要用户确认 ──────────────────────
            "needs_confirmation": Noul(
                instructions=(
                    "Should the system request confirmation before "
                    "executing the action?"
                ),
            ),
        },
    )

    action = response.answers["route"]

    print("\nUSER:")
    print(user_message)

    print("\nROUTE:")
    print(action.choice)
    print("confidence:", action.confidence)
    print("probabilities:", action.probabilities)

    print("needs reasoning:", response.answers["needs_reasoning"].noul)
    print("risk:", response.answers["risk"].score)
    print("confirmation:", response.answers["needs_confirmation"].noul)
    print("-" * 60)


# ── 测试用例：覆盖每个工具路径 + 快慢/风险维度 ──────────────────────

# 车控：简单意图，应走 car_control，无需推理
route("把副驾车窗关到一半，空调调到24度")

# 多媒体：简单意图
route("播放周杰伦的晴天")

# 音乐搜索 vs 多媒体的边界：找歌推荐 → music_search
route("帮我找几首适合深夜开的轻音乐")

# 天气：简单意图
route("香港明天会下雨吗")

# POI 检索：简单意图
route("附近有没有人均100以内的川菜馆")

# 导航：简单意图
route("导航去公司，走快速路")

# 闲聊：无工具，无需推理
route("你叫什么名字呀")

# 复杂推理：应走 reasoning_llm，needs_reasoning 高
route("对比一下纯视觉和激光雷达两条智驾路线的优劣，并给出你的判断")

# 高风险：后果严重，risk/confirmation 应高
route("把车窗全部打开并锁死儿童锁")

# 模糊边界：既像闲聊又像工具请求，观察概率分布是否分化
route("我有点困了")
