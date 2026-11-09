# Auto Tagger 使用说明

`auto_tagger` 负责把 `TestCase` 按给定标签树自动打标，核心目标是：  
**让标签来源可配置（标签树驱动）且结果可校验（只能是叶子标签）。**

---

## 1. 目录与职责

- `tagger.py`
  - 异步打标入口：`auto_tag_case_with_llm(...)`
  - prompt 组织、模型输出解析、标签校验与回写
- `tag_tree_schema.py`
  - `TagTreeNode` / `TagTree` 结构定义
  - 标签树增删改、唯一性校验、导入导出、可视化打印
- `tag_tree_template.json`
  - 标签树模板（含 `tagging_guideline`）

---

## 2. 快速开始

```python
from projects.mind.mem.auto_test_script.auto_tagger import auto_tag_case_with_llm
from projects.mind.mem.auto_test_script.auto_tagger.tag_tree_schema import TagTree

# 1) 加载标签树（含打标思路）
tag_tree = TagTree.from_json_file(
    "projects/mind/mem/auto_test_script/auto_tagger/tag_tree_template.json"
)

# 2) 对单个case异步打标（默认最多重试3次）
tags = await auto_tag_case_with_llm(test_case=case, tag_tree=tag_tree)

print(tags)       # e.g. ["导航", "跨多轮对话"]
print(case.tags)  # 已同步写回
```

---

## 3. 关键约束

- 只能用**叶子节点**打标，非叶子会被拒绝
- 同一棵树中节点名必须**全局唯一**
- 模型输出必须是 JSON（推荐 `{"tags": [...]}`）
- `tagging_guideline` 由标签树提供，`tagger.py` 不硬编码业务规则
- 当标签校验失败（树外标签/非叶子标签/格式错误）时，会把错误信息回传给模型重试
- `max_retries` 默认 `3`，即最多调用模型 `4` 次（首次1次 + 重试3次）

---

## 4. 标签树配置建议

- 把“能力维度”“对话结构”“记忆机制”等拆成不同分支
- 叶子标签粒度尽量稳定复用，避免临时词
- 在 `tagging_guideline` 中明确：
  - 主证据来源（`expected_script` / `nl_assertion` / `case_description`）
  - 选标签优先级
  - 冲突标签取舍策略

---

## 5. 常见问题

- **模型返回了树外标签？**  
  系统会自动把校验错误反馈给模型并重试；若超过 `max_retries` 仍失败，会抛出最终错误。

- **标签太多、偏发散？**  
  在 `tagging_guideline` 增加“数量上限 + 主标签优先 + 低证据不打”。

- **需要批量打标？**  
  目前入口是单 case；可在上层并发调用 `auto_tag_case_with_llm(...)`。

- **如何调整重试次数？**  
  通过 `auto_tag_case_with_llm(..., max_retries=N)` 调整；`N=0` 表示不重试。
