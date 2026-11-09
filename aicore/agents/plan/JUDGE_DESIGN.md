# Jev × PLACT：判定器驱动的 plan-and-act

本文从两头往中间讲：**Jev `system_one` 提供了什么能力**（第 1 节）、**PLACT 这个业务场景难在哪**
（第 2 节），然后才是两者的接缝（第 3–6 节）。读完应该能回答三个问题：

1. 哪些位置放了判定点，每个点判什么、判完怎么路由；
2. "谁来判"（Jev / LLM）与"怎么合"（代码方程）是如何分层的，两条后端为什么能同构；
3. 出了事（误判 / 假阴性）时，规则和护栏在哪里挡住。

> 与 `README.md` 的分工：README 是**改动记录与真机教训**（为什么撤掉某条护栏、哪次实测改了什么），
> 本文是**设计说明**（能力 → 业务 → 判定点 → 数据流 → 不变量）。两份都在本目录，改代码时请同时更新。
>
> 最后更新：2026-09-24（plact 收口成一个模式 + 把控依赖注入 + 判据形态强类型化之后）。
> 文件位置：`aicore/agents/plan/`，行号请以 `grep` 定位为准。

---

## 1. 能力面：`system_one` 到底提供了什么

### 1.1 一次调用，一组原子问题

```python
response = await client.system_one(state=<给判定器的证据>, questions={qid: Question})
response.answers[qid]  # → JevAnswer(归一化后的原子答案 + 完整概率分布)
```

关键性质：**一次往返可以回答任意多个原子问题**。于是"多问一个维度"的边际成本≈0 延迟——
这是整个设计的经济学基础：判定点宁可把一件事拆成 3–5 个可独立回答的小问题，也不问一句复合的
"这个计划好不好"。实测单次判定 250ms–2.1s（`README.md`）。

### 1.2 三种提问原语，各有各的可信量

| 原语 | 回答形态 | 组合方程读什么 | 适合什么问题 |
|---|---|---|---|
| `Noul` | `noul`：0–1 校准概率（**无 confidence**） | 概率值 + `_sharpness(p)=|p-0.5|*2` 代理尖锐度 | "是不是/能不能"这类二值事实（覆盖度、可修性、硬约束） |
| `Choice` | `choice`：选中标签 + `probabilities` 全分布 + `confidence` | 标签进枚举、`confidence` 当置信度 | 互斥枚举（路径、缺口类型、失败根因、三态判定） |
| `Score` | `score`：概率加权均值 + `level`（argmax 档位）+ `legend` | 均值做连续量、档位做分级 | 有档位的程度判断（风险、覆盖度档） |

两条使用纪律（踩过坑才写下来的）：

- **模型只填概率/标签，不写叙事**。自由文本（`rationale`）是证据、不进控制流；控制流只读数值与
  枚举。这样判定结果可复现、可统计、可离线重算。
- **A-or-B 不能塞进一个 `Noul`**。"这条约束是用户硬要求，**还是**计划自己猜的？"塞进二值概率会
  得到 0.68 这种没法用的中间值（实测：`Q_DIAG_HARD` → 灰区 → 白花一轮重规划）——这种问题必须
  用 `Choice` 给互斥选项。

### 1.3 工程封装（`judges/jev_client.py`）

| 事项 | 实现 |
|---|---|
| 异步 | 直接用 SDK 的 `AsyncTypeSafeClient`（httpx 异步客户端）：`await client.system_one(state, questions, timeout=...)`。**不需要**任何线程包装——早先用 `anyio.to_thread.run_sync` 包同步 SDK 的那一层已整体删除 |
| 超时 | `DEFAULT_JEV_TIMEOUT = 6.0s`（SDK 默认 10s 对热路径太长）；用 SDK 的 per-call `timeout`（直接成为这次 HTTP 请求的 timeout），`TypeSafeAPITimeoutError` 归一成 `JevTimeoutError` |
| 鉴权 | `TYPESAFE_API_KEY`：进程环境变量优先，否则按序加载 `.env`（包内 → `v2/experiments/jev_lab/` → cwd），**不覆盖**已存在的环境变量 |
| 归一化 | SDK 的 `ChoiceAnswer/ScoreAnswer/NoulAnswer` → `JevAnswer`（纯数据、可 JSON 序列化）；`Score` 的档位取 `probabilities` 的 argmax（四舍五入在偏斜分布下会指错档位） |
| 失败策略 | `JevError` / `JevTimeoutError` **直接抛**，不静默降级——静默降级会让 A/B 不可归因（分不清"判得对"和"根本没判"） |
| 测试替身 | `tests/agents/_fake_jev.py` 的 `FakeJevClient` + 脚本化答案（`choice_answer/noul_answer/score_answer`），全部判定逻辑可离线单测（测试件放 tests 下，运行时代码不再携带） |

### 1.4 由能力推出的三条设计准则

1. **判定点要小**：每个点只回答一件事，宁多问几个原子问题（反正一次往返）。
2. **裁决要由代码合**：模型给事实，代码给结论——否则同一份实验里两条后端跑的不是同一套规则。
3. **能代码推的不占判定预算**：如 `execution_outcome` 由 `errors`/`unmet`/`steps_done` 直接推
   （`derive_execution_outcome`），判定器给的 `outcome` 只作为"两者是否一致"的可观测量落进事件。

---

## 2. 业务面：PLACT 要解决什么、难在哪

### 2.1 场景

一条自然语言请求（车载：查天气 / 查条件 / 调空调 / 找店 / 导航 / 放歌 / 闲聊），要变成"计划 → 工具
调用 → 结果汇总 → 回答"。请求常常带**条件与依赖**，例如：

> 先查一下北京明天的天气，如果气温超过 30 度就把空调调到 22 度，再找一家评分高的烤鸭店并导航过去

这条请求里同时有：串行意图、条件分支（`condition`）、跨步数据引用（导航目的地来自 POI 结果的
最高分项）、以及一个**只有执行后才知道**的判断（气温到底超没超过 30）。

### 2.2 难点：一路上都是"不可信输入"

| 环节 | 谁写的 | 可能错在哪 |
|---|---|---|
| `query` | 用户 | 模糊、隐含、口语化 |
| 计划 `plan` | LLM | 漏诉求、自造阈值、依赖/条件写错、把叙述顺序当数据依赖 |
| 达成判据 `success_check`（`jq_expr` / `nature_assertion` 两种形态） | LLM | 判据落到工具给不出的字段上（POI 没有"是否营业"）→ 产出正常也必然判失败 |
| 工具产出 `tool_output` | 第三方 | 空结果、限流被吞、字段缺失 |
| 最终回答 | LLM | 谎称完成、把没做到的包装成做到了 |

`plact` 原实现在**计划生成后只有两处判断**：`success_check` 求值（jq 布尔式）与诊断裁决
（三选一）。其余环节靠"结构过了就算过"。于是经典失效形态是：判据写错 → 产出正常被判失败 →
整体重规划 → 越修越坏 → 轮次耗尽 → 用户什么都没得到。

### 2.3 为什么判定点能对上

把上面的"可能错在哪"按**问题形态**分类，正好对应三种原语：

| 问题形态 | 例子 | 原语 |
|---|---|---|
| 互斥枚举 | 该走 plan/direct/clarify；这步的断言是成立/被证伪/无证据；缺口类型 | `Choice` |
| 二值事实（要校准） | 完美执行能否满足诉求；换条路能不能满足；产出还够不够用 | `Noul` |
| 有档位的程度 | 后果多严重；覆盖度到第几档 | `Score` |

再加一条关键分层（第 6 节详述）：**判定器只提供事实，结论由代码算**。

---

## 3. 判定点地图

### 3.1 总表

| 判定点 | 位置 | 判什么（原子问题） | 结论怎么来 | 结论影响 | 谁承担 |
|---|---|---|---|---|---|
| `preflight` | 入口，进 plan 之前 | 路径 choice + needs_plan + ambiguity + goal_count + risk + confirm | Choice 主判 + **单向**护栏 | plan / direct / clarify | `supports(PREFLIGHT)` |
| `plan_audit` | `PlanCreatedEvent` 之后、执行前 | coverage + strictness + gap_kind + risk + confirm | coverage≥0.6 **且** strictness≥0.5 才放行 | 不放行 → `plan.semantics` 错误 → 整图重规划 | `supports(PLAN_AUDIT)` |
| `step_assert` | 每个执行完的 step（工具跑成了） | goal 达标度 + 每条断言三态 + 每条判据可靠性 + 每条把握 + 补救 4 原子 + cause | 见 3.4（两轴 + 共享路由） | 达成 / 降级接受 / 交补救方程 | `supports(STEP_ASSERT)`（必需：判据是断言时没有它就没有达成门） |
| `diagnosis` | 过程错误（参数/引用/条件/执行/投影失败）且规则层未命中 | 同上的补救 4 原子 + cause | 组合方程（5 分支 + 灰区） | replan / skip_unsolvable / accept_degraded | `supports(DIAGNOSIS)`；未承担时退回原生成式诊断 |
| `round_gate` | 每轮有错、决定是否再修 | worth_another_round + same_root_cause | 同根因≥0.8 且无希望<0.35 → 判无解；单看无希望<0.3 → 止损 | continue / stop / mark_unsolvable | `supports(ROUND_GATE)` |
| `finish` | 生成最终回答之后 | 覆盖度档 + 虚构 + 披露 + 结局 + 是否值得回问 | 置信度 = 覆盖 ×(1−虚构)×(0.5+0.5×披露) | 置信度 / outcome / 反向重试 | `supports(FINISH)` |

判定点定义全部集中在 `points.py`（`DecisionPoint` = 问题集 + LLM 契约 schema + 组合方程 +
可选共享路由），出口是 `ALL_POINTS`。

### 3.2 `preflight`：入口分流

- 原实现无状态，永远进 plan。新点补上"该不该规划 / 要不要先澄清"。
- 方程：`Choice` 选路径为主；原子判断只做**单向保守覆盖**——`ambiguity > 0.8` 时无论路由说什么
  都升为 `clarify`。**刻意不做 plan → direct 的降级**：实测"打开车窗"的 `needs_plan` 只有 0.21
  （判断失误），而看得到工具目录的路由 Choice 正确选了 `plan`；降级护栏会把对的改错，升级护栏
  只会多问一句——**护栏的价值不对称，就不该做成对称的**。

### 3.3 `plan_audit`：执行前的语义门

- 补 dag_checker（13 条纯静态规则）之外的语义判断：漏诉求、缺口类型、判据严格度、风险。
- 方程：`coverage ≥ 0.6` **且** `strictness ≥ 0.5` 才 `passed`；`gap_kind` 只进 rationale。
- **已知风险（待治）**：`Q_AUDIT_STRICTNESS` 问的是 `success_check` 的严格度，而 JEV 变体把
  `success_check` 摘掉了（改断言）——在 JEV 臂这个数会系统性偏低（实测 0.16/0.23 < 0.5），
  于是 JEV 臂的计划会被近乎必然地拒掉；另外审计器会**发明 schema 里没有的规则**（实测：以
  "用户说了先…再…"为由要求把叙述顺序写成 `depends_on`，而 schema 规定 `depends_on` 只表达数据
  依赖，加进去反而会让条件步被跳过时连带阻塞下游）。诊断见 `reports/plact_jev_ab_*/`。

### 3.4 `step_assert`：断言验收 + 补救裁决（核心）

**三个正交维度的信息**

```
C 轴（产出对这条断言是什么结论）：成立 / 被证伪 / 无证据    ← 事实
A 轴（这条断言本身值不值得当判据）：grounded / invented / unverifiable
把握（判定器对 C 轴结论有多确信）：0~1
B 轴（该步目标达成了吗）：goal_achieved                    ← 与断言解耦（提问要求"断言盲"）
```

**为什么 C 轴要三态**：jq 时代"判不了"只能表现为 `success_check == false`，于是必然触发一次修不好
的重规划（判据落到投影给不出的字段上就是典型）。三态把"判不了"从"产出错了"里切出来。

**结论怎么来（`compose_step_assert` → 事实 → `route_step_assert`）**

| 事实 | 结论 |
|---|---|
| 断言全成立 | 达成 |
| 被证伪，且**有可信断言**被证伪 | 真失败 → 交补救方程 |
| 被证伪，但**全部**不可靠（invented） | 忽略断言结论、改看 B：B≥0.6 干净放行；B∈[0.4,0.6) 降级披露；B<0.4 仍需补救 |
| 被证伪，但结论不可用（unverifiable / 把握<0.6） | 不失败，**也不咨询 B**（B 同样被这条判不了的断言带偏）→ 保产出 + 降级披露 |
| 只有无证据（无证伪） | 降级接受 |
| 判失败但一条逐条证据都没报 | 按"无断言可判"的兜底看 B（否则模型不报"哪条失败"就能绕开整套规则） |
| 完全没有断言 | 按 B：≥0.6 达成，否则交补救方程 |

**为什么需要 A 轴**：实测那条 badcase——用户只说"找一家"，计划却断言"至少返回 5 家"，判定器以
`confidence=0.94` 确信"产出与该断言矛盾"而且它没判错：**错的是判据**。只看 C 轴只能把它当"真没
做到"→ 灰区 → 白花一轮重规划。A 轴把"判据不适用"和"产出没做到"分开，这一轮就省下来了。

**四条不变量**（都是防"把没做到洗成降级"或"把真失败误杀"的）

1. **全有或全无**：只要有一条 grounded 且确信的断言被证伪，就是真失败——不然"某条判据不靠谱"
   会变成洗白通道。
2. **unknown 视为可信**：`clause_quality` / `clause_certainty` 缺失时**不**触发忽略，否则一个字段
   漏填就能把整套断言关掉。
3. **灰区不静默放行**：B 落在 [0.4, 0.6) 时降级披露，不因为"判据自设"就干净通过。
4. **可观测**：`assert_verdict_ignored` 记录"这次裁决不是由断言证据决定的"——常用即说明断言系统
   在退化成"只看 goal"的弱判定。

### 3.5 `diagnosis`：补救三选一

- 触发：过程错误（参数/引用/条件/执行/投影失败）且**规则前置层**未命中。规则层（`_rule_based_
  diagnosis`）与后端无关，逐字保留原行为。
- 方程（两后端共用 `_outcome_from_facts`，5 分支 + 灰区）：
  ① `retry>0.7` 且（`hard<0.6` 或 cause 属于可修类）→ replan；
  ② cause 客观不可得 + `hard≥0.6` + `usable<0.6` + `retry<0.7` → skip_unsolvable；
  ③ `usable>0.6` 且 `blocking<0.4` → accept_degraded；
  ④ `hard≥0.8` 且 `retry<0.3` → skip_unsolvable；
  ⑤ 其余（灰区）→ **保守 replan**，并把低置信度如实记进事件。
- 设计要点：**判无解必须同时要求"换 approach 也没戏"**——"指定歌手的歌搜不到"会给
  `hard≈0.66/retry≈0.90`（数据确实没有，但换个工具可能找到），只看 hard 会把可解问题错报无解。

### 3.6 `round_gate`：止损与跨轮证据门槛

原实现只有"`errors` 非空 → 再修一轮" + 固定 `max_turns`，既不知道"再修有没有希望"，也不知道
"这个错是不是已经修过好几轮的同一个"。跨轮的 `failures` 由编排层累积（runner 每轮新建、自身无记忆）。

### 3.7 `finish`：收尾评估

产出 `confidence`、`outcome`（success/partial/not_executed/clarify）、`ask_user_worth`，补上原实现
"`forced` 二值 + reason 取首错"说不清的结局；置信度由组合方程算（没给就用
`覆盖 × (1−虚构) × 披露折减`），`confidence_reported` 保留判定器自报值供对比。

---

## 4. 一次执行的数据流

```
query
  │
  ├─[preflight]───────────────────────────────→ path=direct/clarify 时直接出答案
  │      JudgeDecisionEvent(stage=preflight)
  ▼
PlActRoundStartEvent(round, repair_context)
  │
  ├─ create_plan(query, tools, spec, repair_context?) ─→ PlanCreatedEvent(plan)
  │                                        （计划生成与 native 臂**同一份实现**）
  ├─[plan_audit]──────────────────────────────→ 不过 → PlanError(plan.semantics) → 整图重规划
  │      JudgeDecisionEvent(stage=plan_audit)
  ▼
PlanDAGRunner.run(spec.build_dag(plan))        （按拓扑层并行执行）
  │  每层、每一步：
  │    PlanStepStartedEvent(resolved_inputs)
  │    ├─ 工具调用（失败 → process_error → 规则层/诊断）
  │    ├─ concept 投影（把工具产出投影成计划声明的字段）
  │    ├─ PlanStepAssertStartedEvent(assertion)
  │    │    ├─[step_assert]──────────────→ JudgeDecisionEvent(stage=step_assert)
  │    │    │                                 （含三态/质量/把握/原子事实/完整分布）
  │    │    └─ PlanStepAssertCompletedEvent(decision)
  │    │                                   passed=False →
  │    │                                     ├ replan → PlanError(step.remediation) → 本层结束后整图重规划
  │    │                                     └ 无解/降级 → PlanStepDoneEvent.unmet（无解还会级联跳过下游）
  │    └─[diagnosis]（仅过程错误路径）──────→ JudgeDecisionEvent(stage=diagnosis)
  │    PlanStepDoneEvent(tool_output, concept_output, unmet?)
  ▼
PlActErrorsEvent(round, errors, policy)         （有错时）
  ├─[round_gate]──────────────────────────────→ continue / stop / mark_unsolvable
  └─ continue → 组装 PlanRepairContext → 下一轮（回到 PlActRoundStartEvent）
  ▼
最终回答（LLM 生成）
  ├─[finish]──────────────────────────────────→ JudgeDecisionEvent(stage=finish)
  └─ PlActFinishEvent(response, forced, reason, confidence, outcome)
```

**事件与 trace**：判定结果落成 `JudgeDecisionEvent`，除裁决本身外还带 `answers`（原子答案 + 完整概率
分布）与 `latency_ms`——这是后续做校准统计、阈值调参、"LLM 自报 vs 校准概率"对比的唯一数据来源。
新事件只有三类且都是增量的（`JudgeDecisionEvent` 全新；`PlanStepAssert*` 是新增生命周期；
`PlActFinishEvent` 直接补上 `confidence` / `outcome` / `ask_user_worth` 三个字段——只有一个模式了，不再需要靠子类做兼容）。

---

## 5. 两条后端如何保持同构

```python
# 实验组：Jev
astream_plact(query, ..., judge=JevJudge(AsyncJevClient()), spec=plan_spec_v1)
# 对照组：LLM
astream_plact(query, ..., judge=LlmJudge(model_api),     spec=plan_spec_v1)
```

| 层 | 两条后端 | 是否相同 |
|---|---|---|
| 判定输入 state | `trim.py` 统一裁剪（同一份 policy、同一个预算） | ✅ |
| 判定点的"问题集" | Jev：`system_one(questions=...)`；LLM：`structured_output(output_type=点.schema)` | ⬜ 形态不同（见下） |
| 裁决类型 | `decisions.py` 里的同一批 pydantic 模型 | ✅ |
| **规则性出口** | `DecisionPoint.route`：LLM 后端解析后立即应用；Jev 的 compose 末尾调用同一个函数 | ✅ **同一份代码** |
| 补救三选一 | `compose_diagnosis` 与 `route_diagnosis` 走同一个 `_outcome_from_facts` | ✅ **同一方程** |
| 规则前置层 | `_rule_based_diagnosis` 在 runner 里，与后端无关 | ✅ |
| 数值来源 | Jev=校准概率分布；LLM=自报 | ⬜ **刻意不同——这才是 A/B 的自变量** |

三条设计原则：

1. **不让 LLM 去镜像概率**。Jev 的数是校准概率，LLM 自报的数是另一种统计量；硬塞进同一组阈值
   只会造出"伪装成对称"的新不对称（阈值按 Jev 定标，在 LLM 臂行为漂移）。所以对齐的是**事实与
   控制流**：两端都填同一组字段（三态、`clause_quality`、`clause_certainty`、`goal_achieved`、
   `diagnosis_atoms`），规则由代码执行。
2. **规则性出口收进代码**。哪些必须一致：判据自设 → 忽略断言看 goal；判不了 → 不失败也不看 goal；
   无证据 → 降级；补救三选一 → 方程。哪些留给"谁来判"：数值本身、以及尚未对齐的点（下条）。
3. **还未对齐的点**（明确记录，别误以为已对齐）：`preflight` / `plan_audit` / `round_gate` /
   `finish` 的 LLM 后端仍是"一个模型直接给裁决"（`judges/llm.py` 的对照组定义），只有
   `step_assert` 与 `diagnosis` 已经由 `route` 把控制流收进代码。

`route` 的**幂等**是这套做法的正确性依据：`route(compose(answers)) == compose(answers)`（有测试
钉住），所以"Jev 走 compose、LLM 走 route"不会得到两种语义。

---

## 6. 裁决为什么写成代码

判定器会错，而且会以"看起来很有把握"的方式错。把结论写成**纯函数**换来三件事：可回归、可离线
重算、两条后端可比。

1. **组合方程**：每个判定点的 compose 是 `dict[qid] → JevAnswer` 的纯函数，不依赖网络与全局状态。
   `tests/agents/test_jev_decide.py` 是各点的真值表——改阈值/改分支顺序会立刻报警。
2. **共享路由**：`route` 只读事实字段，两后端同一份实现；不改变"谁来判"这个自变量。
3. **护栏单向**：保守方向（升为澄清、降级、拒绝）可以有护栏，激进方向（自动放行、自动判无解）
   必须由方程给出的证据支持（见 `preflight` 的教训、`diagnosis` 的 `retry` 门）。
4. **可观测字段**：`assert_verdict_ignored`、`confidence_reported`、`_trim.shrunk/dropped_fields`、
   `judge_stages.verdicts` —— 规则一旦被滥用，trace 里能看出来。

---

## 7. 工程与运维

### 7.1 额外的把控：把增益拆到各来源

把增益拆到各来源不是靠关 core 的开关（core 里没有开关），而是靠**注入的实现声明它承担哪些判定点**：

```python
judge = JevJudge(AsyncJevClient(), points={Point.STEP_ASSERT, Point.DIAGNOSIS})
# == 把控只承担达成验收与补救诊断，其余额外把控（入口分流/审计/闸门/收尾）不做
#    注意：判据形态跟着把控走（不注入把控 → jq），所以"只换把控的某几个点"要按
#    points 裁剪，而不是去关 core 的开关——core 里已经没有开关了。
```

注意判据形态与把控必须自洽：注入按把控（`criterion=nature_assertion`）时必须有谁承担
`step_assert`，否则 core 在入口直接拒（计划里会出现没人能判的达成门）。

注入的落点：形态由 `judge.criterion` 提供，`create_plan` 用
`criterion.bind_criterion(spec, kind)` 取「绑好了形态的 spec」再建 system prompt。
这是**可选能力**（`criterion.CriterionAware`）——`PlanSpec` 协议保持不动，历史实验的 spec
（`plan_schema_v0/v2/v3`，提示词各自冻结）不受影响。

### 7.2 离线可跑

| 手段 | 说明 |
|---|---|
| `_mock_tools.get_mock_tools` | `get_default_tools` 的 mock 版：**只换 worker，不换工具契约**（工具名/description/args_schema 一律沿用真实工具——planner 的 prompt 由它们生成，换掉等于换了实验对象） |
| 固定数据 | 烤鸭店 POI（按评分降序，让"评分最高"与 `[0]` 一致）、周杰伦《晴天》、北京/上海天气（明天 34℃ > 30 触发条件分支，今天/后天 < 30 做日期落地判别）、车控/导航/媒体回执；导航回执带 `resolved_poi`（真实插件落地时会回 poiId/名称/地址，用来支撑"目的地与最高分店地址一致"这类断言） |
| pytest 用例 | `test_plact_judge.py` 的离线用例用假判定器 + 假模型 + 固定计划，不需要网络；`test_judge_trim/decide/runner/client.py` 是各层单测 |

### 7.3 真机 A/B

```bash
python -m tests.agents.test_plact_jev --judges native jev llm --mock-tools --cases 1
python -m tests.agents.test_plact_jev --judges native jev llm --no-plan-audit   # 关掉审计门跑基线
```

产物：`reports/plact_jev_ab_<时间戳>/c<case>.<judge>.trace.json`（run 配置 + 指标 + 全量事件）与
`summary.json`。指标含 `rounds/plans/steps_started/steps_done/asserts/assert_failed/steps_skipped/
error_sources/diagnoses/unmet/judge_stages/judge_calls/judge_total_ms/outcome/confidence`。

### 7.4 预算

判定输入统一过 `trim.py`：默认 `TrimPolicy(max_total_chars=8000)`，超预算时"降档收紧值 → 丢最大的
顶层字段"两级处理，并把丢了什么记进 `_trim`。`step_assert` 的 state 带 `all_step_outputs`
（runtime_state 快照）——跨步断言（"目的地与**上一步返回的**地址一致"）没有它就无法判定，只会
落"无证据"→ 降级。

---

## 8. 边界与待办

| 事项 | 现状 |
|---|---|
| 阈值 | `COVERAGE_MIN/STRICTNESS_MIN/DIAG_*/ASSERT_GOAL_*/CLAUSE_CONF_MIN` 等仍是**无数据初值**，需用 trace 里的分布定标 |
| `plan_audit` 的两处病 | ① `strictness` 问的是 JEV 臂已删除的 `success_check`；② 会发明 schema 里没有的规则（叙述顺序→`depends_on`）。二者都会让整轮 0 步执行 |
| `Q_ASSERT_GOAL` 的污染 | 判定器看得到该步断言，会把自设阈值反算进"目标达成度"；已要求"断言盲"，但需要数据验证 |
| 未对齐的判定点 | `preflight` / `plan_audit` / `round_gate` / `finish` 的 LLM 后端仍直填裁决 |
| 缺的出口 | `ask_user`（诊断的第四个出口，`diagnosis.py` 的 TODO）、step 级重试（`RepairPolicy.REGENERATE_STEP` 是占坑；当前"修复"只有整图重规划） |
| 断言验收未按层合并 | 每个执行完的 step 打一次判定；Jev"多问不增时"本可把同层 N 步合并成一次调用，代价是事件顺序变动 |
| 灰区不回退 LLM | 灰区取保守分支并记录低置信度；若将来要升级，应给 `JevJudge` 加可选 escalation 后端而不回退 |
| 音乐硬编码 | `diagnosis` 系统提示里仍有"音乐搜不到→无解"的权宜规则，等判定质量够了应移除 |

---

## 附录 A：常量表（`points.py`）

| 常量 | 值 | 含义 |
|---|---|---|
| `AMBIGUITY_BLOCK` | 0.8 | 歧义高于此 → 路径升为 clarify |
| `NEEDS_PLAN_GATE` / `RISK_MEDIUM` / `RISK_HIGH` | 0.4 / 0.75 / 1.5 | preflight 路由与风险档 |
| `COVERAGE_MIN` / `STRICTNESS_MIN` | 0.6 / 0.5 | plan_audit 放行门 |
| `ASSERT_GOAL_PASS` | 0.6 | 目标达成（干净放行）线 |
| `ASSERT_GOAL_FLOOR` | 0.4 | 目标达成度下限（低于此值连达成度都不足信） |
| `CLAUSE_CONF_MIN` | 0.6 | 断言结论把握低于此 → "判不准" |
| `DIAG_RETRY_CAN_FIX` | 0.7 | 换做法可解的门 |
| `DIAG_HARD_CONSTRAINT` / `_STRICT` | 0.6 / 0.8 | 硬约束门 / 严格硬约束门 |
| `DIAG_USABLE` / `DIAG_NOT_BLOCKING` / `DIAG_HOPELESS` | 0.6 / 0.4 / 0.3 | 产出够用 / 不阻塞 / 无希望 |
| `SAME_CAUSE_STRONG` / `WORTH_HOPELESS` / `WORTH_STOP` | 0.8 / 0.35 / 0.3 | 轮次闸门 |
| `GRAY_ZONE` | — | 灰区兜底文案（灰区取保守分支） |

## 附录 B：事件表

| 事件 | 何时 | 关键字段 |
|---|---|---|
| `JudgeDecisionEvent`（`plan.judge.decision`） | 每个判定点判定完成 | `stage` / `backend` / `decision` / `answers`（原子答案 + 分布）/ `latency_ms` |
| `PlanStepAssertStartedEvent` | 判定调用**之前**（间隔即耗时） | `step_id` / `step_goal` / `assertion` |
| `PlanStepAssertCompletedEvent` | 判定完成 | `decision`（`StepAssertDecision`：三态 / 质量 / 把握 / 原子事实 / 补救裁决） |
| `PlActFinishEvent` | 收尾 | `confidence` / `confidence_reported` / `outcome` / `ask_user_worth` |

## 附录 C：文件索引

| 文件 | 职责 |
|---|---|
### core（与实现无关）

| 文件 | 职责 |
|---|---|
| `core.py` | `astream_plact`：唯一编排入口（轮次、审计门、闸门、收尾；没有开关） |
| `plan_dag_runner.py` | runner：按判据形态分派达成判定（断言 → 把控；jq → 规则层） |
| `judge.py` | 把控契约：`Point` 词汇、`PlanJudge` 协议、`JudgeOutcome` |
| `decisions.py` | 裁决模型（含 `DiagnosisAtoms`、`StepAssertDecision`、`FinishDecision`）、置信度组合方程 |
| `criterion.py` | 达成判据：`jq_expr` / `nature_assertion` 两个形态 + 提示词唯一变化段 |
| `trim.py` | 判定输入裁剪（各点的 state builder + 预算） |
| `events.py` | 事件（含 `JudgeDecisionEvent`、`PlanStepAssert*`、finish 的 confidence/outcome） |
| `experiment/plan_schema_v1.py` | 唯一 plan schema（`success_check` 是强类型联合）与提示词 |
| `dag_checker.py` | 静态校验（第 7 项按判据形态分派，两形态等强度） |

### 实现（把控制注入 core）

| 文件 | 职责 |
|---|---|
| `judges/jev.py` | `JevJudge`：判定点表 → `system_one` → 组合方程 |
| `judges/jev_client.py` | Jev 客户端（`AsyncTypeSafeClient`、超时、鉴权、答案归一化） |
| `judges/llm.py` | `LlmJudge`：结构化输出 + 内部保守兜底 |
| `judges/points.py` | 全部判定点：问题集、schema、组合方程、共享路由、阈值 |

### 测试

| 文件 | 职责 |
|---|---|
| `tests/agents/_mock_tools.py` | 确定性 mock 工具集（只换 worker） |
| `tests/agents/_fake_jev.py` | `FakeJevClient` 与答案构造器（测试替身） |
| `tests/agents/test_plact_judge.py` | 离线用例 + 真机 A/B 驱动（CLI、trace 落盘、报表） |
