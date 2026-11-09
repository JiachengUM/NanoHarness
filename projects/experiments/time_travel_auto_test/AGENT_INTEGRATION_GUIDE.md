# 被测 Agent 接入指引（任何 Agent 架构 → 可测）

> 本文档是面向「接入者」的操作指南：无论你的助手底层是什么框架（自研对话引擎、某个
> multi-agent 编排、某家大模型 SDK、甚至是封装了物理设备的驱动），读完本文并完成
> 「接入思考清单」，就能写出一层薄薄的适配代码，让你的 Agent 进入
> `time_travel_auto_test` 平台接受自动测试与评判。
>
> 本文**只讲概念与协议契约**，不与任何具体 agent 框架（例如 v2_agent）在代码上耦合。
> 文末的「参考实现」只用于对照思路，不要求照抄。

---

## 0. 一页纸总览

你唯一要做的事：**写一个「适配层」类，实现 `AssistantProtocol` 的 5 个核心方法，再按
你的 Agent 能力选择性实现一组可选钩子。**

| 谁的责任 | 干什么 |
|---------|--------|
| 平台（CaseRunner / TimelineEngine / TraceRecorder / Judge） | 调度剧本事件、推进虚拟时间、投喂假人话语、记录全量轨迹、评分 |
| 你的适配层 | 把「你的原生事件」翻译成「统一协议事件」，把「协议调用」转发给「你的 Agent」 |
| 你的 Agent | 该干嘛干嘛（推理、调工具、控制车机……） |

**分水岭（关键概念）**：适配层以上是你的框架差异，适配层以下是平台统一世界。平台不
关心你的 Agent 是 ReAct 还是 pipeline，它只认 `AssistantEvent` / `StreamingReply` /
`ContextUpdateResult` 这几个统一契约。

```
       你的 Agent 原生事件（各框架不同）
                 │  ← 适配层在这里翻译（你的责任）
       统一协议事件 AssistantEvent（L1）
                 │  ← 平台统一处理（平台的责任）
   TraceRecorder → 时间线/对话流/工具泳道 → Judge
```

---

## 1. 先厘清平台怎么对待你的 Agent

接入前，先理解 4 个前提，否则容易写出「看似能跑、实则时序错乱」的适配层。

### 1.1 中立观察者模型：平台不打断你的 Agent

平台是**中立的记录者**，绝不主动打断你的 Agent 的推理与输出，只如实记录双方的事件流。

- 你说你的话，Agent 回它的话，双方可以**同时说话**（时间区间重叠会被如实记录）。
- 断言「你的 Agent 有没有响应插话打断」这件事，**由你的 Agent 自己驱动**：框架只负责
  把「用户开口」这个时机信号准确送到，打不打断是你 Agent 的能力，测试只是观察并记录
  它的真实行为。

> 这意味着：如果你的 Agent 本来不支持打断，你不用「假装」支持——按真实行为接入即可，
> 测试会把「不支持打断」如实呈现。但如果你的 Agent 支持打断，适配层要负责把「收到新的
> 用户开口」转成「打断自己旧输出流」的动作（见 §2.3）。

### 1.2 虚拟时间线：1:1 自然流逝 + 快进

平台内部有一条**虚拟时间线**（mock time），平时和真实时间 1:1 流逝，遇到远期剧本事件
会「快进」跳跃。你接触到的 `current_time`、以及事件上的 `wall_time` 都会被投影到这条
线上。对适配层的两个约束：

1. 事件时间戳要在**事件发生的那一刻**现场打（`datetime.now()`），不要事后补——否则
   TTFT（首字延迟）和停顿检测会失真。
2. 如果你的 Agent 内部有「定时任务 / 到期提醒」，它应该读取平台注入的「虚拟当前时间」
   而不是自己取系统时间（见 §4.2、§4.3），否则触发时刻会和虚拟时间线错位。

### 1.3 流式输入契约：第一个 chunk = 用户开口

`achat_stream` 收到的**不是一整句话**，而是一个**异步文本流**（模拟流式 ASR）：

- 第一个 chunk 到达 = **用户开口**（这是插话打断的时机信号）；
- 迭代器耗尽 = **用户说完**。

适配层要按这个语义消费输入，而不是「等全部字符到齐再一次性处理」（除非你的 Agent 底层
确实只能聚合后处理）。

### 1.4 事件流分层（L0 → L1）

- **L0**：你的 Agent 的原生事件（各框架自定义，平台不关心）。
- **L1**：统一协议事件 `AssistantEvent`（只有 3 种：文本增量 / 工具调用 / 工具返回）。

适配层的核心工作就是把 L0 翻译成 L1。这个翻译做得越细（文本能切到 chunk 级、工具能切到
调用/返回两个点），平台能记录到的轨迹就越丰富。

---

## 2. 核心协议：5 个必须实现的方法

平台用鸭子类型校验这 5 个方法（`is_assistant`），缺一不可。

### 2.1 `create(session_id, system_prompt="") -> None`

创建 / 重置一次对话会话。

- **职责**：清空所有会话级状态（对话历史、活跃流、后台任务句柄、定时任务等）。
- **session_id 规范**：平台每次 run 都用 `<case_id>-<t0_isoformat>` 保证隔离。
- 要点：如果上一轮残留了后台任务/定时器，**必须在 `create` 里停掉/清空**，否则会跨 case
  串扰。

### 2.2 `achat(user_text) -> str`（非流式，简单兜底）

发一句用户消息，返回 Agent 的完整回复文本。平台在 `use_streaming=False` 或某些简单路径
使用。**适配要点**：把输入塞给 Agent、拿回完整文本、写入你自己的对话历史即可。

### 2.3 `achat_stream(chunks) -> StreamingReply`（流式，主路径）

发一段流式输入，返回一个 `StreamingReply` 对象。这是绝大多数测试走的主路径。流程：

1. 消费输入流，感知「第一个 chunk（用户开口）」与「迭代耗尽（用户说完）」。
2. 启动一个**生产者逻辑**：调用你的 Agent 的流式推理接口；把每一个原生输出翻译成
   `AssistantEvent`，用 `reply.put_event(...)` 放入。
3. 全部结束后调用 `await reply.finish()`。
4. 立即 `return reply`（平台会异步消费 `reply.stream()`）。

**打断契约（按能力二选一）**：

- **支持插话打断**：收到第一个 chunk 时，中断自己**旧的活跃输出流**（旧回复提前结束，
  记为半截话），等本次输入收完后生成新回复。
- **不支持打断**：聚合完输入再处理（如实暴露底层限制），平台会记录「多流并行」的实际
  行为。

`StreamingReply` 的关键方法（生产者/消费者两侧都要知道）：

| 方法 | 谁用 | 作用 |
|------|------|------|
| `put_event(event)` | 生产者（适配层） | 放入一个 `AssistantEvent` |
| `put_chunk(text)` | 生产者（适配层） | 快捷放入一段文本（自动转 TEXT_DELTA） |
| `finish()` | 生产者（适配层） | 标记回复完成（放哨兵结束流） |
| `interrupt()` | 生产者（适配层打断时） | 标记半截话 + 取消进行中的推理 |
| `stream()` | 消费者（平台） | 异步迭代 `AssistantEvent` |

### 2.4 `aupdate_context(car_info, current_time=None) -> ContextUpdateResult`

通知 Agent「外部世界变了」。平台在两类时点调用：

- **车态变更**：剧本 set_state 模拟外部世界变化时，把最新 `car_info` 推给你。
- **时间推进**：快进到目标时刻时，把新 `current_time` 注入给你。

返回 `ContextUpdateResult`，三个字段：

| 字段 | 类型 | 何时填 | 作用 |
|------|------|--------|------|
| `proactive_text` | `str \| None` | 定时任务到期、Agent 主动开口时 | 记录主动话语（主动智能） |
| `proactive_segments` | `list[(float, str)]` | 同上，且你能拿到切块 | 让主动话语在时间线呈「区间+流式」而非瞬时点（偏移秒相对生成起点） |
| `injected_events` | `list[WorldTickScriptEvent]` | 你内部有定时任务时 | 让平台把「到期前 N 秒」作为停靠锚点注入事件队列 |

> 约定：`proactive_text` 是「助理自主说出口的话」，是评测点；`injected_events` 是「告诉
> 平台我什么时刻可能有事，请别跳过去」。

### 2.5 `adump_history() -> list[dict[str, str]]`

导出对话历史，格式 `[{"role": "user"/"assistant", "content": "..."}]`，供 Judge 回看。
**适配要点**：保持和你内部对话链一致，顺序正确、不要漏被打断的半截话。

---

## 3. 事件翻译：把原生事件映射成 `AssistantEvent`

`AssistantEvent` 只有三种类型，每种携带一个 `wall_time`（真实时间戳，现场打）：

| 类型 | 必填字段 | 含义 |
|------|---------|------|
| `TEXT_DELTA` | `delta` | 流式文本增量（越细越好，落到 chunk 级） |
| `TOOL_CALL` | `tool_name`, `tool_args` | 一次工具调用开始 |
| `TOOL_RESULT` | `tool_name`, `tool_result`, `tool_duration_ms` | 一次工具调用返回 |

`wall_time` 的用途（决定翻译质量）：

- 首字延迟 TTFT：首个 `TEXT_DELTA.wall_time - 回复开始时刻`。
- 流式停顿：相邻 `TEXT_DELTA` 间隔过大。
- 工具区间：`TOOL_CALL → TOOL_RESULT` 的时长。

**工具事件分两类，接入方式不同：**

- **同步工具**（调用→返回都在同一次回复流内）：翻译成相邻的 `TOOL_CALL` + `TOOL_RESULT`
  两个事件即可，平台自动配对成工具区间。
- **异步工具**（调用后返回，结果晚于主回复、甚至晚于整条流结束才回来）：主回复流里只能
  看到「调用」，看不到「结果」（结果后台才回来）。这种情况走 §4.4 的「回灌」钩子。

如果你的 Agent 底层**根本不吐**工具事件（把工具调用内部消化了），那平台就记录不到工具
泳道——这是你的框架能力边界，先如实承认，再决定是否在你的适配层里补一层「结果回灌」（见
§4.4）。

---

## 4. 可选钩子：按你的 Agent 能力按需实现

以下都不是 `is_assistant` 强制项，平台用 `hasattr` 探测，缺了就静默跳过。**实现得越多，
可测的能力维度越全。**

| 钩子 | 触发为真的条件 | 不实现的后果 |
|------|--------------|-------------|
| `virtual_car` 属性 | 你的 Agent 会操作车机状态（车控工具） | 车控结果不会被测试的状态断言看到 |
| `set_time_source(fn)` | 你的 Agent 内部需要「当前时间」（如定时提醒） | 定时任务触发时刻与虚拟时间线错位 |
| `get_pending_scheduled_tasks()` | 你有定时任务/到期行为 | 快进会一步跳过触发点，漏记主动话语 |
| `await_idle(timeout)`（统一权威忙碌信号） | 你有任何进行中活动（回复流 / 后台任务 / 回灌回复） | 时间快进穿透进行中的话语/工具/回灌回复，时间戳被扭曲 |
| `drain_backfill_tool_calls()` / `drain_backfill_tool_results()` / `drain_backfill_utterances()` | 你有异步工具、且结果晚于主回复回来 | 工具泳道缺「结果端」、后续主动回复不可见 |

### 4.1 `virtual_car`（车控状态共享）

平台初始化一个虚拟车实例后，会执行 `assistant.virtual_car = car` 把它共享给你。

**你要做的**：让 Agent 的车控工具去修改这个共享实例（例如把它传给车控工具的上下文），
而不是自己另造一份状态。这样剧本断言看到的、和 Agent 实际改的，是同一份状态。

### 4.2 `set_time_source(get_now)`（虚拟时钟注入）

平台调用 `assistant.set_time_source(lambda: mock_time)` 注入一个「实时虚拟时钟」回调。

**你要做的**：在 Agent 内部任何需要「当前时间」的地方（尤其是定时任务计算触发时间的工
具），走这个回调而不是 `datetime.now()`。这样即使回复期间时间在流逝，触发时刻也天然正确。

### 4.3 `get_pending_scheduled_tasks() -> list[(trigger_time, description)]`

返回你内部所有未触发的定时任务 `(到期时刻, 描述)`。

**作用**：平台快进时据此插入「中间停靠点」，保证不会一步跳过某个提醒的到期时刻。
**实现要点**：只返回**尚未触发**的；每项给一个人类可读的 `description`（会出现在日志/轨迹里）。

### 4.4 后台异步工具的回灌（三个 drain + 一个 idle）

概念：你的 Agent 甩出一个异步工具调用后，主回复流就结束了（Agent 先回一句「正在查询」），
真正的结果在**后台任务**里算完，才回灌给 Agent 产出「后续主动回复」。要把这段也记进轨迹，
需要三个「取走队列」的方法 + 一个「等待空闲」的方法：

- `await_idle(timeout)`：**统一权威忙碌信号**——阻塞直到你内部**所有**进行中活动都结束
  （或超时），须覆盖三类：回复流生成、后台异步任务执行、回灌回复生成。平台在**快进前**
  和**收尾时**调用，确保不会穿透任何进行中的活动、结果不丢、时间戳不被快进扭曲。
  （旧名 `await_async_idle` 保留为兼容别名。）
- `drain_backfill_tool_calls()`：返回 `[(wall_time, task_id, tool_name, tool_args), ...]`，清空队列。
- `drain_backfill_tool_results()`：返回 `[(wall_time, tool_name, result), ...]`。
- `drain_backfill_utterances()`：返回「后续主动回复」列表，每条需给出 `started_wall`、
  `ended_wall`、`text`、`segments`（chunk 级），让它在时间线呈区间 + 流式。

**关键经验（概念层）**：异步工具的结果回灌和你自己的「用户轮」是**并发**关系，如果你的
Agent 底层是基于同一条模型链串行推理，务必用一把「turn 锁」串行化「用户轮」与「回灌轮」，
否则会抢跑、上下文错乱。

### 4.5 主动话语区间化（`proactive_segments`）

见 §2.4。若你能在生成主动话语时拿到 chunk 级时间，就填 `proactive_segments`（每项 `(相对
生成起点的偏移秒, 文本增量)`），平台据此重建「起止区间 + 流式内容」；否则留空，平台回退成
「点事件」（功能不受影响，只是时间线不呈现时长）。

---

## 5. 接入思考清单（从你的架构反推）

动手前，用下面六个问题把「你的 Agent」映射到「协议实现」。这是本文最核心的部分。

1. **它有流式输出吗？**
   - 有 → `achat_stream` 用流式路径，逐 chunk 翻译成 `TEXT_DELTA`。
   - 没有（一次给全文）→ 也走 `achat_stream`，但整段作为 1~N 个大的 `TEXT_DELTA` 放入，
     或直接 `put_chunk(全文)`。

2. **它支持插话打断吗？**（决定 `achat_stream` 的分支）
   - 支持 → 第一个输入 chunk 触发「打断旧活跃流」。
   - 不支持 → 聚合输入后再处理。

3. **它有工具吗？工具是同步还是异步？**
   - 无工具 → 只产出 `TEXT_DELTA` 即可。
   - 同步工具 → 翻译成 `TOOL_CALL` + `TOOL_RESULT`。
   - 异步工具（结果后到）→ 加 §4.4 的 `await_idle` + 三个 `drain_backfill_*`。
   - 底层不吐工具事件 → 平台记录不到工具泳道（能力边界），可选在适配层补回灌层。

4. **它有定时任务 / 主动智能吗？**
   - 有 → 实现 `set_time_source`（虚拟时钟）、`get_pending_scheduled_tasks`（停靠点）、
     `aupdate_context` 里返回 `proactive_text`（+ `proactive_segments`）+ `injected_events`。

5. **它操作车机状态吗？**
   - 有 → 暴露 `virtual_car` 属性，让车控工具写共享实例。

6. **它的会话如何隔离？**
   - 在 `create` 里**全部重置**（历史、活跃流、后台任务、定时器），避免跨 case 串扰。

---

## 6. 最小可运行骨架（通用伪代码，不依赖任何具体框架）

```python
class MyAgentAdapter:
    def __init__(self):
        self.virtual_car = None              # 4.1 可选
        self._history: list[dict] = []
        self._active_reply = None            # 用于打断旧流
        self._get_now = None                 # 4.2 可选
        self._pending_tasks = []             # 4.3 可选
        self._backfill_tool_calls = []       # 4.4 可选
        self._backfill_tool_results = []
        self._backfill_utterances = []

    # ---- 2.1 会话隔离 ----
    def create(self, session_id, system_prompt=""):
        self._history = []
        self._active_reply = None
        self._pending_tasks = []
        self._backfill_tool_calls = []
        self._backfill_tool_results = []
        self._backfill_utterances = []

    # ---- 2.2 非流式 ----
    async def achat(self, user_text: str) -> str:
        reply = await self._agent_call(user_text)     # 你的 Agent 一次返回全文
        self._history += [{"role": "user", "content": user_text},
                          {"role": "assistant", "content": reply}]
        return reply

    # ---- 2.3 流式（打断契约）----
    async def achat_stream(self, chunks) -> StreamingReply:
        first = await self._first(chunks)             # 手动取第一个 chunk
        if first is None:
            r = StreamingReply(); await r.finish(); return r
        if self._active_reply is not None and not self._active_reply.is_done:
            self._active_reply.interrupt()            # 支持打断：中断旧流
        user_text = "".join([first] + [c async for c in chunks])

        reply = StreamingReply()
        self._active_reply = reply
        async def _produce():
            try:
                async for token in self._agent_stream(user_text):   # 你的流式接口
                    await reply.put_event(AssistantEvent(           # L0→L1 翻译
                        type=AssistantEventType.TEXT_DELTA,
                        wall_time=datetime.now(),                    # 现场打时间戳
                        delta=token,
                    ))
            finally:
                await reply.finish()
        asyncio.create_task(_produce())
        return reply

    # ---- 2.4 上下文 + 主动智能 ----
    async def aupdate_context(self, car_info, current_time=None) -> ContextUpdateResult:
        if current_time is not None:
            due = self._due_tasks(current_time)      # 你的定时任务到期检查
            if due:
                text, segs = await self._generate_proactive(due)   # 生成提醒
                return ContextUpdateResult(proactive_text=text, proactive_segments=segs)
        return ContextUpdateResult()

    # ---- 2.5 导出历史 ----
    async def adump_history(self) -> list[dict]:
        return list(self._history)

    # ---- 4.x 可选钩子按需实现：set_time_source / get_pending_scheduled_tasks / await_idle / drain_backfill_* ----
```

> 上面 `_agent_call` / `_agent_stream` / `_due_tasks` / `_generate_proactive` 都是「你的 Agent
> 的能力」，用你自己的框架实现；协议侧的骨架与上面的通用逻辑一致。

---

## 7. 经验与陷阱（概念层）

1. **时间戳现场打**：`wall_time` 必须在事件产生的那一刻 `datetime.now()`，不要等流结束了统一补。
2. **不要事后补事件顺序**：工具/文本事件按产生顺序放入 `StreamingReply`，平台按序消费。
3. **并发轮要上锁**：异步工具回灌轮和正常用户轮若共用一条模型链，必须串行化，否则上下文错乱。
4. **结果回灌要等到终态**：快进前平台会 `await_idle`，你的实现必须保证「任务终态 + 回灌
   回复产出」都完成才返回，否则最后一轮结果会被快进穿透、丢失。
5. **会话隔离要彻底**：`create` 里漏掉某个后台任务/定时器清空，会在后续 case 里诡异地出现残留行为。
6. **打断是能力不是义务**：不支持打断就如实接入，别「假装打断」；测试观察的是真实行为。
7. **工具泳道取决于你是否吐 TOOL_CALL/TOOL_RESULT**：底层不吐，平台就空着，这不算接入 bug，
   但若想展示工具，就要在适配层补回灌层。
8. **主动话语区间化可选**：不给 `proactive_segments` 也能测「主不主动」，只是时间线呈现成点；
   给了就是区间 + 流式。

---

## 8. 验证清单（接入完成标准）

- [ ] 5 个核心方法全部实现，`is_assistant(你的实例)` 返回 `True`。
- [ ] 跑一个纯文本 case，对话流能看到逐字/逐块文本，时间为区间而非点。
- [ ] 若支持打断：跑一个插话 case，旧流被标记为半截话，时序正确。
- [ ] 若有工具：跑一个带工具 case，工具泳道能看到调用→返回的区间。
- [ ] 若有异步工具：结果回灌后，工具泳道补上「结果端」+ 后续主动回复，且时间戳没被快进扭曲。
- [ ] 若有定时任务：快进在到期点停靠，主动话语被记录且时刻正确。
- [ ] 若有车控：状态断言能看到 Agent 改的车态（共享 `virtual_car` 生效）。
- [ ] 同一助手连跑多个 case，无历史/后台任务/定时器残留。

---

## 9. 参考实现对照（看思路即可，不必照抄）

| 文件 | 看什么 |
|------|--------|
| `case_runner/assistant_protocol.py` | 协议权威定义：`AssistantProtocol` / `StreamingReply` / `AssistantEvent` / `ContextUpdateResult` |
| `case_runner/mock_assistant.py` | **最小参考实现**（无 LLM、纯规则、代码最短），先看这个上手 |
| `case_runner/runner.py` | 平台如何调用你（`hasattr` 探测可选钩子、`achat`/`achat_stream` 两条路径、快进/收尾的 drain 时机、`_handle_context_update` 如何落主动话语） |
| `judge/judge.py` | 平台如何用 TraceRecorder 产出的轨迹做终局评判 |
| 项目内一个真实的 LLM Agent 适配层 | 观察「流式打断 + 异步工具回灌 + 主动智能」的完整实现（作为进阶参考，不代表必须照搬其框架） |