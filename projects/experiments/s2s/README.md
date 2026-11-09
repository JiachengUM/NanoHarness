# S2S 实时对话实验

基于火山/字节实时对话 WebSocket 的语音对话（Speech-to-Speech）小实验：麦克风采集、上行音频、下行 TTS 播放，并解析服务端事件。

## 模块说明


| 文件                            | 作用                                                                                                             |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **main.py**                   | 程序入口：解析命令行参数（如是否用规整事件打印、是否仅用自定义文本走 TTS），创建 `DialogSession` 并启动。                                                |
| **config.py**                 | 连接与会话配置：WebSocket 地址与鉴权头、`StartSession` 相关模型（ASR/TTS/对话人设等）、输入/输出音频参数（采样率、chunk 等）。**密钥与 App 信息请在本机修改，勿提交仓库。** |
| **protocol.py**               | S2S 二进制协议：消息类型常量、请求头生成、`parse_response` 解析服务端帧（与官方协议示例一致）。                                                     |
| **realtime_dialog_client.py** | WebSocket 客户端：建连、`StartConnection` / `StartSession`、以及 `SayHello`、文本查询、TTS 文本、RAG 等请求的发送与响应读取。                 |
| **event.py**                  | 服务端事件：事件码与名称映射、各类 JSON 载荷的 Pydantic 模型、可选的 `ServerEventPrinter` 用于终端里规整打印。                                     |
| **audio_manager.py**          | 会话与音频：`AudioDeviceManager` 管理 PyAudio 输入/输出流；`DialogSession` 串联采集、发送、收包、状态切换与播放队列。                             |
| **init.py**                   | 包标识，无业务逻辑。                                                                                                     |


## 依赖

- **pyaudio**：麦克风与扬声器。
- **websockets**：与服务端长连接。

## 运行

1. 安装依赖：`pip install -r requirements.txt`
2. 在 `config.py` 中填好你自己的连接参数与业务配置。
3. 在项目根目录下执行（与现有 `import` 路径一致）：

```bash
cd projects/experiments/s2s
python main.py
```

可选参数见 `main.py` 内 `argparse` 说明（如 `--use_event_printer`、`--use_custom_text_tts_only`）。



