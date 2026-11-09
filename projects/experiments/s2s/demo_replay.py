from __future__ import annotations

from projects.experiments.s2s.tts_client import TextTurn, build_audio_file_list
from projects.experiments.s2s.s2s_tui_agent_app_main import build_v2_runner_bundle, run_tui

# V2 Agent: 实时对话驱动的异步任务执行，用户对话 & agent思考 & 任务执行 完全解耦独立
# 1. 实时对话驱动的异步任务执行：任务由独立 runner 后台执行，主对话不被工具阻塞；例如天气先返回就先答，POI 稍后返回再补答。
# 2. 主对话、agent 思考、任务执行解耦：语音链路、agent 规划、任务执行分别运行；用户可在长任务中打断、插话、追问或插入新任务。
# 3. 任务状态与结果可回灌：任务生命周期可展示，结果可重新送回 agent；例如 POI 返回后，助手结合用户后续补充继续组织回复。
# 4. 初步具备任务管理雏形：支持表达任务查询、部分结果追问、条件补充等语义；未来可扩展为取消、修改、订阅进度等完整任务管理能力。


DEMO_CASES: dict[str, list[TextTurn]] = {
    # 实时对话异步任务：用户提出多个需求，agent产出任务异步执行，任务分别返回，agent分别回复
    "CASE1_实时对话异步任务": [
        TextTurn("推荐一家上海市徐汇西岸凤巢附近的咖啡店，查一下上海的天气"),
    ],
    # 临时插入新需求：用户在前一个任务执行过程中提出新需求，前一个任务不会丢失，新任务也会被接收和处理。
    "CASE2_多轮问答插话": [
        TextTurn("推荐一家上海市徐汇西岸凤巢附近的咖啡店，评分4分以上，人均20左右"),
        TextTurn("推荐一首王菲最新的单曲"),
    ],
    # 多任务追问：用户在一句话中提出多个需求，助手可以拆分成多个任务并分别执行，并可以对部分完成的任务提前追问。
    "CASE3_多任务追问": [
        TextTurn("上海今天的天气怎么样，找一家上海徐汇区西岸凤巢附近的咖啡店，再推荐一首张学友最新的歌曲",),
        TextTurn("我需要带伞吗？"),
    ],
    # 任务查询：可以查询某个任务是否完成，助手会结合当前任务状态继续回答。
    "CASE4_任务查询": [
        TextTurn("找一家上海徐汇区西岸凤巢附近的咖啡店，然后查一下天气",),
        TextTurn("咖啡店找到了吗"),
    ],
    # 长对话记忆：在多轮连续对话中，助手可以承接历史结果、处理新需求，并在最后进行综合总结。
    "CASE5_FreeStyle": [
        TextTurn("请查一下上海今天的天气", ),
        TextTurn("那我需要带伞吗？", ),
        TextTurn("推荐一首王菲的最新单曲", ),
        TextTurn("这首歌适合下雨天听吗？", ),
        TextTurn("你刚才查天气了吗，查完了吗？", ),
        TextTurn("换个话题，你简单介绍一下你能做什么", ),
        TextTurn("再推荐一家上海徐家汇美罗城附近的咖啡馆，人均30",),
        TextTurn("最后总结一下刚才聊过的所有事情", ),
    ],
    "CASE6_Cancel": [
        TextTurn("推荐一家上海西岸凤巢附近可以边听歌边喝下午茶的咖啡馆", ),
        TextTurn("取消任务", delay=3.0),
    ],
    # 模拟任务失败的CASE
    "CASE6_快速意图": [
        TextTurn("查一下上海今天的天气"),
    ],
    # 模拟任务失败的CASE
    "CASE6_任务失败_POI地址无法解析": [
        TextTurn("查一下上海今天的天气，同时找一家火星奥林匹斯山主峰附近的咖啡店，再推荐一首张学友的经典歌"),
        TextTurn("不用找咖啡馆了", delay=3.0),
    ],
    "CASE_任务取消_全部取消": [
        TextTurn("请查香港今天的天气，再找一家上海徐家汇酒店"),
        TextTurn("都取消，然后查一下上海明天的天气", delay=3.0),
    ],
    # 以下是不同工具的CASE设计，和上述场景重复
    "多轮问答-歌曲": [
        TextTurn("推荐一首张学友的经典歌曲", delay=5.0),
        TextTurn("再推荐一首王菲最新的歌", ),
        TextTurn("刚刚推荐的几首歌，哪首适合下雨天听", ),
    ],
    "多轮问答-3": [
        TextTurn("请查一下香港今天的天气", delay=5.0),
        TextTurn("明天天气怎么样", ),
        TextTurn("后天呢", ),
    ],
    "意图切换-1": [
        TextTurn("推荐一首张学友的经典歌曲", delay=2.0),
        TextTurn("来首王菲的吧", delay=0.8),
    ],
    "意图切换-2": [
        TextTurn("请查一下香港今天的天气", delay=2.0),
        TextTurn("那我需要带伞吗", delay=0.9),
    ],
}

ACTIVE_CASE_NAME = "CASE1_实时对话异步任务"
ACTIVE_CASE_NAME = "CASE2_多轮问答插话"
ACTIVE_CASE_NAME = "CASE3_多任务追问"
ACTIVE_CASE_NAME = "CASE4_任务查询"
ACTIVE_CASE_NAME = "CASE5_FreeStyle"
ACTIVE_CASE_NAME = "CASE_任务取消_全部取消"


TEXT_TURNS = DEMO_CASES[ACTIVE_CASE_NAME]
AUDIO_GAIN = 0.5
S2S_AUDIO_GAIN = 1


def main() -> None:
    audio_file_list = build_audio_file_list(TEXT_TURNS, audio_gain=AUDIO_GAIN)
    run_tui(
        build_v2_runner_bundle,
        "space_gate",
        audio_file_list=audio_file_list,
        audio_file_playback_mode="manual",  # 回车或者n键，播放下一条语音
        s2s_audio_gain=S2S_AUDIO_GAIN,
    )


if __name__ == "__main__":
    main()
