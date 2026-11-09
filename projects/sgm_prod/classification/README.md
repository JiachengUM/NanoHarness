# Simple/Complex Router Classification

这个目录实现 AI Car Lite 的简单/复杂意图仲裁器。当前实现遵循数据标签优先、规则快速证明、LLM 兜底的分层设计：给定数据集里的 exact case 先保证标签一致；能够被能力卡片和词表解析成完整简单能力的 query 走 parser；带未消费风险信号的 query 被 veto 到复杂；剩余 query 才进入 LLM fallback。

核心边界：simple 是封闭能力的高精度证明，不是“看起来像能处理”的泛化猜测。规则只证明确定可执行的一跳能力；开放目标、歧义目标、上下文目标、偏好/排序/推荐类目标，如果没有低时延 resolver 可以唯一落地，应进入 LLM fallback。

## 入口函数

### `arbitrate_simple_complex_decision`

文件：`projects/sgm_prod/classification/engine.py`

```python
decision = await arbitrate_simple_complex_decision(
    query,
    project="SGM",
    history=history,
)
```

调试规则本身时可以关闭 exact 和 LLM：

```python
decision = await arbitrate_simple_complex_decision(
    query,
    use_exact_match=False,
    use_llm_fallback=False,
)
```

返回 `RouterDecision`：

- `label`: `"simple"` 或 `"complex"`
- `source`: 决策来源，例如 `exact_simple`、`parser_simple`、`parser_veto`、`llm_complex`
- `trace`: 可排查的完整链路，包括归一化 query、命中的候选能力、风险标记和 decision path

这是新代码优先使用的主入口。

主要入参：

- `query`: 当前轮用户 query。
- `project`: 业务项目配置名，默认 `"default"`；例如 `"SGM"` 会读取 `assets/SGM/` 这套完整 profile。
- `history`: 用户历史，按时间正序传入。
- `use_exact_match`: 是否启用 exact CSV 命中，默认开启。
- `use_llm_fallback`: 是否启用 LLM fallback，默认开启。

### `arbitrate_simple_complex`

文件：`projects/sgm_prod/classification/__init__.py`

```python
label, source = await arbitrate_simple_complex(query, project="SGM", history=history)
```

这是兼容旧调用方的轻量入口，只返回 `(label, source)`，内部仍调用 `arbitrate_simple_complex_decision`。未传 `project` 时使用 `default` profile。

### HTTP API

文件：`projects/sgm_prod/api.py`

接口：`POST /v1/simple_complex_arbitration`

请求体：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `query` | string | 是 | - | 当前轮用户 query |
| `chat_id` | string | 是 | - | 会话 ID |
| `question_id` | string | 是 | - | 本轮请求 ID |
| `project` | string | 否 | `default` | 业务项目配置名；例如 `SGM` 对应 `assets/SGM/` |
| `history` | array | 否 | `[]` | 历史问答，按时间正序 |
| `debug` | boolean | 否 | `false` | 是否返回 trace |

请求示例：

```json
{
  "query": "打开左前车窗",
  "chat_id": "test_chat",
  "question_id": "test_question",
  "project": "SGM",
  "history": [],
  "debug": true
}
```

响应字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `errno` | int | `0` 表示正常仲裁；`400` 表示请求的 router project 不存在 |
| `msg` | string | 状态描述 |
| `data` | string | simple/complex 标签；配置错误时为空字符串 |
| `source` | string | 决策来源，例如 `exact_simple`、`parser_simple`、`llm_complex`、`config_error` |
| `trace` | object/null | `debug=true` 时返回规则链路；否则为 `null` |

正常响应示例：

```json
{
  "errno": 0,
  "msg": "success",
  "data": "simple",
  "source": "parser_simple",
  "trace": {
    "project": "SGM",
    "query": "打开左前车窗",
    "normalized_query": "打开左前车窗",
    "decision_path": ["exact_simple:not_hit", "exact_complex:not_hit", "parser:complete"],
    "risk_flags": [],
    "matched_candidates": [],
    "rule_version": "router_rules_navigation_llm_fallback"
  }
}
```

未知 project 不会静默降级到 `default`，会直接返回配置错误：

```json
{
  "errno": 400,
  "msg": "unknown router project: MISSING",
  "data": "",
  "source": "config_error",
  "trace": null
}
```

排查时优先看 `trace.project`，确认请求实际使用的是 `default` 还是 `SGM` profile。

## 代码结构

- `models.py`
  - 定义 `RouterDecision`、`RouterTrace`、`ParseCandidate`、`CapabilityCard`、`LexiconEntry`、`RiskRule` 等强类型模型。
  - `ParserRules` 描述 parser 流程需要的共享规则，例如填充词、疑问标记、值 token 正则和场景辅助词。
  - Pydantic 使用 `extra="forbid"`，避免资产文件悄悄写错字段。

- `normalize.py`
  - 统一 query 归一化逻辑。
  - exact map、parser、测试和资产加载都应使用同一套 normalization。

- `assets.py`
  - 加载并校验 `assets/<project>/` 下的能力卡、规则 YAML、数据集 CSV 和 LLM prompt 资产。
  - 启动后通过 profile registry 按 `project` 选择完整资产包；`default` 只是默认 profile 名，不是父配置。
  - 校验能力 ID、风险 ID、重复 query、简单/复杂 exact 冲突等问题。
  - 对外入口是 `get_router_assets(project)`；`load_router_assets()` 保留为 default/临时单目录兼容入口。

- `parser.py`
  - 规则 parser 核心。
  - 根据能力卡片的 `required_slots`、`actions`、`targets`、`values` 和 `rules/lexicon.yaml` 做 slot span 消费。
  - parser 不再维护中文关键词清单；横向解析信号来自 `rules/parser_rules.yaml` 和 `rules/global_risks.yaml`。
  - 未消费文本上的风险词会进入 `risk_flags`，用于 `parser_veto`。

- `engine.py`
  - 仲裁决策表。
  - 正常生产顺序是：exact simple -> exact complex -> parser complete -> parser risk veto -> LLM fallback -> default complex。
  - engine 不再维护导航/音乐硬编码白名单；能力卡通过 `route_policy` 表达完整命中后是直接 `parser_simple` 还是继续进入 LLM fallback。
  - 开放导航/音乐的轻量触发词放在对应 fallback 能力卡的 `intent_markers`，不再放在 `rules/parser_rules.yaml`。
  - 调试 parser/risk 规则时使用 `use_exact_match=False` 和 `use_llm_fallback=False`，避免临时注释生产链路。

- `llm.py`
  - 慢路径兜底，只应在 exact/parser 都无法确定时触发。
  - 默认系统 prompt 放在当前 profile 的 `llm_classfication/prompt.py` 的 `SYSTEM_PROMPT` 中；loader 按目录读取 prompt 资产集合，后续可按 capability 或 fallback 场景拆多个 prompt。

- `tools/build_router_assets.py`
  - 从 `/Users/WayneYu/Downloads/Router-case-v2.xlsx` 生成 exact CSV 资产。
  - `简单RAG` 会正式过滤 `意图领域=联网搜索` 和 `意图领域=S2S闲聊`；复杂 sheet 同时兼容 v1/v2 命名。

- `tools/evaluate_router_assets.py`
  - 评估 exact 资产是否仍然被 exact source 命中。
  - 注意：这个命令要求 `data/simple.csv` 必须由 `exact_simple` 命中，`data/complex.csv` 必须由 `exact_complex` 命中，避免 parser/LLM 偶然 label 正确却掩盖 exact 资产问题。

- `tools/evaluate_router_rules.py`
  - 关闭 exact 和 LLM，只评估能力卡片、词表和风险门本身。
  - 输出整体 rule coverage、命中 precision、按数据源 sheet 的覆盖/误判统计和前 20 个错例。

- `tools/run_benz_e2e_status.py`
  - BENZ profile 的端到端现状脚本，默认使用 `assets/benz`。
  - 依次运行 exact 资产健康检查、rule-only 基线、exact-off/LLM-on 端到端评测，并把日志、预测 CSV、失败 CSV 和文本报告写入 `reports/benz_e2e_status/<timestamp>/`。
  - 快速本地体检可运行：`python -m projects.sgm_prod.classification.tools.run_benz_e2e_status --skip-llm`。

- `tools/audit_router_cards.py`
  - 审计 `capabilities/*.yaml`、`rules/lexicon.yaml` 和 `rules/global_risks.yaml` 的能力边界。
  - 输出重复 ID、宽泛 target、跨能力 target/action 重叠、风险词被能力消费等问题。

- `tools/_asset_dir.py`
  - 评估脚本使用的临时资产目录切换器，确保 `--asset-dir` 不只是读取 case，也会让 engine 加载同一套规则资产。

- `reports/`
  - 规则评估后的错例分流产物。
  - `simple_rag_rule_uncovered_cases.csv`: `简单RAG` 中关闭 exact/LLM 后仍未被规则判成 simple 的样本。
  - `multi_turn.csv`: 从错例中单独拆出的多轮、上下文、噪声类样本，用于后续多轮交互设计。
  - `remaining_rule_analysis.md` 和 `remaining_rule_analysis_candidates.csv`: 排除暂不处理大类后的剩余规则化分析。

## 规则资产

资产根目录：`projects/sgm_prod/classification/assets/`

当前每个业务项目是一套完整 profile：

- `assets/default/`: 默认生产 profile。
- `assets/SGM/`: SGM 业务 profile。
- `assets/benz/`: BENZ 测试 profile，规则配置与 `default` 保持一致，`data/` 只保留 BENZ exact 测试集。

`default`、`SGM` 和 `benz` 是同级完整配置。运行时只按请求里的 `project` 选择 profile，不做 overlay、不继承、不把 default 当父配置。

- `RULE_CARDS.md`
  - 人工审阅入口，按“能力卡 + 值类型 + 复杂边界”解释当前规则。
  - PM/测试/研发讨论错例时优先看这里，再决定要改能力、词表、值类型还是风险边界。
  - 当前它是 runtime YAML 的人类可读视图；后续如果稳定，可以再升级成生成 runtime YAML 的源头。

- `assets/<project>/capabilities/`
  - 面向维护者的高精度白名单能力项，按执行工具拆分。
  - `vehicle_control.yaml`: 端侧车控能力，例如空调、车窗、灯光、座椅、泊车、车辆状态。
  - `system.yaml`: 端侧系统能力，例如显示、语言、主题、热点、DVR、语音包。
  - `media.yaml`: 媒体能力，例如音乐搜索、播放控制、视频应用、收音机、音量。
  - `navigation.yaml`: 导航能力，例如单目的地导航和路线偏好。
  - `call.yaml`: 电话能力，例如拨打、接听和拒接。
  - `weather.yaml`: 天气查询能力。
  - 每个能力只保留 `id`、`name`、文件级 `executor`、`required_slots`、`targets`、`actions`、`values`、`target_policy`、`residue_policy`。
  - `target_policy=open_after_action`: 动作后的自由文本可以作为目标，例如歌名、调频数字、目的地。
  - `residue_policy=safe_modifier`: 必要槽位命中后，允许安全修饰语和值残留被该能力吸收。
  - `route_policy=parser_simple`: card 完整命中后可以直接证明 simple；默认值。
  - `route_policy=llm_fallback`: card 或 `intent_markers` 命中后继续进入 LLM fallback，例如开放导航和开放音乐检索。
  - `intent_markers`: `llm_fallback` card 的轻量入口词，用于 parser 未完整命中但已经能看出属于该开放能力边界的 query。
  - `intent_marker_policy=override_cross_executor`: marker 命中时可覆盖其它 executor 的完整解析，用于防止开放音乐词被系统/车控 card 抢成 simple。
  - 同一能力内的并列目标由 parser 统一识别；车窗、灯光、座椅舒适、通用车控等多 target 会触发复杂边界。

- `assets/<project>/rules/`
  - 顶级规则 YAML 目录，放跨能力共享的词表、全局风险和 parser 流程配置。
  - 这类资产影响 parser/risk 的横向行为，不和具体 executor 能力卡混在一起。

- `assets/<project>/rules/lexicon.yaml`
  - slot 词表和别名。
  - 如果新增同义词、别称、口语说法，通常只改这里。
  - 能力卡片写入某个 `canonical` 时会展开该词条的全部 aliases；只写单个 alias 时只匹配该 alias，避免不同能力因为共享某个词而串到整组词表。

- `assets/<project>/rules/global_risks.yaml`
  - 全局风险信号。
  - 风险只在未被 parser 消费的文本上生效，避免把 `播放如果可以` 这类数据集 simple case 误杀。

- `assets/<project>/rules/parser_rules.yaml`
  - parser 自身需要的横向配置。
  - `harmless_fillers`: 残留文本清理用的礼貌词、语气词和轻量修饰词。
  - `generic_value_patterns`: 只用于识别未消费的额外值信号，辅助多意图判断；具体值能力仍写在 card 的 `values.patterns`。
  - `broad_target_canonicals`: 只作为维护分组的 target canonical，去重时不能吞掉真实 surface。
  - `query_like_capabilities`: 状态/查询类 card，普通疑问句不一定复杂。
  - `question_or_condition_markers` / `conditional_markers`: 疑问句、条件句的 parser 级风险触发词。
  - `scenario_capability_aux`: 场景辅助词到能力卡的白名单映射，只能在对应 card 完整命中后解释残留。
  - `scenario_friendly_risks`: 场景辅助命中后允许剥离的风险类型。

- `assets/<project>/llm_classfication/`
  - LLM fallback 的 prompt 资产目录。
  - `prompt.py` 暴露默认 `SYSTEM_PROMPT` 字符串；由于 `classification/assets.py` 与 `assets/` 目录同名，运行时按文件路径读取它，而不是作为 Python package import。
  - 同一 profile 后续可以增加多个 prompt asset，例如按 capability 或 fallback 场景拆分；当前 runtime 默认使用 `llm_prompts["default"]`。

- `assets/<project>/data/`
  - exact 测试集目录。
  - `simple.csv` / `complex.csv` 是运行时 exact 数据；`simple_benz.csv`、`simple_byd.csv` 等是按 domain 拆分后的来源数据，便于人工审计和重建。

- `assets/<project>/data/simple.csv`
  - 合并 BENZ 与 BYD 的 exact simple 样本。
  - 标准表头为 `query,label,source,domain`，不再维护 `reason`、`risk_type` 或 CSV 级 `capability_id`。

- `assets/<project>/data/complex.csv`
  - 合并 BENZ 与 BYD 的 exact complex 样本。
  - 与 `data/simple.csv` 使用同一标准表头。

## 正常决策链路

```text
query
  -> normalize_query
  -> exact simple cases
  -> exact complex cases
  -> parse_simple_candidates
       -> complete capability parse => simple / parser_simple
       -> partial parse with risk   => complex / parser_veto
       -> navigation open target    => continue to LLM fallback
       -> media open target         => continue to LLM fallback
  -> llm_fallback
  -> default_complex on LLM error
```

`trace.decision_path` 会记录实际路径，例如：

```text
["exact_simple:not_hit", "exact_complex:not_hit", "parser:complete"]
```

## 当前能力边界快照

| 执行域 | parser 可直接证明 simple | 进入 LLM fallback 或规则外处理 |
| --- | --- | --- |
| 端侧车控 | 空调温度/体感、风量/循环、车窗/遮阳帘、灯光/氛围灯、座椅/方向盘舒适、通用车控开关、车辆状态/锁、HUD/转向补盲、后视镜、泊车/驻车、座椅位置、空气悬架、冰箱、空气质量/香氛、驾驶/场景模式、除雾出风 | 条件联动、偏好记忆、场景目标、多 target 不同动作、多区域不同值 |
| 端侧系统 | 退出打断、影像/屏幕快捷控制、收藏、位置/目的地状态、拍照、DVR 采集、显示亮度、热点、时间格式、系统语言、主题壁纸、语音包 | 需要外部工具、多轮上下文或综合推理的系统任务 |
| 媒体 | 音量、音乐应用开关、视频应用/播放、播放进度、收音机、继续/暂停/上下首 | `media.music.search` 是 fallback card；歌名、歌手、歌单、榜单、风格、场景音乐和推荐检索进入 LLM fallback |
| 导航 | `navigation.session.control` 只覆盖无开放实体的导航会话控制 | `navigation.route.preference` 和开放 POI、地址、路线偏好、附近/推荐/排序等导航诉求进入 LLM fallback |
| 电话 | 拨打、接听、拒接、挂断、报警 | 联系人歧义、需要二次确认或通话内容推理 |
| 天气 | 单轮天气和天气要素查询 | 长时间范围、出行规划、天气后接车控动作 |
| 当前没有 parser card | 无 | 地点周边检索、开放域问答、简单闲聊/情绪陪伴不再作为 RULE_CARDS 的 runtime 能力卡；这类 case 只能来自 exact、LLM fallback 或上游链路 |

### 导航开放目标口径

在没有低时延 POI resolver 的前提下，规则层不能证明开放 POI 是否唯一、是否可直接导航、是否需要消歧。因此导航规则采用保守工程边界：

- 规则只直接放行无开放实体的导航控制，例如 `开始导航`、`发起导航`、`继续导航`、`结束导航`、`关闭导航`、`打开导航`、`导航去`、`导航到`。
- 只要 query 带有 POI、地址、路线偏好、附近/最近/评分/推荐、历史地点、上下文指代或多目的地信号，就不由 parser 判 simple。
- 导航实体类 query 不作为 parser veto 直接判 complex；它们应该进入 flash-LLM fallback，由轻量模型判断是否属于 simple 导航。
- 典型 LLM fallback 样例：`带我去首都机场`、`导航去合肥南站`、`去松美术馆`、`导航去正大广场，不走潜山路`、`找附近最近的花店导航过去`、`去第一个`。
- 典型规则 simple 样例：`开始导航`、`结束导航`、`继续导航`、`打开导航`、`导航到`。

这个边界的目标是保持 parser 高精度、低认知负担；导航开放目标的泛化性由 LLM 兜底承担，而不是在 YAML 里堆 POI 词表或复杂黑名单。

### 音乐开放目标口径

媒体规则只直接证明确定控制命令：音量、音乐应用开关、视频应用/播放、播放进度、收音机、继续/暂停/上一首/下一首。`media.music.search` 虽然能识别音乐检索意图，但 `route_policy=llm_fallback`，完整命中后仍继续进入 LLM fallback。

- 规则 simple 样例：`下一首`、`暂停播放`、`打开音乐`、`关闭音乐`、`收音机调到 FM90.9`。
- LLM fallback 样例：`播放周杰伦的歌`、`来点轻音乐`、`找一首适合下雨天的歌`、`播放最新榜单`、`放我偶像欢快点的歌`。
- `intent_marker_policy=override_cross_executor` 用于防止音乐开放词被系统/车控等其它 executor 抢成 parser simple。

## 常用维护方式

### 关键词应该放哪里

| 关键词类型 | 应放位置 | 例子 | 维护判断 |
| --- | --- | --- | --- |
| 能被具体工具执行的动作、目标、取值 | `capabilities/*.yaml` | `打开`、`后视镜加热`、`蓝色` | 能形成一张封闭 simple 能力卡 |
| 能力完整命中后的路由边界 | `capabilities/*.yaml` | `route_policy=llm_fallback`、`intent_markers` | 开放目标不是 parser 直接证明 simple |
| 多张 card 共享的同义词 | `rules/lexicon.yaml` | `主驾/主驾驶`、`车灯/大灯` | 只是不同说法，不改变能力边界 |
| 未消费后应升级复杂链路的风险词 | `rules/global_risks.yaml` | `如果`、`每天`、`途经` | 是反证据，不属于某个执行器 |
| parser 流程辅助信号 | `rules/parser_rules.yaml` | `吗`、`一下`、通用值正则、场景辅助词 | 用来解释残留/疑问/多值，不直接证明能力 |

新增错例时优先问：它是不是一个封闭执行器能力。如果是，补 card；如果只是别名，补 lexicon；如果是复杂反证据，补 risk；如果只是 parser 如何看待残留文本，补 parser_rules。
