from __future__ import annotations

import asyncio
import uuid

from projects.sgm_prod.v1 import AgentDoStreamRequest, create_agent


def _make_req(query: str, chat_id: str) -> AgentDoStreamRequest:
    return AgentDoStreamRequest(
        chat_id=chat_id,
        question_id=chat_id,
        query=query,
        intent_type="复杂推理",
    )


async def run_base(query: str) -> None:
    """基础：使用 v1 Agent + toolset 默认工具。"""
    chat_id = f"sgm_v1_test_{uuid.uuid4().hex[:8]}"
    agent = create_agent(chat_id=chat_id)
    req = _make_req(query, chat_id)

    print(f"\n=== [v1 base] {query} ===")
    async for chunk in agent.astream_chunks(req):
        print(chunk.model_dump(exclude_none=True))


def main() -> None:
    query = "周杰伦有什么歌，帮我搜一下并播放"
    asyncio.run(run_base(query))


if __name__ == "__main__":
    main()
