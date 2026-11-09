# Auto Test Script（新手可直接上手版）

这个目录提供一套“全自动评测”机制，用来测车机助手在真实对话场景中的表现，尤其适合测试：

- 单轮/多轮对话质量
- 跨会话长期记忆能力
- 工具调用与意图理解
- 人设与上下文一致性

核心思路是：

1. 用 `FakePerson` 扮演用户和被测 Bot 对话  
2. 用 `Judge` 按 `expected_script + nl_assertion` 自动裁决  
3. 用 `AutoTestAndRLDataGenerator` 串联执行、汇总结果、写报告

---

## 1. 你需要知道的 4 个核心对象

- `TestCase`：一条测试用例定义
- `AnyBotToTest`：被测 Bot 协议（你自己的 Bot 只要实现这个协议就能接入）
- `AutoTestAndRLDataGenerator`：执行器（跑 case、收集 history、调用 judge）
- `VolcMemoryStore / MemoryProducer`：长期记忆写入与召回（按配置启用）

---

## 2. 最快上手（5 分钟）

### 第一步：准备一个 `TestCase`

最常用字段：

- `case_id`：用例业务 ID（建议可读）
- `context_config`：上下文配置（系统提示模板参数、记忆配置、用户信息等）
- `user_query_lists`：多次“多轮对话”的起始输入
- `expected_script`：理想剧本
- `nl_assertion`：通过标准

`user_query_lists` 支持两种格式：

- 旧格式：`list[Message]`
- 新格式：`DialogueRoundConfig`（推荐，支持 `mock_info` / `mock_time`）

---

### 第二步：准备被测 Bot（实现协议）

当前执行器依赖的协议方法是：

```python
class AnyBotToTest(Protocol):
    @classmethod
    def create(cls, context_config: dict[str, Any], *args, **kwargs): ...
    async def aupdate_context(self, context_config: dict[str, Any]) -> None: ...
    async def achat(self, query: str, session_id: str) -> str: ...
    async def adump_history(self) -> list[dict[str, str]]: ...
    async def adump_state_trace(self) -> dict: ...
```

其中最关键是：

- `aupdate_context(...)`：每次“多轮对话”开始前会调用，用于让 `mock_info/mock_time` 生效
- `achat(..., session_id)`：同一轮多轮对话 session_id 固定，跨轮会切换

---

### 第三步：执行

同步收敛结果：

```python
run_all_cases_result = auto_test.run_full_auto_judge_test(
    concurrency_mode=True,
    concurrency_num=10,
    pause_mode=False,
    memory_reset_mode=True,
    upload_history_to_volc_memory=False,
)
```

异步流式（推荐）：

```python
async for item in auto_test.arun_full_auto_judge_test(...):
    if isinstance(item, RunCaseResult):
        ...
    elif isinstance(item, RunAllCasesResult):
        final_result = item
```

---

## 3. 执行器机制（你需要理解的关键规则）

## 3.1 每个 case 的执行流程

1. 可选清理记忆（`memory_reset_mode=True`）
2. 初始化 `FakePerson`
3. 逐个执行 `user_query_lists` 中的“多轮对话”
4. 收集历史与 trace
5. `Judge` 给出通过/失败和理由

## 3.2 会话切分规则

- 每次“多轮对话”会生成新的 `session_id`
- 同一个 case 内，Bot 实例会复用，靠 `session_id` 切换触发 `new_session()` 与记忆提交

## 3.3 记忆 `user_id` 规则（非常重要）

- 只要 `context_config` 中有 `collection_name`，执行器会**强制**使用 `case_id` 作为 `user_id`
- 目的：避免并发或多 case 之间记忆串扰

## 3.4 `mock_info` 与 `mock_time` 的作用域

- `mock_info`：每次对话前通过 `aupdate_context` 注入，用于刷新 prompt/运行上下文（如 `car_info`）
- `mock_time`：每次对话前通过 `aupdate_context` 注入，供记忆写入时间使用
  - 如果 Bot 接入 `UserInfoMetadata.with_mock_time(...)`，则会按 mock_time 写入
  - 不配置 `mock_time` 时，回退为当前系统时间

---

## 4. 什么时候用 `upload_history_to_volc_memory`

- `False`（默认推荐）：被测 Bot 自己负责记忆生产（例如内置 `MemoryProducer`）
- `True`：执行器在每段多轮结束后，把 `history` 直接上传到火山记忆（旁路方式）

两条路径都支持 `mock_time`，但注入点不同：

- Bot 自生产路径：建议在 Bot 内通过 `UserInfoMetadata` 注入
- 执行器旁路上传：由 `VolcMemoryStore.aadd_history_to_memory(..., mock_time=...)` 注入

---

## 5. 推荐实践（避免踩坑）

- 一个 case 里需要跨会话记忆验证时，优先使用 `DialogueRoundConfig`
- 让 Bot 的 `aupdate_context` 做两件事：
  - 更新 prompt 渲染参数（让 `mock_info` 生效）
  - 更新记忆写入时间上下文（让 `mock_time` 生效）
- 若发现最后一段对话记忆没写入，检查是否在末轮后触发了 flush（这是 session 切换模型常见边界）
- Windows 终端调试建议开启 UTF-8，避免 `rich` 输出 emoji 编码报错

---

## 6. 目录说明

```
auto_test_script/
├── auto_test_and_rl_data_generator.py   # 核心执行器（FakePerson/Judge/ReportWriter）
├── case_schema.py                        # TestCase / DialogueRoundConfig 定义
├── auto_tagger/                          # 标签树与自动打标模块（详见 auto_tagger/README.md）
│   ├── tagger.py
│   ├── tag_tree_schema.py
│   └── tag_tree_template.json
├── auto_test_demos/                      # 可直接运行的示例脚本
│   ├── demo_auto_test.py
│   ├── demo_complex_reasoning_memory_production_auto_test.py
│   └── ...
└── auto_test_report/                     # 输出报告目录
```

---

## 7. 常用入口

- 本地手工验证：`auto_test_demos/demo_auto_test.py`
- 复杂推理服务验证：`auto_test_demos/demo_complex_reasoning_memory_production_auto_test.py`
- 标签树打标模块：`auto_tagger/README.md`
  - 支持标签树叶子校验失败自动重试（默认3次）
- 后台任务执行链路：`projects/mind/test_backend/service/task/task_auto_run_service.py`

---

## 8. 一句话总结

这套机制本质是“**用例驱动 + 虚拟人对话 + LLM 裁判 + 记忆可控注入**”。  
你只要准备好 `TestCase` 和实现 `AnyBotToTest`，就能稳定地把功能测试、记忆测试、回归测试统一到一条自动化流水线上。
