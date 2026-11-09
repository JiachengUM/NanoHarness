# Duplex Speech Shell

这个包是 v2 浏览器和本地设备共用的 **ASR/TTS 壳层**。文本理解、工具选择和回答生成
始终由外部 v2 Agent 负责；Duplex provider 不拥有业务推理，也不注册服务端 tools。

## 边界与数据流

两条方向相反的数据流在这里汇合：

```text
Browser / local PCM16 (16 kHz)
  -> raw DuplexClient.input_audio_append
  -> Duplex ASR final
  -> external v2 Agent text input

external v2 Agent text deltas
  -> raw DuplexClient.speech_text_append / speech_text_commit
  -> Duplex TTS PCM16 (24 kHz)
  -> Browser Float32 audio / local PCM16 playback
```

外部 Agent 的已有文本入口不经过 Duplex。Duplex 产生的 native answer、function call
或其他 provider 业务事件也不得进入外部 Agent；session profile 通过 transport-only
instructions 和 `tools=[]` 固定这一点。

## 代码职责

- `profile.py` 维护 transport prompt 和 `tools=[]`。通用 builder 保留调用方音频格式；
  浏览器 builder 另行固定 16 kHz PCM16 输入 / 24 kHz PCM16 输出，并且都不修改
  调用方持有的 `DuplexConfig`。
- `backend.py` 是唯一允许接触 raw provider dict 和 raw `DuplexClient` 的位置；它固定
  `connect -> session.create -> 单 receive loop -> close`，并输出 `events.py` 的窄事件。
- `agent_tts.py` 独占 Agent `message_id`、generation 和文本队列。同一语音轮对前
  N-1 段执行 append，最后一段必须 commit；被打断的 generation 不得复活。
- `turn_state.py` 用无 I/O 的显式转移维护 ASR、barge-in、accepted response 和客户端
  playback 状态。
- `frontend_bridge.py` 只负责编排：把 ASR final 提交给外部 Agent，把 Agent 文本交给
  TTS pump，再转发浏览器 `voice.*` 与 Float32 音频。
- `local_audio.py` 将 speech backend 适配给现有 `DuplexLocalAudio`，并读取/发送有限
  PCM/WAV 文件；文件 EOF 只执行一次 audio commit。
- `local_frontend.py` 组合 backend、pump、state 与本地声卡，不读取 provider dict；
  `local_runtime.py` 只管理外部 Agent 与 TTS generation。
- `cli.py` 是本地组合根，负责旧 v2 Agent profile、终端空格门控和进程信号。
- `v2_frontend_duplex_voice.py` 只保留原类名、默认 client builder 和 PCM 转换函数的
  浏览器注入兼容导出。

语音回复以 `response.output_audio.done` 为唯一 provider 终态；`response.done` 只是
provider summary，不能释放 TTS 调度状态。打断是 client-only：停止接受旧 response、
清空本地播放状态并通知浏览器，不向 Duplex 发送 cancel，也不取消外部 Agent turn。

## 本地入口

```bash
# 空格打开一轮麦克风
python -m aicore.v2.experiments.duplex_speech_shell.cli

# 连续麦克风
python -m aicore.v2.experiments.duplex_speech_shell.cli --mic-mode continuous

# 16 kHz mono PCM16 raw 或 WAV；完成后将 TTS 写入 output.pcm
python -m aicore.v2.experiments.duplex_speech_shell.cli --audio input.pcm
```

文件输入按 640 bytes / 20 ms 发送，EOF 显式 commit。实时麦克风只播放、不累计整场
音频；只有文件模式保存输出。启动时不自动发送问候。

## 依赖边界

底层直接复用 raw `DuplexClient`、transport、config 和惰性加载的本地音频实现。这里
不使用 `DuplexStreamModelAPI`、`DuplexAgentSession` 或 StreamModelAPI input/event。
替换 provider 时只替换 backend adapter，不改变外部 Agent、浏览器协议或两条数据流。
