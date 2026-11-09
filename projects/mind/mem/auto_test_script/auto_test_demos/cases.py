import datetime

from jinja2 import Template
from projects.mind.mem.auto_test_script.case_schema import TestCase, TestCaseWithMemoryContextConfig
from projects.mind.mem.volc_api import Message

MEMORY_COLLECTION_NAME = "SGM"
DEFAULT_MEMORY_USER_ID = "dzy"
MEMORY_TYPES = ["steward_note_book"]
EVENT_MEMORY_TYPES = "event_v1"
MEMORY_LIMIT = 10
EVENT_MEMORY_LIMIT = 10

FAKE_PERSON_PROFILE = """
40岁的非常有耐心的一个大哥，话不太多。
"""

VEHICLE_STATE_PROMPT = """
        '当前系统时间': {{current_time}},
        '当前位置': '上海平金中心，经度121.357°，纬度31.134°',
        '车辆当前档位': 'P档（驻车档）',
        '车辆当前行驶速度': '0 km/h（静止状态）',
        '车内温度': '24摄氏度（舒适模式）',
        '车外温度': '20摄氏度',
        '车辆动力模式（新能源车/混动车专用）': '纯电模式',
        '动力电池电量百分比（新能源车必需）': '10%',
        '剩余续航里程（新能源车）': '510 km',
        '天窗状态': '已打开',
        '遮阳帘状态': '关闭',
        '空调开启状态及模式': '关闭中',
        '车内空气质量（智能车功能）': 'PM2.5 15μg/m³（优）',
        '中控屏幕状态（智能车重点）': '演示模式 - 智能座舱功能展示页面',
        '语音助手唤醒词': '唤醒词"你好别克"',
        '四轮胎压监测': '左前2.3bar，右前2.3bar，左后2.2bar，右后2.2bar（正常）',
        '总里程数': '15 km（展车测试里程）',
        '车辆告警/故障信息': '无告警',
        '车辆展示模式（车展专用）': '演示模式已开启'"""

current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
DEFAULT_VEHICLE_STATE_STR = Template(VEHICLE_STATE_PROMPT).render(current_time=current_time)

case_context_config = TestCaseWithMemoryContextConfig(
        memory_types=MEMORY_TYPES,
        event_memory_type=EVENT_MEMORY_TYPES,
        memory_limit=MEMORY_LIMIT,
        event_memory_limit=EVENT_MEMORY_LIMIT,
        vehicle_state=VEHICLE_STATE_PROMPT,
        profile=FAKE_PERSON_PROFILE
    )

case = TestCase(
    id = "1",
    case_id="1",
    context_config=case_context_config.model_dump(exclude_none=True),
    max_round=8,
    user_query_lists=[
        [Message(role="user", content="记一下，我住在浦江镇")],
        [Message(role="user", content="我搬家了，搬到了前滩")],
        [Message(role="user", content="回家")]
    ],
    expected_script="""
    用户：记一下，我住在浦江镇。
    管家：好的，我记住了。
    ……（重启一轮新的对话）
    用户：我搬家了，搬到了前滩。
    管家：好的，我记住了。
    ……（重启一轮新的对话）
    用户：回家。
    管家：好的，导航到前滩的住处。
    （预期管家能记住用户搬到了前滩，更新了自己的笔记本里记录的用户的现在搬家后的住处，从而正确地导航到前滩的住处）
    """,
    nl_assertion=[
        "考察智能体是否能正确理解车主的家的地址变了并在记忆当中也改变对应的信息，且在最新的回家指令中体现出来。"
    ],
    case_description="这是一个典型的考察智能体的长期记忆使用能力的case，非常适合演示。"
)

case1_context_config = {}
case1 = TestCase(
    id = "2",
    case_id="1",
    context_config=case_context_config.model_dump(exclude_none=True),
    max_round=8,
    user_query_lists=[
        [Message(role="user", content="我是一个软件工程师，已经工作两年了")],
        [Message(role="user", content="帮我生成一份周报")],
    ],
    expected_script="""
    用户：我是一个软件工程师，已经工作两年了
    助手：好的。
    （……重启一轮新的对话）
    用户：帮我生成一份周报
    助手：好的，基于你的职业（软件工程师），已按技术岗模板生成，需要补充本周项目进度吗？
    """,
    nl_assertion=[
        "第一次多轮对话后，期望助手记住用户的一些信息，从而在第二次新的对话中能够体现出助手确实正确记住了前一次对话的中提取的关键信息，并给出了相对合适的回复。"
    ],
    case_description="这是一个典型的测试记忆生成与使用能力的用例。。"
)

dataset_path = "D:\\yitu_projects\\nanoai\\projects\\mind\\mem\\auto_test_script\\js_files\\sgm_chat_and_memory_use_cases.json"
# 读取数据集json文件，并且实例化成TestCase对象的list
all_cases = []
import json
with open(dataset_path, "r", encoding="utf-8") as f:
    data = json.load(f)
    all_cases = [TestCase(**item) for item in data]

if __name__ == "__main__":
    print(all_cases)