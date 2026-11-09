# svw_afc 原始输入文件

此目录存放环节0的原始输入文件，可能包括：

- 需求文档（PRD、产品需求说明书）
- 已有测试用例（Excel、JSON、其他格式）
- 标签线索文档
- 竞品分析报告
- 其他参考资料

## 文件命名建议

- `prd_<版本>.md` - 产品需求文档
- `legacy_cases_<来源>.json/xlsx` - 已有用例
- `tag_hints_<来源>.md` - 标签线索

---

环节0脚本将处理这些原始文件，提取出：
- `extracted_tag_hints.json` - 标签线索
- `extracted_cases_raw.json` - 已有用例（标准化格式）
- `extracted_requirements.md` - 需求描述
- `extraction_report.md` - 提取报告

并输出到 `../extracted/` 目录。
