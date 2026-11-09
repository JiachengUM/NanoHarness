import asyncio
import json
import uuid

from projects.mind.complex_reasoning.utils.http_client import HttpClient
from aicore.agents.events import DefaultReActEventTranslator
from projects.mind.demo.sgm_processor.agent import AgentDoStreamRequest, SGMAgent


async def main() -> None:
    chat_id = "aipfox_" + uuid.uuid4().hex[:8]
    req = AgentDoStreamRequest(
        chat_id=chat_id,
        question_id=chat_id,
        query="打开车窗",
    )

    agent = SGMAgent.create(chat_id=chat_id, event_translator=DefaultReActEventTranslator())

    try:
        async for chunk in agent.astream(req):
            print(json.dumps(chunk.model_dump(exclude_none=True), ensure_ascii=False))
    finally:
        await HttpClient.close_for_current_loop()


if __name__ == "__main__":
    asyncio.run(main())
