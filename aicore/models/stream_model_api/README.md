# Stream Model API

`stream_model_api` 是 session-scoped、事件驱动的流式模型边界。业务通过
`submit()` 提交模型输入；音频 chunk、音频 commit、外部文本 observation 和工具结果
都属于输入，文本、转写、音频、Function Call 和上下文查询结果都属于输出事件。

当前包含两个 backend：

- `ResponsesStreamModelAPI`：复用已有 `ResponsesModelAPI` 的文本 POC。通过
  `events()` 对外暴露模型事件流。
- `DuplexStreamModelAPI`：Duplex provider adapter，通过 `submit()` 接收音频和工具
  结果，通过 `events()` 暴露统一事件流。
- `DuplexAgentSession`：外部单消费者，负责音频 I/O、FC 执行、TaskManager 和回灌。

`DuplexStreamModelAPI` 链路不会调用 Responses 模型，也不会通过
`speech_text_buffer` 把另一个模型的文本送回 Duplex TTS。外部 v2 Agent 的独立
speech-shell 不属于这条模型链路。

## Duplex backend

Duplex 完整实现维护在 `aicore.models.stream_model_api.duplex`：

- `duplex_events.py`：Duplex 原生事件名、codec 和请求 builder。
- `websocket_transport.py`：WebSocket、鉴权和串行写入；诊断通过 observer 注入。
- `duplex_client.py`：provider command、event id 和 session handshake。
- `duplex_stream_model_api.py`：`DuplexStreamModelAPI`——provider session、上行
  `submit()` 与下行统一事件映射。
- `duplex_agent_session.py`：`DuplexAgentSession`——`events()` 的唯一消费者，负责
  会话循环、音频 I/O、FC 分组/执行、TaskManager 和异步回灌。
- `local_audio.py`：PyAudio 麦克风采集与播放（惰性依赖）。
- `config.py`：统一定义 API key、session profile、VAD 和审核文案等配置。
- `async_backfill.py`：DynamicTask 的 Context 回灌与 PCM 激活调度。
- `duplex_agent_app.py`：统一应用入口和组合根，负责选择 prompt 与
  `tool_call_mode`，并组装 transport、client、model API、AgentSession、raw tools
  和 session 级 TaskManager。
- `cli.py`：参数解析、终端信号和键盘麦克风控制。

外部 v2 Agent 使用的 ASR/TTS 壳层位于
`aicore.v2.experiments.duplex_speech_shell`。它直接组合 raw `DuplexClient`，不经过
`DuplexStreamModelAPI` 或 `DuplexAgentSession`。

依赖方向固定为 `aicore.models.stream_model_api.duplex → Duplex WebSocket 服务`。
唯一例外是 `duplex_agent_app.py` 组合根：实验工具实现暂时位于
`projects.mind.toolset`
（`get_task_tools`），属于临时的 aicore → projects 反向依赖，工具栈迁入
aicore 后消除；`DuplexStreamModelAPI` 和 `DuplexAgentSession` 本身都不依赖 projects。

Duplex 会话创建时直接携带 AICore 本地工具 schema：

```text
AudioChunkInput
  → Duplex input_audio_buffer.append
  → Duplex 原生模型
  → response.function_call_arguments.done
  → DuplexStreamModelAPI.events()
  → DuplexAgentSession 收齐同组 StreamToolCallEvent
  → session 级 TaskManager 执行 raw TaskTool
  → sync / async continuation policy
  → ToolResultBatchInput / Context update + PCM
  → Duplex conversation.item.create
  → StreamAudioDeltaEvent
```

统一入口通过 `--tool-call-mode` 选择互斥的续推策略；同一个
session 生命周期内不会切换。默认使用 async：

```bash
# 默认 async：先返回占位回执，任务完成后 Context update + PCM 续推
uv run python -m aicore.models.stream_model_api.duplex

# sync：等同组工具全部终态后，一次批量回传真实结果
uv run python -m aicore.models.stream_model_api.duplex --tool-call-mode sync

# 本地音频只支持 sync；async 需要完整的实时 session
uv run python -m aicore.models.stream_model_api.duplex \
  --tool-call-mode sync \
  --audio /path/to/input.pcm \
  --output-audio output.pcm
```

组合根按模式选择 system prompt，并在创建 Duplex session 时覆盖
`DuplexConfig.instructions`：async 使用 `async_agent_prompt.py` 的
`ASYNC_AGENT_SYSTEM_PROMPT`，sync 使用 `sync_agent_prompt.py` 的
`SYNC_AGENT_SYSTEM_PROMPT`。AgentSession 不解析 CLI，也不选择 prompt。

两种模式都把 raw `TaskTool` 提交到同一个 session 级 `TaskManager`，只有
continuation policy 不同：sync 等本组全部终态后按原 FC 顺序批量回传；
async 先上行本组占位回执，任务成功后由兼容层（`async_backfill.py`）把结果
投影到原始 question：

```text
TaskSuccessEvent(result)
  → 按 question_id 累积“原转写 + 该问题全部已完成结果”
  → conversation.item.update 整段更新原始 question
  → 等待当前 Duplex 回复和本地播放结束（多结果可以合并一次激活）
  → 暂停实时麦克风上行并丢弃 PCM 上传期间采集的帧
  → 上传本地 16 kHz mono PCM16 工具完成提示并 commit
  → commit 写入完成后立即恢复麦克风
  → Duplex 读取 question 结果区块并生成下一轮语音回复
```

Canary 对照实验证明：当前 Duplex 的 `conversation.item.create(role=user,
input_text)` 虽可上行，但正文不进入后续音频轮次可见的推理上下文；正确 `id` 的
`conversation.item.update` 才会生效。update 是整段 replace，因此兼容层必须在本地
保存每个 question 的最小结果投影，防止较晚完成的任务覆盖较早结果。它仍是对 Duplex
缺少“追加外部 observation 并主动 create response”原语的 provider 兼容层，不是
`DynamicStreamTaskRunner` 的能力，也不进入工具执行职责。sync 模式完全不创建该调度器。

为验证 Duplex 服务端实际保存的上下文，当前 AgentSession 只在每次
`response.output_audio.done` 后发送一次不带 item id 的
`conversation.item.retrieve`（查询最近 20 轮）。不在 observation create 或后续
`response.done` 上重复采点。retrieve 请求及
`conversation.item.retrieved` 的完整 JSON 使用紫色 `[DUPLEX CONTEXT]` 日志输出；
查询仅用于观测，不参与回复调度。该探针可用 AgentSession 的
`context_diagnostics=False` 关闭。

## Duplex 输入/输出契约

- ``DuplexStreamModelAPI.submit()`` 恒返回 ``None``：Duplex 的 ``item_id`` /
  ``response_id`` 全部由服务端异步下发并出现在下行事件上，submit 时不存在同步
  correlation id（Responses 后端则可以同步保留 query id）。
- 普通用户 query 只能通过 ``AudioChunkInput + AudioCommitInput`` 提交。
  DynamicTask 使用 ``ContextItemUpdateInput`` 更新原问题，并用 PCM 另行激活推理。
  `conversation.item.create(role=user, input_text)` 仅保留在 Canary provider 实验中，
  不属于公共 `StreamModelInput`。
- 下行事件通过 ``DuplexStreamModelAPI.events()`` 暴露，并由一个外部
  ``DuplexAgentSession`` 独占消费；收到 ``session.closed`` 后事件流正常结束，此后
  ``submit()`` 抛错。
- ``ContextItemRetrieveInput`` 的服务端结果映射为
  ``StreamContextRetrievedEvent``，与音频、转写和 FC 一样只从统一 ``events()`` 通道
  下发；异步回灌调度器不自行发起额外 retrieve。
- Function Call 事件带 ``group_id`` / ``group_size``：同一次模型响应内的全部调用
  属于一个封闭分组，必须一起回传；Responses 后端在 sync 模式下也填充该分组。
- 音频播放层和会话编排只消费映射后的 ``StreamModelEvent``，不直接读取 WebSocket。

## Responses POC

## 核心语义

- 一个 session 只有一条串行模型生成通道。
- user query、占位 continuation 和真实工具结果共享同一个 FIFO mailbox。
- function call 与 function result 的相邻、成对关系是软约束；未完成的 tool call
  不会全局阻塞新的 user query。
- 每个真实工具结果独立形成 continuation，因此模型可以逐工具回答。
- query、模型事件和后续 continuation 均通过 `query_id` / `root_query_id` 关联。
- 普通 query 使用 `ModelAPI.stream()`；结构化 query 使用
  `ModelAPI.structured_output()`，两者共享 session context。

## sync 与 async 工具模式

`tool_call_mode="sync"` 时，ResponsesStreamModelAPI 不发送占位。同一模型轮次的真实
结果全部到齐后，它们会合并为一条配对的 `ToolResultsMessage` 继续模型调用；因此
sync 模式不会在同轮其他工具仍运行时提前回答。

`tool_call_mode="async"` 时，每个模型轮次产生的 tool calls 会合并为一条占位
`ToolResultsMessage`，不等待真实工具结果。同轮批量占位可避免只闭合部分调用而诱发
重复调用；如果模型第一轮只发出了一个慢 tool call，占位轮次仍能立即推动模型继续规划
并发出下一个独立 tool call。真实结果完成后，以 `[工具结果回灌]` user query 继续对话。

`ignore_placeholder_response_text=True` 只屏蔽占位轮次对外产生的 text 事件；该轮响应
仍会被完整消费、写入上下文，其中产生的 tool call 也仍会正常发出。

## Tool runner 边界

Responses 后端不依赖 runner。业务层消费 `StreamToolCallEvent`，调用外部
runner，拿到终态结果后再回灌。Duplex 会话内部则统一由 session 级
`TaskManager + DynamicStreamTaskRunner` 执行 raw tools，`tool_call_mode` 只决定结果
何时以真实批次或占位回执交还给 Duplex。

## API 示例

```python
from aicore.models.stream_model_api import ResponsesStreamModelAPI

session = ResponsesStreamModelAPI(
    model_api=create_responses_model_api(model="doubao-seed-1-8-251228"),
    tools=tools,
    system_prompt="...",
    tool_call_mode="async",
    ignore_placeholder_response_text=True,
)

async with session:
    await session.submit("查天气和咖啡店", query_id="q1")
    async for event in session.events():
        ...
```
