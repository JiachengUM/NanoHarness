# Canary 手工实验日志

`../test_log/canary/` 保存 `canary_experiment` 的 create/update 对照日志。
每次运行使用不同文件名，避免覆盖。

五份日志的结论：control/create-short/create-long 均无法复述 canary；update-short 和
update-long 均收到 `conversation.item.updated`，定向 retrieve 包含 canary，模型随后
精确复述。这里保存的是协议能力证据，不是业务工具质量评测。
