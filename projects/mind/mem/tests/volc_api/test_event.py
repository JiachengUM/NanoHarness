from rich import print

from projects.mind.mem.volc_api.event import (
    EventTypeSchema,
    EventProperty,
    ProfileAndPrimaryKey,
    batch_delete_event,
    search_event_memory,
    add_custom_event_memory,
)
from projects.mind.mem.volc_api.base import CollectionID
from projects.mind.mem.volc_api.sys_event_v1 import sys_event_v1_dict

__all__ = [
    "sys_event_v1",
    "event_english_study",
    "event_cabin_user_boarding",
    "event_cabin_user_leaving",
    "event_cabin_navigation_start",
    "event_cabin_voice_command",
]

sys_event_v1 = EventTypeSchema(**sys_event_v1_dict)

event_english_study = EventTypeSchema(
    EventType="english_study",
    Description="记录一次英语学习会话中助教与学生的问答及评分",
    Properties=[
        EventProperty(
            PropertyName="knowledge_point_name",
            PropertyValueType="string",
            Description="当前对话涉及的知识点名称",
        ),
        EventProperty(
            PropertyName="question",
            PropertyValueType="string",
            Description="助教提出的问题",
        ),
        EventProperty(
            PropertyName="answer",
            PropertyValueType="string",
            Description="学生的回答",
        ),
        EventProperty(
            PropertyName="rating_score",
            PropertyValueType="int64",
            Description="对学生回答的数值评分",
        ),
        EventProperty(
            PropertyName="fluency_score",
            PropertyValueType="int64",
            Description="口语流利度评分 (1-5)",
        ),
    ],
    Version="2",
)

event_cabin_user_boarding = EventTypeSchema(
    EventType="cabin_user_boarding",
    Description="用户上车事件，智能体可根据此事件检查空调、座椅等设置是否符合用户习惯",
    Properties=[
        EventProperty(
            PropertyName="user_id",
            PropertyValueType="string",
            Description="用户唯一标识",
        ),
        EventProperty(
            PropertyName="seat_position",
            PropertyValueType="string",
            Description="用户座位位置，如 'driver', 'front_passenger', 'rear_left' 等",
        ),
        EventProperty(
            PropertyName="boarding_time",
            PropertyValueType="string",
            Description="上车时间",
        ),
        EventProperty(
            PropertyName="weather_condition",
            PropertyValueType="string",
            Description="当前天气状况，如 '晴天', '雨天', '雪天' 等",
        ),
    ],
    Version="1",
)

event_cabin_user_leaving = EventTypeSchema(
    EventType="cabin_user_leaving",
    Description="用户下车事件，智能体可根据此事件保存用户偏好设置并关闭相关设备",
    Properties=[
        EventProperty(
            PropertyName="user_id",
            PropertyValueType="string",
            Description="用户唯一标识",
        ),
        EventProperty(
            PropertyName="seat_position",
            PropertyValueType="string",
            Description="用户座位位置，如 'driver', 'front_passenger', 'rear_left' 等",
        ),
        EventProperty(
            PropertyName="leaving_time",
            PropertyValueType="string",
            Description="下车时间",
        ),
    ],
    Version="1",
)

event_cabin_navigation_start = EventTypeSchema(
    EventType="cabin_navigation_start",
    Description="开始导航事件，智能体可根据此事件提供路线建议和沿途服务信息",
    Properties=[
        EventProperty(
            PropertyName="user_id",
            PropertyValueType="string",
            Description="用户唯一标识",
        ),
        EventProperty(
            PropertyName="destination",
            PropertyValueType="string",
            Description="目的地名称或地址",
        ),
        EventProperty(
            PropertyName="route_type",
            PropertyValueType="string",
            Description="路线类型，如 'fastest', 'shortest', 'scenic' 等",
        ),
        EventProperty(
            PropertyName="estimated_duration",
            PropertyValueType="int64",
            Description="预计行程时长（分钟）",
        ),
    ],
    Version="1",
)

event_cabin_voice_command = EventTypeSchema(
    EventType="cabin_voice_command",
    Description="语音指令事件，智能体根据用户语音指令执行相应操作",
    Properties=[
        EventProperty(
            PropertyName="user_id",
            PropertyValueType="string",
            Description="用户唯一标识",
        ),
        EventProperty(
            PropertyName="command_text",
            PropertyValueType="string",
            Description="语音指令的文本内容",
        ),
        EventProperty(
            PropertyName="command_category",
            PropertyValueType="string",
            Description="指令类别，如 'music_control', 'navigation', 'climate_control' 等",
        ),
        EventProperty(
            PropertyName="execution_result",
            PropertyValueType="string",
            Description="指令执行结果，如 'success', 'failed', 'partial' 等",
        ),
    ],
    Version="1",
)


def test_event():
    
    print(event_english_study)
    print(event_cabin_user_boarding)
    print(event_cabin_user_leaving)
    print(event_cabin_navigation_start)
    print(event_cabin_voice_command)

def test_add_search_delete_event():
    test_collection_id = CollectionID(collection_name="SGM")
    user_id="dzy_test_event"
    add_result = add_custom_event_memory(
        collection_id=test_collection_id,
        user_id=user_id,
        event_type="event_v1",
        memory_content={
            "summary": "我手搓了一个event加进来",
        },
    )
    print(add_result)
    print("*" *80)
    input("看一下记忆是否加进来了")
    search_result = search_event_memory(
        collection_id=test_collection_id,
        event_type="event_v1",
        # query="手搓",
        user_id=user_id,
    )
    print(search_result)
    print("*" *80)
    batch_delete_event(
        collection_id=test_collection_id,
        event_type="event_v1",
        user_id=user_id,
    )
    search_result = search_event_memory(
        collection_id=test_collection_id,
        event_type="event_v1",
        query="手搓",
        user_id=user_id,
    )
    print(search_result)
    print("*" *80)
    

if __name__ == "__main__":
    # test_event()
    test_add_search_delete_event()