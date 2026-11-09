# AI 评测可信度技术方案

> 本方案用于将当前基于对话文本的二元 LLM Judge，升级为可解释、可校准、可回放的测试评测系统。

---

## 1. 目标

当前评测主要将对话历史和自然语言断言交给 LLM，输出 `pass/fail + reason`。这种方式无法可靠判断工具是否真正执行、车机状态是否变化、日志是否缺失，也无法证明模型给出的置信度是否可信。

本方案的目标是：

- 用日志和 Trace 判断客观事实。
- 用 LLM 判断难以编码的语义问题。
- 用确定性的聚合策略产生最终结果。
- 用人工专家黄金集测量误判率并校准置信度。
- 保存完整证据和版本，使历史结果可以重新评测。

最终结果采用四态，而不是简单的二元结果：

| 结果 | 含义 |
|---|---|
| `PASS` | 必需证据完整，硬规则和语义要求均通过 |
| `FAIL` | 至少一项产品硬性要求失败 |
| `INCONCLUSIVE` | 缺少必需证据，无法判断产品是否正确 |
| `INFRA_ERROR` | 设备、网络、Adapter 或采集系统异常 |

---

## 2. 总体架构

```text
原始音频 / Agent Trace / 端侧日志 / 视频
                    │
                    ▼
       Evidence Collector（证据采集）
                    │
                    ▼
       Log Parser（项目级日志解析器）
                    │
                    ▼
       Evidence Bundle（统一证据模型）
              ┌─────┴─────┐
              ▼           ▼
      Rule Evaluator   Semantic Judge
       客观事实规则      LLM 语义判断
              └─────┬─────┘
                    ▼
       Decision Aggregator（决策聚合）
                    │
                    ▼
 PASS / FAIL / INCONCLUSIVE / INFRA_ERROR
                    │
                    ▼
       人工复核 + 黄金集评估 + 线上监控
```

职责边界：

| 组件 | 职责 | 不负责 |
|---|---|---|
| Evidence Collector | 收集原始音频、Trace、日志、视频并建立时间关联 | 不判断通过或失败 |
| Log Parser | 将不同车型日志转换为统一字段 | 不决定业务验收规则 |
| Rule Evaluator | 判断工具调用、返回值、状态变化等客观事实 | 不理解复杂自然语言 |
| Semantic Judge | 判断回复语义、上下文一致性、表达真实性 | 不覆盖明确的日志事实 |
| Decision Aggregator | 根据硬条件和优先级生成最终结果 | 不调用 LLM 自由决定结果 |
| Human Review | 复核低置信度、冲突和重要交付结果 | 不替代自动化运行 |

---

## 3. 核心数据结构

### 3.1 统一证据

```ts
interface EvidenceBundle {
  caseRunId: string
  timeWindow: { startedAt: string; endedAt: string }

  input: {
    expectedText?: string
    asrText?: string
    audioRef?: string
  }

  understanding: {
    intent?: string
    slots?: Record<string, unknown>
    resolvedEntities?: Array<{ type: string; name: string; id?: string }>
  }

  trace: {
    messages: Message[]
    toolCalls: ToolCall[]
    toolResults: ToolResult[]
  }

  state: {
    before?: Record<string, unknown>
    after?: Record<string, unknown>
  }

  output: {
    responseText?: string
    ttsStarted?: boolean
    ttsCompleted?: boolean
  }

  quality: {
    missingFields: string[]
    parserWarnings: string[]
    timeAlignmentValid: boolean
  }
}
```

原始证据必须保留，解析结果必须记录 `parser_version`。发现解析错误后，应能重新解析历史日志，而不需要重新运行车机。

### 3.2 评测结果

```ts
type Verdict = 'pass' | 'fail' | 'inconclusive' | 'infrastructure_error'

interface CheckResult {
  checkId: string
  source: 'rule' | 'llm' | 'derived_rule' | 'human'
  verdict: Verdict
  reasonCode: string
  reason: string
  evidenceRefs: string[]
  confidence?: number
}

interface EvaluationResult {
  verdict: Verdict
  summary: string
  checks: CheckResult[]
  missingEvidence: string[]
  confidenceLevel: 'high' | 'medium' | 'low'
  requiresHumanReview: boolean

  versions: {
    caseVersion: string
    projectConfigVersion: string
    logParserVersion: string
    ruleSetVersion: string
    judgePromptVersion?: string
    judgeModel?: string
    aggregatorVersion: string
  }
}
```

---

## 4. 完整开发流程

### 阶段 1：定义业务验收规范

由测试专家为每类能力定义：

- 必需证据字段。
- 硬性通过条件。
- 需要 LLM 判断的语义条件。
- `INCONCLUSIVE` 条件。
- 产品失败与基础设施失败的边界。

产物：版本化的 `EvaluationSpec`，例如 `navigation.start@v3`。

### 阶段 2：实现证据采集

为每个 `CaseRun` 采集：

- 用户输入和 ASR 结果。
- Agent 消息、Tool Call、Tool Result。
- 测试前后车机状态。
- TTS 状态、视频、截图和端侧原始日志。
- 各证据的时间戳和来源。

产物：可回放的原始 `EvidenceRecord`。

### 阶段 3：实现统一日志解析

每个项目的 Log Parser 将车型专属日志转换成 `EvidenceBundle`，并执行：

- 字段完整性检查。
- Tool Call 与 Tool Result 配对。
- CaseRun 时间窗口对齐。
- 上一条用例日志污染检测。
- 日志截断和解析警告记录。

产物：标准化证据及解析器测试样本。

### 阶段 4：实现规则评测引擎

规则采用声明式配置：

```yaml
id: navigation-start-v3
required_evidence:
  - understanding.resolvedEntities
  - trace.toolResults
  - state.after.navigation

checks:
  - id: poi_match
    source: understanding.resolvedEntities
    operator: contains_expected_entity
    required: true

  - id: navigation_tool_success
    source: trace.toolResults
    operator: successful_result
    tool: navigate_to
    required: true

  - id: final_navigation_state
    source: state.after.navigation
    operator: in
    expected: [NAVIGATING, ARRIVED]
    required: true
```

规则只输出结构化 `CheckResult`，不自由生成最终结论。

### 阶段 5：实现 LLM 语义 Judge

LLM 只处理规则不擅长的问题，例如：

- 回复是否声称操作已经成功。
- 多轮上下文是否一致。
- 是否正确处理歧义或澄清。
- 回复是否违反客户语言规范。

LLM 输入应是小而明确的问题，输出必须包含枚举结论和证据引用。禁止将整份日志直接交给 LLM 决定最终通过与否。

### 阶段 6：实现决策聚合器

建议使用固定优先级：

```text
设备或采集系统异常                  → INFRA_ERROR
缺少必需证据                        → INCONCLUSIVE
任一硬规则失败                      → FAIL
规则与 LLM 冲突                     → FAIL 或强制人工复核
硬规则通过且语义条件通过            → PASS
语义判断不稳定                      → 强制人工复核
```

最终结果由聚合器决定；LLM 可以生成摘要，但不能修改结构化结论。

### 阶段 7：构建专家黄金集

黄金集用于验证整个链路，而不只是验证 LLM。样本应覆盖：

- 正常通过和明确失败。
- 回复正确但工具失败。
- 工具成功但回复含糊。
- 日志缺失或互相冲突。
- 多轮、别名、ASR 错误和设备异常。
- 不同车型、版本和业务模块。

每条样本由两位专家独立标注；结论冲突时由第三位专家仲裁。标注内容包括总结果、各维度结果、失败类型和证据引用。

黄金集拆分为：

- 开发集：调试规则和 Prompt。
- 验证集：选择方案和阈值。
- 冻结测试集：发布门禁，开发期间不可反复调参。

### 阶段 8：评估、校准和灰度上线

重点指标：

| 指标 | 含义 |
|---|---|
| 误放率 | 专家判定失败、系统判定通过；最重要的风险指标 |
| 误杀率 | 专家判定通过、系统判定失败 |
| 可判定率 | 非 `INCONCLUSIVE` 的比例 |
| 证据完整率 | 必需日志字段齐全的比例 |
| 人工复核率 | 自动结果需要人工介入的比例 |
| 高置信度准确率 | 系统标记为高置信度的真实正确率 |

上线分三步：

1. **影子模式**：人工仍是最终结论，AI 只在后台比较。
2. **辅助模式**：AI 提供结论和证据，人工确认或改判。
3. **条件自动化**：仅证据完整、规则无冲突且经过校准的高置信度结果自动生效。

人工改判必须沉淀为困难样本，并定期加入下一版黄金集。

---

## 5. 完整示例：POI 别名导航

### 5.1 用例

```text
用户：带我去那个波浪形状的写字楼

预期：
1. 将“波浪形状的写字楼”解析为上海中心大厦。
2. 调用 navigate_to。
3. 导航工具执行成功。
4. 最终状态为 NAVIGATING 或 ARRIVED。
5. 回复不得谎称未发生的操作已经成功。
```

### 5.2 实际回复

```text
助手：好的，正在为您导航到上海中心大厦。
```

仅根据文本，LLM 很可能判定通过。但端侧证据为：

```json
{
  "asr_result": "带我去那个波浪形状的写字楼",
  "resolved_poi": { "name": "上海中心大厦" },
  "tool_call": {
    "name": "navigate_to",
    "arguments": { "poi": "上海中心大厦" }
  },
  "tool_result": {
    "success": false,
    "error_code": "ROUTE_ENGINE_TIMEOUT"
  },
  "navigation_state": "IDLE"
}
```

### 5.3 分项判定

| 判定明细 | 来源 | 结果 |
|---|---|---|
| ASR 正确识别用户输入 | 规则 | 通过 |
| POI 解析为上海中心大厦 | 规则 | 通过 |
| 已调用 `navigate_to` | 规则 | 通过 |
| 工具返回 `ROUTE_ENGINE_TIMEOUT` | 规则 | 失败 |
| 最终导航状态仍为 `IDLE` | 规则 | 失败 |
| 回复表达“导航已经开始” | LLM | 命中 |
| 回复与实际执行状态冲突 | 组合规则 | 失败 |

聚合结果：

```json
{
  "verdict": "fail",
  "summary": "目的地理解正确，但导航工具执行超时，最终状态仍为 IDLE；助手却声称已经开始导航。",
  "confidenceLevel": "high",
  "requiresHumanReview": false
}
```

这里的 `FAIL` 由硬规则和聚合器产生，不是由 LLM 自由决定。LLM 只判断“回复是否表达了成功”。

### 5.4 缺日志时的结果

如果缺少 `tool_result` 和 `navigation_state`：

```json
{
  "verdict": "inconclusive",
  "summary": "缺少导航工具结果和最终状态，无法确认导航是否执行成功。",
  "missingEvidence": [
    "trace.toolResults.navigate_to",
    "state.after.navigation"
  ],
  "requiresHumanReview": true
}
```

此结果不能计入产品通过率分母，应单独计入证据完整率。

### 5.5 黄金集如何发现问题

假设黄金集中专家结论为 `FAIL`，但当前系统输出 `PASS`，差异分析可能定位到：

```text
专家：工具失败，因此整体失败
系统：只使用了对话文本，未读取 Tool Result
误判类型：FALSE_PASS / TOOL_FAILURE_IGNORED
修复动作：增加 navigation_tool_success 硬规则
```

修复后在冻结测试集重跑。如果导航误放率下降且其他模块没有退化，才允许发布新规则版本。

---

## 6. 与当前代码的衔接

当前 `packages/evaluation` 已具备 Agent Adapter、对话历史和 LLM Judge，可按以下顺序改造：

1. 将 `JudgeResult.is_pass` 升级为四态 `EvaluationResult.verdict`。
2. 为每次执行新增 `CaseRun`、原始证据和版本快照。
3. 在 Adapter 中完整保留 Tool Call、Tool Result 和错误事件。
4. 增加 `EvidenceNormalizer` 与 `EvidenceValidator`。
5. 增加声明式 `RuleEvaluator`。
6. 将现有 Judge 收敛为细粒度 `SemanticJudge`。
7. 增加确定性的 `DecisionAggregator`。
8. 建设人工复核页面、黄金集管理和离线评测流水线。

第一版应优先支持 Agent Trace 中已有的 Tool Call/Tool Result；端侧日志和视频证据随后接入。这样可以先建立评测结构，再逐步提高证据完整度。

---

## 7. 发布要求

每次修改 Log Parser、规则、Prompt、模型或聚合策略时必须：

1. 在冻结黄金集上重跑。
2. 对比误放率、误杀率、可判定率和人工复核率。
3. 检查各业务模块是否发生退化。
4. 保存评测报告和所有组件版本。
5. 未达到项目门槛时不得替换线上版本。

可信评测的核心不是让 LLM 更笃定，而是让每个结论都有证据、每个版本都能验证、每次误判都能被发现和修复。
