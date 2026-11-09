# Duplex 实时对话

全双工实时语音对话接口，使用 JSON WebSocket 协议，Python 3.13 基线。

## 结构

- `duplex_events.py`：Duplex 原生事件常量、codec 和请求 builder。
- `websocket_transport.py`：鉴权、WebSocket 连接与串行帧收发。
- `duplex_client.py`：provider command、event id 和 session handshake。
- `duplex_stream_model_api.py`：`DuplexStreamModelAPI`——provider session、
  `submit()` 上行映射和 `events()` 下行统一事件映射。
- `duplex_agent_session.py`：`DuplexAgentSession`——`events()` 的唯一消费者，负责
  音频输入输出、FC 分组、TaskManager 事件路由，以及 sync/async 两种结果续推策略。
- `local_audio.py`：本地 PyAudio 麦克风采集与播放（惰性依赖）。
- `config.py`：统一定义 session profile；VAD、审核文案等产品策略在这里配置，
  不进入低层 client；API key 也直接维护在该配置类中。
- `async_backfill.py`：DynamicTask 的 Context 回灌与 PCM 激活调度。
- `async_agent_prompt.py`：async continuation 专用提示词，约束模型只消费已写入
  原问题结果区块的真实异步结果，不推测仍在执行的并发任务。
- `sync_agent_prompt.py`：sync continuation 专用提示词，约束模型基于本轮真实工具结果
  自然续答。
- `duplex_agent_app.py`：统一应用入口和组合根，负责选择 prompt 与
  `tool_call_mode`，并组装配置、transport、client、model API、AgentSession、raw
  tools 和 session 级 TaskManager。
- `cli.py`：参数解析、终端信号和键盘麦克风控制。
- `diagnostics.py`：transport observer、Task 与 Runtime 实验日志。
- `experiment/`：手工协议与语音实验；`canary_experiment.py` 是独立的 create/update
  上下文可见性诊断，`docs/` 保存测评文档，`test_log/` 保存原始日志。整体 Demo 产品判断见
  [`experiment/docs/DUPLEX_DYNAMIC_DEMO_PRODUCT_EVALUATION.md`](experiment/docs/DUPLEX_DYNAMIC_DEMO_PRODUCT_EVALUATION.md)。
- `aicore.v2.experiments.duplex_speech_shell`：外部 v2 Agent 的浏览器与本地 ASR/TTS
  壳层；直接复用 raw `DuplexClient`，不经过 StreamModelAPI。
- `assets/*_ready.pcm`：按工具区分的异步结果激活语音；多个或未知工具使用
  `async_results_ready.pcm` 通用提示。

## 依赖方向

```text
aicore.models.stream_model_api.duplex
  → Duplex WebSocket 服务
```

`DuplexStreamModelAPI` 和 `DuplexAgentSession` 不依赖 `projects`。唯一例外是
`duplex_agent_app.py` 组合根：实验工具
实现暂时位于 `projects.mind.toolset`（通过 `get_task_tools` 引入），属于
临时的 aicore → projects 反向依赖，工具栈迁入 aicore 后消除。

## 工具执行与续推

统一入口的两种模式共用一个 session 级
`TaskManager(max_concurrency=10)` 和同一套 raw
`TaskTool`。Session 是 `TaskManager.astream()` 的唯一消费者，按独立 `task_id`
路由任务生命周期；Duplex 的 `call_id` 只用于关闭原始 function call。

- `--tool-call-mode sync`：同组工具并发执行，等全部
  success/failure/cancelled 后按原 FC 顺序一次批量上行真实结果。
- `--tool-call-mode async`（默认）：整组先批量上行占位回执，
  每个成功结果在本组回执被接受后进入串行 Context update + PCM 激活队列；失败和
  取消只保留在 TaskManager 投影与诊断日志中。
- `cancel_task` 是短期的控制工具例外：直接执行、不进入业务并发队列，因此即使 10 个
  执行槽都被占满仍可取消 pending/running 任务。

```bash
# 默认 async
uv run python -m aicore.models.stream_model_api.duplex

# 显式 sync
uv run python -m aicore.models.stream_model_api.duplex --tool-call-mode sync

# 本地音频只支持 sync
uv run python -m aicore.models.stream_model_api.duplex \
  --tool-call-mode sync \
  --audio /path/to/input.pcm \
  --output-audio output.pcm
```

## 输入边界

- 普通 Duplex query 只接受音频，通过 `AudioChunkInput` 提交数据并用
  `AudioCommitInput` 提交当前音频缓冲区。
- `conversation.item.create(role=user, input_text)` 仅由 Canary 直接调用 provider 做
  create/update 对照，不属于公共 `StreamModelInput`。Canary 已确认当前 Duplex 后续
  音频推理看不到这种 create 文本。
- `ContextItemRetrieveInput` 的下行结果是 `StreamContextRetrievedEvent`，由
  `DuplexAgentSession` 所消费的同一条 `events()` 事件流返回。
- `ContextItemUpdateInput` 原位替换指定 `item_id` 的文本；它不会追加新 observation。
  async 兼容层按原始 `question_id` 维护“原转写 + 已完成结果”的最小本地投影，
  每次任务完成后用完整投影更新该 question，再上传本地 PCM 激活下一轮推理。
- async 仅支持实时 session；`--audio` 模式在首个占位回复后没有可靠的
  session 终态，因此入口会明确拒绝。sync 仍支持单轮本地音频。

## 手工语音日志

麦克风模式启动时会询问一个新的 `.log` 文件名；每次运行对应一个独立 case，旧文件
不会被覆盖。也可以通过 `--case-log case01.log` 显式指定。日志保留毫秒时间戳、相对
耗时、上行/下行 Duplex 事件、Context 和本地任务事件，同时过滤连续音频帧和无语义的
音频/文本 delta。测试步骤见 `experiment/docs/VOICE_TEST_CASES.md`。

## 依赖

服务端和无声卡调用只需要项目基础依赖，其中 `websockets>=15,<16` 是 Duplex 的
直接依赖。麦克风与扬声器支持属于开发依赖（PyAudio 惰性导入）。
