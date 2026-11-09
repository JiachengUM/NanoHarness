"""交互式测试 audio_recorder：启动后手动选择 mic/spk 设备，回车控制 start/stop。"""
import sys
import io
import time
import wave
from pathlib import Path

# Windows 默认 GBK，强制 stdout 用 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from audio_recorder import AudioRecorder, OUTPUT_DIR  # noqa: E402


def main() -> None:
    if not AudioRecorder().is_available():
        print("FAIL: 缺依赖，先 pip install soundcard numpy")
        return

    # 1. 交互式选设备（复用 AudioRecorder 的能力）
    picked = AudioRecorder.pick_devices_interactive()
    if picked is None:
        return
    mic_dev, spk_dev = picked

    # 2. 用选中的设备构造 recorder
    rec = AudioRecorder(mic_device=mic_dev, spk_device=spk_dev)
    print("\n=== 已选设备 ===")
    print(f"mic:         {mic_dev.name!r}")
    print(f"spk_loopback:{spk_dev.name!r}")
    print(f"output_dir:  {OUTPUT_DIR.resolve()}")

    issues = rec.health_issues()
    if issues:
        print(f"WARN: {'、'.join(issues)}")

    # 3. 录音循环
    out_dir = OUTPUT_DIR / "test"
    case_idx = 0
    while True:
        case_idx += 1
        case_id = f"interactive_{case_idx:03d}"
        ts = time.strftime("%Y%m%d_%H%M%S")
        case_dir = out_dir / case_id / ts
        case_dir.mkdir(parents=True, exist_ok=True)

        input(f"\n按回车开始录音 [case_id={case_id}]... (Ctrl+C 退出)")
        t1 = time.perf_counter()
        rec.start(case_dir)
        print(f"start 耗时: {(time.perf_counter()-t1)*1000:.1f}ms")
        print("录音中... 请说话 + 播放音乐")

        input("按回车停止录音...")
        t2 = time.perf_counter()
        wav = rec.stop()
        print(f"stop 耗时: {(time.perf_counter()-t2)*1000:.1f}ms")

        if wav is None:
            print("FAIL: 未生成 wav")
            continue

        with wave.open(str(wav), "rb") as w:
            dur = w.getnframes() / w.getframerate()
            print(f"文件: {wav}")
            print(f"时长: {dur:.3f}s")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n退出")
