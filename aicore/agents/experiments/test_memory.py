from rich import print
import asyncio
import uuid

from typing import cast

from unittest.mock import patch

from aicore.models.messages import HumanMessage, AIMessage
from pydantic import ValidationError

from aicore.agents.experiments.memory import (
    MemoryProducerConfig,
    MemoryConsumerConfig,
    MemoryProducer,
    MemoryConsumer,
    UserInfoMetadata,
    SKILL_LAST_USED_DATETIME_KEY,
    normalize_skill_last_used_datetime,
    skill_last_used_datetime_now,
)

from projects.mind.mem.volc_api import CollectionID
from projects.mind.mem.volc_api.event import EventMemoryResponse
from projects.mind.mem.volc_api.profile import ProfileMemoryResponse
from projects.mind.mem.volc_api import abatch_delete_event, abatch_delete_profile

# 测试用记忆库配置
TEST_COLLECTION_NAME = "test_prompt"
TEST_USER_ID = "test_memory_user_id"
TEST_USER_NAME = "张三"
TEST_ASSISTANT_NAME = "测试记忆机制"
TEST_ASSISTANT_ID = "test_assistant_id"
# 默认创建collection时包含的profile和event类型
TEST_PROFILE_TYPES = ["steward_note_book"]
TEST_EVENT_TYPES = ["event_v1"]
SKILL_PROFILE_TYPE = "skills"


def profile_and_event_format_for_llm(response: ProfileMemoryResponse | EventMemoryResponse) -> str:
    """将召回结果格式化为适合大模型理解的字符串"""
    if response.code != 0 or not response.data.result_list:
        return ""
    
    lines = ["【用户记忆画像】"]
    
    for item in response.data.result_list:
        memory_type = item.memory_type
        info = item.memory_info
        
        match memory_type:
            case "sys_profile_v1":
                lines.append(f"\n[用户画像] {info.get('user_profile', '{}')}")
            case "sys_event_v1":
                lines.append(f"\n[事件记录] 总结:{info.get('summary', '{}')}")
            case _:
                lines.append(f"\n[{memory_type}] {info}")
    
    return "\n".join(lines)


async def test_memory_producer(producer: MemoryProducer):
    # 模拟的对话，用于触发记忆写入
    conversation = [
        (HumanMessage(content="你好"), AIMessage(content="你好！我是小途，有什么我可以帮助你的吗？")),
        (HumanMessage(content="我是张三，在上海闵行平金中心上班，平常喜欢打羽毛球、听音乐"), AIMessage(content="好的，张三。")),
        (HumanMessage(content="记一下我做瑜伽的地方在闵行区顾戴路2468号"), AIMessage(content="已帮你记录瑜伽馆地址：闵行区顾戴路2468号。下次需要导航过去可以随时告诉我哦～")),
        (HumanMessage(content="不用，导航到我爸妈家"), AIMessage(content="好的，为你导航到爸妈家。不过我还不知道叔叔阿姨家的具体地址，麻烦告诉我一下详细地址。")),
        (HumanMessage(content="万达广场3号楼"), AIMessage(content="以下是多个结果，请问是第几个？1. 万达广场 3 号楼 上海市宝山区共和新路 4995 号宝山万达广场。")),
        (HumanMessage(content="就第一个"), AIMessage(content="好的，为你导航到宝山万达广场 3号楼。")),
        (HumanMessage(content="你帮我记一下我爸妈的地址吧"), AIMessage(content="好的，已经帮你记下来了。")),
        (HumanMessage(content="记一下我外婆家的地址在今天花园8号楼"), AIMessage(content="已帮你记录外婆家地址：今天花园8号楼。下次需要导航过去可以随时告诉我哦～")),
        (HumanMessage(content="播放周杰伦的稻香"), AIMessage(content="好的，正在播放周杰伦的稻香。已为你播放周杰伦的《稻香》，需要调整音量或切换其他歌曲随时告诉我～")),
        (HumanMessage(content="音量调高"), AIMessage(content="音量已调高，当前音量是否合适？需要继续调整或切换其他歌曲吗？")),
        (HumanMessage(content="今天天气怎样"), AIMessage(content="今天上海市闵行区天气晴朗，气温10-20度，适合户外活动。")),
        (HumanMessage(content="你知道周杰伦是我最喜欢的歌手不"), AIMessage(content="哈哈，从你刚才点了周杰伦的歌，就猜到他是你的心头好了～需要我继续为你播放他的其他经典曲目吗？")),
        (HumanMessage(content="喜欢蛮多的吧枫晴天七里香之类的，喜欢这些歌的歌词"), AIMessage(content="周杰伦的中国风歌词确实很有韵味，《枫》的'缓缓飘落的枫叶像思念'、《晴天》的'故事的小黄花'，每一句都很有画面感。")),
        (HumanMessage(content="我喜欢周传雄的歌曲，一定要记住！"), AIMessage(content="好的，为你播放周传雄的《黄昏》")),
    ]
    for i, delta in enumerate(conversation):
        
        print(f"\n===== 第{i+1}次调用 =====")
        # Windows 默认 gbk 编码下 rich + emoji 可能报编码错误，测试里关闭打印 listener
        async for _ in producer.add_memory(delta, event_listeners=[]):
            pass

        # 原始event
        # async for event in producer.add_memory(delta, event_listeners=[]):
        #     print(event)
        
    # 打印缓冲区待处理轮数和累计处理轮数
    print(f"缓冲区待处理轮数: {producer.pending_count}")
    print(f"累计处理轮数: {producer.total_handled}")


async def adelete_all_memory(collection_id: CollectionID, user_id: str):
    """删除记忆"""
    await abatch_delete_event(collection_id, user_id=user_id)
    await abatch_delete_profile(collection_id, user_id=user_id)
    # 等待几秒
    print("等待10s 清空记忆。")
    await asyncio.sleep(10)


async def test_consumer_retrieve_memory(consumer: MemoryConsumer):
    """测试召回记忆"""
    rsp_profile = await consumer.retrieve_profiles(
        "你好呀，我现在在上海闵行平金中心上班。",
    )
    
    if rsp_profile.code == 0:
        print("\n画像原始响应: ")
        print(rsp_profile)
        print(f"召回成功，共 {rsp_profile.data.count} 条")
        print(f"\n自定义格式化记忆: {profile_and_event_format_for_llm(rsp_profile)}")
    else:
        print(f"画像召回失败: {rsp_profile.message}")
    print("\n" + "="*80)
    rsp_event = await consumer.retrieve_events(
        "你好呀，我现在在上海闵行平金中心上班。",
    )
    if rsp_event.code == 0:
        print("\n事件原始响应: ")
        print(rsp_event)
        print(f"召回成功，共 {rsp_event.data.count} 条")
        print(f"\n自定义格式化记忆: {profile_and_event_format_for_llm(rsp_event)}")
    else:
        print(f"事件召回失败: {rsp_event.message}")


def _print_skill_last_used_from_row(label: str, row: object) -> str:
    """从画像查询结果里取出 last_used 原始值与规范化值，并打印。"""
    mi_obj = getattr(row, "memory_info", None)
    if isinstance(mi_obj, dict):
        memory_info: dict[str, object] = cast(dict[str, object], mi_obj)
    else:
        memory_info = {}
    raw_val = memory_info.get(SKILL_LAST_USED_DATETIME_KEY, "")
    raw = raw_val if isinstance(raw_val, str) else str(raw_val)
    normalized = normalize_skill_last_used_datetime(raw)
    print(f"  [{label}] last_used_datetime 原始值: {raw!r}")
    print(f"  [{label}] last_used_datetime 规范化后: {normalized!r}")
    return normalized


async def _find_skill_by_name_retry(
    consumer: MemoryConsumer,
    skill_name: str,
    *,
    label: str,
    attempts: int = 8,
    delay_sec: float = 2.0,
):  # type: ignore[no-untyped-def]
    """记忆库写入后可能短暂不可查：轮询 `_find_skill_by_name`。"""
    for i in range(attempts):
        row = await consumer._find_skill_by_name(skill_name)  # type: ignore[reportPrivateUsage]
        if row is not None:
            if i > 0:
                print(f"  [{label}] 第 {i + 1} 次查询命中该 skill")
            return row
        if i < attempts - 1:
            print(
                f"  [{label}] 暂未查到 skill，{delay_sec:g}s 后再试 ({i + 1}/{attempts})"
            )
            await asyncio.sleep(delay_sec)
    return None


async def _wait_until_skill_last_used_matches(
    consumer: MemoryConsumer,
    skill_name: str,
    expected: str,
    *,
    phase_label: str,
    attempts: int = 15,
    delay_sec: float = 2.0,
) -> str:
    """
    load 写入 last_used 后，读链路也可能晚于写入；直到规范化后的字段与 expected 相等或用尽次数。
    """
    last_seen = ""
    keys_printed = False
    for i in range(attempts):
        row = await consumer._find_skill_by_name(skill_name)  # type: ignore[reportPrivateUsage]
        if row is None:
            print(f"  [{phase_label}] 第 {i + 1} 次：未查到该 skill，{delay_sec:g}s 后重试")
            await asyncio.sleep(delay_sec)
            continue
        mi_obj = getattr(row, "memory_info", None)
        if isinstance(mi_obj, dict):
            mi = cast(dict[str, object], mi_obj)
            if not keys_printed:
                keys_printed = True
                print(f"  [{phase_label}] memory_info 字段键（便于确认是否带回 last_used）: {sorted(mi.keys())!r}")
            raw_val = mi.get(SKILL_LAST_USED_DATETIME_KEY, "")
        else:
            raw_val = ""
        raw = raw_val if isinstance(raw_val, str) else str(raw_val)
        last_seen = normalize_skill_last_used_datetime(raw)
        if last_seen == expected:
            if i > 0:
                print(f"  [{phase_label}] 第 {i + 1} 次查询读到期望值 {expected!r}")
            return last_seen
        print(
            f"  [{phase_label}] 当前 last_used={last_seen!r}，期望={expected!r}，"
            f"{delay_sec:g}s 后再试 ({i + 1}/{attempts})"
        )
        await asyncio.sleep(delay_sec)
    return last_seen


async def skill_last_used_datetime_demo(consumer: MemoryConsumer) -> None:
    """
    直观走一遍「创建 → 看时间 → load → 再查库看时间」。

    依赖真实火山记忆库（与 main 里相同的 collection / user），需已开启 skills 画像类型。

    说明：
    - 新建 skill 时 last_used_datetime 应为空字符串。
    - load_skill 返回的 last_used_datetime 是「本次 load 之前」库里存的值（新建后第一次 load 应为空）。
    - load 成功后会把「当前时间」写回记忆；为便于打印和断言与 load 时刻严格一致，这里对
      skill_last_used_datetime_now 做了 patch（生产环境无 patch，即为真实当前时间）。
    """
    if not consumer.has_skill_profile_type:
        print("skill_last_used_datetime_demo: 未启用 skills 搜索类型，跳过。")
        return

    # 随机名称，避免与库里已有 skill 冲突
    skill_name = f"skill_ls_demo_{uuid.uuid4().hex[:12]}"
    print("\n" + "=" * 60)
    print("skill_last_used_datetime_demo 开始")
    print(f"  使用 skill_name = {skill_name!r}")
    print("=" * 60)

    # ---------- 1) 创建 skill ----------
    print("\n--- 步骤 1：create_new_skill_worker 写入画像 ---")
    create_worker = consumer.create_new_skill_worker()
    created = await create_worker(
        skill_name,
        "demo：last_used 测试用描述",
        "# demo\n仅用于 test_memory 里打印 last_used_datetime。",
    )
    if not created.success:
        print(f"创建 skill 失败，结束 demo: {created.messages}")
        return
    print(f"  创建结果: success={created.success}, messages={created.messages!r}")

    # ---------- 2) 查库，打印创建后的 last_used（应为空）；写入后可能对账有延迟，故带重试 ----------
    print("\n--- 步骤 2：创建后按 skill_name 查画像（可多等几秒直至命中）---")
    row_after_create = await _find_skill_by_name_retry(consumer, skill_name, label="创建后")
    if row_after_create is None:
        print("创建后查询不到该 skill，可能写入延迟或未生效，结束 demo。")
        return
    last_after_create = _print_skill_last_used_from_row("创建后（查库）", row_after_create)
    assert last_after_create == "", (
        "新建 skill 的 last_used_datetime 规范化后应为空字符串"
    )

    # ---------- 3) load_skill：写入「本次使用时间」 ----------
    # 若去掉这个 patch，则下面 expected_write 应改为 load 前后的 skill_last_used_datetime_now()，
    # 并放宽为时间窗口断言，避免因跨秒导致严格相等失败。
    expected_write_at_load = "2099-11-08 06:07:09"
    print("\n--- 步骤 3：load_skill（本 demo patch 写入时间为固定值便于核对）---")
    print(f"  本次将向记忆库写入的 last_used_datetime = {expected_write_at_load!r}")

    load_worker = consumer.create_load_skill_worker()
    with patch(
        "aicore.agents.experiments.memory.skill_last_used_datetime_now",
        return_value=expected_write_at_load,
    ):
        loaded_out = await load_worker(skill_name)

    if loaded_out.skill is None:
        print(f"load_skill 失败: {loaded_out.messages}")
        return

    print(f"  load 工具返回 messages: {loaded_out.messages!r}")
    print(
        "  load 返回的 skill.last_used_datetime（= load 之前在库里的上次使用时间，新建后应为空）: "
        f"{loaded_out.skill.last_used_datetime!r}"
    )
    assert loaded_out.skill.last_used_datetime == "", (
        "新建后首次 load，工具返回的上次使用时间应为空"
    )

    # ---------- 4) 再查库：应与 load 写入时间一致（轮询容忍读延迟）----------
    print("\n--- 步骤 4：load 后轮询读库，直到 last_used_datetime 等于本次写入值 ---")
    last_after_load = await _wait_until_skill_last_used_matches(
        consumer,
        skill_name,
        expected_write_at_load,
        phase_label="load 后读到库里",
    )
    row_final = await consumer._find_skill_by_name(skill_name)  # type: ignore[reportPrivateUsage]
    if row_final is None:
        print("轮询已拿到期望值，但最后一步画像查询返回空（少见）；仍以轮询返回值为准对比断言。")
    else:
        _print_skill_last_used_from_row("load 后（查库·与断言一致快照）", row_final)

    assert last_after_load == expected_write_at_load, (
        f"查库得到的 last_used 应为本次 load 写入的时间 {expected_write_at_load!r}，实为 {last_after_load!r}"
        " —— 若长期为空，请在火山侧确认 skills 画像类型是否注册了 last_used_datetime 字段。"
    )

    # 顺带打印「若不 patch 会得到什么格式的当前时间」（仅展示，不写库）
    print("\n--- 参考：skill_last_used_datetime_now() 无 patch 时的格式示例 ---")
    print(f"  {skill_last_used_datetime_now()!r}")

    print("\n" + "=" * 60)
    print("skill_last_used_datetime_demo 结束：创建后为空；load 后查库时间与 load 写入一致。")
    print("=" * 60 + "\n")


def run_skill_last_used_demo(consumer: MemoryConsumer) -> None:
    """同步入口：`main()` 里可直接调用。"""
    asyncio.run(skill_last_used_datetime_demo(consumer))


def test_consumer_config_validation():
    """测试消费者配置校验规则。"""
    # 允许只消费事件记忆
    event_only_config = MemoryConsumerConfig(
        collection_id=CollectionID(collection_name=TEST_COLLECTION_NAME),
        event_types=TEST_EVENT_TYPES,
    )
    assert event_only_config.event_types == TEST_EVENT_TYPES

    # 不允许画像与事件都不消费
    try:
        MemoryConsumerConfig(
            collection_id=CollectionID(collection_name=TEST_COLLECTION_NAME),
        )
    except ValidationError:
        print("配置校验通过：不允许同时不消费画像与事件记忆。")
    else:
        raise AssertionError("期望抛出 ValidationError，但未抛出。")


def main():
    # 创建一个记忆库，用于测试，执行一次即可。
    # create_collection(CollectionCreate(
    #     CollectionName=TEST_COLLECTION_NAME,
    #     BuiltinProfileTypes=TEST_PROFILE_TYPES, # 火山内置的画像类型
    #     BuiltinEventTypes=TEST_EVENT_TYPES, # 火山内置的事件类型
    #     ))

    user_info = UserInfoMetadata(
        user_id=TEST_USER_ID,
        user_name=TEST_USER_NAME,
        assistant_id=TEST_ASSISTANT_ID,
        assistant_name=TEST_ASSISTANT_NAME,
    )
    producer_config = MemoryProducerConfig(
        collection_id=CollectionID(collection_name=TEST_COLLECTION_NAME),
        memory_type=TEST_PROFILE_TYPES + TEST_EVENT_TYPES,
        # memory_type=["test_profile"],# 传入不存在的memory_type, 会抛异常
        # memory_type=[], # 测试空列表，会抛异常
    )
    consumer_config = MemoryConsumerConfig(
        collection_id=CollectionID(collection_name=TEST_COLLECTION_NAME),

        system_prompt_profile_types=TEST_PROFILE_TYPES,
        search_profile_types=[SKILL_PROFILE_TYPE],
        event_types=TEST_EVENT_TYPES,

        # system_prompt_profile_types=["a"], # 传入未知的profile_type, 不会报错，但召回无结果，count=0
        # search_profile_types=["a"], # 传入未知的profile_type, 不会报错，但召回无结果，count=0
        # event_types=["A"], # 传入未知的event_type, 不会报错，但召回无结果，count=0

        # system_prompt_profile_types=[], # 不支持传入空列表，会抛异常，故在basemodel中校验
        # search_profile_types=[], # 不支持传入空列表，会抛异常，故在basemodel中校验
        # event_types=[], # 不支持传入空列表，会抛异常，故在basemodel中校验
        profile_limit=3,
        event_limit=3,
    )

    # session_size: 窗口大小，未处理过的轮数达到窗口大小开始写入记忆。
    memory_producer = MemoryProducer(producer_config, user_info, session_size=3)

    memory_consumer = MemoryConsumer(consumer_config, user_info)

    # test_consumer_config_validation()

    run_skill_last_used_demo(memory_consumer)

    # 清空记忆：先清空，再测试
    asyncio.run(adelete_all_memory(producer_config.collection_id, user_info.user_id))

    # 测试memory_producer写入记忆   
    asyncio.run(test_memory_producer(memory_producer))

    asyncio.run(test_consumer_retrieve_memory(memory_consumer))

if __name__ == "__main__":
    main()