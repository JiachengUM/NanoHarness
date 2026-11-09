"""
记忆召回工具：从 dag_v2 MemoryRecallExecutor._memory_single 迁移而来的自包含版本。

- 输入收敛为 query + memory_type，移除 dag_v2 中无消费的 filters/limit。
- query 同时承担 dag_v2 中 query 与 query 两个语义（query 就是 query）。
- 不再 import aicore.tools.dag_v2：模型 / prompt / LLM 编排全部内联。
- 通过 create_tool 工厂封装，命名/参数风格对齐 WebsearchTool / music_search_v2.qq_music_*_tool。
- work 参数允许外部注入自定义记忆召回函数。
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from functools import cached_property
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field

from aicore.models.credentials import AsyncArk, ModelName, create_client
from aicore.models.responses import ResponseParams, ainvoke
from aicore.tools import create_tool

__all__ = [
    "MemoryRecallInput",
    "MemoryRecallOutput",
    "MemoryTool",
    "memory_tool",
    "MemoryWorker",
]

logger = logging.getLogger(__name__)


# =============================================================================
# 1. 本地数据模型（替代 dag_v2.operator_models.MemoryRecallOutput）
# =============================================================================


class MemoryRecallOutput(BaseModel):
    """记忆召回输出 — 与 dag_v2.operator_models.MemoryRecallOutput 字段一致。"""

    facts: str = Field(default="", description="mock 的记忆事实文本")


# =============================================================================
# 2. LLM 客户端单例（替代 dag_v2.step.Client / ClientParams）
# =============================================================================


class _MemoryClientParams(BaseModel):
    """LLM 客户端参数 — 与 dag_v2.step.ClientParams 字段一致。"""

    model: str = Field(default=ModelName.SEED_1_6_FLASH_250828, description="模型名称")
    params: ResponseParams = Field(
        default=ResponseParams(thinking={"type": "disabled"}),
        description="响应参数配置",
    )

    @cached_property
    def client(self) -> AsyncArk:
        """模型客户端（按 model 名懒加载）"""
        m = ModelName(self.model)
        client, _ = create_client(m, AsyncArk)
        return client


# 模块级单例 — worker 共享同一 Client
_MemoryClient = _MemoryClientParams()


# =============================================================================
# 3. Prompt 构造器（替代 dag_v2.step._build_memory_mock_prompt，合并 query/query 槽位）
# =============================================================================


def _build_memory_mock_prompt(query: str) -> str:
    """构造记忆 Mock 答案 LLM 提示词。

    旧版本同时接受 query 和 query 两段冗余槽位；本工具收敛为单 query。
    """
    return f"""
    你是一个车内助手记忆系统，负责根据用户的当前目标返回对应的记忆实体，内容要具体真实。
    请直接输出一个目标实体，不要加任何解释或JSON格式。

    【步骤目标】
    {query}
"""


# =============================================================================
# 4. 默认 worker（替代 dag_v2.step.generate_memory_mock + dag_v2.tools.executors.MemoryRecallExecutor._memory_single）
# =============================================================================


async def _memory_single_worker(
    query: str
) -> MemoryRecallOutput:

    prompt = _build_memory_mock_prompt(
        query=query
    )

    response = await ainvoke(
        prompt,
        client=_MemoryClient.client,
        model=_MemoryClient.model,
        params=_MemoryClient.params,
    )
    raw_text = response.raw_text or ""

    facts = yaml.safe_load(
        raw_text.strip()
        .removeprefix("```json")
        .removeprefix("```python")
        .removeprefix("```")
        .removesuffix("```")
    )
    return MemoryRecallOutput(facts=facts)


# =============================================================================
# 5. Tool 封装（create_tool 工厂 — 与 WebsearchTool / poi_search_tool 对齐）
# =============================================================================


class MemoryRecallInput(BaseModel):
    """记忆召回工具：根据步骤目标从后台记忆数据中召回用户偏好"""
    query: str = Field(description="记忆查询描述")
    memory_type: Literal["preference", "history", "context", "profile"] = Field(
        default="preference",
        description="记忆类型: preference/history/context/profile")
MemoryWorker = Callable[..., Awaitable[MemoryRecallOutput]]


class MemoryRecallWorker:
    """memory_tool 的 worker 包装：接受 work 注入，默认等价于 _memory_single。"""

    def __init__(self, work: Optional[MemoryWorker] = None):
        self.work = work or _memory_single_worker

    async def __call__(
        self,
        query: str,
        memory_type: Literal["preference", "history", "context", "profile"] = "preference",
    ) -> MemoryRecallOutput:
        return await self.work(
            query=query
        )


def memory_tool(work: Optional[MemoryWorker] = None, *, timeout: float | None = None):
    """记忆召回工具：与 dag_v2 MemoryRecallExecutor._memory_single 等价。

    Args:
        work: 自定义 worker，签名 ``(query, memory_type) -> MemoryRecallOutput``。
              缺省时使用 ``_memory_single_worker``（内部调 ainvoke 走 LLM）。
        timeout: 工具执行超时（秒）。
    """
    return create_tool(
        name="MemoryRecall",
        description=(
            "记忆召回工具：根据步骤目标从后台记忆数据中召回用户偏好。"
            "输出：记忆实体"
        ),
        args_schema=MemoryRecallInput,
        worker=MemoryRecallWorker(work=work),
        timeout=timeout,
    )


# 类风格别名，参考 WebsearchTool / NavigateTool 的命名约定
MemoryTool = memory_tool
