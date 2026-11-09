import asyncio
import uuid

from rich import print

from projects.mind.mem.auto_test_script.auto_test_demos.benz_demo.s2s_voice_bot import (
    S2SVoiceBot,
    DEFAULT_VOICE_PRINT_ID,
    NEAT_STREAM_OUTPUT,
)

# S2S 最小可执行测试脚本 - 使用之前能工作的格式

QUERIES = [
        "你好",
        "我是张三",
        "我刚刚说了啥",
        "导航去公司",
        "播放周杰伦的音乐",
        "打开前排和后排的车窗，并播放音乐",
    ]
async def test_bot():
    bot = S2SVoiceBot(
        {
            "voice_print_id": DEFAULT_VOICE_PRINT_ID,
        }
    )
    session_id = uuid.uuid4().hex
    print("[CLIENT] WebSocket 已连接（由 S2SVoiceBot 管理）")
    print(f"[CLIENT] 规整输出: {NEAT_STREAM_OUTPUT}")

    queries = QUERIES

    for i, query in enumerate(queries, 1):
        print(f"\n{'=' * 60}")
        print(f"[CLIENT] === 第 {i} 轮对话 ===")
        print(f"{'=' * 60}")
        print(f"[CLIENT] 发送查询: {query}")
        answer = await bot.achat(query, session_id)
        print(f"[CLIENT] 合并回复: {answer}")

    history = await bot.adump_history()
    print(f"\n[CLIENT] sessionId: {session_id}")
    print(f"[CLIENT] 对话历史轮数: {len(history)}")
    print(history)


import asyncio
import json
import uuid
import websockets
from rich import print

# S2S 最小可执行测试脚本 - 使用之前能工作的格式

WS_URL = "ws://101.126.11.190/voice-manager-benz/voice/ws"
X_APP_ID = "extour-inc"
X_ACCESS_KEY = "REDACTED"
X_DEVICE_ID = "LE4AG4CB2SL611680"


async def original_s2s_test_script():
    # 连接参数
    ws_connect_kwargs = {
        "additional_headers": {
            "X-App-ID": X_APP_ID,
            "X-Access-Key": X_ACCESS_KEY,
            "X-Device-ID": X_DEVICE_ID
        }
    }

    async with websockets.connect(WS_URL, **ws_connect_kwargs) as ws:
        print("[CLIENT] WebSocket 已连接")

        session_id = uuid.uuid4().hex
        request_id = uuid.uuid4().hex

        # 1. 发送 StartSession 消息（使用 ogg_opus 格式）
        start_msg = {
            "topic": "recorder.stream.start",
            "recordId": uuid.uuid4().hex,
            "sessionId": session_id,
            "asrParams": {"realBack": True},
            "nluParams": {"enableNLPEmotion": True, "enableEarlyResult": True, "enableNBest": True},
            "audio": {"audioType": "ogg_opus", "sampleRate": 16000, "sampleBytes": 2, "channel": 1},
            "context": {"attributes": {"voicePrintId": "test_user_stream"}}
        }
        await ws.send(json.dumps(start_msg, ensure_ascii=False))
        print("[CLIENT] StartSession 已发送")

        async def send_query(query):
            """发送单个文本查询"""
            request_id = uuid.uuid4().hex
            query_msg = {
                "contextId": session_id,
                "pinyin": "jin tian tian qi zen me yang",
                "sentenceBeginTime": 0,
                "recordId": "89b2732723d143528451acab860352b1:e5fc8865216a44099f54b61774928278:0615e89724094ab6973e93edd140044f",
                "topic": "asr.speech.sentence",
                "sentenceEndTime": 1640,
                "nbest": [{"text": query}],
                "languageClass": "putonghua",
                "context": {
                    "cloudVadEnd": 1774928279558,
                    "cloudVadBegin": 1774928278381,
                    "asrLastDuration": 187,
                    "wordsEnd": True,
                    "rec": query,
                    "asrChoice": "mix"
                },
                "sentence": query,
                "requestId": request_id,
                "conf": 0.715,
                "sessionId": session_id,
                "ortho": 0,
                "nbest_formatted": [query]
            }
            await ws.send(json.dumps(query_msg, ensure_ascii=False))
            print(f"[CLIENT] 文本查询已发送: {query}")
            return request_id

        async def wait_for_response_end(timeout=15):
            """等待当前请求响应（收到 dm.output 或超时）"""
            print("[CLIENT] 等待响应...")
            end_time = asyncio.get_event_loop().time() + timeout
            dm_output_received = False
            
            while asyncio.get_event_loop().time() < end_time:
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    
                    # 尝试解析 JSON
                    if isinstance(response, str):
                        try:
                            data = json.loads(response)
                            topic = data.get("topic", "")
                            
                            # tts.audio 只打印收到音频
                            if topic == "tts.audio":
                                print("[SERVER] 收到音频")
                                continue
                            
                            # dm.output 详细打印
                            print("\n" + "="*60)
                            print("[SERVER] 原始响应:")
                            print("-"*60)
                            print(json.dumps(data, ensure_ascii=False, indent=4))
                            print("="*60)
                            
                            print(f"\n[SERVER] 解析结果:")
                            print(f"  topic: {topic}")
                            if "dm" in data:
                                dm = data["dm"]
                                print(f"  input: {dm.get('orthography', '')}")
                                if "command" in dm:
                                    cmd = dm["command"]
                                    print(f"  intentApi: {cmd.get('intentApi', '')}")
                                    if "param" in cmd:
                                        param = cmd["param"]
                                        if "aiSprite" in param:
                                            content = param["aiSprite"].get("data", {}).get("content", "")
                                            if content:
                                                print(f"  AI回复: {content}")
                                        elif param.get("customInnerType") == "nativeCommand":
                                            print(f"  控制命令: {param.get('action', '')}{param.get('object', '')}")
                                nlg = dm.get("customNlg", {}).get("nlg", "")
                                if nlg:
                                    print(f"  NLG: {nlg}")
                            
                            # 标记收到 dm.output
                            if topic == "dm.output":
                                dm_output_received = True
                            
                            # 检查是否是响应结束标志
                            if data.get("end", False):
                                print("\n[CLIENT] ✅ 当前请求完全结束")
                                return True
                                
                        except json.JSONDecodeError:
                            print(f"\n[SERVER] 文本响应: {response[:200]}...")
                    else:
                        print(f"[SERVER] 二进制数据: {len(response)} bytes")
                            
                except asyncio.TimeoutError:
                    continue
            
            # 如果收到了 dm.output 但没收到 end，也认为可以继续
            if dm_output_received:
                print("[CLIENT] ⚠️ 未收到 end，但已收到 dm.output，继续下一轮")
                return True
            
            print("[CLIENT] ⚠️ 等待响应超时")
            return False

        # 2. 发送多个查询（连续对话）
        queries = QUERIES

        for i, query in enumerate(queries, 1):
            print(f"\n{'='*60}")
            print(f"[CLIENT] === 第 {i} 轮对话 ===")
            print(f"{'='*60}")
            print(f"[CLIENT] 发送查询: {query}")
            await send_query(query)
            
            # 等待响应
            success = await wait_for_response_end()
            if not success:
                print(f"[CLIENT] 第 {i} 轮对话异常，尝试继续下一轮")
            
            # 间隔1秒再发送下一个
            await asyncio.sleep(1)

        print(f"\n[CLIENT] sessionId: {session_id}")



def main():
    asyncio.run(test_bot())

    # 测试同学提供的原始S2S测试脚本。
    # asyncio.run(original_s2s_test_script())

if __name__ == "__main__":
    main()
