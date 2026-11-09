from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from projects.mind.test_backend.schemas.agent.react import ReActAgentRequest
from projects.mind.test_backend.schemas.response import ApiResponse, ok, sse_ok
import projects.mind.test_backend.service.agent.react as ReActAgentService
from aicore.models.credentials import ModelName


router = APIRouter(
    prefix="/react",
    tags=["ReAct Agent"],
)


@router.get("/models", response_model=ApiResponse[list[str]])
async def get_models() -> ApiResponse[list[str]]:
    """获取ReAct Agent可用模型列表"""
    models = [model.name for model in ModelName]
    return ok(models)


@router.get("/tools", response_model=ApiResponse[list[str]])
async def get_tools() -> ApiResponse[list[str]]:
    """获取ReAct Agent可用工具列表"""
    tools = list(ReActAgentService.get_tool_map().keys())
    return ok(tools)
