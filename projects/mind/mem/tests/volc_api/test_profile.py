from rich import print

from projects.mind.mem.volc_api.profile import (
    ProfileProperty,
    ProfileTypeSchema,
    add_custom_profile_memory,
    search_profile_memory,
    batch_delete_profile
)
from projects.mind.mem.volc_api.base import CollectionID
from projects.mind.mem.volc_api.sys_profile_v1 import sys_profile_v1_dict

sys_profile_v1 = ProfileTypeSchema(**sys_profile_v1_dict)

car_user_profile = ProfileTypeSchema(
    ProfileType="car_user_profile",
    Description="车载场景下的用户画像，包含用户的用车习惯、导航旅游、饮食偏好、车载音乐等相关信息",
    Properties=[
        ProfileProperty(
            PropertyName="user_id",
            PropertyValueType="string",
            Description="用户唯一标识",
            IsPrimaryKey=True,
        ),
        ProfileProperty(
            PropertyName="frequent_routes",
            PropertyValueType="list<string>",
            Description="常用路线列表，如 '家-公司', '家-健身房' 等",
        ),
        ProfileProperty(
            PropertyName="driving_time_preference",
            PropertyValueType="string",
            Description="偏好驾驶时间段，如 '早晨', '晚上', '周末' 等",
        ),
        ProfileProperty(
            PropertyName="driving_style",
            PropertyValueType="string",
            Description="驾驶风格，如 '平稳', '激进', '经济' 等",
        ),
        ProfileProperty(
            PropertyName="navigation_preferences",
            PropertyValueType="list<string>",
            Description="导航偏好，如 '避开拥堵', '优先高速', '风景路线' 等",
        ),
        ProfileProperty(
            PropertyName="favorite_destination_types",
            PropertyValueType="list<string>",
            Description="喜欢的目的地类型，如 '购物中心', '景区', '餐厅', '加油站' 等",
        ),
        ProfileProperty(
            PropertyName="food_preferences",
            PropertyValueType="list<string>",
            Description="饮食偏好，如 '川菜', '粤菜', '日料', '快餐' 等",
        ),
        ProfileProperty(
            PropertyName="favorite_restaurants",
            PropertyValueType="list<string>",
            Description="常去的餐厅列表",
        ),
        ProfileProperty(
            PropertyName="music_genres",
            PropertyValueType="list<string>",
            Description="喜欢的音乐类型，如 '流行', '摇滚', '古典', '电子' 等",
        ),
        ProfileProperty(
            PropertyName="favorite_artists",
            PropertyValueType="list<string>",
            Description="喜欢的歌手或乐队列表",
        ),
        ProfileProperty(
            PropertyName="music_volume_preference",
            PropertyValueType="int64",
            Description="音乐音量偏好等级 (1-10)",
        ),
        ProfileProperty(
            PropertyName="voice_assistant_usage",
            PropertyValueType="bool",
            Description="是否频繁使用语音助手",
        ),
    ],
    Version="2",
)

__all__ = [
    "sys_profile_v1",
    "car_user_profile",
]


def test_profile():
    print(sys_profile_v1)
    print(car_user_profile)

def test_add_search_delete_profile():
    test_collection_id = CollectionID(collection_name="SGM")
    user_id="dzy_test_event"
    assistant_id = "dzy_test_assistant"
    result = add_custom_profile_memory(
        collection_id=test_collection_id,
        profile_type="steward_note_book",
        memory_content={
            "note_book_content": ["测试增加一条笔记"],
            "work_notice": ["测试增加一条工作建议"]
        },
        user_id=user_id,
        assistant_id=assistant_id,
        is_upsert=True
    )
    print(result)
    input("看一下记忆")
    result = search_profile_memory(
        collection_id=test_collection_id,
        query="工作建议",
        profile_type="steward_note_book",
        user_id=user_id,
        assistant_id=assistant_id,
    )
    print(result)
    print("*"*100)
    result = batch_delete_profile(
        collection_id=test_collection_id,
        profile_type="steward_note_book",
        user_id=user_id,
        assistant_id=assistant_id,
    )
    print(result)

def test_search_profile_memory():
    test_collection_id = CollectionID(collection_name="test_prompt")
    user_id="dzy_test_memory_new"
    assistant_id = "simulate_assistant"
    result = search_profile_memory(
        collection_id=test_collection_id,
        query="用户的空调偏好",
        profile_type=["work_notice","the_hint_fact_about_user","interaction_records"],
        user_id=user_id,
        assistant_id=assistant_id,
    )
    print(result)



if __name__ == "__main__":
    # test_profile()
    # test_add_search_delete_profile()
    test_search_profile_memory()