# StreamTask 同步版对照日志

`../test_log/sync/` 保存原始同步版 Duplex（`StreamTaskToolRunner`、
`tool_call_mode="sync"`）的手工语音对照日志。测试输入和说话顺序以同级
[`VOICE_TEST_CASES.md`](VOICE_TEST_CASES.md) 中记录的 DynamicTask 实际口语流程为准。

测评结果见 [`SYNC_VOICE_TEST_REPORT.md`](SYNC_VOICE_TEST_REPORT.md)，两种执行策略的横向
结论见 [`DYNAMIC_VS_SYNC_TEST_REPORT.md`](DYNAMIC_VS_SYNC_TEST_REPORT.md)。

启动示例：

```bash
.venv/bin/python -m aicore.models.stream_model_api.duplex \
  --tool-call-mode sync \
  --case-log aicore/models/stream_model_api/duplex/experiment/test_log/sync/case01.log
```

约定：

- 每条 case 启动一个全新 session。
- 使用 `case01.log` 至 `case12.log`；Case 10、11 的第二次录制使用
  `case10_02.log`、`case11_02.log`。
- 不修改原始口语来迁就同步版。即使同步版没有 `cancel_task`，也继续原样说取消和修改指令。
- 工具执行期间插话的 Case 07–11，按矩阵中的相对时机说，不等待工具最终回复。
- 该目录的固定 case 日志作为测评原始证据纳入版本管理。
