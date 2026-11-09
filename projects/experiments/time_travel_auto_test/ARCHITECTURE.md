# TimeTravelRunner 架构文档

> **维护约定**：本目录下任何实质性架构/实现变更后，须同步更新本文档。
> 最后更新：2026-08-28（可视化 M1 增强：**时间线推倒重写——live 滑动窗口 + replay 缩放视窗双模式**——live：当前虚拟时刻轴线恒居中 x=0.5，窗口 [axis±半窗] 基准 20s 按轨道像素 25ms/px 自适应，历史在左未来在右、秒级网格线随窗流动，事件块在轴线生成向左移动；replay：泳道=全程分段映射（快进压缩 6% 窄带），游标可拖拽 + 横向缩放 ×1~×64 锚定游标 + 平移滑块 + 播放自动跟随；clipSpanToView 视窗裁剪统一；此前："劲舞团"式过程可视化（script_plan 未来区预设事件竖线预览 + car_set_state 来源三色标注 script 金/assistant 红/fake_person 蓝预留 + 车态变更分组临时置顶 + builtin-god-view 混合来源 case）；更早：虚拟车设备模型大扩展——对齐车控标签树 69 字段 + CAR_INFO_GROUPS 九大分组 + case_started 全量 initial_car_info 快照 + CarStatePanel 分层分组多列展示）

---

## 1. 一句话定义

> **CaseRunner = 让一个"假人"和"被测助手"在一条会流动的虚拟时间线上对话，中间可以插入剧本事件、双方可以同时说话（重叠如实记录，框架不打断被测助手），结束后由 Judge 评判。**

---

## 2. 为什么需要它？旧 vs 新

### 旧（auto_test）：回合制 ping-pong

```
用户 → 助手 → 用户 → 助手 → 用户 → 助手 ...
└──────────────────────────────────────┘
   一问一答，没有时间概念，无法测：
   - 插话打断
   - "周五提醒我"这种延时任务
   - 长时间静默后的行为
```

### 新（time_travel）：时序演进 + 全双工

```
T0          T30s           T45s              T5m
 │            │              │                │
 ▼            ▼              ▼                ▼
假人说话    插话"改主意"   检查空调是否开    静默 → 快进到下一事件
（时间在流动，事件按时间点精确触发；
  插话与助手回复重叠时双方同时说话，框架是中立观察者，不打断、不截流）
```

**核心差异**：

| 维度 | auto_test（旧） | time_travel（新） |
|------|----------------|-------------------|
| 对话模式 | 回合制 ping-pong | 全双工，双方可同时说话（重叠如实记录） |
| 时间 | 每轮 mock_time 推进 | 事件驱动，时间会流动、会快进 |
| 插话 | 不支持 | 锚点事件精确插入，与回复重叠时如实记录重叠窗口 |
| 长周期场景 | 测不了 | 时间加速（5 天 → 60 秒） |
| 车态断言 | 无 | 虚拟车 k/v 状态检查 |

---

## 3. 核心概念（6 个名词看懂）

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  ① 假人 FakePerson                                          │
│     扮演用户，有 profile（人设）+ event_memory（记忆）       │
│     可以说固定台词，也可以由 LLM 自由发挥                    │
│                                                             │
│  ② 被测助手 TestedAssistant                                 │
│     你要测试的车载 Agent（代码层 or 物理设备）               │
│     实现 AssistantProtocol，接入即可测                       │
│                                                             │
│  ③ 虚拟车 VirtualCar                                        │
│     车的"世界"：69 个 car_info 字段九大分组                  │
│     （行驶能源/空调/座椅方向盘/乘员/门窗天窗/灯光/媒体/导航/  │
│      车载电器），设备覆盖面对齐车控标签树                    │
│     devices 是唯一真相源，car_info 是只读派生视图            │
│     助手通过车控工具改它，剧本可模拟外部世界（驾驶员踩油门） │
│                                                             │
│  ④ 剧本事件 ScriptEvent                                     │
│     时间线上的一个"动作"：假人说话 / 车态变更 / 车态检查     │
│     有时间戳 = 锚点；没时间戳 = 边界（上一轮完就执行）       │
│                                                             │
│  ⑤ WorldTick（时间锚点事件）                                │
│     时间线上一个"停靠点"：没有执行主体，只表示"时间演进到此刻 │
│     必须停一下，因为有事会发生"。                             │
│     来源：剧本显式定义 / 被测助手运行时注入（定时任务触发时间）│
│                                                             │
│  ⑥ 轨迹 Trace                                               │
│     全程录像：谁在什么时间说了什么、车态怎么变、谁打断谁     │
│     结束后交给 Judge 评判                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 整体架构（组件协作图）

```
┌──────────────────────────────────────────────────────────────┐
│                       CaseRunner                             │
│                                                              │
│   ┌──────────┐   ┌──────────────┐   ┌──────────┐            │
│   │  假人    │   │  被测助手    │   │  虚拟车  │            │
│   │FakePerson│   │TestedAssistant│   │VirtualCar│            │
│   └────┬─────┘   └──────┬───────┘   └────┬─────┘            │
│        │                │                │                   │
│        └────────┬───────┴───────┬────────┘                   │
│                 ▼               ▼                            │
│      ┌────────────────┐  ┌──────────┐                       │
│      │ 事件调度器     │  │ 时间引擎 │                       │
│      │EventScheduler  │◄─┤Timeline │  ←── 静默检测/快进     │
│      │ (heapq+Event)  │  └──────────┘                       │
│      └────────┬───────┘                                     │
│               │                                             │
│               ▼                                             │
│      ┌────────────────┐                                     │
│      │ 对话管理器     │  ←── 边界检测：                     │
│      │DialogueManager │      助手说完一句 → 结束本轮        │
│      └────────┬───────┘                                     │
│               │                                             │
│               ▼                                             │
│      ┌────────────────┐         ┌──────────┐                │
│      │ 轨迹记录器     │ ──────► │  Judge   │ → Pass/Fail    │
│      │ TraceRecorder  │         │ (终局)   │                │
│      └────────────────┘         └──────────┘                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**组件一句话**：

| 组件 | 干什么 |
|------|--------|
| EventScheduler | heapq 优先队列 + asyncio.Event 零轮询，事件就绪时回调 Runner |
| TimelineEngine | 管理虚拟时间，能快进、能检测静默 |
| DialogueManager | 驱动一轮对话，检测"这轮该结束了吗" |
| TraceRecorder | 全程录像，连半截话都记下来 |
| AssistantProtocol | 被测助手接入协议（achat / achat_stream / aupdate_context） |

---

## 5. 完整执行流程（一个 Case 怎么跑起来）

```
┌─────────────────────────────────────────────────────────────┐
│ ① 加载 Case                                                 │
│   从 JSON 读 TestCase：假人 / 虚拟车 / 剧本事件 / 断言       │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ ② 初始化所有组件（_init_session）                           │
│   - FakePerson 实例（含人设、记忆）                          │
│   - VirtualCar 实例（devices 为真相源，从 car_info 解析）    │
│   - TestedAssistant.create(session_id)                       │
│   - 共享 VirtualCar 给助手（车控工具和剧本操作同一份状态）   │
│   - EventScheduler + TimelineEngine + TraceRecorder          │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ ③ 构造调度事件列表（_build_scheduled_events）               │
│   - script_events + virtual_car_state_check_assertions       │
│   - 每个 event → ScheduledEvent（sort_key 由时间戳决定）     │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ ④ EventScheduler 主循环（_scheduler.run）                   │
│                                                             │
│   ┌───────────────────────────────────────────────────┐    │
│   │  从 heapq pop 最早就绪的事件                       │    │
│   │                                                   │    │
│   │  ┌── 边界事件 ──→ 立即回调 _execute_event          │    │
│   │  │                                                │    │
│   │  └── 锚点事件 ──→ 等待到 anchor_time（可被打断）  │    │
│   │                  fast_mode=True 时立即执行         │    │
│   └───────────────────────────────────────────────────┘    │
│                                                             │
│   _execute_event 根据事件类型分发：                         │
│   ┌───────────────────────────────────────────────────┐    │
│   │  FakePersonScriptEvent:                           │    │
│   │    假人说台词（固定 or LLM 生成）                  │    │
│   │    → 喂给助手（achat / achat_stream）              │    │
│   │    → 收集回复，记 trace                            │    │
│   │                                                   │    │
│   │  VirtualCarPerformScriptEvent:                    │    │
│   │    car.perform(event) → set_state 写 devices      │    │
│   │    → 记 trace                                     │    │
│   │                                                   │    │
│   │  VirtualCarStateCheckScriptEvent:                 │    │
│   │    car.perform(event) → state_check k/v 断言      │    │
│   │    → 记 trace                                     │    │
│   └───────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ ⑤ 所有事件执行完毕                                          │
│   - 收集 Trace 完整时间线                                   │
│   - 收集 state_check 断言结果                               │
│   - 返回 RunResult                                          │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ ⑥ Judge 终局评判（独立模块 `judge/`，Runner 不调）          │
│   输入：JudgeInput                                          │
│         - timeline_text（trace 渲染的带时间线文本）         │
│         - must_pass_assertions（必过断言，至少一条）         │
│         - bonus_assertions（加分断言，可选）                 │
│         - state_check_summary（已自动判定，算必过项）       │
│         - assistant_history（助手视角对话历史，可选）       │
│         - fake_person_profiles（假人人设，让裁判对齐价值观） │
│   输出：JudgeVerdict                                        │
│         - overall_passed: bool（以打分结果为准）            │
│         - score: float（0-100，打分明细见 ScoreBreakdown）  │
│         - assertion_results: list[AssertionResult]          │
│           每条含 assertion_type / passed / reasoning / evidence │
│         - summary: 总评                                     │
│                                                             │
│   打分公式（线性插值）：                                     │
│   - 必过任一不过（含 state_check 失败）→ 0 分              │
│   - 必过全过 + 无加分 → 满分 100                           │
│   - 必过全过 + 加分全过 → 满分 100                         │
│   - 必过全过 + 加分全没过 → 及格分 60                      │
│   - 必过全过 + 加分部分过 → 60 + 40 * (通过比例)           │
│                                                             │
│   prompt 关键：只含读懂 trace 的机制常识 + 对齐假人价值观   │
│   - 时间快进不是剧情断裂                                    │
│   - 半截话成因区分（插话打断=正常机制 / 超时截断=基建兜底）  │
│   - 快进后无假人说话时助手开口 = 主动开口机制                │
│   - state_check 已自动判定，不重复评                        │
│   - 行为对错不写死在 prompt——评判标准完全以断言为准         │
│   - 从假人视角评判助手表现（不是冷冰冰的功能性判定）        │
│                                                             │
│   用法：                                                     │
│     result = await runner.run(case)                         │
│     judge_input = build_judge_input_from_run_result(        │
│         case, runner._trace, result, assistant_history)     │
│     verdict = await judge.ajudge(judge_input)               │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. 核心机制：双层演进（这是和旧版最大的不同）

### 6.1 边界驱动（默认 90% 场景）

> **没有时间戳的事件**：上一轮对话自然结束 → 立即执行下一个

```
假人: "开空调"  ──→  助手: "好的"  ──→  助手说完
                                              │
                                              ▼
                                       (本轮边界到达)
                                              │
                                              ▼
                                      立即开始下一轮
                                      (delta = 0，不等)

时间轴：
T0 ──── 假人说话 ──── 助手回 ──── 助手说完 ──── T0+几秒
                                              ↑
                                         边界触发，下一轮立即开始
```

**适用**：跨多轮记忆 case、20 轮闲聊、普通多轮对话

**实现**：`event_t0_plus_timedelta = None`，sort_key 用 `(t0, original_index)`，和 PT0S 锚点同等优先级，按 original_index 顺序执行。

### 6.2 锚点驱动（覆盖 10% 场景）

> **有时间戳的事件**：精确到秒，时间到就触发。若被测助手正在说话，
> 假人插话与助手回复在时间上重叠——框架是**中立观察者**：不打断助手、
> 不截断其输出流，双方话语按各自时间区间如实记入 trace，
> 插话语句排队等助手当前回复说完后再投喂。

```
T0            T30s                        T45s
 │              │                           │
 ▼              ▼                           ▼
假人正在       锚点事件到达:               state_check:
自然对话  ──── (PT30S 插话,重叠)  ────  检查空调状态
                │
                ▼
            假人如实开口（助手继续说完）
            - 双方话语区间重叠 → trace 记重叠窗口
            - 插话语句 FIFO 排队
            - 助手说完当前回复 → 投喂插话 → 助手响应新指令
```

**适用**：插话重叠、长时间等待后验证、精确时序控制

**实现**：`event_t0_plus_timedelta = PT30S`，sort_key 用 `(t0 + delta, original_index)`，按时间先后排序。

### 6.3 两种模式对比

```
                  边界驱动                     锚点驱动
              ──────────────              ──────────────
触发条件:     上一轮结束                    时间戳到达
打断当前:     否（无缝衔接）                否（中立观察者，重叠如实记录）
时间间隔:     0（立即下一轮）               按设定（可 P30S / P5D）
适用场景:     90% 自然对话                  10% 精确控制
事件标记:     event_t0_plus_timedelta=None  event_t0_plus_timedelta=PT30S
sort_key:     (t0, original_index)          (t0+delta, original_index)
```

---

## 7. 五大关键机制

### 7.1 时间加速（快进）

> 事件队列就是"是否有人会说话"的充分信息源。距下一锚点事件 > 阈值 → 直接快进。
> 核心洞察：开口说话的角色只有假人（剧本事件触发）和助手（假人喂话触发），
> 只要下一事件还没到，就没人会说话——**确定**，不需要"等 N 秒确认"。

```
周一 8:00                                    周五 18:00
  │                                              │
  ▼                                              ▼
  假人: "记得周五放周杰伦"                       检查: 是否在播放周杰伦？
  ──────────────快进 5 天─────────────────────────→

  实际耗时: 0 秒（基于事件队列判定，直接跳）
  虚拟跳过: 5 天
  Trace 记录: AccelerationRecord(from=周一, to=周五)
```

**触发条件**（`_maybe_accelerate`，见 `runner.py:297`）：
- 下一事件是锚点事件（有时间戳）
- `gap = anchor_time - current_time > 阈值（默认 60s）`
- 快进前先 `aupdate_context(car_info, current_time=target)` 同步助手时间

#### 7.1.1 两层时间：mock_time vs wall_time（自然流逝模型）

框架中存在两层时间，必须严格区分：

| | mock_time（虚拟时间） | wall_time（真实耗时） |
|---|---|---|
| **管理者** | `TimelineEngine` | `datetime.now()` |
| **语义** | 测试场景中的"世界时间" | 真实墙钟 |
| **推进方式** | 与 wall_time 1:1 自然流逝；唯一跳跃方式是 `accelerate_to`（快进） | 自然流逝，不可控 |
| **用途** | 事件调度、trigger 判断、trace 时间戳 | 换算事件流的 wall_time 时间戳 |

**核心模型（2026-08-25 定稿）——不存在"时间冻结"**：

```
TimelineEngine 内部只存一个锚点对 (anchor_mock, anchor_wall)：

    mock_time = anchor_mock + (now - anchor_wall)     ← 每次读取实时计算

- 虚拟时间与真实时间 1:1 连续流逝：助手回复、假人说话、LLM 生成期间，时间照常走
- 唯一的时间跳跃方式是快进 accelerate_to(target)：重新锚定 (target, now)
- pin_to：调度器按真实时间等待锚点事件存在毫秒级误差，容差内（5s）对齐让时间戳干净
- wall_to_mock：把事件流携带的 wall_time 换算进虚拟时间线（1:1 流逝期间双向换算）
```

**为什么必须自然流逝**：本框架评测的就是"时间自然流逝下被测 agent 与假人的交互"。
假人和助手的说话都是耗时的（流式输出天然模拟逐字说出的耗时感），trace 时间戳必须
直观反映实际发生时刻；助手在回复期间调用 `set_reminder` 等工具拿到的就是实时的
虚拟时刻，`trigger_time` 天然包含回复耗时——**无需任何偏移修正补丁**。

```
自然流逝下的定时任务时间线（真实 LLM 实测，2026-08-25）：

T0:          假人: "提醒我30分钟后喝水"          （说了 0.8s）
T0+3.69s:    set_reminder 工具被调用（回复生成期间）
             → get_current_time() = T0+3.69s（实时虚拟时间）
             → trigger_time = T0+3.69s + 30min   ← 天然正确
T0+5.87s:    助手: "已设置提醒..." （首字延迟 5.2s, 说了 0.7s）
T0+29m58.69s:[WorldTick 锚点到达]                 ← trigger_time - 5s
T0+30m5.99s:  助手: "喝水提醒到时间啦..."（主动, 触发后 2.3s 开口）
              （任务于 T0+30m3.69s 到期，时间戳 = 到期时刻 + 2.3s 开口延迟）
```

**实时时间源注入**：Runner 初始化时调 `assistant.set_time_source(lambda: timeline.mock_time)`，
助手侧工具（如 `set_reminder`）通过该时间源取当前虚拟时刻。Runner 注入的调度器
`get_now` 同样基于虚拟时间——快进后虚拟时间领先真实时间，锚点等待必须按虚拟距离算。

#### 7.1.3 多步快进 + 时间锚点（WorldTick）

若助手在 `[current, target]` 区间内有 pending 定时任务，不能一步跳到 target。Runner 通过两层保障确保不跳过：

| 机制 | 谁来驱动 | 时间点 | 作用 |
|------|----------|--------|------|
| **WorldTick 注入** | Scheduler 事件队列 | `trigger_time - 5s` | 显式锚点，确保 Scheduler 一定停靠 |
| **多步快进** | `_maybe_accelerate` → `get_pending_scheduled_tasks()` | `trigger_time` | Runner 主动查询，精确触发 |

**WorldTick 的 5 秒缓冲**：时间锚点设在 `trigger_time - 5s`，而非 `trigger_time` 本身。理由：
- 安全裕度：即使某个环节有精度问题，5s 缓冲确保不会刚好错过
- 职责分离：WorldTick 是 agent 视角的"附近停一下"，多步快进是框架视角的"精确到点"
- 更真实：真实场景中提醒通常提前几秒触发

```
完整时间线示例（假人设 30 分钟提醒，2026-08-25 真实 LLM 实测验证）：

T0:         假人: "提醒我30分钟后喝水"
T0+3.69s:   set_reminder 被调用（回复生成期间，实时虚拟时间）
            → trigger_time = T0+3.69s + 30min     ← 自然流逝，天然正确
            → WorldTick 注入: trigger_time - 5s = T0+29m58.69s
T0+5.87s:   助手: "好的，已设置提醒"

T0+29m58.69s: [WorldTick 锚点到达]   ← Scheduler 显式停靠，快进在此停下
            → _drain_pending_tasks_near_anchor: 发现 5s 后有 pending 任务
T0+30m3.69s: 助手: "叮~喝水时间到啦..."  ← 5s 缓冲静默推进后任务到期触发
T0+2h:      假人: "我刚才提醒什么来着？"
```

**两级触发保障**：

| 通道 | 触发者 | 条件 | trace 呈现 |
|------|--------|------|-----------|
| **通道 A：锚点 drain** | `_execute_world_tick` → `_drain_pending_tasks_near_anchor` | WorldTick 锚点存在（助手注入或剧本定义）且准时到达 | 锚点系统事件 + 主动话语，层次清晰 |
| **通道 B：多步快进停靠** | `_maybe_accelerate` → `get_pending_scheduled_tasks()` | 快进区间内有 pending 任务（无论有无锚点） | 直接在停靠点触发，无锚点事件行 |

两级互为保障，**先到者生效**。真实 LLM 运行中通道 B 常常先到（处理后续事件时
`_maybe_accelerate` 直接把快进目标延伸到 trigger_time 停靠触发）；通道 A 的注入锚点
被调度器串行回调拖晚时按"迟到锚点静默跳过"处理（见下）。

**迟到锚点静默跳过**（`_execute_world_tick` + `_has_tasks_near_now`，2026-08-25）：
注入型锚点到达时若其锚定的任务已被通道 B 先行触发（锚点附近无待触发任务），
直接返回，**不记录"锚点到达"系统事件**——避免 trace 出现排在任务触发之后的
冗余锚点行（任务的如实记录是它实际被触发的时刻，由先到的通道完成）。

**实现细节**（`_execute_world_tick` + `_drain_pending_tasks_near_anchor`，`runner.py`）：
1. 锚点到达时先等助手通道空闲（`_wait_assistant_idle`，时间推进不与助手说话并发）
2. 迟到检查：`_has_tasks_near_now()` 为假 → 静默返回（见上）
3. **先记录系统事件**（world_tick），再推进触发任务——保证 trace 上"锚点到达"必排在"主动话语"之前
4. `_drain_pending_tasks_near_anchor` 只处理距当前 mock_time ≤ 加速阈值（60s）的任务（即本锚点锚定的任务，通常在 5s 缓冲之后），不会越界吞掉更远任务；**过期任务（gap ≤ 0）立即触发**，不静默丢弃
5. 5 秒缓冲是虚拟时间的静默推进（低于阈值，**不记为快进事件**），trace 呈现"锚点到达 → 5 秒后助手主动开口"
6. 主动话语时间戳 = 任务触发时刻 + 开口延迟（`at + timedelta(seconds=ttft)`，2026-08-26 修正：此前直接用触发时刻，与"触发后 Xs 开口"标注自相矛盾——时间戳说此刻开口、标注说 X 秒后才开口）
7. 多步快进兜底：查询中间停靠点时筛选 `current < trigger_time <= target`，快进到锚点（trigger-5s）时不会提前触发任务

### 7.2 插话重叠 + 流式投喂（中立观察者模型，2026-08-25 定稿，2026-08-26 改流式投喂）

> **框架是中立测试工具**：不打断被测助手、不截断其输出流、不遗漏任何一侧事件。
> 锚点（插话）到达时若助手正在流式回复，假人按锚点时刻如实开口，
> 双方话语在时间上重叠——trace 按各自区间如实记录，渲染层标出重叠窗口。
> 假人话语流式投喂（模拟流式 ASR）：说出第一个字就把文本流实时推给助手
> （第一个 chunk = 用户开口 = 插话打断时机信号，说完 = EOF）——不等说完、
> 不等助手空闲。助手支不支持打断是它自己的事：支持打断的助手在第一个
> chunk 即中断旧流（旧流记为半截话，插话打断能力可测）；不支持的助手
> 多流并行，每条流的输出区间独立记录。

```
T0            T0+3s                         T0+5s        T0+6s
 │               │                             │            │
 ▼               ▼                             ▼            ▼
 假人开场:       锚点到达，假人插话:            助手首字     假人说完
 "陪我唠两句呗"  "先别唠了，帮我定个闹钟..."    （继续说）   
                 │                             │
                 ▼                             ▼
            ┌──────────────────────────────────────────┐
            │ 1. 不打断助手推理（中立观察者）           │
            │ 2. 假人按锚点时刻开口，说话区间如实记录   │
            │ 3. 双方区间相交 → 重叠窗口记入 trace      │
            │ 4. 第一个字即投（输入流实时推给助手）     │
            │ 5. 助手多流并行，每条流独立记录           │
            │ 6. 助手响应新指令                        │
            └──────────────────────────────────────────┘

trace 呈现（complex case 真实 LLM 实测，2026-08-25）：
  [T0 + 0.000s → T0 + 1.486s] 假人(driver): 哎，今天跑了一天客户... (说了 1.5s)
  [T0 + 3.000s → T0 + 6.209s] 假人(driver): 哦对了，先别唠了，帮我定个35分钟的闹钟... (说了 3.2s)
  ━━━ 双方同时说话 [T0 + 5.007s → T0 + 5.771s] ━━━
    助手（同时段说到）: 哎呀，今天辛苦了呀！...要不要我给你放点轻松的音乐...
    假人(driver)（同时段说到）: 楼下拿快递。顺手把空调也打开呗
  [T0 + 5.007s → T0 + 5.771s] 助手: 哎呀，今天辛苦了呀！... (首字延迟 3.5s, 说了 0.8s)
  [T0 + 11.011s → T0 + 12.004s] 助手: 已经帮你设置好35分钟后的拿快递提醒啦... (首字延迟 4.8s, 说了 1.0s)
```

**重叠可视化（切片算法）**：话语携带 chunk 级时间戳（`segments`），
`get_overlaps()` 检测假人/助手话语的区间交集；渲染层在重叠窗口内
按 `segments` 切出双方**在窗口内实际说出**的文字（不完全重叠时各自只显示
重叠部分，窗口外的部分仍在各自话语行中完整呈现），无重复无遗漏。

**半截话语义（两种成因）**：中立模型下助手话语**不会被框架**
截断，`is_partial=True` 出现于：回复超时被截断（测试基建兜底）或
**助手响应插话打断自中断旧流**（`reply.is_interrupted=True`）。
`UtteranceRecord.interrupted_by_barge_in` 字段区分成因，渲染为不同标记——
`（半截话，被用户插话打断）` vs `（半截话，超时截断）`。Judge prompt 对两者
只给**机制解释**（前者是插话打断机制的正常呈现、后者意味着回复未在时限内
完成），**不写死对错**——面对插话该合作容忍还是该中止响应、半截话该不该
扣分，由各用例断言定义（裁判中立原则，见 §5 prompt 关键）。

**被测助手接入层插话打断参考实现**（v2 TestedAssistant，2026-08-26）：
v2_agent 底层（`ReactAgentWithTaskRunner.astream`）无打断机制，音频侧的
插话打断在 TTS 播放层做（`v2_frontend_voice.py`）——文字层插话打断由接入层
`tested_assistant.py` 的 `achat_stream` 补齐，不改底层框架代码：
- 第一个输入 chunk 到达（用户开口）→ 立即 `interrupt()` 旧的活跃流
  （`_active_reply` 跟踪），实测 13ms 内旧流中止；
- 被打断旧流的半截话同步写入 `_history`（`［被用户打断，未说完］`标记，
  顺序确定），供 Judge 回看；
- 被打断轮次不写回模型链（底层 response 未完成即被取消）——"丢弃"语义，
  新轮基于打断前的链续接，如实暴露底层行为。
框架侧不需要任何配合改动：`runner.py` 消费事件流时若见
`reply.is_interrupted`，旧流自然记为半截话（`is_partial=True` +
`interrupted_by_barge_in=True`，渲染为"被用户插话打断"标记）。

**插话投喂时机的归责**：插话锚点设多少秒、落在回复窗口内还是窗口外，
是**用例构造问题**；框架只负责按锚点时刻如实开口、如实记录。
助手收到排队后的插话如何处理（是否表现为"没听见"），是**被测助手的能力边界**，
测试平台的任务是如实记录和如实评价。

### 7.3 state_check 断言（虚拟车 k/v）

> 在指定时间点，检查虚拟车的某个字段是否等于期望值

```
T45s
 │
 ▼
 检查: car_info["空调开启状态及模式"] == "制冷中"？

 ┌──────────────────────────────────┐
 │ 实际值: "制冷中"                  │
 │ 期望值: "制冷中"                  │
 │ 结果:   ✓ PASS                    │
 └──────────────────────────────────┘

 注意：
 - 助手车控结果（如开空调）必须由助手调车控工具写入 devices
 - 用例里禁止用 set_state「上帝之手」代写助手能做的事
 - 外部世界变化（如驾驶员踩油门）才用 set_state
 - car_info 是 devices 的只读派生视图，断言时从 devices 读实际值
```

#### 7.3.1 虚拟车设备模型（2026-08-27 大扩展，对齐车控标签树）

> 设备覆盖面参考 `base_vehicle_assistant_case_tag_tree.json` 的车控操作子树，
> car_info 键名与用例生态词汇对齐（如"导航目的地""冰箱模式""方向盘加热"）。

**三层结构**：

```
car_devices.py（Pydantic 设备模型，唯一真相源）
    ↓ CAR_INFO_FIELD_MAP（69 字段双向映射：中文值 ↔ devices 字段）
models.py VirtualCar（set_field / get_field / car_info 派生视图）
    ↓ CAR_INFO_GROUPS（九大展示分组，随 case_started 下发前端）
CarStatePanel（分组折叠面板 + 多列布局）
```

**九大分组与代表字段**（共 69 个 car_info 键）：

| 分组 | 代表字段 |
|------|----------|
| 行驶与能源 | 速度/档位/手刹/点火/驾驶模式/续航/电量/充电状态 |
| 空调 | 开启状态及模式/温度/风量/风向（吹脸/吹脚/吹脸和脚）/内外温度 |
| 座椅与方向盘 | 四座 × 加热/通风/按摩/模式（零重力/标准）+ 方向盘加热 |
| 乘员 | 四座是否有人 + 主驾/副驾安全带 |
| 门窗与天窗 | 四门状态/后备箱/四车窗开合度/天窗/遮阳帘 |
| 灯光 | 阅读灯（×2 + 亮度）/氛围灯（颜色/亮度/模式）/大灯模式 |
| 媒体 | 多媒体播放状态（播放中/暂停中/停止中）/歌曲名/歌手名/歌单名/音源/音量 |
| 导航 | 导航状态/导航目的地 |
| 车载电器 | 车载电视/车载冰箱/冰箱温度/冰箱模式 |

**车控工具指令解析**（`virtual_car_control.py`）：自然语言指令 → `{car_info key: 中文值}` 写入集 → 统一 `VirtualCar.set_field` 落盘（触发 on_field_change → car_set_state 事件）。行驶安全约束：行驶中开窗/开门等危险操作会被拒绝。

**导航 / 媒体是独立工具**（非车控，2026-08-28 拆分）：对齐 aicore sgm_tools_v2 的 `navigation` / `media` 工具名，实现在 `demos/v2_agent_to_test/tools/`（`navigation_control.py` / `media_control.py`），同样走 `VirtualCar.set_field` 落盘。导航支持设目的地/取消/查询；媒体支持播放控制/点歌（歌手+歌曲/歌单）/音量/音源切换/查询，切歌诚实拒绝（虚拟车无歌单队列）。被测 Agent 的工具列表：`car_control` + `navigation` + `media` 三件套。

### 7.4 注入事件 + WorldTick（2026-08-25 已实现）

> 时间线不只是剧本定义的——被测助手在运行时也可以"注入"时间锚点，要求 Runner
> 在某个时间点停下来，因为有事会发生（如定时任务触发）。

**为什么需要注入事件**：
- 剧本只能定义"已知时间点"的事件（假人说话、车态检查）
- 但被测助手内部的定时任务触发时间是在运行时才确定的
- 如果 Runner 不知道这些时间点，快进时会直接跳过，导致定时任务丢失

**实现方式**：

1. **WorldTick 事件类型**：`ScriptEventType.WORLD_TICK`，无执行主体（`target="world"`），只表示"时间演进到此刻必须停一下"。来源：剧本显式定义 / 被测助手运行时注入。

2. **ContextUpdateResult 结构化返回**：`aupdate_context` 返回 `ContextUpdateResult`，包含：
   - `proactive_text: str | None` — 助手主动话语（定时任务到期触发）
   - `injected_events: list[WorldTickScriptEvent]` — 注入的时间锚点事件

3. **注入事件合并**：Runner 的 `_handle_context_update` 将注入的 WorldTick 通过 `ScheduledEvent.from_event(wt, t0=mock_time)` 转为调度事件，以 `original_index=-1` 标记注入来源，`schedule_one(immediate=True)` 加入事件队列。

4. **5 秒缓冲**：`ScheduledTaskManager.add_task` 时自动记录 `trigger_time - WORLD_TICK_BUFFER`（默认 5s）作为时间锚点注入时间。`aupdate_context` 收集待注入锚点并计算相对偏移，放入 `ContextUpdateResult.injected_events`。

```
剧本事件队列（初始）：
  T0: 假人说话
  T2h: 假人追问
         ↑
    快进到这里，但中间没有事件 → 一步跳过

注入 WorldTick 后：
  T0: 假人说话
  T30m-5s: [WorldTick]  ← 助手注入：定时任务触发前 5s
             → _execute_world_tick: 先记录锚点到达，再 drain 附近任务
  T30m:     [任务触发]  ← 锚点后 5s 缓冲静默推进，任务到期，助手主动开口
  T2h: 假人追问
         ↑
    快进分两段：T0 → T30m-5s（锚点停靠）→ drain 5s → T30m → T2h
    兜底：若无锚点，多步快进查 get_pending_scheduled_tasks 直接在 T30m 停靠触发
```

**锚点执行时序保证**（`_execute_world_tick`，2026-08-25 定稿）：
1. 快进停在锚点时刻（trigger - 5s），trace 先记 `[系统事件] WorldTick 锚点到达`
2. 锚点 drain 推进虚拟时间 5 秒（低于加速阈值，不记为快进事件）到触发点
3. `aupdate_context(current_time=trigger_time)` 触发到期任务，Agent 生成主动话语
4. 话语时间戳 = 触发时刻，trace 呈现"锚点到达 → 5 秒后主动开口"的清晰层次

**WorldTick 来源**：
| 来源 | 何时产生 | 示例 |
|------|---------|------|
| 剧本定义 | 编写 case 时显式声明 | `event_type: world_tick, t0_plus: PT30M` |
| 助手注入 | `aupdate_context` 返回 `injected_events` | 设置提醒后返回 `WorldTick(trigger_time - 5s)` |

**关键代码位置**：
- `script_events/script_event.py`：`WorldTickScriptEvent` 定义
- `case_runner/assistant_protocol.py`：`ContextUpdateResult` dataclass
- `case_runner/runner.py:367-395`：`_handle_context_update` 注入事件合并
- `demos/v2_agent_to_test/tools/scheduled_tasks/manager.py`：`WORLD_TICK_BUFFER` + `get_pending_world_ticks`
- `demos/v2_agent_to_test/tested_assistant.py`：`aupdate_context` WorldTick 注入 + `set_time_source` 实时时间源

### 7.5 事件流协议 + 四层轨迹命名体系（2026-08-25）

> 双侧（假人 + 被测助手）都以**事件流协议**接入，Runner 把交织的事件流记录成轨迹，
> 再渲染成裁判可读的文本。翻译是必要且有损的——关键在于**分层控制损失**：
> 丢掉冗余，但保留评测需要的行为证据和时序信息。

#### 四层命名体系

| 层 | 名称 | 英文 | 谁产出 | 谁消费 | 格式 |
|---|---|---|---|---|---|
| L0 | **SUT 原生事件** | Raw SUT Events | 被测助手框架 | 接入适配层 | 各框架自定义（如 v2_agent 的 `AgentOutTextDeltaEvent`） |
| L1 | **协议事件** | Protocol Events | 接入适配层（翻译） | Runner | 统一的 `AssistantEvent` / `FakePersonEvent` |
| L2 | **测试轨迹** | Test Trace | Runner（交织） | 渲染器 / Judge | `TraceRecorder` 记录的时间轴对齐事件序列 |
| L3 | **裁判视图** | Judge View | 渲染器 | Judge LLM | 高可读字符串 |

```
L0: v2_agent 原生事件 ──┐                              ┌── 假人剧本事件（剧本定义）
                       │ 翻译（_translate_event）       │ 产出（deliver_fake_person_speech_stream）
L1: AssistantEvent ───┼────────── 交织 ──────────────┼─── FakePersonEvent
                       │        Runner 调度            │
L2:                   Test Trace（TraceRecorder）
                       │
                       │ 渲染（render_timeline_text）
L3:                   Judge View（字符串）
```

**L1 是分水岭**：L1 以上是"接入层的责任"（各助手自己翻译自己的原生事件），L1 以下是"平台的责任"（Runner 统一处理）。平台保持中立，不关心 v2_agent 和其他助手的事件格式差异。

#### 为什么要分层翻译

- **L0 不可读且冗余**：原始事件流（逐字 TextDelta + 内部任务事件）直接给 Judge 会塞爆上下文，大量冗余让裁判难以判断
- **L2 是权威记录**：测试唯一的事实来源——Judge 从它渲染、可视化从它导出、回归分析从它比对
- **L3 是投影**：L2 的人类/LLM 可读投影，保留时序语义但转为自然语言，刻意省略 Judge 不需要关心的细节

#### 事件流携带的时序信息（体验维度评测）

| 信息 | 采集方式 | 评测价值 |
|------|---------|---------|
| 首字延迟（TTFT） | 第一个 TEXT_DELTA 的 wall_time − 请求发起时刻 | 响应速度 |
| 工具调用 | TOOL_CALL / TOOL_RESULT 事件（名称+参数+耗时+结果） | 行为证据：不只"说了什么"，还有"实际做了什么" |
| 流式停顿 | Runner 检测文本流内相邻 TEXT_DELTA 的 wall_time 差 > 2s（工具边界间隙不算——工具执行 + LLM 围绕工具的思考是正常节奏，工具区间单独可见） | 流畅度体验 |
| 假人说话时长 | speak_start → speak_done 的 wall_time 差 | 假人侧语速（对照基准） |
| 主动话语触发延迟 | `_aupdate_context_timed` 测量 aupdate_context 真实耗时 | 主动智能响应速度（任务到期后多快开口） |

#### 裁判视图中的呈现

以下为 2026-08-25 真实 LLM 实测输出（scheduled case，中立观察者模型 + 迟到锚点静默跳过后，Judge 100/100）：

```
[T0 + 0.000s → T0 + 0.6s] 假人(driver): 提醒我30分钟后喝水 (说了 0.6s)
[T0 + 5.791s → T0 + 6.447s] 助手: 好的，我已经为您设置了30分钟后提醒喝水的提醒，到时间我会通知您的~ (首字延迟 5.2s, 说了 0.7s)
[T0 + 30m3.860s] [时间快进] 从 19:36:35 跳到 20:06:32（静默期间无对话活动）
[T0 + 30m3.860s] 助手: 您好呀，您设置的喝水提醒时间到啦，现在该喝水了哦~ (主动, 触发后 2.0s 开口)
[T0 + 2h] [时间快进] 从 20:06:32 跳到 21:36:29（静默期间无对话活动）
[T0 + 2h → T0 + 2h0.807s] 假人(driver): 我刚才让你提醒我什么来着？ (说了 0.8s)
[T0 + 2h2.524s → T0 + 2h3.396s] 助手: 您刚才在2026年08月25日19:36设置了30分钟后喝水的提醒，该提醒已经在20:06的时候通知您啦。 (首字延迟 1.7s, 说了 0.9s)
```

注：`set_reminder` 在 T0+3.86s（回复生成期间，ReAct 先调工具后吐字）被调用，
trigger_time = T0+3.86s + 30min = T0+30m3.86s。处理 T+2h 事件时多步快进直接把
目标延伸到 trigger_time 停靠触发（通道 B 先到），注入锚点（trigger - 5s）迟到被
静默跳过——trace 无冗余锚点行，时间线干净，全程无任何偏移修正补丁。

以下为 2026-08-25 真实 LLM 实测输出（complex case：插话重叠 + 双指令定时 + 快进 + 恢复轮，Judge 100/100）：

```
[T0 + 0.000s → T0 + 1.486s] 假人(driver): 哎，今天跑了一天客户，累得不行，你陪我唠两句呗。 (说了 1.5s)
[T0 + 3.000s → T0 + 6.209s] 假人(driver): 哦对了，先别唠了，帮我定个35分钟的闹钟，到点提醒我去楼下拿快递。顺手把空调也打开呗，车里有点闷。 (说了 3.2s)
━━━ 双方同时说话 [T0 + 5.007s → T0 + 5.771s] ━━━
  助手（同时段说到）: 哎呀，今天辛苦了呀！跑了一天客户肯定特别累，要不要我给你放点轻松的音乐解解乏，或者你想聊点什么都可以呀~
  假人(driver)（同时段说到）: 楼下拿快递。顺手把空调也打开呗
[T0 + 5.007s → T0 + 5.771s] 助手: 哎呀，今天辛苦了呀！跑了一天客户肯定特别累，要不要我给你放点轻松的音乐解解乏，或者你想聊点什么都可以呀~ (首字延迟 3.5s, 说了 0.8s)
[T0 + 11.011s → T0 + 12.004s] 助手: 已经帮你设置好35分钟后的拿快递提醒啦，空调也已经打开了，现在是29度制冷模式，稍等会儿车里就凉快啦~ 要是觉得温度不合适随时告诉我调整哦。 (首字延迟 4.8s, 说了 1.0s)
[T0 + 35m9.603s] [时间快进] 从 19:37:26 跳到 20:12:23（静默期间无对话活动）
[T0 + 35m9.603s] 助手: 叮咚~ 你设置的35分钟提醒时间到啦，该去楼下拿快递咯😉 (主动, 触发后 3.9s 开口)
[T0 + 1h] [时间快进] 从 20:12:23 跳到 20:37:14（静默期间无对话活动）
[T0 + 1h → T0 + 1h1.986s] 假人(driver): 快递拿到啦，多亏你提醒！行了我要上楼了，把空调关了吧，别费电了。 (说了 2.0s)
[T0 + 1h6.933s → T0 + 1h7.725s] 助手: 空调已经帮你关好啦，今天跑了一天好好上楼休息吧~ 下次需要帮忙随时喊我哦😊 (首字延迟 4.9s, 说了 0.8s)
[T0 + 1h2m] [时间快进] 从 20:37:21 跳到 20:39:14（静默期间无对话活动）
[T0 + 1h2m] [状态检查] 期望={"空调开启状态及模式": "关闭中"}, 实际=… [✓ 通过]
```

注：插话锚点 T0+3s 落在助手闲聊回复窗口内（助手首字 T0+5.007s，假人 3.000s→6.209s
正在说），双方话语在 [5.007s, 5.771s] 重叠——框架不打断助手，重叠窗口内双方
各自实际说出的文字如实呈现（假人只显示落在窗口内的"楼下拿快递。顺手把空调也打开呗"，
窗口前的部分在其完整话语行中）。插话说完即投（即时投喂），助手（不支持打断）
两条流并行处理双指令，`set_reminder` 在第二次回复生成期间被调用，
trigger = T0+35m9.603s——重叠、定时、
快进三要素在自然流逝时间线上因果有序，无任何人工对齐痕迹。

**渲染规则**：
- **区间化渲染**：话语渲染为 `[T0 + Xs → T0 + Ys] 角色: 内容`（开口 → 说完），说话是耗时事件，起止都标
- **重叠窗口块**：假人与助手话语区间相交时，插入 `━━━ 双方同时说话 [起点 → 终点] ━━━` 块，块内按 chunk 级时间戳（`segments`）切出双方在窗口内实际说出的文字——完全重叠显示全部，不完全重叠只显示重叠部分（各自窗口外的内容仍在自己的完整话语行中）
- **工具调用合并**：TOOL_CALL + TOOL_RESULT 配对渲染为单条区间记录（`[工具] 名称 调用 → 返回 (耗时 Zs)`），避免两条独立行打断阅读
- **主动 vs 被动**：主动话语标注 `(主动, 触发后 X.Xs 开口)`，X.Xs 是任务到期后 LLM 真实生成耗时（体验指标，非虚拟 5 秒缓冲）；**话语时间戳 = 任务到期时刻 + X.Xs 开口延迟**（2026-08-26 修正，与标注自洽；上文 2026-08-25 历史实测块中时间戳为旧语义的触发时刻本身）；被动回复标注 `(首字延迟 X.Xs)`
- **时间戳格式**（`_fmt_clock`）：快进时刻仅显示时分秒（跨日附加月-日），丢弃微秒，避免冗长
- **数字结构恒定**：触发时刻尾数（如 30m3.860s）= `set_reminder` 调用时刻（回复生成期间的自然流逝时刻）+ 定时时长，每次运行随 LLM 耗时变化，但"触发时刻 = 工具调用时刻 + 定时时长"结构不变

Judge prompt 中已声明这些标注的语义（时序演进语义第 8/9/10 条）：工具调用/返回是行为证据，流式停顿用于评价流畅度，同时说话是重叠窗口的事实呈现（不是助手出错）。

**关键代码位置**：
- `case_runner/assistant_protocol.py`：`AssistantEvent` / `AssistantEventType`（TEXT_DELTA / TOOL_CALL / TOOL_RESULT），每个事件携带 `wall_time`
- `fake_person/event.py`：`FakePersonEvent`（speak_start / text_delta / speak_done）+ `deliver_fake_person_speech_stream`
- `demos/v2_agent_to_test/tested_assistant.py`：`_translate_event` 把 v2_agent 原生事件翻译为 `AssistantEvent`
- `case_runner/runner.py`：`_assistant_chat_streaming` 消费事件流（TTFT 计算 + 停顿检测 + 工具记录；`reply.is_interrupted` 时记半截话 = 助手插话打断）；`_execute_fake_person_event` 消费假人事件流（说话时长 + segments）并把 text_delta 实时推入输入队列（第一个字即投）；`_spawn_stream` 启动后台流任务（`_active_stream_tasks` 跟踪并发流）；`_wait_assistant_idle` 时间推进前的通道空闲等待
- `case_runner/trace.py`：`TOOL_CALL` / `TOOL_RESULT` / `LONG_PAUSE` RecordKind；`UtteranceRecord` 含 `speech_duration` / `ttft` / `segments` 字段；`get_overlaps()` 重叠窗口检测
- `judge/prompt.py`：`render_timeline_text` 渲染时序信息 + 重叠窗口块 + 工具配对合并

**已知局限**：v2_agent 的 `ReactAgentWithTaskRunner.astream` 在框架内部消化工具调用，不吐独立的 TOOL_CALL / TOOL_RESULT 事件。`_translate_event` 已预留检测逻辑（`event.tool_calls` / `event.output` 属性），未来接入方若暴露这些事件即可自动捕获。

---

## 8. 真实 Case 演绎示例（case-001）

**Case 描述**：主驾说"有点热"，助手应开空调；45 秒后检查空调状态

```
Case: case-001 固定台词_有点热开空调
─────────────────────────────────────────────────────────────────

[T0 = 周一 14:00:00]
  │
  ▼ 边界事件 (event_t0_plus_timedelta=PT0S, 假人说话)
  │
  │  假人(driver): "你好小涂，有点热，把空调打开吧。"
  │       │
  │       ▼ TestedAssistant.achat_stream 流式响应
  │       │
  │       │  助手内部思考:
  │       │   → 调用 car_control 工具
  │       │   → 工具操作 VirtualCar.devices.ac: is_on=True, mode=COOLING
  │       │   → 返回 observation: {"空调开启状态及模式": "制冷中"}
  │       │
  │       ▼ 助手回复
  │       │
  │  助手: "好的，已为您打开空调并调至舒适温度。"
  │
  │  边界检测: 助手说完 → 本轮结束
  │
  ▼ 没有更多边界事件，等待下一个锚点
  │
  │  [时间加速候选：T0 → T45s 距离 45 秒 < 60 秒阈值，正常等待]
  │
[T45s = 周一 14:00:45]
  │
  ▼ 锚点事件 (event_t0_plus_timedelta=PT45S, state_check)
  │
  │  检查: car_info["空调开启状态及模式"] == "制冷中"
  │       │
  │       ▼ 从 devices 读取实际值
  │       实际: "制冷中"  ✓ PASS
  │
  ▼ 所有事件执行完毕
  │
  ▼ Judge 评判（独立模块 judge/，Runner 不调）
  │
  │  must_pass_assertions:
  │   ✓ "助手应理解用户觉得热并开启或调节空调"
  │   ✓ "车辆静止时不应拒绝合理的空调控制请求"
  │
  │  bonus_assertions:
  │   - "助手应主动询问用户期望的温度"（可选，加分项）
  │
  │  state_check: 1/1 passed（算必过项）
  │  trace: 2 utterances, 0 interrupted, 0 accelerated
  │
  ▼ 最终结果: ✓ PASS（必过全过 + 加分部分过 → 60 + 40 * 比例）
```

---

## 9. 多种场景的演进模式对照

```
场景                         演进模式              时间轴示意
──────────────────────────────────────────────────────────────────
单轮车控                     纯边界驱动            T0: 说话 → T0+几秒: 检查
(case-001)

多轮续聊 + 自主发挥          边界 → 锚点           T0: 固定台词 → T1M30S: LLM 自由发挥
(case-002)

插话打断                     边界 + 锚点抢占       T0: 开始对话 → T0.5S: 打断改主意
(case-009)

长周期延时任务               边界 + 快进           T0 周一: "周五提醒" → 快进 5 天 → 周五检查
(case-010)

并发多假人                   多边界并发            T0: 假人A说话 + 假人B说话 (并发执行)
(case-011)

负向断言                     锚点 state_check      T0: 说话 → TXX: 检查应失败 (验证负向路径)
(case-012)
```

---

## 10. 文件地图

```
time_travel_auto_test/
│
├── 📄 ARCHITECTURE.md          ← 本文档（架构 + 流程图）
├── 📄 CONTEXT.md               ← 工作上下文 + 设计原则
├── 📄 KNOWLEDGE_GRAPH.md       ← 知识图谱（详细实体关系）
│
├── 📦 case_schema.py           ← TestCase 定义 + JSON 导入
├── 📦 script_events/
│   └── script_event.py         ← 剧本事件（假人/虚拟车/环境）
├── 📦 fake_person/
│   ├── models.py               ← 假人 = 人设 + 剧本 + LLM
│   ├── event.py                ← FakePersonEvent 事件流（speak_start/delta/done）
│   └── llm_prompt.py           ← 假人 prompt 模板（纯剧本驱动，无退下/打分）
├── 📦 virtual_car/
│   ├── models.py               ← VirtualCar (devices 为真相源, car_info 只读派生) +
│   │                              CAR_INFO_FIELD_MAP (69 字段双向映射) + CAR_INFO_GROUPS (九大展示分组)
│   └── car_devices.py          ← 详细设备（空调/四座座椅/门窗天窗/灯光/媒体/导航/方向盘/车载电器）
│
├── 📦 case_runner/             ← Runner 核心框架
│   ├── __init__.py             ← 公开 API 汇总
│   ├── runner.py               ← CaseRunner 主调度器
│   ├── scheduler.py            ← EventScheduler (heapq + asyncio.Event)
│   ├── timeline.py             ← TimelineEngine + 快进
│   ├── dialogue.py             ← DialogueManager + BoundaryDetector
│   ├── trace.py                ← TraceRecorder + 半截话保存
│   └── assistant_protocol.py   ← AssistantProtocol + StreamingReply
├── 📦 judge/                   ← Judge 终局评判（独立模块）
│   ├── __init__.py             ← 公开 API 汇总
│   ├── models.py               ← JudgeInput / JudgeVerdict / ScoreBreakdown
│   ├── scoring.py              ← 打分公式（必过 + 加分 → 0-100）
│   ├── prompt.py               ← JUDGE_SYSTEM_PROMPT + render_timeline_text
│   └── judge.py                ← Judge 类 + build_judge_input_from_run_result
│
├── 📦 demos/                    ← 被测 Agent 实现
│   ├── run_e2e_demo.py          ← 端到端 demo（内置 case 工厂 + 真实 LLM 跑测）
│   ├── tools/
│   │   └── virtual_car_control.py  ← 车控工具 car_control（被测 Agent 调用；自然语言指令 →
│   │                                  car_info 写入集 → set_field 落盘；不含导航/媒体——
│   │                                  它们是独立工具）
│   └── v2_agent_to_test/
│       ├── __init__.py         ← 公开 API（导出 TestedAssistant）
│       ├── tested_assistant.py ← TestedAssistant (实现 AssistantProtocol)
│       └── tools/
│           ├── navigation_control.py  ← 导航工具 navigation（设目的地/取消/查询）
│           ├── media_control.py       ← 媒体工具 media（播放/点歌/音量/音源/查询）
│           └── scheduled_tasks/       ← 定时任务机制（时间锚点注入）
│
├── 📦 visualizer/               ← 测试过程可视化（M1 实时模式已上线）
│   ├── event_bus.py            ← 旁路事件总线（双时间戳信封：wall_time + mock_time）
│   ├── run_server.py           ← FastAPI + WebSocket 服务器（命令-ACK + 事件流推送 +
│   │                              case 完成自动终局评判 + judge_case 手动重评，
│   │                              挂载 frontend/dist，端口 8800）
│   ├── tui_viewer.py           ← 终端 TUI 观察器
│   ├── export_trace.py         ← trace 导出工具
│   └── frontend/               ← React 19 + Vite + TS 前端（对齐 v2_frontend 模式）
│       ├── src/adapters/visualizerClient.ts   ← WS 客户端（命令-ACK 协议，含 judgeCase）
│       ├── src/domain/events.ts               ← 事件信封 → 强类型事件归一化（含 judge_verdict / initialCarInfo）
│       ├── src/app/consoleReducer.ts          ← 核心 reducer（事件即 action，含 JudgeState + PlaybackState 回放状态机 + live 缓冲开口时刻）
│       ├── src/app/projections.ts             ← 纯函数投影（对话流回放裁剪/车态时间机/双模式时间线刻度 live 滑动窗口+replay 缩放视窗/工具子泳道/live 增长条/重叠窗口/clipSpanToView 视窗裁剪）
│       ├── src/app/usePlaybackEngine.ts       ← rAF 回放引擎（倍速推进游标，单帧 dt 钳制）
│       ├── src/app/useNowTicker.ts            ← 实时虚拟时钟（双时间戳外推 nowMs，驱动轴伸长/增长条）
│       └── src/components/                    ← RunConsole / ChatStream / TimelineLanes / CarStatePanel / VerdictPanel / PanelResizer
│
└── 📦 test/                     ← 测试（126 个 pytest 全通过）
    ├── cases/
    │   └── fixture_cases.json  ← 12 个测试用例
    ├── test_virtual_car_v2.py  ← VirtualCar 单元测试
    ├── test_scheduler_v3.py    ← EventScheduler 单元测试
    ├── test_case_runner_e2e.py ← CaseRunner 端到端测试（mock assistant，
    │                              含中立观察者/重叠渲染/迟到锚点回归）
    ├── test_case_schema.py     ← TestCase schema 测试
    ├── test_fixture_cases_json.py ← fixture cases 导入/导出测试
    ├── test_judge.py           ← Judge 评判测试（mock LLM，25 个，含打分）
    ├── test_tested_assistant.py ← TestedAssistant 单元测试（10 个，mock agent）
    ├── test_navigation_media_tools.py ← 导航/媒体独立工具单元测试（19 个，真实 VirtualCar 链路）
    ├── test_event_bus.py       ← 事件总线 + TraceRecorder 事件发射测试
    └── test_run_server.py      ← WS 服务器命令/事件流/自动+手动终局评判测试
```

---

## 11. 被测助手接入协议（怎么把你的 Agent 接进来测）

```
你的 Agent 只需实现 AssistantProtocol：

┌─────────────────────────────────────────────────┐
│  class MyAssistant:                              │
│      def create(self, session_id: str,           │
│                 system_prompt: str = ""): ...    │  ← 创建/重置会话
│                                                  │
│      async def achat(query: str) -> str: ...     │  ← 非流式对话
│                                                  │
│      async def achat_stream(                     │
│          chunks: AsyncIterator[str])             │
│          -> StreamingReply: ...                  │  ← 流式对话（流式输入：
│                                                  │     第一个 chunk = 用户开口
│                                                  │     = 插话打断时机信号，
│                                                  │     迭代器耗尽 = 用户说完；
│                                                  │     支持打断的助手应在
│                                                  │     第一个 chunk 中断旧流）
│                                                  │
│      async def aupdate_context(                  │
│          car_info: dict[str, Any],               │  ← 更新车态上下文
│          current_time: datetime | None = None     │  ← 注入虚拟时间
│      ) -> ContextUpdateResult: ...                │  ← proactive_text + injected_events
│                                                  │
│      def get_pending_scheduled_tasks()           │  ← 查询 pending 定时任务
│          -> list[tuple[datetime, str]]: ...      │     (触发时间, 描述)，供 Runner
│                                                  │     判断中间停靠点（duck typing）
│                                                  │
│      async def adump_history() -> list[dict]:... │  ← 导出给 Judge
└─────────────────────────────────────────────────┘

接入方式：

  ① 代码层 Agent  → 直接实现 AssistantProtocol
                    (参考 demos/v2_agent_to_test/tested_assistant.py)

  ② 物理设备      → 用 VoiceDeviceDriver（预留）
                    TTS 播放 + VAD 检测 + 流式 ASR
```

**StreamingReply**：流式回复对象（事件流协议 v2）
- `put_event(event)`：生产者放入 `AssistantEvent`（TEXT_DELTA / TOOL_CALL / TOOL_RESULT）
- `put_chunk(chunk)`：兼容旧版，自动转为 TEXT_DELTA 事件
- `finish()`：标记完成
- `interrupt()`：取消推理、保存已说部分为半截话（中立观察者模型下框架**不会因插话调用它**，仅在流卡死超时的基建兜底中使用）
- `stream()`：消费者异步迭代获取 `AssistantEvent`
- `stream_text()`：兼容旧版，只迭代文本片段

**事件流协议（L1）**：各助手在对接时负责把自身原生事件（L0）翻译为统一的 `AssistantEvent`，每个事件携带 `wall_time`。Runner 据此计算 TTFT、检测流式停顿、记录工具调用，为 Judge 提供行为证据和时序信息（详见 §7.5）。

**session_id 规范**：Runner 用 `<case_id>-<t0_isoformat>` 确保每次 run 隔离

**VirtualCar 共享**：Runner 初始化 VirtualCar 后，通过 `assistant.virtual_car = car` 共享给助手，车控工具和剧本事件操作同一份状态。

---

## 12. 已完成 vs 待完成

### ✅ 已完成
- Schema 层：TestCase / ScriptEvent / FakePersonInfo / VirtualCarInfo
- 12 个 fixture cases（覆盖所有演进模式）
- VirtualCar 重构：devices 为唯一真相源 + CAR_INFO_FIELD_MAP 映射 + 只读 car_info 视图
- 假人 FakePerson：纯剧本驱动 prompt（去掉退下/打分残留）+ LLM 自主发挥 bug 修复
- 被测助手 TestedAssistant：实现 AssistantProtocol，基于 aicore v2 ReAct；直接用 `agent.astream()` 而非 `AgentRunner.achat()`（后者不存在）；`achat_stream` 用 `anyio.CancelScope` 支持打断；含完整异步回执 system prompt；10 个单元测试通过（mock agent）
- EventScheduler：heapq 优先队列 + asyncio.Event 零轮询 + fast_mode
- TimelineEngine：虚拟时间 + 快进接口
- DialogueManager + BoundaryDetector
- TraceRecorder：时间切片 + 半截话保存 + summary
- AssistantProtocol + StreamingReply
- CaseRunner 主调度器：完整 run() 流程，事件回调模式
- 端到端测试：8 个 case 通过 mock assistant 验证（含长周期 fast_mode）
- **Judge 终局评判模块（独立 `judge/` 目录，与 `fake_person/` 同级）**：
  - 独立于 Runner（Runner 只跑出 trace，Judge 是独立步骤）
  - 必过 + 加分线性插值打分：`60 + 40 * (bonus_passed/bonus_total)`，state_check 算必过项
  - 裁判价值观对齐假人：prompt 注入假人人设，从假人视角评判助手表现
  - `overall_passed` 以打分结果为准（LLM 返回值不覆盖）
  - prompt 理解时序演进语义（时间快进/半截话/打断/主动智能/state_check 已判定）
  - 4 个文件：models.py / scoring.py / prompt.py / judge.py
- **断言分化**：`nl_assertions` → `must_pass_assertions` + `bonus_assertions`；旧字段保留向后兼容，导入时自动迁移
- 57 个测试全通过（含 25 个 Judge 测试：8 打分 + 4 渲染 + 9 LLM 评判 + 2 模型 + 1 prompt + 1 同步）
- **TestedAssistant v2 接入修复 + 打断支持**：修复 `react_agent_with_task_manager` → `react_agent_with_task_runner` import bug；删除 `AgentRunner.achat` 不存在的调用，改用 `agent.astream()`；`achat_stream` 用 `anyio.CancelScope` 包消费协程，`StreamingReply.interrupt` 真正取消推理；合并完整异步回执 system prompt；删除重复的 `TimeTravelSUTAgent` 封装；`StreamingReply` 加 `_cancel_scope` 字段；10 个单元测试通过（mock agent，不依赖真 LLM）
- **时间加速集成到 Runner 主循环**（2026-08-25）：`_maybe_accelerate` 方法，基于事件队列判定快进，快进前 `aupdate_context` 同步助手时间
- **多步快进 + 定时任务不跳过**（2026-08-25）：`get_pending_scheduled_tasks` 查询中间停靠点，逐个快进并触发到期任务，主动话语记入 Trace
- **aupdate_context 协议升级**（2026-08-25）：加 `current_time` 参数 + `str | None` 返回值，支持主动智能测试
- **插话打断 Runner 集成**（2026-08-25）：`_assistant_chat_streaming` 中锚点到达时调用 `reply.interrupt()` 打断推理，保存半截话
- **定时任务管理**（2026-08-25）：`ScheduledTaskManager` + `set_reminder` 工具，`aupdate_context` 检查到期任务并注入系统消息触发助手主动提醒
- **WorldTick 事件类型**（2026-08-25）：`ScriptEventType.WORLD_TICK` + `WorldTickScriptEvent`，无执行主体的时间锚点事件
- **ContextUpdateResult 结构化返回**（2026-08-25）：`aupdate_context` 返回 `ContextUpdateResult(proactive_text, injected_events)` 替代 `str | None`
- **注入事件 → 事件队列合并**（2026-08-25）：`_handle_context_update` 将注入 WorldTick 转为 `ScheduledEvent` 并 `schedule_one`
- **自然时间流逝模型**（2026-08-25 定稿）：取消"时间冻结"假设——虚拟时间与真实时间 1:1 连续流逝（TimelineEngine 锚点对实时计算 mock_time），唯一跳跃方式是快进 `accelerate_to`；删除 `advance_to` 与 `offset_recent_tasks` 偏移修正补丁（工具通过 `set_time_source` 注入的实时虚拟时间源取当前时刻，trigger_time 天然包含回复耗时）；话语区间化（started_at → ended_at），打断 = 半截话（ASSISTANT_REPLY + is_partial），删除 INTERRUPT 记录类型；调度器锚点等待基于虚拟时间（get_now 注入）；`_format_offset` 毫秒进位修复
- **WorldTick 5 秒缓冲**（2026-08-25）：`WORLD_TICK_BUFFER = 5s`，时间锚点设在 trigger_time - 5s，配合多步快进双重保障
- **事件流协议 v2 + 四层轨迹命名体系**（2026-08-25）：`AssistantEvent`（TEXT_DELTA / TOOL_CALL / TOOL_RESULT，携带 wall_time）+ `FakePersonEvent`（speak_start / text_delta / speak_done）；`StreamingReply` 队列从 `str` 升级为 `AssistantEvent`（保留 `put_chunk` / `stream_text` 兼容旧版）；`TestedAssistant._translate_event` 翻译 v2_agent 原生事件；Runner 消费双侧事件流，计算 TTFT、检测 >2s 流式停顿、记录工具调用；`UtteranceRecord` 加 `speech_duration` / `ttft` 字段；`render_timeline_text` 渲染时序信息（"说了 Xs" / "首字延迟 Xs" / `[工具调用]` / `[工具返回]` / `⚠ 流式停顿`）；Judge prompt 声明第 8/9/10 条时序演进语义
- **71 个测试全通过**（含 12 e2e + 10 tested_assistant + 其余；新增 test_natural_time_flow_during_reply 自然流逝断言）
- **自然时间流逝模型真实 LLM 验证**（2026-08-25）：scheduled case（定时任务不跳过 + 主动提醒 + 跨时记忆）与 complex case（插话打断 + 双指令 + 35 分钟定时 + 快进 + 恢复轮）均用真实 LLM 跑通，Judge 100/100；时间线验证：set_reminder 在回复生成期间调用 → trigger_time 天然含回复耗时 → WorldTick 锚点精确停靠 → 主动话语恰在 trigger 时刻触发，全程无偏移修正补丁
- **中立观察者模型**（2026-08-25 定稿）：框架不打断被测助手、不截断其输出流——删除锚点到达时的 `reply.interrupt()` 主动打断逻辑与调度器锚点打断信号机制；假人话语 FIFO 队列 + feeder 循环串行投喂（助手空闲时才喂，消息顺序正确且不阻塞调度器）；话语/工具事件区间化记录（started_at + ended_at + chunk 级 `segments`）；`get_overlaps()` 检测假人/助手话语重叠窗口，渲染层以 `━━━ 双方同时说话 ━━━` 块呈现双方在窗口内实际说出的文字（不完全重叠只标重叠部分）；工具调用/返回配对合并为单条区间记录；时间推进前 `_wait_assistant_idle` 等助手通道空闲；过期任务（gap ≤ 0）立即触发不丢弃
- **迟到 WorldTick 锚点静默跳过**（2026-08-25）：注入型锚点被调度器串行回调拖晚、且其锚定任务已被多步快进停靠先触发时，`_execute_world_tick` 检查 `_has_tasks_near_now()` 无待触发任务即静默返回，不记录冗余"锚点到达"系统事件，避免 trace 尾部噪音
- **中立观察者模型真实 LLM 验证**（2026-08-25）：scheduled + complex case 重跑均 100/100——插话与助手回复重叠窗口如实呈现（假人窗口内部分正确截取）、插话排队延迟投喂后助手正确处理双指令、迟到锚点无冗余记录、定时任务在触发点停靠主动提醒、跨时记忆与恢复轮正常；74 个测试全通过（含重叠渲染测试 + 迟到锚点回归测试）
- **接入层插话打断实现**（2026-08-26）：v2_agent 打断行为探测（`run_interrupt_probe.py` 三模式：concurrent/serial/cancel）证实底层 `astream` 无打断机制（并发=多流并行+链路分叉、串行=排队非打断、调用方 interrupt=唯一打断途径）；文字层插话打断由接入层 `tested_assistant.py` 补齐（不改 aicore 框架代码）：第一个输入 chunk 到达即 `interrupt()` 旧活跃流（`_active_reply` 跟踪），半截话同步入 `_history`（`［被用户打断，未说完］`标记），被打断轮不写回模型链（丢弃语义）；真实 LLM 实测 13ms 内旧流中止、车态正确执行；新增 2 个单测（插话打断 + 已完成旧流不重复记账），77 个测试全通过
- **测试过程可视化 M1（实时模式）**（2026-08-26）：
  - **旁路事件总线**（`visualizer/event_bus.py`）：双时间戳事件信封（`wall_time` 真实墙钟 + `mock_time` 虚拟时间，支撑实时/回放两套坐标系）；单订阅者零开销旁路——不注入则 TraceRecorder/Runner 行为与旧版完全一致，中立观察者原则（事件采集不参与执行决策，trace 落盘仍是唯一判卷依据）
  - **两层事件**：层1 = TraceRecorder 落盘即推（utterance / state_check / car_set_state / acceleration / system / tool_call / tool_result / long_pause）；层2 = Runner 过程事件（case_started / case_finished / fake_person_delta / assistant_delta）+ run_server 的 case_cancelled / run_error——补过程感（chunk 逐字到达、生命周期边界）
  - **WS 服务器**（`visualizer/run_server.py`）：FastAPI + 单条 WebSocket 命令-ACK 协议（`list_cases` / `run_case` / `stop_case` / `judge_case` 终局评判），对齐 v2_frontend 模式为语音测试预留多路复用；RunContext 事件泵（bus → asyncio.Queue → ws.send_json）；全局互斥单 run；连接断开自动停止后台执行；挂载 `frontend/dist` 静态文件（生产模式单端口 8800）
  - **前端**（`visualizer/frontend/`，React 19 + Vite 6 + TS 5.8 + vitest 3，对齐 v2_frontend 技术栈）：事件即 action 的单一 `useReducer` 扇出多投影（纯函数投影可独立测试）；`visualizerClient.ts` WS 客户端（命令-ACK + 事件流归一化，未知 kind 中立保留为 unknown_event 不丢弃，`judgeCase()` 发起终局评判）；`projections.ts` 纯函数投影——**分段时间映射**（normal 段按时长比例分宽、快进段压缩为固定 6% 窄带，30s 对话与 5 天快进同轴共存）+ **重叠说话窗口检测**（假人×助手话语区间求交，渲染为跨泳道高亮竖带）+ **相对 T0 时间区间**（气泡/工具卡片显示"T+3.2s → T+8.7s"）；三栏布局 = 左 RunConsole（case 列表/运行控制/运行摘要/车态）+ 中 ChatStream（落盘话语权威记录 + 层2 delta 打字机，半截话区分"被插话打断/超时截断"标记，气泡头带相对 T0 时间区间）+ 右纵向堆叠 TimelineLanes（四泳道：假人/助手/虚拟车/系统，快进斜纹带、重叠高亮、当前时刻游标）与 VerdictPanel（裁判终局评判：总分/及格徽章/打分明细/每条断言✓✗+裁判理由+证据）
  - 测试：后端 pytest 95 个全通过（含 test_event_bus 11 + test_run_server 4）+ 前端 vitest 29 个（events 7 + client 4 + reducer 6 + projections 12）全通过；端到端联调通过（真实 uvicorn 服务器 + WS 客户端跑 builtin-complex-combo（fast_mode=False，mock 助手）：119 事件流完整——case 生命周期 + delta×108 打字机 + utterance×6 + acceleration×2 快进带 + state_check；静态文件挂载 + list_cases 7 个 case 验证通过）
  - **信封时间不变式**（端到端联调发现并修复）：seq 递增序下 `mock_time` 不倒退（快进只会向前跳）。话语落盘事件（层1 utterance）信封时间用 `ended_at`（落盘时刻）而非 `started_at`——话语进行中的 delta 事件已携带更晚的虚拟时间，回填开口时刻会造成信封流时间倒退；话语区间仍在 payload 的 `started_at`/`ended_at` 里。`case_finished` 信封补当前虚拟时间（原来为 None，回放模式无法定位终点）。回归断言写入 test_event_bus.py
  - **M1 增强：工具调用全程可见 + 流式停顿语义修正**（2026-08-26）：
    - **对话流工具卡片**：`projectDialogue` 把 `tool_call`/`tool_result` 事件按到达序混排进话语气泡之间（toolName FIFO 配对），ChatStream 渲染橙色工具卡片（工具名/参数/返回/耗时/执行中）——工具执行过程不再只藏在时间线小点里
    - **时间线工具区间化**：`projectTimelineSpans` 把 call×result 栈式配对（LIFO，与轨迹渲染 `_merge_tool_records` 一致，支持嵌套）为 `[call 时刻, result 时刻]` 区间 span（tone=tool 橙色）；未配对 call 渲染为"执行中"点事件
    - **long_pause 误报修复（完整版）**：流式停顿只测文本流内停顿（TEXT_DELTA→TEXT_DELTA 间隔 > 2s）——任何一侧是工具事件（TOOL_CALL/TOOL_RESULT）的间隙一律不算：工具执行 + LLM 围绕工具的思考是 agent 正常节奏，工具区间已单独可见不重复记停顿。修复前 v2 助手（真实 LLM 延迟）在工具边界两侧的思考间隙被误报为停顿标记，恰好集中在插话响应（含工具调用）处，看起来像"被插话失败"
    - **流式停顿 = 警示不是失败**：可视化 long_pause 由 tone-fail（红）改为 tone-warn（琥珀警示色），图例拆分"流式停顿"与"检查失败"——失败红只留给真正的错误（state_check 失败等）；插话打断半截话用 tone-partial 黄色斜纹（早已区分）
    - **被测助手选择**：RunConsole 加 mock/v2 切换（v2 = 真实 LLM + 接入层插话打断，不人为拉宽助手流式节奏，忠实记录其自然速度）；mock 无工具调用/定时任务，跑 complex case 看不到插话重叠与主动提醒
    - 修复 App.tsx 漏调 `client.connect()`（WS 从未连接、case 列表空）与 run_server 类名错误（`V2AgentTestedAssistant` → `TestedAssistant`）
    - 后端 98 pytest（含新增 test_tool_boundary_gaps_not_long_pause / test_text_stream_stall_still_records_long_pause）+ 前端 32 vitest（含工具区间配对 + 流式停顿 warn tone 测试）全通过
  - **M1 增强：裁判终局评判面板 + 相对 T0 时间戳**（2026-08-27）：
    - **终局评判链路**（层3 事件 judge_verdict）：`judge_case` WS 命令 → RunContext 保留 run 产物（case / runner.trace / run_result / assistant_history，`_current_run`/`_last_run` 双全局，stop 后仍可评判半程轨迹）→ `_execute_judge`（构造 JudgeInput → `Judge().ajudge()` 真实 LLM）→ `_judge_and_send` 把 judge_verdict 事件**直发发起连接**（不走事件泵——case 自然结束后泵已停止，重连/stop 后泵绑定的连接可能已换）；评判进行中重复发起被拒；`_execute_judge` 独立为模块级函数供 pytest monkeypatch（judge_case 测试不依赖真实 LLM）
    - **VerdictPanel**（右栏时间线下方，`.right-column` 纵向堆叠布局）：开始/重新评判按钮（run finished/cancelled 后可用）→ pending 态（"裁判正在评判…"）→ 结果态（总分大数字 + 及格/不及格徽章、必过/加分/状态检查打分行、summary、每条断言 ✓/✗ + 裁判理由 + 证据列表）；前端 JudgeState（idle/pending/done/error）由 consoleReducer 管理，case_started/resetRun 重置
    - **相对 T0 虚拟时间戳**：对话流每个气泡与工具卡片显示相对 T0 时间区间——气泡用 started_at/ended_at（"T+3.2s → T+8.7s"），工具卡片用 call→result 的 mock_time 配对区间（未配对时仅开始时刻）；`projections.formatTimeRange` 统一格式化，无 t0 或 live 打字机气泡为 null
    - 后端 101 pytest（+3 judge_case：无 run rejected / verdict 事件直达 + 可重复评判 / 异常 error payload）+ 前端 39 vitest（+7：judge_verdict 归一化 / JudgeState 流转 / 气泡与工具卡片时间区间）全通过；真实 Judge 端到端验证（builtin-simple-ac：60 分，必过 2/2，加分 0/1，summary + 每条 reasoning 完整）
  - **M1 增强：回放模式 + 虚拟车状态观察窗**（2026-08-27，会话内回放，像视频播放器）：
    - **车态数据链路统一**：`case_started` payload 携带 `initial_car_info` 全量初始车态快照（VirtualCar 派生视图，含未在 case 中指定的设备默认值，共 69 字段）+ `car_state_groups` 分组元数据（CAR_INFO_GROUPS 九大分组：行驶与能源/空调/座椅与方向盘/乘员/门窗与天窗/灯光/媒体/导航/车载电器，前端分层展示依据）；`VirtualCar.on_field_change` 钩子捕获助手车控工具的 `set_field` 字段变化 → Runner 旁路发射单字段增量 `car_set_state` 事件（剧本多字段 set_state 走 TraceRecorder 原"多字段一条"格式，`notify_enabled` 标志抑制钩子）——初始快照 + 增量序列 = 可重建任意虚拟时刻的车全量状态
    - **回放状态机**（consoleReducer `PlaybackState`）：mode（idle 运行中 / paused 可拖拽 / playing 倍速推进）+ cursorMs（游标，相对 T0 毫秒）+ speed（倍速）；case_finished/cancelled/run_error 自动切 paused 激活回放，case_started/resetRun 重置 idle（保留倍速设置）；运行中 playbackScrub 被忽略；playbackTick 到 maxMs 钳制并自动暂停
    - **rAF 回放引擎**（`app/usePlaybackEngine.ts`）：playing 时每帧 dispatch playbackTick（deltaMs = 真实帧间 dt × speed），单帧真实 dt 钳制 250ms——tab 切后台 rAF 停摆，恢复时不会瞬间跳到结尾
    - **时间线拖拽交互**（TimelineLanes）：pointer capture 拖拽/点击时间线任意位置定位游标，`TimeScale.inverseX` 把归一化 x 位置反算回虚拟毫秒（非线性段内线性插值——拖到快进带末尾 = 快进完成时刻，语义正确）；回放控制条：播放/暂停按钮（游标在终点时播放自动从头）、倍速 1x/1.25x/1.5x/2x/3x/5x、当前时刻/总时长显示
    - **车态时间机**（`projectCarState`）：初值 = case_started.initialCarInfo（69 字段全量），增量 = mock_time ≤ 游标的 car_set_state 按序合并（cursorMs=null 全量合并 = 实时最新状态）；`groupCarStateEntries` 按分组元数据把字段归入九大组（元数据缺失时回退单组"全部状态"，未被分组声明的字段进"其他"组兜底）
    - **CarStatePanel 分层分组展示**（右栏中部，信息密度优化）：`<details>` 可折叠分组面板（默认展开，组头显示组名 + 字段数 + 最近变化琥珀圆点），组内字段 CSS Grid 多列自适应布局（窄面板 1 列 → 宽面板 3 列），最近变化字段琥珀高亮 + 变化时刻 tooltip，"观察时刻 T+xx"随回放跳动
    - **对话流回放裁剪**（`projectDialogue(state, cursorMs)`）：未开始的话语不显示、说到一半的按 segments 拼接部分内容（打字机效果 status=speaking）、说完的全量显示；工具卡片结果未到显示"执行中"；live 打字机气泡不显示（回放基于落盘权威记录）——回放时左侧对话流随游标倍速回放
    - 后端 104 pytest + 前端 60 vitest（+10：groupCarStateEntries 分组归入/兜底/元数据缺失回退）全通过；WS 端到端实跑验证（builtin-simple-ac + builtin-navigation-multi-condition：initial_car_info 69 字段全量快照 + 九大分组元数据 + 助手车控 car_set_state 增量事件 + state_check 通过；车控工具 15 条新设备指令解析抽查全部通过——座椅按摩/零重力/方向盘加热/空调风向/媒体歌曲/电视/冰箱/导航/氛围灯）
  - **M1 增强：实时增长条 + 工具子泳道 + 面板拖拽布局**（2026-08-27）：
    - **实时虚拟时钟**（`app/useNowTicker.ts`）：信封双时间戳是外推锚点——最近一个携带虚拟时间的事件给出 (wall_time, mock_time)，虚拟时间与真实时间 1:1 流逝故 `now = mock + (Date.now() - wall)`，100ms 定时器驱动重绘，事件每次到达自动重锚消除漂移，快进由 acceleration 事件把锚点跳到未来。运行中驱动：时间轴平滑伸长（`buildTimeScale` 接 nowMs，轴终点 = max(落盘事件, now)）、live 增长条、执行中工具条右端推进
    - **live 增长条**（说话开始即可见，不再说完才出现）：reducer 的 live 缓冲记录开口时刻（首个 delta 的 mockTime → `liveFakePerson.startedAt` / `liveAssistant.startedAt`）；`projectLiveSpans` 投影 [开口, now] 区间 → TimelineLanes 渲染虚线脉冲条（tone-info + span-live 动画），落盘后由权威 utterance 区间无缝接管（reducer 同刻清空缓冲）
    - **工具子泳道**（助手下层低一层级，替代原系统泳道里的工具条）：`projectToolSpans` 把 tool_call×tool_result 栈式配对（LIFO 同轨迹渲染）为区间 + **行打包算法**（按 call 时刻贪心分配并行工具到不同行，执行中条视为占满整行防止后到并行条错分行）；TimelineLanes 渲染 `assistant-group`（助手泳道 + ↳ 工具子泳道组）：橙色矮条（⚙ 名称 + ⟳ 执行中/✓ 完成）+ **call/result 时刻竖线**（伸进助手泳道底边，直观关联"何时开始调用/何时结束获得结果"，竖线高度 = 行数×行步进 + 伸入深度）；执行中条右端尾随 nowMs（实时）或游标（回放）不断增长，hover 看入参/返回/耗时/区间；回放裁剪语义：游标未到 call 不显示、call ≤ 游标 < result 执行中尾随游标
    - **面板拖拽布局**（右栏三面板用户自行调整高度适配不同屏幕）：`PanelResizer` 组件（pointer capture 纵向拖拽，row-resize 光标 + 中央抓握短横线）插在 时间线/车态窗/评判面板 之间；高度经 CSS 变量（`--timeline-h` / `--car-h`）下发，clamp 120..1200px，localStorage（`ttat.rightColumnLayout`）持久化，评判面板吃剩余空间
    - 前端 56 vitest（+6：buildTimeScale nowMs 轴伸长 / projectToolSpans 配对·行打包·回放裁剪 / projectLiveSpans 开口区间与缓冲清空 / live 缓冲 startedAt 断言）全通过；后端 104 pytest 回归全通过；WS 实跑 builtin-navigation-multi-condition（nav_tool_delay=2s）验证：tool_call/tool_result 各 2 个事件成对到达（含 tool_args/result/duration_ms）、119 个 delta 全部携带 mock_time + wall_time（live 增长条锚点数据源）、首个 tool_call 前有承接语 delta 且最后一个 tool_result 后有总结语 delta（工具区间夹在助手话语间）、mock_time 整体单调不减、case_started 带 initial_car_info
  - **M1 增强：时间线居中轴 + 未来区预览 + 车态变更来源三色**（2026-08-28，"劲舞团"式过程可视化）：
    - **居中时间轴**（`buildTimeScale` axisMs 参数）：当前虚拟时刻轴线恒映射 x=0.5（实时 = useNowTicker 外推的当前虚拟时刻；回放 = 游标），左半历史（话语/工具条块从轴线向左"长出"）右半未来（预设事件从右向左飞向轴线）；实现 = 全域分段映射后做保序重标定 `[0,axisX]→[0,0.5]` `[axisX,1]→[0.5,1]`（两半各自保持快进压缩结构）；axisMs=null 保持旧语义（轴线即终点）；实时模式轴终点外扩 FUTURE_LOOKAHEAD_MS=60s 前瞻窗口。**坑**：段坐标 warp 必须作用于副本——就地 warp 会让 x()=warp(xRaw()) 二次 warp，轴线偏离 0.5（0.44/0.75 类偏差根因，测试抓出）
    - **未来区预设事件竖线**（`projectTimelineSpans` scriptPlan 参数）：后端 `case_started` 新增 `script_plan` 载荷（`_build_script_plan`：锚点驱动的假人说话/剧本改车态/状态检查 → {kind, at, target, label} 按时刻升序；边界驱动事件无预设时刻不进入）；前端过滤 at > axisMs 的预设事件投影为 tone=future 点事件 → TimelineLanes 渲染半透明金色竖线 + 无框文字（越接近轴线透明度越高），随时间推进从右向左飞向轴线——直观预览即将发生什么
    - **车态变更来源标注**（car_set_state.source 字段，三色区分）：后端 `record_set_state` 新增 source 参数——剧本 set_state 路径 source="script"（上帝视角）、助手车控工具（on_field_change 钩子）source="assistant"、假人直接操作 source="fake_person"（预留）、None=旧事件流未知；前端 projectCarState 把 source 附加到 CarStateEntry（entry.source / view.changedSource / changedAtMs），CarStatePanel 按来源渲染金色（剧本）/红色（助手）/蓝色（假人预留）加粗键值文字，持续 1 秒闪烁
    - **车态变更分组临时置顶**（CarStatePanel）：字段被改动的分组临时提到最顶展示 1 秒（useMemo 重排 + setTimeout 恢复），配合来源颜色一眼看到"什么被谁改了"
    - 新增内置 case `builtin-god-view`（剧本上帝视角 set_state 起步行驶 + 假人请助手开空调）：混合来源演示——时间线未来区金色竖线（剧本改车态）飞向轴线 + 车态面板金色（剧本）/红色（助手）交替闪烁；前端 65 vitest（+5：轴线居中重标定/axisMs=0 全右半/未来事件投影过滤/车态来源数据链/buildTimeScale 前瞻窗口）+ 后端 106 pytest（+2：case_started script_plan 生成/car_set_state 双来源标注）全通过；WS 实跑三 case 验证（script_plan 升序含三类事件、source 标注正确、混合来源 state_check 通过）
  - **M1 增强：自动终局评判 + 左右面板拖拽 + 时间快进标记 + 导航/媒体独立工具**（2026-08-28）：
    - **自动终局评判**：run_case 结束无需手动点"开始评判"——`RunContext._run` 在 case 自然完成后（`auto_judge` 选项默认 true）自动起 `_auto_judge` 任务：`_execute_judge` 结果经事件总线推送（与泵串行，避免与泵并发 ws.send_json 竞态），推送完毕由 `_auto_judge` 停泵；前端 consoleReducer 收到 case_finished 即置 JudgeState=pending（"裁判正在评判…"），judge_verdict 事件到达转 done/error；手动 `judge_case` 命令保留为重新评判入口
    - **左右面板拖拽**：对话流与右栏观察区宽度可调——`PanelResizer` 组件扩展 `orientation` 属性（horizontal 纵向调高 / vertical 横向调宽，col-resize 光标）；App.tsx 以 CSS 变量 `--left-width` 下发宽度（clamp 480..窗口-右栏最小值，localStorage `ttat.layout` 持久化）；`.app-stage` grid-template-columns 自适应——窗口过窄时对话流自动收缩，右栏观察区保底 360px
    - **对话流时间快进标记**：projections.ts `projectDialogue` 解析 acceleration 事件为 `AccelerationEntry`（时长 + T0 起止区间），ChatStream 渲染居中虚线圆角胶囊条（"⏩ 时间快进 X（T+..s → T+..s）"）——快进区间不再被误读为持续对话；回放模式下未到游标的快进条不显示
    - **前端源码入库**：`.gitignore` 解除对 `frontend/index.html` / `package.json` / `package-lock.json` / `tsconfig.json` / `vite.config.ts` / `src/**` 的忽略（原全局 `*.json`/`*.html` 规则误伤前端必要文件），前端可完整 clone 运行
    - **导航/媒体独立工具**（对齐 aicore sgm_tools_v2 工具名）：`demos/v2_agent_to_test/tools/navigation_control.py`（name="navigation"：设目的地/取消/查询）+ `media_control.py`（name="media"：播放控制/点歌/歌单/音量/音源/查询，切歌诚实拒绝）；`virtual_car_control.py` 移除导航/媒体分支并对齐 69 字段设备描述；TestedAssistant 工具列表 = `car_control` + `navigation` + `media` 三件套，系统提示同步三工具约定
    - 后端 126 pytest（+19 导航/媒体工具单测 + 1 WS 自动评判测试）+ 前端 65 vitest 全通过
  - **M1 增强：时间线推倒重写——live 滑动窗口 + replay 缩放视窗双模式**（2026-08-28，替代此前"居中重标定"实现）：
    - **live 滑动窗口（自动测试运行中）**：`buildTimeScale` 改为 ScaleOptions 联合类型（LiveScaleOptions / ReplayScaleOptions）。实时模式 = 中央轴线滑动窗口——当前虚拟时刻轴线恒固定画面中央 x=0.5，窗口 `[axis-半窗, axis+半窗]` 随虚拟时间从右向左流动；轴线右侧是未来（剧本预设事件竖线从右缘飞入、越接近轴线越亮、抵达轴线由真实事件接管），左侧是历史（事件块在轴线处生成向左移动，进行中的块右端贴轴线增长、结束后定长左移滑出左缘）。窗口基准 20s（过去 10s + 未来 10s），`computeLiveWindowMs` 按轨道像素宽自适应扩大（25ms/px，ResizeObserver 上报）；秒级网格线落在整数倍刻度上随窗口流动（1-2-5 步长序列按密度选档，T0 原点线加粗，负时间标签带负号），右半未来区微弱冷色渐变暗示方向。线性映射（20s 量级窗口内快进表现为窗口整体跳变，不压缩）
    - **replay 全程视窗（case 结束后，视频回放器）**：泳道宽度 = 整个 case 虚拟时间全程（快进段仍压缩 6% 窄带），游标默认最左可拖拽全程定位（对话流/车态窗跟随回放）；**横向缩放 ×1~×64**（`zoomReplayView` 锚定游标缩放——游标在视窗内则游标屏幕位置不动，在外则锚定视窗中心不拽回）+ **底部平移滑块**（`clampPanX` 钳制 [0, 1-1/zoom]，zoom=1 禁用）；播放中 `followCursorView` 视窗自动跟随游标（滑出视窗平移居中）；新 run 开始视窗重置 zoom=1。全域分段映射（normal 按时长比例 + 快进窄带）后经 zoom/pan 视窗变换，`domainX` 提供与视窗无关的全域坐标（缩放锚点系）
    - **视窗裁剪统一**：`clipSpanToView`——事件区间 → 视窗内屏幕位置（完全窗外返回 null 不渲染；跨缘两端裁剪 [0,1]；点事件给最小渲染宽度）；live 与 replay 共用一套裁剪，`x()` 不钳位（窗外时间同样可映射，可见性交给裁剪）
    - App.tsx 接线：viewportWidth/replayView 本地状态 + ResizeObserver 宽度上报 + 播放跟随 effect + 新 run 重置 effect；前端 79 vitest（时间刻度测试重写为双模式 + 新增 computeLiveWindowMs/clipSpanToView/clampPanX/zoomReplayView/followCursorView 共 14 个）全通过，vite build 通过

### 🚧 待完成
- [ ] 真实 LLM 端到端测试：fixture cases 批量跑通（builtin scheduled/complex 已验证 100/100）
- [ ] VoiceDeviceDriver 实现（物理设备测试）

---

## 13. 变更记录

| 日期 | 变更 | 说明 |
|------|------|------|
| 2026-06-17 | 初始架构 | Runner 核心设计，确认插话=普通剧本事件 |
| 2026-06-17 | 流式+并发设计 | SUTDriver 流式交互 + 半截话保存 |
| 2026-06-17 | 双层演进模式 | 默认边界驱动 + 显式时间戳锚点覆盖 |
| 2026-06-18 | 扩展测试 Cases | case-008~012：纯边界 / 锚点抢占 / 快进 / 并发 / 负向 |
| 2026-07-24 | 文档重写 | 用图示+直白语言展示时序演进测试全过程 |
| 2026-07-24 | Runner 重写 | time_travel_case_runner → case_runner；SUTBot → TestedAssistant；SUTBotProtocol → AssistantProtocol；删除 CodeBotDriver/SUTDriver 套娃；EventScheduler 用回调模式替代旧 ConcurrentEventScheduler |
| 2026-07-24 | VirtualCar 重写 | devices 为唯一真相源，car_info 只读派生；CAR_INFO_FIELD_MAP 映射表；删除 dict↔devices 双向同步 |
| 2026-07-24 | 假人 prompt 重写 | 去掉退下/打分/max_round 自决等回合制残留，纯剧本驱动 |
| 2026-07-24 | fast_mode | RunnerConfig.fast_mode + EventScheduler.fast_mode，跳过锚点真实等待，长周期测试从 209s 降到 8.9s |
| 2026-07-24 | Judge 模块 | 独立模块（Runner 不调）；trace + nl_assertions → JudgeVerdict；prompt 理解时序演进语义；18 个测试通过 |
| 2026-07-24 | Judge 重写为 judge/ 独立目录 | 从 `case_runner/judge.py` 移到 `judge/` 包（与 `fake_person/` 同级）；拆为 4 文件：models / scoring / prompt / judge；新增 ScoreBreakdown / AssertionType 模型；裁判价值观对齐假人；25 个测试（含打分 8 + 渲染 4 + LLM 评判 9 + 模型/prompt 4） |
| 2026-07-24 | 断言分化 + 打分公式 | `nl_assertions` → `must_pass_assertions`（必过，≥1 条）+ `bonus_assertions`（加分，可选）；线性插值 `60 + 40 * (bonus_passed/bonus_total)`；state_check 算必过项；旧字段保留向后兼容；12 个 fixture cases 全迁移；`overall_passed` 以打分结果为准 |
| 2026-07-24 | RunResult 字段同步 | `RunResult.nl_assertions` → `must_pass_assertions` + `bonus_assertions`；runner.py `_build_result` 和 `build_judge_input_from_run_result` 同步取新字段 |
| 2026-07-24 | TestedAssistant v2 接入修复 + 打断支持 | 修复 import bug（`react_agent_with_task_manager` → `react_agent_with_task_runner`）；改用 `agent.astream()`（旧代码调 `AgentRunner.achat` 但该方法不存在）；`achat_stream` 用 `anyio.CancelScope` 包消费协程，`StreamingReply.interrupt` 真正取消推理（不只放哨兵）；合并 `TimeTravelSUTAgent` 的完整异步回执 system prompt；删除重复的 `TimeTravelSUTAgent` / `create_time_travel_agent` / `run_agent_with_fake_person` 封装；`StreamingReply` 加 `_cancel_scope` 字段；新增 `test_tested_assistant.py`（10 个测试，mock agent 不依赖真 LLM）；测试总数 57 → 67 |
| 2026-08-25 | 时间加速集成到 Runner | `_maybe_accelerate` 方法，基于事件队列判定快进（不需要"静默检测"），快进前 `aupdate_context` 同步助手时间；快进事件记入 Trace |
| 2026-08-25 | 多步快进 + 定时任务不跳过 | Runner 查 `get_pending_scheduled_tasks()` 获取中间停靠点，逐个快进并触发到期任务；`ScheduledTaskManager` + `set_reminder` 工具；`aupdate_context` 检查到期任务并注入系统消息触发主动提醒 |
| 2026-08-25 | aupdate_context 协议升级 | 加 `current_time: datetime | None` 参数 + `str | None` 返回值，支持主动智能测试 |
| 2026-08-25 | 插话打断 Runner 集成 | `_assistant_chat_streaming` 检测下一锚点到达时调用 `reply.interrupt()` + `anyio.CancelScope.cancel()` 真正取消推理，保存半截话 |
| 2026-08-25 | 架构文档更新 | 新增 WorldTick 概念（§3）、注入事件机制（§7.4）、多步快进设计（§7.1）；更新 AssistantProtocol 签名（§11）；同步已完成/待完成列表（§12） |
| 2026-08-25 | 时间演进机制深度梳理 + 实现 | §7.1 扩展：mock_time vs wall_time 两层时间区分、时间偏移修正机制（`offset_recent_tasks` + `_created_at` 防重复偏移）、多步快进 + WorldTick 双重保障。§7.4 更新：WorldTick 事件类型、ContextUpdateResult 结构化返回、注入事件合并、5 秒缓冲（`WORLD_TICK_BUFFER`）全部实现。§12 标记 5 个待办为已完成。修复两个时间相关 bug：(1) 助手回复耗时导致 trigger_time 偏差——`add_task` 传入 `created_at` 并在 `aupdate_context` 中调用 `offset_recent_tasks`；(2) `_created_at` 存 trigger_time 而非创建时间导致重复偏移——改为存 mock_time 创建时间。70 个测试全通过。 |
| 2026-08-25 | 事件流协议 v2 + 四层轨迹命名体系 | 协议从"文本流"进化为"事件流"：`achat_stream` 产出 `AssistantEvent`（TEXT_DELTA / TOOL_CALL / TOOL_RESULT，携带 wall_time）替代 `str`；假人侧新增 `FakePersonEvent`（speak_start / text_delta / speak_done）+ `deliver_fake_person_speech_stream`。确立四层命名：L0 SUT 原生事件 → L1 协议事件（分水岭：接入层责任 vs 平台责任）→ L2 测试轨迹（TraceRecorder 权威记录）→ L3 裁判视图（render_timeline_text 投影）。Runner 新增：TTFT 计算、>2s 流式停顿检测（LONG_PAUSE）、工具调用/返回记录（TOOL_CALL / TOOL_RESULT RecordKind）、假人说话时长（speech_duration）。Judge 视图新增时序标注：`(说了 Xs)` / `(首字延迟 Xs)` / `[工具调用]` / `[工具返回]` / `⚠ 流式停顿`，prompt 声明第 8/9/10 条时序演进语义。§7 更名为五大关键机制，新增 §7.5。 |
| 2026-08-25 | WorldTick 锚点执行时序定稿 + 主动话语时序标注 | 确立两级触发保障：主通道为锚点 drain（`_execute_world_tick` 先记录锚点到达系统事件，`_drain_pending_tasks_near_anchor` 只处理 60s 内任务、5s 缓冲静默推进不记快进），兜底通道为多步快进（无锚点时靠 `get_pending_scheduled_tasks` 停靠触发）。主动话语标注 `(主动, 触发后 X.Xs 开口)`（`UtteranceRecord.is_proactive` + `_aupdate_context_timed` 真实耗时，区别于被动回复的首字延迟）；`_fmt_clock` 格式化快进时间戳（时分秒，跨日附加月-日）。§7.1.3 / §7.4 / §7.5 同步更新为真实 LLM 实测输出（scheduled case，Judge 100/100）。 |
| 2026-08-25 | 自然时间流逝模型重构（取消时间冻结） | `TimelineEngine` 改为锚点对 `(anchor_mock, anchor_wall)` 实时计算 `mock_time`，虚拟时间与真实时间 1:1 连续流逝，唯一跳跃方式是 `accelerate_to`（快进重新锚定）；删除 `advance_to` 与 `offset_recent_tasks`/`_created_at` 偏移修正补丁——助手工具经 `set_time_source` 注入的实时虚拟时间源取当前时刻，trigger_time 天然包含回复耗时；话语区间化（`UtteranceRecord.started_at/ended_at` 必填），打断 = `ASSISTANT_REPLY(is_partial=True)` 半截话（删除 INTERRUPT 记录类型与 `[打断事件]` 渲染行）；调度器 `get_now` 注入虚拟时间源，锚点等待按虚拟距离计算；`wall_to_mock` 把事件流 wall_time 换算进虚拟时间线。71 个测试全通过（新增 test_natural_time_flow_during_reply）。scheduled + complex case 真实 LLM 验证 100/100。 |
| 2026-08-25 | 中立观察者模型（框架不打断被测助手） | 删除锚点到达时 `reply.interrupt()` 主动打断与调度器锚点打断信号（wait_next_anchor_due 等）；假人话语 FIFO + `_feeder_loop` 串行投喂（助手空闲才喂，不阻塞调度器）；`UtteranceRecord` 加 chunk 级 `segments`，`get_overlaps()` 检测重叠窗口；`render_timeline_text` 区间化渲染 + `━━━ 双方同时说话 ━━━` 重叠切片块（不完全重叠只标重叠部分）+ 工具调用/返回配对合并为单条区间记录；时间推进前 `_wait_assistant_idle`；过期任务（gap ≤ 0）立即触发。§2/§6.2/§7.2 全面改写为"插话重叠 + 延迟投喂"。 |
| 2026-08-25 | 迟到 WorldTick 锚点静默跳过 | 注入型锚点被调度器串行回调拖晚、锚定任务已被多步快进停靠（通道 B）先触发时，`_execute_world_tick` 经 `_has_tasks_near_now()` 判定附近无待触发任务即静默返回，不记录冗余"锚点到达"行；两级触发保障改为"先到者生效"。新增回归测试 test_late_world_tick_silently_skipped / test_world_tick_anchor_fires_pending_task。 |
| 2026-08-25 | 中立观察者模型真实 LLM 验证 | scheduled + complex 重跑均 100/100：重叠窗口如实呈现（假人只显示窗口内部分）、插话延迟投喂后双指令正确处理、迟到锚点无冗余记录、定时任务触发点停靠主动提醒、跨时记忆 + 恢复轮 + state_check 通过；scheduled case 断言措辞修正（提醒在 30 分钟触发点触发而非 2h，与多步快进行为一致）。74 个测试全通过。 |
| 2026-08-26 | 即时投喂改造（说完即投） | 删除 FIFO 队列 + `_feeder_loop` 串行投喂（不迎合被测 agent 的空闲等待），改为 `_spawn_stream` 即时投喂：假人话语 `speak_done` 后立即启动后台流任务（`_active_stream_tasks` 集合跟踪，可并发）；助手（不支持打断）多流并行，每条流输出独立记录，重叠由 `get_overlaps()` 呈现——是否中断旧流由被测助手自行决定，框架保持中立观察者；`_wait_assistant_idle` 改为等所有活跃流任务收完；§7.2 更名为"插话重叠 + 即时投喂"；测试断言改为验证并发流重叠（回复2开口早于回复1说完）。 |
| 2026-08-26 | 流式投喂（第一个字即投）+ 插话打断能力可测 | 协议 `achat_stream` 输入从完整文本改为异步文本流（模拟流式 ASR）：第一个 chunk = 用户开口（插话打断时机信号），迭代器耗尽 = 用户说完。Runner 在假人第一个 `text_delta` 即 `_spawn_stream` 启动投喂（`_queue_to_aiter` 队列包装），后续字实时推入，`speak_done` 发 EOF。支持打断的助手在第一个 chunk 中断旧流（`reply.is_interrupted` → trace 记半截话，插话打断能力可测）；不支持的聚合输入后处理（多流并行如实记录）。TestedAssistant 聚合输入（v2_agent 不支持流式输入，如实暴露）。新增 BargeInMockAssistant + test_barge_in_assistant_interrupts_old_stream（旧流半截 + 新流完整）；插话测试改结构性断言（首/末 chunk 到达相隔 ≈ 说话时长 = 逐字流式投喂证明）。75 个测试全通过。 |
| 2026-08-26 | v2_agent 打断行为探测（三模式） | `run_interrupt_probe.py` 扩展 concurrent / serial / cancel 三模式并用真实 LLM 实测：concurrent（异步并发双 astream）= 旧流不中断（插话后仍产出 30 chunk）+ 链路分叉（message_history 顺序颠倒、两轮互不知晓）；serial（同步串行 = AgentRunner._run_agent 行为）= 排队非打断（旧流完整说完才处理新输入，链路一致）；cancel（调用方 interrupt）= 13ms 干净中止旧流。结论：同步/异步不是打断的关键，"取消"才是——v2_agent 底层无打断机制，音频侧插话打断在 TTS 播放层（v2_frontend_voice.py），文字层需接入层补齐。 |
| 2026-08-26 | 接入层插话打断（文字层，不改 aicore 框架） | `tested_assistant.py` 的 `achat_stream` 实现插话打断契约：第一个输入 chunk 到达（用户开口）即 `interrupt()` 旧活跃流（`_active_reply` 跟踪），旧流半截话同步入 `_history`（`［被用户打断，未说完］`/`［被用户打断，尚未开口］`标记，顺序确定），聚合剩余输入后再调底层（v2_agent 不支持流式输入）；被打断轮不写回模型链（丢弃语义，与音频层"丢弃 TTS 输出"对齐）。真实 LLM 验证：插话 13ms 内旧流中止、车态正确执行、history 四条顺序完整、模型链只剩插话轮。新增 test_achat_stream_barge_in_interrupts_old_stream + test_achat_stream_barge_in_skips_finished_old_stream，77 个测试全通过。 |
| 2026-08-26 | 测试过程可视化 M1（实时模式）上线 | `visualizer/` 新模块：旁路事件总线（`event_bus.py`，双时间戳信封 wall_time + mock_time，单订阅者零开销）+ 两层事件（层1 TraceRecorder 落盘即推 8 种 / 层2 Runner 过程事件 case_started / case_finished / fake_person_delta / assistant_delta）+ FastAPI WebSocket 服务器（`run_server.py`，命令-ACK 协议 list_cases / run_case / stop_case，RunContext 事件泵，全局互斥单 run，断连自动停止，挂载 frontend/dist 单端口 8800）+ React 19 前端（对齐 v2_frontend 技术栈：事件即 action 单 reducer 多投影、分段时间映射（快进段压缩 6% 窄带）、重叠说话窗口检测、三面板 RunConsole/ChatStream/TimelineLanes）。端到端联调通过（builtin-complex-combo，fast_mode=False：119 事件流含 acceleration×2）。后端 95 pytest + 前端 29 vitest 全通过。 |
| 2026-08-26 | 信封时间不变式修复（端到端联调发现） | 事件信封 `mock_time` 在 seq 递增序下不倒退（快进只向前跳）：层1 utterance 落盘事件信封时间由 `started_at`（开口时刻）改为 `ended_at`（落盘时刻）——话语进行中的 delta 事件已携带更晚的虚拟时间，回填开口时刻会倒退；话语区间仍在 payload（started_at / ended_at）里，前端投影用 payload 区间不受影响。`case_finished` 信封补当前虚拟时间（原为 None，回放模式无法定位终点）。回归断言写入 test_event_bus.py（信封单调性 + 生命周期事件带虚拟时间）。 |
| 2026-08-26 | 可视化 M1 增强：工具调用全程可见 + long_pause 语义修正 | 对话流面板新增工具卡片（tool_call/tool_result 按 toolName FIFO 配对混排在话语气泡间，显示工具名/参数/返回/耗时/执行中）；时间线工具区间化（call×result 栈式 LIFO 配对成区间 span，与轨迹渲染 _merge_tool_records 策略一致，支持嵌套；未配对 call 渲染"执行中"点事件）；修复 long_pause 误报——工具执行期间（TOOL_CALL→TOOL_RESULT）的 gap 是正常执行时间不算流式停顿（_consume_stream 跟踪上一事件类型排除）；RunConsole 加被测助手 mock/v2 选择（v2=真实 LLM+接入层插话打断，chunk_delay=0.25 拉宽回复窗口）；修复 App.tsx 漏调 client.connect()（WS 从未连接）与 run_server 类名错误（V2AgentTestedAssistant→TestedAssistant）。轨迹渲染侧工具区间（[start→end] [工具] name(args)→result, 耗时）此前已由 _merge_tool_records 支持，无需改。 |
| 2026-08-26 | long_pause 语义修正完整版：工具边界间隙一律不算停顿 + 流式停顿去失败化 | 用户发现"被插话那边有失败停顿"——上一版修复只排除了 TOOL_CALL→TOOL_RESULT，但 TEXT→TOOL_CALL（LLM 决定调工具的思考）和 TOOL_RESULT→TEXT（LLM 看到结果恢复生成）间隙在真实 v2 助手上通常 3-5s，仍被误记为 long_pause，且插话响应恰好含工具调用，误报的红色停顿标记集中在"被插话"处。修正：long_pause 只测文本流内停顿（TEXT_DELTA→TEXT_DELTA 间隔 > 2s），任何一侧是工具事件的间隙一律排除（工具执行+LLM 围绕工具的思考是正常节奏，工具区间已单独可见）；可视化 long_pause 由 tone-fail 红改为 tone-warn 琥珀警示色，图例拆分"流式停顿"/"检查失败"（失败红只留给 state_check 失败等真正错误）。新增测试 test_tool_boundary_gaps_not_long_pause（工具前后思考间隙不报停顿）+ test_text_stream_stall_still_records_long_pause（文本流内真实停顿仍记录，回归保护）+ 前端 warn tone 断言；后端 98 pytest + 前端 32 vitest 全通过。 |
| 2026-08-27 | 运行基建修复 + 多条件导航 case | MockAssistant 从 test_case_runner_e2e.py 提取到生产位置 case_runner/mock_assistant.py（可视化服务器 DemoToolMockAssistant 复用）；修复僵尸 run——_run finally 清全局 _current_run（此前跑完后残留，后续 run_case 被永久拒绝）；run_case 新增 nav_tool_delay 选项（默认 6s）；新增内置 navigation-multi-condition case（多条件导航长耗时工具），两个 6s 工具区间在时间线/对话流可见，T+45s 状态检查验证最终目的地。 |
| 2026-08-27 | 可视化 M1 增强：裁判终局评判面板 + 相对 T0 时间戳 | judge_case WS 命令 → RunContext 保留 run 产物（_current_run/_last_run 双全局）→ _execute_judge（真实 Judge LLM）→ judge_verdict 层3 事件直发发起连接（不走事件泵）；前端 VerdictPanel 在右栏时间线下方（总分/及格徽章/必过+加分+状态检查打分行/每条断言✓✗+裁判理由+证据/pending/error 态，JudgeState 由 consoleReducer 管理）；对话流气泡与工具卡片显示相对 T0 虚拟时间区间（projections.formatTimeRange，气泡用 started_at/ended_at，工具卡片用 call→result mock_time 配对区间）。后端 101 pytest（+3 judge_case）+ 前端 39 vitest（+7）全通过；真实 Judge 端到端验证（builtin-simple-ac 60 分，summary+reasoning 完整）。 |
| 2026-08-27 | 可视化 M1 增强：回放模式 + 虚拟车状态观察窗 | 车态数据链路统一（case_started 携带 initial_car_info 快照 + VirtualCar.on_field_change 钩子旁路发射助手车控增量 car_set_state）；PlaybackState 回放状态机（idle/paused/playing + cursorMs + speed）+ rAF 回放引擎（usePlaybackEngine，单帧 dt 钳制 250ms 防后台 tab 跳变）；时间线拖拽定位（TimeScale.inverseX 非线性反算）+ 倍速控制条（1x~5x）；车态时间机 projectCarState（初值+按游标合并增量，CarStatePanel 展示游标时刻全量状态）；对话流回放裁剪（projectDialogue 按 segments 拼接说到一半的内容、工具卡片执行中、live 气泡不显示）。后端 104 pytest + 前端 50 vitest 全通过；WS 实跑验证。 |
| 2026-08-27 | 可视化 M1 增强：实时增长条 + 工具子泳道 + 面板拖拽布局 | 实时虚拟时钟 useNowTicker（双时间戳外推 nowMs，事件到达自动重锚，100ms 重绘）；live 增长条——reducer live 缓冲记录开口时刻（首个 delta mockTime），projectLiveSpans 投影 [开口, now] 区间，说话开始即见不断变长的虚线脉冲条，落盘后权威区间无缝接管；工具子泳道——projectToolSpans 栈式配对 + 行打包（并行工具分行，执行中条占满整行防错分），TimelineLanes assistant-group 渲染橙色矮条（⚙ 名称 + ⟳/✓）+ call/result 时刻竖线伸进助手泳道底边（直观关联何时开始调用/结束获得结果），执行中右端尾随 nowMs/游标增长，hover 看入参返回耗时；面板拖拽布局——PanelResizer（pointer capture）+ CSS 变量高度 + localStorage 持久化（ttat.rightColumnLayout），右栏三面板用户自行调整适配屏幕。前端 56 vitest（+6）+ 后端 104 pytest 回归全通过；WS 实跑 navigation case 验证（2 组 call/result 配对含 args/result/duration_ms、工具区间夹在承接语与总结语 delta 之间、119 delta 全带 mock_time+wall_time、mock_time 单调）。 |
| 2026-08-28 | 可视化 M1 增强：时间线居中轴 + 未来区预览 + 车态变更来源三色（"劲舞团"式） | buildTimeScale axisMs 居中重标定（当前虚拟时刻轴线恒映射 x=0.5，左半历史从轴线向左长出，右半未来 60s 前瞻窗口；修复段坐标就地 warp 导致的二次 warp 轴线偏离 bug）；case_started 新增 script_plan 剧本时间表（锚点驱动事件 {kind,at,target,label} 升序），前端投影 at>axisMs 的预设事件为半透明金色竖线+无框文字从右向左飞向轴线；record_set_state 新增 source 参数（script=剧本上帝视角/assistant=助手车控/fake_person 预留），CarStatePanel 按来源金色/红色/蓝色加粗键值闪烁 1 秒 + 变更分组临时置顶 1 秒；新增 builtin-god-view 内置 case（混合来源演示）。前端 65 vitest（+5）+ 后端 106 pytest（+2）全通过；WS 实跑三 case 验证。 |
| 2026-08-28 | 可视化 M1 增强：自动终局评判 + 左右面板拖拽 + 时间快进标记 + 导航/媒体独立工具 + 前端源码入库 | run_case 完成自动终局评判（RunContext._auto_judge，结果经事件泵推送后停泵，前端 case_finished 即置 pending；judge_case 保留为手动重评）；PanelResizer 扩展 orientation 双向（对话流/右栏观察区左右拖宽，--left-width CSS 变量 + localStorage 持久化，右栏保底 360px 自适应）；projectDialogue 解析 acceleration 事件渲染快进胶囊条（时长 + T0 区间，快进不再误读为持续对话）；.gitignore 解除前端必要文件忽略（index.html/package.json/package-lock.json/tsconfig.json 等，前端可 clone 运行）；导航/媒体拆为独立工具（demos/v2_agent_to_test/tools/navigation_control.py name="navigation" + media_control.py name="media"，对齐 sgm_tools_v2 工具名，均走 VirtualCar.set_field 落盘；virtual_car_control.py 对齐 69 字段并移除导航/媒体分支；TestedAssistant 工具列表 car_control+navigation+media 三件套）。后端 126 pytest（+20）+ 前端 65 vitest 全通过。 |
| 2026-08-28 | 可视化时间线推倒重写：live 滑动窗口 + replay 缩放视窗双模式 | buildTimeScale 重构为 ScaleOptions 联合类型。live 模式 = 中央轴线滑动窗口（轴线恒 x=0.5，20s 基准窗口按轨道像素宽 25ms/px 自适应，秒级网格线 1-2-5 步长随虚拟时间从右向左流动，T0 原点线加粗；未来预设竖线从右缘飞入渐亮抵达轴线、历史事件块从轴线生成向左移动滑出左缘）；replay 模式 = 全程分段映射（快进 6% 窄带）+ zoom/pan 视窗变换（缩放 ×1~×64 锚定游标、平移滑块钳制 [0,1-1/zoom]、播放自动跟随、新 run 重置）；clipSpanToView 统一视窗裁剪（窗外 null / 跨缘裁剪 / 点事件最小宽度），x() 不钳位。App.tsx 接线 viewportWidth/replayView 状态 + ResizeObserver 上报 + 跟随/重置 effect；styles.css 新增网格线/缩放/平移/未来区渐变。前端 79 vitest（+14）全通过，vite build 通过。 |
