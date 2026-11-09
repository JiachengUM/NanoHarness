"""响应管理功能模块"""

from __future__ import annotations

import time

from typing import Literal

from pydantic import BaseModel, Field


# 下述symbol是实现细节。只要无需对外暴露，就不需要进入.core。
from volcenginesdkarkruntime.types.responses import ResponseItem
from volcenginesdkarkruntime._exceptions import ArkAPIError

from aicore.models.responses.core import Response

from .core import (
    Ark, 
    AsyncArk,
    ResponseOutputMessage,
)


class Message(BaseModel):
    id: str = Field(default="", description="消息ID")
    role: Literal["user", "assistant", "system"] = Field(..., description="消息角色")
    content: str = Field(default="", description="消息内容")


class ResponseContext(BaseModel):
    data: list[ResponseItem] = Field(default_factory=list, description="响应上下文")
    has_more: bool | None = Field(default=None, description="是否有更多")

    # TODO：first_id和last_id暂时没用上，后续可以考虑使用。
    # first_id: str = Field(default="", description="第一条的ID")
    # last_id: str = Field(default="", description="最后一条的ID")

    @classmethod
    def for_messages(cls, response: ResponseContext) -> list[Message]:
        # TODO：目前只能处理MessageItem类型的内容，后续要支持其他类型。如 FunctionToolCallItem
        messages: list[Message] = []
        for item in response.data:
            if isinstance(item, ResponseOutputMessage):
                messages.append(Message(id=item.id, role=item.role, content=item.content[0].text))
                
        return messages



def retrieve(id: str, /, *,client: Ark) -> Response:
    """同步查询模型响应，根据Response ID获取Response。失败时抛出异常。"""
    try:
        start = time.perf_counter()
        response = client.responses.retrieve(response_id=id)
        # TODO：临时处理 message_history 传入空列表。将来要解决。
        return Response.from_raw(response, message_history=[], latency=time.perf_counter() - start)

    except ArkAPIError as e:
        raise RuntimeError(f"查询Response失败(API错误): {e}") from e
    except Exception as e:
        raise RuntimeError(f"查询Response失败(未知错误): {e}") from e


async def aretrieve(id: str, /, *,client: AsyncArk) -> Response:
    """异步查询模型响应，根据Response ID获取Response。失败时抛出异常。"""

    try:

        start = time.perf_counter()
        response = await client.responses.retrieve(response_id=id)
        # TODO：临时处理 message_history 传入空列表。将来要解决。
        return Response.from_raw(response, message_history=[], latency=time.perf_counter() - start)

    except ArkAPIError as e:
        raise RuntimeError(f"异步查询Response失败(API错误): {e}") from e
    except Exception as e:
        raise RuntimeError(f"异步查询Response失败(未知错误): {e}") from e


def delete(id: str, /, *, client: Ark) -> bool:
    """删除模型响应，根据Response ID删除Response。官方成功返回None，失败时抛出异常。"""
    try:
        client.responses.delete(response_id=id)
        return True
    except ArkAPIError as e:
        raise RuntimeError(f"删除Response失败(API错误): {e}") from e
    except Exception as e:
        raise RuntimeError(f"删除Response失败(未知错误): {e}") from e


async def adelete(id: str, /, *, client: AsyncArk) -> bool:
    """异步删除模型响应，根据Response ID删除Response。官方成功返回None，失败时抛出异常。"""
    try:
        await client.responses.delete(response_id=id)
        return True
    except ArkAPIError as e:
        raise RuntimeError(f"异步删除Response失败(API错误): {e}") from e
    except Exception as e:
        raise RuntimeError(f"异步删除Response失败(未知错误): {e}") from e


def list_items(
    id: str,
    /,
    *,
    limit: int = 20,
    order: Literal["asc", "desc"] = "asc",
    client: Ark
) -> ResponseContext:
    """获取响应上下文
    默认查找最近20条输入项，正序排列(历史在前面，新对话在末尾)
    如 ：limit = 3， 历史有10条，正序排序，0-9，传入id为9，则召回的是0、1、2，而不是7、8、9
    Args:
        id: Response ID
        limit: 查找的条数
        order: 排列顺序(asc: 正序，desc: 倒序)
        client: 客户端
    Returns:
        ResponseContext: 响应上下文
    """
    try:
        response = client.input_items.list(
            response_id=id,
            order=order,
            limit=limit,
        )

        return ResponseContext(
            data=response.data,
            has_more=response.has_more,
        )
    except ArkAPIError as e:
        raise RuntimeError(f"查询Response上下文失败(API错误): {e}") from e
    except Exception as e:
        raise RuntimeError(f"查询Response上下文失败(未知错误): {e}") from e

async def alist_items(
    id: str,
    /,
    *,
    limit: int = 20,
    order: Literal["asc", "desc"] = "asc",
    client: AsyncArk
) -> ResponseContext:
    """获取响应上下文
        获取逻辑：默认查找20条输入项，正序排列，传入最新id为100，则返回1-20条
        总数据：1-100 条（asc 正序），limit=20：
        第 1 页：不传 after → 返回 1-20 条；
        第 2 页：after=20 的 ID → 返回 21-40 条；
        ...
        直至没有更多。
    Args:
        id: Response ID
        limit: 查找的条数
        order: 排列顺序
        client: 客户端
    Returns:
        list[ResponseItem]: 响应上下文
    """
    try:
        response = await client.input_items.list(
            response_id=id,
            order=order,
            limit=limit,
        )

        return ResponseContext(
            data=response.data,
            has_more=response.has_more,
        )
    except ArkAPIError as e:
        raise RuntimeError(f"异步查询Response上下文失败(API错误): {e}") from e
    except Exception as e:
        raise RuntimeError(f"异步查询Response上下文失败(未知错误): {e}") from e


def list_all_items(id: str, /, *, client: Ark) -> list[ResponseItem]:
    """获取所有响应上下文（自动分页直到没有更多）
        获取逻辑：默认查找20条输入项，正序排列，传入最新id为100，则返回1-20条
        总数据：1-100 条（asc 正序），limit=20：
        第 1 页：不传 after → 返回 1-20 条；
        第 2 页：after=20 的 ID → 返回 21-40 条；
        ...
        直至没有更多。
    Args:
        id: Response ID
        client: 客户端
        
    Returns:
        list[ResponseItem]: 包含所有响应项的列表
    """
    all_data: list[ResponseItem] = []
    after = None
    
    try:
        while True:
            response = client.input_items.list(
                response_id=id,
                order="asc",
                limit=20,  # 固定批次大小，可根据需要调整
                after=after, # type: ignore   暂时无法处理NOT_GIVEN
            )
            
            if response.data:
                all_data.extend(response.data)
                after = response.data[-1].id # 取历史最后一条数据的ID作为下次获取的起点
                
            if not response.has_more:
                break
                
        return all_data
            
    except ArkAPIError as e:
        raise RuntimeError(f"获取所有响应项失败(API错误): {e}") from e
    except Exception as e:
        raise RuntimeError(f"获取所有响应项失败(未知错误): {e}") from e


async def alist_all_items(id: str, /, *, client: AsyncArk) -> list[ResponseItem]:
    all_data: list[ResponseItem] = []
    after = None
    
    try:
        while True:
            response = await client.input_items.list(
                response_id=id,
                order="asc",
                limit=100,
                after=after,
            )
            
            if response.data:
                all_data.extend(response.data)
                after = response.data[-1].id
                
            if not response.has_more:
                break
                
        return all_data
        
    except ArkAPIError as e:
        raise RuntimeError(f"异步获取所有响应项失败(API错误): {e}") from e
    except Exception as e:
        import copy
        from pydantic import ValidationError
        if isinstance(e, ValidationError) and "annotations" in str(e) and "ResponseOutputText" in str(e):
            all_data = []
            after = None
            while True:
                raw_response = await client.input_items.list(
                    response_id=id,
                    order="asc",
                    limit=100,
                    after=after,
                )
                if raw_response.data:
                    fixed_data = _patch_missing_annotations(raw_response.data)
                    all_data.extend(fixed_data)
                    after = raw_response.data[-1].id
                if not raw_response.has_more:
                    break
            return all_data
        raise RuntimeError(f"异步获取所有响应项失败: {e}") from e
