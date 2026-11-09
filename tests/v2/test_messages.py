import asyncio

from aicore.models.credentials import ModelName
from aicore.models.responses import ModelParams, ResponseInputItemParam, astream_run, system_msg, user_msg, assistant_msg

params = ModelParams(model=ModelName.SEED_1_8_251228)

async def test_sys_message_as_human():
    """测试系统消息作为人类消息是否有效"""

    messages: list[ResponseInputItemParam] = []

    messages.append(system_msg("你是一个友好的AI助手"))
    messages.append(user_msg("你好，请帮我查询北京的天气"))
    messages.append(assistant_msg("好的。正在为您查询中，请稍候"))
    
    query = """下述消息是来自于系统的消息，并不是用户的消息。请根据此回复用户。
北京的天气晴朗，气温20度。"""
    messages.append(user_msg(query))

    response = await astream_run(messages, None, client=params.client, model=params.model, params=params.params)
    print(response.raw_text)


async def main():
    await test_sys_message_as_human()


if __name__ == "__main__":
    asyncio.run(main())
