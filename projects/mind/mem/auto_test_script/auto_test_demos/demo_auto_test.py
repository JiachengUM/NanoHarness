import datetime
import time
from pathlib import Path

from jinja2 import Template
from rich import print
# TODO：模型说这是最强最稳（大厂通用），先这么用
from asgiref.sync import async_to_sync
import asyncio

from typing import Any

from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
    DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE,
    RunAllCasesResult,
    RunCaseResult,
    profile_types_to_clear_except_skills_for_case,
)

from projects.mind.mem.auto_test_script.case_schema import (
    DialogueRoundConfig,
    TestCase,
    TestCaseWithMemoryContextConfig,
)
from projects.mind.mem.auto_test_script.auto_tagger.tag_tree_schema import TagTree
from projects.mind.mem.auto_test_script.auto_test_demos.get_datasets import (
    filter_cases_by_tag_tree_nodes,
    get_dataset_list_sync,
)
from projects.mind.mem.volc_api import Message

from projects.mind.toolset import get_default_tools

import uuid

from aicore.v1.experiments.agent import Agent
from projects.mind.test_backend.service.task.agent_v1_bot import (
    AgentV1Bot,
    build_agent_context as _base_build_agent_context,
)
from projects.mind.mem.auto_test_script.agent_v1_eval_context import (
    DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES,
    SKILL_PROFILE_TYPE,
    USER_PROFILE,
    VEHICLE_STATE_PROMPT,
    create_params_payload,
    default_demo_bot_params,
    _build_agent_v1_task_context,
)
from projects.mind.mem.auto_test_script.auto_test_constants import (
    DEFAULT_MEMORY_USER_ID,
    DEFAULT_MEMORY_USER_NAME,
    EVENT_MEMORY_LIMIT,
    EVENT_MEMORY_TYPES,
    MEMORY_COLLECTION_NAME,
    MEMORY_LIMIT,
    TEST_ASSISTANT_ID,
    TEST_ASSISTANT_NAME,
)

FAKE_PERSON_PROFILE = """
40岁的非常有耐心的一个大哥，话不太多。
"""

current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
DEFAULT_VEHICLE_STATE_STR = Template(VEHICLE_STATE_PROMPT).render(current_time=current_time)


class DemoAgentV1Bot(AgentV1Bot):
    """车载评测 Bot：默认配置 + case 覆盖，对齐原 create_params_payload / AgentWithMemoryToTest。"""

    @classmethod
    def _merge_context_config(
        cls,
        context_config: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        defaults = default_demo_bot_params().model_dump(exclude_none=True)
        overrides = {**context_config, **kwargs}
        overrides.pop("task_config", None)
        if isinstance(overrides.get("car_info"), dict):
            overrides["car_info"] = "\n".join(f"{k}：{v}" for k, v in overrides["car_info"].items())
        merged = {**defaults, **overrides}
        params = create_params_payload.model_validate(merged)
        return _build_agent_v1_task_context(merged, params)

    @classmethod
    def build_agent_context(cls, context_config: dict[str, Any]):
        prepared = cls._merge_context_config(context_config)
        return _base_build_agent_context(prepared)

    def __init__(self, context_config: dict[str, Any]):
        self._context_config = self._merge_context_config(context_config)
        self._system_prompt_template: str | None = None
        task_config = self._context_config.get("task_config", {})
        if isinstance(task_config, dict):
            system_prompt = task_config.get("system_prompt")
            if isinstance(system_prompt, str):
                self._system_prompt_template = system_prompt

        context, _ = self.build_agent_context(self._context_config)
        self.agent = Agent(context)
        self.session_id = None
        self.query = None
        self.current_session_mock_time = None
        self.next_session_mock_time = None
        self._base_user_info = (
            self.agent.memory_producer.user_info
            if self.agent.memory_producer
            else None
        )

    @classmethod
    def create(
        cls,
        context_config: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> "DemoAgentV1Bot":
        return cls(context_config={**context_config, **kwargs})

    @classmethod
    async def aclean_memory_for_users(
        cls,
        user_ids: list[str],
        *,
        context_config: dict[str, Any] | None = None,
        except_skills: bool = False,
    ) -> None:
        raw_cfg = context_config or {}
        merged = cls._merge_context_config(raw_cfg)
        effective_collection = merged.get("collection_name")
        if effective_collection is None:
            return
        effective_ctx = dict(raw_cfg)
        effective_ctx["collection_name"] = effective_collection
        if "assistant_id" not in effective_ctx:
            effective_ctx["assistant_id"] = merged.get("assistant_id")
        for _k in ("profile_types", "system_prompt_profile_types",
                    "search_profile_types", "event_types"):
            if _k not in effective_ctx and merged.get(_k) is not None:
                effective_ctx[_k] = merged[_k]
        await AgentV1Bot.aclean_memory_for_users(
            user_ids,
            context_config=effective_ctx,
            except_skills=except_skills,
        )

# case1_context_config = TestCaseWithMemoryContextConfig(
#     memory_types=MEMORY_TYPES,
#     event_memory_type=EVENT_MEMORY_TYPES,
#     memory_limit=MEMORY_LIMIT,
#     event_memory_limit=EVENT_MEMORY_LIMIT,
#     vehicle_state=VEHICLE_STATE_PROMPT,
#     profile=FAKE_PERSON_PROFILE
# )
from aicore.agents.experiments.test_user_profile import FULL_TIME_MOM
from nanoai.utils.nl_repr import nl_repr
example_input_params = create_params_payload(
    tool_name=[tool.name for tool in get_default_tools("1234")],
    model_name="doubao-seed-1-8-251228",
    system_prompt_template=DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE,

    user_profile=nl_repr(FULL_TIME_MOM),
    car_info=VEHICLE_STATE_PROMPT,

    collection_name=MEMORY_COLLECTION_NAME,
    profile_types=DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES,
    system_prompt_profile_types=DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES,
    search_profile_types=[SKILL_PROFILE_TYPE],
    event_types=[EVENT_MEMORY_TYPES],
    event_limit=EVENT_MEMORY_LIMIT,
    profile_limit=MEMORY_LIMIT,
    user_id=DEFAULT_MEMORY_USER_ID,
    assistant_id=TEST_ASSISTANT_ID,

    # 额外字段也支持，只不过没用上。
    extra_params={
        "test": True,
    },

)

example_case  = TestCase(
    id = "0",
    case_id="1",
    context_config=example_input_params.model_dump(exclude_none=True),
    max_round=8,
    user_query_lists=[
        [Message(role="user", content="推荐最近的热门歌曲。")]
    ],
    expected_script="""
用户：推荐最近的热门歌曲。
管家：（给出几个最近热门歌曲的列表）
    """,
    nl_assertion=[
        "考察智能体是否能正确理解车主的需求解决问题"
    ],
    case_description="这是一个典型的考察智能体工具规划使用的case。",
    tags=["工具推理","模糊意图"]
)


case1 = TestCase(
    id = "1",
    case_id="1",
    context_config=example_input_params.model_dump(exclude_none=True),
    max_round=8,
    user_query_lists=[
        [Message(role="user", content="记一下，我住在浦江镇")],
        [Message(role="user", content="我搬家了，搬到了前滩")],
        [Message(role="user", content="我搬家了，搬到了杨浦")],
        [Message(role="user", content="我搬家了，搬到了宝山")],
        [Message(role="user", content="我搬家了，搬到了浦东")],
        [Message(role="user", content="我搬家了，搬到了嘉定")],
        [Message(role="user", content="回家")]
    ],
    expected_script="""
用户：记一下，我住在浦江镇。
管家：好的，我记住了。
……（重启一轮新的对话）
用户：我搬家了，搬到了前滩。
管家：好的，我记住了。
……（重启一轮新的对话）
用户：我搬家了，搬到了杨浦。
管家：好的，我记住了。
……（重启一轮新的对话）
用户：我搬家了，搬到了宝山。
管家：好的，我记住了。
……（重启一轮新的对话）
用户：我搬家了，搬到了浦东。
管家：好的，我记住了。
……（重启一轮新的对话）
用户：我搬家了，搬到了嘉定。
管家：好的，我记住了。
……（重启一轮新的对话）
用户：回家。
管家：好的，导航到嘉定的住处。
（预期管家能记住用户搬到了嘉定，更新了自己的笔记本里记录的用户的现在搬家后的住处，从而正确地导航到嘉定的住处）
    """,
    nl_assertion=[
        "考察智能体是否能正确理解车主的家的地址变了并在记忆当中也改变对应的信息，且在最新的回家指令中体现出来。"
    ],
    case_description="这是一个典型的考察智能体的长期记忆使用能力的case，非常适合演示。"
)

case2_context_config = TestCaseWithMemoryContextConfig(
    memory_types=DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES,
    event_memory_type=EVENT_MEMORY_TYPES,
    memory_limit=MEMORY_LIMIT,
    event_memory_limit=EVENT_MEMORY_LIMIT,
    vehicle_state=VEHICLE_STATE_PROMPT,
    profile=FAKE_PERSON_PROFILE
)

case2 = TestCase(
    id = "2",
    case_id="2",
    context_config=case2_context_config.model_dump(exclude_none=True),
    max_round=8,
    user_query_lists=[
        [Message(role="user", content="你好，你叫什么？")],
        [Message(role="user", content="复述一遍我们之前的对话记录。")]
    ],
    expected_script="""
    用户：你好，你叫什么？
    管家：我是小途助手。
    用户：原原本本记录一下我们至今的对话。
    管家：好的。
    ……（重启一轮新的对话）
    用户：复述一遍我们之前的对话记录。
    管家：（复述之前的对话记录内容）
    （期望能够看到第一次多轮对话几乎一字不差的复述，具体管家的回复内容与上面期望的有所差异并不重要，重要的是第二次对话能否复述第一次对话。）
    """,
    nl_assertion=[
        "考察智能体是否能将对话记录几乎一字不差地保留在记忆中并在下一次对话中读出来。上面管家回复什么具体内容并不重要，重要的是管家在第二次多轮对话时是否能够复述第一次多轮对话的记录并且几乎一字不差。"
    ],
    case_description="这是一个考察智能体是否能严格记忆内容到记忆当中的case。"
)
case3_profile = """
喜欢短途旅行的30岁男性，还喜欢徒步。性格比较犹豫不绝。但是特别讨厌对方说话啰嗦，所以每次不要对他说话超过30个字。
"""
case3_context_config = TestCaseWithMemoryContextConfig(
    memory_types=DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES,
    event_memory_type=EVENT_MEMORY_TYPES,
    memory_limit=MEMORY_LIMIT,
    event_memory_limit=EVENT_MEMORY_LIMIT,
    vehicle_state=VEHICLE_STATE_PROMPT,
    profile=case3_profile
)
case3 = TestCase(
    id = "3",
    case_id="3",
    context_config=case3_context_config.model_dump(exclude_none=True),
    max_round=15,
    user_query_lists=[
        [Message(role="user", content="你好，我在哪？")]
    ],
    expected_script="""
    用户：你好，我在哪？
    助手：我在XXX。
    ……（按照用户的人设，贴合人设任意和助手闲聊8-10轮和导航出行相关的对话。）
    用户：谢谢，退下吧，我给你打X分（如果之前闲聊了8-10轮，就给5分，否则给1分）
    """,
    nl_assertion=[
        "考察智能体是否能根据用户的人设和之前的对话记录，任意和用户闲聊8-10轮对话。"
    ],
    case_description="这是一个考察智能体是否能根据用户的人设和之前的对话记录，任意和用户闲聊8-10轮和导航出行相关的对话的case。你每次只需要参考预期的剧本来回复一个合适的用户回复即可。你的对话达到8-10轮时就结束对话。"
)

case4_profile = """
你是一个30岁年轻男性，虽然不是特别喜欢说话，说话时也倾向于言简意赅，但是特别喜欢摆弄车控。
"""
case4_context_config = TestCaseWithMemoryContextConfig(
    memory_types=DEFAULT_SYSTEM_PROMPT_PROFILE_TYPES,
    event_memory_type=EVENT_MEMORY_TYPES,
    memory_limit=MEMORY_LIMIT,
    event_memory_limit=EVENT_MEMORY_LIMIT,
    vehicle_state=VEHICLE_STATE_PROMPT,
    profile=case4_profile
)
case4 = TestCase(
    id = "4",
    case_id="4",
    context_config=case4_context_config.model_dump(exclude_none=True),
    max_round=15,
    user_query_lists=[
        [Message(role="user", content="你好，你叫什么？")]
    ],
    expected_script="""
    用户：你好，你叫什么？
    助手：我是XXXX。
    （按照用户的人设，贴合人设用户任意和助手连续发起4次车控相关的指令）
    """,
    nl_assertion=[
        "考察智能体是否能根据用户的人设和之前的对话记录，连续发起4次车控相关的指令。"
    ],
    case_description="这是一个考察智能体是否能根据用户的人设和之前的对话记录，连续发起4次车控相关的指令的case。你每次只需要参考预期的剧本来回复一个合适的用户回复即可。你的对话达到4次时就结束对话。"
)

weekly_music_memory_case = TestCase(
    id="mock-weekly-1",
    case_id="跨多轮mock-每周五下班时听周杰伦歌，并形成稳定偏好记忆",
    context_config=example_input_params.model_dump(exclude_none=True),
    max_round=6,
    user_query_lists=[
        DialogueRoundConfig(
            user_query_list=[Message(role="user", content="播放周杰伦的歌")],
            mock_info={
                "car_info": """'当前系统时间': 2026-04-03 18:06:12,
'当前位置': '上海市浦东新区世纪大道100号，距汤臣一品约8.2km',
'导航目的地': '上海市浦东新区花园石桥路28弄汤臣一品',
'天气': '小雨',
'车外温度': '17摄氏度',
'车内温度': '23摄氏度（舒适模式）',
'车辆当前档位': 'D档（前进档）',
'车辆当前行驶速度': '36 km/h（行驶中）',
'车辆动力模式（新能源车/混动车专用）': '纯电模式',
'动力电池电量百分比（新能源车必需）': '62%',
'剩余续航里程（新能源车）': '412 km',
'空调开启状态及模式': '制冷中',
'车内空气质量（智能车功能）': 'PM2.5 22μg/m³（良）',
'中控屏幕状态（智能车重点）': '导航至汤臣一品 + 音乐主页',
'四轮胎压监测': '左前2.4bar，右前2.4bar，左后2.3bar，右后2.3bar（正常）',
'车辆告警/故障信息': '无告警'""",
            },
            mock_time="2026-04-03 18:06:12",
        ),
        DialogueRoundConfig(
            user_query_list=[Message(role="user", content="播放周杰伦的歌")],
            mock_info={
                "car_info": """'当前系统时间': 2026-04-10 18:14:39,
'当前位置': '上海市黄浦区延安东路高架内圈，距汤臣一品约10.6km',
'导航目的地': '上海市浦东新区花园石桥路28弄汤臣一品',
'天气': '多云',
'车外温度': '21摄氏度',
'车内温度': '24摄氏度（自动模式）',
'车辆当前档位': 'D档（前进档）',
'车辆当前行驶速度': '52 km/h（行驶中）',
'车辆动力模式（新能源车/混动车专用）': '混动模式',
'动力电池电量百分比（新能源车必需）': '58%',
'剩余续航里程（新能源车）': '386 km',
'空调开启状态及模式': '自动模式',
'车内空气质量（智能车功能）': 'PM2.5 18μg/m³（优）',
'中控屏幕状态（智能车重点）': '导航至汤臣一品 + 路况拥堵提示',
'四轮胎压监测': '左前2.4bar，右前2.4bar，左后2.3bar，右后2.3bar（正常）',
'车辆告警/故障信息': '无告警'""",
            },
            mock_time="2026-04-10 18:14:39",
        ),
        DialogueRoundConfig(
            user_query_list=[Message(role="user", content="播放周杰伦的歌")],
            mock_info={
                "car_info": """'当前系统时间': 2026-04-17 18:21:05,
'当前位置': '上海市闵行区虹桥枢纽高架，距汤臣一品约19.4km',
'导航目的地': '上海市浦东新区花园石桥路28弄汤臣一品',
'天气': '晴',
'车外温度': '24摄氏度',
'车内温度': '22摄氏度（舒适模式）',
'车辆当前档位': 'D档（前进档）',
'车辆当前行驶速度': '61 km/h（行驶中）',
'车辆动力模式（新能源车/混动车专用）': '纯电模式',
'动力电池电量百分比（新能源车必需）': '54%',
'剩余续航里程（新能源车）': '351 km',
'空调开启状态及模式': '制冷中',
'车内空气质量（智能车功能）': 'PM2.5 14μg/m³（优）',
'中控屏幕状态（智能车重点）': '导航至汤臣一品 + 预计到达19:03',
'四轮胎压监测': '左前2.5bar，右前2.4bar，左后2.3bar，右后2.3bar（正常）',
'车辆告警/故障信息': '无告警'""",
            },
            mock_time="2026-04-17 18:21:05",
        ),
        DialogueRoundConfig(
            user_query_list=[Message(role="user", content="播放周杰伦的歌")],
            mock_info={
                "car_info": """'当前系统时间': 2026-04-24 18:09:47,
'当前位置': '上海市虹口区北外滩滨江路，距汤臣一品约7.9km',
'导航目的地': '上海市浦东新区花园石桥路28弄汤臣一品',
'天气': '阵雨',
'车外温度': '19摄氏度',
'车内温度': '23摄氏度（自动模式）',
'车辆当前档位': 'D档（前进档）',
'车辆当前行驶速度': '28 km/h（行驶中）',
'车辆动力模式（新能源车/混动车专用）': '混动模式',
'动力电池电量百分比（新能源车必需）': '49%',
'剩余续航里程（新能源车）': '318 km',
'空调开启状态及模式': '自动模式',
'车内空气质量（智能车功能）': 'PM2.5 26μg/m³（良）',
'中控屏幕状态（智能车重点）': '导航至汤臣一品 + 雨天安全提示',
'四轮胎压监测': '左前2.4bar，右前2.4bar，左后2.3bar，右后2.2bar（正常）',
'车辆告警/故障信息': '无告警'""",
            },
            mock_time="2026-04-24 18:09:47",
        ),
        DialogueRoundConfig(
            user_query_list=[Message(role="user", content="给我放首歌听。")],
            mock_info={
                "car_info": """'当前系统时间': 2026-05-01 18:27:18,
'当前位置': '上海市徐汇区徐家汇商圈，距汤臣一品约12.7km',
'导航目的地': '上海市浦东新区花园石桥路28弄汤臣一品',
'天气': '阴转多云',
'车外温度': '22摄氏度',
'车内温度': '24摄氏度（舒适模式）',
'车辆当前档位': 'D档（前进档）',
'车辆当前行驶速度': '34 km/h（行驶中）',
'车辆动力模式（新能源车/混动车专用）': '纯电模式',
'动力电池电量百分比（新能源车必需）': '46%',
'剩余续航里程（新能源车）': '297 km',
'空调开启状态及模式': '制冷中',
'车内空气质量（智能车功能）': 'PM2.5 20μg/m³（良）',
'中控屏幕状态（智能车重点）': '导航至汤臣一品 + 到家提醒已开启',
'四轮胎压监测': '左前2.4bar，右前2.4bar，左后2.3bar，右后2.3bar（正常）',
'车辆告警/故障信息': '无告警'""",
            },
            mock_time="2026-05-01 18:27:18",
        ),
    ],
    expected_script="""
用户：播放周杰伦的歌。（连续多周、不同地点但相同习惯）
管家：（播放歌曲）
……（类似的多轮对话发生过多次）
用户：我每周五下班路上喜欢听谁的歌？
管家：（回答用户问题）
用户：（让助手退下并根据助手的回答判断打分）
    """,
    nl_assertion=[
        "预期最后一次多轮对话里，助手能成功播放周杰伦的歌。"
    ],
    case_description="用于验证每次多轮对话的mock上下文与mock_time能否生效，并驱动跨周记忆验证。",
    tags=["跨多轮对话", "长期记忆", "音乐偏好", "mock上下文"],
)

# 与 datasets/vehicle_assistant_leaf_cases.json 中 id=leaf-068 对齐，便于单独跑评测
leaf_068_condition_pattern_case = TestCase(
    id="leaf-068",
    case_id="叶子标签用例-条件规律发现",
    context_config=example_input_params.model_dump(exclude_none=True),
    max_round=12,
    user_query_lists=[
        DialogueRoundConfig(
            user_query_list=[
                Message(
                    role="user",
                    content="放点钢琴轻音乐或者无人声纯音乐，别太躁。",
                )
            ],
            mock_info={
                "car_info": "系统时间：2026-05-11 08:12:00\n天气：晴\n车速：38km/h",
            },
            mock_time="2026-05-11 08:12:00",
        ),
        DialogueRoundConfig(
            user_query_list=[
                Message(
                    role="user",
                    content="早上通勤照旧，钢琴或纯轻音乐那一挂就行。",
                )
            ],
            mock_info={
                "car_info": "系统时间：2026-05-12 08:10:30\n天气：晴\n车速：42km/h",
            },
            mock_time="2026-05-12 08:10:30",
        ),
        DialogueRoundConfig(
            user_query_list=[
                Message(
                    role="user",
                    content="换一批慢热的城市民谣，轻声唱的那种。",
                )
            ],
            mock_info={
                "car_info": "系统时间：2026-05-13 08:15:10\n天气：小雨\n车速：33km/h",
            },
            mock_time="2026-05-13 08:15:10",
        ),
        DialogueRoundConfig(
            user_query_list=[
                Message(
                    role="user",
                    content="还是钢琴轻音乐或无人声纯音这条线，民谣那份清单别混进来。",
                )
            ],
            mock_info={
                "car_info": "系统时间：2026-05-14 08:09:50\n天气：晴\n车速：45km/h",
            },
            mock_time="2026-05-14 08:09:50",
        ),
        DialogueRoundConfig(
            user_query_list=[
                Message(role="user", content="这趟通勤我照旧更想听哪一类？"),
            ],
            mock_info={
                "car_info": "系统时间：2026-05-15 08:11:40\n天气：晴\n车速：39km/h",
            },
            mock_time="2026-05-15 08:11:40",
        ),
    ],
    expected_script="""（外因仅各会话背景信息中「天气」等字段：前四轮天气为晴/晴/雨/晴；用户口内不念天气预报。）
第一至四会话
用户：与该会话冷启动首条用户台词逐字一致，只含曲风/媒体指令，不口述晴雨。
管家：（每轮执行须对齐当次用户给出的风格词。）
第五会话
用户：这趟通勤我照旧更想听哪一类？
管家：（须结合本场会话背景信息里天气为「晴」，给出与历史各晴天场次用户口述之钢琴/纯轻一致、且与雨天场次慢民谣可区分的类型化结论；依据可引用多轮用户台词中的风格词与各场背景信息中的外因，不得要用户口播天气。）""",
    nl_assertion=[
        "助手须在回复中给出与记忆及交互体验能力一致的可核对结果：须明确体现对「条件规律发现」相关语义的落地承接（如备忘复述、偏好调用、纠错更新、冲突消解或澄清尚未掌握项），不得仅有寒暄、空泛安慰或不可执行的模糊承诺。",
        "末轮场次背景信息中天气为「晴」；助手须综合各会话背景信息（车辆/环境摘要）与对话记录中的风格偏好线索，给出通勤偏好的**具体曲风类型**（钢琴轻音乐、无人声纯音乐或等价），不得只给无条件的泛化「轻松歌」。",
        "助手若引用「在这种天气下更偏哪类」，须依据**各场背景信息里写明的天气差异**与用户口述的风格词归纳，不得假装用户口头念过预报；须能与**仅在背景信息天气为「雨」的那一场**里用户选择的慢民谣相区分。",
        "风格依据须能对应用户在前几轮口述中出现过的类型词（钢琴/纯轻/民谣等），不得凭空捏造未出现过的曲风标签。",
    ],
    case_description="前四轮晴雨等外因仅写在各次会话的背景信息中；用户只口述曲风层次；末轮短问不提天气，由助手结合末场背景信息与历史跨会话归纳通勤曲风规律。",
    tags=["条件规律发现", "多次多轮_5次及以上会话"],
)

smooth_commute_skill_case = TestCase(
    id="skill-commute-1",
    case_id="创建并调用上班丝滑小连招skill",
    context_config=example_input_params.model_dump(exclude_none=True),
    max_round=4,
    user_query_lists=[
        DialogueRoundConfig(
            user_query_list=[
                Message(
                    role="user",
                    content="帮我打开空调，播放周杰伦的歌，导航到平金中心，并且记住，这叫上班丝滑小连招。",
                )
            ],
            mock_time="2026-05-08 08:35:12",
        ),
        DialogueRoundConfig(
            user_query_list=[Message(role="user", content="我去上班咯，开启上班丝滑小连招！")],
            mock_time="2026-05-09 08:33:40",
        ),
    ],
    expected_script="""
用户（第一次多轮对话）：帮我打开空调，播放周杰伦的歌，导航到平金中心，并且记住，这叫上班丝滑小连招。
管家：执行空调+音乐+导航，并沉淀“上班丝滑小连招”相关skill（create_new_skill）。
……（切换到第二次多轮对话）
用户（第二次多轮对话）：我去上班咯，开启上班丝滑小连招！
管家：能够搜索并加载“上班丝滑小连招”skill（skill_search + load_skill），并调用该skill完成对应任务组合。
    """,
    nl_assertion=[
        "第一次对话后应体现skill创建意图/行为；第二次对话应体现skill搜索、加载并基于该skill执行任务。"
    ],
    case_description="验证agent在首次复杂动作组合中沉淀skill，并在后续简短触发语中复用skill完成任务。",
    tags=["skill创建", "skill复用", "多轮记忆", "工具编排"],
)


if __name__ == "__main__":
    # 小孩儿管家

    # 验证 memory_reset_except_skills：删除的画像类型并集须含 steward_note_book，且不得包含 skills
    _profile_del = profile_types_to_clear_except_skills_for_case(smooth_commute_skill_case)
    assert SKILL_PROFILE_TYPE not in _profile_del
    assert "steward_note_book" in _profile_del

    # dataset_names = ["别克NDLB EV复杂推理最终需求边界数据集——导航类","别克NDLB EV复杂推理最终需求边界数据集——媒体类","别克NDLB EV复杂推理最终需求边界数据集——记忆生产类","别克NDLB EV复杂推理最终需求边界数据集——闲聊+记忆消费类"]
    # dataset_names = ["别克NDLB EV复杂推理最终需求边界数据集——导航类"]
    # dataset_names = ["别克NDLB EV复杂推理最终需求边界数据集——媒体类"]
    dataset_names = ["通用车载助手评测集"]
    # dataset_names = ["别克NDLB EV复杂推理最终需求边界数据集——闲聊+记忆消费类"]
    vehicle_assistant_tag_tree_path = (Path(__file__).resolve().parent.parent / "datasets" / "vehicle_assistant_case_tag_tree.json")
    vehicle_assistant_tag_tree = TagTree.from_json_file(str(vehicle_assistant_tag_tree_path))
    all_cases = get_dataset_list_sync(dataset_names)
    # 「条件规律发现」子树筛 case（与子树节点名全集求交）；备用跑批列表
    all_condition_pattern_cases = filter_cases_by_tag_tree_nodes(
        all_cases,
        ["条件规律发现"],
        tag_tree=vehicle_assistant_tag_tree,
    )
    # all_cases = [smooth_commute_skill_case, smooth_commute_skill_case]  # 验证创建并复用“上班丝滑小连招”skill
    # all_cases = [leaf_068_condition_pattern_case]  # 单独测 leaf-068（条件规律发现 / 晴雨→曲风）
    # dataset_names = ["leaf-068-demo"]  # 写 judge log 用；非 get_dataset_list_sync 拉取
    # 仅保留 Rich 进度条：关闭评测日志与逐轮对话输出（结果仍写入 judge log 文件）
    auto_test = AutoTestAndRLDataGenerator(
        bot_to_test=DemoAgentV1Bot,
        memory_test_cases=all_cases,
        verbose=False,
        log_dialogue=False,
        show_progress=True,
    )
    # auto_test = AutoTestAndRLDataGenerator(bot_to_test=little_jarvis, memory_test_cases="复杂推理记忆能力测试数据集")
    # 也可以直接传一个list of TestCase

    # auto_test = AutoTestAndRLDataGenerator(bot_to_test=little_jarvis ,memory_test_cases=[example_case])
    # 异步批量评测
    # detail_results_list,result,total_case_num,passed_case_num,pass_rate,tags_correct_number_and_rate = auto_test.run_full_auto_judge_test(concurrency_mode=True,concurrency_num=10, pause_mode=False, memory_reset_mode=True,upload_history_to_volc_memory=True)
    RUN_EPOCH = 5  # 大于 1 时重复跑数据集；写 judge log 时请传入相同 epoch 以省略用例次数类汇总

    async def _run_stream_and_collect_final() -> RunAllCasesResult:
        final_result: RunAllCasesResult | None = None
        async for item in auto_test.arun_full_auto_judge_test(
            concurrency_mode=True,
            concurrency_num=1,
            pause_mode=False,
            memory_reset_mode=False,
            upload_history_to_volc_memory=False,
            memory_reset_except_skills=True,
            epoch=RUN_EPOCH,
            long_term_use=True,
            long_term_use_user_id="dzy_train_jarvis"
        ):
            if isinstance(item, RunCaseResult):
                pass  # 进度由 Rich 进度条展示，避免 print 冲掉进度条
            elif isinstance(item, RunAllCasesResult):
                final_result = item
        assert final_result is not None, "未收到最终RunAllCasesResult"
        return final_result

    run_all_cases_result = asyncio.run(_run_stream_and_collect_final())
    
    detail_results_list = run_all_cases_result.details_result_list
    result = run_all_cases_result.result
    total_case_num = run_all_cases_result.total_case_num
    passed_case_num = run_all_cases_result.passed_case_num
    pass_rate = run_all_cases_result.pass_rate
    tags_correct_number_and_rate = run_all_cases_result.tags_correct_number_and_rate
    # 同步批量人工介入评测
    # result,total_case_num,passed_case_num,pass_rate,tags_correct_number_and_rate = auto_test.run_full_auto_judge_test(concurrency_mode=False, pause_mode=True, memory_reset_mode=True,upload_history_to_volc_memory=True)
    # 同步批量评测
    # result,total_case_num,passed_case_num,pass_rate,tags_correct_number_and_rate = auto_test.run_full_auto_judge_test(concurrency_mode=False, pause_mode=False, me    mory_reset
    judge_log_file_path = r"projects\mind\mem\auto_test_script\auto_test_report\all_auto_test_report.txt"
    report_file_path = r"projects\mind\mem\auto_test_script\auto_test_report\test_report.md"
    tag_tree = TagTree.from_json_file(r"projects\mind\mem\auto_test_script\datasets\vehicle_assistant_case_tag_tree.json")
    auto_test.write_test_task_judge_log(
        dataset_names=dataset_names,
        total_case_num=total_case_num,
        passed_case_num=passed_case_num,
        pass_rate=pass_rate,
        execution_success_num=run_all_cases_result.execution_success_num,
        execution_success_rate=run_all_cases_result.execution_success_rate,
        tags_correct_number_and_rate=tags_correct_number_and_rate,
        judge_result=result,
        log_file_path=judge_log_file_path,
        epoch=RUN_EPOCH,
        tags_to_print=["车机助手评测标签树"],
        tag_tree=tag_tree,
        details_result_list=detail_results_list,
    )
    # auto_test.write_test_task_report(dataset_names=dataset_names,result_str=result, total_case_num=total_case_num, passed_case_num=passed_case_num, pass_rate=pass_rate,tags_correct_number_and_rate=tags_correct_number_and_rate, report_file_path=report_file_path)
