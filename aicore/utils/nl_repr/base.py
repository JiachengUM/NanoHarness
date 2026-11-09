from typing import Any, Callable, Protocol


class NLReprError(Exception):
    """nl_repr错误。"""

    def __init__(self, obj: Any, reason: str):
        """obj: 待转换的对象。reason: 错误原因。"""
        self.obj = obj
        self.reason = reason
        # 不在这里生成消息，而是在__str__中动态生成

    def __str__(self) -> str:
        return f"nl_repr转换失败, 输入: {self.obj}，原因: {self.reason}"

class NLReprHandler(Protocol):
    def __call__(self, obj: Any, **kwargs: Any) -> str:
        ...


_type_registry: dict[type, NLReprHandler] = {}


def register(cls_type: type) -> Callable[[NLReprHandler], NLReprHandler]:
    def decorator(handler: NLReprHandler) -> NLReprHandler:
        _type_registry[cls_type] = handler
        return handler
    return decorator
