from projects.mind.intent.task_data.message import Message
from projects.mind.mem.volc_api.base import CollectionID, MemoryContentType
from projects.mind.mem.volc_api.collection import CollectionCreate, create_collection
from projects.mind.mem.volc_api.event import (
    ProfileAndPrimaryKey,
    add_custom_event_memory,
    batch_delete_event,
    search_event_memory,
    aadd_custom_event_memory,
    abatch_delete_event,
    asearch_event_memory,
)
from projects.mind.mem.volc_api.profile import (
    add_custom_profile_memory,
    batch_delete_profile,
    search_profile_memory,
    aadd_custom_profile_memory,
    abatch_delete_profile,
    asearch_profile_memory,
)
from projects.mind.mem.volc_api.session import (
    Message as MessageVolcMem,
    MessageContent,
    SessionCreate,
    SessionMetadata,
    _msg_to_volc_format,
    add_session,
    get_session_info,
    aadd_session,
    aget_session_info,
)

# def add_to_memory(
#     conversation: list[Message],
#     /,
#     *,
#     collection_name: str,
#     user_id: str,
#     default_assistant_id: str = "小途助手",
#     session_id: str | None = None,
#     ) -> None:
#     """将对话添加到记忆库
#     对add_session的API wrapper
#     """

#     msgs = _msg_to_volc_format(conversation)
#     add_session(
#         session=SessionCreate(
#             collection_name=collection_name,
#             session_id=session_id,
#             messages=msgs,
#             metadata=SessionMetadata(
#                 default_user_id=user_id,
#                 default_assistant_id=default_assistant_id,
#                 time=int(time.time() * 1000),
#             )
#         ),
#     )


# 导出 msg_to_volc_format 作为 _msg_to_volc_format 的公共别名
msg_to_volc_format = _msg_to_volc_format

__all__ = [
    "Message",
    "CollectionCreate",
    "create_collection",
    "SessionCreate",
    "MessageVolcMem",
    "MessageContent",
    "SessionMetadata",
    "MemoryContentType",
    "msg_to_volc_format",
    "add_session",
    "batch_delete_event",
    "search_event_memory",
    "add_custom_event_memory",
    "aadd_custom_event_memory",
    "abatch_delete_event",
    "asearch_event_memory",
    "batch_delete_profile",
    "search_profile_memory",
    "add_custom_profile_memory",
    "aadd_custom_profile_memory",
    "abatch_delete_profile",
    "asearch_profile_memory",
    "get_session_info",
    "aadd_session",
    "aget_session_info",
    "ProfileAndPrimaryKey",
    "CollectionID"
]