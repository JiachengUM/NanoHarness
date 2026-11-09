"""
ReAct Agent API 测试用例
测试 /api/react/run 和 /api/react/run_stream 接口
"""

import pytest
from httpx import AsyncClient, ASGITransport
from projects.mind.complex_reasoning.tools import get_default_tools
from projects.mind.test_backend.main import app


@pytest.fixture
def sample_payload():
    """测试用例的标准输入数据"""
    tools = [tool.name for tool in get_default_tools(chat_id="")]

    return {
        "query": "看看今天天气如何，根据情况帮我开空调",
        "config": {
            "model": "SEED_1_8_251228",
            "params": {"thinking": {"type": "disabled"}},
            "tools": tools,
        },
    }


@pytest.mark.asyncio
async def test_run_react_agent(sample_payload):
    """测试普通的 ReAct Agent 执行接口"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/react/run",
            json=sample_payload,
        )

        # 验证响应状态码
        assert response.status_code == 200

        # 验证响应结构
        data = response.json()
        assert "code" in data

        # 验证业务状态码
        assert data["code"] == 200

        # 验证数据是列表
        assert isinstance(data["data"], list)

        print(f"\n✅ 测试通过！返回了 {len(data['data'])} 个执行步骤")


@pytest.mark.asyncio
async def test_run_react_agent_stream(sample_payload):
    """测试 SSE 流式 ReAct Agent 执行接口"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=30.0,  # SSE 流可能需要更长时间
    ) as client:
        async with client.stream(
            "POST",
            "/api/react/run_stream",
            json=sample_payload,
        ) as response:
            # 验证响应状态码
            assert response.status_code == 200

            # 验证 Content-Type
            assert "text/event-stream" in response.headers.get("content-type", "")

            # 验证响应头
            assert response.headers.get("cache-control") == "no-cache"
            assert response.headers.get("connection") == "keep-alive"

            # 收集所有事件
            events = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    import json

                    event_data = json.loads(line[6:])  # 去掉 "data: " 前缀
                    events.append(event_data)
                    print(f"收到事件: {event_data['type']}")

            print(f"\n✅ SSE测试通过！收到 {len(events)} 个事件")


if __name__ == "__main__":
    # 可以直接运行此文件进行测试
    pytest.main([__file__, "-v", "-s"])
