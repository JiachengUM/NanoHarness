from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import torch
import asyncio
from qwen_tts import Qwen3TTSModel
from qwen_asr import Qwen3ASRModel
import os
import tempfile
import numpy as np
import soundfile as sf
import sounddevice as sd
import io
import threading
import queue
import time
from collections import deque

from aicore.models.credentials import ModelName
from aicore.v1.experiments.agent import create_agent, Agent, SystemPrompt

system_prompt = SystemPrompt(role="他极具表演天赋，能完美扮演任何角色。你给出设定，他迅速进入，高度契合角色性格与语言风格，根据经历情境互动，为你带来沉浸式体验。",
                             guidelines=["站在一名乘客的角度，简短聊些POI相关的问题和事情",
                                         "回复要极简极简极简极简"])
agent = create_agent(model=ModelName.SEED_1_8_251228, tools=[], system_prompt=system_prompt, react_max_turns=1)

tts_model_file = "/tts"
asr_model_file = "/asr"

# Always-on microphone settings
MICROPHONE_ALWAYS_ON = False
RECOGNIZED_TEXT_QUEUE = queue.Queue()
SILENCE_THRESHOLD = 50  # 音量阈值，用于检测语音
SILENCE_DURATION = 3.0  # 静默持续时间（秒），超过则认为语音结束
BUFFER_DURATION = 15.0  # 缓冲区持续时间（秒）
SAMPLERATE = 16000  # 采样率


# 加载TTS模型
tts_model = Qwen3TTSModel.from_pretrained(
    tts_model_file,
    device_map="xpu",
    dtype=torch.bfloat16,
    local_files_only=True
)

# 加载ASR模型
asr_model = Qwen3ASRModel.from_pretrained(
    asr_model_file,
    dtype=torch.bfloat16,
    device_map="xpu",
    max_inference_batch_size=16,
    max_new_tokens=256,
    local_files_only=True
)

# 创建FastAPI应用
app = FastAPI(
    title="Qwen ASR/TTS Streaming API",
    description="Streaming interfaces for Qwen3 ASR and TTS models",
    version="1.0.0"
)


async def trace(query, agent: Agent):
    """从 Agent 中提取对话数据"""
    await agent.run_astream(query, event_listeners=[])
    _, state = await agent.dump()
    state_json = state.model_dump()

    system_msg = ""
    assistant_msg = ""
    tool_call_input = []
    tool_call_output = []

    for item in state_json["response"]["history"]:
        role = item.get("role", "")
        if role == "system":
            system_msg = item["content"][0]["text"]
        elif role == "assistant":
            assistant_msg = item["content"][0]["text"]
        elif item.get("name", ""):
            tool_call_input.append({item["name"]: item["arguments"]})
        else:
            if item["type"] == "function_call_output":
                tool_call_output.append(item.get("output", ""))
    return system_msg, assistant_msg, tool_call_input, tool_call_output


async def dump(query, agent):
    """处理单个查询"""
    system_msg, assistant_msg, tool_input, tool_output = await trace(query, agent)
    return system_msg, assistant_msg, tool_input, tool_output


async def passenger(query, agent):
    tasks = [dump(query, agent)]
    results = await asyncio.gather(*tasks)

    print("\n=== 执行结果 ===")
    for i, result in enumerate(results, 1):
        system_msg, assistant_msg, tool_input, tool_output = result
        print(f"查询: {query}")
        print(f"助手回复: {assistant_msg}")
        if tool_input:
            print(f"工具调用输入: {tool_input}")
        if tool_output:
            print(f"工具调用输出: {tool_output}")
        return assistant_msg


# ASR相关函数
def transcribe_audio(audio_content):
    # 使用临时文件在内存中处理
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
        temp_file.write(audio_content)
        temp_path = temp_file.name
    
    try:
        results = asr_model.transcribe(
            audio=temp_path,
            language=None,  # 自动检测语言
        )
        return results[0]
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# TTS相关函数
def generate_speech(text: str, language: str = "Chinese"):
    try:
        # # 创建一个1秒的静音音频作为默认参考
        silence = np.zeros(16000, dtype=np.float32)
        sf.write("../../../../silence.wav", silence, 16000)
        # 使用这个静音文件作为参考
        wavs, sr = tts_model.generate_voice_clone(
            text=text,
            language=language,
            ref_audio="silence.wav",
            ref_text=text
        )
        return wavs[0], sr
    except Exception as e:
        print(f"生成语音失败: {e}")
        # 创建一个简单的静音音频作为 fallback
        return np.zeros(16000, dtype=np.float32), 16000

# 麦克风录制功能
def record_from_microphone(duration=5, samplerate=16000):
    """从麦克风录制音频"""
    print(f"开始录制，持续 {duration} 秒...")
    recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype=np.float32)
    sd.wait()  # 等待录制完成
    print("录制完成")
    return recording.flatten(), samplerate

# 扬声器播放功能
def play_to_speaker(audio_data, samplerate=16000):
    """播放音频到扬声器"""
    print("开始播放...")
    sd.play(audio_data, samplerate)
    sd.wait()  # 等待播放完成
    print("播放完成")

# 语音检测函数
def is_speech(audio_data, threshold=SILENCE_THRESHOLD):
    """检测音频是否包含语音"""
    return np.max(np.abs(audio_data)) > threshold

# 持续监听函数
def continuous_listening():
    """持续监听麦克风输入"""
    global MICROPHONE_ALWAYS_ON
    
    buffer = deque(maxlen=int(BUFFER_DURATION * SAMPLERATE))
    silence_timer = 0.0
    block_size = 1024  # 每个块的大小
    block_duration = block_size / SAMPLERATE  # 每个块的持续时间
    
    print("开始持续监听...")
    
    try:
        with sd.InputStream(samplerate=SAMPLERATE, channels=1, dtype=np.float32, blocksize=block_size) as stream:
            while MICROPHONE_ALWAYS_ON:
                # 读取音频数据
                audio_data, overflowed = stream.read(block_size)
                audio_data = audio_data.flatten()
                
                # 添加到缓冲区
                buffer.extend(audio_data)
                
                # 检测是否有语音
                if is_speech(audio_data):
                    silence_timer = 0.0
                else:
                    silence_timer += block_duration
                
                # 如果检测到语音结束
                if silence_timer > SILENCE_DURATION and len(buffer) > int(SAMPLERATE * 0.5):  # 至少0.5秒的音频
                    print("检测到语音结束，开始识别...")
                    # 提取缓冲区中的音频数据
                    audio_buffer = np.array(buffer)
                    # 将音频数据转换为字节
                    buffer_io = io.BytesIO()
                    sf.write(buffer_io, audio_buffer, SAMPLERATE, format='wav')
                    buffer_io.seek(0)
                    audio_content = buffer_io.read()
                    try:
                        result = transcribe_audio(audio_content)
                        if result.text.strip():
                            print(f"识别结果: {result.text}")
                            # TODO 调用agent获取过程和结果
                            agent_execute_result = asyncio.run(passenger(query=result.text, agent=agent))

                            # TODO 基于XPU的tts响应可能超过分钟
                            print("语音识别：{result}".format(result=agent_execute_result))
                            reply = tts_play(text=agent_execute_result, language=result.language)
                            print("语音回复：{result}".format(result=reply.body.decode()))
                            RECOGNIZED_TEXT_QUEUE.put(result)
                    except Exception as e:
                        print(f"识别失败: {e}")
                    # 清空缓冲区
                    buffer.clear()
                    silence_timer = 0.0
                
                # 短暂休眠，减少CPU占用
                time.sleep(0.01)
    except Exception as e:
        print(f"监听过程中出错: {e}")
    finally:
        print("持续监听已停止")


# 麦克风输入ASR接口
@app.post("/asr/microphone")
async def asr_microphone(duration: int = 5):
    """使用麦克风进行语音识别"""
    try:
        # 从麦克风录制音频
        audio_data, sr = record_from_microphone(duration=duration)
        
        # 将音频数据转换为字节
        buffer = io.BytesIO()
        sf.write(buffer, audio_data, sr, format='wav')
        buffer.seek(0)
        audio_content = buffer.read()

        # 进行语音识别
        result = await transcribe_audio(audio_content)
        
        # 返回识别结果
        return JSONResponse({
            "language": result.language,
            "text": result.text
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 扬声器输出TTS接口
@app.post("/tts/play")
def tts_play(text: str, language: str = "Chinese", volume: float=1.0):
    """生成语音并直接播放到扬声器"""
    try:
        # 生成语音
        wav, sr = generate_speech(text, language)

        # 播放到扬声器
        play_to_speaker(wav*volume, sr)
        
        # 返回成功消息
        return JSONResponse({
            "message": "语音播放成功",
            "text": text,
            "language": language,
            "volume": volume
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Always-on麦克风控制接口
@app.post("/asr/always-on/start")
def start_always_on():
    """启动持续监听麦克风"""
    global MICROPHONE_ALWAYS_ON
    
    if MICROPHONE_ALWAYS_ON:
        return JSONResponse({"message": "持续监听已经在运行"})
    
    MICROPHONE_ALWAYS_ON = True
    
    # 启动监听线程
    listener_thread = threading.Thread(target=continuous_listening, daemon=True)
    listener_thread.start()
    
    return JSONResponse({"message": "持续监听已启动"})

@app.post("/asr/always-on/stop")
def stop_always_on():
    """停止持续监听麦克风"""
    global MICROPHONE_ALWAYS_ON
    
    if not MICROPHONE_ALWAYS_ON:
        return JSONResponse({"message": "持续监听未运行"})
    
    MICROPHONE_ALWAYS_ON = False
    
    return JSONResponse({"message": "持续监听已停止"})

@app.get("/asr/always-on/status")
def get_always_on_status():
    """获取持续监听状态"""
    global MICROPHONE_ALWAYS_ON
    
    return JSONResponse({
        "status": "running" if MICROPHONE_ALWAYS_ON else "stopped"
    })

@app.get("/asr/always-on/result")
def get_recognition_result():
    """获取最新的识别结果"""
    try:
        # 尝试从队列中获取最新的结果
        results = []
        while not RECOGNIZED_TEXT_QUEUE.empty():
            result = RECOGNIZED_TEXT_QUEUE.get()
            results.append({
                "language": result.language,
                "text": result.text
            })
        
        if not results:
            return JSONResponse({"message": "暂无识别结果"})
        
        return JSONResponse({"results": results})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # 启动时自动开启always-on麦克风
    print("启动时自动开启always-on麦克风...")
    start_always_on()
    print("always-on麦克风已启动")
    
    import uvicorn
    # 优化Uvicorn配置
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        loop="asyncio",
        limit_concurrency=100,
        limit_max_requests=1000
    )