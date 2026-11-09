import asyncio
from datetime import datetime
import time
from typing import Literal

from tqdm.asyncio import tqdm

from nanoai.utils.nl_repr import nl_repr
from projects.mind.mem.volc_api import (
    CollectionID,
    Message,
    SessionMetadata,
    abatch_delete_event,
    abatch_delete_profile,
    add_session,
    asearch_event_memory,
    asearch_profile_memory,
    batch_delete_event,
    batch_delete_profile,
    msg_to_volc_format,
)

DEFAULT_MEMORY_TYPES = ["profile_v1"]
DEFAULT_EVENT_MEMORY_TYPES = "event_v1"
DEFAULT_MEMORY_LIMIT = 10
DEFAULT_EVENT_MEMORY_LIMIT = 10

# 技能类画像在火山侧的类型名（业务常量；按类型清空时由调用方决定是否包含在 profile_types 中）
SKILL_PROFILE_MEMORY_TYPE = "skills"

CleanMemoryMode = Literal["all", "by_type"]


async def abatch_clear_volc_memory_for_users(
    collection_id: CollectionID,
    user_ids: list[str],
    assistant_id: str,
    *,
    mode: CleanMemoryMode = "all",
    clear_events: bool = True,
    clear_profiles: bool = True,
    event_types: str | list[str] | None = None,
    profile_types: str | list[str] | None = None,
) -> None:
    """
    按过滤条件批量清空多个 user_id 下的事件/画像记忆。

    火山 batch_delete 接口并发配额为 1：此处只做串行的单次批量删除（user_id 传列表），
    避免对每个用户分别发起一批请求。
    """
    if not user_ids:
        return
    if mode == "all":
        # 事件与画像须分两次请求；禁止 asyncio.gather 并行，以免触发 batch_delete 并发限制。
        await abatch_delete_event(
            collection_id,
            event_type=None,
            user_id=user_ids,
            assistant_id=assistant_id,
        )
        await abatch_delete_profile(collection_id, user_ids, assistant_id)
        return

    if clear_events:
        await abatch_delete_event(
            collection_id,
            event_type=event_types,
            user_id=user_ids,
            assistant_id=assistant_id,
        )
    if clear_profiles:
        if profile_types is None:
            await abatch_delete_profile(collection_id, user_ids, assistant_id)
        elif profile_types == []:
            pass
        else:
            await abatch_delete_profile(
                collection_id,
                user_ids,
                assistant_id,
                profile_type=profile_types,
            )


def batch_clear_volc_memory_for_users(
    collection_id: CollectionID,
    user_ids: list[str],
    assistant_id: str,
    *,
    mode: CleanMemoryMode = "all",
    clear_events: bool = True,
    clear_profiles: bool = True,
    event_types: str | list[str] | None = None,
    profile_types: str | list[str] | None = None,
) -> None:
    """同步版 :func:`abatch_clear_volc_memory_for_users`（每条批量删除串行执行）。"""
    if not user_ids:
        return
    if mode == "all":
        # 与异步版相同：两次调用顺序执行。
        batch_delete_event(collection_id, user_ids, assistant_id)
        batch_delete_profile(collection_id, user_ids, assistant_id)
        return

    if clear_events:
        batch_delete_event(
            collection_id,
            user_ids,
            assistant_id,
            event_type=event_types,
        )
    if clear_profiles:
        if profile_types is None:
            batch_delete_profile(collection_id, user_ids, assistant_id)
        elif profile_types == []:
            pass
        else:
            batch_delete_profile(
                collection_id,
                user_ids,
                assistant_id,
                profile_type=profile_types,
            )


async def add_to_memory(
    conversation: list[Message],
    /,
    *,
    collection_name: str,
    user_id: str,
    assistant_id: str = "小途助手",
    session_id: str | None = None,
    mock_time: str | None = None,
    ) -> None:
    """将对话添加到记忆库"""

    msgs = msg_to_volc_format(conversation)
    collection_id = CollectionID(collection_name=collection_name)
    event_time_ms = int(time.time() * 1000)
    if mock_time is not None:
        mock_dt = datetime.strptime(mock_time, "%Y-%m-%d %H:%M:%S")
        event_time_ms = int(mock_dt.timestamp() * 1000)
    metadata=SessionMetadata(
            default_user_id=user_id,
            default_assistant_id=assistant_id,
            time=event_time_ms)
    
    # 将同步的 add_session 调用放到线程池中执行，避免阻塞事件循环
    await asyncio.to_thread(add_session, collection_id, messages=msgs, session_id=session_id, metadata=metadata)

class VolcMemoryStore:
    """火山长期记忆类，可安插到任何bot里使用。"""

    def __init__(self, collection_name: str, user_id: str, assistant_id: str = "小途助手", memory_types: str | list[str] | None = None, memory_limit: int = DEFAULT_MEMORY_LIMIT, event_type: str | list[str] | None = None, event_limit: int = DEFAULT_EVENT_MEMORY_LIMIT):
        """初始化时设置好记忆库名和用户id，之后就不用一次次传入了"""
        self.collection_id = CollectionID(collection_name=collection_name)
        self.user_id = user_id
        self.assistant_id = assistant_id
        self.memory_types = memory_types
        self.memory_limit = memory_limit
        self.event_type = event_type
        self.event_limit = event_limit

    def delete_event_memory(self, event_type: str | list[str] | None = DEFAULT_EVENT_MEMORY_TYPES):
        """删除用户的特定事件记忆"""
        batch_delete_event(self.collection_id, self.user_id, self.assistant_id, event_type=event_type)

    def delete_profile_memory(self, profile_type: str | list[str] | None = DEFAULT_MEMORY_TYPES):
        """删除用户的特定画像记忆"""
        batch_delete_profile(self.collection_id, self.user_id, self.assistant_id, profile_type=profile_type)

    # def add_custom_profile_memory(self, profile_type: str, memory_content: dict[str, MemoryContentType], group_id: str | None = None, is_upsert: bool = True, incremental_update_keys: list[str] | None = None, keep_other_keys_content: bool = True):
    #     """添加自定义画像记忆"""
    #     collection_id = CollectionID(collection_name=self.collection_name)
    #     add_custom_profile_memory(
    #         collection_id=collection_id,
    #         profile_type=profile_type,
    #         memory_content=memory_content,
    #         user_id=self.user_id,
    #         assistant_id=self.assistant_id,
    #         group_id=group_id,
    #         is_upsert=is_upsert,
    #         incremental_update_keys=incremental_update_keys,
    #         keep_other_keys_content=keep_other_keys_content,
    #     )

    async def aadd_history_to_memory(
        self,
        volc_history: list[Message],
        wait_seconds: int = 30,
        mock_time: str | None = None,
    ):
        """
        添加多轮对话记录到火山记忆平台等待生成记忆
        Args:
            volc_history (list[Message]): 火山记忆平台的对话记录格式
            wait_seconds (int | None, optional): 等待记忆抽取生效的秒数。默认等待30秒。
        """
        assert self.collection_id.collection_name is not None, "collection_name 不能为空"
        await add_to_memory(volc_history, user_id=self.user_id,
                    collection_name=self.collection_id.collection_name,
                    assistant_id=self.assistant_id,
                    mock_time=mock_time)
        # 等待记忆抽取完毕生效
        if wait_seconds == 0:
            return
        elif wait_seconds < 0:
            raise ValueError("wait_seconds 不能小于0")
        else:
            print(f"等待记忆抽取生效...{wait_seconds}秒")
            # 异步等待记忆抽取生效，增加异步tqdm进度条
            for _ in tqdm(range(wait_seconds), desc="倒计时", unit="秒", ncols=75):
                await asyncio.sleep(1)
            print("等待记忆生成时间到！")
            return

    def add_history_to_memory(
        self,
        volc_history: list[Message],
        wait_seconds: int = 30,
        mock_time: str | None = None,
    ):
        """
        添加多轮对话记录到火山记忆平台等待生成记忆
        Args:
            volc_history (list[Message]): 火山记忆平台的对话记录格式
            wait_seconds (int | None, optional): 等待记忆抽取生效的秒数。默认等待30秒。
        """
        asyncio.run(
            self.aadd_history_to_memory(
                volc_history,
                wait_seconds=wait_seconds,
                mock_time=mock_time,
            )
        )

    async def aget_profile_memory_str(self, limit: int | None = None, profile_type: str | list[str] | None = None, query: str | None = None) -> str:
        """
        获取特定的记忆字符串
        Args:
            profile_type (str | list[str] | None, optional): 要获取的记忆类型列表。默认 None则使用初始化时设置的 memory_types。
            limit (int | None, optional): 获取的记忆数量上限。默认 None则使用初始化时设置的 memory_limit。
            query (str | None, optional): 搜索查询字符串。默认 None则返回全量记忆，否则根据query进行检索。
        Returns:
            str: 格式化后的记忆字符串
        """
        if profile_type is None:
            profile_type = self.memory_types
        if limit is None:
            limit = self.memory_limit
        # 将同步的 search_memory 调用放到线程池中执行，避免阻塞事件循环
        memory = await asearch_profile_memory(self.collection_id, profile_type, query, self.user_id, self.assistant_id, limit=limit)
        memory_str = nl_repr(
            [item.memory_info for item in memory.data.result_list])
        # print("*" * 80)
        # print(f"用户最新记忆：\n{memory_str}")
        return memory_str

    async def aget_event_memory_str(self, event_type: str | list[str] | None = None, limit: int | None = None, query: str | None = None) -> str:
        """
        获取特定类型的事件记忆字符串
        Args:
            event_type (str | list[str] | None, optional): 要获取的事件记忆类型。默认 None则使用初始化时设置的 event_type。
            limit (int | None, optional): 获取的记忆数量上限。默认 None则使用初始化时设置的 event_limit。
            query (str | None, optional): 搜索查询字符串。默认 None则返回全量记忆，否则根据query进行检索。
        Returns:
            str: 格式化后的事件记忆字符串
        """
        if event_type is None:
            event_type = self.event_type
        if limit is None:
            limit = self.event_limit
        event_memory = await asearch_event_memory(self.collection_id, event_type, query, self.user_id, self.assistant_id, limit=limit)
        event_memory_str = "\n".join(
            [str(item.memory_info["summary"]) for item in event_memory.data.result_list])
        return event_memory_str

    def clean_memory(
        self,
        *,
        mode: CleanMemoryMode = "all",
        clear_events: bool = True,
        clear_profiles: bool = True,
        event_types: str | list[str] | None = None,
        profile_types: str | list[str] | None = None,
    ) -> None:
        """
        清空该用户在当前记忆库下的火山记忆。

        Args:
            mode:
                - ``all``（默认）：删除**全部**事件记忆与**全部**画像记忆；忽略 ``clear_*`` 与类型参数。
                - ``by_type``：按开关与类型选择性删除。
            clear_events: 仅在 ``mode="by_type"`` 时生效；为真则调用事件批量删除。
            clear_profiles: 仅在 ``mode="by_type"`` 时生效；为真则按需调用画像批量删除。
            event_types: 仅在 ``mode="by_type"`` 且 ``clear_events`` 时传入 ``batch_delete_event`` 的
                ``event_type``。``None`` 表示不限制类型（删除该用户全部事件记忆）；非空字符串或列表表示只删这些类型。
            profile_types: 仅在 ``mode="by_type"`` 且 ``clear_profiles`` 时生效。
                ``None`` 表示删除**全部**画像；非空字符串或列表表示只删这些画像类型；``[]`` 空列表表示不删画像。
        """
        batch_clear_volc_memory_for_users(
            self.collection_id,
            [self.user_id],
            self.assistant_id,
            mode=mode,
            clear_events=clear_events,
            clear_profiles=clear_profiles,
            event_types=event_types,
            profile_types=profile_types,
        )

    async def a_clean_memory(
        self,
        *,
        mode: CleanMemoryMode = "all",
        clear_events: bool = True,
        clear_profiles: bool = True,
        event_types: str | list[str] | None = None,
        profile_types: str | list[str] | None = None,
    ) -> None:
        """异步版 :meth:`clean_memory`。"""
        await abatch_clear_volc_memory_for_users(
            self.collection_id,
            [self.user_id],
            self.assistant_id,
            mode=mode,
            clear_events=clear_events,
            clear_profiles=clear_profiles,
            event_types=event_types,
            profile_types=profile_types,
        )
    # def add_custom_memory(self, memory_content: BaseModel):
    #     """
    #     添加自定义记忆到火山记忆平台等待生成记忆
    #     Args:
    #         memory_content (BaseModel): 自定义记忆内容，必须是 BaseModel 的子类实例
    #     """
    #     pass

    # # def update_memory