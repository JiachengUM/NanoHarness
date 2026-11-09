# svw_afc 用例库

此目录存放环节2/4（叶子示范用例 / 复合用例）的产物：

## 文件清单

| 文件 | 说明 |
|------|------|
| `vehicle_assistant_cases.json` | 项目用例库（含 `leaf-*` 叶子示范和 `composite-*` 复合用例） |

## 约定

- 每写完一批 case，**必须**跑格式校验：
  ```powershell
  D:\apps\miniconda\envs\dzy_env\python.exe scripts/leaf_cases/check_json_format.py artifacts/projects/svw_afc/cases/vehicle_assistant_cases.json
  ```
- 冷启动入口单条（C1）：`user_query_lists` 每个 session 只能有1条 user 消息
- 写作原则：`skills/_shared_case_writing_principles.md`（基础）→ `<P>/tag_tree/vehicle_assistant_case_tagging_guideline.md` §2.1（项目覆盖，优先）
