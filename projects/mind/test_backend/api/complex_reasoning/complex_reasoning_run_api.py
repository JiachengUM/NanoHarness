from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from aicore.agents.experiments.base import SystemPrompt
from projects.mind.test_backend.schemas.agent.react import (
    AgentMemoryResponse,
    AgentModel,
    ReActAgentAutoChatRequest,
    ReActAgentRequest,
)
from projects.mind.test_backend.schemas.response import ApiResponse, ok, sse_ok
import projects.mind.test_backend.service.agent.react as ReActAgentService
from aicore.models.credentials import ModelName

router = APIRouter(
    prefix="/complex_reasoning_run",
    tags=["ReAct Agent"],
)


@router.get("/models", response_model=ApiResponse[list[AgentModel]])
async def get_models() -> ApiResponse[list[AgentModel]]:
    """获取ReAct Agent可用模型列表"""
    models = [AgentModel(name=model.name, value=model.value) for model in ModelName]
    return ok(models)


@router.get("/tools", response_model=ApiResponse[list[str]])
async def get_tools() -> ApiResponse[list[str]]:
    """获取ReAct Agent可用工具列表"""
    tools = list(ReActAgentService.get_tool_map().keys())
    return ok(tools)

@router.get("/system_prompt", response_model=ApiResponse[SystemPrompt])
async def get_system_prompt() -> ApiResponse[SystemPrompt]:
    """获取ReAct Agent系统提示词"""
    system_prompt = ReActAgentService.get_system_prompt()
    return ok(system_prompt)


@router.post("/base_agent_stream", response_class=StreamingResponse)
async def run_base_agent_stream(payload: ReActAgentRequest) -> StreamingResponse:
    """SSE流式返回Base Agent执行过程"""
    return sse_ok(ReActAgentService.run_base_agent_stream(payload))


@router.post("/base_agent_stream/auto_chat", response_class=StreamingResponse)
async def run_base_agent_stream_auto_chat(
    payload: ReActAgentAutoChatRequest,
) -> StreamingResponse:
    """SSE流式返回Base Agent执行过程(自动对话)"""
    return sse_ok(ReActAgentService.run_base_agent_stream_auto_chat(payload))


@router.get(
    "/retrieve_memory/{session_id}", response_model=ApiResponse[AgentMemoryResponse]
)
async def retrieve_memory(session_id: str) -> ApiResponse[AgentMemoryResponse]:
    """Agent记忆召回结果"""
    result = await ReActAgentService.retrieve_memory(session_id)
    return ok(result)


# @router.get("/list", response_model=ApiResponse[list[ComplexReasoningRunOut]])
# async def list_complex_reasoning_run(filters: ComplexReasoningRunFilter = Depends()):
#     docs = await mdb_api.get_list(model=AgentTraceDBSchema, query=filters.get_filters(), sort="-updated_time")
#     return ok(to_out_list(docs, ComplexReasoningRunOut))


# @router.get("/page", response_model=ApiResponse[Page[ComplexReasoningRunOut]])
# async def page_complex_reasoning_run(
#         filters: ComplexReasoningRunFilter = Depends(),
#         page_params: PageQuery = Depends(),
# ):
#     page_docs = await mdb_service.get_page(
#         model=AgentTraceDBSchema,
#         filters=filters.get_filters(),
#         page=page_params.page,
#         page_size=page_params.page_size,
#         sort="-updated_time"
#     )
#     return ok(to_out_page(page_docs, ComplexReasoningRunOut))


# @router.put("/{complex_reasoning_run_id}", response_model=ApiResponse[ComplexReasoningRunOut])
# async def update_complex_reasoning_run(payload: AgentTraceDBSchema):
#     doc = await mdb_api.update(model=AgentTraceDBSchema, data=payload)
#     return ok(to_out(doc, ComplexReasoningRunOut), message="更新成功")


# @router.delete("/{complex_reasoning_run_id}", response_model=ApiResponse)
# async def delete_complex_reasoning_run(intent_run_id: PydanticObjectId):
#     result = await mdb_api.delete_by_id(model=AgentTraceDBSchema, id=intent_run_id)
#     if not result:
#         return fail(code=ErrorCode.NOT_FOUND, message="未查询到记录")
#     return ok(message="删除成功")

__all__ = ["router"]
