import asyncio
import json
import uuid

import aiohttp

URL = "https://llm-test.extour-inc.com:8900/v1/agent/do/stream"

BODY = {
    "query": "周杰伦有什么好听的歌，帮我播放一首",
    "request_id": "test_req_001",
    "history": [
      { "q": "你是谁", "a": "我是车机助手" }
    ],
    "chat_id": "chat_test_001",
    "question_id": "q_test_001",
    "intent_type": "复杂推理",
    "car_info": {}
}


async def main() -> None:
    print(f"POST {URL}")
    print(json.dumps(BODY, ensure_ascii=False, indent=2))
    print("\nstream response:")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            URL,
            json=BODY,
            headers={"Accept": "text/event-stream"},
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            async for raw in resp.content:
                line = raw.decode().strip()
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    print(json.dumps(json.loads(payload), ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
