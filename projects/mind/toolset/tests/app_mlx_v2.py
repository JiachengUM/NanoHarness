from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
import asyncio
import os
import tempfile
import numpy as np
import soundfile as sf
import sounddevice as sd
import io
import threading
import queue
import logging
import time
from collections import deque

from mlx_audio.stt.utils import load_model as asr_load_model
from mlx_audio.stt.generate import generate_transcription

from projects.mind.toolset.tests.stream_intent_agent import (
    ASROutput,
    IntentInput,
    IntentResult,
    get_intent_model,
)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)


class ModelManager:
    """流式语音意图识别只用 ASR 模型。"""

    def __init__(self):
        self.asr_model = None
        self.lock = threading.RLock()

    def get_asr_model(self):
        with self.lock:
            if self.asr_model is None:
                from projects.mind.toolset.tests.stream_intent_agent import resolve_local_path
                repo_id = "mlx-community/Qwen3-ASR-0.6B-8bit"
                resolved_path = resolve_local_path(repo_id)
                logger.info("Loading ASR model from: %s", resolved_path)
                self.asr_model = asr_load_model(resolved_path)
                logger.info("ASR model loaded successfully")
            return self.asr_model


model_manager = ModelManager()
model_manager.get_asr_model()
# 启动时预热意图模型，避免首次语音命中时冷加载阻塞。
get_intent_model().ensure_loaded()


class Config:
    MICROPHONE_ALWAYS_ON = False
    RECOGNIZED_TEXT_QUEUE = queue.Queue()
    SILENCE_THRESHOLD = 0.5
    SILENCE_DURATION = 2.0
    BUFFER_DURATION = 15.0
    SAMPLERATE = 16000

    VAD_AGGRESSIVENESS = 1
    VAD_MIN_SPEECH_DURATION = 0.3
    VAD_MAX_SILENCE_BEFORE_SPEECH = 0.5
    VAD_MAX_SILENCE_AFTER_SPEECH = 2.0


class ImprovedVAD:
    def __init__(self, aggressiveness=1):
        self.aggressiveness = aggressiveness
        self.energy_thresholds = [0.05, 0.1, 0.2, 0.3, 0.5]
        self.current_threshold = self.energy_thresholds[aggressiveness]

        self.is_speaking = False
        self.speech_started = False
        self.silence_count = 0
        self.speech_count = 0

        self.min_speech_frames = int(Config.VAD_MIN_SPEECH_DURATION / (1024 / Config.SAMPLERATE))
        self.max_silence_frames_before = int(Config.VAD_MAX_SILENCE_BEFORE_SPEECH / (1024 / Config.SAMPLERATE))
        self.max_silence_frames_after = int(Config.VAD_MAX_SILENCE_AFTER_SPEECH / (1024 / Config.SAMPLERATE))

        self.noise_floor = 0.0
        self.noise_floor_history = deque(maxlen=50)
        self.adaptive_threshold = self.current_threshold
        self.initial_calibration_done = False
        self.calibration_frames = 20

    def update_noise_floor(self, audio_data):
        current_noise = np.mean(np.abs(audio_data))
        self.noise_floor_history.append(current_noise)

        if len(self.noise_floor_history) >= self.calibration_frames:
            self.noise_floor = np.mean(self.noise_floor_history)
            # 车内环境噪声底较稳定，用加法而非 max，避免 noise_floor 升高时阈值跳变。
            # 上下界防止过敏感（<0.02）或过迟钝（>0.15）。
            self.adaptive_threshold = max(
                0.02,
                min(0.15, self.current_threshold + self.noise_floor * 1.0),
            )
            self.initial_calibration_done = True
        else:
            self.adaptive_threshold = self.current_threshold

    def has_voice_activity(self, audio_data):
        energy = np.max(np.abs(audio_data))
        is_loud = energy > self.adaptive_threshold

        if is_loud:
            self.speech_count += 1
            self.silence_count = 0

            if self.speech_count >= self.min_speech_frames:
                self.speech_started = True
                self.is_speaking = True
        else:
            # 仅在静音帧更新 noise_floor，避免语音段高能量帧污染阈值。
            self.update_noise_floor(audio_data)
            self.silence_count += 1
            self.speech_count = 0

            if self.speech_started and self.silence_count >= self.max_silence_frames_after:
                self.is_speaking = False
                self.speech_started = False

        return self.is_speaking

    def reset(self):
        self.is_speaking = False
        self.speech_started = False
        self.silence_count = 0
        self.speech_count = 0


def transcribe_audio(audio_content):
    logger.info("Starting audio transcription")
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(audio_content)
            temp_path = temp_file.name
        logger.debug(f"Created temp file for audio: {temp_path}")

        try:
            asr_model = model_manager.get_asr_model()
            logger.debug("ASR model loaded, starting transcription")
            transcription = generate_transcription(
                model=asr_model,
                audio=temp_path,
                stream=True)
            logger.info(f"Transcription completed: {transcription.text[:50]}..." if len(
                transcription.text) > 50 else f"Transcription completed: {transcription.text}")
            return transcription
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                logger.debug(f"Removed temp file: {temp_path}")
    except Exception as e:
        logger.error(f"Error in transcription: {e}")
        raise


class AudioCapture:
    """anyio-friendly 音频捕获。

    同步采集 + VAD 必须在独立线程跑（sounddevice InputStream 是阻塞的）。
    线程入口 run()，由 lifespan 通过独立 threading.Thread 拉起；activate / deactivate 控制是否采集。
    采集到的 wav bytes 通过 send_nowait 推进 anyio memory object stream，由 ASR worker 消费。
    """

    def __init__(self, audio_send: MemoryObjectSendStream[bytes]) -> None:
        self._audio_send = audio_send
        self._active = threading.Event()
        self._stop = threading.Event()

    def activate(self) -> None:
        self._active.set()

    def deactivate(self) -> None:
        self._active.clear()

    def shutdown(self) -> None:
        self._stop.set()
        self._active.set()  # 唤醒等待中的 run()

    def run(self) -> None:
        """线程入口：外层 while 直到 shutdown；内层 while 直到 deactivate。"""
        try:
            while not self._stop.is_set():
                self._active.wait()
                if self._stop.is_set():
                    break
                self._do_capture()
        except Exception:
            logger.exception("audio capture thread error")
        finally:
            logger.info("audio capture thread exited")

    def _do_capture(self) -> None:
        """内层：拉起 sd.InputStream，循环读 block + VAD，段结束推流。"""
        # 用 list 累积，无上限（车机一段对话几分钟可接受）。
        buffer: list[float] = []
        silence_timer = 0.0
        block_size = 1024
        block_duration = block_size / Config.SAMPLERATE
        vad = ImprovedVAD(aggressiveness=Config.VAD_AGGRESSIVENESS)
        speech_start_buffer: list[float] = []
        was_speaking = False

        logger.info("Opening audio stream...")
        try:
            with sd.InputStream(
                samplerate=Config.SAMPLERATE,
                channels=1,
                dtype=np.float32,
                blocksize=block_size,
            ) as stream:
                logger.info("Audio stream opened")
                while self._active.is_set() and not self._stop.is_set():
                    audio_data, overflowed = stream.read(block_size)
                    if overflowed:
                        logger.warning("Audio buffer overflow detected")
                    audio_data = audio_data.flatten()

                    speech_start_buffer.extend(audio_data)
                    is_speech_detected = vad.has_voice_activity(audio_data)

                    if is_speech_detected:
                        if len(buffer) == 0 and len(speech_start_buffer) > 0:
                            buffer.extend(speech_start_buffer)
                            speech_start_buffer.clear()
                        buffer.extend(audio_data)
                        silence_timer = 0.0
                        was_speaking = True
                    else:
                        silence_timer += block_duration
                        if was_speaking and len(buffer) > int(Config.SAMPLERATE * 0.5) and silence_timer > Config.SILENCE_DURATION:
                            logger.info("Speech end detected, pushing wav to async pipeline")
                            audio_buffer = np.array(buffer)
                            buffer_io = io.BytesIO()
                            sf.write(buffer_io, audio_buffer, Config.SAMPLERATE, format="wav")
                            buffer_io.seek(0)
                            audio_content = buffer_io.read()

                            try:
                                self._audio_send.send_nowait(audio_content)
                            except anyio.WouldBlock:
                                logger.warning("audio stream buffer full, dropping segment")

                            buffer.clear()
                            speech_start_buffer.clear()
                            vad.reset()
                            was_speaking = False
                            silence_timer = 0.0
        except Exception:
            logger.exception("audio capture inner loop error")
        finally:
            logger.info("Audio stream closed")


# ---------- 异步 worker 流水线 ----------

async def _asr_worker(
    audio_recv: MemoryObjectReceiveStream[bytes],
    text_send: MemoryObjectSendStream[ASROutput],
) -> None:
    """audio bytes → ASR → text。transcribe_audio 是 sync，丢到线程池避免阻塞事件循环。"""
    async with audio_recv:
        async for audio_content in audio_recv:
            if not audio_content:
                continue
            asr_t0 = time.perf_counter()
            try:
                asr_result = await anyio.to_thread.run_sync(transcribe_audio, audio_content)
            except Exception:
                logger.exception("transcribe_audio failed in pipeline")
                continue
            asr_ms = (time.perf_counter() - asr_t0) * 1000
            if asr_result.text.strip():
                await text_send.send(ASROutput(
                    text=asr_result.text,
                    language=getattr(asr_result, "language", "unknown"),
                ))
                logger.info("ASR timing: %.1fms, text=%r", asr_ms, asr_result.text[:80])


async def _intent_worker(
    text_recv: MemoryObjectReceiveStream[ASROutput],
    result_send: MemoryObjectSendStream[IntentResult],
) -> None:
    """ASR text → 意图分类。IntentInput.aclassify 内部走 anyio.to_thread.run_sync，不阻塞事件循环。"""
    intent_model = get_intent_model()
    async with text_recv:
        async for asr_output in text_recv:
            if not asr_output.text.strip():
                continue
            intent_t0 = time.perf_counter()
            try:
                classified = await IntentInput(text=asr_output.text).aclassify(intent_model)
            except Exception:
                logger.exception("intent classify failed for %r", asr_output.text)
                continue
            intent_ms = (time.perf_counter() - intent_t0) * 1000
            await result_send.send(IntentResult(
                intent=classified.intent,
                text=asr_output.text,
                language=asr_output.language,
            ))
            logger.info("Intent timing: %.1fms, intent=%s, text=%r", intent_ms, classified.intent, asr_output.text[:80])


async def _downstream_consumer(
    result_recv: MemoryObjectReceiveStream[IntentResult],
) -> None:
    """所有 ASR+意图结果都入队，供下游 qwen agent 通过 /asr/always-on/result 消费。

    不再按 intent 过滤，意图作为元数据保留供 agent 决策。命中与未命中均输出 log 区分。
    """
    async with result_recv:
        async for intent_result in result_recv:
            if intent_result.intent:
                logger.info(
                    "意图命中: %r (lang=%s)",
                    intent_result.text, intent_result.language,
                )
            else:
                logger.info(
                    "无意图: %r (lang=%s)",
                    intent_result.text, intent_result.language,
                )
            Config.RECOGNIZED_TEXT_QUEUE.put({
                "text": intent_result.text,
                "language": intent_result.language,
                "intent": intent_result.intent,
            })


# ---------- FastAPI lifespan ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时建 anyio 流水线（audio → asr → intent → 下游），关停时按顺序 cancel。"""
    get_intent_model().ensure_loaded()

    audio_send, audio_recv = anyio.create_memory_object_stream[bytes](100)
    text_send, text_recv = anyio.create_memory_object_stream[ASROutput](100)
    result_send, result_recv = anyio.create_memory_object_stream[IntentResult](100)

    capture = AudioCapture(audio_send)
    app.state.audio_capture = capture

    capture_thread = threading.Thread(target=capture.run, daemon=True, name="audio-capture")
    capture_thread.start()

    async with anyio.create_task_group() as tg:
        tg.start_soon(_asr_worker, audio_recv, text_send)
        tg.start_soon(_intent_worker, text_recv, result_send)
        tg.start_soon(_downstream_consumer, result_recv)
        logger.info("async intent pipeline started")

        try:
            yield
        finally:
            logger.info("shutting down async intent pipeline")

    capture.shutdown()
    capture_thread.join(timeout=5.0)
    await audio_send.aclose()
    await text_send.aclose()
    await result_send.aclose()


app = FastAPI(
    title="Streaming Voice Intent Recognition",
    description="anyio-based pipeline: sd capture → ASR → intent → downstream",
    version="3.0.0",
    lifespan=lifespan,
)


@app.post("/asr/always-on/start")
async def start_always_on():
    logger.info("Received request to start continuous listening")
    if Config.MICROPHONE_ALWAYS_ON:
        logger.warning("Continuous listening is already running")
        return JSONResponse({"message": "持续监听已经在运行"})

    Config.MICROPHONE_ALWAYS_ON = True
    app.state.audio_capture.activate()
    logger.info("MICROPHONE_ALWAYS_ON flag set to True, capture activated")

    await asyncio.sleep(0.1)
    return JSONResponse({"message": "持续监听已启动"})


@app.post("/asr/always-on/stop")
async def stop_always_on():
    logger.info("Received request to stop continuous listening")
    if not Config.MICROPHONE_ALWAYS_ON:
        logger.warning("Continuous listening is not running")
        return JSONResponse({"message": "持续监听未运行"})

    Config.MICROPHONE_ALWAYS_ON = False
    app.state.audio_capture.deactivate()
    logger.info("MICROPHONE_ALWAYS_ON flag set to False, capture deactivated")
    return JSONResponse({"message": "持续监听已停止"})


@app.get("/asr/always-on/status")
async def get_always_on_status():
    status = "running" if Config.MICROPHONE_ALWAYS_ON else "stopped"
    logger.debug(f"Getting continuous listening status: {status}")
    return JSONResponse({"status": status})


@app.get("/asr/always-on/result")
async def get_recognition_result():
    logger.info("Received request to get recognition results")
    try:
        results = []
        while not Config.RECOGNIZED_TEXT_QUEUE.empty():
            item = Config.RECOGNIZED_TEXT_QUEUE.get()
            if isinstance(item, dict):
                results.append({
                    "text": item.get("text", ""),
                    "language": item.get("language", "unknown"),
                    "intent": item.get("intent", True),
                })
            else:
                # 兼容旧的 ASRResult 对象（前置轮次遗留）
                results.append({
                    "text": getattr(item, 'text', ''),
                    "language": getattr(item, 'language', 'unknown'),
                    "intent": True,
                })
        logger.debug(f"Retrieved {len(results)} recognition results")

        if not results:
            logger.info("No recognition results available")
            return JSONResponse({"message": "暂无识别结果"})

        return JSONResponse({"results": results})
    except Exception as e:
        logger.error(f"Error getting recognition result: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        loop="asyncio",
        limit_concurrency=100,
        limit_max_requests=1000,
        workers=1,
        log_level="info"
    )