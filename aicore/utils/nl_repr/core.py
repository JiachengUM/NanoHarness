from typing import Any

from pydantic import BaseModel

from aicore.utils.nl_repr.base import NLReprError, _type_registry
from aicore.utils.nl_repr.list import _nl_repr_list
from aicore.utils.nl_repr.dict import _nl_repr_dict
from aicore.utils.nl_repr.basemodel import nl_repr_base_model, nl_repr_base_model_type

__all__ = [
    "nl_repr",
    "nl_repr_safe",
    "_bool_true_text",
    "_bool_false_text",
    "set_bool_texts",
    "register_bool_texts",
    "_none_text",
    "set_none_text",
    "register_none_text",
]


_bool_true_text = "True"
_bool_false_text = "False"
_none_text = "None"


def set_bool_texts(true_text: str, false_text: str) -> None:
    global _bool_true_text, _bool_false_text
    _bool_true_text = true_text
    _bool_false_text = false_text


def register_bool_texts(true_text: str, false_text: str) -> None:
    global _bool_true_text, _bool_false_text
    _bool_true_text = true_text
    _bool_false_text = false_text


def set_none_text(text: str) -> None:
    global _none_text
    _none_text = text


def register_none_text(text: str) -> None:
    global _none_text
    _none_text = text


def nl_repr(x: Any, **kwargs: Any) -> str:
    if hasattr(x, "__nl_repr__"):
        method = getattr(x, "__nl_repr__")
        if not callable(method):
            raise NLReprError(x, f"__nl_repr__ must be callable, got {type(method)}")
        result = method(**kwargs)
        if not isinstance(result, str):
            raise NLReprError(x, f"__nl_repr__()必须返回str, 不能是{type(result)}")
        return result

    obj_type = type(x)
    if obj_type in _type_registry:
        handler = _type_registry[obj_type]
        if not callable(handler):
            raise NLReprError(x, f"registered handler must be callable, got {type(handler)}")
        result = handler(x, **kwargs)
        if not isinstance(result, str):
            raise NLReprError(x, f"registered handler must return str, got {type(result)}")
        return result

    if x is None:
        return _none_text
    elif isinstance(x, str):
        return x
    elif isinstance(x, bool):
        return _bool_true_text if x else _bool_false_text
    elif isinstance(x, int):
        return str(x)
    elif isinstance(x, float):
        return str(x)
    elif isinstance(x, list):
        return _nl_repr_list(x, nl_repr, **kwargs)
    elif isinstance(x, dict):
        return _nl_repr_dict(x, nl_repr, **kwargs)
    elif isinstance(x, BaseModel):
        return nl_repr_base_model(x, nl_repr)
    elif isinstance(x, Exception):
        return f"错误: {type(x).__name__}: {str(x)}"
    elif issubclass(x, BaseModel):
        return nl_repr_base_model_type(x)
    else:
        raise NLReprError(x, f"对于类型{type(x)}未实现nl_repr, 值为{x}")


def nl_repr_safe(x: Any, **kwargs: dict[Any, Any]) -> str:
    try:
        return nl_repr(x, **kwargs)
    except NLReprError:
        return str(x)
