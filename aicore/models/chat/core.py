"""核心数据结构和基础功能模块"""

from __future__ import annotations

from typing import Final
from volcenginesdkarkruntime import Ark, AsyncArk

from volcenginesdkarkruntime.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionToolParam
)


# message helpers
def system_msg(content: str) -> ChatCompletionSystemMessageParam:
    return {"role": "system", "content": content}

def user_msg(content: str) -> ChatCompletionUserMessageParam:
    return {"role": "user", "content": content}

def assistant_msg(content: str) -> ChatCompletionAssistantMessageParam:
    return {"role": "assistant", "content": content}

DEFAULT_SYS_PROMPT: Final[str] = "你是一个有用的助手"

def _compose_messages(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str,
) -> list[ChatCompletionMessageParam]:
    """将输入和消息历史合并为OpenAI API的messages参数。"""

    assert isinstance(input, str), f"input must be str, but got {type(input)}"
    assert isinstance(messages_or_sys_prompt, (str, list)), f"messages_or_sys_prompt must be str or list, but got {type(messages_or_sys_prompt)}"

    messages: list[ChatCompletionMessageParam]

    if isinstance(messages_or_sys_prompt, str):
        messages = [system_msg(messages_or_sys_prompt)]
    else:
        messages = messages_or_sys_prompt

    # 创建用户消息
    messages.append(ChatCompletionUserMessageParam(role="user", content=input))
    
    return messages
