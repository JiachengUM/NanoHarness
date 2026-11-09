"""
chat包 - 基于火山方舟引擎chat api的封装
原则上， 需要封装所有外部需要使用的symbol。外部代码无需访问volcenginesdkarkruntime包
"""

from volcenginesdkarkruntime.types.chat import ChatCompletionToolParam
from volcenginesdkarkruntime.types.shared_params import FunctionDefinition

from .core import (
    Ark, 
    AsyncArk,
    system_msg,
    user_msg,
    assistant_msg,
    DEFAULT_SYS_PROMPT,
    _compose_messages,
)

from .params import ChatParams

from .invocation import (
    ChatResult,
    invoke,
    ainvoke,
    invoke_output_by_schema,
    ainvoke_output_by_schema,
)

from .streaming import (
    ChatResultStreamBase,
    ChatResultStream,
    ChatResultAsyncStream,
    stream,
    astream,
)


__all__ = [
    "system_msg",
    "user_msg",
    "assistant_msg",
    "ChatParams",
    "ChatResult",
    "ChatResultStreamBase",
    "ChatResultStream",
    "ChatResultAsyncStream",
    "invoke",
    "ainvoke",
    "stream",
    "astream",
    "invoke_output_by_schema",
    "ainvoke_output_by_schema",
]
