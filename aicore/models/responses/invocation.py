"""核心LLM调用功能模块"""

from __future__ import annotations

from typing import Iterable, Type, cast, Any

import time

from pydantic import BaseModel

# 下述symbol是实现细节。只要无需对外暴露，就不需要进入.core。
from volcenginesdkarkruntime.types.responses import ResponseTextConfigParam    # type: ignore
from volcenginesdkarkruntime.types.responses.response_format_text_config_param import ResponseFormatJSONObject  # type: ignore
from aicore.utils.misc import safe_update

from .core import (
    Ark, 
    AsyncArk,
    ResponseRaw, 
    Response, 
    ResponseInputParam,
    FunctionToolParam,
    _prepare_request,
)

from .params import ResponseParams


def _apply_message_history(response: Response) -> None:
    """
    在拿到 response 后，根据是否有 message/tool_calls 更新 message_history。
    供 invoke、ainvoke 复用。
    """
    # 有 tool call 或没有 message 时，不更新 message_history。
    if response.tool_calls or not response.message:
        return

    # 主路径：prepare 已经写入了 (user, "") 占位，直接回填本轮回复。
    if response.message_history and response.message_history[-1][1].content == "":
        response.message_history[-1][1].content = response.raw_text
        return

    #TODO： 不确定还有没有其他场景，还没遇到。


def invoke(
    input: str | ResponseInputParam,
    previous_response_or_system_prompt: Response | str | None = None,
    /,
    *,
    client: Ark,
    model: str,
    tools: Iterable[FunctionToolParam] | None = None,
    params: ResponseParams | None = None,
    **kwargs: Any,
) -> Response:
    """
    核心LLM调用函数。在底层的responses api上增加如下功能：
    1. 计时
    2. 显式暴露一些重要参数
    3. 更好用的Response对象
    
    Args:
        input: 用户输入
        previous_response_or_system_prompt: 上一轮对话输出的Response对象或系统提示词
        client: 火山方舟引擎客户端
        model: 模型名称
        params: 运行时参数
        **kwargs: 传递给API的其他参数，作为对于params的补充
    
    Returns:
        ResponseResult[T]: 包含处理后的输出结果
    """

    start = time.perf_counter()

    # 合并两组参数。确保不会重复
    if params is not None:
        safe_update(kwargs, params.model_dump(exclude_none=True))

    # 确保一些重要参数不在kwargs中。需要显式指定。
    assert "format" not in kwargs, "format must not be specified in kwargs in invoke, use invoke_output_xxx instead."
    assert "previous_response_id" not in kwargs, "previous_response_id should not be in kwargs"

    previous_response_id, message_history, input = _prepare_request(
        input,
        previous_response_or_system_prompt,
    )
    
    response = client.responses.create(
        model=model, 
        input=input, 
        tools=tools,
        previous_response_id=previous_response_id,
        **kwargs,
    )

    response = cast(ResponseRaw, response)
    response = Response.from_raw(
        response, 
        message_history=message_history,
        latency=time.perf_counter() - start,
    )

    _apply_message_history(response)

    return response


async def ainvoke(
    input: str | ResponseInputParam,
    previous_response_or_system_prompt: Response | str | None = None,
    /,
    *,
    client: AsyncArk,
    model: str,
    tools: Iterable[FunctionToolParam] | None = None,
    params: ResponseParams | None = None,
    **kwargs: Any,
) -> Response:
    """
    异步版本的 invoke。使用 AsyncArk 客户端，不阻塞事件循环。
    """
    start = time.perf_counter()

    if params is not None:
        safe_update(kwargs, params.model_dump(exclude_none=True))

    assert "format" not in kwargs, "format must not be specified in kwargs in ainvoke, use ainvoke_output_by_json instead."
    assert "previous_response_id" not in kwargs, "previous_response_id should not be in kwargs"

    previous_response_id, message_history, input = _prepare_request(
        input,
        previous_response_or_system_prompt,
    )

    response = await client.responses.create(
        model=model,
        input=input,
        tools=tools,
        previous_response_id=previous_response_id,
        **kwargs,
    )

    response = cast(ResponseRaw, response)

    response = Response.from_raw(
        response, 
        message_history=message_history,
        latency=time.perf_counter() - start,
    )

    _apply_message_history(response)

    return response


def invoke_output_by_json[T: Type[BaseModel]] (
    input: str,
    /,
    *,
    output_type: T,
    previous_response_or_system_prompt: Response | str | None = None,
    client: Ark,
    model: str,
    params: ResponseParams | None = None,
    output_schema: str | None = None,
    **kwargs: Any,
) -> tuple[T, Response]:
    """
    基于JSON Schema的结构化输出。目前的实现是基于invoke的一个简单wrapper。
    支持输入消息历史，技术上可以连续调用了，但不应该这么使用，也还缺少测试。

    TODO: 
    - 输出tuple显然不好用。但也想不清怎么改进。
    """

    assert issubclass(output_type, BaseModel), f"output_type must be BaseModel, but got {type(output_type)}"

    # TODO: 将结构化prompt放入system prompt是随便写的。这假设了不要消息历史。是非常强的限制条件。要改。
    sys_prompt = "你是一位结构化数据专家，需以结构化 JSON 格式输出。格式要求如下:"
    sys_prompt += f"\n{output_schema or output_type.model_json_schema()}"
    sys_prompt += "\n请勿输出 JSON 以外的内容。"

    assert "format" not in kwargs
    format = ResponseTextConfigParam(format=ResponseFormatJSONObject(type="json_object"))
    #format = ResponseTextConfigParam(format={"type": "json_schema"})  # 不支持
    kwargs.update({"text": format})

    input = f"{sys_prompt}\n\n{input}"
    response = invoke(
        input,
        previous_response_or_system_prompt,
        client=client,
        model=model,
        params=params,
        **kwargs,
    )

    res = output_type.model_validate_json(response.raw_text)

    return res, response


async def ainvoke_output_by_json[T: BaseModel] (
    input: str,
    /,
    *,
    output_type: type[T],
    previous_response_or_system_prompt: Response | str | None = None,
    client: AsyncArk,
    model: str,
    params: ResponseParams | None = None,
    output_schema: str | None = None,
    **kwargs: Any,
) -> tuple[T, Response]:
    """异步版本的 invoke_output_by_json。基于 JSON 的结构化输出。"""
    assert issubclass(output_type, BaseModel), f"output_type must be BaseModel, but got {type(output_type)}"

    sys_prompt = "你是一位结构化数据专家，需以结构化 JSON 格式输出。格式要求如下:"
    sys_prompt += f"\n{output_schema or output_type.model_json_schema()}"
    sys_prompt += "\n请勿输出 JSON 以外的内容。"

    assert "format" not in kwargs
    format = ResponseTextConfigParam(format=ResponseFormatJSONObject(type="json_object"))
    kwargs.update({"text": format})
    input = f"{sys_prompt}\n\n{input}"
    response = await ainvoke(
        input,
        previous_response_or_system_prompt,
        client=client,
        model=model,
        params=params,
        **kwargs,
    )

    res = output_type.model_validate_json(response.raw_text)

    return res, response


async def ainvoke_output_by_schema[T: BaseModel](
    input: str,
    /,
    *,
    output_type: type[T],
    previous_response_or_system_prompt: Response | str | None = None,
    client: AsyncArk,
    model: str,
    params: ResponseParams | None = None,
    **kwargs: Any,
) -> tuple[T, Response]:
    """
    TODO：方舟ark，上下文缓存 API 暂不支持 json_schema。ResponseTextConfigParam的format不支持json_schema。
    目前不可用。对应的同步方法后续再补充。
    """
    assert issubclass(output_type, BaseModel), f"output_type must be BaseModel, but got {type(output_type)}"

    if "json" not in input.lower():
        input = f"{input}\n请根据要求返回 JSON。不要包括 JSON 以外的文字。"

    assert "text" not in kwargs
    assert "format" not in kwargs
    text = ResponseTextConfigParam(
        format={
            "type": "json_schema",
            "name": output_type.__name__,
            "schema": output_type.model_json_schema(),
            "strict": True,
        },
    )
    kwargs.update({"text": text})

    response = await ainvoke(input, previous_response_or_system_prompt, client=client, model=model, params=params, **kwargs)
    parsed = output_type.model_validate_json(response.raw_text)
    return parsed, response
