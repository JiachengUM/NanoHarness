"""Base classes and utilities for LangChain tools."""

from __future__ import annotations

import functools
import inspect
import textwrap
import logging
import typing
import warnings
from abc import abstractmethod

from collections.abc import Callable  # noqa: TC003
from types import GenericAlias
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
    get_args,
    get_origin,
)

import typing_extensions
from pydantic import (
    BaseModel,
    ConfigDict,
    PydanticDeprecationWarning,
    ValidationError,
    validate_arguments,
    create_model,
)
from pydantic.fields import FieldInfo

import asyncer

# from langchain_core.utils.function_calling import (
#     _parse_google_docstring,
#     _py_38_safe_origin,
# )

# source code is copied below

import collections.abc

_ORIGIN_MAP: dict[type, Any] = {
    dict: dict,
    list: list,
    tuple: tuple,
    set: set,
    collections.abc.Iterable: typing.Iterable,
    collections.abc.Mapping: typing.Mapping,
    collections.abc.Sequence: typing.Sequence,
    collections.abc.MutableMapping: typing.MutableMapping,
}

_MIN_DOCSTRING_BLOCKS = 2


def _parse_google_docstring(
    docstring: str | None,
    args: list[str],
    *,
    error_on_invalid_docstring: bool = False,
) -> tuple[str, dict]:
    """Parse the function and argument descriptions from the docstring of a function.

    Assumes the function docstring follows Google Python style guide.

    Args:
        docstring: The docstring to parse.
        args: The list of argument names to extract descriptions for.
        error_on_invalid_docstring: Whether to raise an error if the docstring is
            invalid.

    Returns:
        A tuple of the function description and a dictionary of argument descriptions.
    """
    if docstring:
        docstring_blocks = docstring.split("\n\n")
        if error_on_invalid_docstring:
            filtered_annotations = {
                arg
                for arg in args
                if arg not in {"run_manager", "callbacks", "runtime", "return"}
            }
            if filtered_annotations and (
                len(docstring_blocks) < _MIN_DOCSTRING_BLOCKS
                or not any(block.startswith("Args:") for block in docstring_blocks[1:])
            ):
                msg = "Found invalid Google-Style docstring."
                raise ValueError(msg)
        descriptors = []
        args_block = None
        past_descriptors = False
        for block in docstring_blocks:
            if block.startswith("Args:"):
                args_block = block
                break
            if block.startswith(("Returns:", "Example:")):
                # Don't break in case Args come after
                past_descriptors = True
            elif not past_descriptors:
                descriptors.append(block)
            else:
                continue
        description = " ".join(descriptors).strip()
    else:
        if error_on_invalid_docstring:
            msg = "Found invalid Google-Style docstring."
            raise ValueError(msg)
        description = ""
        args_block = None
    arg_descriptions = {}
    if args_block:
        arg = None
        for line in args_block.split("\n")[1:]:
            if ":" in line:
                arg, desc = line.split(":", maxsplit=1)
                arg = arg.strip()
                arg_name, _, annotations_ = arg.partition(" ")
                if annotations_.startswith("(") and annotations_.endswith(")"):
                    arg = arg_name
                arg_descriptions[arg] = desc.strip()
            elif arg:
                arg_descriptions[arg] += " " + line.strip()
    return description, arg_descriptions


def _py_38_safe_origin(origin: type) -> type:
    return cast("type", _ORIGIN_MAP.get(origin, origin))


# from langchain_core.utils.pydantic import (
#     TypeBaseModel,
#     _create_subset_model,
#     get_fields,
#     is_basemodel_subclass,
# )

# source code is copied below

TypeBaseModel = type[BaseModel]


def _create_subset_model(
    name: str,
    model: type[BaseModel],
    field_names: list[str],
    *,
    descriptions: dict | None = None,
    fn_description: str | None = None,
) -> type[BaseModel]:
    """Create a Pydantic model with a subset of the model fields."""
    descriptions_ = descriptions or {}
    fields = {}
    for field_name in field_names:
        field = model.model_fields[field_name]
        description = descriptions_.get(field_name, field.description)
        field_info = FieldInfo(description=description, default=field.default)
        if field.metadata:
            field_info.metadata = field.metadata
        fields[field_name] = (field.annotation, field_info)

    rtn = cast(
        "type[BaseModel]",
        create_model(  # type: ignore[call-overload]
            name, **fields, __config__=ConfigDict(arbitrary_types_allowed=True)
        ),
    )

    # TODO(0.3): Determine if there is a more "pydantic" way to preserve annotations.
    # This is done to preserve __annotations__ when working with pydantic 2.x
    # and using the Annotated type with TypedDict.
    # Comment out the following line, to trigger the relevant test case.
    selected_annotations = [
        (name, annotation)
        for name, annotation in model.__annotations__.items()
        if name in field_names
    ]

    rtn.__annotations__ = dict(selected_annotations)
    rtn.__doc__ = textwrap.dedent(fn_description or model.__doc__ or "")
    return rtn


def get_fields(
    model: type[BaseModel] | BaseModel,
) -> dict[str, FieldInfo]:
    """Return the field names of a Pydantic model.

    Args:
        model: The Pydantic model or instance.

    Raises:
        TypeError: If the model is not a Pydantic model.
    """
    if not isinstance(model, type):
        model = type(model)
    if issubclass(model, BaseModel):
        return model.model_fields

    msg = f"Expected a Pydantic model. Got {model}"
    raise TypeError(msg)


def is_basemodel_subclass(cls: type) -> bool:
    """Check if the given class is a subclass of Pydantic `BaseModel`.

    Check if the given class is a subclass of any of the following:

    * `pydantic.BaseModel` in Pydantic 2.x
    * `pydantic.v1.BaseModel` in Pydantic 2.x

    Returns:
        `True` if the given class is a subclass of Pydantic `BaseModel`.
    """
    # Before we can use issubclass on the cls we need to check if it is a class
    if not inspect.isclass(cls) or isinstance(cls, GenericAlias):
        return False

    return issubclass(cls, BaseModel)


if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

FILTERED_ARGS = ("run_manager", "callbacks")
TOOL_MESSAGE_BLOCK_TYPES = (
    "text",
    "image_url",
    "image",
    "json",
    "search_result",
    "custom_tool_call_output",
    "document",
    "file",
)

_logger = logging.getLogger(__name__)


class SchemaAnnotationError(TypeError):
    """Raised when `args_schema` is missing or has an incorrect type annotation."""


def _is_annotated_type(typ: type[Any]) -> bool:
    """Check if a type is an `Annotated` type.

    Args:
        typ: The type to check.

    Returns:
        `True` if the type is an `Annotated` type, `False` otherwise.
    """
    return get_origin(typ) in {typing.Annotated, typing_extensions.Annotated}


def _get_annotation_description(arg_type: type) -> str | None:
    """Extract description from an `Annotated` type.

    Checks for string annotations and `FieldInfo` objects with descriptions.

    Args:
        arg_type: The type to extract description from.

    Returns:
        The description string if found, `None` otherwise.
    """
    if _is_annotated_type(arg_type):
        annotated_args = get_args(arg_type)
        for annotation in annotated_args[1:]:
            if isinstance(annotation, str):
                return annotation
            if isinstance(annotation, FieldInfo) and annotation.description:
                return annotation.description
    return None


def _parse_python_function_docstring(
    function: Callable, annotations: dict, *, error_on_invalid_docstring: bool = False
) -> tuple[str, dict]:
    """Parse function and argument descriptions from a docstring.

    Assumes the function docstring follows Google Python style guide.

    Args:
        function: The function to parse the docstring from.
        annotations: Type annotations for the function parameters.
        error_on_invalid_docstring: Whether to raise an error on invalid docstring.

    Returns:
        A tuple containing the function description and argument descriptions.
    """
    docstring = inspect.getdoc(function)
    return _parse_google_docstring(
        docstring,
        list(annotations),
        error_on_invalid_docstring=error_on_invalid_docstring,
    )


def _validate_docstring_args_against_annotations(
    arg_descriptions: dict, annotations: dict
) -> None:
    """Validate that docstring arguments match function annotations.

    Args:
        arg_descriptions: Arguments described in the docstring.
        annotations: Type annotations from the function signature.

    Raises:
        ValueError: If a docstring argument is not found in function signature.
    """
    for docstring_arg in arg_descriptions:
        if docstring_arg not in annotations:
            msg = f"Arg {docstring_arg} in docstring not found in function signature."
            raise ValueError(msg)


def _infer_arg_descriptions(
    fn: Callable,
    *,
    parse_docstring: bool = False,
    error_on_invalid_docstring: bool = False,
) -> tuple[str, dict]:
    """Infer argument descriptions from function docstring and annotations.

    Args:
        fn: The function to infer descriptions from.
        parse_docstring: Whether to parse the docstring for descriptions.
        error_on_invalid_docstring: Whether to raise error on invalid docstring.

    Returns:
        A tuple containing the function description and argument descriptions.
    """
    annotations = typing.get_type_hints(fn, include_extras=True)
    if parse_docstring:
        description, arg_descriptions = _parse_python_function_docstring(
            fn, annotations, error_on_invalid_docstring=error_on_invalid_docstring
        )
    else:
        description = inspect.getdoc(fn) or ""
        arg_descriptions = {}
    if parse_docstring:
        _validate_docstring_args_against_annotations(arg_descriptions, annotations)
    for arg, arg_type in annotations.items():
        if arg in arg_descriptions:
            continue
        if desc := _get_annotation_description(arg_type):
            arg_descriptions[arg] = desc
    return description, arg_descriptions


class _SchemaConfig:
    """Configuration for Pydantic models generated from function signatures."""

    extra: str = "forbid"
    """Whether to allow extra fields in the model."""

    arbitrary_types_allowed: bool = True
    """Whether to allow arbitrary types in the model."""


def create_schema_from_function(
    model_name: str,
    func: Callable,
    *,
    filter_args: Sequence[str] | None = None,
    parse_docstring: bool = False,
    error_on_invalid_docstring: bool = False,
    include_injected: bool = True,
) -> type[BaseModel]:
    """Create a Pydantic schema from a function's signature.

    Args:
        model_name: Name to assign to the generated Pydantic schema.
        func: Function to generate the schema from.
        filter_args: Optional list of arguments to exclude from the schema.

            Defaults to `FILTERED_ARGS`.
        parse_docstring: Whether to parse the function's docstring for descriptions
            for each argument.
        error_on_invalid_docstring: If `parse_docstring` is provided, configure
            whether to raise `ValueError` on invalid Google Style docstrings.
        include_injected: Whether to include injected arguments in the schema.

            Defaults to `True`, since we want to include them in the schema when
            *validating* tool inputs.

    Returns:
        A Pydantic model with the same arguments as the function.
    """
    sig = inspect.signature(func)

    # https://docs.pydantic.dev/latest/usage/validation_decorator/
    with warnings.catch_warnings():
        # We are using deprecated functionality here.
        # This code should be re-written to simply construct a Pydantic model
        # using inspect.signature and create_model.
        warnings.simplefilter("ignore", category=PydanticDeprecationWarning)
        validated = validate_arguments(func, config=_SchemaConfig)  # type: ignore[operator]

    # Let's ignore `self` and `cls` arguments for class and instance methods
    # If qualified name has a ".", then it likely belongs in a class namespace
    in_class = bool(func.__qualname__ and "." in func.__qualname__)

    has_args = False
    has_kwargs = False

    for param in sig.parameters.values():
        if param.kind == param.VAR_POSITIONAL:
            has_args = True
        elif param.kind == param.VAR_KEYWORD:
            has_kwargs = True

    inferred_model = validated.model

    if filter_args:
        filter_args_ = filter_args
    else:
        # Handle classmethods and instance methods
        existing_params: list[str] = list(sig.parameters.keys())
        if existing_params and existing_params[0] in {"self", "cls"} and in_class:
            filter_args_ = [existing_params[0], *list(FILTERED_ARGS)]
        else:
            filter_args_ = list(FILTERED_ARGS)

        for existing_param in existing_params:
            if not include_injected and _is_injected_arg_type(
                sig.parameters[existing_param].annotation
            ):
                filter_args_.append(existing_param)  # type: ignore

    description, arg_descriptions = _infer_arg_descriptions(
        func,
        parse_docstring=parse_docstring,
        error_on_invalid_docstring=error_on_invalid_docstring,
    )
    # Pydantic adds placeholder virtual fields we need to strip
    valid_properties = []
    for field in get_fields(inferred_model):
        if not has_args and field == "args":
            continue
        if not has_kwargs and field == "kwargs":
            continue

        if field == "v__duplicate_kwargs":  # Internal pydantic field
            continue

        if field not in filter_args_:
            valid_properties.append(field)

    return _create_subset_model(
        model_name,
        inferred_model,
        list(valid_properties),
        descriptions=arg_descriptions,
        fn_description=description,
    )


class ToolException(Exception):  # noqa: N818
    """Exception thrown when a tool execution error occurs.

    This exception allows tools to signal errors without stopping the agent.

    The error is handled according to the tool's `handle_tool_error` setting, and the
    result is returned as an observation to the agent.
    """


ArgsSchema = TypeBaseModel | dict[str, Any]

_EMPTY_SET: frozenset[str] = frozenset()


class BaseTool(BaseModel):
    """Base class for all LangChain tools.

    This abstract class defines the interface that all LangChain tools must implement.

    Tools are components that can be called by agents to perform specific actions.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Validate the tool class definition during subclass creation.

        Args:
            **kwargs: Additional keyword arguments passed to the parent class.

        Raises:
            SchemaAnnotationError: If `args_schema` has incorrect type annotation.
        """
        super().__init_subclass__(**kwargs)

        args_schema_type = cls.__annotations__.get("args_schema", None)

        if args_schema_type is not None and args_schema_type == BaseModel:
            # Throw errors for common mis-annotations.
            # TODO: Use get_args / get_origin and fully
            # specify valid annotations.
            typehint_mandate = """
class ChildTool(BaseTool):
    ...
    args_schema: Type[BaseModel] = SchemaClass
    ..."""
            name = cls.__name__
            msg = (
                f"Tool definition for {name} must include valid type annotations"
                f" for argument 'args_schema' to behave as expected.\n"
                f"Expected annotation of 'Type[BaseModel]'"
                f" but got '{args_schema_type}'.\n"
                f"Expected class looks like:\n"
                f"{typehint_mandate}"
            )
            raise SchemaAnnotationError(msg)

    name: str
    """The unique name of the tool that clearly communicates its purpose."""

    description: str
    """Used to tell the model how/when/why to use the tool.

    You can provide few-shot examples as a part of the description.
    """

    args_schema: type[BaseModel]  # FIXME: 为了对齐 protocol 定义
    # args_schema: Annotated[ArgsSchema | None, SkipValidation] = Field(
    #     default=None, description="The tool schema."
    # )
    """Pydantic model class to validate and parse the tool's input arguments.

    Args schema should be either:

    - A subclass of `pydantic.BaseModel`.
    - A subclass of `pydantic.v1.BaseModel` if accessing v1 namespace in pydantic 2
    - A JSON schema dict
    """

    return_direct: bool = False
    """Whether to return the tool's output directly.

    Setting this to `True` means that after the tool is called, the `AgentExecutor` will
    stop looping.
    """

    verbose: bool = False
    """Whether to log the tool's progress."""

    tags: list[str] | None = None
    """Optional list of tags associated with the tool.

    These tags will be associated with each call to this tool,
    and passed as arguments to the handlers defined in `callbacks`.

    You can use these to, e.g., identify a specific instance of a tool with its use
    case.
    """

    metadata: dict[str, Any] | None = None
    """Optional metadata associated with the tool.

    This metadata will be associated with each call to this tool,
    and passed as arguments to the handlers defined in `callbacks`.

    You can use these to, e.g., identify a specific instance of a tool with its usecase.
    """

    handle_tool_error: bool | str | Callable[[ToolException], str] | None = False
    """Handle the content of the `ToolException` thrown."""

    handle_validation_error: bool | str | Callable[[ValidationError], str] | None = (
        False
    )
    """Handle the content of the `ValidationError` thrown."""

    response_format: Literal["content", "content_and_artifact"] = "content"
    """The tool response format.

    If `'content'` then the output of the tool is interpreted as the contents of a
    `ToolMessage`. If `'content_and_artifact'` then the output is expected to be a
    two-tuple corresponding to the `(content, artifact)` of a `ToolMessage`.
    """

    extras: dict[str, Any] | None = None
    """Optional provider-specific extra fields for the tool.

    This is used to pass provider-specific configuration that doesn't fit into
    standard tool fields.

    Example:
        Anthropic-specific fields like [`cache_control`](https://docs.langchain.com/oss/python/integrations/chat/anthropic#prompt-caching),
        [`defer_loading`](https://docs.langchain.com/oss/python/integrations/chat/anthropic#tool-search),
        or `input_examples`.

        ```python
        @tool(extras={"defer_loading": True, "cache_control": {"type": "ephemeral"}})
        def my_tool(x: str) -> str:
            return x
        ```
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the tool.

        Raises:
            TypeError: If `args_schema` is not a subclass of pydantic `BaseModel` or
                `dict`.
        """
        if (
            "args_schema" in kwargs
            and kwargs["args_schema"] is not None
            and not is_basemodel_subclass(kwargs["args_schema"])
            and not isinstance(kwargs["args_schema"], dict)
        ):
            msg = (
                "args_schema must be a subclass of pydantic BaseModel or "
                f"a JSON schema dict. Got: {kwargs['args_schema']}."
            )
            raise TypeError(msg)
        super().__init__(**kwargs)

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    @property
    def is_single_input(self) -> bool:
        """Check if the tool accepts only a single input argument.

        Returns:
            `True` if the tool has only one input argument, `False` otherwise.
        """
        keys = {k for k in self.args if k != "kwargs"}
        return len(keys) == 1

    @property
    def args(self) -> dict:
        """Get the tool's input arguments schema.

        Returns:
            `dict` containing the tool's argument properties.
        """
        if isinstance(self.args_schema, dict):
            json_schema = self.args_schema
        else:
            input_schema = self.tool_call_schema
            if isinstance(input_schema, dict):
                json_schema = input_schema
            else:
                json_schema = input_schema.model_json_schema()
        return cast("dict", json_schema["properties"])

    @property
    def tool_call_schema(self) -> ArgsSchema:
        """Get the schema for tool calls, excluding injected arguments.

        Returns:
            The schema that should be used for tool calls from language models.
        """
        if isinstance(self.args_schema, dict):
            if self.description:
                return {
                    **self.args_schema,
                    "description": self.description,
                }

            return self.args_schema

        full_schema = self.get_input_schema()
        fields = []
        for name, type_ in get_all_basemodel_annotations(full_schema).items():
            if not _is_injected_arg_type(type_):
                fields.append(name)
        return _create_subset_model(
            self.name, full_schema, fields, fn_description=self.description
        )

    @functools.cached_property
    def _injected_args_keys(self) -> frozenset[str]:
        # Base implementation doesn't manage injected args
        return _EMPTY_SET

    # --- Runnable ---

    # @override
    def get_input_schema(self) -> type[BaseModel]:
        """The tool's input schema.

        Args:
            config: The configuration for the tool.

        Returns:
            The input schema for the tool.
        """
        # TODO: 这里调用了Runnable的get_input_schema，可能有用
        # if self.args_schema is not None:
        #     if isinstance(self.args_schema, dict):
        #         return super().get_input_schema()
        #     return self.args_schema
        return create_schema_from_function(self.name, self._run)

    # --- Tool ---

    def _parse_input(
        self, tool_input: str | dict, tool_call_id: str | None
    ) -> str | dict[str, Any]:
        """Parse and validate tool input using the args schema.

        Args:
            tool_input: The raw input to the tool.
            tool_call_id: The ID of the tool call, if available.

        Returns:
            The parsed and validated input.

        Raises:
            ValueError: If `string` input is provided with JSON schema `args_schema`.
            ValueError: If `InjectedToolCallId` is required but `tool_call_id` is not
                provided.
            TypeError: If `args_schema` is not a Pydantic `BaseModel` or dict.
        """
        input_args = self.args_schema

        if isinstance(tool_input, str):
            if input_args is not None:
                if isinstance(input_args, dict):
                    msg = (
                        "String tool inputs are not allowed when "
                        "using tools with JSON schema args_schema."
                    )
                    raise ValueError(msg)
                key_ = next(iter(get_fields(input_args).keys()))
                if issubclass(input_args, BaseModel):
                    input_args.model_validate({key_: tool_input})
                else:
                    msg = f"args_schema must be a Pydantic BaseModel, got {input_args}"
                    raise TypeError(msg)
            return tool_input

        if input_args is not None:
            if isinstance(input_args, dict):
                return tool_input
            if issubclass(input_args, BaseModel):
                # Check args_schema for InjectedToolCallId
                for k, v in get_all_basemodel_annotations(input_args).items():
                    if _is_injected_arg_type(v, injected_type=InjectedToolCallId):
                        if tool_call_id is None:
                            msg = (
                                "When tool includes an InjectedToolCallId "
                                "argument, tool must always be invoked with a full "
                                "model ToolCall of the form: {'args': {...}, "
                                "'name': '...', 'type': 'tool_call', "
                                "'tool_call_id': '...'}"
                            )
                            raise ValueError(msg)
                        tool_input[k] = tool_call_id
                result = input_args.model_validate(tool_input)
                result_dict = result.model_dump()
            else:
                msg = (
                    f"args_schema must be a Pydantic BaseModel, got {self.args_schema}"
                )
                raise NotImplementedError(msg)

            # Include fields from tool_input, plus fields with explicit defaults.
            # This applies Pydantic defaults (like Field(default=1)) while excluding
            # synthetic "args"/"kwargs" fields that Pydantic creates for *args/**kwargs.
            field_info = get_fields(input_args)
            validated_input = {}
            for k in result_dict:
                if k in tool_input:
                    # Field was provided in input - include it (validated)
                    validated_input[k] = getattr(result, k)
                elif k in field_info and k not in ("args", "kwargs"):
                    # Check if field has an explicit default defined in the schema.
                    # Exclude "args"/"kwargs" as these are synthetic fields for variadic
                    # parameters that should not be passed as keyword arguments.
                    fi = field_info[k]
                    # Pydantic v2 uses is_required() method, v1 uses required attribute
                    has_default = (
                        not fi.is_required()
                        if hasattr(fi, "is_required")
                        else not getattr(fi, "required", True)
                    )
                    if has_default:
                        validated_input[k] = getattr(result, k)

            for k in self._injected_args_keys:
                if k in tool_input:
                    validated_input[k] = tool_input[k]
                elif k == "tool_call_id":
                    if tool_call_id is None:
                        msg = (
                            "When tool includes an InjectedToolCallId "
                            "argument, tool must always be invoked with a full "
                            "model ToolCall of the form: {'args': {...}, "
                            "'name': '...', 'type': 'tool_call', "
                            "'tool_call_id': '...'}"
                        )
                        raise ValueError(msg)
                    validated_input[k] = tool_call_id

            return validated_input

        return tool_input

    @abstractmethod
    def _run(self, *args: Any, **kwargs: Any) -> Any:
        """Use the tool.

        Add `run_manager: CallbackManagerForToolRun | None = None` to child
        implementations to enable tracing.

        Returns:
            The result of the tool execution.
        """

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:
        """Use the tool asynchronously.

        Add `run_manager: AsyncCallbackManagerForToolRun | None = None` to child
        implementations to enable tracing.

        Returns:
            The result of the tool execution.
        """

        return await asyncer.asyncify(self._run)(*args, **kwargs)
        # return await run_in_executor(None, self._run, *args, **kwargs)

    def _filter_injected_args(self, tool_input: dict) -> dict:
        """Filter out injected tool arguments from the input dictionary.

        Injected arguments are those annotated with `InjectedToolArg` or its
        subclasses, or arguments in `FILTERED_ARGS` like `run_manager` and callbacks.

        Args:
            tool_input: The tool input dictionary to filter.

        Returns:
            A filtered dictionary with injected arguments removed.
        """
        # Start with filtered args from the constant
        filtered_keys = set[str](FILTERED_ARGS)

        # Add injected args from function signature (e.g., ToolRuntime parameters)
        filtered_keys.update(self._injected_args_keys)

        # If we have an args_schema, use it to identify injected args
        if self.args_schema is not None:
            try:
                annotations = get_all_basemodel_annotations(self.args_schema)
                for field_name, field_type in annotations.items():
                    if _is_injected_arg_type(field_type):
                        filtered_keys.add(field_name)
            except Exception:
                # If we can't get annotations, just use FILTERED_ARGS
                _logger.debug(
                    "Failed to get args_schema annotations for filtering.",
                    exc_info=True,
                )

        # Filter out the injected keys from tool_input
        return {k: v for k, v in tool_input.items() if k not in filtered_keys}

    def _to_args_and_kwargs(
        self, tool_input: str | dict, tool_call_id: str | None
    ) -> tuple[tuple, dict]:
        """Convert tool input to positional and keyword arguments.

        Args:
            tool_input: The input to the tool.
            tool_call_id: The ID of the tool call, if available.

        Returns:
            A tuple of `(positional_args, keyword_args)` for the tool.

        Raises:
            TypeError: If the tool input type is invalid.
        """
        if (
            self.args_schema is not None
            and isinstance(self.args_schema, type)
            and is_basemodel_subclass(self.args_schema)
            and not get_fields(self.args_schema)
        ):
            # StructuredTool with no args
            return (), {}
        tool_input = self._parse_input(tool_input, tool_call_id)
        # For backwards compatibility, if run_input is a string,
        # pass as a positional argument.
        if isinstance(tool_input, str):
            return (tool_input,), {}
        if isinstance(tool_input, dict):
            # Make a shallow copy of the input to allow downstream code
            # to modify the root level of the input without affecting the
            # original input.
            # This is used by the tool to inject run time information like
            # the callback manager.
            return (), tool_input.copy()
        # This code path is not expected to be reachable.
        msg = f"Invalid tool input type: {type(tool_input)}"
        raise TypeError(msg)

    def run(
        self,
        tool_input: str | dict[str, Any],
        verbose: bool | None = None,  # noqa: FBT001
        start_color: str | None = "green",
        color: str | None = "green",
        *,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        run_name: str | None = None,
        run_id: uuid.UUID | None = None,
        tool_call_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run the tool.

        Args:
            tool_input: The input to the tool.
            verbose: Whether to log the tool's progress.
            start_color: The color to use when starting the tool.
            color: The color to use when ending the tool.
            tags: Optional list of tags associated with the tool.
            metadata: Optional metadata associated with the tool.
            run_name: The name of the run.
            run_id: The id of the run.
            tool_call_id: The id of the tool call.
            **kwargs: Keyword arguments to be passed to tool callbacks (event handler)

        Returns:
            The output of the tool.

        Raises:
            ToolException: If an error occurs during tool execution.
        """
        # Filter out injected arguments from callback inputs
        filtered_tool_input = (
            self._filter_injected_args(tool_input)
            if isinstance(tool_input, dict)
            else None
        )

        content = None
        artifact = None
        status = "success"
        error_to_raise: Exception | KeyboardInterrupt | None = None
        try:
            tool_args, tool_kwargs = self._to_args_and_kwargs(tool_input, tool_call_id)
            response = self._run(*tool_args, **tool_kwargs)
            if self.response_format == "content_and_artifact":
                msg = (
                    "Since response_format='content_and_artifact' "
                    "a two-tuple of the message content and raw tool output is "
                    f"expected. Instead, generated response is of type: "
                    f"{type(response)}."
                )
                if not isinstance(response, tuple):
                    error_to_raise = ValueError(msg)
                else:
                    try:
                        content, artifact = response
                    except ValueError:
                        error_to_raise = ValueError(msg)
            else:
                content = response
        except ValidationError as e:
            if not self.handle_validation_error:
                error_to_raise = e
            else:
                content = _handle_validation_error(e, flag=self.handle_validation_error)
                status = "error"
        except ToolException as e:
            if not self.handle_tool_error:
                error_to_raise = e
            else:
                content = _handle_tool_error(e, flag=self.handle_tool_error)
                status = "error"
        except (Exception, KeyboardInterrupt) as e:
            error_to_raise = e

        if error_to_raise:
            raise error_to_raise

        return content

    async def arun(
        self,
        tool_input: str | dict[str, Any],
        verbose: bool | None = None,  # noqa: FBT001
        start_color: str | None = "green",
        color: str | None = "green",
        *,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        run_name: str | None = None,
        run_id: uuid.UUID | None = None,
        tool_call_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run the tool asynchronously.

        Args:
            tool_input: The input to the tool.
            verbose: Whether to log the tool's progress.
            start_color: The color to use when starting the tool.
            color: The color to use when ending the tool.
            tags: Optional list of tags associated with the tool.
            metadata: Optional metadata associated with the tool.
            run_name: The name of the run.
            run_id: The id of the run.
            tool_call_id: The id of the tool call.
            **kwargs: Keyword arguments to be passed to tool callbacks

        Returns:
            The output of the tool.

        Raises:
            ToolException: If an error occurs during tool execution.
        """
        # Filter out injected arguments from callback inputs
        filtered_tool_input = (
            self._filter_injected_args(tool_input)
            if isinstance(tool_input, dict)
            else None
        )

        # Use filtered inputs for the input_str parameter as well
        tool_input_str = (
            tool_input
            if isinstance(tool_input, str)
            else str(
                filtered_tool_input if filtered_tool_input is not None else tool_input
            )
        )

        content = None
        artifact = None
        status = "success"
        error_to_raise: Exception | KeyboardInterrupt | None = None
        try:
            tool_args, tool_kwargs = self._to_args_and_kwargs(tool_input, tool_call_id)
            response = await self._arun(*tool_args, **tool_kwargs)
            if self.response_format == "content_and_artifact":
                msg = (
                    "Since response_format='content_and_artifact' "
                    "a two-tuple of the message content and raw tool output is "
                    f"expected. Instead, generated response is of type: "
                    f"{type(response)}."
                )
                if not isinstance(response, tuple):
                    error_to_raise = ValueError(msg)
                else:
                    try:
                        content, artifact = response
                    except ValueError:
                        error_to_raise = ValueError(msg)
            else:
                content = response
        except ValidationError as e:
            if not self.handle_validation_error:
                error_to_raise = e
            else:
                content = _handle_validation_error(e, flag=self.handle_validation_error)
                status = "error"
        except ToolException as e:
            if not self.handle_tool_error:
                error_to_raise = e
            else:
                content = _handle_tool_error(e, flag=self.handle_tool_error)
                status = "error"
        except (Exception, KeyboardInterrupt) as e:
            error_to_raise = e

        if error_to_raise:
            raise error_to_raise

        return content


def _handle_validation_error(
    e: ValidationError,
    *,
    flag: Literal[True] | str | Callable[[ValidationError], str],
) -> str:
    """Handle validation errors based on the configured flag.

    Args:
        e: The validation error that occurred.
        flag: How to handle the error (`bool`, `str`, or `Callable`).

    Returns:
        The error message to return.

    Raises:
        ValueError: If the flag type is unexpected.
    """
    if isinstance(flag, bool):
        content = "Tool input validation error"
    elif isinstance(flag, str):
        content = flag
    elif callable(flag):
        content = flag(e)
    else:
        msg = (
            f"Got unexpected type of `handle_validation_error`. Expected bool, "
            f"str or callable. Received: {flag}"
        )
        raise ValueError(msg)  # noqa: TRY004
    return content


def _handle_tool_error(
    e: ToolException,
    *,
    flag: Literal[True] | str | Callable[[ToolException], str] | None,
) -> str:
    """Handle tool execution errors based on the configured flag.

    Args:
        e: The tool exception that occurred.
        flag: How to handle the error (`bool`, `str`, or `Callable`).

    Returns:
        The error message to return.

    Raises:
        ValueError: If the flag type is unexpected.
    """
    if isinstance(flag, bool):
        content = e.args[0] if e.args else "Tool execution error"
    elif isinstance(flag, str):
        content = flag
    elif callable(flag):
        content = flag(e)
    else:
        msg = (
            f"Got unexpected type of `handle_tool_error`. Expected bool, str "
            f"or callable. Received: {flag}"
        )
        raise ValueError(msg)  # noqa: TRY004
    return content


class InjectedToolArg:
    """Annotation for tool arguments that are injected at runtime.

    Tool arguments annotated with this class are not included in the tool
    schema sent to language models and are instead injected during execution.
    """


class _DirectlyInjectedToolArg:
    """Annotation for tool arguments that are injected at runtime.

    Injected via direct type annotation, rather than annotated metadata.

    For example, `ToolRuntime` is a directly injected argument.

    Note the direct annotation rather than the verbose alternative:
    `Annotated[ToolRuntime, InjectedRuntime]`

    ```python
    from langchain_core.tools import tool, ToolRuntime


    @tool
    def foo(x: int, runtime: ToolRuntime) -> str:
        # use runtime.state, runtime.context, runtime.store, etc.
        ...
    ```
    """


class InjectedToolCallId(InjectedToolArg):
    """Annotation for injecting the tool call ID.

    This annotation is used to mark a tool parameter that should receive the tool call
    ID at runtime.

    ```python
    from typing import Annotated
    from langchain_core.messages import ToolMessage
    from langchain_core.tools import tool, InjectedToolCallId

    @tool
    def foo(
        x: int, tool_call_id: Annotated[str, InjectedToolCallId]
    ) -> ToolMessage:
        \"\"\"Return x.\"\"\"
        return ToolMessage(
            str(x),
            artifact=x,
            name="foo",
            tool_call_id=tool_call_id
        )
    ```
    """


def _is_directly_injected_arg_type(type_: Any) -> bool:
    """Check if a type annotation indicates a directly injected argument.

    This is currently only used for `ToolRuntime`.

    Checks if either the annotation itself is a subclass of `_DirectlyInjectedToolArg`
    or the origin of the annotation is a subclass of `_DirectlyInjectedToolArg`.

    For example, `ToolRuntime` or `ToolRuntime[ContextT, StateT]` would both return
    `True`.
    """
    return (
        isinstance(type_, type) and issubclass(type_, _DirectlyInjectedToolArg)
    ) or (
        (origin := get_origin(type_)) is not None
        and isinstance(origin, type)
        and issubclass(origin, _DirectlyInjectedToolArg)
    )


def _is_injected_arg_type(
    type_: type | TypeVar, injected_type: type[InjectedToolArg] | None = None
) -> bool:
    """Check if a type annotation indicates an injected argument.

    Args:
        type_: The type annotation to check.
        injected_type: The specific injected type to check for.

    Returns:
        `True` if the type is an injected argument, `False` otherwise.
    """
    if injected_type is None:
        # if no injected type is specified,
        # check if the type is a directly injected argument
        if _is_directly_injected_arg_type(type_):
            return True
        injected_type = InjectedToolArg

    # if the type is an Annotated type, check if annotated metadata
    # is an intance or subclass of the injected type
    return any(
        isinstance(arg, injected_type)
        or (isinstance(arg, type) and issubclass(arg, injected_type))
        for arg in get_args(type_)[1:]
    )


def get_all_basemodel_annotations(
    cls: TypeBaseModel | Any, *, default_to_bound: bool = True
) -> dict[str, type | TypeVar]:
    """Get all annotations from a Pydantic `BaseModel` and its parents.

    Args:
        cls: The Pydantic `BaseModel` class.
        default_to_bound: Whether to default to the bound of a `TypeVar` if it exists.

    Returns:
        `dict` of field names to their type annotations.
    """
    # cls has no subscript: cls = FooBar
    if isinstance(cls, type):
        fields = get_fields(cls)
        alias_map = {field.alias: name for name, field in fields.items() if field.alias}

        annotations: dict[str, type | TypeVar] = {}
        for name, param in inspect.signature(cls).parameters.items():
            # Exclude hidden init args added by pydantic Config. For example if
            # BaseModel(extra="allow") then "extra_data" will part of init sig.
            if name not in fields and name not in alias_map:
                continue
            field_name = alias_map.get(name, name)
            annotations[field_name] = param.annotation
    # cls has subscript: cls = FooBar[int]
    else:
        annotations = get_all_basemodel_annotations(
            get_origin(cls), default_to_bound=False
        )

    return {
        k: _replace_type_vars(v, default_to_bound=default_to_bound)
        for k, v in annotations.items()
    }


def _replace_type_vars(
    type_: type | TypeVar,
    generic_map: dict[TypeVar, type] | None = None,
    *,
    default_to_bound: bool = True,
) -> type | TypeVar:
    """Replace `TypeVar`s in a type annotation with concrete types.

    Args:
        type_: The type annotation to process.
        generic_map: Mapping of `TypeVar`s to concrete types.
        default_to_bound: Whether to use `TypeVar` bounds as defaults.

    Returns:
        The type with `TypeVar`s replaced.
    """
    generic_map = generic_map or {}
    if isinstance(type_, TypeVar):
        if type_ in generic_map:
            return generic_map[type_]
        if default_to_bound:
            return type_.__bound__ if type_.__bound__ is not None else Any  # type: ignore
        return type_
    if (origin := get_origin(type_)) and (args := get_args(type_)):
        new_args = tuple(
            _replace_type_vars(arg, generic_map, default_to_bound=default_to_bound)
            for arg in args
        )
        # 特殊处理UnionType类型（Python 3.10+的|操作符创建的类型）
        import types

        if origin is types.UnionType:
            from typing import Union

            return Union[new_args]

        return cast("type", _py_38_safe_origin(origin)[new_args])  # type: ignore[index]
    return type_
