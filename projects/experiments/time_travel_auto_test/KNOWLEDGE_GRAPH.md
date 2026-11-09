# time_travel_auto_test 知识图谱

> **四个文档分工**：
> - [`ARCHITECTURE.md`](./ARCHITECTURE.md) — **怎么工作**：架构图、执行流程、核心机制（图示为主）
> - [`CONTEXT.md`](./CONTEXT.md) — **为什么这么设计**：设计原则、决策记录、路径速查
> - [`KNOWLEDGE_GRAPH.md`](./KNOWLEDGE_GRAPH.md) — **实体关系**：详细数据模型、类间关系（本文件）
> - [`AGENT_INTEGRATION_GUIDE.md`](./AGENT_INTEGRATION_GUIDE.md) — **怎么接入**：任何 Agent 架构如何实现 AssistantProtocol 接入平台（操作指引，通用概念层，不耦合具体框架）
>
> 本文档是 `time_travel_auto_test` 项目的知识图谱导出，用于辅助快速理解项目结构与核心设计。
> 维护约定：项目发生实质性架构/实现变更后，须同步更新本文档与 MCP Knowledge Graph Memory 中的对应实体。
> 最后更新：2026-08-28（可视化 M1 增强：**时间线推倒重写——live 滑动窗口 + replay 缩放视窗双模式**——buildTimeScale 改 ScaleOptions 联合类型（live：当前虚拟时刻轴线恒映射 x=0.5 居中，窗口 [axis±半窗] 基准 20s 经 computeLiveWindowMs 按轨道像素 25ms/px 自适应，历史在左未来在右，秒级网格线 1-2-5 步长随窗流动、T0 原点线加粗；replay：全程分段映射 normal 按时长比例 + 快进压缩 6% 窄带，zoomReplayView 锚定游标缩放 ×1~×64 + clampPanX 平移钳制 [0,1-1/zoom] + followCursorView 播放自动跟随 + 新 run 重置 zoom=1；clipSpanToView 视窗裁剪统一（窗外不渲染、跨缘裁 [0,1]、x() 不钳位）；坑：live 20s 窗口内快进表现为窗口整体跳变不压缩）；此前："劲舞团"式过程可视化——script_plan 剧本时间表驱动未来区预设事件竖线预览 + 车态变更来源三色（record_set_state source 参数：script 金/assistant 红/fake_person 蓝预留）+ CarStatePanel 变更分组临时置顶 1 秒 + builtin-god-view 混合来源 case；更早：实时增长条 + 工具子泳道 + 面板拖拽布局——useNowTicker 实时虚拟时钟（双时间戳外推 nowMs）/ live 缓冲记录开口时刻（projectLiveSpans 投影 [开口, now]）/ projectToolSpans 工具子泳道（栈式配对 + 行打包分行）/ PanelResizer 面板拖拽调高 + localStorage 持久化；再早：可视化回放模式 + 虚拟车状态观察窗（时间线拖拽定位游标 / 倍速回放 1x~5x 对话流同步跟随 / 车态时间机 projectCarState / case_started 补 initial_car_info 初值 + VirtualCar.on_field_change 钩子）；再早：自然时间流逝模型 + WorldTick + 事件流协议四层轨迹 + 中立观察者模型（插话重叠如实记录/流式投喂/迟到锚点静默跳过）+ 接入层插话打断（barge-in）文字层实现 + 可视化 M1 实时模式（旁路事件总线 + WS 服务器 + React 前端三面板）+ 工具调用全程可见 + long_pause 语义修正 + 被测助手 mock/v2 选择 + 裁判终局评判 + 相对 T0 时间戳；MCP Knowledge Graph Memory 已同步更新）

---

## 1. 项目概览

### 1.1 time_travel_auto_test（Project）
- 新一代车载助手场景化自动测试框架，位于 `projects/experiments/time_travel_auto_test`
- 目标：全双工时序演进式车载助手测试，支持代码层协议测试 + 物理设备语音测试
- 核心特性：双模接入、自然演进、时序插话、时间加速、完整 Trace、终局评判
- 与 `auto_test_script` 是演进关系：auto_test 是回合制 ping-pong，time_travel 是事件驱动时序 + 全双工 + 打断
- 假人概念与 auto_test 同名类是同一域概念在新范式下的完整实现（人设 + 剧本 + LLM），不 rename
- 现阶段聚焦：实时全双工对话场景测试的 schema 与假人/虚拟车驱动器
- 运行模式：`REALTIME`（wall-clock + 快进检测，测 Siri/实体车机）和 `ACCELERATED`（纯虚拟时间，代码回归测试，对应 `fast_mode=True`）

### 1.2 auto_test_script（Project）— 演进来源
- 现有生产自动测试框架，位于 `projects/mind/mem/auto_test_script`
- 范式：LLM 假人话剧式多轮 ping-pong；回合制；假人 LLM 读 `expected_script`
- 断言：mainly `nl_assertion` + Judge LLM
- 时间：per-session `mock_time`
- `time_travel_auto_test` 仅作参考，不在该目录改代码；演进只在 `time_travel_auto_test` 内进行
- 可复用：`AnyBotToTest` 协议、外部 API 重试、Judge/ReportWriter、火山记忆集成、并发与进度条
- 不应直接照搬：`aauto_chat_test` 的 while 循环（回合制 + 退下终止 + 假人内嵌打分）；`expected_script` 过载

### 1.3 核心文档
| 文档 | 说明 |
|------|------|
| `ARCHITECTURE.md` | CaseRunner 架构文档，含核心架构图、组件设计、双层演进、五大关键机制（自然流逝/WorldTick/插话打断/快进/事件流协议）、已完成清单、变更记录。最后更新 2026-08-28 |
| `CONTEXT.md` | 工作上下文文档，Agent 开始新任务前应优先阅读。含 §0 工作原则（14 条）、核心设计原则（含打分机制 §2.7）、决策记录（含 WorldTick 注入事件机制 §7.4）、路径速查。最后更新 2026-08-25 |
| `AGENT_INTEGRATION_GUIDE.md` | 被测 Agent 接入指引：任何 Agent 架构（不同框架/同步异步工具/有无插话打断/定时主动智能/车控）如何实现 `AssistantProtocol` 的 5 个核心方法 + 可选钩子，含事件翻译（L0→L1）、流式输入与打断契约、主动话语区间化、后台异步结果回灌与「接入思考清单」。通用概念层描述，不耦合 v2_agent 等具体框架代码 |

---

## 2. 核心机制（Concept）

### 2.1 双层演进机制
- CaseRunner 的核心调度模式，由 `EventScheduler` 实现
- **边界驱动（默认，90% 场景）**：对话完成 → 立即下一轮，无显式等待；适用于跨多轮记忆 case、20 轮闲聊
- **显式时间戳锚点（覆盖，10% 场景）**：`event_t0_plus_timedelta` 精确控制；适用于插话打断、长时间等待后验证
- 边界事件 sort_key 用 `(t0, original_index)`（和 PT0S 锚点同等优先级，按 original_index 排序）
- 锚点事件 sort_key 用 `(t0 + delta, original_index)`（按时间先后排序）
- 演进模式对比：旧显式时间戳 `PT0S/PT1M/PT2M` vs 新边界驱动 `第1轮/第2轮/第3轮` 标记自然流动

#### 2.1.1 边界驱动
- 双层演进的默认模式，由 `BoundaryDetector` 检测一轮对话是否应结束
- 边界检测策略（现阶段简单版）：
  - 助手说完一句话 → 触发边界（一轮结束）
- 事件 `event_t0_plus_timedelta` 为 `None` 表示边界驱动模式
- 上一轮自然结束后立即执行下一事件（delta=0，无等待）

#### 2.1.2 锚点驱动
- 双层演进的覆盖模式，用于插话重叠等精确控制场景
- 事件 `event_t0_plus_timedelta` 不为 `None`，表示在精确时间点执行
- 锚点到达时（中立观察者模型，2026-08-25 定稿）：
  - 若助手正在回答 → **不打断**，假人按锚点时刻如实开口，双方话语重叠如实记录
  - 假人话语流式投喂（第一个字即投）：输入流实时推给助手，助手多流并行如实记录
- 示例：`PT30S` 锚点插入"等等，我改主意了"（与助手回复重叠时记重叠窗口）；`P5D` 快进锚点触发时间加速
- `EventSource`: `ANCHOR` / `BOUNDARY` / `STATE_CHECK`

### 2.2 插话重叠 + 流式投喂（中立观察者模型）
- 全双工场景的核心机制（2026-08-25 定稿，2026-08-26 改流式投喂）：框架是中立测试工具，不主动打断被测助手、不截断其输出流、不遗漏任何一侧事件
- `StreamingReply` 支持流式交互：`put_event` / `put_chunk` 增量放入、`stream()` 异步迭代获取；`interrupt()` 供被测助手插话打断自中断旧流（框架不主动调用）
- 重叠记录：假人与助手话语区间相交 → trace 各自区间如实记录，`get_overlaps()` 检测重叠窗口
- 重叠渲染：`━━━ 双方同时说话 [起点 → 终点] ━━━` 块内按 chunk 级时间戳（`segments`）切出双方在窗口内实际说出的文字——不完全重叠只标重叠部分
- 流式投喂（第一个字即投，模拟流式 ASR）：`achat_stream` 输入为异步文本流——第一个 chunk = 用户开口（插话打断时机信号），迭代器耗尽 = 用户说完；Runner 在假人第一个 `text_delta` 即 `_spawn_stream` 启动后台流任务（`_active_stream_tasks` 跟踪），后续字实时推入，`speak_done` 发 EOF
- 插话打断能力可测：支持打断的助手在第一个 chunk 中断旧流（`reply.is_interrupted` → trace 记 `is_partial=True` 半截话）；不支持的聚合输入后处理（多流并行，每条流独立记录）——是否中断旧流由被测助手自行决定，框架如实记录
- 接入层插话打断参考实现（2026-08-26，v2 TestedAssistant）：v2_agent 底层 `astream` 无打断机制（探测证实：并发=多流并行+链路分叉、串行=排队非打断），音频侧插话打断在 TTS 播放层——文字层由接入层 `tested_assistant.py` 补齐（不改 aicore 框架代码）：第一个输入 chunk 到达即 `interrupt()` 旧活跃流（`_active_reply` 跟踪，实测 13ms 中止），半截话同步入 `_history`（`［被用户打断，未说完］`标记），被打断轮不写回模型链（丢弃语义）
- 半截话语义：`is_partial=True` 出现于回复超时被截断（基建兜底）或助手自己插话打断中断旧流（`reply.is_interrupted`）；框架自身不产生半截话
- `StreamingReply` 内部用 `asyncio.Queue` + `asyncio.Lock` 保证生产者/消费者安全

### 2.3 时间加速（快进）
- 由 `TimelineEngine` + `Runner._maybe_accelerate` 实现（已集成）
- 触发条件：下一事件是锚点事件且 `gap = anchor_time - mock_time > 阈值`（默认 60s）
- 行为：`accelerate_to(target)` 跳到目标时间（唯一的时间跳跃方式），记录 `(from, to)` 到 `accelerations`
- 多步快进：若 `[current, target]` 区间内有 pending 定时任务，查 `get_pending_scheduled_tasks()` 逐个停靠触发，不跳过
- 快进前 `aupdate_context(car_info, current_time=target)` 同步助手时间（主动智能测试核心）
- 示例：周五场景 — 周一 8:00 播放"记得周五放周杰伦" → 快进 5 天 → 周五 18:00 验证播放
- `fast_mode`（测试用）：跳过锚点事件的真实时间等待，长周期测试从 209s 降到 8.9s

### 2.4 全双工对话
- CaseRunner 的核心目标，区别于 auto_test 的回合制 ping-pong
- 双方可同时说话：插话与助手流式回复重叠时如实记录重叠窗口（中立观察者模型）
- `StreamingReply` 支持增量获取（`_assistant_chat_streaming` 消费事件流，计算 TTFT/检测停顿/记录工具调用）

### 2.5 调度器回调模式
- `EventScheduler` 的核心设计：调度器跑主循环，事件就绪时回调 Runner
- Runner 只负责初始化、事件分发、结果收集，不参与调度决策
- `set_on_execute(callback)` 注册回调；`schedule_batch(events)` 批量加载；`run()` 启动主循环
- 边界事件立即执行；锚点事件等待到 `anchor_time`（可被新事件抢占）
- `fast_mode=True` 时跳过真实时间等待

### 2.6 助手接入协议
- 类似于 auto_test 的 `AnyBotToTest`，CaseRunner 定义 `AssistantProtocol`
- 核心方法：
  - `create(session_id, system_prompt)` — 创建/重置会话
  - `achat(user_text) → str` — 非流式对话
  - `achat_stream(chunks: AsyncIterator[str]) → StreamingReply` — 流式对话（流式输入 + 可打断），产出 `AssistantEvent` 事件流
  - `aupdate_context(car_info, current_time=None) → ContextUpdateResult` — 通知外部上下文变化（车态 + 时间推进）；返回结构化结果：`proactive_text`（主动话语）+ `injected_events`（注入的 WorldTick 锚点）
  - `adump_history() → list[dict]` — 导出对话历史供 Judge
- 可选扩展：`set_time_source(get_now)` — Runner 注入实时虚拟时间源，助手侧工具取当前虚拟时刻（自然流逝模型核心）
- `session_id` 格式：Runner 使用 `<case_id>-<t0_isoformat>` 确保每次 run 隔离
- `is_assistant(obj)` 类型检查工具函数
- 参考实现：`TestedAssistant` 在 `demos/v2_agent_to_test/tested_assistant.py`（`achat_stream` 实现接入层插话打断：第一个输入 chunk 到达即 interrupt 旧活跃流，半截话入 `_history`，被打断轮不写回模型链——不改 aicore 框架代码）
- VirtualCar 共享：Runner 初始化后通过 `assistant.virtual_car = car` 共享，车控工具和剧本事件操作同一份状态
- 时间推进语义：Runner 快进前调 `aupdate_context(current_time=target)`，助手基于新时间自主决定是否触发行为（主动智能测试核心，§2.5）

### 2.7 state_check 断言
- 剧本事件的一种 `action_type`，用于可结构化断言的主体（现阶段主要是虚拟车 k/v）
- 虚拟车 state_check 只有 k/v（`expected_fields: dict`），无自然语言整体预期
- 假人不做 state_check：`state`/`intent` 为自然语言不可穷举难以可靠 code 断言；假人侧预期走 `must_pass_assertions` + `bonus_assertions` + Judge
- `TestCase.virtual_car_state_check_assertions` 字段专门存放 state_check 事件，不得出现在 `script_events` 中
- Runner 运行时按 `event_t0_plus_timedelta` 合并成同一时间线，state_check 本质上仍是剧本事件
- `VirtualCarStateCheckOutcome` 包含：`expected_fields` / `passed` / `mismatches`（field → {expected, actual}） / `car_info` 快照

### 2.8 虚拟车 set_state 分工（Authoring 约束）
- 区分助手车控与外部世界演进
- **助手车控结果**（空调、车门、导航目的地、媒体等）：须由被测助手程序调 `VirtualCar` 暴露的车控接口写入 devices；用例里禁止用剧本 `set_state`「上帝之手」代写，验收走 `virtual_car_state_check_assertions`
- **外部世界演进**（驾驶员踩油门、挂 D 档上路等助手不应伪造的变化）：可用剧本 `set_state` 模拟（走 CAR_INFO_FIELD_MAP 映射到 devices）
- `VirtualCarControlTool` 是被测助手调用的车控接口（`VirtualCarController`）：自然语言指令 → `{car_info key: 中文值}` 写入集 → 统一 `VirtualCar.set_field` 落盘（触发 on_field_change → car_set_state 事件）；覆盖车载设备（空调含风向/座椅含按摩零重力/方向盘加热/门窗天窗遮阳帘/灯光/电视/冰箱/档位手刹），含行驶安全约束（行驶中开窗开门等危险操作拒绝）；**导航/媒体不是车控**——分别是独立工具 `NavigationControlTool`（name="navigation"）/ `MediaControlTool`（name="media"，demos/v2_agent_to_test/tools/），同样走 set_field 落盘，媒体切歌诚实拒绝（无歌单队列）

### 2.9 自然时间流逝模型（2026-08-25 定稿）
- 取消旧版"助手回复期间虚拟时间冻结"假设：虚拟时间与真实时间 1:1 连续自然流逝
- `TimelineEngine` 内部只存一个锚点对 `(anchor_mock, anchor_wall)`，`mock_time = anchor_mock + (now - anchor_wall)` 每次读取实时计算
- 唯一的时间跳跃方式是快进 `accelerate_to(target)`：重新锚定 `(target, now)`
- `pin_to`：调度器真实等待锚点存在毫秒级误差，容差内（5s）对齐让时间戳干净
- `wall_to_mock`：把事件流携带的 wall_time 换算进虚拟时间线（1:1 流逝期间双向换算）
- **为什么必须自然流逝**：本框架评测的就是"时间自然流逝下被测 agent 与假人的交互"；助手回复期间调用 `set_reminder` 等工具通过 `set_time_source` 注入的实时虚拟时间源取当前时刻，`trigger_time` 天然包含回复耗时——无需任何偏移修正补丁（旧版 `offset_recent_tasks`/`_created_at`/`advance_to` 已全部删除）
- 话语区间化：`UtteranceRecord.started_at/ended_at` 必填，时间戳来自自然流逝的虚拟时间
- 调度器锚点等待基于虚拟时间（`get_now` 注入）：快进后虚拟时间领先真实时间，等待必须按虚拟距离算

### 2.10 WorldTick（时间锚点事件）
- 时间线上一个"停靠点"：无执行主体（`target="world"`），只表示"时间演进到此刻必须停一下，因为有事会发生"
- 来源：剧本显式定义 / 被测助手运行时注入（`aupdate_context` 返回 `ContextUpdateResult.injected_events`）
- 5 秒缓冲：`ScheduledTaskManager.add_task` 自动记录 `trigger_time - WORLD_TICK_BUFFER(5s)` 作为锚点注入时间
- 两级触发保障：主通道为锚点 drain（`_execute_world_tick` → `_drain_pending_tasks_near_anchor`），兜底通道为多步快进（无锚点时靠 `get_pending_scheduled_tasks` 停靠触发）
- 注入事件合并：Runner `_handle_context_update` 将注入 WorldTick 转为 `ScheduledEvent`（`original_index=-1`）加入事件队列

### 2.11 事件流协议 + 四层轨迹命名体系（2026-08-25）
- 双侧（假人 + 被测助手）以统一事件流协议接入，携带 wall_time 时间戳
- 四层命名：L0 SUT 原生事件 → L1 协议事件（`AssistantEvent` / `FakePersonEvent`，分水岭：接入层责任 vs 平台责任）→ L2 测试轨迹（`TraceRecorder` 权威记录）→ L3 裁判视图（`render_timeline_text` 投影）
- `AssistantEvent`：TEXT_DELTA / TOOL_CALL / TOOL_RESULT；`FakePersonEvent`：speak_start / text_delta / speak_done
- 时序信息采集（体验维度评测）：TTFT 首字延迟、说话时长、>2s 流式停顿（LONG_PAUSE，仅文本流内停顿——工具边界间隙不算，2026-08-26 修订）、工具调用耗时、主动话语触发延迟
- `TestedAssistant._translate_event` 把 v2_agent 原生事件翻译为 `AssistantEvent`（L0→L1）

---

## 3. 模块与文件结构

```
time_travel_auto_test/
├── ARCHITECTURE.md                          ← 架构文档
├── CONTEXT.md                               ← 工作上下文
├── KNOWLEDGE_GRAPH.md                       ← 本文档
├── case_schema.py                           # TestCase 模块
├── script_events/
│   └── script_event.py                      # 剧本事件定义
├── fake_person/
│   ├── models.py                            # 假人模型
│   └── llm_prompt.py                        # 假人 LLM prompt（纯剧本驱动）
├── virtual_car/
│   ├── models.py                            # VirtualCar (devices 真相源)
│   └── car_devices.py                       # 虚拟车设备状态
├── case_runner/                             # Runner 核心框架
│   ├── __init__.py                          # 公开 API 汇总
│   ├── runner.py                            # CaseRunner 主调度器
│   ├── scheduler.py                         # EventScheduler
│   ├── timeline.py                          # TimelineEngine
│   ├── dialogue.py                          # DialogueManager + BoundaryDetector
│   ├── trace.py                             # TraceRecorder
│   ├── assistant_protocol.py                # AssistantProtocol + StreamingReply
│   └── mock_assistant.py                    # MockAssistant（规则回复，测试/可视化 demo 共用）
├── judge/                                   # Judge 终局评判（独立模块，与 fake_person/ 同级）
│   ├── __init__.py                          # 公开 API 汇总
│   ├── models.py                            # JudgeInput / JudgeVerdict / AssertionResult / ScoreBreakdown / AssertionType
│   ├── scoring.py                           # compute_score（必过 + 加分 → 0-100 分）
│   ├── prompt.py                            # JUDGE_SYSTEM_PROMPT + render_timeline_text
│   └── judge.py                             # Judge 类 + build_judge_input_from_run_result
├── demos/                                   # 被测 Agent 实现 + 端到端 demo
│   ├── tools/
│   │   └── virtual_car_control.py           # 虚拟车控工具 car_control（不含导航/媒体——独立工具）
│   ├── v2_agent_to_test/
│   │   ├── __init__.py                      # 公开 API（导出 TestedAssistant）
│   │   ├── tested_assistant.py              # TestedAssistant（实现 AssistantProtocol）
│   │   └── tools/
│   │       ├── navigation_control.py        # 导航工具 navigation（设目的地/取消/查询）
│   │       ├── media_control.py             # 媒体工具 media（播放/点歌/音量/音源/查询）
│   │       └── scheduled_tasks/             # 定时任务机制（时间锚点注入）
│   └── run_e2e_demo.py                      # 端到端真实 LLM 测试 demo（TestedAssistant + CaseRunner + Judge）
├── visualizer/                              # 测试过程可视化（M1 实时模式 + 回放模式）
│   ├── event_bus.py                         # 旁路事件总线（双时间戳信封）
│   ├── run_server.py                        # FastAPI + WebSocket 服务器（命令-ACK + 事件流推送 + case 完成自动终局评判 + judge_case 手动重评）
│   └── frontend/                            # React 19 + Vite + TS 前端（对齐 v2_frontend）
│       ├── src/adapters/visualizerClient.ts # WS 客户端
│       ├── src/domain/events.ts             # 事件归一化（信封 → 强类型事件，含 judge_verdict / initialCarInfo）
│       ├── src/app/consoleReducer.ts        # 核心 reducer（事件即 action，含 JudgeState + PlaybackState 回放状态机 + live 缓冲开口时刻）
│       ├── src/app/projections.ts           # 纯函数投影（对话流回放裁剪/车态时间机/双模式时间线刻度 live 滑动窗口+replay 缩放视窗/工具子泳道/live 增长条/重叠窗口/clipSpanToView 视窗裁剪）
│       ├── src/app/usePlaybackEngine.ts     # rAF 回放引擎（倍速推进游标，单帧 dt 钳制）
│       ├── src/app/useNowTicker.ts          # 实时虚拟时钟（双时间戳外推 nowMs，驱动轴伸长/增长条）
│       └── src/components/                  # RunConsole / ChatStream / TimelineLanes / CarStatePanel / VerdictPanel / PanelResizer
└── test/                                    # 测试（126 个全通过）
    ├── cases/
    │   └── fixture_cases.json               # 12 个 fixture cases
    ├── test_virtual_car_v2.py               # VirtualCar 单元测试
    ├── test_scheduler_v3.py                 # EventScheduler 单元测试
    ├── test_case_runner_e2e.py              # CaseRunner 端到端测试（含时间加速 / 主动智能 / 流式打断）
    ├── test_case_schema.py                  # TestCase schema 测试
    ├── test_fixture_cases_json.py           # fixture cases 导入/导出测试
    ├── test_judge.py                        # Judge 评判测试（含打分 + 渲染 + LLM 评判）
    ├── test_tested_assistant.py             # TestedAssistant 单元测试（mock agent）
    ├── test_navigation_media_tools.py       # 导航/媒体独立工具单元测试（19 个，真实 VirtualCar 链路）
    ├── test_event_bus.py                    # 事件总线 + TraceRecorder/Runner 事件发射测试
    └── test_run_server.py                   # WS 服务器命令/事件流/自动+手动终局评判测试（真实 uvicorn 线程）
```

---

## 4. 数据模型层（Schema）

### 4.1 case_schema 模块

#### TestCase（Class）
- 一个车载助手测试场景：假人/虚拟车初始信息 + 剧本事件时间线 + 判据
- 字段：
  - `id` / `case_name` / `case_description` / `tags`
  - `t0: Optional[datetime]` — 场景起始时间（ISO 8601），优先级：传入参数 > `case.t0` > `datetime.now()`
  - `max_round` — 默认 8
  - `fake_persons: list[FakePersonInfo]`（≥1）
  - `virtual_car: VirtualCarInfo`
  - `script_events: list[ScriptPerformEvent]` — `event_t0_plus_timedelta` 为 `None` 表示边界驱动
  - `virtual_car_state_check_assertions: list[VirtualCarStateCheckScriptEvent]` — 仅含 state_check，不得出现在 script_events 中
  - `text_script`
  - `must_pass_assertions: list[str]` — 必过断言，至少一条非空字符串；任一不过 → 0 分（含 state_check 失败）
  - `bonus_assertions: list[str]` — 加分断言，可选；过得越多分数越高
  - `nl_assertions: Optional[list[str]]` — [已废弃] 旧字段，导入时自动迁移到 `must_pass_assertions`
- `model_validator(mode="after")` 验证：旧 `nl_assertions` 自动迁移到 `must_pass_assertions`；`must_pass_assertions` 至少一条非空；role_id 不重复；假人事件 target 须在 fake_persons 中且为 perform；虚拟车事件 target 须为 'car'
- JSON 批量导入：顶层 `[case,...]`、`{"cases":[...]}` 或单个 case 对象均可
- 工具函数：`load_test_cases_from_json` / `load_test_cases_from_json_file` / `dump_test_cases_to_json`
- `TestCase.__test__ = False` 避免 pytest 误收集

#### FakePersonInfo（Class）
- 场景内一名假人的初始信息（JSON 可序列化；由 runner 构造 `FakePerson` 运行时实体）
- 字段：`role_id` / `profile` / `event_memory` / `state` / `intent`

#### VirtualCarInfo（Class）
- 场景内虚拟车的初始信息
- 字段：`car_info: dict[str, Any]`（前端 JSON 传入，构造 VirtualCar 时解析到 devices）

### 4.2 script_events 模块

#### ActionType（Enum）
- `PERFORM = "perform"` — 执行演绎
- `STATE_CHECK = "state_check"` — 在指定时刻检查状态

#### ScriptEventType（Enum）
- `FAKE_PERSON = "fake_person"`
- `VIRTUAL_CAR = "virtual_car"`
- `ENVIRONMENT = "environment"`（预留）
- 主要为 JSON 导入/导出服务；Python 侧优先用 `isinstance` 区分

#### ScriptEventBase（Class）
- 剧本事件公共字段基类
- 字段：
  - `event_t0_plus_timedelta: Optional[timedelta]` — `None` 表示边界驱动
  - `event_type: ScriptEventType` — JSON tag
  - `target: str` — 事件目标主体 id（如 userA、car、world）

#### FakePersonScriptEvent（Class）
- 假人剧本事件：全双工场景下驱动假人说话
- `event_type = FAKE_PERSON`，`target` 为假人角色 id
- `action: FakePersonAction`
- TestCase 验证：假人事件必须为 perform 动作

#### VirtualCarPerformScriptEvent（Class）
- 虚拟车剧本演绎事件：set_state 写 car_info（仅 perform）
- `event_type = VIRTUAL_CAR`，`target = 'car'`
- Authoring 约束：set_state 只模拟非助手车控的外部世界变化

#### VirtualCarStateCheckScriptEvent（Class）
- 虚拟车状态断言事件：在指定时刻对 car_info 做 k/v 检查（仅 state_check）
- 存放在 `TestCase.virtual_car_state_check_assertions`

#### EnvironmentScriptEvent（Class）
- 环境剧本事件：预留，现阶段全双工对话剧本不使用
- `ScriptEventFull` 包含，但 `ScriptEvent`（= `ScriptPerformEvent`）不包含

#### ScriptEvent 联合类型（TypeAlias）
- `ScriptPerformEvent = Annotated[Union[FakePersonScriptEvent, VirtualCarPerformScriptEvent], Field(discriminator='event_type')]`
- `ScriptEvent = ScriptPerformEvent`（script_events 时间线：仅 perform 演绎）
- `ScriptEventFull` 包含 `EnvironmentScriptEvent`
- `VirtualCarScriptEvent = VirtualCarPerformScriptEvent | VirtualCarStateCheckScriptEvent`

---

## 5. 主体模型层

### 5.1 fake_person 模块

#### FakePerson（Class）
- 场景中的假人：人设 + 消费剧本事件 + 自主发言（LLM）
- 假人只持有角色自身字段：`role_id` / `profile` / `event_memory` / `state` / `intent`
- 演绎时由 runner 传入 prompt 上下文：`text_script` / `car_info` / `start_query` / `case_description` / `max_round` / `assistant_last` / `event_at`
- 多轮续聊的对话历史由 LangGraph checkpointer 按 `session_id` 在内存中保留（`InMemorySaver`）
- `perform()` 是对外唯一入口：验证 target 匹配 → 检查 action_type → `_speak` 内部完结
- `_speak`: `args.content` 不为 `None` 返回固定台词；为 `None` 调 `_llm_speak` 由 LLM 生成
- `_llm_speak` 使用 `create_agent(model, checkpointer, system_prompt)` 创建 LangGraph agent，`ainvoke` 传入 `[("user", user_input)]`（assistant_last 为空时用占位文本），重试 `external_api_max_retries` 次
- 假人不支持 state_check：`_STATE_CHECK_UNSUPPORTED_MSG` 明确说明
- 默认 model 从 `projects.mind.mem.auto_test_script.langchain_models` 导入 `doubao_model`

#### FakePersonAction（Class）
- 假人剧本动作（现阶段仅 speak；假人不做 state_check）
- `FakePersonActionKind.SPEAK = 'speak'`
- `FakePersonSpeakArgs`: `content: Optional[str]`（固定台词；None 表示自主发挥）
- `FakePersonSpeakPerformAction`: `action_type='perform'` / `kind=SPEAK` / `args`
- `FakePersonSpeakOutcome`: `kind` / `script_content` / `utterance`
- `FakePersonEventResult`: `role_id` / `event_at` / `outcome`

#### FakePersonPromptTemplate（Class）
- 渲染假人 LLM system prompt，由 auto_test `FAKE_DRIVER_PROFILE_TEMPLATE` 演进
- 模板变量：`profile` / `state` / `intent` / `event_memory` / `car_info` / `text_script` / `case_description` / `start_query` / `max_round`
- 使用 jinja2 `Template` 渲染
- **关键约束（纯剧本驱动）**：不要自己决定何时退下、不要打分、不要说"再见/拜拜"——何时结束由系统控制

#### FakePersonEventMemoryEntry / State / Intent（Class）
- `FakePersonEventMemoryEntry`: `content` / `occurred_at`（对齐火山 event_memory 语义）
- `FakePersonState`: `description`（自然语言一句话，不可穷举）
- `FakePersonIntent`: `description`（可选预设；不设置时由假人自行演绎）

### 5.2 virtual_car 模块

#### VirtualCar（Class）
- 虚拟车：devices 为唯一真相源，car_info 为只读派生视图
- 支持两种状态访问：
  - `devices: VirtualCarDevices` — 结构化设备状态（车控工具使用，真相源）
  - `car_info: dict` — 只读派生视图（假人 prompt / JSON 导出 / state_check 使用）
- `_init_from_car_info` 从旧格式 car_info 初始化 devices（仅在构造时调用一次，通过 `CAR_INFO_FIELD_MAP` 映射）
- 无 dict↔devices 双向同步（删除了旧版 `_update_car_info_from_devices`）
- 透传字段：无法预定义结构的自由元数据（如"当前位置"）存入 `_free_form_fields`
- 快捷属性：`driving` / `ac` / `seats` / `doors` / `media` / `navigation`
- `perform(event)`: 验证 `target='car'` → PERFORM 调 `_set_state` / STATE_CHECK 调 `_state_check`
- `_set_state`: fields 通过 `CAR_INFO_FIELD_MAP` 映射到 devices 字段（或透传到 `_free_form_fields`）
- `_state_check`: 从 devices 读出实际值（通过 getter），对比 `expected_fields`
- `car_info_text()` / `format_car_info()` 格式化为假人 prompt 可读多行文本
- `set_field(key, value)` / `get_field(key)`：车控工具专用接口

#### CAR_INFO_FIELD_MAP（Constant）
- `dict[str, tuple[setter, getter]]` 映射表（2026-08-27 大扩展，69 字段，覆盖面对齐车控标签树）
- 行驶与能源：`车辆当前行驶速度` / `车辆当前档位` / `手刹状态` / `车辆点火状态` / `驾驶模式` / `剩余续航里程（新能源车）` / `电池电量` / `充电状态`
- 空调：`空调开启状态及模式` / `空调温度` / `车内温度` / `车外温度` / `空调风量` / `空调风向`（吹脸/吹脚/吹脸和脚/自动）
- 座椅与方向盘：四座（主驾/副驾/二排左侧/二排右侧）× `座椅加热`/`座椅通风`/`座椅按摩`/`座椅模式`（零重力/标准）+ `方向盘加热`
- 乘员：四座 `是否有人` + `主驾安全带` / `副驾安全带`
- 门窗与天窗：四座 `门状态` + `后备箱状态` + 四座 `车窗`（开合度）+ `天窗状态` / `遮阳帘开合度`
- 灯光：`主驾阅读灯` / `副驾阅读灯` / `阅读灯亮度` / `氛围灯` / `氛围灯颜色` / `氛围灯亮度` / `氛围灯模式` / `大灯模式`
- 媒体：`多媒体播放状态`（播放中/暂停中/停止中）/ `正在播放的歌曲名` / `正在播放的歌手名` / `正在播放的歌单名` / `音源` / `音量`
- 导航：`导航状态` / `导航目的地`
- 车载电器：`车载电视` / `车载冰箱` / `冰箱温度` / `冰箱模式`（冷藏/冷冻）
- 自由元数据 key（`FREE_FORM_KEYS`）：`当前位置` / `当前系统时间` / `中控屏幕状态（智能车重点）` / `语音助手唤醒词` / `空调状态`
- 解析函数：`_parse_speed` / `_parse_gear` / `_parse_ac_state` / `_parse_temp` / `_parse_level` / `_parse_open_percent` / `_parse_bool` 等

#### CAR_INFO_GROUPS（Constant）
- `dict[str, list[str]]`：car_info key 的展示分组（有序，九大分组：行驶与能源/空调/座椅与方向盘/乘员/门窗与天窗/灯光/媒体/导航/车载电器）
- 随 case_started 事件的 `car_state_groups` 字段下发前端，CarStatePanel 据此分层分组展示
- 键名与用例生态词汇对齐（如"导航目的地""冰箱模式"取自真实 case 数据 car_info 词表）

#### VirtualCarDevices（Class）
- 虚拟车所有设备状态汇总（2026-08-27 扩展，覆盖面对齐车控标签树）
- 包含：`driving` / `ac`（含 air_direction 风向）/ `seats`（4 座 dict：加热/通风/按摩/模式/乘员占用/安全带）/ `doors`（6 门 dict）/ `windows`（4 窗 dict 开合度）/ `sunroof`（天窗+遮阳帘）/ `interior_light`（阅读灯+氛围灯）/ `exterior_light` / `media`（三态播放/歌曲/歌手/歌单/音源/音量）/ `navigation` / `steering_wheel`（方向盘加热档位）/ `tv`（车载电视）/ `fridge`（车载冰箱温度/模式）
- `to_car_info_dict()` 转换为 car_info 字典格式（兼容旧接口）
- 各类设备枚举：
  - `ACMode`: OFF / COOLING / HEATING / VENTILATION / AUTO；`ACAirDirection`: 吹脸/吹脚/吹脸和脚/自动
  - `ACFanLevel`: 0-4
  - `SeatHeatLevel`: 0-3
  - `SeatMassageMode`: 轻柔/舒缓/活力；`SeatPositionMode`: 标准/零重力
  - `MediaPlaybackStatus`: 播放中/暂停中/停止中
  - `DoorState`: 4 种
  - `WindowState`: 3 种 + 开合度百分比
  - `LightMode`: 5 种；`AmbientLightMode`: 常亮/呼吸/流动/随音乐律动
  - `Gear`: P / R / N / D / S；`ChargingStatus`: 充电中/未充电/充电完成
  - `FridgeMode`: 冷藏/冷冻

---

## 6. Runner 核心框架层（case_runner 模块）

### 6.1 CaseRunner（Class）— 主调度器
- 执行流程：
  1. `_init_session`: 初始化 FakePerson / VirtualCar / TraceRecorder / TimelineEngine / EventScheduler / TestedAssistant
  2. `_share_virtual_car_with_assistant`: 通过 `assistant.virtual_car = car` 共享 VirtualCar 实例
  3. `_build_scheduled_events`: 合并 script_events + state_check_assertions → ScheduledEvent 列表
  4. `scheduler.schedule_batch(events)` + `scheduler.run()` 启动主循环
  5. 事件就绪时回调 `_execute_event` 分发执行
  6. 返回 `RunResult`
- `run(case, t0)` 执行单个 TestCase
- `trace` 属性：暴露 `TraceRecorder`，供外部（Judge / demo）构造评判输入
- `_execute_event`: 根据事件类型分发到 `_execute_fake_person_event` / `_execute_virtual_car_perform` / `_execute_virtual_car_state_check`
- `_maybe_accelerate(target_time)`: 锚点距 mock_time > 阈值时快进——先 `aupdate_context(current_time=target)` 通知助手（主动智能测试核心），返回主动话语则记 trace，再 `timeline.accelerate_to(target)` + `trace.record_acceleration`；多步快进查 `get_pending_scheduled_tasks()` 在中间触发点逐个停靠
- `_execute_world_tick`: WorldTick 锚点到达——先 `_wait_assistant_idle` 等助手通道空闲；`_has_tasks_near_now()` 无待触发任务则**静默跳过**（迟到锚点，任务已被多步快进停靠先触发，2026-08-25）；否则先记 `[系统事件]` 系统记录，再 `_drain_pending_tasks_near_anchor` 推进 5s 缓冲触发到期任务（过期任务 gap ≤ 0 立即触发）
- `_handle_context_update`: 处理 `ContextUpdateResult`——主动话语记 trace + 注入 WorldTick 合并进事件队列（`original_index=-1`）
- `_execute_fake_person_event`: 假人说话（固定台词或 `_fake_person_llm_speak`，事件流携带 speak_start/text_delta/speak_done）→ 记 trace（话语区间 = started_at → ended_at，含 chunk 级 segments，经 `wall_to_mock` 换算）→ 第一个字即投（第一个 `text_delta` 就 `_spawn_stream` 启动后台流任务，后续字实时推入输入队列，中立观察者：不因插话打断助手）
- `_spawn_stream` / `_wait_assistant_idle`: 即时投喂——每句已说完话语对应一个后台流任务（`_active_stream_tasks` 集合跟踪，可并发）；时间推进（快进/WorldTick）前等所有活跃流任务收完（助手通道空闲）
- `_fake_person_llm_speak`: 构造 content=None 的 FakePersonScriptEvent 触发 LLM 自主发挥
- `_assistant_chat` / `_assistant_chat_streaming`: 调用助手，支持超时；流式版消费 `AssistantEvent` 事件流计算 TTFT / 检测文本流内 >2s 停顿（工具边界间隙不算——工具执行+LLM 围绕工具的思考是正常节奏）/ 记录工具调用 / 收集 chunk 级 segments（中立观察：不因锚点打断，超时截断时才记 is_partial 半截话）
- `RunResult`: `case_id` / `case_name` / `started_at` / `finished_at` / `trace_summary` / `must_pass_assertions` / `bonus_assertions` / `state_check_passed` / `error`

### 6.2 RunnerConfig（Class）
- `fake_person_timeout: float = 30.0` — 假人 LLM 调用超时
- `assistant_timeout: float = 60.0` — 助手回复超时
- `use_streaming: bool = True` — 是否使用流式回复
- `external_api_max_retries: int = 2` — 外部 API 重试次数
- `fast_mode: bool = False` — 测试模式：跳过锚点事件的真实时间等待
- `enable_acceleration: bool = True` — 是否启用时间加速（§2.6）
- `acceleration_threshold: Optional[timedelta] = None` — 快进阈值（None 时用默认 60s）

### 6.3 EventScheduler（Class）— 事件调度器
- 生产级：heapq 优先队列 + asyncio.Event 零轮询 + 动态插入
- 核心机制：`_wakeup_event`（asyncio.Event） + `_heap`（最小堆） + `_shutdown_flag`
- `EventSource`: `ANCHOR` / `BOUNDARY` / `STATE_CHECK`
- `ScheduledEvent`: `sort_key` / `event` / `source` / `original_index` / `anchor_time`
  - sort_key：边界事件用 `(t0, original_index)`，锚点事件用 `(t0+delta, original_index)`
  - `from_event(event, t0, original_index)` 工厂方法
- `schedule_batch(events)` 批量加载；`schedule_one(event, immediate)` 运行时动态插入
- `set_on_execute(callback)` 注册事件就绪回调
- `__init__` 参数：`fast_mode` / `acceleration_threshold: Optional[timedelta]`
  - `acceleration_threshold` 不为 None 时，锚点距当前真实时间 > 阈值则跳过真实等待（Runner 的 `_maybe_accelerate` 处理快进逻辑）
- 打断信号机制已删除（2026-08-25 中立观察者模型：锚点 `_anchor_due_event` / `wait_next_anchor_due()` 等不再存在，调度器不为打断服务）
- `run()` 主循环：
  - 边界事件立即执行
  - 锚点事件等待到 `anchor_time`（`asyncio.wait_for` + `_wakeup_event`）
  - `fast_mode=True` 或 `acceleration_threshold` 命中时跳过真实时间等待
  - 无事件时等待 shutdown 或新事件插入
- `shutdown()` 通知退出

### 6.4 TimelineEngine（Class）— 时间引擎（自然流逝模型，2026-08-25 重构）
- 内部只存一个锚点对 `(anchor_mock, anchor_wall)`；`mock_time` 属性实时计算：`anchor_mock + (now - anchor_wall)`
- 虚拟时间与真实时间 1:1 连续自然流逝（助手回复 / 假人说话 / LLM 生成期间时间照常走）
- `accelerate_to(target)`: 快进到目标时间（**唯一**的时间跳跃方式），重新锚定 `(target, now)`，记录 `(from, to)` 到 `accelerations`
- `pin_to(target)`: 调度器真实等待锚点存在毫秒级误差时，容差内（5s）对齐让时间戳干净
- `wall_to_mock(wall)`: 把事件流携带的真实时间戳换算进虚拟时间线（1:1 流逝期间双向换算）
- 已删除：`advance_to`（冻结-推进模型）、`record_activity` / `should_accelerate`（静默检测由事件队列判定取代）
- **已集成**：`Runner._maybe_accelerate` 在锚点距 mock_time > 阈值时调用 `accelerate_to` + 通知助手

### 6.5 DialogueManager（Class）— 对话管理器
- 职责：协调假人说话和助手回复的时序
- `boundary_detector: BoundaryDetector`
- `run_one_turn(user_text, assistant_chat_fn)`: 执行一轮：用户说话 → 助手回复 → 触发边界

### 6.6 BoundaryDetector（Class）
- `on_assistant_speak_start()` / `on_assistant_speak_end()`: 标记助手说话状态
- `wait_for_boundary(timeout)`: 等待边界触发（助手说完）
- 现阶段规则（简单版）：助手说完一句话即触发边界

### 6.7 TraceRecorder（Class）— 轨迹记录器
- 内部存储：`list[tuple[datetime, RecordKind, Any]]`
- `RecordKind`: `FAKE_PERSON_SPEAK` / `ASSISTANT_REPLY` / `VIRTUAL_CAR_SET_STATE` / `VIRTUAL_CAR_STATE_CHECK` / `ACCELERATION` / `SYSTEM` / `TOOL_CALL` / `TOOL_RESULT` / `LONG_PAUSE`（INTERRUPT 已删除；中立观察者模型下 `is_partial` 仅超时截断出现）
- `record_utterance(role, content, kind, started_at, ended_at, is_partial, ...)`: 记录发言（区间化，started_at/ended_at 必填，可携带 chunk 级 segments）
- `record_state_check(at, result)`: 记录状态检查
- `record_set_state(at, updated_fields)`: 记录车态 set_state
- `record_acceleration(from_time, to_time)`: 记录快进
- `record_system(at, content)`: 记录系统事件（如 WorldTick 锚点到达）
- `get_slices()`: 按时间分组为 `TraceSlice` 列表
- `get_utterances()`: 获取所有发言记录（按时间顺序）
- `get_state_checks()`: 获取所有状态检查记录
- `get_overlaps()`: 检测假人与助手话语的重叠窗口（区间交集），返回 [(窗口起点, 窗口终点, 假人话语, 助手话语), ...]（2026-08-25）
- `records` 属性：暴露全部原始记录（供测试提取系统事件）
- `summary()`: 生成 trace 摘要供 Judge 使用（含 dialogue_text / state_check_details / has_overlapping_speech / overlap_count）

#### UtteranceRecord（Class）
- 一次发言记录（区间化：开口 started_at → 说完 ended_at）
- 字段：`role` / `content` / `is_partial`（仅超时截断）/ `started_at` / `ended_at`（必填，区间化）/ `speech_duration`（说话时长）/ `ttft`（首字延迟）/ `is_proactive`（是否主动话语）/ `segments`（chunk 级时间戳 [(时刻, 文本增量), ...]，支撑重叠说话渲染切片）
- `role` 格式：`"fake_person:<role_id>"` 或 `"assistant"`

#### StateCheckRecord（Class）
- 字段：`expected_fields` / `actual_fields` / `passed` / `mismatches`

#### TraceSlice（Class）
- 时间切片：某一时刻的所有事件
- 字段：`at` / `records: list[UtteranceRecord | StateCheckRecord]`

### 6.8 AssistantProtocol（Protocol）— 助手接入协议
- `@runtime_checkable`，类比 auto_test 的 `AnyBotToTest`
- `create(session_id, system_prompt="")` — 创建/重置会话
- `achat(user_text) → str` — 非流式对话
- `achat_stream(user_text) → StreamingReply` — 流式对话，事件流版本产出 `AssistantEvent`
- `aupdate_context(car_info, current_time=None) → ContextUpdateResult` — 通知外部上下文变化（车态 + 时间推进）；返回 `ContextUpdateResult(proactive_text, injected_events)`（`assistant_protocol.py` 定义）
- `adump_history() → list[dict[str, str]]` — 导出对话历史供 Judge
- `is_assistant(obj)` 类型检查工具

### 6.9 StreamingReply（Class）— 流式回复
- 内部用 `asyncio.Queue[AssistantEvent]` + `asyncio.Lock` 保证线程安全（事件流协议 v2：队列元素从 `str` 升级为 `AssistantEvent`，携带 wall_time；`put_chunk` / `stream_text` 保留兼容旧版）
- `put_chunk(chunk)`: 生产者放入文本片段（内部包装为 TEXT_DELTA 事件）
- `put_event(event)`: 生产者放入 AssistantEvent（TEXT_DELTA / TOOL_CALL / TOOL_RESULT）
- `finish()`: 标记完成，放入哨兵
- `interrupt()`: 取消推理、保存已说部分为半截话（调 `anyio.CancelScope.cancel()`）；中立观察者模型下框架**不因插话调用**，仅流卡死超时的基建兜底使用
- `stream()`: 消费者异步迭代获取事件，遇到哨兵停止
- `is_done` / `is_interrupted` / `collected_text` 属性

### 6.10 Judge（Class）— 终局评判（独立模块 judge/）

> Judge 独立于 Runner，位于 `judge/` 目录（与 `fake_person/` 同级），Runner 不调 Judge。Runner 只跑出 trace，Judge 是独立步骤，可单独迭代/切换模型，可多个 Judge 评判同一 trace，失败 case 也可能有 trace 供 Judge 评判。

- `Judge(model, external_api_max_retries, judge_format_max_retries)`: 构造器，model 默认从 `langchain_models.doubao_model` 懒加载
- `ajudge(judge_input) → JudgeVerdict`: 异步评判
- `judge(judge_input) → JudgeVerdict`: 同步包装（`asyncio.run`）
- prompt 只含读懂 trace 的机制常识：时间快进不是剧情断裂、双方同时说话是中立观察者如实记录、半截话成因区分（插话打断=正常机制 / 超时截断=回复未在时限内完成）、快进后无假人说话时助手开口=主动开口机制、state_check 已自动判定不重复评；行为对错不写死在 prompt（2026-08-26 裁判中立原则：评判标准完全以断言为准，由守护测试 `test_judge_prompt_neutral_no_hardcoded_verdict_rules` 保障）；裁判价值观对齐假人（从假人视角评判）
- 输出 JSON 格式 + 格式重试容错（`judge_format_max_retries`）+ 外部 API 重试（`external_api_max_retries`）
- 解析失败兜底：返回 `JudgeVerdict`（所有断言判 false，`raw_response` 保留原始 LLM 回复）
- **`overall_passed` 以打分结果为准**：LLM 返回的 `overall_passed` 不覆盖打分结果（因为 LLM 可能未正确处理 state_check 失败）
- 与 auto_test 旧 Judge 的关系：参考重试/容错结构，但重写 prompt（旧看平铺对话字符串，新看带时间线 trace）+ 输出结构化（旧 `tuple[bool, str]`，新 `JudgeVerdict`）

#### 打分公式（`compute_score` 函数）
- 必过项任一不过（含 state_check 失败）→ 0 分
- 必过全过 + 无加分 → 满分 100
- 必过全过 + 加分全过 → 满分 100
- 必过全过 + 加分全没过 → 及格分 60
- 必过全过 + 加分部分过 → `60 + 40 * (bonus_passed / bonus_total)`
- 及格线：`score >= 60`
- `PASS_SCORE=60.0` / `FULL_SCORE=100.0` / `BONUS_RANGE=40.0` 写死为常量（不抽配置，§0.2 简单优先）

#### AssertionType（Enum）
- `MUST_PASS = "must_pass"` — 必过断言
- `BONUS = "bonus"` — 加分断言

#### JudgeInput（Class）
- Judge 的输入：`case_id` / `case_name` / `case_description` / `timeline_text` / `must_pass_assertions` / `bonus_assertions` / `state_check_summary` / `assistant_history` / `fake_person_profiles`
- `timeline_text` 是已渲染好的带时间线高可读字符串（由 `render_timeline_text` 生成）
- `state_check_summary` 含 `state_checks_passed` / `state_checks_failed`（已自动判定，算必过项，Judge 不重复评）
- `assistant_history` 可选，由 `AssistantProtocol.adump_history()` 导出
- `fake_person_profiles` 假人人设列表，注入 prompt 让裁判对齐假人价值观（§0.13）

#### JudgeVerdict（Class）
- Judge 的输出：`case_id` / `overall_passed` / `score` / `score_breakdown` / `assertion_results` / `summary` / `judged_at` / `raw_response`
- `overall_passed`：以 `score_breakdown.passed` 为准（不取 LLM 返回值）
- `score: float`：0-100，由 `compute_score` 计算
- `score_breakdown: ScoreBreakdown`：打分明细
- `assertion_results: list[AssertionResult]`：每条断言的评判（含 `assertion_type`）
- `raw_response`：解析失败时保留原始 LLM 回复（便于诊断），成功时为 None

#### ScoreBreakdown（Class）
- 打分明细：`must_pass_total` / `must_pass_passed` / `bonus_total` / `bonus_passed` / `state_check_total` / `state_check_passed` / `score` / `passed`
- state_check 计入必过项总数（combined）

#### AssertionResult（Class）
- 单条断言的评判结果：`assertion` / `assertion_type` / `passed` / `reasoning` / `evidence`
- `assertion_type`: `AssertionType.MUST_PASS` 或 `AssertionType.BONUS`
- `evidence`：引用 trace 中的关键事件片段（如 "T0+3s 助手: 好的，已为您打开空调"）

#### render_timeline_text（Function）
- 把 `TraceRecorder` 渲染成带时间线的高可读文本，是 Judge prompt 的核心输入
- 区间化渲染（2026-08-25）：话语 `[T0 + Xs → T0 + Ys] 角色: xxx`（开口 → 说完）；`[T0 + 45s] [状态检查] ... [✓ 通过]`；`[T0 → T0+7d] 时间快进`
- 重叠窗口块：`━━━ 双方同时说话 [起点 → 终点] ━━━` + 块内双方在窗口内实际说出的文字（基于 segments 切片，不完全重叠只标重叠部分）
- 工具调用配对合并：TOOL_CALL + TOOL_RESULT 合并为单条区间记录（`[工具] 名称 调用 → 返回 (耗时 Zs)`）
- 主动话语标注 `(主动, 触发后 X.Xs 开口)`；被动回复标注 `(首字延迟 X.Xs)`；说话时长 `(说了 X.Xs)`；流式停顿 `⚠ 流式停顿`；超时截断才标 `（半截话）`
- 空白字符偏移量用 `_format_offset` 简化（如 `30s` / `7d` / `1h30m`，毫秒级四舍五入防进位错误）

#### build_judge_input_from_run_result（Function）
- 便捷工具：从 `TestCase` + `TraceRecorder` + `RunResult` + 可选 `assistant_history` 构造 `JudgeInput`
- 自动调用 `render_timeline_text` 渲染 trace
- 从 `run_result` 取 `must_pass_assertions` / `bonus_assertions`（不直接读 case，以运行后状态为准）
- 从 `run_result.trace_summary` 提取 `state_check_summary`

---

## 7. 被测助手实现层（demos 模块）

### 7.1 TestedAssistant（Class）— 参考实现
- 实现 `AssistantProtocol`，基于 aicore v2 `ReactAgentWithTaskRunner`（直接用 `agent.astream`，不用 `AgentRunner` 常驻模式）
- `__test__ = False`：避免 pytest 误收集（类名以 `Test` 开头）
- `__init__(virtual_car, model, system_prompt, chat_id="time-travel-demo")`: 持有 VirtualCar 实例（由 Runner 共享）；model 默认 `ModelName.SEED_1_8_251228`；`chat_id` 用于天气工具初始化（默认 worker 强制要求）
- `create(session_id, system_prompt)`: 重置会话，清空 history，置空 `_agent` 等待懒加载
- `achat(user_text)`: 非流式，迭代 `agent.astream(user_text)` 收集 `event.delta/text` 拼接返回
- `achat_stream(user_text)`: 流式，创建 `StreamingReply` + `asyncio.create_task` 异步生产；生产者用 `anyio.CancelScope` 包裹，`reply._cancel_scope = cs` 持有，`StreamingReply.interrupt()` 调 `cs.cancel()` 真正取消推理
- `aupdate_context(car_info, current_time=None) → ContextUpdateResult`: 检查 `ScheduledTaskManager` 到期任务 → 注入系统消息触发 Agent 生成主动话语（`proactive_text`）；收集待注入 WorldTick 锚点（`injected_events`）；已删除旧版 `offset_recent_tasks` 偏移修正（自然流逝模型下 trigger_time 天然正确）
- `set_time_source(get_now)`: 接受 Runner 注入的实时虚拟时间源（`timeline.mock_time`），助手侧工具（`set_reminder`）取当前虚拟时刻
- `_translate_event(event)`: 把 v2_agent 原生事件（`AgentOutTextDeltaEvent` 等）翻译为统一 `AssistantEvent`（L0→L1，事件流协议核心）
- `adump_history()`: 导出 `list[dict[str, str]]`
- `_ensure_agent()`: 懒加载 `ReactAgentWithTaskRunner`，工具包括 `VirtualCarControlTool`（car_control）/ `NavigationControlTool`（navigation）/ `MediaControlTool`（media）/ `weather_search_v2_tool(chat_id=...)` / `poi_search_v2_tool` / `qq_music_song_search_v2_tool` / `create_task_cancel_tool`；`ambient_context_provider` 用 `render_active_task_context(task_manager)` 注入活跃任务状态
- `_extract_text(event)`: 模块级辅助函数，从事件取 `delta` 或 `text`，非文本事件返回空串
- `DEFAULT_SYSTEM_PROMPT`: 友好车载助手 + 三工具约定（car_control 车控 / navigation 导航 / media 媒体，导航媒体为独立工具非车控）+ 7 条异步回执约定（占位回执 / 工具结果回灌 / pending 规则 / cancel_task 用法等，从 `TimeTravelSUTAgent` 合并而来）
- 10 个单元测试（`test_tested_assistant.py`）：用 `MockAgent` 替换 `create_react_agent_with_task_runner`，monkeypatch 4 个业务工具工厂避免真实 API 初始化，`VirtualCarControlTool` 走真实链路

### 7.2 v2_agent_to_test 模块（参考实现入口）
- `__init__.py` 公开导出 `TestedAssistant` / `DEFAULT_SYSTEM_PROMPT`
- 底层依赖 aicore v2：
  - `create_react_agent_with_task_runner(model, tools, system_prompt, max_turns, ambient_context_provider)`: 工厂函数
  - `render_active_task_context(task_manager)`: 渲染活跃任务上下文
- 基于 aicore v2 ReAct Agent，支持实时流式响应 + 异步工具调用 + 打断取消（`anyio.CancelScope`）

### 7.3 VirtualCarControlTool（Class）
- 虚拟车车控工具，与 `projects/mind/toolset/car_control.py` 接口一致，但操作虚拟车状态
- `VirtualCarControlInput`: `command`（自然语言描述）
- `VirtualCarControlOutput`: `status` / `message` / `observation`
- `VirtualCarController.execute(command)`: 分类处理（空调/座椅/门窗天窗/灯光/车载电器/档位手刹等车载设备）→ 解析指令 → 更新 devices
- **导航/媒体已拆分（2026-08-28）**：不再是车控分支，由独立工具承接（见 §7.3.1 / §7.3.2）
- 安全检查：行驶中（`speed_kmh > 0`）无法执行门窗操作
- 工厂函数 `VirtualCarControlTool(virtual_car)` 使用 `aicore.create_tool` 创建名为 `car_control` 的工具
- 新版 VirtualCar 的 devices 是真相源、car_info 是只读派生视图，无需手动同步

### 7.3.1 NavigationControlTool（Class，demos/v2_agent_to_test/tools/navigation_control.py）
- 虚拟车导航独立工具（非车控），对齐 aicore `sgm_tools_v2.navigation_v2_tool` 接口（name="navigation"）
- `NavigationControlInput`: `command`（自然语言导航指令）
- `NavigationControlOutput`: `status` / `message` / `observation`
- `NavigationController.execute(command)` 复用真实导航核心 `projects.sgm_prod.tools.Navigation.NavigationWorker`（火山 FC，与 `navigation_v2_tool` 同底层）→ 解析返回 `functions` 中「单目的地导航/多目的地导航」的 `params[].destination` → 写入 `导航目的地` / `导航状态`；取消导航（取消/停止/退出/关闭清空状态）→ 查询（返回当前状态不改状态）；worker 可注入（单测用 FakeNavWorker 免网络）
- 同样走 `VirtualCar.set_field` 落盘（devices 真相源 → on_field_change → car_set_state 事件）

### 7.3.2 MediaControlTool（Class，demos/v2_agent_to_test/tools/media_control.py）
- 虚拟车媒体独立工具（非车控），对齐 aicore `sgm_tools_v2.media_v2_tool` 接口（name="media"）
- `MediaControlInput`: `command`（自然语言媒体指令）
- `MediaControlOutput`: `status` / `message` / `observation`
- `MediaController.execute(command)` 顺序：切歌拒绝（下一首/上一首——虚拟车无歌单队列，诚实返回 error 不编造歌曲）→ 查询播放状态（纯疑问不改状态）→ 播放控制（暂停/停止/继续/播放）+ `_parse_track` 点歌（"播放周杰伦的晴天"→歌手+歌曲；"播放歌单XX"→歌单；泛化词"音乐/歌"不点歌）→ 音量（N%设定/调大调小±10，clamp 0..100）→ 音源切换（蓝牙/在线/收音机/USB）
- 写入 `多媒体播放状态` / `正在播放的歌曲名/歌手名/歌单名` / `音量` / `音源`，同样走 `VirtualCar.set_field` 落盘
- 19 个单元测试（`test_navigation_media_tools.py`）：导航 6 + 媒体 10 + 工厂 3，真实 VirtualCar 链路无 LLM 依赖

### 7.4 run_e2e_demo 模块（端到端真实 LLM demo）
- `demos/run_e2e_demo.py`：完整链路 demo（TestedAssistant + CaseRunner + Judge）
- 7 种 case 来源：`--case builtin`（开空调+state_check）/ `builtin-accel`（跨天时间加速）/ `llm-speak`（假人 LLM 自主对话）/ `interrupt`（全双工打断）/ `scheduled`（定时任务不跳过）/ `complex`（插话打断+定时任务+快进+记忆+恢复轮综合）/ `fixture --case-id case-001`
- 命令行开关：`--no-judge`（跳过评判）/ `--no-streaming`（关闭流式）/ `--fast-mode`（跳过锚点真实等待）/ `--show-prompt`（打印 Judge 完整 prompt）
- Windows 兼容：强制 `sys.stdout` / `sys.stderr` 为 UTF-8，避免 GBK 无法打印 ✓/✗
- Runner 暴露 `trace` 属性，demo 直接用 `runner.trace` + `build_judge_input_from_run_result` 构造 JudgeInput
- 真实 LLM 已验证（2026-08-25，自然流逝模型重构后）：scheduled case（定时任务不跳过 + 主动提醒 + 跨时记忆）与 complex case（插话打断 + 双指令 + 35 分钟定时 + 快进 + 恢复轮）均 Judge 100/100

### 7.5 scheduled_tasks 模块（定时任务管理，demos/v2_agent_to_test/tools/scheduled_tasks/）
- `manager.py`: `ScheduledTaskManager`（`add_task` 自动记录 WorldTick 注入时间 = trigger_time - 5s；`get_pending_scheduled_tasks(current, target)` 供 Runner 多步快进查询；`get_due_tasks(current_time)` 返回到期任务）+ `ScheduledTask`（task_id / trigger_time / description / triggered）
- `tool.py`: `set_reminder` 工具（供被测 Agent 调用；通过 `set_time_source` 注入的时间源取当前虚拟时刻，trigger_time 天然含回复耗时）
- `WORLD_TICK_BUFFER = 5s`：WorldTick 锚点缓冲常量

---

## 8. 可视化层（visualizer 模块，M1 实时模式）

### 8.1 EventBus（Class）— 旁路事件总线
- 位于 `visualizer/event_bus.py`，双时间戳事件信封：`seq`（总线序，严格递增）/ `wall_time`（真实墙钟）/ `mock_time`（虚拟时间，回放模式坐标系）/ `kind` / `payload`
- 单订阅者模型（`subscribe(handler)`）：无订阅者时 `emit` 零开销（seq 不推进、信封不构造）——中立观察者原则，事件采集不参与执行决策
- **信封时间不变式**（2026-08-26 端到端联调发现并修复）：seq 递增序下 `mock_time` 不倒退（快进只会向前跳）——层1 utterance 落盘事件信封时间用 `ended_at`（落盘时刻）而非 `started_at`（话语进行中的 delta 事件已携带更晚时间）；`case_finished` 信封携带当前虚拟时间
- 支撑实时模式（按真实时间消费）与回放模式（按虚拟时间消费，M2）两套坐标系

### 8.2 三层事件
- **层1（TraceRecorder 落盘即推）**：utterance / state_check / car_set_state / acceleration / system / tool_call / tool_result / long_pause——`TraceRecorder(event_bus=...)` 可选注入，各 `record_*` 方法旁路发射，不注入则行为与旧版完全一致
- **层2（Runner 过程事件）**：case_started（**payload 含 `initial_car_info` 全量初始车态快照**（VirtualCar 派生视图 69 字段，含未指定设备默认值）**+ `car_state_groups` 分组元数据**（CAR_INFO_GROUPS 九大分组，前端分层展示依据）**+ `script_plan` 剧本时间表**（2026-08-28：锚点驱动事件 {kind, at, target, label} 按时刻升序——假人说话/剧本改车态/状态检查；边界驱动事件无预设时刻不进入；前端时间线"未来区"预设事件竖线的数据源）——车态时间机初值）/ case_finished（含结果摘要）/ fake_person_delta / assistant_delta（chunk 逐字到达，打字机数据源）——`CaseRunner(event_bus=...)` 可选注入；run_server 另有 case_cancelled / run_error
- **层3（终局评判）**：judge_verdict——Judge LLM 分析完整轨迹后的评判结果（总分/打分明细/每条断言的通过情况与理由），评判失败时 payload 为 `{error: ...}`；**自动评判**（2026-08-28）：run_case 自然完成后 `RunContext._auto_judge` 自动触发（`auto_judge` 选项默认 true），结果经事件总线/泵推送（推送完毕由 _auto_judge 停泵）；**手动重评**：judge_case 命令仍可用，结果由 run_server 直接发到发起命令的连接（不走事件泵）
- 话语区间（started_at / ended_at / segments）在层1 utterance 的 payload 里，前端投影用 payload 区间而非信封时间
- **车态事件统一链路**（2026-08-27）：剧本 set_state 与助手车控 `set_field` 都发射 car_set_state——`VirtualCar.on_field_change` 钩子捕获助手车控字段变化（单字段增量事件），剧本多字段 set_state 走原有"多字段一条"格式（`notify_enabled` 抑制钩子）；配合 case_started 的 initial_car_info，前端可重建任意虚拟时刻的车全量状态
- **车态变更来源标注**（2026-08-28）：car_set_state 事件与 trace 落盘均携带 `source` 字段（`record_set_state(source=...)`）——剧本 set_state 路径 source="script"（上帝视角，金色）/ 助手车控钩子路径 source="assistant"（红色）/ "fake_person"（假人直接操作，蓝色，预留）/ None（旧事件流未知，中性）——前端 CarStatePanel 据此三色区分改动人

### 8.3 run_server（File）— FastAPI + WebSocket 服务器
- 位于 `visualizer/run_server.py`，单端口 8800：`GET /`（挂载 frontend/dist 静态文件）+ `GET /api/health` + `WS /ws`
- 命令-ACK 协议（对齐 v2_frontend，为语音测试预留多路复用）：上行 `list_cases` / `run_case`（case_id + assistant_kind + chunk_delay（假人逐字节奏）+ fast_mode + use_streaming + nav_tool_delay + auto_judge（默认 true，case 完成自动终局评判））/ `stop_case` / `judge_case`（对最近一次 run 重新终局评判）；下行 hello / event（事件信封）/ ack / error
- `RunContext`：一次 run 的执行上下文——bus.subscribe(queue.put_nowait) + runner 后台任务 + 事件泵（queue → ws.send_json）；全局互斥单 run（重复 run_case 拒绝）；连接断开自动停止后台执行；**case 自然结束/出错时在 `_run` finally 清全局 `_current_run`**（2026-08-27 修复僵尸 run——此前跑完后 `_current_run` 残留，后续 run_case 被永久拒绝）；run 完成后保留产物（case / runner.trace / run_result / assistant_history）供 judge_case 构造 JudgeInput
- **终局评判链路**（2026-08-27）：`_current_run`（运行中）与 `_last_run`（最近完成）双全局——judge_case 取 `_current_run ?? _last_run`（stop 后仍可评判半程轨迹）；`judge_ready` 判定产物齐备；评判任务经 `_judge_and_send` 直接 `ws.send_json` 发 judge_verdict 到发起连接（不走事件泵——case 自然结束后泵已停止，重连/stop 后泵绑定的连接可能已换）；评判进行中重复发起被拒；新 run / 断连时 shutdown 释放产物
- `_execute_judge`：模块级函数（构造 JudgeInput → `Judge().ajudge()` → `verdict.model_dump(mode="json")`），独立出来是为了 pytest 可 monkeypatch 注入假裁判（judge_case 测试不依赖真实 LLM）
- 内置 9 个 demo case（run_e2e_demo 的工厂函数：simple-ac / **god-view 剧本上帝视角改车态（混合来源：假人请助手开空调 source=assistant + 剧本 set_state 起步行驶 source=script，演示车态来源三色与未来区预设事件竖线）** / acceleration / time-awareness / llm-speak / interrupt / scheduled-task / complex-combo / navigation-multi-condition 多条件导航长耗时工具）
- assistant_kind：mock（默认，无 LLM 依赖）/ v2（真实接入层）；mock 为 `DemoToolMockAssistant`（继承 `case_runner.mock_assistant.MockAssistant`）——导航类指令模拟真实 ReAct 节奏（承接语 → TOOL_CALL 多条件参数 → nav_tool_delay 执行 → TOOL_RESULT 路线摘要 → 总结语 + 写车态），非导航指令走基类纯文本行为；nav_tool_delay 可由 run_case 选项覆盖（默认 6s）

### 8.4 frontend（React 19 + Vite 6 + TS 5.8 + vitest 3）
- 对齐 v2_frontend 技术栈与模式：事件即 action 的单一 `useReducer`（consoleReducer）扇出多投影
- 三栏布局：左 RunConsole / 中 ChatStream / 右纵向堆叠（TimelineLanes 上 + CarStatePanel 中 + VerdictPanel 下，`.right-column` flex 列；**面板高度用户拖拽调整**——PanelResizer 拖拽条 + CSS 变量 `--timeline-h`/`--car-h` + localStorage `ttat.rightColumnLayout` 持久化适配不同屏幕，VerdictPanel 吃剩余空间；**对话流与右栏观察区左右拖宽**（2026-08-28）——PanelResizer 扩展 `orientation` 属性（horizontal 纵向调高 / vertical 横向调宽 col-resize），CSS 变量 `--left-width` 下发对话流宽度（clamp 下限 480px，localStorage `ttat.layout` 持久化），`.app-stage` grid 窗口过窄时对话流自动收缩、右栏保底 360px 自适应）
- `adapters/visualizerClient.ts`：WS 客户端（命令-ACK + 事件流归一化；断线 reject pending 命令；未知 kind 中立保留为 unknown_event 不丢弃；`judgeCase()` 只等受理 ack，verdict 经 judge_verdict 事件异步返回）
- `domain/events.ts`：信封 → 强类型 `VisualizerEvent` 联合类型归一化；judge_verdict payload 平铺 snake_case → `JudgeVerdictData` camelCase（case_id/overall_passed/score/score_breakdown/assertion_results/summary；失败 payload `{error}` → verdict=null + error 文本）；case_started 归一化 `initial_car_info` → `initialCarInfo` + `car_state_groups` → `carStateGroups`（旧事件流缺失为 null）
- `app/consoleReducer.ts`：`JudgeState`（idle/pending/done/error + verdict + errorMessage）——judgeRequested→pending、judge_verdict→done/error、case_started/resetRun 重置为 idle；**case_finished 也置 pending**（2026-08-28 自动终局评判——后端 case 完成后自动起 _auto_judge，前端收到 case_finished 即显示"裁判正在评判…"，judge_verdict 事件到达转 done/error）；**`PlaybackState` 回放状态机**（mode: idle/paused/playing + cursorMs 游标 + speed 倍速）——case_started/resetRun 重置 idle（保留 speed）、case_finished/cancelled/run_error 切 paused（激活回放）、playbackScrub/Play/Pause/Speed/Tick 五动作（运行中 scrub 被忽略；tick 到 maxMs 钳制并自动暂停）；**live 缓冲记录开口时刻**——`liveFakePerson`/`liveAssistant` 为 `{text, startedAt}` 结构，首个 delta 的 mockTime 存为 startedAt（时间线 live 增长条的起点），utterance 落盘/生命周期结束清空
- `app/projections.ts`：纯函数投影——**双模式时间线刻度**（`buildTimeScale(events, t0, options: ScaleOptions)`——LiveScaleOptions {mode:'live', axisMs, windowMs, widthPx} / ReplayScaleOptions {mode:'replay', cursorMs, zoom, panX}；**live 滑动窗口**：轴线恒映射 x=0.5，窗口 [axis-半窗, axis+半窗] 线性映射随虚拟时间从右向左流动，基准 20s 经 `computeLiveWindowMs` 按轨道像素宽 25ms/px 自适应扩大（ResizeObserver 上报）；秒级网格线 `computeGridlines` 按 1-2-5 步长序列选档、落在整数倍刻度上随窗口流动（T0 原点线加粗、负时间标签带负号）；**replay 全程视窗**：normal 段按时长比例分宽 + acceleration 段压缩固定 6% 窄带（30s 对话与 5 天快进同轴共存）的全域分段映射后，经 zoom/pan 视窗变换——`zoomReplayView` 锚定游标缩放（游标在视窗内屏幕位置不动，在外锚定视窗中心不拽回）、`clampPanX` 钳制 [0, 1-1/zoom]、`followCursorView` 播放时游标滑出视窗自动平移居中、`domainX` 提供与视窗无关的全域归一化坐标（缩放锚点系）；`TimeScale.endMs` 轴终点 + `inverseX` 归一化位置反算虚拟毫秒（非线性段内线性插值，拖到快进带末尾=快进完成时刻）；**`clipSpanToView` 统一视窗裁剪**——完全窗外返回 null 不渲染、跨缘两端裁剪到 [0,1]、点事件给最小渲染宽度，live 与 replay 共用，`x()` 不钳位（窗外时间同样可映射）；**`projectTimelineSpans` 未来事件投影**——scriptPlan 中 at > axisMs 的预设事件 → tone=future 点事件（前端渲染半透明竖线随时间从右向左飞向轴线））+ **重叠说话窗口检测**（假人×助手话语区间求交）+ 对话流气泡（落盘权威记录 + 层2 delta 打字机，半截话区分"被插话打断/超时截断"；**`projectDialogue(state, cursorMs)` 回放裁剪**——未开始不显示、说到一半按 segments 拼接部分内容（status=speaking）、已完成全量显示、工具卡片结果未到显示"执行中"、live 打字机气泡不显示）+ long_pause 警示色（warn 琥珀色而非失败红——流式停顿是流畅度观察，不是失败）+ **相对 T0 虚拟时间区间**（`formatTimeRange`：气泡用 started_at/ended_at，工具卡片用 call→result 的 mock_time，渲染为"T+3.2s → T+8.7s"文本；无 t0 或 live 气泡为 null）+ **`projectCarState` 车态时间机**（初值 = case_started.initialCarInfo（69 字段全量），增量 = mock_time ≤ 游标的 car_set_state 按序合并；cursorMs=null 全量合并=实时最新状态；changedKey 标记游标处最近变化字段供高亮；**source 来源透传**（2026-08-28）——entry.source 携带字段最近一次变更来源、view.changedSource/changedAtMs 驱动前端三色闪烁）+ **`groupCarStateEntries` 分组投影**（按 car_state_groups 元数据把字段归入九大分组：元数据缺失回退单组"全部状态"、未声明字段进"其他"组兜底、各组 hasChange 标记供组头变化圆点）+ **`projectToolSpans` 工具子泳道投影**（tool_call×tool_result 栈式 LIFO 配对成区间 + **行打包算法**——按 call 时刻贪心分配并行工具到不同行（执行中条视为占满整行 Infinity 防后到并行条错分行）、已结束条按真实区间复用空闲行；cursorMs/nowMs 双模式尾随：实时执行中条右端尾随 nowMs、回放 call ≤ 游标 < result 尾随游标、游标未到 call 不显示；回填 resultText/durationMs/argsText）+ **`projectLiveSpans` live 增长条投影**（[首个 delta 开口时刻, now] 区间，缓冲清空后消失由权威 utterance 接管；nowMs=null 或回放模式返回空）
- `app/useNowTicker.ts`：实时虚拟时钟——信封双时间戳为外推锚点（最近携带虚拟时间的事件给出 (wall_time, mock_time)，`now = mock + (Date.now() - wall)`），100ms 定时器更新、事件到达自动重锚消除漂移、快进由 acceleration 事件把锚点跳到未来；running=false 返回 null；驱动时间轴伸长/live 增长条/执行中工具条推进
- **对话流时间快进标记**（2026-08-28，`projectDialogue` + ChatStream）：acceleration 事件解析为 `AccelerationEntry`（durationMs 快进时长 + timeRangeText "T+..s → T+..s" 区间），ChatStream 在对应位置渲染居中虚线圆角胶囊条（"⏩ 时间快进 X（T+..s → T+..s）"）——快进区间不再被误读为一直持续的对话；回放模式下 fromMs > cursorMs 的快进条不显示（与话语回放裁剪一致）
- `app/usePlaybackEngine.ts`：rAF 回放引擎——playing 时每帧 dispatch playbackTick（deltaMs = 真实dt × speed），单帧真实 dt 钳制 250ms（防 tab 切后台 rAF 停摆后恢复瞬间跳到结尾）；到 maxMs 由 reducer 自动暂停（effect 卸载）
- `components/`：六组件——RunConsole（case 列表/运行控制/被测助手 mock/v2 选择/运行摘要）+ ChatStream（话语气泡间混排工具卡片：工具名/参数/返回结果/耗时/执行状态/相对 T0 时间区间，从甩出调用到出结果全程可见；回放时对话流随游标倍速回放）+ TimelineLanes（泳道：假人 / **assistant-group（助手 + ↳ 工具子泳道组）** / 虚拟车 / 系统；工具子泳道为助手下层低一层级——橙色矮条（⚙ 名称 + ⟳ 执行中/✓ 完成）+ **call/result 时刻竖线伸进助手泳道底边**（直观关联何时开始调用/何时结束获得结果，竖线高度 = 行数×TOOL_ROW_STEP(24px) + 伸入深度 8px）、多工具并行走打包分行、执行中条右端脉冲动画尾随 nowMs/游标增长、hover 看 toolTooltip（入参/返回/耗时/区间）；**live 增长条**——正在说的话从开口时刻随时间不断变长的虚线脉冲条（span-live 动画），落盘后权威区间无缝接管；快进斜纹带、重叠高亮；**双模式渲染**（2026-08-28 推倒重写）——live 滑动窗口：中央时刻轴线（timeline-now-axis 金色发光竖线 + "现在 T+xx"标签）恒 x=0.5，秒级网格线（timeline-gridline，T0 原点加粗）随虚拟时间从右向左流动，右半未来区微弱冷色渐变；未来预设事件竖线（future-marker 金色，越接近轴线越亮）从右缘飞入、抵达轴线由真实事件接管；历史事件块从轴线生成向左移动滑出左缘（进行中的右端贴轴线增长），所有块经 clipSpanToView 视窗裁剪；replay 全程视窗：游标可拖拽定位（pointer capture + inverseX 反算非线性轴）、**横向缩放 ×1~×64（zoom-button 锚定游标）+ 底部平移滑块**（pan-slider，zoom=1 禁用）、播放中视窗自动跟随游标、新 run 重置 zoom=1；回放控制条（播放/暂停、倍速 1x/1.25x/1.5x/2x/3x/5x、当前时刻/总时长））+ CarStatePanel（虚拟车状态观察窗：**分层分组展示**——`<details>` 可折叠分组面板（默认展开，组头组名+字段数+最近变化琥珀圆点）按九大分组组织 69 字段，组内 CSS Grid 多列自适应（窄 1 列→宽 3 列）；最近变化字段琥珀高亮+变化时刻 tooltip，观察时刻随回放跳动；**变更来源三色 + 分组临时置顶**（2026-08-28）——字段被改动时按 source 三色加粗键值文字闪烁 1 秒（script=金色/assistant=红色/fake_person=蓝色/未知=琥珀），所在分组临时提到最顶展示 1 秒后恢复）+ VerdictPanel（裁判终局评判面板：开始/重新评判按钮、总分大数字+及格徽章、必过/加分/状态检查打分行、每条断言的 ✓/✗ + 裁判理由 + 证据列表、评判 pending/error 态）+ PanelResizer（面板间拖拽条：pointer capture 增量回调 + 中央抓握短横线，App 持久化到 localStorage；**orientation 双向**（2026-08-28）——horizontal 水平条 row-resize 调右栏三面板高度 / vertical 垂直条 col-resize 调对话流与右栏观察区宽度）
- 前端 vitest 65 个全通过（events 11 + client 4 + reducer 12 + projections 38；新增 script_plan/source 归一化、轴线居中重标定/axisMs=0 全右半/未来事件投影过滤/车态来源数据链/前瞻窗口）；dev 模式 vite 代理 → 5173，生产模式 `npm run build` 后单端口 8800
- 端到端联调通过（2026-08-26）：真实 uvicorn + WS 客户端跑 builtin-complex-combo（fast_mode=False，mock 助手）——119 事件流完整（delta×108 + utterance×6 + acceleration×2 + state_check + 生命周期），信封不变式成立
- 终局评判端到端验证通过（2026-08-27）：run builtin-simple-ac → judge_case → 真实 Judge LLM（doubao）返回 verdict——score 60（必过 2/2 + 加分 0/1 + 状态检查 1/1），summary 与每条断言 reasoning 完整，judge_verdict 事件直达发起连接

---

## 9. 测试层（test 目录）

### 9.1 fixture_cases.json（File）
- 位于 `test/cases/fixture_cases.json`
- 包含 12 个 fixture cases（case-001~012）覆盖所有场景类型：
  - case-001~007: 基础场景（case-001 含 `bonus_assertions` 用于打分测试）
  - case-008: 纯边界驱动，验证事件连续执行
  - case-009: 锚点抢占边界，打断 + 半截话保存
  - case-010: 快进触发，5 天静默后自动加速
  - case-011: 并发多 Actor，双假人同时说话
  - case-012: 状态检查失败，负向测试路径
  - case-007 示例 `t0='2025-01-03T18:00:00'`（周五晚上场景）
- 所有 case 已迁移到 `must_pass_assertions`（旧 `nl_assertions` 字段已移除）

### 9.2 pytest 测试（106 个全通过）
- `test_virtual_car_v2.py`（9 个）：VirtualCar 单元测试
  - 测试 devices 真相源、car_info 只读派生、CAR_INFO_FIELD_MAP 映射、set_state/state_check、free_form 字段
- `test_scheduler_v3.py`（6 个）：EventScheduler 单元测试
  - 测试边界事件顺序、锚点等待、边界优先于锚点、动态插入、fast_mode
- `test_case_runner_e2e.py`（22 个）：CaseRunner 端到端测试（用 MockAssistant，不依赖真 LLM）
  - 基础流程：case-001/004/008/012/007/010、流式模式、空 case
  - 剧本时间表（1 个）：`test_case_started_emits_script_plan` 验证 case_started 载荷含 script_plan（锚点驱动事件 {kind,at,target,label} 按时刻升序，边界驱动事件不进入）
  - 车态变更来源（1 个）：`test_car_set_state_source_script_vs_assistant` 验证助手车控 source="assistant" / 剧本 set_state source="script" 双路径标注正确
  - 时间加速（1 个）：`test_time_acceleration_triggers_aupdate_context` 验证锚点距 t0 > 阈值时快进 + `aupdate_context(current_time=target)` 被调用
  - 主动智能（2 个）：`test_proactive_intelligence_via_aupdate_context` 主动话语记入 trace；`test_proactive_utterance_timestamp_includes_ttft` 话语时间戳含开口延迟（trigger + ttft）
  - WorldTick（2 个）：锚点触发到期任务；迟到锚点静默跳过
  - 插话/打断（3 个）：插话重叠不打断（中立观察）、barge-in 中止旧流记半截话、重叠窗口渲染
  - 自然流逝（1 个）：回复期间虚拟时间照常走
  - 流式停顿语义（3 个）：工具执行间隙不算停顿、工具边界间隙（TEXT→TOOL_CALL / TOOL_RESULT→TEXT）不算停顿、文本流内真实停顿仍记录
- `test_case_schema.py`（5 个）：TestCase schema 测试
- `test_fixture_cases_json.py`（4 个）：fixture cases 导入/导出测试
- `test_judge.py`（27 个）：Judge 评判测试（用 MockModel，不依赖真 LLM）
  - 打分测试（8 个）：全过无加分 / 全过有加分 / 部分加分 / 必过失败 / state_check 合并 / 字段完整性
  - trace 渲染测试（5 个）：简单对话 / 快进+主动说话 / 打断+半截话 / 超时截断标记 / 空 trace
  - LLM 评判测试（10 个）：必过+加分通过 / 必过+加分失败 / 必过失败 / 无加分 / state_check 失败→0 分 / 主动智能 / 格式重试 / 全失败兜底 / 缺 overall 字段 / 同步包装
  - 数据模型测试（2 个）：JudgeInput 校验 / JudgeVerdict 序列化
  - prompt 内容测试（2 个）：验证时序语义、必过/加分、假人对齐；裁判中立（无写死行为对错规则）
- `test_tested_assistant.py`（12 个）：TestedAssistant 单元测试（用 MockAgent，不依赖真 LLM）
  - 协议实现测试（1 个）：`is_assistant` 通过
  - 非流式 achat（1 个）：完整回复 + history 累积
  - 流式 achat_stream（1 个）：完整文本 + done 状态
  - 流式打断（1 个）：interrupt 后立即停止，已收到部分保留
  - 接入层 barge-in（2 个）：第一个输入 chunk 即中止旧活跃流（半截话入 _history）；旧流已完成的轮次不受影响
  - VirtualCar 共享（1 个）：Runner 共享后车控工具可操作
  - 会话重置（1 个）：create 清空 history + 重置 agent
  - aupdate_context（1 个）：noop 不抛异常（含 `current_time` 参数）
  - DEFAULT_SYSTEM_PROMPT（1 个）：含占位回执 / 工具结果回灌 / pending / cancel_task / 车控约定
  - _extract_text（1 个）：跳过非文本事件
  - 多轮对话（1 个）：同 session 内 agent 复用 + history 累积
- `test_event_bus.py`（14 个）：事件总线 + 层1/层2事件发射测试
  - 信封结构（seq/wall_time/mock_time/kind）、无订阅者零开销、mock_time=None 容忍
  - TraceRecorder 8 种层1事件全覆盖（utterance 全字段 + 信封时间=落盘时刻 ended_at）
  - Runner 生命周期事件 + chunk delta 流（打字机数据源）+ 信封 mock_time 单调性不变式（回归断言）
  - case_started payload 含 initial_car_info 初始车态快照（车态时间机初值）
  - 助手车控 set_field 触发 car_set_state 事件（VirtualCar.on_field_change 钩子）
  - 剧本多字段 set_state 保持"多字段一条"事件（钩子被 notify_enabled 抑制）
  - 不注入 bus 时行为不变（向后兼容）
- `test_run_server.py`（7 个）：WS 服务器测试（真实 uvicorn 线程 + websockets 客户端，不用 TestClient）
  - hello + list_cases / 未知 case 拒绝 / run_case 事件流（case_started → utterance → case_finished + 运行后可再跑）/ 空闲 stop 幂等
  - judge_case：无已完成 run → rejected；run 完成后 → ack accepted + judge_verdict 事件直达本连接（monkeypatch `_execute_judge` 注入假裁判，不依赖真实 LLM）+ 可重复评判；评判抛异常 → payload 含 error（前端错误态）

### 9.3 MockAssistant（测试用）
- 位于 `case_runner/mock_assistant.py`（2026-08-27 从 test_case_runner_e2e.py 提取到生产位置——可视化服务器的 DemoToolMockAssistant 需要复用；测试文件改为导入）
- 不调 LLM，按预设规则回复（"开空调"→写 devices + 回复）
- 实现 `AssistantProtocol` 完整接口（含流式输入聚合 `_collect_input` 记录首/末 chunk 时刻）
- 用于验证 Runner 流程，不依赖真实 LLM

---

## 10. 实体关系总览

### 10.1 项目结构关系
- `time_travel_auto_test` **演进自** `auto_test_script`
- `time_travel_auto_test` **包含文档** `ARCHITECTURE.md` / `CONTEXT.md` / `KNOWLEDGE_GRAPH.md`
- `time_travel_auto_test` **包含模块** `case_schema模块` / `script_events模块` / `fake_person模块` / `virtual_car模块` / `case_runner模块` / `judge模块` / `demos模块` / `visualizer模块` / `test目录`
- `time_travel_auto_test` **核心机制** 双层演进机制 / 流式打断与半截话 / 时间加速 / 全双工对话 / 调度器回调模式 / 助手接入协议 / state_check断言 / 虚拟车set_state分工 / 打分机制 / 旁路事件总线

### 10.2 模块定义关系
- `case_schema模块` **定义** TestCase / FakePersonInfo / VirtualCarInfo
- `script_events模块` **定义** ScriptEventBase / FakePersonScriptEvent / VirtualCarPerformScriptEvent / VirtualCarStateCheckScriptEvent / EnvironmentScriptEvent / ActionType / ScriptEventType / ScriptEvent联合类型
- `fake_person模块` **定义** FakePerson / FakePersonAction / FakePersonPromptTemplate / FakePersonEventMemoryEntry / FakePersonState / FakePersonIntent
- `virtual_car模块` **定义** VirtualCar / VirtualCarDevices / CAR_INFO_FIELD_MAP / VirtualCarSetStateOutcome / VirtualCarStateCheckOutcome / VirtualCarEventResult
- `case_runner模块` **定义** CaseRunner / RunnerConfig / RunResult / EventScheduler / ScheduledEvent / EventSource / TimelineEngine / DialogueManager / BoundaryDetector / TraceRecorder / TraceSlice / UtteranceRecord / StateCheckRecord / RecordKind / AssistantProtocol / StreamingReply / AssistantEvent / FakePersonEvent / ContextUpdateResult / MockAssistant
- `judge模块` **定义** Judge / JudgeInput / JudgeVerdict / AssertionResult / ScoreBreakdown / AssertionType / compute_score / render_timeline_text / build_judge_input_from_run_result
- `demos模块` **定义** TestedAssistant / VirtualCarControlTool / VirtualCarController / NavigationControlTool / NavigationController / MediaControlTool / MediaController / DEFAULT_SYSTEM_PROMPT / _extract_text / build_builtin_case / build_builtin_case_with_acceleration / load_fixture_case / run_one_case
- `visualizer模块` **定义** EventBus / RunContext / visualizerClient / consoleReducer / projections / usePlaybackEngine / RunConsole / ChatStream / TimelineLanes / CarStatePanel / VerdictPanel
- `test目录` **包含** fixture_cases.json / test_virtual_car_v2.py / test_scheduler_v3.py / test_case_runner_e2e.py / test_case_schema.py / test_fixture_cases_json.py / test_judge.py / test_tested_assistant.py / test_navigation_media_tools.py / test_event_bus.py / test_run_server.py

### 10.3 类间核心关系
- `TestCase` **包含** FakePersonInfo / VirtualCarInfo / FakePersonScriptEvent / VirtualCarPerformScriptEvent / VirtualCarStateCheckScriptEvent
- `FakePersonInfo` **实例化为** FakePerson
- `VirtualCarInfo` **实例化为** VirtualCar
- `FakePersonScriptEvent` / `VirtualCarPerformScriptEvent` / `VirtualCarStateCheckScriptEvent` / `EnvironmentScriptEvent` **继承** ScriptEventBase
- `FakePersonScriptEvent` **被消费于** FakePerson
- `VirtualCarPerformScriptEvent` / `VirtualCarStateCheckScriptEvent` **被消费于** VirtualCar
- `FakePerson` **使用** FakePersonPromptTemplate
- `VirtualCar` **包含** VirtualCarDevices（真相源）
- `VirtualCar` **使用** CAR_INFO_FIELD_MAP 映射表
- `VirtualCar` **被共享给** TestedAssistant（通过 `assistant.virtual_car = car`）

### 10.4 Runner 组件协作关系
- `CaseRunner` **使用** EventScheduler / TimelineEngine / DialogueManager / TraceRecorder / AssistantProtocol
- `CaseRunner` **执行** TestCase
- `CaseRunner` **配置于** RunnerConfig
- `CaseRunner` **返回** RunResult（含 `must_pass_assertions` / `bonus_assertions`）
- `CaseRunner` **共享** VirtualCar **给** TestedAssistant
- `CaseRunner` **暴露** `trace` 属性（外部直接访问 TraceRecorder 构造 JudgeInput）
- `CaseRunner._maybe_accelerate` **调用** `assistant.aupdate_context(current_time=target)` + `timeline.accelerate_to` + `trace.record_acceleration`
- `CaseRunner._assistant_chat_streaming` **用** `asyncio.wait` 并行等回复完成 / 下一锚点到达；**调用** `reply.interrupt()` 保存半截话
- `TimelineEngine` **实现** 时间加速接口（已集成到 Runner._maybe_accelerate）
- `DialogueManager` **使用** BoundaryDetector
- `DialogueManager` / `BoundaryDetector` **实现** 边界驱动
- `EventScheduler` **实现** 双层演进机制 / 调度器回调模式 / 时间加速阈值跳过
- `EventScheduler` **回调** CaseRunner._execute_event
- `TraceRecorder` **记录** UtteranceRecord / StateCheckRecord / TraceSlice / 加速 / 打断
- `Judge`（judge模块）**独立于** CaseRunner（Runner 不调 Judge，Judge 是独立步骤）
- `Judge` **输入** JudgeInput（含 timeline_text 由 render_timeline_text 从 TraceRecorder 渲染；含 `must_pass_assertions` / `bonus_assertions` / `fake_person_profiles`）
- `Judge` **输出** JudgeVerdict（含 ScoreBreakdown + AssertionResult 列表）
- `compute_score` **计算** 必过+加分+state_check → 0-100 分（线性插值公式）
- `render_timeline_text` **渲染** TraceRecorder → 带时间线高可读文本
- `build_judge_input_from_run_result` **构造** JudgeInput（从 TestCase + TraceRecorder + RunResult）

### 10.5 助手接入关系
- `TestedAssistant` **实现** AssistantProtocol
- `TestedAssistant` **使用** `ReactAgentWithTaskRunner.astream()`（直接调用，不走 `AgentRunner` 常驻模式）
- `TestedAssistant` **使用** VirtualCarControlTool / NavigationControlTool / MediaControlTool / weather_search_v2_tool / poi_search_v2_tool / qq_music_song_search_v2_tool / create_task_cancel_tool
- `TestedAssistant` **持有** VirtualCar（由 Runner 共享）
- `TestedAssistant.achat_stream` **用** `anyio.CancelScope` 包裹生产者协程
- `StreamingReply._cancel_scope` **持有** CancelScope，`interrupt()` 调 `cs.cancel()` 真正取消推理
- `StreamingReply` **支持** 流式打断与半截话
- `VirtualCarStateCheckScriptEvent` **实现** state_check断言
- `VirtualCarControlTool` / `NavigationControlTool` / `MediaControlTool` / `VirtualCarPerformScriptEvent` **遵循** 虚拟车set_state分工
- `NavigationControlTool` / `MediaControlTool` **独立于** VirtualCarControlTool（导航/媒体非车控——对齐 aicore sgm_tools_v2 的 navigation/media 独立工具名，2026-08-28 拆分）
- `VirtualCar` **被操作于** VirtualCarControlTool / NavigationControlTool / MediaControlTool（三者均走 set_field 落盘）

### 10.6 测试关系
- `test_virtual_car_v2.py` **测试** VirtualCar / VirtualCarDevices / CAR_INFO_FIELD_MAP
- `test_scheduler_v3.py` **测试** EventScheduler / ScheduledEvent
- `test_case_runner_e2e.py` **测试** CaseRunner（用 MockAssistant）
- `test_case_schema.py` **测试** TestCase / JSON 导入导出
- `test_fixture_cases_json.py` **测试** fixture_cases.json 加载
- `test_tested_assistant.py` **测试** TestedAssistant（用 MockAgent，monkeypatch 业务工具工厂）
- `test_event_bus.py` **测试** EventBus / TraceRecorder 层1事件发射 / CaseRunner 层2事件发射（含信封 mock_time 单调性不变式）
- `test_run_server.py` **测试** run_server（真实 uvicorn 线程 + websockets 客户端）
- `visualizer/frontend` vitest **测试** events 归一化 / visualizerClient / consoleReducer / projections / usePlaybackEngine 数据链路（playback 状态机 + inverseX 互逆 + projectCarState / projectDialogue 回放裁剪）
- `ARCHITECTURE.md` **描述** CaseRunner / 双层演进机制 / visualizer 模块
- `CONTEXT.md` **描述** TestCase / 虚拟车set_state分工 / 工作原则
- `AssistantProtocol` **类似** auto_test_script 的 AnyBotToTest

### 10.7 可视化协作关系
- `EventBus` **被注入** TraceRecorder（层1事件）/ CaseRunner（层2事件）——可选注入，不注入则行为不变
- `TraceRecorder` **发射** 层1事件（utterance / state_check / car_set_state / acceleration / system / tool_call / tool_result / long_pause）
- `CaseRunner` **发射** 层2事件（case_started 含 initial_car_info / case_finished / fake_person_delta / assistant_delta）
- `VirtualCar.on_field_change` **捕获** 助手车控 set_field → CaseRunner 发射 car_set_state（单字段增量；剧本 set_state 走 TraceRecorder 原链路）
- `run_server.RunContext` **订阅** EventBus → asyncio.Queue → ws.send_json（事件泵）
- `run_server` **构造** CaseRunner（event_bus=RunContext.bus）+ TestedAssistant 或 DemoToolMockAssistant（assistant_kind）
- `run_server.DemoToolMockAssistant` **继承** MockAssistant（导航类指令模拟长耗时工具 ReAct 节奏）
- `run_server` **加载** 8 个内置 demo case（demos.run_e2e_demo 工厂函数，含 navigation-multi-condition 多条件导航）
- `visualizerClient` **连接** run_server /ws（命令-ACK + 事件流；judgeCase 重新终局评判——首次评判由 run_server 自动触发）
- `consoleReducer` **消费** 归一化事件（事件即 action）→ ConsoleState（含 JudgeState + PlaybackState）
- `projections` **投影** ConsoleState → 对话流气泡（回放按 cursorMs 裁剪）/ 时间线泳道 spans / 快进段 / 重叠说话窗口 / 相对 T0 时间区间文本 / 车态时间机视图（projectCarState）
- `usePlaybackEngine` **驱动** PlaybackState 游标（rAF 倍速推进 playbackTick；App 接线 dispatch）
- `TimelineLanes` **交互** 回放游标（拖拽/点击 inverseX 反算定位 + 播放/暂停/倍速控制条）
- `CarStatePanel` **展示** 游标时刻虚拟车状态（projectCarState 投影，最近变化字段高亮）
- `run_server` **执行** `_execute_judge`（构造 JudgeInput → Judge.ajudge → judge_verdict；**自动路径**：case 完成后 `_auto_judge` 经事件泵推送 + 停泵；**手动路径**：judge_case 命令直发发起连接）
- `RunContext` **保留** run 产物（case / runner.trace / run_result / assistant_history）供终局评判
- `VerdictPanel` **展示** JudgeVerdict（总分 / 打分明细 / 断言通过情况与裁判理由）
- `EventBus` **遵循** 信封时间不变式（seq 递增序下 mock_time 不倒退）

---

## 11. 待完成事项（WIP）

> ⚠️ 详细待办与已完成项以 [`CONTEXT.md` §6](./CONTEXT.md) 为准，本节仅列高层项。

### 已完成

- [x] **Judge 模块 + 打分机制**：独立 `judge/` 目录（与 `fake_person/` 同级）；必过 + 加分线性插值打分；裁判价值观对齐假人；state_check 算必过项；25 个测试通过
- [x] **断言分化**：`nl_assertions` → `must_pass_assertions` + `bonus_assertions`；旧字段保留做向后兼容，导入时自动迁移
- [x] **TestedAssistant v2 集成（流式 + 打断）**：基于 `ReactAgentWithTaskRunner.astream()`（修正了 `react_agent_with_task_manager` → `react_agent_with_task_runner` 的导入 bug）；`achat_stream` 用 `anyio.CancelScope` 包生产者协程，`StreamingReply.interrupt()` 调 `cs.cancel()` 真正取消推理；合并 `TimeTravelSUTAgent` 的 7 条异步回执 system prompt；删除重复的 `v2_agent_to_test.py`；`VirtualCarControlTool` 接入虚拟车（Runner 共享 `VirtualCar` 实例）；10 个单元测试通过
- [x] **`aupdate_context` 协议升级**：加 `current_time: Optional[datetime]` 参数；返回值从 `Optional[str]` 演进为 `ContextUpdateResult(proactive_text, injected_events)`（2026-08-25 结构化）；TestedAssistant / MockAssistant 全部升级
- [x] **时间加速实际集成**：`Runner._maybe_accelerate` 在锚点距 mock_time > 阈值时调 `aupdate_context(current_time=target)` + `TimelineEngine.accelerate_to` + `trace.record_acceleration`；`EventScheduler` 接 `acceleration_threshold` 参数；`RunnerConfig` 加 `enable_acceleration` / `acceleration_threshold`
- [x] **插话打断的 Runner 主循环集成**：`_assistant_chat_streaming` 用 `asyncio.wait` 并行等回复完成 / 下一锚点到达；锚点先到时调 `reply.interrupt()` 保存半截话（早期记为 INTERRUPT 类型，2026-08-25 自然流逝重构后统一为 `ASSISTANT_REPLY + is_partial=True`，无独立打断事件行）
- [x] **真实 LLM 端到端 demo**：`demos/run_e2e_demo.py` 支持 7 种 case 来源 + 5 个命令行开关；已用真实 LLM 验证开空调 / 时间加速 / scheduled（定时任务不跳过）/ complex（插话打断+定时+快进+记忆）case + Judge 评判链路（后两者 Judge 100/100）
- [x] **修复 `virtual_car_control.py:260`**：已确认新版 VirtualCar 无需手动同步（devices 真相源 + car_info 只读派生视图）
- [x] **自然时间流逝模型重构**（2026-08-25）：取消时间冻结假设，虚拟时间与真实时间 1:1 连续流逝；删除 `advance_to` / `offset_recent_tasks` / `_created_at` 偏移修正补丁；话语区间化；打断 = 半截话（删除 INTERRUPT 记录类型）；71 个测试全通过
- [x] **TestedAssistant 主动智能**：`aupdate_context` 检查 `ScheduledTaskManager` 到期任务并触发主动话语 + WorldTick 注入（`ContextUpdateResult`）
- [x] **WorldTick 事件类型 + 注入事件机制**：`ScriptEventType.WORLD_TICK` + 5 秒缓冲 + 两级触发保障（锚点 drain 主通道 + 多步快进兜底）
- [x] **测试过程可视化 M1（实时模式）**（2026-08-26）：旁路事件总线（双时间戳信封 + 单订阅者零开销）+ 两层事件（层1 TraceRecorder 落盘即推 / 层2 Runner 过程事件）+ FastAPI WebSocket 服务器（命令-ACK 协议，为语音测试预留多路复用）+ React 19 前端三面板（RunConsole / ChatStream / TimelineLanes，分段时间映射 + 重叠说话窗口检测）；信封 mock_time 单调性不变式修复；后端 95 pytest + 前端 29 vitest + 端到端联调（builtin-complex-combo，119 事件流含 acceleration×2）全通过
- [x] **可视化 M1 增强：裁判终局评判面板 + 相对 T0 时间戳**（2026-08-27）：① judge_case WS 命令 → RunContext 保留 run 产物 → 真实 Judge LLM 评判 → judge_verdict 事件直发发起连接（不走事件泵；层3 事件）→ 前端 VerdictPanel（右栏时间线下方：总分/及格徽章/必过+加分+状态检查打分行/每条断言 ✓✗+裁判理由+证据/pending/error 态）；② 对话流每个气泡与工具卡片显示相对 T0 虚拟时间区间（"T+3.2s → T+8.7s"，气泡用 started_at/ended_at，工具卡片用 call→result 配对区间）；后端 101 pytest（+3 judge_case：rejected/verdict/error payload）+ 前端 39 vitest（+7）+ 真实 Judge 端到端验证（builtin-simple-ac：60 分，必过 2/2，加分 0/1，summary+reasoning 完整）
- [x] **可视化回放模式 + 虚拟车状态观察窗**（2026-08-27）：① **数据链路**——case_started payload 补 initial_car_info 初始车态快照 + VirtualCar.on_field_change 钩子捕获助手车控 set_field 发射 car_set_state（剧本多字段 set_state 保持原格式，notify_enabled 抑制钩子）；② **回放状态机**——consoleReducer 新增 PlaybackState（idle/paused/playing + cursorMs + speed），case 完成后自动激活，运行中 scrub 被忽略，playbackTick 到终点钳制自动暂停；③ **rAF 回放引擎**（usePlaybackEngine.ts）——按倍速推进游标（真实dt × speed，单帧 dt 钳 250ms 防 tab 切后台跳变）；④ **时间线交互**——拖拽/点击定位游标（TimeScale.inverseX 反算非线性轴：拖到快进带末尾=快进完成时刻）+ 回放控制条（播放/暂停、倍速 1x/1.25x/1.5x/2x/3x/5x、当前时刻/总时长）；⑤ **车态时间机**（projectCarState）——初值+增量重建任意虚拟时刻车全量状态，CarStatePanel 展示（右栏中部，最近变化字段琥珀高亮）；⑥ **对话流回放裁剪**（projectDialogue cursorMs 参数）——未开始不显示/说到一半按 segments 拼接/工具卡片结果未到显示执行中/live 气泡不显示，回放时左栏对话流随游标倍速回放；后端 104 pytest（+3 车态事件链路）+ 前端 50 vitest（+11）+ WS 端到端实跑验证（builtin-simple-ac：initial_car_info 5 字段 + 助手车控 car_set_state 事件）全通过
- [x] **自动终局评判 + 左右面板拖拽 + 时间快进标记 + 导航/媒体独立工具 + 前端源码入库**（2026-08-28）：① **自动终局评判**——run_case 自然完成后 `RunContext._auto_judge` 自动触发（auto_judge 默认 true，结果经事件泵推送后停泵），前端 case_finished 即置 JudgeState=pending，judge_case 保留为手动重评；② **左右面板拖拽**——PanelResizer 扩展 orientation 双向（vertical col-resize 调对话流/右栏观察区宽度，--left-width CSS 变量 + localStorage ttat.layout 持久化，右栏保底 360px 自适应）；③ **对话流时间快进标记**——projectDialogue 解析 acceleration 为 AccelerationEntry，ChatStream 渲染居中虚线胶囊条（时长 + T0 区间），回放裁剪与话语一致；④ **前端源码入库**——.gitignore 解除 frontend/index.html / package.json / package-lock.json / tsconfig.json 等必要文件忽略；⑤ **导航/媒体独立工具**——demos/v2_agent_to_test/tools/navigation_control.py（name="navigation"）+ media_control.py（name="media"）对齐 sgm_tools_v2 工具名、走 set_field 落盘，virtual_car_control.py 移除导航/媒体分支并对齐 69 字段，TestedAssistant 工具列表 car_control+navigation+media；后端 126 pytest（+19 工具单测 + 1 自动评判 WS 测试）+ 前端 65 vitest 全通过

### 待完成

- [ ] **可视化 M2 剩余（跨会话回放）**：会话内回放已完成（拖拽定位/倍速回放/车态时间机，2026-08-27）；剩余 = 事件流落盘持久化（刷新/重连后仍可加载回放）+ 语音测试接入（WS 多路复用已预留）
- [ ] **VoiceDeviceDriver 实现**：物理设备测试（TTS 播放 + VAD 检测 + 流式 ASR）
- [ ] **环境 schema 与驱动器**：现阶段全双工对话剧本不使用 `EnvironmentScriptEvent`
- [ ] **Scenario 聚合**：多假人、初始车态/环境、剧本列表、标签
- [ ] **旧 case adapter**：`user_query_lists` → script events（迁移 auto_test 旧用例）
- [ ] **fixture cases 真实 LLM 批量跑通**：builtin scheduled/complex 已验证 100/100，fixture 12 case 待批量验证
