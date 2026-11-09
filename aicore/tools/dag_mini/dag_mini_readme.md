# dag_mini 架构与跨 step 依赖处理

> 路径：`aicore/tools/dag_mini/`
> 定位：DAG 多 step 并行框架。

## 1. 模块拓扑

```
dag_mini/
├── __init__.py     公开 API 入口
├── agent.py        Agent — v1 create_agent 薄壳，run() 返 4 键 dict
├── chat_agent.py   ChatAgent — 最外层（v1 create_agent + [TaskAgent] tool）
├── dag.py          DAG — Kahn 拓扑分层
├── models.py       StepGoal / StepRecord / SubagentOutput / Trace / TaskPlan
├── prompt.py       Prompt 拼装 + CHAT_SYSTEM_PROMPT + TASK_AGENT_DESCRIPTION
├── subagent.py     Subagent（核心） + create_taskagent
└── examples/       demo / compare
```

## 2. 架构自下而上（5 层）

| 层 | 类 / 函数 | 职责 |
|---|---|---|
| 1. 执行原子 | [Agent](file:///e:/nanoai/aicore/tools/dag_mini/agent.py) | 包装 v1 `create_agent`，`run(prompt) → {system,user,assistant,tool_calls}`，**单次跑完** |
| 2. 拓扑 | [DAG](file:///e:/nanoai/aicore/tools/dag_mini/dag.py) | Kahn 分层 |
| 3. 调度 | [Subagent](file:///e:/nanoai/aicore/tools/dag_mini/subagent.py#L44-L158) | 并发派发 per-step Agent.run + 跨 step 依赖解耦 |
| 4. 工具包装 | [create_taskagent](file:///e:/nanoai/aicore/tools/dag_mini/subagent.py#L166-L207) | Subagent → `TaskAgent` tool，挂到 chat_agent |
| 5. 最外层 | [ChatAgent](file:///e:/nanoai/aicore/tools/dag_mini/chat_agent.py) | v1 create_agent 懒初始化 + run 一次汇总 |

**与 dag_v3 关键差异**：砍掉 `EvaluatorAgent` / `agent_loop` / `refine` / `skip_validation` / `events` 流，每 step 只跑一次 `Agent.run`，没有 execute↔evaluate 闭环，**无 LLM 评估**。

## 3. 核心调用栈

```
ChatAgent.run(query)                              # chat_agent.py
  └─ self._v1_agent.run_astream(query)            # v1 astream
       └─ chat_agent LLM 拆解 → 调 TaskAgent tool.invoke(TaskPlan{steps})
            └─ worker(steps)                      # subagent.py
                 └─ subagent.run(step_goals)      # subagent.run
                      ├─ DAG(nodes).to_layers()   # Kahn 分层 → 拿 layer_index
                      ├─ records = {}
                      ├─ done_events = {sid: anyio.Event()}
                      ├─ run_limiter = anyio.CapacityLimiter(N)
                      └─ anyio.TaskGroup
                           └─ _runner(step)       # 每个 step 一个
                                ├─ for dep in step.depends_on:    # 1. 等上游
                                │     await done_events[dep].wait()
                                ├─ dep_answers = {dep: records[dep].final_answer}
                                ├─ StepRecord(...)                # 2. 建 record
                                ├─ async with run_limiter:        # 3. 跑 step
                                │     sys_prompt += dep_answers 块
                                │     sys_prompt += runtime_context 块
                                │     agent = Agent(model, sys_prompt, max_turns, tools)
                                │     out = await agent.run(step.goal)
                                │     record.assistant_msg = out["assistant"]
                                │     record.tool_calls = out["tool_calls"]
                                └─ finally (shield=True):         # 4. 兜底解封
                                      records[sid] = record
                                      done_events[sid].set()
                                      await on_step(record)
       └─ tool worker 返 [r.final_answer for r in step_records]
            → 回流到 chat_agent v1 state → chat_agent 汇总回复
  └─ self._v1_agent.dump() → Trace → {system, user, assistant, tool_calls}
```

`Subagent.run` 内部（[subagent.py L62-158](file:///e:/nanoai/aicore/tools/dag_mini/subagent.py#L62-L158)）没有 agent_loop，每 step 的执行序列就是：

1. 等所有依赖 done
2. 构造 `StepRecord` + `dep_answers`
3. 构造 per-step Agent（带 dep_answers 注入 system_prompt）
4. 调一次 `agent.run(step.goal)` 拿 assistant 文本
5. `finally` 中 `set()` done_event + 写 records

## 4. 跨 step 依赖处理（核心）

跨 step 的"输入"是**上游 final_answer 文本字典**，"输出"是**本 step 的 assistant 文本**。**不传中间 tool_calls / reasoning / state**。

### 4.1 解耦同步：`anyio.Event` + TaskGroup

```python
# subagent.py L77-78
done_events = {s.step_id: anyio.Event() for s in step_goals}
run_limiter = anyio.CapacityLimiter(self.max_concurrent_steps)
```

- 所有 step 一次性 `tg.start_soon(_runner, step)` 并发派发（L144-146），无依赖 step **真并发**
- runner 进入前阻塞：`for dep in step.depends_on: await done_events[dep].wait()`（[L90-91](file:///e:/nanoai/aicore/tools/dag_mini/subagent.py#L90-L91)）
- 上游完成时在 `finally` 用 `with anyio.CancelScope(shield=True):` 保护 `done_events[step.step_id].set()`（[L132-137](file:///e:/nanoai/aicore/tools/dag_mini/subagent.py#L132-L137)），确保解封事件不因父级 cancel scope 丢失

`DAG.to_layers()` 只用于 `layer_index` 记录 + 错误信息，**不**作为串行执行依据。

### 4.2 读上游输出：`final_answer`

```python
# subagent.py L92
dep_answers = {dep: records[dep].final_answer for dep in step.depends_on if dep in records}
```

`final_answer` 定义（[models.py L120-123](file:///e:/nanoai/aicore/tools/dag_mini/models.py#L120-L123)）：

```python
@property
def final_answer(self) -> str:
    """同 assistant_msg：chat_agent 收集时用。"""
    return self.assistant_msg
```

`assistant_msg` 在 runner 第 3 步 `record.assistant_msg = out.get("assistant", "")` 写入（[L116](file:///e:/nanoai/aicore/tools/dag_mini/subagent.py#L116)），即 `Agent.run` 返回的 4 键 dict 中 `assistant` 字段。

同时把上游 `StepRecord` 链挂到本 step 的 `dep_records`（[L97](file:///e:/nanoai/aicore/tools/dag_mini/subagent.py#L97)），供后续 `success` 判定或回调使用。

### 4.3 注入下游 system_prompt：构造时一次性

```python
# subagent.py L106-108
sys_prompt = (self.system_prompt or "") + SUBAGENT_SYSTEM_PROMPT_SUFFIX
sys_prompt += build_dep_answers_block(dep_answers)
sys_prompt += build_runtime_context_block(self.runtime_context)
agent = Agent(model=self.model, system_prompt=sys_prompt, max_turns=self.max_react_turns, tools=list(self.tools))
out = await agent.run(step.goal)
```

`build_dep_answers_block`（[prompt.py L8-13](file:///e:/nanoai/aicore/tools/dag_mini/prompt.py#L8-L13)）渲染为：

```
【依赖 step 累积上下文】
[step:s1] xxx
[step:s2] yyy
```

`build_runtime_context_block`（[prompt.py L16-21](file:///e:/nanoai/aicore/tools/dag_mini/prompt.py#L16-L21)）渲染为：

```
【运行时上下文】
- key1: value1
- key2: value2
```

**只构造 Agent 时设一次**。`agent.run(step.goal)` 整个 ReAct 过程（多轮 tool call）都共享这同一段 system_prompt，`user_msg` 每轮只追加 `step.goal` 内容（v1 内部处理）。

结构化规范由 `SUBAGENT_SYSTEM_PROMPT_SUFFIX`（[prompt.py L25-36](file:///e:/nanoai/aicore/tools/dag_mini/prompt.py#L25-L36)）强制：

> 1. 回复必须包含 step_goal 缺失信息的极简说明
> 2. 首轮工具无信息立即停止，不要为凑信息继续调
> 3. final answer 先列"已获取信息"，再列"缺失信息 + 原因"
> 4. **同类查询合并 1 次 list 调用**（POISearch kinds=[]）
> 5. **数字/时间/地点必须从 tool_result 原文摘**，禁止"再算一次"
> 6. **导航成功后停止**，不调 Navigation 验证
> 7. **音频拿到 1 候选即停**，不为"找更好"再调

### 4.4 反向：上游失败如何传递

| 场景 | 行为 |
|---|---|
| 上游 `Agent.run` 抛 `AgentStreamError` | `record.error = str(e)`，L119，**不外抛** |
| 上游其他 `BaseException` | `record.error = f"{type(e).__name__}: {e}"`，L121-124，**不外抛** |
| 上游 CancelledError | `isinstance(e, _CANCEL)` 判定后静默 |
| 下游等不到上游 record | `dep_answers` 不含该 dep（`if dep in records` 过滤） |
| 上游 record 构造前异常/被取消 | `record` 仍为 `None`（L86 初始化），finally 内 `if record is not None` 守护（L134）跳过 `set()` + `records` 写入；`done_events[step.step_id]` 不会被 set |

**关键差异**：dag_mini 没有 evaluator，所以"上游失败"仅以 `record.error` 文本形式存在于 `final_answer` 里，**结构化判定由 chat_agent LLM 看返回列表时自行判断**。

### 4.5 worker 返回值：把 final_answer 列表给 chat_agent

```python
# subagent.py L188-198
async def worker(steps: list) -> dict:
    output: SubagentOutput = await subagent.run(steps)
    if on_subagent_output is not None:
        await on_subagent_output(output)        # side-channel 拿结构化结果
    return [output.final_answer for output in output.step_records]
```

- `worker` 返 `[step_record.final_answer for step_record in step_records]` — 一个 `list[str]`
- tool 框架对返回值（list 同样）走 `nl_repr` 字符串化，chat_agent LLM 看到的是字符串列表文本
- 框架返回值会丢结构，故提供 `on_subagent_output` 回调（[L171](file:///e:/nanoai/aicore/tools/dag_mini/subagent.py#L171)）让上层侧通道拿完整 `SubagentOutput`

## 5. 数据流汇总表

| 方向 | 通道 | 载体 | 时机 |
|---|---|---|---|
| 上游→下游 输入 | system_prompt 末尾 | `dep_answers: {step_id → final_answer}` | Agent 构造时一次性注入 |
| 下游→chat_agent | tool worker 返回值 | `[step_record.final_answer for ...]` | TaskAgent tool 跑完 |
| 下游→外部 | `on_step` callback | `StepRecord` | runner finally |
| 下游→外部（结构化） | `on_subagent_output` | `SubagentOutput` | worker 跑完 |
| Subagent→调用方 | return `SubagentOutput` | `step_records + nodes + elapsed` | TaskGroup 全部 done 后 |

## 6. 关键不变量

1. **每个 step 一个独立 Agent 实例** — v1 state 隔离，跨 step 不污染
2. **每 step 只跑一次 `Agent.run`** — 没有 execute↔evaluate 闭环，没有 LLM 评估
3. **失败不外抛** — step 异常写 `record.error`，继续走完；chat_agent 收到非空 final_answer 列表（可能含 error 文本），由 chat_agent LLM 自行判断
4. **依赖传播靠文本** — 上下游只传 `final_answer` 字符串
5. **refine / skip_validation / events 全部砍掉** — 简化路径，不重试、不优化、不存过程轨迹
6. **构造 vs 运行分离** — `ChatAgent._ensure_v1_agent` 懒构造 v1 agent；`Subagent._runner` 内 per-step 同步构造 `Agent`（Pydantic 字段填值），v1 agent 在 `Agent.run` → `_ensure_v1_agent` 中懒初始化
7. **`on_subagent_output` 是 side-channel** — tool 框架对返回值字符串化丢结构，必须靠回调拿完整 `SubagentOutput`

## 7. 上层接入

```python
from aicore.tools.dag_mini import create_chat_agent

# 1. 工厂构造（未启动 v1 agent）
chat = create_chat_agent(
    model="...",
    available_tools=[...],                    # 实际业务 tool 列表
    runtime_context={...},                    # 透给所有 per-step Agent
    subagent_system_prompt="...",             # 透给所有 per-step Agent
    task_agent_timeout=60,
    subagent_max_concurrent_steps=4,
    subagent_max_react_turns=2,
    on_subagent_output=my_callback,          # 拿结构化 SubagentOutput
)

# 2. 跑（首次调 run 时懒初始化 v1 agent）
result = await chat.run(query)
# result = {system, user, assistant, tool_calls}
# assistant 即 chat_agent 对用户的最终汇总回复
```

`CHAT_SYSTEM_PROMPT`（[prompt.py L70-80](file:///e:/nanoai/aicore/tools/dag_mini/prompt.py#L70-L80)）规定最外层行为：

- 涉及查/找/搜/导航/控车/回忆/推荐/播放/调整/提醒 → **必调** TaskAgent
- 纯知识问答（"X 是什么"）→ 直答
- 完成后按步骤汇总给用户极简回复

`TASK_AGENT_DESCRIPTION`（[prompt.py L43-63](file:///e:/nanoai/aicore/tools/dag_mini/prompt.py#L43-L63)）规定拆解约束：

- tool arguments 必须严格 JSON
- 条件分支 / 并列子查询合 1 step
- **独立子目标才拆 step**（A 和 B 无数据依赖、可并行 → 拆 2 step；A 是 B 的子查询 → 合 1 step 或 B→A）
- **避免"找周边/查资料"过大 step**（多类设施 + 详情 + 综合分析 → 拆"找候选" + "查详情" 2 step）
