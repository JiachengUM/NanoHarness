import asyncio
import sys
from pathlib import Path

# 将项目根目录添加到Python路径
sys.path.append(str(Path(__file__).parent.parent.parent.parent.parent))

from nanoai.model.config import ModelName, create_client
from projects.hwhms.common import volcengine_api
from openai import AsyncOpenAI


async def test_llm():
    query = "打开空调"
    messages_or_sys_prompt = []
    # 创建客户端
    client, _ = create_client(ModelName.DOUBAO_SEED_1_6_FLASH_250715, AsyncOpenAI)
    model = "doubao-seed-1-6-flash-250715"

    result = await volcengine_api.llm(query, messages_or_sys_prompt, client, model)
    print(result.output)
    assert result.output is not None

async def test_search_konwledge():
    query = "打开空调"
    result = await volcengine_api.search_konwledge(query)
    print(result)
    assert result is not None

async def test_volcengine_intent():
    query = "打开空调"
    result = await volcengine_api.volcengine_intent(query)
    print(result)
    assert result.intent_type is not None

if __name__ == "__main__":
    print("=== 测试LLM功能 ===")
    asyncio.run(test_llm())
    
    print("\n=== 测试知识库搜索功能 ===")
    asyncio.run(test_search_konwledge())
    
    print("\n=== 测试火山引擎意图识别功能 ===")
    asyncio.run(test_volcengine_intent())
