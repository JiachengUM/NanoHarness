from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from projects.mind.complex_reasoning.task_mdb_models.chat_history import (
    AgentChatSessionDBSchema,
)
from projects.mind.complex_reasoning.task_schemas.chat_history import (
    AgentChatSessionHumanEval,
    AgentChatSessionOut,
    AgentChatSessionFilter,
    AgentChatSessionCreate,
)
from projects.mind.test_backend.core.errors import ErrorCode
from projects.mind.test_backend.utils.schemas import to_out, to_out_list, to_out_page
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.schemas.paginate import PageQuery, Page
from projects.mind.test_backend.schemas.response import ApiResponse, ok, fail

router = APIRouter(
    prefix="/complex_reasoning_chat_history",
    tags=["Complex Reasoning Chat History Manager"],
)


@router.get("/list", response_model=ApiResponse[list[AgentChatSessionOut]])
async def list_chat_history(filters: AgentChatSessionFilter = Depends()):
    docs = await mdb_service.get_list(
        model=AgentChatSessionDBSchema,
        query=filters.get_filters(),
        sort="-updated_time",
        exclude_fields=["messages", "agent_instance_dump"],
    )
    return ok(to_out_list(docs, AgentChatSessionOut))


@router.get("/page", response_model=ApiResponse[Page[AgentChatSessionOut]])
async def page_chat_history(
        filters: AgentChatSessionFilter = Depends(),
        page_params: PageQuery = Depends(),
):
    page_docs = await mdb_service.get_page(
        model=AgentChatSessionDBSchema,
        filters=filters.get_filters(),
        page=page_params.page,
        page_size=page_params.page_size,
        sort="-updated_time",
        exclude_fields=["messages", "agent_instance_dump"],
    )
    return ok(to_out_page(page_docs, AgentChatSessionOut))

@router.get("/{agent_session_id}", response_model=ApiResponse[AgentChatSessionOut])
async def get_chat_history(agent_session_id: PydanticObjectId):
    doc = await mdb_service.get_by_id(
        model=AgentChatSessionDBSchema, doc_id=agent_session_id
    )
    if not doc:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(to_out(doc, AgentChatSessionOut))


@router.post("", response_model=ApiResponse[AgentChatSessionOut])
async def create_chat_history(payload: AgentChatSessionCreate):
    doc = await mdb_service.create(AgentChatSessionDBSchema, payload)
    return ok(to_out(doc, AgentChatSessionOut), message="创建成功")


@router.put(
    "/{agent_session_id}",
    response_model=ApiResponse[AgentChatSessionOut],
)
async def update_chat_history(agent_session_id: PydanticObjectId, payload: AgentChatSessionDBSchema):
    doc = await mdb_service.update(
        model=AgentChatSessionDBSchema, doc_id=agent_session_id, data=payload
    )
    return ok(to_out(doc, AgentChatSessionOut), message="更新成功")


@router.delete("/{agent_session_id}", response_model=ApiResponse)
async def delete_chat_history(agent_session_id: PydanticObjectId):
    result = await mdb_service.delete_by_id(
        model=AgentChatSessionDBSchema, id=agent_session_id
    )
    if not result:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
    return ok(message="删除成功")

@router.post("/eval", response_model=ApiResponse)
async def eval_chat_history(data: AgentChatSessionHumanEval):
    doc = await mdb_service.get_by_id(model=AgentChatSessionDBSchema, doc_id=data.id)
    if not doc:
        return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")

    # 更新指定消息的评价结果
    if 0 <= data.message_index < len(doc.messages):
        doc.messages[data.message_index].human_evaluation = data.human_evaluation or None
    else:
        return fail(code=ErrorCode.PARAM_INVALID, message="消息索引超出范围")

    await mdb_service.update(model=AgentChatSessionDBSchema, doc_id=data.id, data=doc)

    return ok(message="评价成功")


__all__ = ["router"]
