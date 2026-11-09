---
name: dataset-coverage-and-export
description: >-
  统计叶子覆盖率、导出产品子树用例集、生成最终交付物。
  适用场景：覆盖率缺口分析、按产品子树导出用例、L1分桶导出、
  最终交付物生成。
---

# Dataset Coverage And Export

最终覆盖率报告与导出环节。

**注意**：中间的覆盖率检查已在两个生产循环中完成（环节2循环查叶子覆盖率，环节4循环查场景覆盖率）。本环节只做**最终汇总**——两个循环都达标后，生成最终覆盖率报告和导出文件。

## 输入

| 产物 | 目录 | 说明 |
|------|------|------|
| 用例主库 | `<P>/cases/vehicle_assistant_cases.json` | 审计通过的主库 |
| 项目标签树 | `<P>/tag_tree/vehicle_assistant_case_tag_tree.json` | 标签树 |

## 输出

| 产物 | 目录 |
|------|------|
| 覆盖率报告 | 终端输出 |
| `product_subtree_<子树名>_cases.json` | `<P>/exports/` |
| `product_perspective_L1_export/` | `<P>/exports/product_perspective_L1_export/` |

## 覆盖率分析

### 运行覆盖率报告

```bash
python scripts/coverage/report_composite_leaf_tag_coverage.py --min 8
```

输出：
- 每个叶子标签被 composite-* case 覆盖的次数
- 低于阈值的叶子清单
- 从未出现的叶子清单
- 粗算缺口

### 覆盖率标准

- 每个 `composite-*` case 的 `tags` 里每条叶子计 1 次
- 目标：每个叶子至少在 `tags` 里出现 8 次以上
- 当前目标规模：约 1200 条 `composite-*`

### 缺口补全策略

1. 优先补充「从未出现」的叶子
2. 其次补充「低于 8 次」的叶子
3. 补 case 时仍守叶子-only、口语车主句、expected_script 剧本体等规范
4. 勿为冲覆盖给题打未在剧情里出现的叶子

## 子树导出

### 按产品一级子树导出

```bash
python scripts/coverage/export_product_subtree_cases.py
```

产出文件数量 = 标签树中产品视角下一级子树的数量 + 合规子树（如有）。

每份文件命名：`product_subtree_<子树名>_cases.json`

### 仅导出内容合规

```bash
python scripts/coverage/export_product_subtree_cases.py --only 内容合规
```

### 导出规则

- `tags` 与子树下任一叶子有**交集**即收录
- **不判断主轴**——因此错标1个联网叶 = 整案进联网子树
- 内容合规桶仅含对应叶子交集，勿与行为安全叶混桶

### L1 分桶导出

```bash
python scripts/coverage/export_product_L1_cases.py
```

产出 `product_perspective_L1_export/` 目录及 README。

## 迭代模式

覆盖率报告是最终的质量关卡，发现缺口后需要回溯补全。

### 自回溯

- 覆盖率报告可随时重新生成，是只读分析，不修改用例数据
- 每次运行基于当前用例集重新计算覆盖率
- 人类可根据报告定向补全缺口，补完后重新运行确认

### 跨环节回溯

| 触发场景 | 回溯方式 |
|---------|---------|
| 发现「从未出现」的叶子 | 回到环节3补充涉及该叶子的场景模板，再到环节4合成用例 |
| 发现覆盖不足（低于阈值）的叶子 | 回到环节4为该叶子补充更多用例 |
| 发现联网子树条数虚高（误标） | 回到环节4修正标签，再经环节5审计→6修复后重新统计 |
| 导出结果不符合预期 | 确认标签树和用例标签是否一致，必要时回到环节1/2 |

### 迭代闭环

覆盖率报告是流水线的终点，也是下一轮迭代的起点：
1. 运行覆盖率报告 → 发现缺口
2. 回溯到对应环节补全
3. 补全后重新运行环节5→6→7
4. 直到覆盖率达标

## 何时复跑

- 大批量改 `tags` 后
- 联网改标后
- 内容合规扩库后
- 去重或改标签树 / guideline 后

## 完成前检查清单

- [ ] 每个叶子至少被 8 条 composite case 覆盖
- [ ] 覆盖率报告无「从未出现」的叶子
- [ ] 子树导出文件数量正确
- [ ] 联网子树条数与真联网题数一致（非误标虚高）
- [ ] L1 导出目录完整

## 脚本

| 脚本 | 用途 |
|------|------|
| `scripts/coverage/report_composite_leaf_tag_coverage.py` | 叶子覆盖缺口报告 |
| `scripts/coverage/export_product_subtree_cases.py` | 按产品子树导出 |
| `scripts/coverage/export_product_L1_cases.py` | 按一级子树分桶导出 |
