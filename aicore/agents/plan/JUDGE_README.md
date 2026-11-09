# plact：一个模式 + 注入的把控

`aicore/agents/plan/` 是 plan-and-act 的**唯一**实现。它只有一条流水线
（`preflight → plan → audit → run → repair/gate → finish`），没有开关矩阵；唯一的变量是
**注入的把控**（`judge`，见 `judge.py` 的 `PlanJudge` 协议）。

```python
from aicore.agents.plan.core import astream_plact
from aicore.agents.plan.experiment.plan_schema_v1 import plan_spec_v1
from aicore.agents.plan.judges import AsyncJevClient, JevJudge, LlmJudge

# 有把控：判据是自然语言断言，谁来判由注入的实现决定
stream = astream_plact(query, ..., judge=JevJudge(AsyncJevClient()), spec=plan_spec_v1)
stream = astream_plact(query, ..., judge=LlmJudge(model_api),     spec=plan_spec_v1)

# 没有把控：判据退回 jq，由规则层确定性求值（= 原 astream_plact_base 的行为）
stream = astream_plact(query, ..., judge=None, spec=plan_spec_v1)
```

三条不变量：

- **core 实现无关**：`core.py` / `plan_dag_runner.py` 只 import `judge.py`（协议）、`decisions.py`
  （裁决数据）与 `trim.py`（判定输入），不 import 任何实现；
- **一个模式**：core 里没有 `enable_*`，额外把控（preflight / plan_audit / diagnosis /
  round_gate / finish）做不做，由实现的 `supports(point)` 声明；`step_assert` 是必需能力；
- **判据形态是唯一自变量**：`jq_expr`（规则层求值）或 `nature_assertion`（把控判定），
  由 `judge.criterion` 提供、在 `create_plan` 处注入（`criterion.bind_criterion(spec, kind)`
  → 提示词里唯一变化的一段），并同时决定静态校验走哪一支、以及谁做达成判定。

判据形态是**可选能力**：想跟随注入形态的 spec 实现 `criterion.CriterionAware`（`plan_schema_v1` 就是）；
历史实验的 spec（`plan_schema_v0/v2/v3`）提示词各自冻结、不吃形态注入，也不在 plact 的调用路径上。

## 判定点一览

| 判定点 | 阶段 | 没有把控时 | 有把控时 |
|---|---|---|---|
| `preflight` | 入口 | 无状态，永远进 plan | plan / direct / clarify |
| `plan_audit` | `PlanCreatedEvent` 之后、执行前 | 只有 dag_checker（13 条纯静态规则） | 补语义门（漏诉求、判据过松、依赖不成立） |
| `step_assert` | 每个执行完的 step | —（该形态不存在） | 断言验收 + 补救裁决合并成一次判定 |
| `diagnosis` | 过程错误 / 未达成 | 规则前置层 → 原生成式诊断 | 规则前置层 → 判定点（未承担时退回生成式） |
| `round_gate` | 每轮有错、决定是否再修 | `errors 非空 → 再修`，只受 `max_turns` 限制 | 止损 + 跨轮证据门槛（同根因） |
| `finish` | 生成最终回答之后 | `forced` 二值 + `reason` 取首错 | 覆盖度 / 虚构 / 披露 → confidence 与 outcome |

判据形态与把控能力必须自洽：把控要求 `nature_assertion` 时必须有人承担 `step_assert`，
否则 `astream_plact` 在入口直接抛 `ValueError`（绝不留下没人能判的达成门）。

## 跑测试与 A/B

```bash
# 离线单测（不需要网络）
python -m pytest tests/agents/test_judge_client.py tests/agents/test_judge_trim.py \
    tests/agents/test_judge_decide.py tests/agents/test_judge_runner.py \
    tests/agents/test_plact_judge.py tests/agents/test_plan_schema_prompt.py -q

# 真机 A/B：同一条 query 跑同一根流水线，只换注入的把控
python tests/agents/test_plact_judge.py --judges native jev llm --mock-tools --cases 1
python tests/agents/test_plact_judge.py --judges native jev llm --no-plan-audit
```

产物：`reports/plact_jev_ab_<时间戳>/c<case>.<judge>.trace.json` 与 `summary.json`。
把增益拆到各来源靠**裁剪把控承担的判定点**（`JevJudge(client, points={...})`），而不是关 core 的开关。

## 关键约束

- **失败即抛错（把控自己决定）**：Jev 后端调用失败直接抛 `JevError` / `JevTimeoutError`，
  不静默降级——静默降级会让 A/B 无法归因（分不清"判得对"和"根本没判"）。LLM 后端在
  **实现内部**转成保守裁决并把 `backend` 标成 `llm:fallback`，core 不写 try/except。
- **异步**：判据调用走 SDK 的 `AsyncTypeSafeClient`（per-call `timeout`），没有任何线程包装。
- **预算**：判定输入统一过 `trim.py`（默认 `TrimPolicy(max_total_chars=8000)`），超预算时
  "降档收紧值 → 丢最大的顶层字段"两级处理，并把丢了什么记进 `_trim`。
- **事件**：判定结果落成 `JudgeDecisionEvent`（`plan.judge.decision`，含归一化原子答案与完整
  概率分布）——这是校准统计、阈值调参、"LLM 自报 vs 校准概率"对比的唯一数据来源。
  判据在事件里是**结构化**的（`{kind, expression|assertions}`），前端/消费方按 kind 渲染。
- **代码可推的不占判定预算**：`execution_outcome` 由 `errors` / `unmet` / 执行步数直接推出
  （`derive_execution_outcome`）；把控给出的 `FinishDecision.outcome` 仍落事件，两者是否一致
  本身就是一项可观测量。

## 真机验证记录（Jev `jev-1.13.0`，单次判定 250ms–2.1s）

这些是实际调用后**改掉**的设计，写下来是为了避免它们被好心改回去：

1. **preflight 的护栏必须单向**：早期有一条 `plan → direct` 的降级护栏（"needs_plan 低就不用
   工具"），实测把 `打开车窗` 判成了 direct——它的 `needs_plan` 只有 0.21（判断失误），而路由
   Choice 看得到工具目录、正确选了 `plan`。现在护栏只做"升为 clarify"。
2. **diagnosis 判无解必须同时要求"换 approach 也没戏"**：实测"指定歌手的歌搜不到"会给
   `hard≈0.66 / retry≈0.90`（数据确实没有，但换个工具可能找到）。只看 `hard` 会把可解问题
   错报无解；加上 `retry < 0.7` 这道门后它落灰区取保守 replan。
3. **`ScoreAnswer.probabilities` 以档位下标（int）为 key**，标签在 `legend` 里；
   归一化层负责换成标签，且档位取 `probabilities` 的 argmax（偏斜分布下四舍五入会指错档位）。
4. **jq 的 `success_check` 必须能让位给自然语言断言**（c01 实测，max_turns=3 全烧在判据上）：
   判据写到投影给不出的字段上时，产出完全正常也必然判失败，再被一次修不好的整体重规划带走。
   所以断言验收与补救裁决合并成一次 `step_assert`，断言三态（成立 / 被证伪 / 无证据）——
   判不了就判不了，不当作"产出错了"。
5. **判据形态要写进 schema**：`success_check` 是 `{kind, expression|assertions}` 的强类型联合，
   `kind` 必填（schema 里是 `const`）。这样"这次计划用哪种判据"在 JSON 里就是显式事实，
   不需要靠字段有没有出现去猜。

## 已知取舍 / TODO

- **断言验收未按层合并**：每个执行完的 step 打一次判定（断言 + 补救合并）。Jev 的"多问不增时"
  本可把同层 N 步合并成一次调用，代价是事件顺序变动（trace 顺序变化）。
- **过程错误不打断言判定**：入参/引用/条件/执行/投影失败由规则层确定性定夺（判 replan），
  不占判定预算。代价是"工具被正确调用但环境不可得"这类失败也会被判重规划，只能靠闸门收敛。
- **灰区不回退 LLM**：`compose_diagnosis` 在阈值附近取保守分支并把低置信度记进事件。
  若将来要在灰区升级，应给 `JevJudge` 加可选 `escalation` 后端，而不是回退（否则 A/B 不可归因）。
- **虚构重述默认关闭**：`retry_on_fabrication` 会多打一次生成式调用，先度量判定命中率再开。
- **跨轮失败记忆只记结构**：`failures` 里是"轮次 + step_id + 错误类型 + 文本摘要"。
- **阈值仍是无数据初值**：`COVERAGE_MIN / STRICTNESS_MIN / DIAG_* / ASSERT_GOAL_* / CLAUSE_CONF_MIN`
  需要用 trace 里的分布定标（见 `JUDGE_DESIGN.md` 附录 A）。
- **`plan_audit` 的两处病**：① strictness 问的是已退役的 jq 判据严格度；② 会发明 schema 里
  没有的规则（把叙述顺序当成 `depends_on`）。二者都会让整轮 0 步执行。
- **`plan_schema_v3` 已过期**：它的占位符语法（`{{/s1/outputs/...}}`）与 runner 支持的
  `.s1.outputs...` 不一致，其计划会被第 5 项静态校验拒绝；本次重构只让它复用共享的判据规则段，
  没有修它的引用语法。
- **trace 断代**：`judge_stages` 的键、事件名（`plan.judge.decision`）、提示词与 schema 都变了，
  新 trace 与旧 trace 只能按字段级对齐，别按 stage 名对齐。
