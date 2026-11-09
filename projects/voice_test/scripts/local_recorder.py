#!/usr/bin/env python3
"""
本地记录服务：/health /start /stop（默认 http://127.0.0.1:8765）
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import TextIO

# Windows 默认 GBK，强制 stdout/stderr 用 UTF-8，避免设备名含 ® 等字符时崩溃
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logger = logging.getLogger("local_recorder")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

# 本地音频录制（mic + speaker loopback 混音，生成 case_audio.wav）
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from audio_recorder import AudioRecorder

    _AUDIO_OK = True
except Exception as _audio_err:  # pragma: no cover
    AudioRecorder = None  # type: ignore[assignment,misc]
    _AUDIO_OK = False
    _AUDIO_ERR = str(_audio_err)


# ── TOS 上传（内联，不依赖项目其他模块） ──────────────────────────────────
TOS_BUCKET_NAME = "mb-voice-test"
TOS_ACCESS_KEY_ID = "REDACTED"
TOS_ACCESS_KEY_SECRET = "REDACTED"
TOS_ENDPOINT = "https://tos-cn-beijing.volces.com"
TOS_REGION = "cn-beijing"
TOS_BASE_PATH = "dev/BenZ_test"
ENABLE_TOS_UPLOAD = True
# 分片上传阈值：超过则走分片上传，避免大文件一次性读进内存导致失败/不完整
TOS_MULTIPART_THRESHOLD = 10 * 1024 * 1024  # 10MB
TOS_PART_SIZE = 5 * 1024 * 1024  # 5MB（TOS 分片最小 5MB）
TOS_UPLOAD_TASK_NUM = 5  # 分片并发数


def _tos_sdk_endpoint() -> str:
    host = TOS_ENDPOINT.strip()
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host.rstrip("/")



PORT = int(os.environ.get("PORT", "8765"))
OUTPUT_DIR = Path(
    os.environ.get("OUTPUT_DIR", Path(__file__).resolve().parent / "recordings")
)
ADB_BIN = os.environ.get("ADB_BIN", "").strip().strip('"')
SCRCPY_BIN = os.environ.get("SCRCPY_BIN", "").strip().strip('"')
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "").strip().strip('"')
ENABLE_TOS_UPLOAD = True

SCREEN_VIDEO_FILENAME = "screen.mkv"
LOGCAT_FILENAME = "logcat.log"
CASE_AUDIO_FILENAME = "case_audio.wav"
MERGED_VIDEO_FILENAME = "merged.mp4"
CASE_RESULT_FILENAME = "case_result.json"
STOP_TIMEOUT_SEC = 3

# case 评测结果 marker 文件：空文件，仅用文件名做视觉标记，便于在文件系统一眼看出过没过
RESULT_MARKER_PASS = "RESULT_PASS"
RESULT_MARKER_FAIL = "RESULT_FAIL"
RESULT_MARKER_SKIP = "RESULT_SKIP"
RESULT_MARKER_ERROR = "RESULT_ERROR"
RESULT_MARKERS = (
    RESULT_MARKER_PASS,
    RESULT_MARKER_FAIL,
    RESULT_MARKER_SKIP,
    RESULT_MARKER_ERROR,
)


class HealthResponse(BaseModel):
    ready: bool
    devices: list[str]
    recording: str | None = None
    output_dir: str
    issues: list[str] = Field(default_factory=list)
    tos_enabled: bool = False


class StartRequest(BaseModel):
    case_id: str
    batch_id: str = ""
    # >0 时子目录名为 r01_时间戳，便于多遍区分；0 则只用时间戳
    run_index: int = 0


class StartResponse(BaseModel):
    ok: bool
    case_id: str
    dir: str


class StopRequest(BaseModel):
    case_id: str = ""


class StopItemResponse(BaseModel):
    ok: bool
    case_id: str
    dir: str
    message: str = ""


class StopResponse(BaseModel):
    stopped: list[StopItemResponse] = Field(default_factory=list)


class CaseResultRequest(BaseModel):
    """前端转发过来的 case 评测结果；除 case_id、dir 必填外，其他字段全透传写入 case_result.json。"""

    model_config = ConfigDict(extra="allow")

    case_id: str
    # 前端从 /start 拿到的录制目录绝对路径，后端直接用它写结果，不再维护映射反查
    dir: str
    execution_success: bool = False
    judge_status: str = "not_run"
    is_passed: bool | None = None
    reason: str | None = None
    repeat_index: int | None = None
    repeat_n: int | None = None
    history_for_judge: str = ""
    task_run_item_id: str = ""
    callback_url: str = ""


class CaseResultResponse(BaseModel):
    ok: bool
    case_id: str
    dir: str = ""
    result_tag: str
    message: str = ""


def _tool(name: str, explicit: str) -> str | None:
    if explicit and Path(explicit).is_file():
        return str(Path(explicit).resolve())
    return shutil.which(name)


def _adb() -> str:
    path = _tool("adb", ADB_BIN)
    if not path:
        raise FileNotFoundError("adb not found")
    return path


def _scrcpy() -> str:
    path = _tool("scrcpy", SCRCPY_BIN)
    if not path:
        raise FileNotFoundError("scrcpy not found")
    return path


def _ffmpeg() -> str | None:
    return _tool("ffmpeg", FFMPEG_BIN)


def _win_flags() -> int:
    if sys.platform != "win32":
        return 0
    return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]


def _safe_name(name: str, max_len: int = 80) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.strip())[:max_len]
    return s or "未命名"


def _result_tag_from_outcome(
    execution_success: bool,
    judge_status: str,
    is_passed: bool | None,
) -> str:
    """与后端 _save_voice_case_result 入库语义对齐：判定单 case 的结果标签。"""
    js = (judge_status or "").strip().lower()
    if js == "completed":
        return "PASS" if is_passed is True else "FAIL"
    if js == "skipped":
        return "SKIP"
    # failed / not_run / 执行失败一律归为 ERROR
    return "ERROR"


def _marker_for_tag(tag: str) -> str:
    return {
        "PASS": RESULT_MARKER_PASS,
        "FAIL": RESULT_MARKER_FAIL,
        "SKIP": RESULT_MARKER_SKIP,
        "ERROR": RESULT_MARKER_ERROR,
    }.get(tag, RESULT_MARKER_ERROR)


def _case_dir(batch_id: str, case_id: str, run_index: int = 0) -> Path:
    """目录：{batch或日期}/{case_id}/{r01_时间戳|时间戳}/ —— 同 case 一层，遍数用子目录区分。"""
    batch = (
        _safe_name(batch_id) if batch_id.strip() else datetime.now().strftime("%Y%m%d")
    )
    case = _safe_name(case_id)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sub = f"r{run_index:02d}_{stamp}" if run_index > 0 else stamp
    base = OUTPUT_DIR / batch / case
    out = base / sub
    n = 2
    while out.exists():
        out = base / f"{sub}_{n}"
        n += 1
    return out


def _write_case_result(
    out_dir: Path,
    req: CaseResultRequest,
) -> tuple[str, str]:
    """把 case 评测结果写入 case_result.json + marker 空文件，返回 (result_tag, dir)。"""
    result_tag = _result_tag_from_outcome(
        req.execution_success, req.judge_status, req.is_passed
    )
    # 透传前端转发过来的所有字段，后端加字段无需改本地服务
    payload = {
        **req.model_dump(),
        "result_tag": result_tag,
        "result_written_at": datetime.now().isoformat(timespec="seconds"),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    # 先清掉旧的 marker，避免同一目录多次写入时残留多种结果
    for marker in RESULT_MARKERS:
        old = out_dir / marker
        if old.exists():
            try:
                old.unlink()
            except OSError:
                pass
    (out_dir / CASE_RESULT_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # marker 是空文件，仅用文件名做视觉标记
    (out_dir / _marker_for_tag(result_tag)).touch()
    logger.info(
        f"[result] 写入完成: dir={out_dir} tag={result_tag} judge_status={req.judge_status} is_passed={req.is_passed}"
    )
    return result_tag, str(out_dir.resolve())


def _tos_available() -> bool:
    if not ENABLE_TOS_UPLOAD:
        return False
    if not TOS_BUCKET_NAME or not TOS_ACCESS_KEY_ID or not TOS_ACCESS_KEY_SECRET:
        return False
    return True


def _upload_file_to_tos(
    file_path: Path, task_run_item_id: str, kind: str, content_type: str
) -> str | None:
    """上传单个文件到 TOS，返回 object_key。kind 决定 object_key 路径后缀（merged/logcat）。

    大文件（>TOS_MULTIPART_THRESHOLD）走分片上传，避免一次性读进内存导致失败/不完整。
    """
    if not _tos_available():
        logger.info("[tos] TOS 未启用或配置不完整，跳过上传")
        return None
    if not file_path.is_file():
        logger.error(f"[tos] 文件不存在，跳过上传: {file_path}")
        return None
    try:
        import tos
    except ImportError:
        logger.error(f"[tos] tos SDK 未安装，跳过上传: {file_path.name}")
        return None
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"voice_test_recordings/{task_run_item_id}/{timestamp}_{kind}{'_merged.mp4' if kind == 'merged' else '.log'}"
        base = TOS_BASE_PATH.strip("/")
        object_key = f"{base}/{suffix}" if base else suffix
        key = object_key.lstrip("/")
        file_size = file_path.stat().st_size
        client = tos.TosClientV2(
            TOS_ACCESS_KEY_ID,
            TOS_ACCESS_KEY_SECRET,
            _tos_sdk_endpoint(),
            TOS_REGION,
        )

        # 大文件走分片上传；小文件走 put_object
        if file_size > TOS_MULTIPART_THRESHOLD:
            logger.info(
                f"[tos] 分片上传: file={file_path.name} size={file_size}B part_size={TOS_PART_SIZE}B object_key={object_key}"
            )
            try:
                client.upload_file(
                    TOS_BUCKET_NAME,
                    key,
                    file_path=str(file_path.resolve()),
                    content_type=content_type,
                    part_size=TOS_PART_SIZE,
                    task_num=TOS_UPLOAD_TASK_NUM,
                )
            except Exception as e:
                logger.error(f"[tos] 分片上传失败: object_key={key} err={e}")
                return None
            logger.info(f"[tos] 分片上传成功: object_key={key} size={file_size}B")
            return key

        logger.info(
            f"[tos] put_object: file={file_path.name} size={file_size}B object_key={object_key}"
        )
        with file_path.open("rb") as f:
            data = f.read()
        resp = client.put_object(
            TOS_BUCKET_NAME,
            key,
            content=data,
            content_type=content_type,
        )
        if resp.status_code != 200:
            logger.error(f"[tos] 上传失败: status={resp.status_code}")
            return None
        logger.info(f"[tos] 上传成功: object_key={key} size={file_size}B")
        return key
    except Exception as e:
        import traceback

        logger.error(f"[tos] 上传异常: {e}\n{traceback.format_exc()}")
        return None


def _callback_update_metadata(callback_url: str, object_keys: dict[str, str]) -> bool:
    """回调后端更新 metadata。object_keys 里的非空字段会透传到 PATCH body。"""
    if not callback_url.strip() or not any(object_keys.values()):
        logger.error(
            f"[tos] 回调参数为空，跳过: callback_url={callback_url!r} object_keys={object_keys}"
        )
        return False
    try:
        payload_dict = {k: v for k, v in object_keys.items() if v}
        logger.info(
            f"[tos] 开始回调更新 metadata: url={callback_url} payload={payload_dict}"
        )
        payload = json.dumps(payload_dict).encode("utf-8")
        req = urllib.request.Request(
            callback_url.strip(),
            data=payload,
            method="PATCH",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            ok = 200 <= resp.status < 300
            body = resp.read().decode("utf-8", errors="replace")
            if ok:
                logger.info(f"[tos] 回调成功: status={resp.status} body={body[:200]}")
            else:
                logger.error(f"[tos] 回调失败: status={resp.status} body={body[:200]}")
            return ok
    except Exception as e:
        import traceback

        logger.error(f"[tos] 回调异常: {e}\n{traceback.format_exc()}")
        return False


def _merge_av(out_dir: Path) -> None:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        logger.warning(f"[merge] 跳过：未安装 ffmpeg，dir={out_dir}")
        return
    video = out_dir / SCREEN_VIDEO_FILENAME
    audio = out_dir / CASE_AUDIO_FILENAME
    merged = out_dir / MERGED_VIDEO_FILENAME
    if not video.is_file() or not audio.is_file():
        logger.warning(
            f"[merge] 跳过：源文件缺失 video={video.is_file()} audio={audio.is_file()} dir={out_dir}"
        )
        return
    v_size = video.stat().st_size
    a_size = audio.stat().st_size
    logger.info(f"[merge] 开始合成: dir={out_dir} video={v_size}B audio={a_size}B")
    t0 = time.monotonic()
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(video.resolve()),
            "-i",
            str(audio.resolve()),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(merged.resolve()),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        creationflags=_win_flags(),
    )
    elapsed = time.monotonic() - t0
    # 合并成功才删源文件，避免合并失败导致数据全丢
    if merged.is_file() and merged.stat().st_size > 0:
        m_size = merged.stat().st_size
        logger.info(
            f"[merge] 合成成功: dir={out_dir} merged={m_size}B 耗时={elapsed:.2f}s"
        )
        try:
            video.unlink()
        except OSError:
            pass
        try:
            audio.unlink()
        except OSError:
            pass
        logger.info("[merge] 已清理源文件: screen.mkv + case_audio.wav")
    else:
        logger.error(
            f"[merge] 合成失败: returncode={completed.returncode} merged_size={merged.stat().st_size if merged.is_file() else 0} 耗时={elapsed:.2f}s dir={out_dir}"
        )


class Recorder:
    def __init__(self, mic_device=None, spk_device=None) -> None:
        self.proc: subprocess.Popen[bytes] | None = None
        self.log_proc: subprocess.Popen[bytes] | None = None
        self.log_file_fh: TextIO | None = None
        self.case_id = ""
        self.dir: Path | None = None
        # TOS 上传信息：key=目录路径字符串，value=(task_run_item_id, callback_url)
        # /case_result 时写入，后处理/上传线程读取
        self._upload_info: dict[str, tuple[str, str]] = {}
        # 合成完成事件：key=目录路径字符串，value=Event；ffmpeg 退出后才 set，供上传线程等待文件完整
        self._merge_done: dict[str, threading.Event] = {}
        self._upload_lock = threading.Lock()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # 本地音频录制器（mic + speaker loopback 混音）
        self.audio: AudioRecorder | None = None
        if _AUDIO_OK:
            try:
                self.audio = AudioRecorder(mic_device=mic_device, spk_device=spk_device)
            except Exception as e:
                logger.error(f"[audio] AudioRecorder 初始化失败：{e}")

    def devices(self) -> list[str]:
        out = subprocess.run(
            [_adb(), "devices"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=_win_flags(),
        )
        devices: list[str] = []
        for line in (out.stdout or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    def health(self) -> HealthResponse:
        adb_ok = _tool("adb", ADB_BIN) is not None
        scrcpy_ok = _tool("scrcpy", SCRCPY_BIN) is not None
        ffmpeg_ok = _ffmpeg() is not None
        issues: list[str] = []
        if not adb_ok:
            issues.append("没装 adb（Android 调试工具）")
        if not scrcpy_ok:
            issues.append("没装 scrcpy（本地记录依赖）")
        if not ffmpeg_ok:
            issues.append("没装 ffmpeg（音画合成）")
        # 检查本地音频录制器
        if self.audio is None or not self.audio.is_available():
            issues.append("本地音频录制不可用（缺 soundcard/numpy）")
        else:
            audio_issues = self.audio.health_issues()
            issues.extend(audio_issues)
        devices: list[str] = []
        if adb_ok:
            try:
                devices = self.devices()
            except OSError:
                issues.append("adb 命令异常，请检查是否已安装")
        if adb_ok and not devices and not any("adb 命令" in x for x in issues):
            issues.append("手机未连接（请 USB 连电脑并打开调试）")
        return HealthResponse(
            ready=len(issues) == 0,
            devices=devices,
            recording=self.case_id or None,
            output_dir=str(OUTPUT_DIR.resolve()),
            issues=issues,
            tos_enabled=_tos_available(),
        )

    def _require_ready(self, case_id: str) -> str:
        case_id = case_id.strip()
        if not case_id:
            raise RuntimeError("case_id 不能为空")
        h = self.health()
        if not h.ready:
            raise RuntimeError("、".join(h.issues) or "本地记录未就绪")
        return case_id

    def _prepare_case_dir(
        self, case_id: str, batch_id: str, run_index: int = 0
    ) -> Path:
        self.case_id = case_id
        self.dir = _case_dir(batch_id, case_id, run_index=run_index)
        self.dir.mkdir(parents=True, exist_ok=True)
        return self.dir

    def _clear_logcat(self) -> None:
        subprocess.run(
            [_adb(), "logcat", "-c"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=_win_flags(),
        )

    def _start_scrcpy(self, record_path: Path) -> None:
        # 实现了将手机待播放的音频转到电脑播放了。但是mic 的声音没法记录。android原因，同时只能有一方调取mic。
        cmd = [
            _scrcpy(),
            "--no-control",
            # "--audio-source=output",# 可以由电脑播放
            "--no-audio",
            "--window-x=9999",
            "--window-y=9999",
            "--window-width=100",
            "--window-height=100",
            f"--record={record_path.resolve()}",
        ]
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_win_flags(),
        )
        logger.info(f"[scrcpy] 已启动: pid={self.proc.pid} record={record_path.name}")

    def _start_logcat(self, log_path: Path) -> None:
        fh = log_path.open("w", encoding="utf-8", errors="replace")
        self.log_file_fh = fh
        self.log_proc = subprocess.Popen(
            [_adb(), "logcat", "-v", "time"],
            stdout=fh,
            stderr=subprocess.DEVNULL,
            creationflags=_win_flags(),
        )
        logger.info(f"[logcat] 已启动: pid={self.log_proc.pid} log={log_path.name}")

    def start(
        self, case_id: str, batch_id: str = "", run_index: int = 0
    ) -> StartResponse:
        self.stop()
        case_id = self._require_ready(case_id)
        out_dir = self._prepare_case_dir(case_id, batch_id, run_index=run_index)
        logger.info(
            f"[start] 开始录制: case_id={case_id} run_index={run_index} dir={out_dir}"
        )
        self._clear_logcat()
        self._start_scrcpy(out_dir / SCREEN_VIDEO_FILENAME)
        self._start_logcat(out_dir / LOGCAT_FILENAME)
        # 同步启动本地音频录制（mic + speaker loopback）
        if self.audio is not None and self.audio.is_available():
            try:
                self.audio.start(out_dir)
                logger.info(f"[audio] 已启动: dir={out_dir}")
            except Exception as e:
                logger.error(f"[audio] start 失败：{e}")
        else:
            logger.info("[audio] 跳过：AudioRecorder 不可用")
        return StartResponse(ok=True, case_id=case_id, dir=str(out_dir.resolve()))

    def _stop_scrcpy(self) -> None:
        proc = self.proc
        if proc is not None and proc.poll() is None:
            pid = proc.pid
            # Windows: taskkill；Unix: terminate（macOS 待测试）
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/pid", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                proc.terminate()
            deadline = time.monotonic() + STOP_TIMEOUT_SEC
            while proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=STOP_TIMEOUT_SEC)
            logger.info(f"[scrcpy] 已停止: pid={pid}")
        self.proc = None

    def _stop_logcat(self) -> None:
        if self.log_proc is not None and self.log_proc.poll() is None:
            pid = self.log_proc.pid
            self.log_proc.terminate()
            self.log_proc.wait(timeout=STOP_TIMEOUT_SEC)
            logger.info(f"[logcat] 已停止: pid={pid}")
        self.log_proc = None
        if self.log_file_fh is not None:
            self.log_file_fh.close()
        self.log_file_fh = None

    def _clear_session(self) -> tuple[str, Path | None]:
        case_id = self.case_id
        out_dir = self.dir
        self.case_id = ""
        self.dir = None
        return case_id, out_dir

    def _run_stop_postprocess(self, out_dir: Path | None) -> None:
        if not out_dir:
            return
        # 注册合成完成事件：ffmpeg 退出（进程结束）才 set，保证文件已写完整
        key = str(out_dir.resolve())
        done_evt = threading.Event()
        with self._upload_lock:
            self._merge_done[key] = done_evt

        # 目录不再改名，后处理线程直接用 out_dir 做 ffmpeg 合成
        def _run() -> None:
            try:
                logger.info(f"[postprocess] 后处理线程启动: dir={out_dir}")
                _merge_av(out_dir)
            finally:
                done_evt.set()
                logger.info(f"[postprocess] 合成线程结束: dir={out_dir}")

        threading.Thread(target=_run, daemon=True).start()

    def stop(self) -> StopItemResponse | None:
        if not self.case_id and not self.dir:
            return None
        logger.info(f"[stop] 停止录制: case_id={self.case_id} dir={self.dir}")
        self._stop_scrcpy()
        self._stop_logcat()
        # 停止本地音频录制，生成 case_audio.wav
        if self.audio is not None and self.audio.is_recording():
            try:
                self.audio.stop()
                logger.info(f"[audio] 已停止: dir={self.dir}")
            except Exception as e:
                logger.error(f"[audio] stop 失败：{e}")
        case_id, out_dir = self._clear_session()
        self._run_stop_postprocess(out_dir)
        return StopItemResponse(
            ok=True,
            case_id=case_id,
            dir=str(out_dir.resolve()) if out_dir else "",
        )

    def write_case_result(self, req: CaseResultRequest) -> CaseResultResponse:
        """直接用前端传来的 dir 写结果，不改目录名；若带 TOS 字段则启动后台上传。"""
        out_dir = Path(req.dir).resolve() if req.dir.strip() else None
        if out_dir is None or not out_dir.is_dir():
            logger.error(f"[result] 未找到 dir={req.dir} 对应的录制目录")
            return CaseResultResponse(
                ok=False,
                case_id=req.case_id,
                dir=req.dir,
                result_tag="ERROR",
                message=f"未找到 dir={req.dir} 对应的录制目录",
            )
        result_tag, dir_str = _write_case_result(out_dir, req)
        # 记录 TOS 上传信息，启动后台上传线程（降级：失败不影响主流程）
        if _tos_available() and req.task_run_item_id and req.callback_url:
            logger.info(
                f"[tos] 收到上传任务: task_run_item_id={req.task_run_item_id} callback_url={req.callback_url} dir={out_dir}"
            )
            with self._upload_lock:
                self._upload_info[str(out_dir.resolve())] = (
                    req.task_run_item_id,
                    req.callback_url,
                )
            threading.Thread(
                target=self._upload_and_callback,
                args=(out_dir,),
                daemon=True,
            ).start()
        else:
            logger.info(
                f"[tos] 不上传: tos_enabled={_tos_available()} task_run_item_id={req.task_run_item_id!r} callback_url={req.callback_url!r}"
            )
        return CaseResultResponse(
            ok=True,
            case_id=req.case_id,
            dir=dir_str,
            result_tag=result_tag,
        )

    def _upload_and_callback(self, out_dir: Path) -> None:
        """等待 merged.mp4 生成后上传 TOS 并回调后端更新 metadata。"""
        try:
            self._upload_and_callback_inner(out_dir)
        except Exception as e:
            import traceback

            logger.error(f"[tos] 上传线程异常退出: {e}\n{traceback.format_exc()}")

    def _upload_and_callback_inner(self, out_dir: Path) -> None:
        logger.info(f"[tos] 上传线程启动，等待 merged.mp4: dir={out_dir}")
        merged = out_dir / MERGED_VIDEO_FILENAME
        log_file = out_dir / LOGCAT_FILENAME
        # 取该目录的合成完成事件；拿不到则退化为仅按文件大小判断（兼容未走 stop 的异常路径）
        key = str(out_dir.resolve())
        with self._upload_lock:
            done_evt = self._merge_done.get(key)
        if done_evt is None:
            logger.warning(f"[tos] 未找到合成完成事件，退化为按文件大小等待: {out_dir}")
        # 最多等 10 分钟，每 2 秒检查一次；必须等 ffmpeg 退出(文件写完整)且文件非空
        max_wait = 600
        interval = 2
        waited = 0
        while waited < max_wait:
            size_ok = merged.is_file() and merged.stat().st_size > 0
            merge_ok = done_evt is None or done_evt.is_set()
            if size_ok and merge_ok:
                logger.info(
                    f"[tos] merged.mp4 已就绪: size={merged.stat().st_size} bytes，等待 {waited}s"
                )
                break
            time.sleep(interval)
            waited += interval
            if waited % 30 == 0:
                logger.info(f"[tos] 等待 merged.mp4 完整生成中... 已等 {waited}s")

        if not merged.is_file() or merged.stat().st_size == 0:
            logger.error(f"[tos] merged.mp4 未生成，跳过上传: {out_dir}")
            return

        with self._upload_lock:
            info = self._upload_info.get(str(out_dir.resolve()))
        if not info:
            logger.error(f"[tos] 未找到上传信息，跳过: {out_dir}")
            return
        task_run_item_id, callback_url = info
        logger.info(f"[tos] 准备上传: task_run_item_id={task_run_item_id}")

        # 视频 + 日志并行上传（互不依赖），都完成后一次性回调
        video_key = _upload_file_to_tos(merged, task_run_item_id, "merged", "video/mp4")
        log_key = None
        if log_file.is_file() and log_file.stat().st_size > 0:
            log_key = _upload_file_to_tos(log_file, task_run_item_id, "logcat", "text/plain")
        else:
            logger.warning(f"[tos] logcat.log 不存在或为空，跳过上传: {log_file}")

        object_keys = {"video_object_key": video_key or "", "log_object_key": log_key or ""}
        if not any(object_keys.values()):
            logger.error("[tos] 视频+日志全部上传失败，跳过回调")
            return
        if not video_key:
            logger.warning("[tos] 视频上传失败，仅回调日志")
        if callback_url:
            _callback_update_metadata(callback_url, object_keys)
        else:
            logger.warning("[tos] 无 callback_url，跳过回调")


rec = Recorder()
app = FastAPI(title="Voice Test Local Recorder")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return rec.health()


@app.post("/start", response_model=StartResponse)
def start(body: StartRequest) -> StartResponse:
    try:
        return rec.start(body.case_id, body.batch_id, run_index=body.run_index)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/stop", response_model=StopResponse)
def stop(body: StopRequest | None = None) -> StopResponse:
    req_case = (body.case_id if body else "").strip()
    if req_case and rec.case_id and rec.case_id != req_case:
        return StopResponse(stopped=[])
    item = rec.stop()
    if item is None:
        return StopResponse(stopped=[])
    return StopResponse(stopped=[item])


@app.post("/case_result", response_model=CaseResultResponse)
def case_result(body: CaseResultRequest) -> CaseResultResponse:
    """前端在 batch_case_result 事件时转发 outcome，写入 case_result.json + marker。"""
    try:
        return rec.write_case_result(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    # 启动服务前交互式锁定 mic / spk loopback 设备，避免运行中默认设备被切换导致 mic 静音
    if _AUDIO_OK:
        picked = AudioRecorder.pick_devices_interactive()
        if picked is None:
            logger.error("[local_recorder] 未选择音频设备，退出。请重新启动并选择。")
            sys.exit(1)
        mic_dev, spk_dev = picked
        try:
            rec.audio = AudioRecorder(mic_device=mic_dev, spk_device=spk_dev)
            logger.info(
                f"[local_recorder] 已锁定音频设备: mic={mic_dev.name!r} spk_loopback={spk_dev.name!r}"
            )
        except Exception as e:
            logger.error(f"[local_recorder] AudioRecorder 初始化失败：{e}")
            sys.exit(1)
    else:
        logger.warning(f"[local_recorder] 音频录制不可用，跳过设备选择：{_AUDIO_ERR}")

    logger.info(f"[local_recorder] 服务启动于 http://127.0.0.1:{PORT}")
    logger.info(f"[local_recorder] 录制根目录: {OUTPUT_DIR.resolve()}")
    logger.info(
        f"[local_recorder] TOS 上传: {'已启用 (bucket=' + TOS_BUCKET_NAME + ', region=' + TOS_REGION + ')' if _tos_available() else '未启用'}"
    )
    logger.info(f"[local_recorder] 音频录制: {'可用' if _AUDIO_OK else '不可用: ' + _AUDIO_ERR}")
    uvicorn.run(app, host="127.0.0.1", port=PORT)
