# time_travel_auto_test — 工作上下文

> **三个文档分工**：
> - [`ARCHITECTURE.md`](./ARCHITECTURE.md) — **怎么工作**：架构图、执行流程、核心机制（图示为主）
> - [`CONTEXT.md`](./CONTEXT.md) — **为什么这么设计**：设计原则、决策记录、路径速查（本文件）
> - [`KNOWLEDGE_GRAPH.md`](./KNOWLEDGE_GRAPH.md) — **实体关系**：详细数据模型、类间关系
>
> **维护约定**：本目录下任何实质性设计/实现变更后，须同步更新这三个文档。
> Agent 开始新任务前应优先阅读三个文档。
> **`projects/mind/mem/auto_test_script/` 仅作参考，不在该目录改代码**；演进只在 `time_travel_auto_test` 内进行。

最后更新：2026-08-26（可视化 M1 增强：工具调用全程可见（对话流工具卡片 + 时间线区间化）+ long_pause 语义修正完整版（只测文本流内停顿，工具边界间隙一律不算；可视化 warn 警示色替代失败红）+ 被测助手 mock/v2 选择）

---

## 0. 工作原则（接下来进化的执行准则）

> 在本目录继续研发时，所有改动必须遵守以下四条原则；遇到取舍时按此优先级判断。

1. **多次反思实现是否必要**
   - 动手前先问：这个功能/抽象/字段真的需要吗？现有结构能不能直接覆盖？
   - 写完后回头看：是不是过度设计？有没有更直接的写法？能不能删掉一层间接？
   - 只做"为达成目标最少必要的事"，不为"看起来更完整"而加东西。

2. **能简单实现绝不搞复杂**
   - 优先用最朴素的写法：函数优于类，dict/dataclass 优于自定义继承体系，同步优于异步（除非全双工必需）。
   - 拒绝"为了将来可能需要"的预扩展；真要扩展时再加。
   - 一次只解决一个明确问题，不夹带重构、不夹带风格清理。

3. **高度谨慎，因为我们在研发的是框架**
   - 框架的每一处接口都会被下游用例和被测 Agent 依赖；改动接口 = 改动所有人的代码。
   - 改动前先想清楚：是数据模型变更、接口变更、还是行为变更？三者影响面递增。
   - 任何接口/数据结构变更，必须同步三个文档（ARCHITECTURE / CONTEXT / KNOWLEDGE_GRAPH）。
   - 不轻易新增配置项、不轻易新增可选字段；每个开关都得有明确使用场景。

4. **实现了就立刻设计测试，跑测试**
   - 新功能必须在同一轮提交里附上可运行的测试，不能"先写完再补测试"。
   - 测试要能本地一键跑通（pytest 或 run_xxx.py），失败要能直接定位原因。
   - 改动既有逻辑前先跑一遍现有测试，确认基线；改完再跑确认未回归。
   - 测试不过的代码不算完成，不允许"先合并回头修"。

5. **文档与代码同步，文档之间不打架**
   - 同一个事实只在一个地方写"权威版本"，其他地方只引用、不复述。
   - 当前分工：ARCHITECTURE 讲怎么工作、CONTEXT 讲为什么这么设计 + 工作原则、KNOWLEDGE_GRAPH 讲实体关系。
   - 待办/已完成清单只在 CONTEXT §6 维护，其他文档只引用不重抄。
   - 改代码后顺手检查三个文档是否还准确；发现文档与代码冲突，以代码为准并立刻修文档。

6. **先看文档再动手，先理解再改**
   - 接到任务先读 ARCHITECTURE + CONTEXT + KNOWLEDGE_GRAPH，确认理解一致再写代码。
   - 如果文档和自己的理解不一致，先提出来对齐，不要默默按自己理解改。
   - 改动前能说清楚：改的是哪个模块、影响哪些下游、是否破坏既有接口。

7. **不造重复的轮子，也不强融两套系统**
   - time_travel 和 auto_test 是演进关系，不是合并关系：参考 auto_test 的好东西可以复用/拷贝演进，但不改 auto_test 源码。
   - 同一域概念（如 FakePerson）在新范式下扩充，不另起平行实体、不 rename 制造混淆。
   - 但也不要为了"统一"硬把两套不同范式塞进同一份代码：全双工时序就是全双工时序，不退化成回合制。

8. **没想清楚就问，不要自己脑补**
   - 遇到歧义、缺信息、多种合理理解时，先问清楚再动手，不要凭猜测往下写。
   - 框架研发的代价高、回滚成本大，宁可多一轮提问，也不要走错方向再返工。
   - 问问题时给出自己的理解和候选方案，让用户做选择题而不是填空题。

9. **第一性原理出发，实事求是思考，不要迎合用户**
   - 判断方案对错以代码本身、以事实、以逻辑为准，不因为"用户说了"就附和。
   - 用户说"这块很乱想重写"，先独立读代码评估：是真的乱到要重写，还是有局部问题可改。
   - 用户说"差不多够用了"，也要敢于指出不足：鲁棒性、边界、接口不一致等。
   - 有不同意见直接说出来，给出依据，不为了显得听话而压缩自己的判断。

10. **能用数据模型规范的，不用裸 dict**
    - 除非完全无法预先预见 k/v 的键和值（如自由扩展的环境元数据），否则必须用 Pydantic BaseModel / Enum 定义数据模型，带类型约束和校验。
    - VirtualCar 等核心实体必须有结构化的设备状态定义（温度 ge/le、档位 Enum、门窗状态 Enum），不能退化成 `dict[str, Any]`。
    - 前端 JSON 配置可以传 dict，但运行时必须解析/映射到数据模型实例，由数据模型做唯一真相源。
    - 裸 dict 只允许出现在：JSON 序列化/反序列化的边界、数据模型之间转换的中间态、确实无法预定义结构的元数据。

11. **主动智能必须能自主触发，不引入 polling 方法**
    - 框架的时序演进机制天然支持测主动智能——时间/车辆/人条件构建、侦听、检测、评判都是现有机制的自然组合，无需专门适配。
    - `aupdate_context(car_info, current_time)` 是通知助手"条件变了"的普世方法，助手在内部自主决定要不要行为（说话/车控/调工具），不暴露 `atry_proactive_speak` 这种特殊接口。
    - 主动智能的本质是"某时间点助手自主产生行为"——框架本来就在记录所有时间点的所有行为，所以天然能测。

12. **一切为了更精细地测试被测助手**
    - 框架的所有机制（流式、打断、时间快进、主动智能支持）都是为了以更精细的角度/维度测试被测助手，不是为了框架自身的"完整性"。
    - 设计取舍时优先考虑"能不能测到更多助手的维度"而不是"框架看起来更完善"。

13. **裁判价值观对齐假人**
    - Judge 评判时要从假人视角出发，不是冷冰冰的功能性判定。
    - Judge prompt 必须注入假人人设信息，让 LLM 代入该用户视角评判助手表现（是否体贴、是否到位、是否贴合该用户偏好）。
    - 同一个助手回复对不同假人可能有不同评判（着急的上班族 vs 挑剔的老用户）。

14. **打分公式：必过 + 加分 线性插值**
    - 必过项任一不过 → 0 分（state_check 也算必过项）
    - 必过全过 + 加分全过 → 满分 100
    - 必过全过 + 加分全没过 → 及格分 60
    - 必过全过 + 加分部分过 → `60 + 40 * (加分通过比例)`
    - 无加分项时，必过全过即满分
    - 及格分 60 / 满分 100 写死为常量，不抽配置（§0.2 简单优先）

---

## 1. 项目定位

在 `projects/experiments/time_travel_auto_test` 中构建**新一代车载助手场景化自动测试**的数据模型与演绎框架。

### 与现有 auto_test 的关系

| | auto_test（旧） | 本实验（time_travel） |
|---|----------------|----------------------|
| 范式 | LLM 假人「话剧式」多轮 ping-pong | **时序剧本事件** + **虚拟主体驱动器** |
| 对话 | 回合制；假人 LLM 读 `expected_script` | **实时全双工**（支持打断） |
| 断言 | 主要 `nl_assertion` + Judge LLM | 剧本内 **k/v 状态断言** + NL 断言 |
| 时间 | per-session `mock_time` | `event_t0_plus_timedelta` 相对场景 t0 演进 |
| 插话 | 不支持 | 锚点事件精确插入 + 半截话保存 |
| 长周期 | 测不了 | 时间加速（静默 → 快进） |

### 假人：同一概念在新范式下的扩充

**假人始终是同一个域概念**——场景里可扮演、可被剧本驱动的虚拟乘客/用户。
time_travel 是在 auto_test 假人基础上**扩充 schema + 事件驱动**，不是另起一套平行实体。

| 层次 | auto_test 已有 | time_travel 新增 |
|------|----------------|------------------|
| **数据** | 分散在 `context_config["user_profile"]` 字符串里 | 构造 `FakePerson` 时传入 profile / state / intent / event_memory |
| **剧本动作** | 隐含在 `expected_script` + 首句冷启动 | 显式 `FakePersonAction` + `FakePersonScriptEvent` |
| **演绎过程** | `FakePerson` 类 = LangGraph LLM 演员 | `FakePerson.perform` 消费剧本事件；speak 在内部完结 |

**整合时：不 rename**。本目录 `FakePerson` 与 auto_test 同名类是同一域概念在新范式下的完整实现（人设 + 剧本 + LLM）。

### 可复用 vs 不应照搬（来自 auto_test）

- **可复用**：`AnyBotToTest` 协议、外部 API 重试、Judge/ReportWriter、火山记忆集成、并发与进度条
- **不应照搬**：`aauto_chat_test` 的 while 循环（回合制 + 退下终止 + 假人内嵌打分）；`expected_script` 过载（同时喂假人 LLM 和 Judge）

---

## 2. 核心设计原则（已达成共识）

### 2.1 概念与抽象

1. **概念 = schema + 过程**：数据结构可与行为同文件，但**不为抽象而抽象、不为拆分而拆分**；第一优先级是容易理解。
2. **剧本事件驱动演绎**：每个事件有 `event_t0_plus_timedelta`、`target`、动作。
3. **`event_type` 字段**：主要为 **JSON 文件导入/导出** 的 discriminator；Python 运行时优先 `isinstance(event, FakePersonScriptEvent)` 等。子类用 `Literal[ScriptEventType.X]` 覆写基类字段是刻意设计。
4. **双层演进**：
   - 边界驱动（默认 90%）：`event_t0_plus_timedelta = None`，上一轮结束立即执行下一轮
   - 锚点驱动（覆盖 10%）：`event_t0_plus_timedelta` 不为 `None`，精确时间点执行，可打断边界演进
5. **state_check 断言也是剧本事件**（`action_type = state_check`），适用于**可结构化断言**的主体（现阶段主要是虚拟车 k/v）；不是平行体系。

### 2.2 虚拟车

6. **虚拟车 state_check 只有 k/v**（`expected_fields: dict`），无自然语言整体预期。
7. **虚拟车状态以 `devices: VirtualCarDevices` 为唯一真相源**（结构化 Pydantic 模型，带类型约束和校验，见 §0.10）；`car_info: dict[str, Any]` 是只读派生视图，供假人 prompt 和 JSON 导出使用。前端 JSON 通过 `CAR_INFO_FIELD_MAP` 映射表解析到 devices 实例，运行时不再有 dict↔devices 双向同步。
8. **虚拟车 `set_state` 分工（Authoring 约束）**：
    - **助手车控结果**（空调、车门、导航目的地、媒体等）：须由被测助手程序调 `VirtualCar` 暴露的车控接口写入 devices；用例里**禁止**用剧本 `set_state`「上帝之手」代写，验收走 `virtual_car_state_check_assertions`。
    - **外部世界演进**（驾驶员踩油门、挂 D 档上路等助手不应伪造的变化）：可用剧本 `set_state` 模拟（也走 CAR_INFO_FIELD_MAP 映射到 devices）。
9. **环境事件**可直改环境（预留）；现阶段剧本 union 不含 `EnvironmentScriptEvent` 的常规使用。

### 2.3 假人

10. **人设 / 人物状态**先用**自然语言字符串**；`role_id` 单独字段。**座位等座舱信息**在虚拟车/环境状态里，假人通过感知读取，不冗余存于 `FakePerson`。
11. **假人 `event_memory`**：预配置的事件记忆条目；与 **`profile`（人设）** 区分——后者是固有预设，等价于 auto_test 里原先的 user_profile，**不再单独设 `memory` prompt 变量**。
12. **假人 prompt 变量 `text_script`**：time_travel 侧对齐 `TestCase.text_script`；参考 auto_test 的 `FAKE_DRIVER_PROFILE_TEMPLATE` 时在本目录复制/演进，**不修改** `auto_test_script`。
13. **假人 `speak` 只有 `content`**（固定台词 or `None` 自主发挥）；**不要** `wake_assistant`（是否唤醒由会话层推断，如是否首条 speak）。
14. **假人 Action** 与 `FakePerson` 同在 `fake_person/models.py`；现阶段**仅 speak**；不含 `state_check`。
15. **假人不做 state_check**：`state` / `intent` 为自然语言、不可穷举、难以可靠 code 断言；假人侧预期走 **`must_pass_assertions` + `bonus_assertions` + Judge**（与域模型文档一致）。

### 2.4 TestCase 与 Runner

16. **TestCase 存储分家 vs Runner 合并**：`script_events` 与 `virtual_car_state_check_assertions` 在 case 层语义分家（演绎 vs 车态 k/v 断言）；Runner 运行时按 `event_t0_plus_timedelta` **合并**成同一时间线，state_check 本质上仍是剧本事件。
17. **TestCase.t0**：可选的场景起始时间（ISO 8601）；优先级：传入参数 > `case.t0` > `datetime.now()`；支持模拟"周五 18:00"等场景。
18. **ActionType**（`perform` | `state_check`）定义在 `script_events/script_event.py`。
19. **助手侧无剧本事件**（被测客体）；不单独做助手状态断言，盯假人 + 虚拟车结果 + NL 断言。
20. **断言分化（2026-07-24 升级）**：`nl_assertions` 字段升级为 `must_pass_assertions` + `bonus_assertions`。旧 `nl_assertions` 字段保留做向后兼容，导入时自动迁移到 `must_pass_assertions`。`must_pass_assertions` 至少一条非空字符串；`bonus_assertions` 可选。state_check 算必过项。

### 2.5 主动智能测试（2026-07-24 新增）

> 本节是关键理解推进，从"助手被动回复"模型进化到"助手有主动智能"模型。

20. **主动智能的本质**：助手内部有触发机制（定时任务 / 事件循环 / 条件监听），条件满足时自主开口说话或执行动作——不是被外部"你有没有话说"的 polling 问出来的。

21. **主动智能测试 = 条件构建 + 侦听 + 检测 + 评判**（四段式）：
    - **条件构建**（通过剧本事件）：时间条件（`event_t0_plus_timedelta`）、车辆条件（`VirtualCarPerformScriptEvent`）、环境条件（预留）、人条件（`FakePersonScriptEvent` 让假人先说"30分钟后提醒我"）。
    - **侦听**：被动观察助手有没有自主行为，不是主动询问。Runner 通知助手"条件变了"，然后等助手自己决定要不要动。
    - **检测**：`state_check` 剧本事件做结构化 k/v 验证（如助手默默开了空调 → 车态变了）。
    - **评判**：全过程送 Judge，裁判看带时间线的 trace 判定"助手有没有在期望条件下主动做对的事"。

22. **被测助手的可测试性要求**：要测主动智能，助手必须满足：
    - **时间作为可注入依赖**：关键决策不能用 `datetime.now()`，必须接收 `aupdate_context(car_info, current_time)` 注入的时间。
    - **内部定时任务可在注入时间时触发**：不能靠 `asyncio.sleep(real_time)`，必须能在收到时间更新时检查到期任务并触发。
    - 不满足这两条的助手无法测主动智能——这是合理的可测试性要求，和后端服务测试时 mock 数据库连接同理。

23. **快进与主动智能的关系**：时间加速跳到 T+n 时，**必须先通过 `aupdate_context` 把新时间注入助手**，否则助手内部时钟没动、定时任务不会触发——这正是"为什么快进必须同步助手时间"的根本原因。
    - 顺序：`accelerate_to(target)` 之前先 `assistant.aupdate_context(car_info, current_time=target)`。
    - 助手收到新时间后内部触发到期任务，主动说话内容通过返回值或车控工具副作用体现，Runner 被动收集。

24. **不要新增 `atry_proactive_speak` 这种 polling 方法**（已否决的设计）：
    - 不普世：要求助手把内部触发逻辑暴露成接口方法，大多数助手封装对接困难。
    - 不本质：主动智能是"条件满足自动触发"，不是"被问起才想起"。
    - 正确姿势：复用 `aupdate_context` 通知条件变化，让助手内部自主决定要不要行为。

### 2.6 时间加速策略（2026-07-24 初版，2026-08-25 修订）

25. **快进触发判定不需要"N秒静默"**：事件队列本身就是"是否有人会说话"的充分信息源。
    - 开口说话的角色只有假人（剧本事件触发）和助手（假人喂话触发）。
    - 只要下一事件还没到，就没人会说话——**确定**，不需要"等60秒确认"。
    - 旧设计 `TimelineEngine.should_accelerate` 的"静默检测"思路被否决：`record_activity` / 静默计时器是不必要的复杂度。

26. **快进触发策略（简化版）**：每次"一轮对话活动结束"后判定
    - `next = scheduler.peek_next()`
    - ① `next is None` → Case 结束
    - ② `next 是边界事件` → 立即执行，不快进
    - ③ `next 是锚点事件`：
        - `gap = next.anchor_time - current_time`
        - `gap ≤ 阈值（60s）` → 正常等 gap 秒
        - `gap > 阈值` → 快进到 anchor_time（确定没人会说话）
    - 快进前必须 `assistant.aupdate_context(car_info, current_time=target)` 同步助手时间（见 §2.5.23）。

27. **state_check 事件不算"对话活动"**：车态变更和状态检查不构成对话延续，不影响快进判定。

28. **多步快进（2026-08-25 新增）**：当助手有 pending 定时任务时，不能一步跳到 target
    - Runner 快进前通过 `assistant.get_pending_scheduled_tasks()` 查询 pending 定时任务
    - 在 `[current, target]` 区间内的触发时间作为"中间停靠点"
    - 按时间排序后逐个快进：`当前 → 中间停靠点1 → 中间停靠点2 → ... → target`
    - 每个中间停靠点触发一次 `aupdate_context`，助手检查到期任务并主动提醒
    - 避免一步跳过定时任务触发时间，确保 Trace 时间戳正确
    - `get_pending_scheduled_tasks` 是 duck typing 接口（不在 `AssistantProtocol` 中强制要求），助手可选实现

29. **WorldTick 概念（2026-08-25 新增）**：时间线上的"停靠点"——没有执行主体，只表示"时间演进到此刻必须停一下"
    - 来源：剧本显式定义（`event_type: world_tick`）/ 被测助手运行时注入（定时任务触发时间）
    - 当前阶段：中间停靠点通过 `get_pending_scheduled_tasks()` 查询实现
    - 未来方向：`aupdate_context` 返回结构化 `ContextUpdateResult`，内含 `injected_events: list[WorldTick]`，Runner 将 WorldTick 注入事件队列统一调度

### 2.7 打分机制（2026-07-24 新增）

30. **断言分化为必过 + 加分**：
    - **必过项**（`must_pass_assertions`）：必须通过，任一不过 → 0 分。state_check 算必过项。
    - **加分项**（`bonus_assertions`）：可选，过得越多分数越高。
    - Schema 校验：`must_pass_assertions` 至少一条非空字符串；`bonus_assertions` 可选。

31. **打分公式（线性插值，§0.14）**：
    - `score = 0` 如果必过项有失败（含 state_check 失败）
    - `score = 100` 如果必过全过且无加分项
    - `score = 60 + 40 * (bonus_passed / bonus_total)` 如果必过全过且有加分项
    - 及格线：`score >= 60`
    - `overall_passed` 以打分结果为准，LLM 返回的 `overall_passed` 不覆盖

32. **Judge 模块独立于 Runner**（方案 B）：Runner 只负责跑出 trace，Judge 是独立步骤。理由：
    - Runner 职责单一（跑剧本）
    - Judge 可独立迭代（prompt 调优、模型切换）不影响 Runner
    - 可多个 Judge 评判同一 trace
    - 失败的 case 也可能有 trace，Judge 仍可评判

33. **Judge prompt 只含读懂 trace 的机制常识，不写死行为对错**（2026-08-26 中立化修订）：让 LLM 知道——
    - 时间快进不是剧情断裂（是正常机制）
    - 双方同时说话是中立观察者的如实记录（不是任何一方出错）
    - 半截话成因区分：插话打断=正常机制呈现；超时截断=回复未在时限内完成
    - 快进后无假人说话时助手开口 = 主动开口机制（不是异常）
    - state_check 已自动判定，不重复评
    - **评判标准完全以断言为准**：什么通过什么不通过取决于被测对象和用例断言的要求，prompt 不预设"该合作容忍还是该中止响应""该不该扣分"等行为模板（平台中立原则）
    - **裁判价值观对齐假人**：从假人视角评判（§0.13）

34. **Judge 输出结构化**：`JudgeVerdict`（含 `score` / `score_breakdown` / `assertion_results` / `summary`）。每条 `AssertionResult` 含 `assertion_type`（must_pass/bonus）、`passed`、`reasoning`、`evidence`（引用 trace 中的具体事件）。

35. **Judge 容错**：JSON 格式重试（`judge_format_max_retries`）+ 外部 API 重试（`external_api_max_retries`）。全失败兜底返回 `JudgeVerdict`（所有断言 false，`raw_response` 保留原始回复）。

---

## 3. 当前代码结构

```
time_travel_auto_test/
│
├── 📄 ARCHITECTURE.md          ← 架构 + 流程图
├── 📄 CONTEXT.md               ← 本文件（设计原则 + 决策）
├── 📄 KNOWLEDGE_GRAPH.md       ← 知识图谱（实体关系）
│
├── 📦 case_schema.py           ← TestCase + JSON 批量导入
├── 📦 script_events/
│   └── script_event.py         ← ActionType + ScriptEvent + 虚拟车/环境动作
├── 📦 fake_person/
│   ├── models.py               ← 假人：Action schema + FakePerson（纯剧本驱动）
│   └── llm_prompt.py           ← 假人 prompt 模板（无退下/打分残留）
├── 📦 virtual_car/
│   ├── models.py               ← VirtualCar（devices 真相源 + car_info 只读派生）
│   └── car_devices.py          ← CarDevices（空调/座椅/门窗/灯光/媒体/导航）
├── 📦 judge/                   ← Judge 终局评判（独立模块，与 fake_person/ 同级）
│   ├── __init__.py             ← 公开 API 汇总
│   ├── models.py               ← JudgeInput / JudgeVerdict / AssertionResult / ScoreBreakdown
│   ├── scoring.py              ← 打分公式（必过 + 加分 → 0-100 分）
│   ├── prompt.py               ← JUDGE_SYSTEM_PROMPT + render_timeline_text
│   └── judge.py                ← Judge 类主逻辑 + build_judge_input_from_run_result
│
├── 📦 case_runner/             ← Runner 核心框架
│   ├── __init__.py             ← 公开 API 汇总
│   ├── runner.py               ← CaseRunner 主调度器 + RunnerConfig + RunResult
│   ├── scheduler.py            ← EventScheduler（heapq + asyncio.Event + fast_mode）
│   ├── timeline.py             ← TimelineEngine + 快进接口
│   ├── dialogue.py             ← DialogueManager + BoundaryDetector
│   ├── trace.py                ← TraceRecorder（时间切片 + 半截话）
│   └── assistant_protocol.py   ← AssistantProtocol + StreamingReply
│
├── 📦 demos/                    ← 被测 Agent 实现
│   ├── tools/
│   │   └── virtual_car_control.py  ← VirtualCarControlTool（被测 Agent 调用）
│   └── v2_agent_to_test/
│       ├── __init__.py         ← 公开 API（导出 TestedAssistant）
│       ├── tested_assistant.py ← TestedAssistant（实现 AssistantProtocol，基于 aicore v2 ReactAgentWithTaskRunner）
│       └── tools/
│           └── scheduled_tasks/
│               ├── __init__.py     ← 公开 API
│               ├── manager.py      ← ScheduledTaskManager（定时任务存储+到期检查）
│               └── reminder_tool.py ← create_reminder_tool（set_reminder 工具）
│
├── 📦 visualizer/               ← 测试过程可视化（M1 实时模式）
│   ├── event_bus.py            ← 旁路事件总线（双时间戳信封：wall_time + mock_time）
│   ├── run_server.py           ← FastAPI + WebSocket 服务器（命令-ACK + 事件流推送，端口 8800）
│   └── frontend/               ← React 19 + Vite + TS 前端（npm run dev / build）
│
└── 📦 test/                     ← 测试（98 个 pytest + 32 个 vitest 全通过）
    ├── cases/
    │   └── fixture_cases.json  ← 12 个 fixture cases
    ├── test_virtual_car_v2.py  ← VirtualCar 单元测试（9 个）
    ├── test_scheduler_v3.py    ← EventScheduler 单元测试（6 个）
    ├── test_case_runner_e2e.py ← CaseRunner 端到端测试（mock assistant，含插话/重叠/定时回归）
    ├── test_case_schema.py     ← TestCase schema 测试（5 个）
    ├── test_fixture_cases_json.py ← fixture cases 导入/导出测试（4 个）
    ├── test_judge.py           ← Judge 评判测试（27 个，含打分 8 + 渲染 5 + LLM 评判 10 + 模型/prompt 4）
    ├── test_tested_assistant.py ← TestedAssistant 单元测试（mock agent）
    ├── test_event_bus.py       ← 事件总线 + 层1/层2事件发射测试（11 个）
    └── test_run_server.py      ← WS 服务器命令/事件流测试（4 个，真实 uvicorn 线程）
```

### 3.1 关键模块速查

| 模块 | 核心类 | 职责 |
|------|--------|------|
| `case_schema.py` | `TestCase` / `FakePersonInfo` / `VirtualCarInfo` | 场景 schema + JSON 导入 |
| `script_events/script_event.py` | `ScriptEventBase` + 4 个子类 | 剧本事件定义（假人/虚拟车 perform/state_check/环境预留） |
| `fake_person/models.py` | `FakePerson` + `FakePersonAction` | 假人 = 人设 + 剧本 + LLM 自主发挥 |
| `virtual_car/models.py` | `VirtualCar` / `VirtualCarDevices` | 虚拟车 = devices 真相源 + car_info 只读派生视图 |
| `case_runner/runner.py` | `CaseRunner` / `RunnerConfig` / `RunResult` | 主调度器（事件回调模式） |
| `case_runner/scheduler.py` | `EventScheduler` / `ScheduledEvent` / `EventSource` | heapq 优先队列 + asyncio.Event 零轮询 + fast_mode |
| `case_runner/timeline.py` | `TimelineEngine` | 虚拟时间 + 静默检测接口 + 快进接口 |
| `case_runner/dialogue.py` | `DialogueManager` / `BoundaryDetector` | 边界驱动 + 边界检测 |
| `case_runner/trace.py` | `TraceRecorder` / `TraceSlice` / `UtteranceRecord` | 时间切片 + 半截话保存 |
| `case_runner/assistant_protocol.py` | `AssistantProtocol` / `StreamingReply` | 被测助手接入协议 + 流式回复 |
| `judge/models.py` | `JudgeInput` / `JudgeVerdict` / `AssertionResult` / `ScoreBreakdown` / `AssertionType` | Judge 数据模型 |
| `judge/scoring.py` | `compute_score` | 打分公式（必过 + 加分 → 0-100 分） |
| `judge/prompt.py` | `JUDGE_SYSTEM_PROMPT` / `render_timeline_text` | Judge prompt + trace 渲染 |
| `judge/judge.py` | `Judge` / `build_judge_input_from_run_result` | Judge 类主逻辑 + 便捷工具 |
| `demos/v2_agent_to_test/tested_assistant.py` | `TestedAssistant` / `DEFAULT_SYSTEM_PROMPT` | 参考实现（实现 AssistantProtocol，基于 aicore v2 `ReactAgentWithTaskRunner.astream()` + `anyio.CancelScope` 打断） |
| `demos/v2_agent_to_test/tools/scheduled_tasks/manager.py` | `ScheduledTaskManager` / `ScheduledTask` | 定时任务存储 + 到期检查 + pending 查询 |
| `demos/v2_agent_to_test/tools/scheduled_tasks/reminder_tool.py` | `create_reminder_tool` | `set_reminder` 工具（供被测 Agent 调用） |
| `demos/tools/virtual_car_control.py` | `VirtualCarControlTool` | 被测 Agent 调用的车控工具 |
| `visualizer/event_bus.py` | `EventBus` | 旁路事件总线（双时间戳信封，单订阅者零开销；信封 mock_time 单调性不变式） |
| `visualizer/run_server.py` | `RunContext` + FastAPI app | WS 服务器（命令-ACK + 事件流推送；内置 7 个 demo case；assistant_kind: mock/v2） |
| `visualizer/frontend/src/app/projections.ts` | `projectDialogue` / `buildTimeScale` / `computeOverlaps` | 纯函数投影（分段时间映射 + 重叠说话窗口检测） |

---

## 4. 剧本事件 schema 速查

```
ScriptEventBase（公共字段）
  event_t0_plus_timedelta: Optional[timedelta]   ← None = 边界驱动
  event_type: ScriptEventType                    ← JSON tag
  target: str                                    ← userA / car / world

├── FakePersonScriptEvent          → action: FakePersonAction（discriminated union，当前仅 SPEAK）
├── VirtualCarPerformScriptEvent   → action: VirtualCarPerformAction（discriminated union，当前仅 SET_STATE）
├── VirtualCarStateCheckScriptEvent → action: VirtualCarStateCheckAction（state_check）
└── EnvironmentScriptEvent         → 预留，不在 ScriptEvent 常规路径

联合类型：
  ScriptPerformEvent = FakePersonScriptEvent | VirtualCarPerformScriptEvent
  ScriptEvent = FakePersonScriptEvent | VirtualCarPerformScriptEvent | VirtualCarStateCheckScriptEvent
  VirtualCarScriptEvent = VirtualCarPerformScriptEvent | VirtualCarStateCheckScriptEvent
```

### Action 类型对照

**假人 Action**（FakePersonAction discriminated union，`kind` 区分）：

| kind | action_type | 说明 |
|------|-------------|------|
| speak | perform | `content: str \| None`（固定台词；None = LLM 自主发挥） |
| *未来* | perform | MANUAL_CONTROL / STATE_CHANGE / GESTURE |

**虚拟车 perform Action**（VirtualCarPerformAction discriminated union，`kind` 区分）：

| kind | action_type | 说明 |
|------|-------------|------|
| set_state | perform | `fields: dict[str, Any]` 写入 car_info，至少一项 |
| *未来* | perform | SIMULATE_BUTTON / SIMULATE_SENSOR |

**虚拟车 state_check Action**（独立事件类型，不走 discriminated union）：

| action_type | 说明 |
|-------------|------|
| state_check | `expected_fields: dict[str, Any]`，至少一项 |

---

## 5. TestCase 字段速查

```python
TestCase(
    id="case-001",
    case_name="有点热",
    t0=datetime(2025, 1, 3, 18, 0),  # 可选，ISO 8601
    max_round=8,
    fake_persons=[FakePersonInfo(role_id="userA", profile="张三…")],
    virtual_car=VirtualCarInfo(car_info={"车内温度": "28摄氏度"}),
    script_events=[...],                                   # perform 事件
    virtual_car_state_check_assertions=[...],              # state_check 事件
    text_script="…",                                       # 假人 prompt 参考
    must_pass_assertions=["助手应帮助用户降温"],           # 必过断言（≥1 条，任一不过 → 0 分）
    bonus_assertions=["助手应主动询问期望温度"],           # 加分断言（可选，过得越多分数越高）
    case_description="...",
    tags=[...],
)
```

| 字段 | 说明 |
|------|------|
| `t0` | 场景起始时间（可选）；优先级：传入参数 > `case.t0` > `now()` |
| `fake_persons` | 假人初始信息 `FakePersonInfo`（≥1） |
| `virtual_car` | 虚拟车初始信息 `VirtualCarInfo` |
| `script_events` | 剧本时间线（仅 perform 演绎事件） |
| `virtual_car_state_check_assertions` | 仅 state_check 事件；**不得**出现在 `script_events` 中 |
| `text_script` / `must_pass_assertions` / `bonus_assertions` / `case_description` / `max_round` / `tags` | 判据与元数据 |

**JSON 批量导入**：顶层 `[case, …]`、`{"cases": [...]}` 或单个 case 对象均可。
**工具函数**：`load_test_cases_from_json` / `load_test_cases_from_json_file` / `dump_test_cases_to_json`

**Validator 验证**：
- `must_pass_assertions` 至少一条非空（旧 `nl_assertions` 导入时自动迁移）
- `role_id` 不重复
- 假人事件 target 须在 `fake_persons` 中且为 perform
- 虚拟车事件 target 须为 `'car'`

---

## 6. 已知 WIP / 待办

### 已完成

- [x] 剧本事件 BaseModel + JSON `event_type` discriminator
- [x] 假人 / 虚拟车 Action schema
- [x] 假人 `FakePerson`（人设 + perform + prompt；纯剧本驱动，无退下/打分残留）
- [x] TestCase 场景 schema（`fake_persons` / `virtual_car` 初始化 + JSON 导入）
- [x] VirtualCar 重构：devices 为唯一真相源 + CAR_INFO_FIELD_MAP 映射 + car_info 只读派生视图
- [x] VirtualCarControlTool 车控工具（解析指令 + 操作 devices）
- [x] TestedAssistant 被测助手（基于 aicore v2 ReAct，实现 AssistantProtocol）
- [x] AssistantProtocol + StreamingReply（流式回复 + 打断）
- [x] EventScheduler（heapq 优先队列 + asyncio.Event 零轮询 + fast_mode）
- [x] TimelineEngine（虚拟时间 + 静默检测接口 + 快进接口）
- [x] DialogueManager + BoundaryDetector
- [x] TraceRecorder（时间切片 + 半截话保存 + summary）
- [x] CaseRunner 主调度器（事件回调模式，完整 run() 流程）
- [x] 12 个 fixture cases（覆盖所有演进模式）
- [x] 端到端测试：8 个 case 通过 mock assistant 验证（含长周期 fast_mode）
- [x] Judge 终局评判模块（独立目录 `judge/`）：必过+加分打分机制；prompt 理解时序演进语义 + 对齐假人价值观；25 个测试通过（mock LLM）
- [x] 断言分化：`nl_assertions` → `must_pass_assertions` + `bonus_assertions`；旧字段向后兼容自动迁移；fixture_cases.json 已迁移
- [x] TestedAssistant v2 集成（流式 + 打断）：修正 `react_agent_with_task_manager` → `react_agent_with_task_runner` 导入 bug；改用 `agent.astream()` 直接迭代（不走 `AgentRunner` 常驻模式）；`achat_stream` 用 `anyio.CancelScope` 包生产者协程，`StreamingReply.interrupt()` 调 `cs.cancel()` 真正取消推理；合并 `TimeTravelSUTAgent` 的 7 条异步回执 system prompt；删除重复的 `v2_agent_to_test.py`；`VirtualCarControlTool` 接入虚拟车（Runner 共享 `VirtualCar` 实例）；10 个单元测试通过（mock agent）
- [x] **`aupdate_context` 协议升级**：加 `current_time: Optional[datetime]` 参数；返回值 2026-08-25 起从 `Optional[str]` 升级为 `ContextUpdateResult(proactive_text, injected_events)`；TestedAssistant / MockAssistant 全部升级；3 个新单测覆盖时间加速触发、主动智能返回、流式打断
- [x] **时间加速实际集成**：`Runner._maybe_accelerate` 在锚点距 mock_time > 阈值（默认 60s）时快进；快进前调 `aupdate_context(current_time=target)` 通知助手（主动智能测试核心）；`EventScheduler` 接 `acceleration_threshold` 参数，远期锚点跳过真实等待；`RunnerConfig` 加 `enable_acceleration` / `acceleration_threshold`
- [x] **插话打断的 Runner 主循环集成**：`_assistant_chat_streaming` 用 `asyncio.wait` 并行等回复完成 / 下一锚点到达；锚点先到时调 `reply.interrupt()` 保存半截话（早期记为 INTERRUPT 类型，2026-08-25 自然流逝重构后统一为 `ASSISTANT_REPLY + is_partial=True`，无独立打断事件行；**2026-08-25 晚被中立观察者模型取代**——框架不再因插话打断助手，interrupt 仅保留流卡死超时兜底）
- [x] **真实 LLM 端到端 demo**：`demos/run_e2e_demo.py` 支持 7 种 case 来源（builtin / builtin-accel / llm-speak / interrupt / scheduled / complex / fixture）；完整链路 TestedAssistant + CaseRunner + Judge；命令行参数 `--case` / `--case-id` / `--no-judge` / `--no-streaming` / `--fast-mode` / `--show-prompt`；Runner 暴露 `trace` 属性供 Judge 构造输入
- [x] **修复 `virtual_car_control.py:260`**：已确认新版 VirtualCar 的 devices 是真相源、car_info 是只读派生视图，无需手动同步（注释已说明）
- [x] **TestedAssistant 主动智能**：`aupdate_context` 收到 `current_time` 时检查 `ScheduledTaskManager` 到期任务，注入系统消息触发 Agent 主动提醒；`get_pending_scheduled_tasks` 暴露 pending 任务供 Runner 多步快进（2026-08-25）
- [x] **多步快进 + 定时任务不跳过**：Runner 在 `_maybe_accelerate` 中查 `get_pending_scheduled_tasks()` 获取中间停靠点，逐个快进并触发到期任务（2026-08-25）
- [x] **`set_reminder` 工具**：`ScheduledTaskManager` + `create_reminder_tool`，被测助手可通过工具调用设置定时提醒（2026-08-25）
- [x] **自然时间流逝模型重构**（2026-08-25）：取消"助手回复期间虚拟时间冻结"假设，虚拟时间与真实时间 1:1 连续自然流逝（`TimelineEngine` 锚点对 + `mock_time` 实时计算）；删除 `advance_to` / `offset_recent_tasks` / `_created_at` 偏移修正补丁；话语区间化（`UtteranceRecord.started_at/ended_at` 必填，经 `wall_to_mock` 换算）；打断 = 半截话（删除 INTERRUPT 记录类型）；71 个测试全通过
- [x] **WorldTick 事件类型 + 注入事件机制**（2026-08-25）：`ScriptEventType.WORLD_TICK` + 5 秒缓冲（`trigger_time - WORLD_TICK_BUFFER`）+ 两级触发保障（`_execute_world_tick` 锚点 drain 主通道 + 多步快进兜底）；`aupdate_context` 返回 `ContextUpdateResult(proactive_text, injected_events)`；Runner `_handle_context_update` 将注入 WorldTick 转 `ScheduledEvent`（`original_index=-1`）合并进事件队列
- [x] **真实 LLM 验证 scheduled + complex case**（2026-08-25）：定时任务不跳过（trigger_time 天然含回复耗时，无偏移补丁）+ 主动提醒准时触发 + 插话打断半截话 + 快进 + 跨时记忆 + 恢复轮，均 Judge 100/100
- [x] **中立观察者模型**（2026-08-25 定稿）：框架不打断被测助手、不截断输出流——删除锚点打断逻辑与调度器打断信号；假人话语 FIFO + `_feeder_loop` 串行投喂；话语/工具事件区间化（started_at/ended_at/chunk 级 segments）；`get_overlaps()` 重叠检测 + `━━━ 双方同时说话 ━━━` 切片渲染（不完全重叠只标重叠部分）；工具调用/返回配对合并；时间推进前 `_wait_assistant_idle`；过期任务立即触发
- [x] **迟到 WorldTick 锚点静默跳过**（2026-08-25）：锚点被串行回调拖晚、任务已被多步快进停靠先触发时，`_has_tasks_near_now()` 无待触发任务即静默返回，不记录冗余锚点行；两级触发保障改为"先到者生效"；新增 2 个回归测试
- [x] **中立观察者模型真实 LLM 验证**（2026-08-25）：scheduled + complex 重跑均 100/100（重叠窗口如实呈现、延迟投喂双指令正确处理、迟到锚点无冗余记录、定时任务触发点停靠、跨时记忆 + 恢复轮）；scheduled case 断言措辞修正（提醒在 30 分钟触发点触发）；74 个测试全通过
- [x] **即时投喂改造（说完即投，2026-08-26）**：删除 FIFO 队列 + `_feeder_loop` 串行投喂，改为 `_spawn_stream` 即时投喂——假人话语 `speak_done` 后立即启动后台流任务（`_active_stream_tasks` 集合跟踪），不等助手空闲、不排队；助手（不支持打断）多流并行，每条流输出独立记录，重叠由 `get_overlaps()` 呈现；是否中断旧流由被测助手自行决定，框架保持中立观察者；`_wait_assistant_idle` 改为等所有活跃流任务收完；时间快进/锚点推进语义不变
- [x] **流式投喂（第一个字即投，2026-08-26）**：`achat_stream` 协议输入改为异步文本流（模拟流式 ASR）——第一个 chunk = 用户开口（插话打断时机信号），迭代器耗尽 = 用户说完；Runner 在假人第一个 `text_delta` 即 `_spawn_stream` 启动投喂（`_queue_to_aiter` 队列包装），后续字实时推入，`speak_done` 发 EOF；支持打断的助手在第一个 chunk 中断旧流（`reply.is_interrupted` → trace 记半截话，插话打断能力可测，新增 BargeInMockAssistant 回归测试）；不支持的聚合输入后处理（TestedAssistant/v2_agent 如是暴露底层限制）；75 个测试全通过
- [x] **v2_agent 打断行为探测（三模式，2026-08-26）**：`run_interrupt_probe.py` 扩展 concurrent/serial/cancel 三模式真实 LLM 实测——concurrent（异步并发双 astream）= 旧流不中断 + 链路分叉（message_history 顺序颠倒、两轮互不知晓）；serial（同步串行 = AgentRunner._run_agent 行为）= 排队非打断；cancel（调用方 interrupt）= 13ms 干净中止。结论：同步/异步不是打断的关键，"取消"才是；v2_agent 底层无打断机制，音频侧插话打断在 TTS 播放层（v2_frontend_voice.py）
- [x] **接入层插话打断（文字层，2026-08-26）**：`tested_assistant.py` 的 `achat_stream` 实现插话打断契约（不改 aicore 框架代码）——第一个输入 chunk 到达即 `interrupt()` 旧活跃流（`_active_reply` 跟踪），半截话同步入 `_history`（`［被用户打断，未说完］`标记，顺序确定），聚合剩余输入后调底层；被打断轮不写回模型链（丢弃语义，与音频层丢弃 TTS 对齐）；真实 LLM 验证 13ms 中止 + 车态正确 + history 完整；新增 2 个单测，77 个测试全通过
- [x] **测试过程可视化 M1（实时模式，2026-08-26）**：`visualizer/` 新模块——旁路事件总线（双时间戳信封 wall_time + mock_time，单订阅者零开销，中立观察者原则）+ 两层事件（层1 TraceRecorder 落盘即推 8 种 / 层2 Runner 过程事件含 chunk delta 打字机流）+ FastAPI WebSocket 服务器（命令-ACK 协议对齐 v2_frontend，为语音测试预留多路复用；内置 7 个 demo case；assistant_kind mock/v2）+ React 19 前端三面板（RunConsole / ChatStream / TimelineLanes；分段时间映射让 30s 对话与 5 天快进同轴共存；重叠说话窗口检测）；后端 95 pytest + 前端 29 vitest + 端到端联调（builtin-complex-combo 119 事件流）全通过
- [x] **信封时间不变式修复（2026-08-26，端到端联调发现）**：事件信封 `mock_time` 在 seq 递增序下不倒退——层1 utterance 落盘事件信封时间由 `started_at` 改为 `ended_at`（落盘时刻；话语进行中的 delta 已带更晚时间，回填开口时刻会倒退）；`case_finished` 信封补当前虚拟时间（原为 None）；话语区间仍在 payload，前端投影不受影响；回归断言写入 test_event_bus.py
- [x] **可视化 M1 增强：工具调用全程可见 + 流式停顿语义修正（2026-08-26）**：工具调用区间化（ChatStream 工具卡片混排话语间 + TimelineLanes LIFO 配对橙色区间，从甩出调用到出结果全程可见）；`_consume_stream` 停顿检测只测文本流内 TEXT_DELTA→TEXT_DELTA 间隔（工具边界间隙一律不算）；long_pause 可视化 warn 警示色替代失败红（被插话是正常时序不是失败），图例拆分"流式停顿"与"检查失败"；RunConsole 被测助手 mock/v2 选择（v2 含 barge-in 插话打断）；后端 98 pytest + 前端 32 vitest 全通过

### 待完成

- [ ] **可视化 M2（回放模式）**：事件流落盘 + 按虚拟时间回放（信封双时间戳已预留两套坐标系）；语音测试接入（WS 多路复用已预留）
- [ ] **VoiceDeviceDriver 实现**：物理设备测试（TTS 播放 + VAD 检测 + 流式 ASR）
- [ ] **环境 schema 与驱动器**：现阶段全双工对话剧本不使用 `EnvironmentScriptEvent`
- [ ] **Scenario 聚合**：多假人、初始车态/环境、剧本列表、标签
- [ ] **旧 case adapter**：`user_query_lists` → script events（迁移 auto_test 旧用例）
- [ ] **fixture cases 真实 LLM 批量跑通**：builtin scheduled/complex 已验证 100/100，fixture 12 case 待批量验证

### 未来扩展设计（已预留接口，等待需求驱动）

以下扩展点已在代码中预留 discriminated union + kind 分发机制，新增动作/事件/主体无需修改现有事件类。

#### 假人动作扩展（FakePersonAction）

| 动作种类 | 说明 | 优先级 |
|----------|------|--------|
| `SPEAK` | 假人说话（当前已实现） | — |
| `MANUAL_CONTROL` | 假人手动操作车控（如按空调按钮、调座椅） | 中 |
| `STATE_CHANGE` | 假人自身状态变更（如"睡着了"、"下车了"） | 低 |
| `GESTURE` | 假人做手势/动作（如"指了一下窗外"） | 低 |

扩展方式：在 `fake_person/models.py` 的 `FakePersonAction` Union 中添加新 Action 类，在 `FakePersonDriver.drive()` 中按 `kind` 分发。

#### 虚拟车动作扩展（VirtualCarPerformAction）

| 动作种类 | 说明 | 优先级 |
|----------|------|--------|
| `SET_STATE` | 写 car_info dict（当前已实现） | — |
| `SIMULATE_BUTTON` | 模拟物理按键事件（如"乘客按下空调AC按钮"） | 中 |
| `SIMULATE_SENSOR` | 模拟传感器读数注入（如"车外温度传感器报 42°C"） | 低 |

扩展方式：在 `script_events/script_event.py` 的 `VirtualCarPerformAction` Union 中添加新 Action 类，在 `VirtualCarDriver.drive()` 中按 `kind` 分发。

#### 新主体扩展（未来可能）

| 主体 | 说明 | 优先级 |
|------|------|--------|
| 虚拟环境 | 天气、交通、路况（`EnvironmentScriptEvent` 已预留） | 远期 |
| 假人状态检查 | 一段时间后检查假人是否开心/满意/不满意（通过 Judge LLM 推断） | 远期 |

> 扩展原则：每个主体概念配一个驱动器。事件按类型路由到对应驱动器，驱动器按 `kind` 分发到具体执行方法。新增主体 = 新增数据模型 + 新增驱动器 + 新增事件类型。现有事件 types 无需修改。

---

## 7. 决策记录

| 日期 | 决策 |
|------|------|
| 2026-06-16 | `FakePersonInfo` / `VirtualCarInfo` 仅承载场景数据；实例化归 runner |
| 2026-06-16 | TestCase = 场景：`fake_persons` + `virtual_car` 初始化；JSON 批量导入 |
| 2026-06-16 | TestCase：`script`→`script_events`，`expected_script`→`text_script`；去掉 `code_assertion` |
| 2026-06-16 | speak 逻辑内聚于 `perform`；去掉对外 `achat`/`chat` |
| 2026-06-16 | 假人不绑定 TestCase；prompt 参数由 runner 在 perform 时传入 |
| 2026-06-16 | 假人 Action 并入 `fake_person/models.py` |
| 2026-06-16 | 去掉 FakePersonSceneContext；假人 prompt 用例字段改绑 TestCase |
| 2026-06-16 | 虚拟车简化为 car_info dict + set_state；`VirtualCar.perform` |
| 2026-06-16 | `ScriptEventUnion` → `ScriptEvent`；基类改名 `ScriptEventBase` |
| 2026-06-16 | ActionType 并入 script_event.py；`action` → `perform` |
| 2026-06-16 | 合并 FakePersonEventDriver / speak / llm_actor → 单一 `FakePerson` 类 |
| 2026-06-16 | 去掉 prompt 变量 memory（与 profile 重复，均为人设预设） |
| 2026-06-16 | 假人去掉 seat（座舱信息归虚拟车）；episodic → event_memory；time_travel prompt 用变量名 script（不改 auto_test） |
| 2026-06-16 | 假人不做 state_check；state/intent 不可结构化，断言用 nl_assertion + Judge |
| 2026-06-16 | 假人 Action / 驱动器现阶段仅保留 speak |
| 2026-06-16 | 假人非命名冲突：time_travel 是在同一假人概念上扩充 schema + 事件驱动，与 auto_test LLM 演员层互补 |
| 2026-06-16 | 现阶段只做全双工对话方向；环境剧本暂不进入 `ScriptEvent` 常规路径（用 `ScriptEventFull`） |
| 2026-06-16 | 去掉 `wake_assistant` |
| 2026-06-16 | 假人 profile 改为字符串 |
| 2026-06-16 | 虚拟车断言仅 k/v，不用 NL expected_state |
| 2026-06-16 | 保留 `event_type` 用于 JSON 导入，尽管 Python 类型已可区分 |
| 2026-06-16 | 助手侧无剧本事件（被测客体）；不单独做助手状态断言，盯假人 + 虚拟车结果 + NL 断言 |
| 2026-06-17 | 双层演进：默认边界驱动 + 显式时间戳锚点覆盖 |
| 2026-06-17 | 流式 + 并发设计：SUTDriver 流式交互 + 半截话保存 + Actor 独立执行器 |
| 2026-06-17 | 插话 = 普通剧本事件（锚点到达时打断当前） |
| 2026-06-17 | 生产级调度器：AsyncEventScheduler = heapq + asyncio.Event，零轮询 + 动态抢占 |
| 2026-06-18 | TestCase.t0 字段：场景起始时间可配置（ISO 8601） |
| 2026-06-18 | 清理冗余：删除旧 `scheduler.py`，保留 `scheduler_v2.py` 为唯一调度器 |
| 2026-06-18 | SUT 协议规范：`SUTBotProtocol` 类比 auto_test `AnyBotToTest`，标准化接入接口 |
| 2026-06-18 | 被测 Agent 简化封装：`SUTBot` 实现 `create()` → `achat()` → `adump_history()` |
| 2026-07-24 | 文档分工：ARCHITECTURE 讲怎么工作、CONTEXT 讲为什么这么设计、KNOWLEDGE_GRAPH 讲实体关系 |
| 2026-07-24 | Runner 重写：`time_travel_case_runner` → `case_runner`；`TimeTravelCaseRunner` → `CaseRunner`；调度器回调模式替代旧 ConcurrentEventScheduler 接口 |
| 2026-07-24 | 命名简化：SUTBot → TestedAssistant；SUTBotProtocol → AssistantProtocol；SUTDriver/CodeBotDriver 套娃删除，直接 AssistantProtocol + StreamingReply |
| 2026-07-24 | VirtualCar 重构：devices 为唯一真相源，car_info 只读派生；CAR_INFO_FIELD_MAP 映射表；删除 dict↔devices 双向同步 |
| 2026-07-24 | 假人 prompt 重写：去掉退下/打分/max_round 自决等回合制残留，纯剧本驱动 |
| 2026-07-24 | fast_mode：RunnerConfig.fast_mode + EventScheduler.fast_mode，跳过锚点真实等待，长周期测试从 209s 降到 8.9s |
| 2026-07-24 | 修复假人 `_llm_speak` bug：把字符串当 messages 列表传入 → 改为 `[("user", user_input)]` |
| 2026-07-24 | 新增原则 §0.11：主动智能必须能自主触发，框架不引入 polling 方法（`atry_proactive_speak` 已否决） |
| 2026-07-24 | 新增原则 §0.12：一切为了更精细地测试被测助手；设计取舍时优先"测助手更精细"而非"框架更复杂" |
| 2026-07-24 | 主动智能测试四段式（§2.5）：条件构建 + 侦听 + 检测 + 评判；被测助手可测试性要求 = 时间作为可注入依赖 |
| 2026-07-24 | `aupdate_context` 升级语义：复用已有方法注入 `current_time`，助手基于新条件自主决定行为；不新增协议方法 |
| 2026-07-24 | 快进策略简化（§2.6）：否决"N秒静默检测"，改用"事件队列判定"——下一事件远即快进，因为确定没人会说话 |
| 2026-07-24 | 快进必须同步助手时间：`accelerate_to` 前先 `aupdate_context(car_info, current_time=target)`，否则助手内部定时任务不触发 |
| 2026-07-24 | Judge 模块实现：独立模块（方案 B），Runner 不调；输入带时间线 trace + nl_assertions，输出结构化 JudgeVerdict；prompt 重写以理解时序演进语义（快进/半截话/主动说话）；不照搬旧 auto_test Judge |
| 2026-07-24 | Judge prompt 时序语义：明确让 LLM 理解时间快进不是剧情断裂、半截话是打断不是出错、快进后助手说话是主动智能、state_check 已自动判定不重复评 |
| 2026-07-24 | Judge 输出结构化：旧版 `tuple[bool, str]` → 新版 `JudgeVerdict`（含每条 nl_assertion 的 AssertionResult + evidence 证据引用 + summary）；JSON 格式输出 + 格式重试容错 |
| 2026-07-24 | 断言分化：`nl_assertions` → `must_pass_assertions` + `bonus_assertions`；旧字段向后兼容自动迁移；state_check 算必过项 |
| 2026-07-24 | 打分公式：线性插值 `60 + 40 * (bonus_passed/bonus_total)`；必过任一不过→0；全过+无加分→100；及格线 60；写死常量不抽配置 |
| 2026-07-24 | Judge 独立目录：`case_runner/judge.py` → `judge/`（与 `fake_person/` 同级）；拆分 models/scoring/prompt/judge 4 文件 |
| 2026-07-24 | 裁判价值观对齐假人：Judge prompt 注入假人人设，从假人视角评判（§0.13） |
| 2026-07-24 | `overall_passed` 以打分结果为准：LLM 返回的 overall_passed 不覆盖打分（防止 LLM 误判 state_check 失败为通过） |
| 2026-07-24 | TestedAssistant v2 集成：修正 `react_agent_with_task_manager` → `react_agent_with_task_runner` 导入 bug；弃用 `AgentRunner` 常驻模式（过重且无 `achat`/`cancel` 方法），直接用 `ReactAgentWithTaskRunner.astream()` 异步生成器；`achat_stream` 用 `anyio.CancelScope` 包生产者协程实现真正取消（aicore v2 无内置 `runner.cancel()`，`TaskManager.cancel_task` 只取消异步任务不取消模型生成）；合并 `TimeTravelSUTAgent` 的 7 条异步回执 system prompt 到 `TestedAssistant.DEFAULT_SYSTEM_PROMPT`；删除重复的 `v2_agent_to_test.py`（§0.7 不造重复轮子）；`VirtualCarControlTool` 接入虚拟车（Runner 共享 `VirtualCar` 实例，车控工具直接操作 devices） |
| 2026-07-24 | `TestedAssistant.__test__ = False`：类名以 `Test` 开头会被 pytest 误收集为测试类，加属性禁用 |
| 2026-07-24 | 时间加速 Runner 集成：`EventScheduler` 接 `acceleration_threshold` 参数，远期锚点跳过真实等待；`Runner._maybe_accelerate` 在锚点距 mock_time > 阈值时调 `aupdate_context(current_time=target)` + `TimelineEngine.accelerate_to` + `TraceRecorder.record_acceleration`；`RunnerConfig.enable_acceleration` / `acceleration_threshold` 暴露给外部 |
| 2026-07-24 | 流式打断 Runner 集成：`_assistant_chat_streaming` 用 `asyncio.wait` 并行等（回复完成 / 下一锚点到达）；锚点先到时调 `reply.interrupt()` 取消推理 + 保存半截话为 INTERRUPT；返回 `tuple[str, bool]` 让调用方跳过重复 ASSISTANT_REPLY 记录（解决双记录 bug） |
| 2026-07-24 | Runner 暴露 `trace` 属性：外部（如 demo / Judge）可直接访问 `runner.trace` 构造 `JudgeInput`，无需反射 `_trace` |
| 2026-07-24 | `TestedAssistant` 加 `chat_id` 参数：天气工具 `weather_search_v2_tool` 默认 worker 强制要求 `chat_id`，构造时传入避免初始化抛错 |
| 2026-07-24 | 端到端 demo `demos/run_e2e_demo.py`：3 种 case 来源（builtin / builtin-accel / fixture）+ 5 个命令行开关；Windows 控制台强制 UTF-8 输出避免 ✓/✗ 乱码；真实 LLM 已验证完整链路（开空调 + 时间加速 + Judge 评判） |
| 2026-08-25 | **多步快进**：当助手有 pending 定时任务时，Runner 不能一步跳到 target；通过 `get_pending_scheduled_tasks()` 查询中间停靠点，逐个快进并触发 `aupdate_context`；每个停靠点检查到期任务并记录主动话语（§2.6.28） |
| 2026-08-25 | **WorldTick 概念**：时间线上的"停靠点"——无执行主体，只表示时间演进到此刻必须停一下；来源为剧本定义或助手运行时注入；当前通过中间停靠点查询实现，未来升级为 `ContextUpdateResult` 结构化返回（§2.6.29） |
| 2026-08-25 | **`get_pending_scheduled_tasks` duck typing**：不在 `AssistantProtocol` 中强制要求，助手可选实现；Runner 通过 `hasattr` 检查，有则用于多步快进，无则一步跳到 target |
| 2026-08-25 | **定时任务管理器**：`ScheduledTaskManager` 独立于 Agent 框架，管理 pending 任务；`aupdate_context` 收到 `current_time` 时检查 `[old_time, current_time]` 区间到期任务，注入系统消息触发 Agent 主动提醒；`set_reminder` 工具供助手调用 |
| 2026-08-25 | **架构文档同步**：更新 ARCHITECTURE.md（7.1 多步快进、7.4 注入事件+WorldTick、11 协议签名、12 已完成/待办、13 变更记录）；更新 CONTEXT.md（2.6 时间加速策略、6 已完成/待办、7 决策记录） |
| 2026-08-25 | **`aupdate_context` 主动智能实测**：用真实 v2_agent + SEED_2_0_PRO_260215 模型实测，验证时间快进 + 定时任务触发完整链路；确认定时任务在快进过程中不会丢失，助手主动提醒正常工作 |
| 2026-08-25 | **时间戳精度**：LLM 响应时间从秒级升级为毫秒级（`.3f` 格式），在 `_format_offset` 中实现；实测 SEED_2_0_PRO_260215 响应时间约 1.2-1.4s |
| 2026-08-25 | **自然时间流逝模型定稿**：取消"助手回复期间虚拟时间冻结"假设——该假设严重违背时间旅行自动测试机制（评测的就是时间自然流逝下的交互）；`TimelineEngine` 只存锚点对 `(anchor_mock, anchor_wall)`，`mock_time` 实时计算，唯一跳跃方式是快进 `accelerate_to`；话语区间化 + 打断=半截话（删除 INTERRUPT 记录类型）；删除 `advance_to`/`offset_recent_tasks`/`_created_at` 全部偏移修正补丁——`set_reminder` 经 `set_time_source` 注入的时间源取当前虚拟时刻，trigger_time 天然含回复耗时；真实 LLM 验证 scheduled/complex 均 Judge 100/100 |
| 2026-08-25 | **WorldTick 落地**：`ScriptEventType.WORLD_TICK` + `ContextUpdateResult(proactive_text, injected_events)` 结构化返回已实现（§2.6.29 的"未来方向"已兑现）；`ScheduledTaskManager.add_task` 自动记录 `trigger_time - 5s` 锚点注入时间；两级触发保障：锚点 drain 主通道（`_execute_world_tick` → `_drain_pending_tasks_near_anchor`）+ 多步快进兜底 |
| 2026-08-25 | **中立观察者模型（总原则）**：自动测试工具必须实事求是——不主动打断、不拒收被测 agent 输出流，如实记录假人和助手演绎出的完整事件流，不遗漏不改变；被测助手不支持打断时，假人插话会与助手流式回复同时输出，这正是要测的真实场景 |
| 2026-08-25 | **插话投喂时机归责**：插话锚点设多少秒是**用例构造问题**，与框架无关；助手收到排队后的插话如何处理是被测助手的能力边界；测试平台只负责按锚点时刻如实开口、如实记录、如实评价 |
| 2026-08-25 | **长耗时事件区间化**：说话类与工具类事件除起始时间外必须标记结束时间；话语渲染为 `[T0 + Xs → T0 + Ys]`，工具调用/返回配对合并为单条区间记录 |
| 2026-08-25 | **重叠切片渲染**：基于 chunk 级时间戳（segments）按重叠窗口切片，`━━━ 双方同时说话 ━━━` 块内显示双方在窗口内实际说出的文字——完全重叠显示全部，不完全重叠只标重叠部分（各自窗口外内容仍在完整话语行中），无重复无遗漏 |
| 2026-08-25 | **迟到锚点静默跳过**：注入型 WorldTick 被调度器串行回调拖晚、锚定任务已被多步快进停靠先触发时，`_has_tasks_near_now()` 无待触发任务即静默返回不记录——任务的如实记录是它实际被触发的时刻，由先到的通道完成；两级触发保障语义从"主/兜底"修正为"先到者生效" |
| 2026-08-26 | **裁判中立原则（prompt 瘦身）**：Judge prompt 删除写死的行为对错评判规则（附和型"不应扣分"/否决型"应及时中止…才是问题"、超时截断"通常是扣分信号"、主动开口"主动智能的体现"、停顿"体验不佳"），只保留读懂 trace 的机制常识；新增总则"评判标准以断言为准，不要套用预设行为模板"——什么通过什么不通过取决于被测对象与用例断言，平台不预设；新增守护测试 `test_judge_prompt_neutral_no_hardcoded_verdict_rules` |
| 2026-08-26 | **主动话语时间戳含开口延迟（用户发现）**：修复 `_handle_context_update` 直接用任务触发时刻做话语时间戳的 bug——渲染自相矛盾（时间戳说此刻开口、标注说"触发后 X.Xs 开口"）。修正为 `started_at = at + timedelta(seconds=ttft)`（任务到期后 ttft 秒才开口），时间戳与标注自洽；顺带澄清：35m13.394s 的 trigger 本身正确（v2 ReAct 先调工具后吐字，set_reminder 于假人说完+思考约 2.9s 的 T0+13.394s 被调用，非助手开口的 18.106s）；`ProactiveMockAssistant` 增加 `proactive_delay` 参数模拟生成耗时，新增回归测试 `test_proactive_utterance_timestamp_includes_ttft` |
| 2026-08-26 | **可视化旁路设计（中立观察者延伸）**：事件采集不参与执行决策——EventBus 单订阅者零开销旁路（不注入则 TraceRecorder/Runner 行为与旧版完全一致），trace 落盘仍是唯一判卷依据；信封双时间戳（wall_time + mock_time）为 M2 回放模式预留两套坐标系；WS 协议对齐 v2_frontend 的命令-ACK 模式，为语音测试预留多路复用 |
| 2026-08-26 | **信封时间不变式**：事件信封 `mock_time` 在 seq 递增序下不倒退——层1 utterance 落盘事件信封时间用 `ended_at`（落盘时刻）而非 `started_at`（开口时刻），因为话语进行中的 delta 事件已携带更晚的虚拟时间；话语区间（started_at/ended_at/segments）在 payload 里，前端投影用 payload 区间不受影响 |
| 2026-08-26 | **工具调用是区间事件，不是点事件**：从被测助手甩出 TOOL_CALL 到 TOOL_RESULT 返回是一个完整执行过程——轨迹渲染侧由 `_merge_tool_records` 栈式配对为 `[start→end] [工具] name(args)→result, 耗时` 区间行（早已支持）；可视化侧 M1 增强对齐：对话流工具卡片（FIFO 配对混排话语间）+ 时间线区间 span（LIFO 配对与渲染一致，支持嵌套）。后端事件保持两个独立点事件（tool_call/tool_result），配对在展示层完成 |
| 2026-08-26 | **long_pause 语义修正（完整版）**：流式停顿只测"文本流内"的停顿（TEXT_DELTA→TEXT_DELTA 间隔 > 2s）——**任何一侧是工具事件（TOOL_CALL/TOOL_RESULT）的间隙都不算停顿**：工具执行 + LLM 围绕工具的思考（文本→调工具的决策间隙、结果返回后恢复生成的间隙）是 agent 正常节奏，且工具区间已单独可见，不重复记停顿。修复前 v2 助手（真实 LLM 延迟 3-5s）在工具边界两侧的思考间隙被误报为红色"失败停顿"标记，恰好集中在插话响应（含工具调用）处，看起来像"被插话失败"。可视化同步：long_pause 用 tone-warn 琥珀警示色（非失败红），图例拆分"流式停顿"与"检查失败"；插话打断（半截话）tone-partial 黄色斜纹 ≠ 失败 |

---

## 8. 相关路径速查

| 用途 | 路径 |
|------|------|
| 架构 + 流程图 | `./ARCHITECTURE.md` |
| 设计原则 + 决策（本文件） | `./CONTEXT.md` |
| 知识图谱（实体关系） | `./KNOWLEDGE_GRAPH.md` |
| TestCase | `./case_schema.py` |
| 剧本事件 | `./script_events/script_event.py` |
| 假人 | `./fake_person/models.py`、`llm_prompt.py` |
| 虚拟车 | `./virtual_car/models.py`、`car_devices.py` |
| Runner 主调度器 | `./case_runner/runner.py` |
| 事件调度器 | `./case_runner/scheduler.py` |
| 时间引擎 | `./case_runner/timeline.py` |
| 对话管理器 | `./case_runner/dialogue.py` |
| 轨迹记录器 | `./case_runner/trace.py` |
| 助手接入协议 | `./case_runner/assistant_protocol.py` |
| 终局评判 | `./judge/judge.py`、`./judge/models.py`、`./judge/scoring.py`、`./judge/prompt.py` |
| 被测助手 | `./demos/v2_agent_to_test/tested_assistant.py` |
| 定时任务管理 | `./demos/v2_agent_to_test/tools/scheduled_tasks/manager.py` |
| 定时任务工具 | `./demos/v2_agent_to_test/tools/scheduled_tasks/reminder_tool.py` |
| 车控工具 | `./demos/tools/virtual_car_control.py` |
| 可视化事件总线 | `./visualizer/event_bus.py` |
| 可视化 WS 服务器 | `./visualizer/run_server.py`（`python run_server.py` → http://127.0.0.1:8800） |
| 可视化前端 | `./visualizer/frontend/`（`npm run dev` → 5173 走代理 / `npm run build` 后单端口 8800） |
| 测试用例 | `./test/cases/fixture_cases.json` |
| VirtualCar 测试 | `./test/test_virtual_car_v2.py` |
| Scheduler 测试 | `./test/test_scheduler_v3.py` |
| Runner E2E 测试 | `./test/test_case_runner_e2e.py` |
| TestedAssistant 测试 | `./test/test_tested_assistant.py` |
| 现有执行器（参考） | `../../mind/mem/auto_test_script/auto_test_and_rl_data_generator.py` |
| 现有 TestCase（参考） | `../../mind/mem/auto_test_script/case_schema.py` |
