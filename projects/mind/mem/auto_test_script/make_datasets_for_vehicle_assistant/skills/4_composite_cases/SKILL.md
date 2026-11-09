---
name: composite-cases
description: >-
  基于环节3的场景模板，合成车载助手复合评测用例（composite-*），
  遵循多会话/记忆闭环/口语化用户句/expected_script剧本体等规范。
  适用场景：按场景模板编写复合case、emit批次产出、合并入库。
---

# Composite Cases

合成复合用例环节。基于环节3产出的场景模板，将每个场景具象化为可执行的评测用例。

> **用例编写通用原则**：本环节与环节2、6共享用例编写/审查原则，详见 [_shared_case_writing_principles.md](../_shared_case_writing_principles.md)。以下仅列出本环节独有的内容。**项目写作增补优先于基础原则**，两者冲突时以项目增补为准。

## 输入

| 产物 | 目录 | 说明 |
|------|------|------|
| 项目标签树 | `<P>/tag_tree/vehicle_assistant_case_tag_tree.json` | 叶子标签全集 |
| 项目打标指南 | `<P>/tag_tree/vehicle_assistant_case_tagging_guideline.md` | 叶子语义定义和例子（含项目写作原则覆盖，优先于基础原则） |
| 叶子示范用例 | `<P>/cases/vehicle_assistant_cases.json` | `leaf-*` 用例，作为风格参考 |
| 场景模板 | `<P>/composite_sampling/scenario_templates.json` | 来自环节3，场景+标签组合+复杂度 |
| 覆盖缺口报告 | `<P>/composite_sampling/coverage_gap_report.json` | 来自环节3，优先处理未覆盖场景 |
| 环节0提取的已有case | `<P>/inputs/extracted/extracted_cases_raw.json` | 项目方已有的评测用例（风格参考和场景灵感，不直接复用） |

## 输出

| 产物 | 目录 | 说明 |
|------|------|------|
| 复合用例 | `<P>/cases/vehicle_assistant_cases.json` | 追加 `composite-*` 部分（本批次新增） |
| 批次文件 | `<P>/batches/handwritten_batches/` | emit 产出的中间批次 |

## 批量生产循环

本环节不是一次性为所有场景生成用例，而是**分批生产**：

```
1. 查场景覆盖率 → 找出未覆盖的场景模板
2. 挑一批未覆盖场景（约20个）→ 写一批 composite case
3. 送环节5审计 → 环节6修复
4. 合并入总集
5. 查场景覆盖率 → 未达标? 回到步骤1
```

### 场景覆盖率计算

- 场景覆盖率 = 已有 `composite-*` 用例覆盖的场景模板数 / 场景模板总数
- 每个场景模板至少1条 `composite-*` 用例即为"已覆盖"
- 目标：**所有场景模板都被覆盖**
- 优先处理覆盖缺口报告中的未覆盖场景

## 本环节独有的原则

**场景模板是工作单元**：环节3已为每个场景标注了自然涉及的标签组合，本环节的任务是将场景模板**具象化**为可执行的评测用例——写出真实车主台词、助手预期回复、断言判据。

## 从场景模板到用例

### 场景模板 → 用例的转化过程

```
场景模板（环节3产出）          用例（本环节产出）
┌─────────────────┐          ┌──────────────────────┐
│ scenario_name    │          │ case_id              │
│ description      │  ──→    │ case_description     │
│ tags[]           │          │ tags[]               │
│ frequency        │          │ user_query_lists     │
│ complexity_level │          │ expected_script      │
│                  │          │ nl_assertion         │
│                  │          │ context_config       │
└─────────────────┘          └──────────────────────┘
```

1. 读取场景模板的 `description`，理解场景要测什么
2. 读标签树该叶 `description` + guideline 对应例子，确认每个标签的语义
3. 构思真实车主在这个场景下会怎么说（口语化、短句、不剧透）
4. 为每个标签设计触发和验证方式
5. 检查 `tags` 里每个叶子是否都被题干与 `nl_assertion` 直接支撑
6. `case_id` / 用户句 / `case_description` 让人一眼看出场景主轴

### 优先级策略

基于覆盖缺口报告确定处理优先级：
1. **从未被覆盖的场景模板**（`covered_by_existing_case: false`）优先
2. **高频场景**（`frequency: "高频"`）优先
3. **覆盖缺口报告中的 `uncovered_scenarios`** 优先

### 触发 → 验证（两步至少想清楚）

| 维度 | 要求 |
|------|------|
| **触发** | 车主口语里**真的发生**该叶定义的事件，且是典型、可辨认的场景 |
| **验证** | 用最直接的方式看助手有没有做对/做错 |

## 迭代模式

复合用例是持续演进的产物，每次运行应基于当前状态增量补充。

### 自回溯

本环节的输出（复合用例）可作为下次运行的输入：
- 如果 `vehicle_assistant_cases.json` 已有 `composite-*` 用例，只合成未被覆盖的场景模板对应的用例
- 人类可直接编辑已有用例（修正对话、改写断言等），下次运行时保留这些修改
- 增量模式：只为未覆盖的场景模板合成新用例
- 全量模式：用户明确要求时，重新合成所有场景模板的用例

### 跨环节回溯

| 触发场景 | 回溯方式 |
|---------|---------|
| 环节3新增场景模板 | 回到环节4为新模板合成用例 |
| 环节6审计发现用例质量问题 | 回到环节4修复特定用例（对话不自然、断言不准确等） |
| 环节7发现覆盖缺口 | 回到环节3补充场景模板，再到环节4合成用例 |

### 人类编辑保留

- 人类手动编辑用例后，在该 case 中添加 `"manually_edited": true` 字段
- 批次合并时跳过带该标记的 case，不覆盖人类修改
- 如需重新生成某条已编辑的 case，需用户明确指定

## Emit → 合并 Checklist

1. 每条 case 过入库前勾表
2. 新批次 `composite-(上一编号+1)` 起连续编号
3. `python run_emit.py emit_XXX.py handwritten_batches/batch_XXX.json`
4. `python merge_handwritten_batches.py`（叶子校验 + append）
5. 大库合并后做一次去重
6. 联网叶按 §2.2 核对主轴
7. 同会话多轮：`user_query_lists` 每项仅一条冷启动 user

## 入库前勾表

- [ ] 主轴叶子：车主句 + 剧情是否直截了当对应该叶？
- [ ] 未用车主句「剧透」记住/别记/记一下？
- [ ] `user_query_lists` 每项是否只有 1 条 user？
- [ ] 需第2轮验证时，`expected_script` 是否写了对应 `用户：`？
- [ ] `tags` 是否全是叶子、且无多余叶蹭覆盖？
- [ ] `nl_assertion` 是否评助手且可核对？

## 脚本

| 脚本 | 用途 |
|------|------|
| `scripts/composite_cases/compose_handwritten_helpers.py` | 辅助函数（`sess`, `director_script`, `pattern_case` 等） |
| `scripts/composite_cases/run_emit.py` | 执行 emit 模块产出 batch JSON |
| `scripts/composite_cases/merge_handwritten_batches.py` | 合并批次到主库（含叶子校验） |
