"""
连接responses API和BaseTool的helper functions
它们不进入tools的namespace, 因为可能会和chat API冲突
"""

from pydantic import BaseModel

from aicore.models.responses import (
    FunctionToolParam,
    FunctionCallOutput,
    ResponseFunctionToolCall,
    function_call_output,
)
from aicore.tools import ToolProtocol

__all__ = [
    "FunctionCallOutput",
    "ResponseFunctionToolCall",
    "function_call_output",
    "base_tool_to_param",
]


def base_tool_to_param(tool: ToolProtocol[BaseModel]) -> FunctionToolParam:
    """将 BaseTool 转换为 FunctionToolParam"""

    assert isinstance(tool.args_schema, type), "工具参数schema必须是 BaseModel 或 dict"
    assert issubclass(tool.args_schema, BaseModel)

    params = tool.args_schema.model_json_schema()

    return FunctionToolParam(
        name=tool.name,
        parameters=params,
        type="function",
        description=tool.description,
    )
