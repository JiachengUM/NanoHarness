#!/usr/bin/env python3
"""本地记录服务 v2：/health /start /stop /case_result（接口与 local_recorder.py 一致）

v2 = v1(最新版, 含 TOS 上传/分片/日志系统) + 车机日志证据链增强：

【来自 v1 最新 pull 的逻辑】
  1. logging 日志系统（logger 替代 print）
  2. TOS 上传：merged.mp4 + logcat.log + evidence.json/md 上传火山 TOS（>10MB 分片），
     /case_result 带 task_run_item_id + callback_url 时启动后台上传线程，
     上传完成后 PATCH 回调后端（video/logcat/evidence/evidence_md 四个 object_key）
  3. /case_result 新接口：前端直接传 dir 绝对路径写结果，不再维护目录映射/改目录名
  4. 去掉音频设备交互选择、去掉 audio_url 下载兜底（本地录音已是唯一来源）
  5. _merge_av 合成成功后清理源文件（screen.mkv + case_audio.wav）

【v2 独有的证据链增强（来自 2026-08-11 session 的四层证据链分析）】
  6. logcat 采集：-v threadtime（带 PID/TID）+ 显式 -b main,system,crash
     （四层证据所在 buffer 最小集；实测 L1/L3 证据行可能落在 crash 段，不能省；
      不能加 *:I 优先级过滤——L4 的 CAR.HAL 证据是 D 级）
  7. case 开始/结束时尽力打 VoiceCase 设备标记 + 记录设备时间（时间对齐用，无权限静默降级）
  8. case 后处理自动提取粗粒度四层证据：
       - evidence.json：结构化，供裁判 AI 直接判"agent 是否真执行了操作"
       - evidence.md：人类可读，供人工复核
     粒度：粗粒度 = 时间窗匹配（L2 [-15s,+5s]，L3 [0,+5s]，L4 [0,+10s]），未做 recordId 串链
  9. 按需求暂缓：logcat watchdog 断线重连、多设备 -s 选择、日志轮转
  10. 启动时把电脑时间同步到设备（需 adb root；SYNC_DEVICE_TIME=0 可关闭跳过），
      同步失败直接终止启动；时间对齐以设备时间为准（同步成功后即等于电脑时间）

产物（每个 case 目录）：
  screen.mkv / case_audio.wav / merged.mp4 / logcat.log
  evidence.json / evidence.md（v2 新增）
  case_result.json + RESULT_PASS/FAIL/SKIP/ERROR marker
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
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import TextIO

# Windows 默认 GBK，强制 stdout/stderr 用 UTF-8，避免设备名含 ® 等字符时崩溃
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logger = logging.getLogger("local_recorder_v2")
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


# ── TOS 上传（内联，不依赖项目其他模块；来自 v1） ─────────────────────────
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

SCREEN_VIDEO_FILENAME = "screen.mkv"
LOGCAT_FILENAME = "logcat.log"
CASE_AUDIO_FILENAME = "case_audio.wav"
MERGED_VIDEO_FILENAME = "merged.mp4"
CASE_RESULT_FILENAME = "case_result.json"
EVIDENCE_JSON_FILENAME = "evidence.json"
EVIDENCE_MD_FILENAME = "evidence.md"
STOP_TIMEOUT_SEC = 3

# 初始化时是否把电脑时间同步到设备（需 adb root；置 0 关闭）
SYNC_DEVICE_TIME = os.environ.get("SYNC_DEVICE_TIME", "1") != "0"

# ---- v2 新增：logcat 采集参数 ----
# 四层证据所在 buffer 的最小集（见文件头注释）；threadtime 带 PID/TID
LOGCAT_FORMAT = "threadtime"
LOGCAT_BUFFERS = "main,system,crash"

# ---- v2 新增：证据提取（query 驱动，见 parse_dm_queries.py） ----
# query 边界 = onAsrResult 按 recordId 分组；事件分类 = decision/operation/reply/
# results/ui_changes/state；不再使用时间窗匹配（旧四层实现已废弃）。

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
    recorder_version: str = "v2-evidence"


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


# ── TOS 上传（来自 v1） ───────────────────────────────────────────────────


def _tos_available() -> bool:
    if not ENABLE_TOS_UPLOAD:
        return False
    if not TOS_BUCKET_NAME or not TOS_ACCESS_KEY_ID or not TOS_ACCESS_KEY_SECRET:
        return False
    return True


def _upload_file_to_tos(
    file_path: Path, task_run_item_id: str, kind: str, content_type: str
) -> str | None:
    """上传单个文件到 TOS，返回 object_key。kind 决定 object_key 路径后缀（merged/logcat/evidence/evidence_md）。

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
        ext_by_kind = {
            "merged": "_merged.mp4",
            "logcat": ".log",
            "evidence": ".json",
            "evidence_md": ".md",
        }
        suffix = f"voice_test_recordings/{task_run_item_id}/{timestamp}_{kind}{ext_by_kind.get(kind, '.log')}"
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


# ============================================================================
# v2 新增：设备时间 / VoiceCase 标记（尽力而为，失败不影响主流程）
# ============================================================================


def _device_date() -> dict | None:
    """读设备当前时间 (epoch + 文本)，用于证据时间对齐；失败返回 None。"""
    try:
        out = subprocess.run(
            [_adb(), "shell", "date '+%s %F %T'"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=_win_flags(),
            timeout=5,
        )
        parts = (out.stdout or "").strip().split()
        if len(parts) >= 3 and parts[0].isdigit():
            return {"epoch": int(parts[0]), "text": f"{parts[1]} {parts[2]}"}
    except Exception:
        pass
    return None


def _mark_voice_case(event: str, case_id: str) -> None:
    """尽力而为：往设备 log 打一条 VoiceCase 标记（便于对齐 case 边界）。
    log 命令无权限/不存在时静默忽略。"""
    try:
        msg = f"VoiceCase|{event}|{_safe_name(case_id)}"
        subprocess.run(
            [_adb(), "shell", f"log -t VoiceCase -p I '{msg}'"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=_win_flags(),
            timeout=5,
        )
    except Exception:
        pass


# 设备时间同步状态（写入 evidence 供裁判参考对齐方式）
TIME_SYNC_STATE: dict = {"attempted": False, "ok": False, "at": "", "note": ""}


def _sync_device_time() -> bool:
    """把电脑时间同步到设备（需 adb root；参考 Windows 版时间同步脚本）。

    仅服务启动时调用一次：失败时由调用方终止启动（见 __main__）。
    同步状态写入 TIME_SYNC_STATE，随 evidence 输出，供裁判参考时间对齐方式。
    """
    try:
        TIME_SYNC_STATE["attempted"] = True
        # 0. 设备必须已连接，否则直接失败（由调用方决定是否终止启动）
        out = subprocess.run(
            [_adb(), "devices"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=_win_flags(),
        )
        has_device = any(
            len(p) >= 2 and p[1] == "device"
            for p in (line.split() for line in (out.stdout or "").splitlines()[1:])
        )
        if not has_device:
            TIME_SYNC_STATE["note"] = "设备未连接"
            logger.error("[timesync] 设备未连接，无法同步时间")
            return False
        # 1. adb root（已 root 会直接返回；生产版会提示 cannot run as root）
        out = subprocess.run(
            [_adb(), "root"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            creationflags=_win_flags(),
        )
        msg = (out.stdout or "").strip() or (out.stderr or "").strip()
        if (
            out.returncode != 0
            or "cannot run as root" in msg.lower()
            or "no devices" in msg.lower()
        ):
            TIME_SYNC_STATE["note"] = msg or "adb root 不可用"
            logger.warning(
                f"[timesync] adb root 不可用（{TIME_SYNC_STATE['note']}），跳过设备时间同步"
            )
            return False
        if "restarting" in msg.lower():
            # adb root 会重启 adbd，等设备重新上线
            subprocess.run(
                [_adb(), "wait-for-device"],
                capture_output=True,
                timeout=30,
                creationflags=_win_flags(),
            )
            time.sleep(1)
        # 2. 主格式: date -s 'yyyy-MM-dd HH:mm:ss'
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        out = subprocess.run(
            [_adb(), "shell", f"date -s '{now}'"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            creationflags=_win_flags(),
        )
        if out.returncode == 0:
            TIME_SYNC_STATE.update(
                ok=True, at=datetime.now().isoformat(timespec="seconds"), note="date -s"
            )
            logger.info(f"[timesync] 设备时间已同步为电脑时间: {now}")
            return True
        # 3. 备用格式: date MMddHHmmyyyy.ss（Android 原生）
        now2 = datetime.now().strftime("%m%d%H%M%Y.%S")
        out = subprocess.run(
            [_adb(), "shell", f"date {now2}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            creationflags=_win_flags(),
        )
        if out.returncode == 0:
            TIME_SYNC_STATE.update(
                ok=True,
                at=datetime.now().isoformat(timespec="seconds"),
                note="date MMddHHmmyyyy.ss",
            )
            logger.info(f"[timesync] 设备时间已同步（备用格式）: {now2}")
            return True
        TIME_SYNC_STATE["note"] = (out.stderr or "").strip() or "date 设置失败"
        logger.warning(
            f"[timesync] date 设置失败（{TIME_SYNC_STATE['note']}），证据将按设备时间偏移对齐"
        )
        return False
    except Exception as e:
        TIME_SYNC_STATE["note"] = str(e)
        logger.warning(f"[timesync] 时间同步异常，跳过: {e}")
        return False


# ============================================================================
# v2 新增：query 驱动的车机日志证据提取（case 后处理）
#   解析管线复用同目录的 parse_dm_queries.py：
#     query 边界 = onAsrResult 按 recordId 分组（组内最后一条 = ASR final）
#     每个 query 机械分类出: decision（意图解析/命令下发）/ operation（API 调用与回调，
#     含 CAR.HAL set/get）/ replies（tts+ui 文本，流式聚合）/ results（poi_list 等结构化
#     结果）/ ui_changes（页面切换+Activity 启动）/ state（HAL 属性后值快照）
#   产物: evidence.json（结构化，供裁判 AI）+ evidence.md（人类复核）
# ============================================================================

try:
    import parse_dm_queries as _pdq
except Exception as _pdq_err:  # pragma: no cover
    _pdq = None
    _PDQ_ERR = str(_pdq_err)


def _snip(line: str, max_len: int = 160) -> str:
    s = (line or "").strip()
    return s if len(s) <= max_len else s[:max_len] + "…"


def _extract_evidence(
    out_dir: Path,
    case_id: str,
    device_start: dict | None,
    device_stop: dict | None,
) -> None:
    """用 parse_dm_queries 管线解析 logcat.log，产出 evidence.json + evidence.md。"""
    log_file = out_dir / LOGCAT_FILENAME
    if not log_file.is_file():
        _write_evidence_files(
            out_dir,
            case_id,
            device_start,
            device_stop,
            None,
            error=f"缺少 {LOGCAT_FILENAME}，证据提取跳过",
        )
        return
    if _pdq is None:
        _write_evidence_files(
            out_dir,
            case_id,
            device_start,
            device_stop,
            None,
            error=f"parse_dm_queries 不可用: {_PDQ_ERR}",
        )
        return
    try:
        events = _pdq.parse_log([str(log_file)])
        finals = _pdq.find_asr_finals(events)
        vcs = _pdq.find_voicecase(events)
        sessions = _pdq.group_sessions(finals)
        session_of: dict[str, str] = {}
        for gi, fs in enumerate(sessions):
            for f in fs:
                session_of[f["rid"]] = f"sess_{gi:02d}"
        queries = _pdq.build_queries(events, finals)
        models = _pdq.to_models(queries, session_of, vcs)
        first_raw = events[0]["ts"] if events else ""
        last_raw = events[-1]["ts"] if events else ""
        with log_file.open("r", encoding="utf-8", errors="replace") as fh:
            total_lines = sum(1 for _ in fh)
        result = {
            "total_lines": total_lines,
            "first_raw_time": first_raw,
            "last_raw_time": last_raw,
            "log_size_bytes": log_file.stat().st_size,
            "queries": [m.model_dump() for m in models],
            "voicecases": vcs,
        }
    except Exception as exc:
        _write_evidence_files(
            out_dir,
            case_id,
            device_start,
            device_stop,
            None,
            error=f"证据解析失败: {exc}",
        )
        return
    _write_evidence_files(out_dir, case_id, device_start, device_stop, result, None)


def _write_evidence_files(
    out_dir: Path,
    case_id: str,
    device_start: dict | None,
    device_stop: dict | None,
    result: dict | None,
    error: str | None,
) -> None:
    """把解析结果写成 evidence.json（结构化，裁判 AI 用）+ evidence.md（人类复核用）。"""
    generated_at = datetime.now().isoformat(timespec="seconds")

    if result is None:
        payload = {
            "case_id": case_id,
            "generated_at": generated_at,
            "granularity": "query-evidence",
            "collection": {"format": LOGCAT_FORMAT, "buffers": LOGCAT_BUFFERS},
            "error": error or "未知错误",
        }
        (out_dir / EVIDENCE_JSON_FILENAME).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / EVIDENCE_MD_FILENAME).write_text(
            f"# 车机日志证据报告\n\n- case_id: {case_id}\n- 生成时间: {generated_at}\n\n"
            f"**提取失败**：{error or '未知错误'}\n",
            encoding="utf-8",
        )
        return

    queries: list[dict] = result["queries"]
    total = len(queries)
    sessions = len({q.get("session_id") for q in queries})
    with_decision = sum(1 for q in queries if q.get("decision"))
    with_operations = sum(1 for q in queries if q.get("operations"))
    with_replies = sum(1 for q in queries if q.get("replies"))
    with_ui = sum(1 for q in queries if q.get("ui_changes"))
    with_results = sum(1 for q in queries if q.get("results"))
    hal_props = Counter(
        prop for q in queries for prop in ((q.get("state") or {}).get("hal") or {})
    )

    def _enum_value(x):
        """pydantic model_dump 可能保留枚举对象，统一取 value。"""
        return x.value if hasattr(x, "value") else x

    op_kinds = Counter(
        _enum_value(o.get("kind")) for q in queries for o in (q.get("operations") or [])
    )
    vc_names = [v.get("name") for v in result["voicecases"]]

    payload = {
        "case_id": case_id,
        "generated_at": generated_at,
        "granularity": "query-evidence",
        "collection": {"format": LOGCAT_FORMAT, "buffers": LOGCAT_BUFFERS},
        "time_sync": dict(TIME_SYNC_STATE),
        "device_time": {"start": device_start, "stop": device_stop},
        "logcat": {
            "file": LOGCAT_FILENAME,
            "size_bytes": result["log_size_bytes"],
            "lines": result["total_lines"],
            "time_range": {
                "first": result["first_raw_time"],
                "last": result["last_raw_time"],
            },
        },
        "voicecases": vc_names,
        # pydantic QueryEvidence 的 JSON Schema（供裁判模型理解证据结构，与数据同源生成）
        "query_schema": _pdq.QueryEvidence.model_json_schema(),
        "summary": {
            "queries": total,
            "sessions": sessions,
            "with_decision": with_decision,
            "with_operations": with_operations,
            "with_replies": with_replies,
            "with_ui_changes": with_ui,
            "with_results": with_results,
            "hal_properties": dict(hal_props.most_common()),
            "operation_kinds": dict(op_kinds.most_common()),
        },
        "queries": queries,
    }
    (out_dir / EVIDENCE_JSON_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---- evidence.md ----
    lines_md: list[str] = []
    lines_md.append("# 车机日志证据报告（query 驱动）\n")
    lines_md.append(f"- case_id: {case_id}")
    lines_md.append(f"- 目录: `{out_dir.name}`")
    lines_md.append(f"- 生成时间: {generated_at}")
    lines_md.append(f"- 采集: `adb logcat -v {LOGCAT_FORMAT} -b {LOGCAT_BUFFERS}`")
    lines_md.append(
        f"- logcat: `{LOGCAT_FILENAME}`（{result['log_size_bytes'] / 1024 / 1024:.1f} MB，"
        f"{result['total_lines']} 行，{result['first_raw_time']} ~ {result['last_raw_time']}）"
    )
    if device_start and device_stop:
        lines_md.append(
            f"- 设备时间: start {device_start.get('text')} / stop {device_stop.get('text')}"
        )
    if TIME_SYNC_STATE.get("ok"):
        lines_md.append(f"- 设备时间同步: 已同步（{TIME_SYNC_STATE.get('at', '')}）")
    elif TIME_SYNC_STATE.get("attempted"):
        lines_md.append(
            "- 设备时间同步: 失败/未开启（时间对齐以 device_time 偏移为准）"
        )
    if error:
        lines_md.append(f"\n> 提取异常：{error}")

    lines_md.append("\n## 汇总\n")
    lines_md.append("| 指标 | 值 |")
    lines_md.append("|---|---|")
    lines_md.append(f"| query 数（ASR final 去重） | {total} |")
    lines_md.append(f"| 会话数（60s 间隔切分） | {sessions} |")
    lines_md.append(f"| 有决策事件 | {with_decision} |")
    lines_md.append(f"| 有操作事件（API/HAL） | {with_operations} |")
    lines_md.append(f"| 有回复文本（tts/ui） | {with_replies} |")
    lines_md.append(f"| 有 UI 变化（页面/Activity） | {with_ui} |")
    lines_md.append(f"| 有结构化结果（poi_list 等） | {with_results} |")
    if hal_props:
        parts = [f"{k}×{n}" for k, n in hal_props.most_common()]
        lines_md.append(f"| HAL 属性写入 | {'、'.join(parts)} |")
    if op_kinds:
        parts = [f"{k}×{n}" for k, n in op_kinds.most_common()]
        lines_md.append(f"| 操作类型 | {'、'.join(parts)} |")

    lines_md.append("\n## Query 明细\n")
    for q in queries:
        qid = q.get("query_id", "")
        lines_md.append(
            f"### #{q.get('turn_index', 0):02d} [{q.get('session_id', '')}] "
            f"{q.get('ts_asr_final', '')}「{q.get('text', '')}」"
        )
        if qid:
            lines_md.append(f"- recordId: `{qid}`")
        vc = q.get("voicecase")
        if vc:
            lines_md.append(f"- 用例: {vc}")
        for d in (q.get("decision") or [])[:6]:
            lines_md.append(
                f"- 决策 `{d.get('ts', '')}` [{','.join(d.get('tags', []))}] {_snip(d.get('payload', ''))}"
            )
        for o in (q.get("operations") or [])[:10]:
            lines_md.append(
                f"- 操作 `{o.get('ts', '')}` [{_enum_value(o.get('kind', ''))}] {o.get('api', '')} "
                f"{_snip(o.get('params', ''))}"
            )
        for r in (q.get("replies") or [])[:8]:
            lines_md.append(
                f"- 回复 [{_enum_value(r.get('source', ''))}] `{r.get('ts', '')}` {_snip(r.get('payload', ''))}"
            )
        for u in (q.get("ui_changes") or [])[:6]:
            if u.get("kind") == "page_change":
                lines_md.append(
                    f"- UI 切换 `{u.get('ts', '')}` {u.get('from_path', '')} -> {u.get('to_path', '')}"
                )
            else:
                lines_md.append(
                    f"- UI 启动 `{u.get('ts', '')}` {u.get('component', '')}"
                )
        for r in (q.get("results") or [])[:3]:
            lines_md.append(
                f"- 结果 [{r.get('type', '')}] `{r.get('ts', '')}` count={r.get('count')} "
                f"items={len(r.get('items', []))}"
            )
        hal = (q.get("state") or {}).get("hal") or {}
        for prop, st in hal.items():
            lines_md.append(
                f"- HAL 后值 {prop}={st.get('value', '')} area={st.get('area_id', '')} "
                f"`{st.get('ts', '')}`"
            )
        media = (q.get("state") or {}).get("media")
        if media:
            prog = media.get("progress")
            prog_txt = (
                f"进度 {prog.get('first_ms')}~{prog.get('last_ms')}ms×{prog.get('updates')}"
                if prog
                else ""
            )
            lines_md.append(
                f"- 媒体: {'播放中' if media.get('playing') else '未播放'}（{media.get('play_state') or '-'}）"
                f"「{media.get('track') or '-'} - {media.get('artist') or '-'}」"
                f"{(' ' + prog_txt) if prog_txt else ''}"
                f"{(' playlist=' + str(media.get('playlist_size'))) if media.get('playlist_size') is not None else ''}"
            )
        lines_md.append("")

    lines_md.append("## 说明\n")
    lines_md.append(
        "- query 边界 = onAsrResult 按 recordId 分组（组内最后一条 = ASR final）；"
        "replies 已做流式聚合；operation 的 result 回调（onSuccess 等）以 kind=result 保留。"
    )
    lines_md.append(
        "- 全量日志保留在 `logcat.log`，本报告仅提取证据，供裁判 AI / 人工复核快速定位。"
    )
    (out_dir / EVIDENCE_MD_FILENAME).write_text(
        "\n".join(lines_md) + "\n", encoding="utf-8"
    )


# ============================================================================
# Recorder：接口与 v1 一致（/health /start /stop /case_result）
# ============================================================================


class Recorder:
    def __init__(self, mic_device=None, spk_device=None) -> None:
        self.proc: subprocess.Popen[bytes] | None = None
        self.log_proc: subprocess.Popen[bytes] | None = None
        self.log_file_fh: TextIO | None = None
        self.case_id = ""
        self.dir: Path | None = None
        self.device_start: dict | None = None
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
            [_adb(), "logcat", "-v", LOGCAT_FORMAT, "-b", LOGCAT_BUFFERS],
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
        # v2：记录设备时间 + 打 VoiceCase 开始标记（尽力而为）
        self.device_start = _device_date()
        _mark_voice_case("start", case_id)
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

    def _run_stop_postprocess(
        self,
        out_dir: Path | None,
        case_id: str,
        device_start: dict | None,
        device_stop: dict | None,
    ) -> None:
        if not out_dir:
            return
        # 注册合成完成事件：ffmpeg 退出（进程结束）才 set，保证文件已写完整
        key = str(out_dir.resolve())
        done_evt = threading.Event()
        with self._upload_lock:
            self._merge_done[key] = done_evt

        # 目录不再改名，后处理线程直接用 out_dir 做合成
        def _run() -> None:
            try:
                logger.info(f"[postprocess] 后处理线程启动: dir={out_dir}")
                # v2：先提取四层证据（只依赖 logcat.log），再合成音视频
                _extract_evidence(out_dir, case_id, device_start, device_stop)
                _merge_av(out_dir)
            finally:
                done_evt.set()
                logger.info(f"[postprocess] 合成线程结束: dir={out_dir}")

        threading.Thread(target=_run, daemon=True).start()

    def stop(self) -> StopItemResponse | None:
        if not self.case_id and not self.dir:
            return None
        logger.info(f"[stop] 停止录制: case_id={self.case_id} dir={self.dir}")
        # v2：先记录设备时间 + 打 VoiceCase 结束标记（要赶在 logcat 停止前）
        device_stop = _device_date()
        _mark_voice_case("end", self.case_id)
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
        self._run_stop_postprocess(out_dir, case_id, self.device_start, device_stop)
        self.device_start = None
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
        """等待后处理完成（证据提取+合成）后上传 TOS 并回调后端更新 metadata。"""
        try:
            self._upload_and_callback_inner(out_dir)
        except Exception as e:
            import traceback

            logger.error(f"[tos] 上传线程异常退出: {e}\n{traceback.format_exc()}")

    def _upload_and_callback_inner(self, out_dir: Path) -> None:
        logger.info(f"[tos] 上传线程启动，等待后处理完成: dir={out_dir}")
        merged = out_dir / MERGED_VIDEO_FILENAME
        log_file = out_dir / LOGCAT_FILENAME
        evidence_json = out_dir / EVIDENCE_JSON_FILENAME
        evidence_md = out_dir / EVIDENCE_MD_FILENAME
        # 取该目录的合成完成事件；拿不到则退化为仅按视频文件大小判断（兼容未走 stop 的异常路径）
        key = str(out_dir.resolve())
        with self._upload_lock:
            done_evt = self._merge_done.get(key)
        if done_evt is None:
            logger.warning(f"[tos] 未找到合成完成事件，退化为按文件大小等待: {out_dir}")
        # 最多等 10 分钟，每 2 秒检查一次；后处理线程（证据提取+ffmpeg 合成）结束即视为完成
        max_wait = 600
        interval = 2
        waited = 0
        while waited < max_wait:
            size_ok = merged.is_file() and merged.stat().st_size > 0
            merge_ok = done_evt is None or done_evt.is_set()
            if merge_ok or (done_evt is None and size_ok):
                logger.info(
                    f"[tos] 后处理完成: merge_done={merge_ok} merged_size={merged.stat().st_size if merged.is_file() else 0}B，等待 {waited}s"
                )
                break
            time.sleep(interval)
            waited += interval
            if waited % 30 == 0:
                logger.info(f"[tos] 等待后处理完成中... 已等 {waited}s")

        with self._upload_lock:
            info = self._upload_info.get(str(out_dir.resolve()))
        if not info:
            logger.error(f"[tos] 未找到上传信息，跳过: {out_dir}")
            return
        task_run_item_id, callback_url = info
        logger.info(f"[tos] 准备上传: task_run_item_id={task_run_item_id}")

        # 视频 / 日志 / 证据 json / 证据 md 分别上传（互不依赖），都完成后一次性回调
        def _upload_if_exists(path: Path, kind: str, content_type: str) -> str | None:
            if path.is_file() and path.stat().st_size > 0:
                return _upload_file_to_tos(path, task_run_item_id, kind, content_type)
            logger.warning(f"[tos] {path.name} 不存在或为空，跳过上传: {path}")
            return None

        video_key = _upload_if_exists(merged, "merged", "video/mp4")
        log_key = _upload_if_exists(log_file, "logcat", "text/plain")
        evidence_key = _upload_if_exists(evidence_json, "evidence", "application/json")
        evidence_md_key = _upload_if_exists(evidence_md, "evidence_md", "text/markdown")

        object_keys = {
            "video_object_key": video_key or "",
            "log_object_key": log_key or "",
            "evidence_object_key": evidence_key or "",
            "evidence_md_object_key": evidence_md_key or "",
        }
        if not any(object_keys.values()):
            logger.error("[tos] 视频+日志+证据全部上传失败，跳过回调")
            return
        if not video_key:
            logger.warning("[tos] 视频上传失败，仅回调日志/证据")
        if callback_url:
            _callback_update_metadata(callback_url, object_keys)
        else:
            logger.warning("[tos] 无 callback_url，跳过回调")


rec = Recorder()
app = FastAPI(title="Voice Test Local Recorder v2")
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
            logger.error("[local_recorder_v2] 未选择音频设备，退出。请重新启动并选择。")
            sys.exit(1)
        mic_dev, spk_dev = picked
        try:
            rec.audio = AudioRecorder(mic_device=mic_dev, spk_device=spk_dev)
            logger.info(
                f"[local_recorder_v2] 已锁定音频设备: mic={mic_dev.name!r} spk_loopback={spk_dev.name!r}"
            )
        except Exception as e:
            logger.error(f"[local_recorder_v2] AudioRecorder 初始化失败：{e}")
            sys.exit(1)
    else:
        logger.warning(f"[local_recorder_v2] 音频录制不可用，跳过设备选择：{_AUDIO_ERR}")

    logger.info(f"[local_recorder_v2] 服务启动于 http://127.0.0.1:{PORT}")
    logger.info(f"[local_recorder_v2] 录制根目录: {OUTPUT_DIR.resolve()}")
    logger.info(
        f"[local_recorder_v2] TOS 上传: {'已启用 (bucket=' + TOS_BUCKET_NAME + ', region=' + TOS_REGION + ')' if _tos_available() else '未启用'}"
    )
    logger.info(
        f"[local_recorder_v2] 音频录制: {'可用' if _AUDIO_OK else '不可用: ' + _AUDIO_ERR}"
    )
    # 初始化：启动前必须完成设备时间同步，失败则终止启动（可用 SYNC_DEVICE_TIME=0 跳过）
    if SYNC_DEVICE_TIME and not _sync_device_time():
        logger.error(
            "[timesync] 设备时间同步失败，终止启动；如确认不需要同步请设 SYNC_DEVICE_TIME=0 后重启"
        )
        sys.exit(1)
    uvicorn.run(app, host="127.0.0.1", port=PORT)
