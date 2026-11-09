"""
验证 aclean_memory_for_users 是否能正确清空记忆。

测试两种 case：
1. context_config 自带 collection_name 的 case（模拟旧式 case）
2. context_config 为空 {} 的 case（模拟从数据库加载的 case，依赖 bot 默认配置）

流程：
1. 用两个 case 分别跑一轮对话，让记忆产生
2. 搜索记忆确认记忆已产生
3. 调用 clean_case_memory 清空
4. 再次搜索记忆，确认已被清空
"""
import asyncio
import sys

from rich import print

from projects.mind.mem.auto_test_script.case_schema import TestCase
from projects.mind.mem.volc_api import CollectionID, Message
from projects.mind.mem.volc_api.event import asearch_event_memory
from projects.mind.mem.volc_api.profile import asearch_profile_memory
from projects.mind.mem.auto_test_script.auto_test_constants import (
    EVENT_MEMORY_TYPES,
    MEMORY_COLLECTION_NAME,
    TEST_ASSISTANT_ID,
)
from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
)
from projects.mind.mem.auto_test_script.auto_test_demos.demo_auto_test import (
    DemoAgentV1Bot,
    example_input_params,
)


CASE_WITH_COLLECTION = TestCase(
    id="verify-with-collection",
    case_id="verify_with_collection",
    context_config=example_input_params.model_dump(exclude_none=True),
    max_round=3,
    user_query_lists=[
        [Message(role="user", content="记住，我家在浦东。")],
    ],
    expected_script="用户：记住，我家在浦东。\n管家：好的，记住了。",
    nl_assertion=["助手须确认已记录住址"],
    case_description="验证清空记忆：自带 collection_name 的 case",
    tags=["验证脚本"],
)

CASE_WITHOUT_COLLECTION = TestCase(
    id="verify-without-collection",
    case_id="verify_without_collection",
    context_config={},
    max_round=3,
    user_query_lists=[
        [Message(role="user", content="记住，我喜欢听周杰伦的歌。")],
    ],
    expected_script="用户：记住，我喜欢听周杰伦的歌。\n管家：好的，记住了。",
    nl_assertion=["助手须确认已记录音乐偏好"],
    case_description="验证清空记忆：不带 collection_name 的 case（依赖 bot 默认配置）",
    tags=["验证脚本"],
)


async def _search_memory_for_user(user_id: str, collection_name: str, assistant_id: str):
    """搜索某个 user_id 下的画像和事件记忆，返回 (profile_count, event_count)"""
    cid = CollectionID(collection_name=collection_name)
    try:
        profile_resp = await asearch_profile_memory(
            cid,
            profile_type="steward_note_book",
            user_id=user_id,
            assistant_id=assistant_id,
            limit=10,
        )
        profile_count = profile_resp.data.count if profile_resp.code == 0 else -1
    except Exception as e:
        print(f"[WARN] 搜索画像记忆异常: {e}")
        profile_count = -1

    try:
        event_resp = await asearch_event_memory(
            cid,
            event_type=EVENT_MEMORY_TYPES,
            user_id=user_id,
            assistant_id=assistant_id,
            limit=10,
        )
        event_count = event_resp.data.count if event_resp.code == 0 else -1
    except Exception as e:
        print(f"[WARN] 搜索事件记忆异常: {e}")
        event_count = -1

    return profile_count, event_count


async def main():
    cases = [CASE_WITH_COLLECTION, CASE_WITHOUT_COLLECTION]

    print("=" * 60)
    print("Step 1: 用两个 case 各跑一轮对话，产生记忆")
    print("=" * 60)

    auto_test = AutoTestAndRLDataGenerator(
        bot_to_test=DemoAgentV1Bot,
        memory_test_cases=cases,
        verbose=True,
        log_dialogue=False,
        show_progress=False,
    )

    async for item in auto_test.arun_full_auto_judge_test(
        concurrency_mode=False,
        pause_mode=False,
        memory_reset_mode=False,
        upload_history_to_volc_memory=False,
        epoch=1,
    ):
        if hasattr(item, 'case_id'):
            print(f"  case [{item.case_id}] 执行完成, passed={item.is_passed}")

    print("\n" + "=" * 60)
    print("Step 2: 搜索记忆，确认记忆已产生")
    print("=" * 60)

    for a_case in cases:
        user_id = a_case.case_id
        collection_name = a_case.context_config.get("collection_name", MEMORY_COLLECTION_NAME)
        assistant_id = a_case.context_config.get("assistant_id", TEST_ASSISTANT_ID)
        if collection_name is None:
            merged = DemoAgentV1Bot._merge_context_config(a_case.context_config)
            collection_name = merged.get("collection_name", MEMORY_COLLECTION_NAME)
            assistant_id = merged.get("assistant_id", TEST_ASSISTANT_ID)

        p_count, e_count = await _search_memory_for_user(user_id, collection_name, assistant_id)
        print(f"  case [{a_case.id}] user_id={user_id}")
        print(f"    画像记忆数: {p_count}, 事件记忆数: {e_count}")
        if p_count <= 0 and e_count <= 0:
            print(f"    ⚠️ 记忆未产生，可能需要等待更长时间")

    print("\n" + "=" * 60)
    print("Step 3: 调用 clean_case_memory 清空记忆")
    print("=" * 60)

    auto_test2 = AutoTestAndRLDataGenerator(
        bot_to_test=DemoAgentV1Bot,
        memory_test_cases=cases,
        verbose=True,
        log_dialogue=False,
        show_progress=False,
    )
    await auto_test2.clean_case_memory(memory_reset_except_skills=False)
    print("  clean_case_memory 执行完毕")

    print("\n" + "=" * 60)
    print("Step 4: 再次搜索记忆，确认已被清空")
    print("=" * 60)

    all_passed = True
    for a_case in cases:
        user_id = a_case.case_id
        collection_name = a_case.context_config.get("collection_name", MEMORY_COLLECTION_NAME)
        assistant_id = a_case.context_config.get("assistant_id", TEST_ASSISTANT_ID)
        if collection_name is None:
            merged = DemoAgentV1Bot._merge_context_config(a_case.context_config)
            collection_name = merged.get("collection_name", MEMORY_COLLECTION_NAME)
            assistant_id = merged.get("assistant_id", TEST_ASSISTANT_ID)

        p_count, e_count = await _search_memory_for_user(user_id, collection_name, assistant_id)
        print(f"  case [{a_case.id}] user_id={user_id}")
        print(f"    画像记忆数: {p_count}, 事件记忆数: {e_count}")
        if p_count == 0 and e_count == 0:
            print(f"    ✅ 记忆已清空")
        else:
            print(f"    ❌ 记忆未清空！")
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 验证通过：所有 case 的记忆均已被正确清空")
    else:
        print("❌ 验证失败：部分 case 的记忆未被清空")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
