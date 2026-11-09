---
name: dataset-audit-fix
description: >-
  根据审计报告修复用例，含格式清洗+LLM修复循环。
  适用场景：批量修复审计问题、格式归一化、审核修复循环、
  通过率阈值控制。
---

# Dataset Audit Fix

审计修复环节。根据环节5的审计报告修复问题用例，循环直到通过率达标。

> **用例编写通用原则**：本环节与环节2、4共享用例编写/审查原则，详见 [_shared_case_writing_principles.md](../_shared_case_writing_principles.md)。修复时以该共享原则为标准。**项目写作原则优先于基础原则**，两者冲突时以项目增补为准。
>
> **用例审核通用原则**：审计 Prompt 中的审核原则来自 [_shared_case_audit_principles.md](../_shared_case_audit_principles.md)，项目级审核原则覆盖见 `<P>/tag_tree/case_audit_supplements.md`（优先级更高，冲突时以项目级为准）。修复时须同时遵守写作原则和审核原则。

**公共服务**：本环节被两个生产循环共用——叶子用例生产循环（环节2→5→6）和复合用例生产循环（环节4→5→6）。每批用例审计后，调用本环节修复。

## 输入

| 产物 | 目录 | 说明 |
|------|------|------|
| 用例主库 | `<P>/cases/vehicle_assistant_cases.json` | 待修复的主库 |
| 审计报告 | `<P>/audit_results/` | 来自环节5的问题清单 |
| 项目标签树 | `<P>/tag_tree/vehicle_assistant_case_tag_tree.json` | 叶子标签全集 |
| 项目打标指南 | `<P>/tag_tree/vehicle_assistant_case_tagging_guideline.md` | 标签语义定义+项目写作原则覆盖（修复时须遵守，优先于基础原则） |

## 输出

| 产物 | 目录 | 说明 |
|------|------|------|
| 用例主库 | `<P>/cases/vehicle_assistant_cases.json` | 修复后（原地更新） |

## 修复流程

### 步骤1：格式清洗（确定性、幂等）

先修复格式问题，再修复语义问题。格式清洗是确定性的，不会引入新问题。

1. **归一化 expected_script 格式**：`scripts/normalize/normalize_composite_expected_scripts.py`
   - `【自动评测说明】` → `（评测说明：…）`
   - `管家：台词`（非括号）→ `管家：（…）`
   - 用户行只保留口述台词

2. **全面移除标注括号**：`scripts/normalize/strip_user_meta_parentheticals.py`
   - 60+ 种精确匹配 + 正则模式

3. **Schema 校验**：`scripts/leaf_cases/validate_cases_schema.py`

### 步骤2：LLM 语义修复（迭代循环）

格式清洗后，对审计报告中的语义问题进行 LLM 修复。

**核心循环**（`scripts/audit/batch_audit_fix.py`）：

```
修复 → 审计 → 修复 → 审计 → ... → 通过率达标
```

1. **LLM 自动修复**：`scripts/audit/fix_case_by_audit.py`
   - 根据审核反馈自动修复有问题的 case
   - 含完整修复规范 Prompt（A-E 五大类原则）

2. **批量审计+修复循环**：`scripts/audit/batch_audit_fix.py`
   - 含 429 限流自适应控制器（ThrottleController）
   - 支持 `--max-rounds` 控制最大修复轮数
   - 支持 `--concurrent` 控制并发数
   - 支持 `--ids` / `--tags` / `--id-range` 筛选特定 case

### 步骤3：通过率检查

循环终止条件：

| 条件 | 阈值 |
|------|------|
| 规则审计 | 0 issue |
| LLM 审计通过率 | ≥ 95%（可配置） |
| 内容合规专项 | 0 issue |
| 非叶子标签 | 0 |
| 互斥结果标签共存 | 0 |

**未达标的 case**：输出到 `<P>/audit_results/remaining_issues.json`，供人类手动处理。

## 迭代模式

### 自回溯

- 修复后自动触发审计验证（循环内置）
- 人类可手动修复问题用例，修复后重跑环节5审计验证
- 格式清洗对已清洗的用例是幂等的

### 跨环节回溯

| 触发场景 | 回溯方式 |
|---------|---------|
| 大量用例修复失败 | 回到环节4批量重写 |
| 修复引入新问题 | 回到步骤1重新清洗 |
| 标签错误无法通过修复解决 | 回到环节1/2修正标签树 |

### 人类编辑保留

- 人类手动修复的用例，在该 case 中添加 `"manually_edited": true` 字段
- 修复时保留带该标记的 case 的核心内容
- 如人类修复引入新问题，下一轮审计仍会报告

## 完成标准

- 格式清洗全部通过（Schema 校验 0 issue）
- 规则审计 0 issue
- LLM 审计通过率 ≥ 95%
- 内容合规专项 0 issue

## 脚本

| 脚本 | 用途 |
|------|------|
| `scripts/normalize/normalize_composite_expected_scripts.py` | 统一导演本格式 |
| `scripts/normalize/strip_user_meta_parentheticals.py` | 全面移除标注括号 |
| `scripts/leaf_cases/validate_cases_schema.py` | Schema 合法性校验 |
| `scripts/audit/fix_case_by_audit.py` | LLM 自动修复 |
| `scripts/audit/batch_audit_fix.py` | 批量审计+修复循环 |
