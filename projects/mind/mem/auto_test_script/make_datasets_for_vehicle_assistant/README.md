# 车载助手评测数据集合成项目

## 背景

车载语音助手（车机助手）的评测需要大量高质量的对话测试用例，覆盖从车控操作、导航服务到记忆理解等各类能力。传统方式依赖人工逐条编写，效率低、覆盖率难以保证、质量标准不统一。

本项目沉淀了一套**从需求到数据集的完整工作流**，将数据集合成拆解为8个可独立执行的环节，每个环节有明确的输入/输出、质量标准和自动化脚本支持。

## 目的

- **自动化**：将评测数据集的合成过程流程化、脚本化，减少人工重复劳动
- **高覆盖**：通过标签树 + 复合标签采样确保能力点全覆盖
- **高质量**：通过清洗管线 + 多层审计确保用例质量
- **可复用**：以基础标签树为起点，不同车载助手项目只需做少量增量调整即可复用整个流程
- **内容层面评测**：所有环节聚焦于「助手说了什么、做对了没有」，不涉及技术实现、性能指标、UI规格等非内容层面
- **多项目并行**：支持同时进行多个项目的数据集合成，互不干扰

## 目录结构

```
make_datasets_for_vehicle_assistant/
├── skills/              8个环节的Skill定义（执行规范）
│   ├── _shared_case_writing_principles.md   用例编写通用原则（环节2/4/5/6共享）
│   ├── _shared_case_audit_principles.md     用例审核通用原则（环节5/6共享）
│   └── <stage>/SKILL.md                     各环节独有规范
├── scripts/             各环节的自动化脚本
├── artifacts/           数据产物
│   ├── base/            共享基础资源（领域级，所有项目共用）
│   └── projects/        各项目独立工作空间
│       ├── <project_a>/ 项目A的完整工作空间
│       └── <project_b>/ 项目B的完整工作空间
└── docs/                经验沉淀文档
```

## 多项目并行

本项目支持同时进行多个车载助手项目的数据集合成工作。各项目共享基础标签树，但拥有独立的工作空间，互不干扰。

```
artifacts/
├── base/                                  ← 共享基础资源（领域级）
│   ├── base_vehicle_assistant_case_tag_tree.json
│   └── base_vehicle_assistant_case_tagging_guideline.md
└── projects/
    ├── sgm_2026/                          ← 项目A
    │   ├── inputs/                        ← 环节0: 原始文件+提取产物
    │   ├── tag_tree/                      ← 环节1: 标签树+打标指南+审核覆盖
    │   ├── cases/                         ← 环节2/4: 用例库
    │   ├── composite_sampling/            ← 环节3: 复合标签组合
    │   ├── batches/                       ← 环节4: 批次文件
    │   ├── audit_results/                 ← 环节5: 审计结果
    │   └── exports/                       ← 环节7: 导出
    └── byd_seal/                          ← 项目B
        └── ...（同结构）
```

**约定**：
- `artifacts/base/` 是领域级共享资源，所有项目从这里读取基础标签树，不应被项目环节修改
- `artifacts/projects/<project_name>/` 是项目级独立工作空间，项目间完全隔离
- 项目命名建议：`<客户>_<车型>` 或 `<产品线>_<版本>`，如 `sgm_2026`、`byd_seal`
- 各环节执行时需指定项目名，脚本和 Skill 会定位到对应项目目录

## 核心产物

每个项目的工作空间围绕三件核心产物展开，它们必须保持一致：

| 产物 | 文件（项目目录下） | 说明 |
|------|------|------|
| **标签树** | `tag_tree/vehicle_assistant_case_tag_tree.json` | 所有可测能力点的层级定义，唯一事实来源 |
| **打标指南** | `tag_tree/vehicle_assistant_case_tagging_guideline.md` | 每个叶子标签的语义定义、用户说法示例、项目写作原则覆盖 |
| **用例库** | `cases/vehicle_assistant_cases.json` | 包含 `leaf-*`（叶子示范）和 `composite-*`（复合用例） |

**环节0预处理产物**：`<P>/inputs/extracted/` 下的文件是中间产物，不是核心产物，但为环节1/2/4提供重要参考。标签线索辅助增量识别，已有case辅助风格参考和场景灵感，需求描述补充需求增量。

**写作原则优先级**：`skills/_shared_case_writing_principles.md`（基础）→ `<P>/tag_tree/vehicle_assistant_case_tagging_guideline.md` §2.1（项目覆盖，优先）。项目指南中没有覆盖的标签，遵循基础原则。项目覆盖从评审反馈中增量生长——评审时吐槽了什么项目特有的问题，就补什么。

**审核原则优先级**：`skills/_shared_case_audit_principles.md`（基础）→ `<P>/tag_tree/case_audit_supplements.md`（项目覆盖，优先）。`full_case_audit.py` 运行时自动加载并合并两者。项目审核原则从审计反馈中增量生长——审计时发现了项目特有的审核问题，就补什么。

**三者一致性原则**：标签树定义了哪些能力可测 → 打标指南解释每个能力怎么测 → 用例库按定义写出具体测试。任何一方的变更都必须同步到另外两方。

**反馈回路**：环节2生成高质量叶子示范后，应将优质用例反哺回打标指南，替换初始的粗糙示例。这是因为环节1构建标签树时，guideline 中的例子往往比较概括；环节2产出真实可用的示范用例后，guideline 应同步更新为更精准的示例。

## 环节流程

整个数据集合成分8个环节，但不是简单的线性推进。实际工作方式是**分批生产**——每次手写一批（约20条），审计修复后并入总集，检查覆盖率，不够就再写一批。因此形成了**两个生产循环**：

```
环节0: 输入预处理（按需）
  <P>/inputs/raw/各种原始文件 → <P>/inputs/extracted/标签线索+已有case+需求描述
  👤 人工确认提取报告
  ↓
环节1: 构建标签树（一次性）
  <base>/基础标签树 + <P>/inputs/extracted/提取产物（或需求文档）→ <P>/tag_tree/标签树+指南
  👤 人工确认标签树和指南
  ↓
╔═══ 叶子用例生产循环 ═══════════════════════════════════════════════╗
║  环节2: 挑未覆盖叶子 → 写一批leaf case（约20条）                    ║
║    👤 人工确认本批用例                                              ║
║    ↓                                                              ║
║  环节5: 审计本批 → 审计报告                                        ║
║    👤 人工确认审计报告                                              ║
║    ↓                                                              ║
║  环节6: 修复本批 → 修复后用例                                      ║
║    👤 人工确认修复结果                                              ║
║    ↓                                                              ║
║  合并入总集 → 查叶子覆盖率 → <100%? 回到环节2继续                  ║
╚════════════════════════════════════════════════════════════════════╝
  ↓ (叶子覆盖率100%)
环节3: 场景模板与覆盖采样
  <P>/tag_tree/ → <P>/composite_sampling/场景模板+缺口报告
  👤 人工确认场景模板
  ↓
╔═══ 复合用例生产循环 ═══════════════════════════════════════════════╗
║  环节4: 挑未覆盖场景 → 写一批composite case（约20条）              ║
║    👤 人工确认本批用例                                              ║
║    ↓                                                              ║
║  环节5: 审计本批 → 审计报告                                        ║
║    👤 人工确认审计报告                                              ║
║    ↓                                                              ║
║  环节6: 修复本批 → 修复后用例                                      ║
║    👤 人工确认修复结果                                              ║
║    ↓                                                              ║
║  合并入总集 → 查场景覆盖率 → 未达标? 回到环节4继续                 ║
╚════════════════════════════════════════════════════════════════════╝
  ↓ (场景覆盖率达标)
环节7: 最终覆盖率报告与导出
  <P>/cases/ + <P>/tag_tree/ → 终端报告 + <P>/exports/
  👤 人工确认最终报告

写作原则 = _shared_case_writing_principles.md（基础）+ <P>/guideline §2.1（项目覆盖，优先）
环节5/6是公共服务，被两个生产循环共用
每个环节支持迭代：输出可作为下次输入，增量改进而非从零重建
```

### 各环节输入输出详表

| 环节 | Skill | 输入 | 输出 |
|------|-------|------|------|
| 0.输入预处理 | `0_input_ingestion` | `<P>/inputs/raw/`各种原始文件 | `<P>/inputs/extracted/`标签线索+已有case+需求描述+提取报告 |
| 1.构建标签树 | `1_tag_tree_from_requirements` | `<base>/base_*_tag_tree.json` + `<base>/base_*_guideline.md` + `<P>/inputs/extracted/` | `<P>/tag_tree/`标签树+指南 |
| 2.叶子示范用例 | `2_tag_tree_to_testset` | `<P>/tag_tree/`标签树+指南(含写作覆盖) + 叶子覆盖率报告 | `<P>/cases/`用例库(leaf-*) + `<P>/tag_tree/`指南(反哺更新) |
| 3.场景模板与覆盖采样 | `3_composite_tag_sampling` | `<P>/tag_tree/`标签树+指南 | `<P>/composite_sampling/`场景模板+缺口报告 |
| 4.合成复合用例 | `4_composite_cases` | `<P>/tag_tree/`标签树+指南(含写作覆盖) + `<P>/cases/` + `<P>/composite_sampling/` + 场景覆盖率报告 | `<P>/cases/`(追加composite-*) + `<P>/batches/` |
| 5.质量审计 | `5_quality_audit` | `<P>/cases/` + `<P>/tag_tree/`标签树+指南 | `<P>/audit_results/`审计报告 |
| 6.审计修复 | `6_audit_fix` | `<P>/cases/` + `<P>/audit_results/` + `<P>/tag_tree/`指南(含写作覆盖) | `<P>/cases/`(原地更新) |
| 7.覆盖率与导出 | `7_coverage_and_export` | `<P>/cases/` + `<P>/tag_tree/`标签树 | 终端报告 + `<P>/exports/` |

**环节1核心理念**：车载助手项目大同小异，标签树的主体来自领域常识，需求文档和环节0提取产物只提供增量。通用对话Agent视角是行业层面的评测视角，不会出现在需求文档中，由基础标签树自带。

---

## 数据流总览

```
skills/                                    ← 执行规范
  _shared_case_writing_principles.md            ← 用例编写通用原则（环节2/4/5/6共享）
  _shared_case_audit_principles.md              ← 用例审核通用原则（环节5/6共享）
  <stage>/SKILL.md                              ← 各环节独有规范

artifacts/base/                            ← 领域级共享资源（所有项目共用）
  base_vehicle_assistant_case_tag_tree.json       ← 基础标签树
  base_vehicle_assistant_case_tagging_guideline.md ← 基础打标指南

artifacts/projects/<project>/              ← 项目级独立工作空间
  inputs/                                  ← 环节0: 原始文件+提取产物
    raw/                                          ← 各种原始文件（环节0输入）
    extracted/                                    ← 环节0提取产物
      extracted_tag_hints.json                      ← 标签线索
      extracted_cases_raw.json                      ← 已有case（原始格式）
      extracted_requirements.md                     ← 需求描述
      extraction_report.md                          ← 提取报告
  tag_tree/                                ← 环节1产出 → 环节2/3/4/5/6/7读取
    vehicle_assistant_case_tag_tree.json         ← 项目标签树
    vehicle_assistant_case_tagging_guideline.md  ← 项目打标指南（含§2.1项目写作原则覆盖）
    case_audit_supplements.md                    ← 项目审核原则覆盖（优先于基础审核原则）
  cases/                                   ← 环节2产出 → 环节3/4读取 → 环节4追加 → 环节5/6原地更新
    vehicle_assistant_cases.json                 ← 含leaf-*和composite-*
  composite_sampling/                      ← 环节3产出 → 环节4读取
    scenario_templates.json                       ← 场景模板（场景+标签组合）
    coverage_gap_report.json                      ← 覆盖缺口报告
  batches/                                 ← 环节4中间产物
    handwritten_batches/
  audit_results/                           ← 环节5产出 → 环节6读取
  exports/                                 ← 环节7产出
    product_subtree_*.json
    product_perspective_L1_export/
```

## 知识图谱

本项目提供了 `project_knowledge_graph.json`，将项目的架构（8个环节、产物依赖、脚本归属、原则优先级链、生产循环）建模为知识图谱。

### 图谱内容

| 实体类型 | 数量 | 说明 |
|---------|------|------|
| `project` | 1 | 项目根节点 |
| `stage` | 8 | 环节0-7 |
| `shared_principle` | 2 | 写作原则 + 审核原则 |
| `project_override` | 2 | 项目级写作覆盖 + 审核覆盖 |
| `production_loop` | 2 | 叶子用例循环 + 复合用例循环 |
| `script` | 14 | 所有活跃脚本 |
| `artifact` | 10 | 关键产物文件 |

关系类型包括：`feeds_into`（数据流）、`feeds_back_to`（修复回环）、`produces`/`consumes`（产物关系）、`uses_script`（脚本归属）、`references`（原则引用）、`loads_at_runtime`（运行时加载）、`overrides`（优先级覆盖）、`includes`（循环组成）。

### 用途

如果你使用的 AI 工具支持知识图谱（如 MCP Knowledge Graph Memory），可以加载此文件获得以下能力：

1. **影响分析**：修改某个产物文件时，通过 `consumes` 关系快速定位所有下游环节。例如修改标签树会影响环节2/3/4/5/6/7
2. **脚本定位**：执行某个环节时，通过 `uses_script` 关系找到对应的脚本。例如环节6需要运行 `fix_case_by_audit.py` + `batch_audit_fix.py` + 两个 normalize 脚本
3. **原则追踪**：修改共享原则时，通过 `references` 和 `loads_at_runtime` 关系确认影响范围。例如修改 `_shared_case_audit_principles.md` 会影响 `full_case_audit.py` 和 `fix_case_by_audit.py` 的运行时行为
4. **回溯路径**：通过 `feeds_back_to` 关系理解修复回环。环节6修复后回到环节2或环节4重新生产
5. **优先级判断**：通过 `overrides` 关系确认项目覆盖优先于基础原则

### 加载方式

```python
import json
with open("project_knowledge_graph.json", encoding="utf-8") as f:
    graph = json.load(f)
# graph["entities"] — 所有实体
# graph["relations"] — 所有关系
```

如果使用 MCP Knowledge Graph Memory 工具，可以直接将实体和关系逐条导入。

## 快速开始

### Python 环境约定

本项目所有脚本统一使用 conda 的 `dzy_env` 环境：

```
Python 解释器: D:\apps\miniconda\envs\dzy_env\python.exe
CLI 工具:     markitdown（已装在 dzy_env，用于把 office/pdf 等原始文件转 markdown）
```

下文命令示例中 `python` 均指上述解释器。在 PowerShell 中可这样调用：

```powershell
D:\apps\miniconda\envs\dzy_env\python.exe scripts/leaf_cases/check_json_format.py
```

`markitdown` 可直接处理环节0的原始文件（csv/xlsx/docx/pdf/pptx），把内容转成 markdown 供后续提取：

```powershell
D:\apps\miniconda\envs\dzy_env\python.exe -m markitdown inputs/raw/xxx.xlsx -o inputs/extracted/xxx.md
```

### 查看基础标签树

```bash
python scripts/tag_tree/preview_vehicle_tag_tree.py
```

### 查看指定标签树文件

```bash
python scripts/tag_tree/preview_vehicle_tag_tree.py artifacts/projects/<project>/tag_tree/vehicle_assistant_case_tag_tree.json
```

### 仅查看叶子标签清单

```bash
python scripts/tag_tree/preview_vehicle_tag_tree.py --leaves-only
```

### 校验用例 JSON 格式（强烈建议每写完一批就跑一次）

每写完一批 case 后，**必须**跑格式校验脚本，确保 JSON 可解析、字段完整、id 唯一：

```bash
python scripts/leaf_cases/check_json_format.py artifacts/projects/<project>/cases/vehicle_assistant_cases.json
```

不带参数时默认校验 benz 项目：

```bash
python scripts/leaf_cases/check_json_format.py
```

校验内容：
- JSON 格式是否合法（解析失败会给出错误行号和上下文）
- 顶层是否为数组
- 每条 case 是否包含必需字段（id / case_id / context_config / max_round / user_query_lists / expected_script / nl_assertion / code_assertion / case_description / tags）
- id 是否唯一
- tags / user_query_lists / nl_assertion 是否为数组且非空

### 修复字符串值内误用的 ASCII 双引号

如果校验报 `JSON 解析失败`，且错误指向字符串值内部的引号（常见于 expected_script / nl_assertion 字段里用 `"..."` 包裹中文内容），可一键修复：

```bash
python scripts/leaf_cases/fix_ascii_quotes.py artifacts/projects/<project>/cases/vehicle_assistant_cases.json
```

该脚本会逐字符扫描，把字符串值内部未转义的 ASCII `"` 转义为 `\"`。**但更推荐的做法是写作时遵守下面的约定**：

**写作约定**：在 case 的字符串字段（expected_script / nl_assertion / case_description 等）内引用中文内容时，**使用中文引号 `"..."` 或单引号 `'...'`，不要使用 ASCII 双引号 `"`**，以免与 JSON 字符串分隔符冲突。

---

## 全局数据合成工作原则

本节是贯穿所有环节的工作原则。无论你在哪个环节（写 case / 审计 / 修复 / 扩展标签树 / 改脚本），都必须遵守以下约定。这些约定来自实际踩坑，每条都有对应的自动化校验或审核原则。

### 原则1：每写完一批 case，必跑格式校验

**强制**。每写完一批 case（无论手写还是脚本生成），**立即**跑 `check_json_format.py`，不跑不算完成。

```powershell
D:\apps\miniconda\envs\dzy_env\python.exe scripts/leaf_cases/check_json_format.py artifacts/projects/<project>/cases/vehicle_assistant_cases.json
```

校验内容（脚本已实现）：
- JSON 格式是否合法（解析失败会给出错误行号和上下文）
- 顶层是否为数组
- 每条 case 是否包含必需字段（id / case_id / context_config / max_round / user_query_lists / expected_script / nl_assertion / code_assertion / case_description / tags）
- id 是否唯一
- tags / user_query_lists / nl_assertion 是否为数组且非空
- **C1 检查**：`user_query_lists` 每 session 是否只有1条 user（冷启动入口单条原则）

若校验报 `JSON 解析失败` 且指向字符串内引号，跑 `fix_ascii_quotes.py` 一键修复。

### 原则2：冷启动入口单条（C1）

`user_query_lists` 是冷启动入口，被测侧只读这一条触发对话。**每个 session 只能有1条 user 消息**。同会话第2轮起的用户台词，全部写在 `expected_script` 的「用户：」行里。

**反例（❌）**：
```json
"user_query_lists": [
  [
    {"role": "user", "content": "今天有什么热点新闻？"},
    {"role": "user", "content": "关于第一条新闻，还有什么相关报道？"}
  ]
]
```

**正例（✅）**：
```json
"user_query_lists": [
  [
    {"role": "user", "content": "今天有什么热点新闻？"}
  ]
],
"expected_script": "用户：今天有什么热点新闻？\n管家：（...）\n用户：关于第一条新闻，还有什么相关报道？\n管家：（...）"
```

详见 [_shared_case_writing_principles.md](file:///d:/yitu_projects/nanoai/projects/mind/mem/auto_test_script/make_datasets_for_vehicle_assistant/skills/_shared_case_writing_principles.md) §8.4 和 [_shared_case_audit_principles.md](file:///d:/yitu_projects/nanoai/projects/mind/mem/auto_test_script/make_datasets_for_vehicle_assistant/skills/_shared_case_audit_principles.md) §C1。校验已内置在 `check_json_format.py`。

### 原则3：闭环前置（不用 car_info 预设代替对话生产前提）

**禁止用 car_info 预设来代替对话建立前提**。以下三类前提必须通过对话生产：

| 前提类型 | 反例（❌） | 正例（✅） |
|---|---|---|
| 媒体状态 | `car_info: 当前媒体：陈奕迅《十年》播放中` + 单轮 `这是什么歌` | 第一轮 `我想听陈奕迅的歌` → 第二轮 `这是什么歌` |
| 用户偏好记忆 | `car_info: 用户记忆：喜欢蓝色` + 单轮 `把氛围灯调成我喜欢的颜色` | 第一次对话 `你记住我喜欢蓝色` → 第二次对话 `把氛围灯调成我喜欢的颜色` |
| 任务上下文 | `car_info: 当前导航：前往天安门` + 单轮 `还有多久到` | 第一轮 `导航去天安门` → 第二轮 `还有多久到` |

**car_info 仅用于客观硬件/环境状态**：位置、时间、档位、车速、车外/车内温度、蓝牙/USB/已安装应用等不依赖用户对话的初始环境信息。

两种实现结构：
- **单会话多轮前置**：前提与消费在同一会话，`user_query_lists: [[首条指令]]`，expected_script 同会话内多轮
- **多次多轮前置**：前提与消费跨会话，`user_query_lists: [[前提指令], [消费指令]]`，expected_script 用 `（重启新的对话……）` 分隔

详见 [_shared_case_writing_principles.md](file:///d:/yitu_projects/nanoai/projects/mind/mem/auto_test_script/make_datasets_for_vehicle_assistant/skills/_shared_case_writing_principles.md) §10.0 和 [_shared_case_audit_principles.md](file:///d:/yitu_projects/nanoai/projects/mind/mem/auto_test_script/make_datasets_for_vehicle_assistant/skills/_shared_case_audit_principles.md) §C2b。

### 原则4：JSON 写作约定（避免引号冲突）

在 case 的字符串字段（expected_script / nl_assertion / case_description 等）内引用中文内容时，**使用中文引号 `"..."` 或单引号 `'...'`，不要使用 ASCII 双引号 `"`**。

若校验报 `JSON 解析失败`，跑 `fix_ascii_quotes.py` 一键修复：
```powershell
D:\apps\miniconda\envs\dzy_env\python.exe scripts/leaf_cases/fix_ascii_quotes.py artifacts/projects/<project>/cases/vehicle_assistant_cases.json
```

### 原则5：重试先导剧本（奔驰项目特有）

> **注意**：重试先导段是**奔驰项目特有规则**（含"你好奔驰"唤醒词），定义见奔驰项目写作原则 §2.1.7（`artifacts/projects/benz_project/tag_tree/vehicle_assistant_case_tagging_guideline.md`）。通用原则不强制重试先导段（通用写作原则§7.3.7 仅定义前导段的通用结构，项目特有先导段由各项目自行定义）。

奔驰项目所有 case 的 `expected_script` 最开始都加上重试先导剧本，让假人在管家没说话时可重试：

```
管家可能耳背，有时听不到导致没能回复你，那么你扮演用户时如果发现管家没说话的话，你可以重试最多3次，每次重试时都需要在指令前加上固定的唤醒词"你好，你好奔驰"，且你可以把除了唤醒词之外的内容换各种同义说法重试。

用户：...
管家：（...）
```

先导剧本用空行与正文分隔。批量添加用 `add_retry_preamble.py`（若需要重新生成）。

### 原则6：项目产物三件一致性

标签树、打标指南、用例库三者必须一致：
- **标签树**定义了哪些能力可测 → **打标指南**解释每个能力怎么测 → **用例库**按定义写出具体测试
- 任何一方的变更都必须同步到另外两方
- 新增叶子 → 标签树加节点 + guideline 加说明 + 至少1条 case 覆盖
- 修改叶子语义 → 三方同步更新

### 原则7：分批生产 + 人工确认

实际工作方式是**分批生产**——每次手写一批（约20条），审计修复后并入总集，检查覆盖率，不够就再写一批。不要一次性写完所有 case 再审，这样质量无法保证。

两个生产循环：
- **叶子用例循环**：环节2写 → 环节5审 → 环节6修 → 查叶子覆盖率 → <100% 回到环节2
- **复合用例循环**：环节4写 → 环节5审 → 环节6修 → 查场景覆盖率 → 未达标回到环节4

每批都需人工确认本批用例、审计报告、修复结果。

### 原则8：原则优先级链

**写作原则**：`skills/_shared_case_writing_principles.md`（基础）→ `<P>/tag_tree/vehicle_assistant_case_tagging_guideline.md` §2.1（项目覆盖，优先）

**审核原则**：`skills/_shared_case_audit_principles.md`（基础）→ `<P>/tag_tree/case_audit_supplements.md`（项目覆盖，优先）

项目指南中没有覆盖的标签，遵循基础原则。项目覆盖从评审反馈中增量生长——评审时吐槽了什么项目特有的问题，就补什么。

### 原则9：Python 环境约定

所有脚本统一使用 conda 的 `dzy_env` 环境：

```
Python 解释器: D:\apps\miniconda\envs\dzy_env\python.exe
CLI 工具:     markitdown（已装在 dzy_env，用于把 office/pdf 等原始文件转 markdown）
```

下文命令示例中 `python` 均指上述解释器。在 PowerShell 中可这样调用：

```powershell
D:\apps\miniconda\envs\dzy_env\python.exe scripts/leaf_cases/check_json_format.py
```

`markitdown` 可直接处理环节0的原始文件（csv/xlsx/docx/pdf/pptx），把内容转成 markdown 供后续提取：

```powershell
D:\apps\miniconda\envs\dzy_env\python.exe -m markitdown inputs/raw/xxx.xlsx -o inputs/extracted/xxx.md
```

### 原则10：脚本通用化（避免硬编码）

所有脚本必须通用化，不能硬编码项目名。已有脚本支持 `--project` 参数：

```powershell
# 审计指定项目
D:\apps\miniconda\envs\dzy_env\python.exe scripts/audit/full_case_audit.py --project benz_project --all

# 校验指定项目
D:\apps\miniconda\envs\dzy_env\python.exe scripts/leaf_cases/check_json_format.py artifacts/projects/benz_project/cases/vehicle_assistant_cases.json
```

新增脚本时，必须支持 `--project` 参数或接受项目路径作为参数，不得硬编码 `general_vehicle_assistant` 或 `benz_project`。

### 原则11：sys.path 路径修正

部分脚本需要 import `nanoai` 包（如 `full_case_audit.py` import `nanoai.model.llm`）。这些脚本的 `sys.path.insert` 必须指向 `d:\yitu_projects\nanoai` 根目录：

```python
# 加到 d:\yitu_projects\nanoai 根目录，使 from nanoai.model.llm import allm_output 可用
sys.path.insert(0, str(Path(__file__).resolve().parents[7]))
```

`parents[7]` 是从 `scripts/audit/full_case_audit.py` 往上7级到 `d:\yitu_projects\nanoai`。若脚本位置变化，需相应调整层级数。

### 常见脚本一览

| 脚本 | 用途 | 环节 |
|---|---|---|
| `scripts/leaf_cases/check_json_format.py` | 校验 cases JSON 格式 + C1 检查 | 2/4/5/6 |
| `scripts/leaf_cases/fix_ascii_quotes.py` | 修复字符串值内 ASCII 双引号 | 2/4/6 |
| `scripts/audit/full_case_audit.py` | LLM 全量审计 case | 5 |
| `scripts/audit/fix_case_by_audit.py` | LLM 根据审计报告修复 case | 6 |
| `scripts/audit/batch_audit_fix.py` | 批量审计+修复 | 5/6 |
| `scripts/tag_tree/preview_vehicle_tag_tree.py` | 预览标签树/叶子清单 | 1 |
| `scripts/coverage/report_composite_leaf_tag_coverage.py` | 叶子标签覆盖率报告 | 7 |
| `scripts/coverage/export_product_subtree_cases.py` | 按产品子树导出 case | 7 |
| `scripts/coverage/export_product_L1_cases.py` | 按 L1 导出 case | 7 |
| `scripts/normalize/normalize_composite_expected_scripts.py` | 归一化 expected_script 格式 | 6 |
| `scripts/normalize/strip_user_meta_parentheticals.py` | 清理用户行括号说明 | 6 |

