from __future__ import annotations

import json
from typing import AsyncIterator, Any, Sequence, cast, assert_never

from pydantic import BaseModel, TypeAdapter, ValidationError, model_validator

from volcenginesdkarkruntime import AsyncArk # type: ignore
from volcenginesdkarkruntime._streaming import AsyncStream # type: ignore
from volcenginesdkarkruntime.types.responses import ( # type: ignore
    Response,
    ResponseStreamEvent,
    ResponseOutputItemAddedEvent,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
    ResponseCompletedEvent,
    ResponseFunctionToolCall,
    ResponseReasoningItem,
    FunctionToolParam,
    ResponseOutputItemDoneEvent,
    ResponseTextConfigParam,
    ResponseFunctionToolCallParam,
)
from volcenginesdkarkruntime.types.responses.response_input_message_item import ResponseInputMessageItem # type: ignore
from volcenginesdkarkruntime.types.responses.response_output_message import ResponseOutputMessage # type: ignore
from volcenginesdkarkruntime.types.responses.response_function_tool_call_item import ResponseFunctionToolCallItem # type: ignore
from volcenginesdkarkruntime.types.responses.response_function_tool_call_output_item import ResponseFunctionToolCallOutputItem # type: ignore
from volcenginesdkarkruntime.types.responses.response_input_param import ResponseInputItemParam # type: ignore

from aicore.tools.protocol import ToolProtocol
from aicore.tools.run import ToolRunRequest, ToolRunResult
from aicore.utils.misc import safe_update

from aicore.models.responses.management import alist_all_items
from aicore.models.responses.params import ResponseParams, Thinking
from aicore.models.responses.core import (
    assistant_msg,
    system_msg,
    user_msg,
    function_call_output,
)


from .events import (
    ModelEvent,
    ModelTextStartEvent,
    ModelTextDeltaEvent,
    ModelTextDoneEvent,
    ModelToolCallEvent,
)
from .protocol import ModelAPI, ModelStream
from .types import (
    AssistantMessage,
    ModelCallParams,
    ModelInput,
    ModelMessage,
    ModelResponse,
    ModelState,
    ModelStateDump,
    StructuredModelResponse,
    SystemMessage,
    ToolResultsMessage,
    UserMessage,
)

_RESPONSES_STATE_DUMP_FORMAT = "responses.state"
_RESPONSES_STATE_DUMP_FORMAT_VERSION = 1


class ResponsesModelState(ModelState):
    response: Response | None = None
    history: list[ModelMessage] | None = None
    system_prompt: str | None = None

    @model_validator(mode="after")
    def _check_exclusive(self) -> ResponsesModelState:
        non_none = sum(x is not None for x in (self.response, self.history, self.system_prompt))
        if non_none > 1:
            raise ValueError("response, history, and system_prompt are mutually exclusive")
        return self


class _ResponsesStatePayload(BaseModel):
    history: list[ModelMessage] | None = None
    system_prompt: str | None = None


def _response_tool_param_from_tool(tool: ToolProtocol[BaseModel]) -> FunctionToolParam:
    assert isinstance(tool.args_schema, type)
    assert issubclass(tool.args_schema, BaseModel)
    return FunctionToolParam(
        name=tool.name,
        parameters=tool.args_schema.model_json_schema(),
        type="function",
        description=tool.description,
    )


def _response_input_params_from_input(input: ModelInput) -> list[ResponseInputItemParam]:
    messages = [input] if isinstance(input, (UserMessage, ToolResultsMessage)) else input
    result: list[ResponseInputItemParam] = []
    for message in messages:
        match message:
            case UserMessage():
                result.append(user_msg(message.text))
            case ToolResultsMessage():
                result.extend(
                    function_call_output(tool_result.run_id, tool_result.output)
                    for tool_result in message.results
                )
            case _:
                assert_never(message)
    return result


def _parse_tool_arguments(raw_arguments: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise ValueError("Responses tool arguments are not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Responses tool arguments must be a JSON object")

    return cast(dict[str, object], parsed)


def _run_request_from_sdk_tool_call(call: ResponseFunctionToolCall) -> ToolRunRequest:
    return ToolRunRequest(
        run_id=call.call_id,
        tool_name=call.name,
        arguments=_parse_tool_arguments(call.arguments),
        raw_arguments=call.arguments,
    )


def _extract_text(response: Response) -> str | None:
    for item in (response.output or []):
        if isinstance(item, ResponseOutputMessage):
            if item.content:
                return item.content[0].text
    return None


def _extract_tool_calls(response: Response) -> list[ToolRunRequest]:
    result: list[ToolRunRequest] = []
    for item in (response.output or []):
        if isinstance(item, ResponseFunctionToolCall):
            result.append(_run_request_from_sdk_tool_call(item))
    return result


def _response_input_params_from_history(
    history: Sequence[ModelMessage],
) -> list[ResponseInputItemParam]:
    result: list[ResponseInputItemParam] = []
    for message in history:
        match message:
            case SystemMessage():
                result.append(system_msg(message.text))
            case UserMessage():
                result.append(user_msg(message.text))
            case AssistantMessage():
                if message.text or not message.tool_calls:
                    result.append(assistant_msg(message.text))
                result.extend(
                    _response_tool_call_param_from_run_request(tool_call)
                    for tool_call in message.tool_calls
                )
            case ToolResultsMessage():
                result.extend(
                    function_call_output(tool_result.run_id, tool_result.output)
                    for tool_result in message.results
                )
            case _:
                assert_never(message)
    return result


def _message_from_response_message(
    message: ResponseInputMessageItem | ResponseOutputMessage,
) -> ModelMessage:
    role = message.role
    text = _text_from_response_message(message)
    if role == "system":
        return SystemMessage(text=text)
    if role == "user":
        return UserMessage(text=text)
    if role == "assistant":
        return AssistantMessage(text=text, tool_calls=[])
    raise ValueError(f"Unsupported Responses message role: {role!r}")


def _text_from_response_message(
    message: ResponseInputMessageItem | ResponseOutputMessage,
) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if content:
        text = getattr(content[0], "text", None)
        if isinstance(text, str):
            return text
    raise ValueError("Responses message content is not text")


def _model_messages_from_response_item(
    item: ResponseInputMessageItem
    | ResponseOutputMessage
    | ResponseFunctionToolCallItem
    | ResponseFunctionToolCallOutputItem
    | ResponseReasoningItem,
) -> list[ModelMessage]:
    if isinstance(item, (ResponseInputMessageItem, ResponseOutputMessage)):
        return [_message_from_response_message(item)]
    if isinstance(item, ResponseFunctionToolCallItem):
        return [
            AssistantMessage(
                text="",
                tool_calls=[_run_request_from_response_tool_call_item(item)],
            )
        ]
    if isinstance(item, ResponseFunctionToolCallOutputItem):
        return [
            ToolResultsMessage(
                results=[
                    ToolRunResult(
                        run_id=item.call_id,
                        output=item.output,
                    )
                ]
            )
        ]

    return [] # 暂不处理其他类型, 包括 ResponseReasoningItem


def _run_request_from_response_tool_call_item(
    item: ResponseFunctionToolCallItem,
) -> ToolRunRequest:
    return ToolRunRequest(
        run_id=item.call_id,
        tool_name=item.name,
        arguments=_parse_tool_arguments(item.arguments),
        raw_arguments=item.arguments,
    )


def _response_tool_call_param_from_run_request(
    tool_call: ToolRunRequest,
) -> ResponseFunctionToolCallParam:
    raw_arguments = tool_call.raw_arguments
    if raw_arguments is None:
        raw_arguments = json.dumps(tool_call.arguments, ensure_ascii=False)
    return ResponseFunctionToolCallParam(
        arguments=raw_arguments,
        call_id=tool_call.run_id,
        name=tool_call.tool_name,
        type="function_call",
    )


def _convert_stream_event(event: ResponseStreamEvent) -> ModelEvent | None:
    if isinstance(event, ResponseOutputItemDoneEvent):
        if isinstance(event.item, ResponseFunctionToolCall):
            return ModelToolCallEvent(tool_call=_run_request_from_sdk_tool_call(event.item))
        return None

    if isinstance(event, ResponseOutputItemAddedEvent):
        if isinstance(event.item, ResponseOutputMessage) and event.item.type == "message":
            return ModelTextStartEvent()
        return None

    if isinstance(event, ResponseTextDeltaEvent):
        return ModelTextDeltaEvent(delta=event.delta)

    if isinstance(event, ResponseTextDoneEvent):
        return ModelTextDoneEvent(text=event.text)

    return None


async def ahistory(response: Response, /, *, client: AsyncArk) -> list[ModelMessage]:
    """获取当前response id对应的消息历史，以及当前的output"""

    # 根据当前id 获取之前的历史对话，不包含当前id的结果
    history_items_list = await alist_all_items(response.id, client=client)

    #TODO：将当前id的输出结果加上，隐患，后续需要处理，可能有多个output
    if response.output:  # 先判断 self.output 非空（避免空列表/None）
        for output_item in response.output:
            # TODO：目前只处理指定的两种类型，过滤其他类型
            if isinstance(output_item, (ResponseOutputMessage, ResponseReasoningItem, ResponseFunctionToolCall)):
                if isinstance(output_item, ResponseFunctionToolCall):
                    # 工具调用，需要转换为 ResponseFunctionToolCallItem
                    assert output_item.id is not None, "function call id must be provided"
                    new_item = ResponseFunctionToolCallItem(
                        id=output_item.id,
                        type="function_call",
                        name=output_item.name,
                        arguments=output_item.arguments,
                        status="completed",
                        call_id=output_item.call_id,
                    )
                    history_items_list.append(new_item)
                    continue

                history_items_list.append(output_item)  # pyright: ignore[reportArgumentType], 火山的类型 bug

    history: list[ModelMessage] = []
    for item in history_items_list:
        history.extend(_model_messages_from_response_item(item)) # pyright: ignore[reportArgumentType]
    return history


class _ResponsesModelStream(ModelStream[ResponsesModelState]):
    def __init__(
        self,
        stream: AsyncStream[ResponseStreamEvent],
    ) -> None:
        self._stream = stream
        self._response: ModelResponse[ResponsesModelState] | None = None

    @property
    def response(self) -> ModelResponse[ResponsesModelState] | None:
        return self._response

    async def __aiter__(self) -> AsyncIterator[ModelEvent]:
        async for event in self._stream:
            if isinstance(event, ResponseCompletedEvent):
                self._response = ModelResponse[ResponsesModelState](
                    text=_extract_text(event.response),
                    tool_calls=_extract_tool_calls(event.response),
                    state=ResponsesModelState(response=event.response),
                )
                continue

            model_event = _convert_stream_event(event)
            if model_event is not None:
                yield model_event

        await self._stream.close()


class ResponsesModelAPI(ModelAPI[ResponsesModelState]):

    def __init__(
        self,
        *,
        client: AsyncArk,
        model: str,
    ) -> None:
        self.client = client
        self.model = model

    @classmethod
    def initial_state(
        cls,
        *,
        system_prompt: str | None = None,
    ) -> ResponsesModelState:
        return ResponsesModelState(system_prompt=system_prompt)

    def _build_kwargs(self, call_params: ModelCallParams | None) -> dict[str, Any]:
        if call_params is None:
            call_params = ModelCallParams()
        # TODO：转换为sdk的params
        result = ResponseParams(
            temperature=call_params.temperature,
            top_p=call_params.top_p,
            max_output_tokens=call_params.max_output_tokens,
            thinking=Thinking(type=call_params.thinking) if call_params.thinking else None,
        ).model_dump(exclude_none=True)

        if call_params.extra:
            safe_update(result, call_params.extra)

        return result

    def _prepare_call(
        self,
        input: ModelInput,
        state: ResponsesModelState,
    ) -> tuple[list[ResponseInputItemParam], str | None]:
        resp_input = _response_input_params_from_input(input)
        final_input = resp_input
        previous_response_id: str | None = None

        if state.history is not None:
            history_input = _response_input_params_from_history(state.history)
            final_input = [*history_input, *resp_input]
        elif state.response is not None:
            previous_response_id = state.response.id
        elif state.system_prompt:
            final_input = [system_msg(state.system_prompt), *resp_input]

        return final_input, previous_response_id

    async def invoke(
        self,
        input: ModelInput,
        *,
        state: ResponsesModelState,
        tools: Sequence[ToolProtocol[BaseModel]] | None = None,
        params: ModelCallParams | None = ModelCallParams(),
    ) -> ModelResponse[ResponsesModelState]:
        final_input, previous_response_id = self._prepare_call(input, state)
        kwargs = self._build_kwargs(params)
        resp_tools = [_response_tool_param_from_tool(t) for t in tools] if tools else None

        assert "format" not in kwargs, "format must not be specified in kwargs in invoke."
        assert "previous_response_id" not in kwargs, "previous_response_id should not be in kwargs"
        kwargs.pop("stream", None)

        raw_response = cast(
            Response,
            await self.client.responses.create(
                model=self.model,
                input=final_input,
                tools=resp_tools,
                previous_response_id=previous_response_id,
                **kwargs,
            ),
        )

        return ModelResponse[ResponsesModelState](
            text=_extract_text(raw_response),
            tool_calls=_extract_tool_calls(raw_response),
            state=ResponsesModelState(response=raw_response),
        )

    async def structured_output[T](
        self,
        input: ModelInput,
        *,
        output_type: type[T],
        state: ResponsesModelState,
        params: ModelCallParams | None = ModelCallParams(),
    ) -> StructuredModelResponse[T, ResponsesModelState]:
        final_input, previous_response_id = self._prepare_call(input, state)
        kwargs = self._build_kwargs(params)
        output_adapter = TypeAdapter(output_type)

        assert "format" not in kwargs, "format must not be specified in kwargs in structured_output."
        assert "previous_response_id" not in kwargs, "previous_response_id should not be in kwargs"
        kwargs.pop("stream", None)
        kwargs.pop("caching", None)
        #TODO 待火山SDK兼容: The SDK's Responses TypedDict has not caught up with the documented
        # json_schema shape yet, so pass the official text. object directly.
        kwargs["text"] = ResponseTextConfigParam(
            format=cast(
                Any,
                {
                    "type": "json_schema",
                    "name": "response",
                    "schema": output_adapter.json_schema(),
                    "strict": True,
                },
            )
        )

        raw_response = cast(
            Response,
            await self.client.responses.create(
                model=self.model,
                input=final_input,
                previous_response_id=previous_response_id,
                **kwargs,
            ),
        )

        raw_text = _extract_text(raw_response)
        parsed: T | None
        metadata: dict[str, object] = {}
        try:
            if raw_text is None:
                raise ValueError("structured output response has no text")
            parsed = output_adapter.validate_json(raw_text)
        except (ValidationError, ValueError) as exc:
            parsed = None
            metadata["structured_output_error"] = str(exc)

        return StructuredModelResponse[T, ResponsesModelState](
            text=raw_text,
            tool_calls=[],
            state=ResponsesModelState(response=raw_response),
            metadata=metadata,
            parsed=parsed,
        )

    async def stream(
        self,
        input: ModelInput,
        *,
        state: ResponsesModelState,
        tools: Sequence[ToolProtocol[BaseModel]] | None = None,
        params: ModelCallParams | None = ModelCallParams(),
    ) -> ModelStream[ResponsesModelState]:
        final_input, previous_response_id = self._prepare_call(input, state)
        kwargs = self._build_kwargs(params)
        resp_tools = [_response_tool_param_from_tool(t) for t in tools] if tools else None

        assert "format" not in kwargs, "format must not be specified in kwargs in stream."
        assert "previous_response_id" not in kwargs, "previous_response_id should not be in kwargs"
        kwargs.pop("stream", None)  # 由本函数固定为 True

        raw_stream = cast(
            AsyncStream[ResponseStreamEvent], 
            await self.client.responses.create(
                model=self.model,
                input=final_input,
                tools=resp_tools,
                previous_response_id=previous_response_id,
                stream=True,
                **kwargs,
            )
        )

        return _ResponsesModelStream(raw_stream)

    async def dump_state(
        self,
        state: ResponsesModelState,
    ) -> ModelStateDump:
        if state.response is None:
            forked = state
        else:
            history = await ahistory(state.response, client=self.client)
            forked = ResponsesModelState(history=history)

        payload = _ResponsesStatePayload(
            history=forked.history,
            system_prompt=forked.system_prompt,
        )
        serialized = payload.model_dump_json(exclude_none=True)

        return ModelStateDump(
            format=_RESPONSES_STATE_DUMP_FORMAT,
            format_version=_RESPONSES_STATE_DUMP_FORMAT_VERSION,
            serialized=serialized,
            metadata={"model": self.model},
        )

    async def history(
        self,
        state: ResponsesModelState,
    ) -> list[ModelMessage]:
        if state.history is not None:
            return list(state.history)
        if state.system_prompt is not None:
            return [SystemMessage(text=state.system_prompt)]
        if state.response is not None:
            return await ahistory(state.response, client=self.client)
        return []

    def state_from_history(
        self,
        history: Sequence[ModelMessage],
    ) -> ResponsesModelState:
        return ResponsesModelState(history=list(history))

    def restore_state(
        self,
        dump: ModelStateDump,
    ) -> ResponsesModelState:
        if dump.format != _RESPONSES_STATE_DUMP_FORMAT:
            raise ValueError(f"Unsupported dump format: {dump.format}")
        if dump.format_version != _RESPONSES_STATE_DUMP_FORMAT_VERSION:
            raise ValueError(f"Unsupported dump format version: {dump.format_version}")

        payload = _ResponsesStatePayload.model_validate_json(dump.serialized)
        return ResponsesModelState(
            history=payload.history,
            system_prompt=payload.system_prompt,
        )
