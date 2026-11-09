"""
模拟用户对话，逐条发送记忆更新请求
每隔 20-30 秒触发一次记忆更新
支持两种测试维度：1min 和 1day
"""
import asyncio
import json
import random
from datetime import datetime

import pandas as pd
from rich import print

from projects.mind.mem.volc_api import CollectionID, SessionMetadata, aadd_session
from projects.mind.mem.volc_api.session import MessageContent, Message


def parse_csv_data(csv_path: str, column: str = "conversation_1min") -> list[dict[str, str | list[dict[str, str]]]]:
    """
    读取 CSV 并解析指定列
    
    Args:
        csv_path: CSV 文件路径
        column: 列名，可选 "conversation_1min" 或 "conversation_1day"
    """
    df = pd.read_csv(csv_path)
    results: list[dict[str, str | list[dict[str, str]]]] = []
    
    for _, row in df.iterrows():
        timestamp: str = row["timestamp"]
        conversation_str = row.get(column, "")
        
        # 跳过空值
        if pd.isna(conversation_str) or conversation_str == "":
            continue
        
        try:
            messages = json.loads(conversation_str)
        except:
            continue
        
        if messages:
            results.append({
                "timestamp": timestamp,
                "messages": messages
            })
    
    return results


def to_volc_messages(messages: list[dict[str, str]]) -> list[Message]:
    """转换为火山记忆平台格式"""
    result: list[Message] = []
    for msg in messages:
        user_text = msg.get("user", "")
        assistant_text = msg.get("assistant", "")
        
        result.append(Message(
            role="user",
            content=[MessageContent(type="text", text=user_text)]
        ))
        result.append(Message(
            role="assistant",
            content=[MessageContent(type="text", text=assistant_text)]
        ))
    return result


async def simulate_memory_update(
    csv_path: str,
    collection_id: CollectionID,
    user_id: str,
    column: str = "conversation_1min",
    min_interval: int = 20,
    max_interval: int = 30,
):
    """
    模拟用户对话，逐条发送记忆更新请求
    
    Args:
        csv_path: CSV 文件路径
        collection_id: 记忆库 ID
        user_id: 用户 ID
        column: 列名，可选 "conversation_1min" 或 "conversation_1day"
        min_interval: 最小间隔（秒）
        max_interval: 最大间隔（秒）
    """
    data = parse_csv_data(csv_path, column=column)
    total = len(data)
    
    print(f"📊 共 {total} 条对话记录")
    print(f"📊 数据列: {column}")
    print(f"⏱️ 间隔: {min_interval}-{max_interval} 秒")
    print(f"👤 用户: {user_id}")
    print(f"📁 记忆库: {collection_id.collection_name}")
    print("-" * 50)
    for i, item in enumerate(data):
        timestamp: str = item["timestamp"]
        messages: list[dict[str, str]] = item["messages"]
        
        volc_messages = to_volc_messages(messages)
        
        # 使用文件中的真实时间戳
        dt = datetime.strptime(timestamp, "%Y%m%d %H:%M:%S")
        time_ms = int(dt.timestamp() * 1000)
        
        metadata = SessionMetadata(
            default_user_id=user_id,
            default_user_name="张三",
            default_assistant_id="simulate_assistant",
            default_assistant_name="小途",
            time=time_ms,
        )
        
        print(f"\n[{i+1}/{total}] {timestamp}")
        print(f"  对话轮数: {len(messages)}")
        
        try:
            session_id = await aadd_session(
                collection_id,
                volc_messages,
                metadata=metadata,
            )
            print(f"  ✅ 写入成功: session_id={session_id}")
        except Exception as e:
            print(f"  ❌ 写入失败: {e}")
        
        if i < total - 1:
            interval = random.randint(min_interval, max_interval)
            print(f"  ⏳ 等待 {interval} 秒...")
            await asyncio.sleep(interval)
    
    print("\n" + "=" * 50)
    print("🎉 模拟完成！")


async def test_1min():
    """测试 1 分钟粒度"""
    CSV_PATH = r"projects\mind\mem\test_real_conversation_memory_extraction\sample-data-v3.csv"
    COLLECTION_ID = CollectionID(collection_name="test_prompt")
    USER_ID = "dzy_test_memory_new_1"
    
    await simulate_memory_update(
        csv_path=CSV_PATH,
        collection_id=COLLECTION_ID,
        user_id=USER_ID,
        column="conversation_1min",
        min_interval=1,
        max_interval=2,
    )


async def test_1day():
    """测试 1 天粒度"""
    CSV_PATH = r"projects\mind\mem\test_real_conversation_memory_extraction\sample-data-v3.csv"
    COLLECTION_ID = CollectionID(collection_name="test_prompt")
    USER_ID = "dzy_test_memory_new_1"
    
    await simulate_memory_update(
        csv_path=CSV_PATH,
        collection_id=COLLECTION_ID,
        user_id=USER_ID,
        column="conversation_1day",
        min_interval=1,
        max_interval=2,
    )


if __name__ == "__main__":
    from projects.mind.mem.test_real_conversation_memory_extraction.aggregate_conversations import aggregate_conversations
    INPUT_CSV = r"projects\mind\mem\test_real_conversation_memory_extraction\sample-data-v2.csv"
    OUTPUT_CSV = r"projects\mind\mem\test_real_conversation_memory_extraction\sample-data-v3.csv"
    # 处理原始数据集，提取出
    # 1、相邻60s内的对话为一轮的数据
    # 2、按照day 来统计数据集
    result_df = aggregate_conversations(
        csv_path=INPUT_CSV,
        output_csv=OUTPUT_CSV,
        interval_seconds=60,
    )


    # 分钟维度
    asyncio.run(test_1min())

    # 按天为维度 
    # asyncio.run(test_1day())
