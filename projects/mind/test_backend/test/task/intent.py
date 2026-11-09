import asyncio
import time
import uuid

import httpx


async def main():
    url = "http://sgm-complex-dev.extour-inc.com/sgm-complex/v1/simple_complex_arbitration"
    async with httpx.AsyncClient() as client:
        payload = {
            "query": "where are 来自哪里",
            "chat_id": uuid.uuid4().hex,
            "question_id": uuid.uuid4().hex,
            "history": [],
        }
        start = time.perf_counter()
        response = await client.post(url, json=payload)
        response.raise_for_status()
        result = response.json().get("data", "")
        elapsed = (time.perf_counter() - start) * 1000

        print(f"Result: {result}, Elapsed time: {elapsed:.2f} ms")

if __name__ == "__main__":
    asyncio.run(main())

# python -m projects.mind.test_backend.test.task.intent
