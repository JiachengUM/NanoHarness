#!/usr/bin/env python3
"""
本地音频录制模块：同时录制麦克风（用户语音）和系统扬声器 loopback（TTS 播放），
混音为单声道 WAV，跨平台（Win WASAPI / Mac CoreAudio / Linux PulseAudio）。

依赖：soundcard, numpy
    pip install soundcard numpy

设计要点：
- 每次 start 新建 recorder 上下文（避免 WASAPI 长期会话被系统降权），stop 关闭
- 两路 mic/spk 独立线程并行读取，避免串行阻塞导致采样率减半
- 录音比视频早开始、晚结束，_merge_av -shortest 自动裁齐

独立测试服务：
    python audio_recorder.py
默认端口 8766（环境变量 AUDIO_RECORDER_PORT 可覆盖）。
"""
from __future__ import annotations

import os
import sys
import threading
import time
import wave
from pathlib import Path

# ---------- 依赖检查 ----------
try:
    import soundcard as sc
    import soundcard.mediafoundation  # noqa: F401  用于屏蔽 discontinuity 警告
    import warnings
    # 屏蔽 WASAPI 偶发的 "data discontinuity in recording" 良性警告
    warnings.filterwarnings("ignore", message="data discontinuity in recording")
    import numpy as np
    from pydantic import BaseModel
    _DEPS_OK = True
    _DEPS_ERR = ""
except ImportError as e:
    sc = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    BaseModel = object  # type: ignore[assignment,misc]
    _DEPS_OK = False
    _DEPS_ERR = str(e)

PORT = int(os.environ.get("AUDIO_RECORDER_PORT", "8766"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parent / "recordings"))
# 可选：指定 mic 设备名（模糊匹配，含关键字即可），不设则用系统默认 mic
MIC_NAME_HINT = os.environ.get("AUDIO_MIC_NAME", "").strip()
# 可选：指定扬声器设备名（模糊匹配），用于 loopback 录制系统播放音；不设则用系统默认 speaker
SPK_NAME_HINT = os.environ.get("AUDIO_SPK_NAME", "").strip()
SAMPLE_RATE = 48000
CHANNELS = 1
CHUNK_FRAMES = 1024
STOP_TIMEOUT_SEC = 5
CASE_AUDIO_FILENAME = "case_audio.wav"


class AudioRecorder:
    """mic + speaker loopback 同步录制，单声道混音输出。

    每次 start 新建 recorder 上下文，stop 关闭。
    """

    def __init__(self, mic_device=None, spk_device=None) -> None:
        """可选手动指定 mic/spk 设备对象（soundcard._Microphone）。
        不传则按 AUDIO_MIC_NAME/AUDIO_SPK_NAME 环境变量或系统默认查找。
        """
        self._lock = threading.Lock()
        self._error: str = ""
        self._mic_thread: threading.Thread | None = None
        self._spk_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._mic_chunks: list = []
        self._spk_chunks: list = []
        self._out_dir: Path | None = None
        self._recording = False
        # 显式指定的设备优先级最高
        self._mic_device = mic_device
        self._spk_device = spk_device

    # ---------- 健康检查 ----------
    def is_available(self) -> bool:
        return _DEPS_OK

    def health_issues(self) -> list[str]:
        issues: list[str] = []
        if not _DEPS_OK:
            issues.append(f"缺依赖（soundcard/numpy）：{_DEPS_ERR}")
            return issues
        mic = self._find_default_mic()
        if mic is None:
            issues.append("未找到麦克风设备")
        elif MIC_NAME_HINT and MIC_NAME_HINT not in mic.name and MIC_NAME_HINT.lower() not in mic.name.lower():
            issues.append(f"AUDIO_MIC_NAME='{MIC_NAME_HINT}' 未匹配到任何 mic，回退为默认: {mic.name}")
        spk = self._find_loopback_mic()
        if spk is None:
            issues.append("未找到扬声器 loopback 设备（系统声音录制不可用）")
        elif SPK_NAME_HINT and SPK_NAME_HINT not in spk.name and SPK_NAME_HINT.lower() not in spk.name.lower():
            issues.append(f"AUDIO_SPK_NAME='{SPK_NAME_HINT}' 未匹配到任何 loopback，回退为默认: {spk.name}")
        return issues

    def current_devices(self) -> dict[str, str]:
        """返回当前选中的 mic/spk 设备名，便于排查。"""
        mic = self._find_default_mic()
        spk = self._find_loopback_mic()
        return {
            "mic": mic.name if mic else "",
            "spk_loopback": spk.name if spk else "",
        }

    # ---------- 交互式选设备（启动前锁定） ----------
    @staticmethod
    def list_devices() -> tuple[list, list]:
        """枚举所有 mic / loopback 设备，返回 (mics, loopbacks)。"""
        if not _DEPS_OK:
            return [], []
        try:
            all_mics = sc.all_microphones(include_loopback=True)  # type: ignore[union-attr]
        except Exception:
            return [], []
        mics = [m for m in all_mics if not getattr(m, "isloopback", False)]
        loopbacks = [m for m in all_mics if getattr(m, "isloopback", False)]
        return mics, loopbacks

    @staticmethod
    def pick_devices_interactive() -> tuple[object, object] | None:
        """交互式让用户选 mic / spk loopback，返回 (mic, spk) 或 None（取消/失败）。"""
        if not _DEPS_OK:
            print(f"[audio_recorder] 依赖缺失，无法选设备：{_DEPS_ERR}", file=sys.stderr)
            return None
        mics, loopbacks = AudioRecorder.list_devices()

        mic = AudioRecorder._pick_one(mics, "麦克风（mic 输入）")
        if mic is None:
            print("未选择 mic，退出")
            return None
        print(
            "\n注意：spk loopback 必须与 Windows 当前默认输出设备一致，否则录不到系统声音。\n"
            "      请看 Windows 声音设置 → 输出，选中的是哪个就选哪个 loopback。"
        )
        spk = AudioRecorder._pick_one(loopbacks, "扬声器 loopback（系统播放音）")
        if spk is None:
            print("未选择 spk loopback，退出")
            return None
        return mic, spk  # type: ignore[return-value]

    @staticmethod
    def _pick_one(devices: list, title: str):
        """让用户从 devices 列表中选择一个，返回选中的设备对象。"""
        print(f"\n=== 选择{title} ===")
        if not devices:
            print(f"未找到任何{title}")
            return None
        for i, d in enumerate(devices):
            print(f"  [{i}] {d.name}")
        while True:
            try:
                sel = input(f"输入序号选择{title}（回车=0）: ").strip()
                idx = int(sel) if sel else 0
                if 0 <= idx < len(devices):
                    return devices[idx]
                print(f"序号越界，请输入 0~{len(devices)-1}")
            except ValueError:
                print("请输入数字")
            except (EOFError, KeyboardInterrupt):
                return None

    # ---------- 设备查找 ----------
    def _find_default_mic(self):
        """优先用构造时传入的设备；其次按 AUDIO_MIC_NAME 模糊匹配；再不行用系统默认 mic。"""
        if self._mic_device is not None:
            return self._mic_device
        if MIC_NAME_HINT:
            try:
                mics = sc.all_microphones(include_loopback=False)  # type: ignore[union-attr]
            except Exception:
                mics = []
            # 优先精确包含匹配
            for m in mics:
                if MIC_NAME_HINT in m.name:
                    return m
            # 兜底：忽略大小写匹配
            hint_lower = MIC_NAME_HINT.lower()
            for m in mics:
                if hint_lower in m.name.lower():
                    return m
        try:
            return sc.default_microphone()  # type: ignore[union-attr]
        except Exception:
            return None

    def _find_loopback_mic(self):
        """优先用构造时传入的设备；其次按 AUDIO_SPK_NAME 匹配；再不行用默认 speaker 的 loopback。"""
        if self._spk_device is not None:
            return self._spk_device
        try:
            mics = sc.all_microphones(include_loopback=True)  # type: ignore[union-attr]
        except Exception:
            return None
        loopbacks = [m for m in mics if getattr(m, "isloopback", False)]
        # 1. 优先按环境变量模糊匹配
        if SPK_NAME_HINT:
            hint_lower = SPK_NAME_HINT.lower()
            for m in loopbacks:
                if SPK_NAME_HINT in m.name or hint_lower in m.name.lower():
                    return m
        # 2. 匹配默认 speaker 名字
        try:
            spk = sc.default_speaker()  # type: ignore[union-attr]
        except Exception:
            spk = None
        if spk is not None:
            for m in loopbacks:
                if spk.name in m.name:
                    return m
        # 3. 兜底取第一个 loopback
        return loopbacks[0] if loopbacks else None

    # ---------- 启停 ----------
    def is_recording(self) -> bool:
        return self._recording

    def start(self, out_dir: Path) -> None:
        """启动录音：新建 mic/spk recorder 上下文 + 两个采集线程。"""
        if not _DEPS_OK:
            return
        if self.is_recording():
            self.stop()
        mic = self._find_default_mic()
        spk = self._find_loopback_mic()
        if mic is None or spk is None:
            with self._lock:
                self._error = "mic 或 loopback 设备不可用"
            return
        with self._lock:
            self._out_dir = out_dir
            self._mic_chunks.clear()
            self._spk_chunks.clear()
            self._error = ""
            self._stop_event.clear()
            self._mic_thread = threading.Thread(
                target=self._record, args=(mic, self._mic_chunks), daemon=True
            )
            self._spk_thread = threading.Thread(
                target=self._record, args=(spk, self._spk_chunks), daemon=True
            )
            self._mic_thread.start()
            self._spk_thread.start()
            self._recording = True

    def stop(self) -> Path | None:
        """停止录音，等线程退出，混音写 WAV，返回文件路径。"""
        if not _DEPS_OK or not self._recording:
            return None
        self._stop_event.set()
        if self._mic_thread is not None:
            self._mic_thread.join(timeout=STOP_TIMEOUT_SEC)
        if self._spk_thread is not None:
            self._spk_thread.join(timeout=STOP_TIMEOUT_SEC)
        with self._lock:
            self._mic_thread = None
            self._spk_thread = None
            self._recording = False
            out_dir = self._out_dir
            mic_chunks = list(self._mic_chunks)
            spk_chunks = list(self._spk_chunks)
            err = self._error
            self._mic_chunks.clear()
            self._spk_chunks.clear()
            self._out_dir = None
        if not out_dir or err:
            if err:
                print(f"[audio_recorder] 录音异常：{err}", file=sys.stderr)
            return None
        wav_path = out_dir / CASE_AUDIO_FILENAME
        try:
            self._write_mixed_wav(wav_path, mic_chunks, spk_chunks)
            return wav_path
        except Exception as e:
            print(f"[audio_recorder] 写 WAV 失败：{e}", file=sys.stderr)
            return None

    # ---------- 采集线程 ----------
    def _record(self, device, chunks: list) -> None:
        """新建 recorder 上下文，循环 record 直到 stop_event。"""
        try:
            with device.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS) as r:
                while not self._stop_event.is_set():
                    data = r.record(numframes=CHUNK_FRAMES)
                    with self._lock:
                        chunks.append(data)
        except Exception as e:
            with self._lock:
                self._error = str(e)

    # ---------- 混音 + 写文件 ----------
    @staticmethod
    def _write_mixed_wav(path: Path, mic_chunks: list, spk_chunks: list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        mic_arr = np.concatenate(mic_chunks, axis=0).flatten() if mic_chunks else np.zeros(0, dtype=np.float32)
        spk_arr = np.concatenate(spk_chunks, axis=0).flatten() if spk_chunks else np.zeros(0, dtype=np.float32)
        min_len = min(len(mic_arr), len(spk_arr))
        if min_len == 0:
            mixed = mic_arr if len(mic_arr) > 0 else spk_arr
        else:
            mixed = (mic_arr[:min_len] + spk_arr[:min_len]) / 2.0
        # float32 [-1,1] -> int16
        clipped = np.clip(mixed, -1.0, 1.0)
        int16_data = (clipped * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(int16_data.tobytes())


# ---------- 独立测试服务 ----------
class _StartReq(BaseModel):
    case_id: str
    batch_id: str = ""


class _StopReq(BaseModel):
    case_id: str = ""


def _build_test_app(rec: AudioRecorder) -> "object":
    from fastapi import FastAPI, HTTPException

    app = FastAPI(title="Audio Recorder (Test)")

    class _State:
        case_id: str = ""
        dir: Path | None = None

    state = _State()

    @app.get("/health")
    def health() -> dict:
        return {
            "available": rec.is_available(),
            "recording": rec.is_recording(),
            "issues": rec.health_issues(),
            "devices": rec.current_devices(),
            "output_dir": str(OUTPUT_DIR.resolve()),
        }

    @app.post("/start")
    def start(body: _StartReq) -> dict:
        if not rec.is_available():
            raise HTTPException(status_code=400, detail="audio_recorder 不可用")
        issues = rec.health_issues()
        if issues:
            raise HTTPException(status_code=400, detail="、".join(issues))
        out_dir = OUTPUT_DIR / "test" / body.case_id / time.strftime("%Y%m%d_%H%M%S")
        out_dir.mkdir(parents=True, exist_ok=True)
        state.case_id = body.case_id
        state.dir = out_dir
        rec.start(out_dir)
        return {"ok": True, "case_id": body.case_id, "dir": str(out_dir.resolve())}

    @app.post("/stop")
    def stop(body: _StopReq) -> dict:
        wav = rec.stop()
        return {"ok": wav is not None, "case_id": state.case_id, "wav": str(wav) if wav else ""}

    return app


if __name__ == "__main__":
    import uvicorn

    # 启动测试服务前交互式锁定 mic / spk 设备
    picked = AudioRecorder.pick_devices_interactive()
    if picked is None:
        print("未选择音频设备，退出。请重新运行并选择。", file=sys.stderr)
        sys.exit(1)
    mic_dev, spk_dev = picked
    rec = AudioRecorder(mic_device=mic_dev, spk_device=spk_dev)
    print(f"AudioRecorder test service on http://127.0.0.1:{PORT}")
    print(f"已锁定 mic={mic_dev.name!r} spk_loopback={spk_dev.name!r}")
    uvicorn.run(_build_test_app(rec), host="127.0.0.1", port=PORT)
