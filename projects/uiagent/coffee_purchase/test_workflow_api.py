from pathlib import Path
from typing import Final
import uuid
import aiohttp
import json

from rich import print

from projects.uiagent.coffee_purchase.workflow_case import WorkflowDatas, TaskType
from nanoai.model.vlm import image_from_path
import traceback

# 默认 XML 字符串
DEFAULT_XML: Final[str] = "默认字符串"

# HTTP接口配置
# BASE_URL = "http://120.26.237.96/volc-llm-nanoai-agent-dev"
# 本地服务地址
BASE_URL = "http://127.0.0.1:9001"
NL_API_URL = f"{BASE_URL}/api/coffee_purchase_nl_only_test"
IMAGE_API_URL = f"{BASE_URL}/api/coffee_purchase_image_only_test"


def generate_chat_id() -> str:
    """生成32位chat_id"""
    return str(uuid.uuid4()).replace("-", "")


async def http_post_nl(query: str, chat_id: str) -> dict:
    """简单的POST请求 - NL接口"""
    payload = {"query": query, "chat_id": chat_id}
    async with aiohttp.ClientSession() as session:
        async with session.post(NL_API_URL, json=payload) as resp:
            return await resp.json()


async def http_post_ui(image: str, image_format: str, xml: str, chat_id: str) -> dict:
    """简单的POST请求 - UI接口"""
    payload = {
        "image_base64": image,
        "image_format": image_format,
        "xml": xml,
        "chat_id": chat_id
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(IMAGE_API_URL, json=payload) as resp:
            return await resp.json()


async def test_normal_workflow(datas: WorkflowDatas):
    """使用HTTP API进行工作流简单测试
    
    Args:
        datas: 工作流数据
    """
    chat_id = generate_chat_id()
    print(f"🌐 使用HTTP接口模式，chat_id: {chat_id}")
    
    print("=" * 80)
    print(f"开始执行工作流: {datas.name}")
    print("=" * 80)
    
    for i, item in enumerate(datas.datas, start=1):
        print("\n" + "=" * 80)
        print(f"【步骤 {i}/{len(datas.datas)}】")
        print("=" * 80)
        print(f"comment: {item['comment']}")
        print(f"预期结果: {item['expected_result']}")
        # 加载图片
        image, image_format = image_from_path(item["image_path"])
        
        # 使用默认 XML
        xml = DEFAULT_XML
        
        try:
            if item["task_type"] == TaskType.UI:
                # HTTP POST请求 - UI接口
                response = await http_post_ui(image, image_format, xml, chat_id)
                print(f"HTTP UI响应 data 字段: {json.dumps(response['data'], ensure_ascii=False, indent=2)}")
            elif item["task_type"] == TaskType.NL:
                # HTTP POST请求 - NL接口
                response = await http_post_nl(item["query"], chat_id)
                print(f"HTTP NL响应 data 字段: {json.dumps(response['data'], ensure_ascii=False, indent=2)}")
            else:
                raise ValueError(f"未知的任务类型: {item['task_type']}")
        except Exception as e:
            print(f"❌ 步骤 {i} 执行推理时发生异常: {e}")
            traceback.print_exc()
            print("=" * 80)
            break


if __name__ == "__main__":
    import asyncio
    from projects.uiagent.coffee_purchase.workflow_case import ID_7
    asyncio.run(test_normal_workflow(ID_7))