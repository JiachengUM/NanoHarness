"""打包本地记录工具，供平台 /voice_test/local_recorder/download 下载。"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
TESTS_SCRIPTS_DIR = SCRIPTS_DIR.parent / "tests" / "scripts"
ZIP_ROOT = "voice_local_recorder"

README = """本地记录工具（windows 版）
==============================

一、下载并解压（按下面这两个包）,可以问AI如何配置。
--------------------------------
1) ffmpeg（做音视频合成用）
   下载：https://www.gyan.dev/ffmpeg/builds/
   版本：ffmpeg-8.0.1-essentials_build.7z

2) scrcpy（手机投屏，包里通常含 adb；本地记录依赖它抓设备画面）
   下载：https://github.com/Genymobile/scrcpy/releases
   版本：scrcpy-win64-v4.0.zip

二、配置「系统」环境变量 Path（推荐，一劳永逸）
----------------------------------------------
目标：让任意新开的终端都能直接敲 ffmpeg / scrcpy。

1. 按 Win 键，搜索「环境变量」，打开「编辑系统环境变量」
2. 点「环境变量…」
3. 在下方「系统变量」里，选中 Path →「编辑」
4. 「新建」，分别加上你的目录（示例，改成你自己的）：
     D:\\software\\ffmpeg\\bin
     D:\\software\\scrcpy
5. 一路「确定」保存

注意：改完 Path 后，必须关掉旧的 CMD/PowerShell，再重新打开一个新窗口，才会生效。

三、校验是否装好（必做）
------------------------
在「新开」的 CMD 或 PowerShell 里依次执行：

  where ffmpeg
  ffmpeg -version

  where scrcpy
  scrcpy --version

通过标准：
  - where 能打出刚才加进 Path 的路径
  - -version / --version 能打印出版本信息、不报「不是内部或外部命令」

任一失败 → 检查：解压路径对不对、Path 里有没有写错、是否用了新终端。

（手机 USB 调试怎么开：自行搜索或问豆包，本说明不写。）

四、安装 Python 依赖
--------------------
  pip install fastapi uvicorn pydantic soundcard numpy tos

说明：
  fastapi/uvicorn/pydantic —— 本地记录服务
  soundcard/numpy          —— 本地音频录制（录 mic + 扬声器播放音，混音后替代后端 audio_url 下载）
  tos                      —— 上传 merged.mp4 + logcat.log 到 TOS（可选）

tos 是可选依赖（代码里延迟导入，没装也能跑）：
  - 装了 tos：merged.mp4 和 logcat.log 会自动上传到 TOS，并回调后端写入 video_object_key / log_object_key，前端详情页可直接播放视频、下载日志
  - 没装 tos：本地录制、合成、写 case_result.json 照常工作，只是跳过上传，前端详情页不会出现视频/日志区块
  - 临时禁用上传：编辑 local_recorder.py 把 ENABLE_TOS_UPLOAD 改成 False

五、启动本地记录服务
--------------------------------
  python local_recorder.py
  默认地址：http://127.0.0.1:8765

启动后自动用系统默认 mic / 扬声器 loopback 录音：
  - mic 收外部声音/被测设备声音
  - 扬声器 loopback 录电脑播放出去的 TTS
  两路会混音成单声道 case_audio.wav，与 screen.mkv 合并成 merged.mp4。
  想换设备：在 Windows「声音设置」里改默认设备；或在启动前 set AUDIO_MIC_NAME / AUDIO_SPK_NAME 模糊匹配指定。

可选项：新建终端手动自测（服务已启动时）：
  python test_local_recorder.py

六、接到 voice-test 页面
------------------------
  「配置 → 本地记录」
  打开开关，服务地址填 http://127.0.0.1:8765，点「检查」。
  显示设备已连接即可开始测试

每个 case 目录产出：
  screen.mkv / case_audio.wav / merged.mp4 / case_meta.json / logcat.log
  case_result.json（评测结果，含 is_passed/judge_status/reason 等）
  RESULT_PASS / RESULT_FAIL / RESULT_SKIP / RESULT_ERROR（空文件 marker，一眼看结果）


平台：Windows 已验证；macOS 待测试。
"""


def build_local_recorder_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(SCRIPTS_DIR / "local_recorder.py", arcname=f"{ZIP_ROOT}/local_recorder.py")
        zf.write(SCRIPTS_DIR / "audio_recorder.py", arcname=f"{ZIP_ROOT}/audio_recorder.py")
        zf.write(
            TESTS_SCRIPTS_DIR / "test_local_recorder.py",
            arcname=f"{ZIP_ROOT}/test_local_recorder.py",
        )
        zf.writestr(f"{ZIP_ROOT}/README.txt", README.strip() + "\n")
    return buf.getvalue()
