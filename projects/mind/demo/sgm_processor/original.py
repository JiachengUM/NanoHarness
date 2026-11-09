import asyncio

from beanie.odm.documents import P
from rich import print

from aicore.agents.react import _astream_react_naive
from aicore.models.credentials import AsyncArk, ModelName, create_client
from aicore.agents.events import default_event_filter
from projects.mind.complex_reasoning.tools import get_default_tools
import uuid


async def main() -> None:
    client, model = create_client(ModelName.SEED_1_8_251228, AsyncArk)
    chat_id = "aipfox_" + uuid.uuid4().hex
    print(f"model: {model}")
    print("=" * 60)

    async for event in _astream_react_naive(
        "今天上海天气怎么样",
        client=client,
        model=model,
        tools=get_default_tools(chat_id=chat_id),
        max_turns=3,
        event_filter=default_event_filter, 
    ):
        print(event)


if __name__ == "__main__":
    asyncio.run(main())
