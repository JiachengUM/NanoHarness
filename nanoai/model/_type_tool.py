from typing import Any

from openai.types.chat import ChatCompletionMessageToolCall, ChatCompletionToolParam
from pydantic import TypeAdapter
from typing_extensions import TypedDict
from functools import lru_cache
import dataclasses
from types import GenericAlias
from typing import (
    Sequence,
    is_typeddict,
)
from pydantic import BaseModel
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaValue
from pydantic_core import core_schema


def is_model_like(type_: Any) -> bool:
    """Check if something is a pydantic model, dataclass or typedict.

    These should all generate a JSON Schema with `{"type": "object"}` and therefore be usable directly as
    function parameters.
    """
    return (
        isinstance(type_, type)
        and not isinstance(type_, GenericAlias)
        and (
            issubclass(type_, BaseModel) or dataclasses.is_dataclass(type_) or is_typeddict(type_)
        )  # pyright: ignore[reportUnknownArgumentType]
    )


type ObjectJsonSchema = dict[str, Any]


def check_object_json_schema(schema: JsonSchemaValue) -> ObjectJsonSchema:

    if schema.get("type") == "object":
        return schema
    elif schema.get("$ref") is not None:
        maybe_result = schema.get("$defs", {}).get(schema["$ref"][8:])  # This removes the initial "#/$defs/".

        if "'$ref': '#/$defs/" in str(maybe_result):
            return schema  # We can't remove the $defs because the schema contains other references
        return maybe_result
    else:
        raise ValueError("Schema must be an object")


class GenerateToolJsonSchema(GenerateJsonSchema):
    def typed_dict_schema(self, schema: core_schema.TypedDictSchema) -> JsonSchemaValue:
        s = super().typed_dict_schema(schema)
        total = schema.get("total")
        if "additionalProperties" not in s and (total is True or total is None):
            s["additionalProperties"] = False
        return s

    def _named_required_fields_schema(self, named_required_fields: Sequence[tuple[str, bool, Any]]) -> JsonSchemaValue:
        # Remove largely-useless property titles
        s = super()._named_required_fields_schema(named_required_fields)
        for p in s.get("properties", {}):
            s["properties"][p].pop("title", None)
        return s


DEFAULT_TOOL_DESCRIPTION = "生成能描述{type_name}类型的对象"


class _BaseTypeTool[T]:
    def __init__(
        self,
        _type: type[T],
        description: str | None = None,
        parameters_json_schema: dict[str, Any] | None = None,
        strict: bool = True,
        type_adapter: TypeAdapter[T] | None = None,
    ):
        self._type = _type
        self.type_adapter = type_adapter or TypeAdapter(_type)

        if parameters_json_schema is None:
            assert False, "parameters_json_schema is None, 不work, 需要使用GeneralTypeTool中的方式。不知道为什么。"
            parameters_json_schema = self.type_adapter.json_schema()

        self.description = description or DEFAULT_TOOL_DESCRIPTION.format(type_name=_type.__name__)
        self.parameters_json_schema = parameters_json_schema
        self.strict = strict

    @property
    def name(self) -> str:
        return f"generator_of_{self._type.__name__}"

    @property
    def tool_param(self) -> ChatCompletionToolParam:
        return ChatCompletionToolParam(
            {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": self.parameters_json_schema,
                    "strict": self.strict,
                },
            }
        )

    def execute(self, tool_call: ChatCompletionMessageToolCall) -> T:
        assert tool_call.function.name == self.name
        assert tool_call.function.arguments is not None

        obj = self.type_adapter.validate_json(tool_call.function.arguments)
        
        return obj


class GeneralTypeTool[T](_BaseTypeTool[T]):
    outer_typed_dict_key: str
    _dict_adapter: TypeAdapter[Any]

    def __init__(self, _type: type[T], strict: bool = True):
        # Store the dict adapter separately
        response_data_typed_dict = TypedDict(  # noqa: UP013
            "response_data_typed_dict",
            {"response": _type},  # pyright: ignore[reportInvalidTypeForm]
        )
        self.outer_typed_dict_key = "response"

        self._dict_adapter = dict_adapter = TypeAdapter(response_data_typed_dict)
        # noinspection PyArgumentList
        parameters_json_schema = check_object_json_schema(
            dict_adapter.json_schema(schema_generator=GenerateToolJsonSchema)
        )

        # including `response_data_typed_dict` as a title here doesn't add anything and could confuse the LLM
        parameters_json_schema.pop("title")
        tool_description = parameters_json_schema.pop("description", None)

        super().__init__(
            _type=_type, description=tool_description, parameters_json_schema=parameters_json_schema, strict=strict
        )

    def execute(self, tool_call: ChatCompletionMessageToolCall) -> T:
        # start_time = time.time()
        obj = self._dict_adapter.validate_json(tool_call.function.arguments)
        # end_time = time.time()
        # print(f"执行type_adapter时间: {end_time - start_time:.3f} 秒")

        # TODO: 如果self._type == tuple，按说需要检查tuple的元素个数和元素类型是否符合要求。
        # 因为无法在__init__中声明“元素个数和类型的信息”。似乎无法做到这一点。
        # 这样的话，有两种方案：改用BaseModel类型（感觉这样更好），或者延迟到具体task的execute中检查。

        return obj[self.outer_typed_dict_key]


class ModeLikeTypeTool[T](_BaseTypeTool[T]):
    def __init__(self, _type: type[T]):
        assert is_model_like(_type)

        type_adapter = TypeAdapter(_type)
        parameters_json_schema = type_adapter.json_schema(schema_generator=GenerateToolJsonSchema)
        assert parameters_json_schema.get("type") == "object"

        tool_description = parameters_json_schema.pop("description", None)

        super().__init__(
            _type=_type,
            description=tool_description,
            parameters_json_schema=parameters_json_schema,
            type_adapter=type_adapter,
        )


@lru_cache(maxsize=128)  # 限制缓存大小，避免内存泄漏
def create_type_tool[T](_type: type[T]) -> _BaseTypeTool[T]:
    if is_model_like(_type):
        return ModeLikeTypeTool(_type)
    else:
        return GeneralTypeTool(_type)
