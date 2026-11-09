# Duplex Context Canary 实验

这个入口只验证一件事：通过 `conversation.item.create` 或
`conversation.item.update` 写入的不可猜测文本，是否真正进入随后 PCM 激活的模型推理。

它不加载业务工具，不使用 TaskManager、占位回执、异步 observation marker 或搜索结果。
五种模式只改变上下文写入方式和长度：

| 模式 | 写入 | 内容 |
|---|---|---|
| `control` | 不写入 | 负对照，模型应说“没有看到验证数据” |
| `create-short` | `conversation.item.create` | 两行短 canary |
| `create-long` | `conversation.item.create` | 约 6000 字符，canary 位于中间 |
| `update-short` | 更新首轮真实 `question_id` | 保留原问题，并追加两行短 canary |
| `update-long` | 更新首轮真实 `question_id` | 保留原问题，并追加长 canary |

## 已验证结论

2026-08-12 的五组实测结果如下：

| 模式 | update/create 回执 | retrieve | 最终回复 |
|---|---|---|---|
| `control` | 无写入 | 无 canary | 没有看到验证数据 |
| `create-short` | 无可验证写入回执 | 无 canary | 没有看到验证数据 |
| `create-long` | 无可验证写入回执 | 无 canary | 没有看到验证数据 |
| `update-short` | `conversation.item.updated` | 包含 canary | 精确复述 marker/value |
| `update-long` | `conversation.item.updated` | 包含 canary | 精确复述 marker/value |

结论：在当前 Duplex 服务端实现中，`conversation.item.create(role=user,
input_text)` 虽然上行成功，但其正文不会进入后续音频轮次可见的推理上下文；只有以
正确 `id` 更新已有 question item 的 `conversation.item.update` 可以稳定生效。此前
DynamicTask 使用 create 回灌的事实遵循实验因此不能用于评价模型“看见结果后是否遵守”；
它最多证明了工具生命周期和 PCM 激活时序。DynamicTask 兼容链路必须改用 update。

## 复现顺序

建议每个模式使用新 session，各运行两次。为便于人工核对，第一轮可固定 marker/value；五种模式
必须使用同一组值：

```bash
.venv/bin/python -m aicore.models.stream_model_api.duplex.experiment.canary_experiment \
  --mode control --marker ZEBRA-7319 --value 17.3 \
  --case-log aicore/models/stream_model_api/duplex/experiment/test_log/canary/rerun-control.log

.venv/bin/python -m aicore.models.stream_model_api.duplex.experiment.canary_experiment \
  --mode create-short --marker ZEBRA-7319 --value 17.3 \
  --case-log aicore/models/stream_model_api/duplex/experiment/test_log/canary/rerun-create-short.log

.venv/bin/python -m aicore.models.stream_model_api.duplex.experiment.canary_experiment \
  --mode update-short --marker ZEBRA-7319 --value 17.3 \
  --case-log aicore/models/stream_model_api/duplex/experiment/test_log/canary/rerun-update-short.log

.venv/bin/python -m aicore.models.stream_model_api.duplex.experiment.canary_experiment \
  --mode create-long --marker ZEBRA-7319 --value 17.3 \
  --case-log aicore/models/stream_model_api/duplex/experiment/test_log/canary/rerun-create-long.log

.venv/bin/python -m aicore.models.stream_model_api.duplex.experiment.canary_experiment \
  --mode update-long --marker ZEBRA-7319 --value 17.3 \
  --case-log aicore/models/stream_model_api/duplex/experiment/test_log/canary/rerun-update-long.log
```

启动后只需要：

1. 按回车打开一轮麦克风。
2. 说：`准备开始上下文实验。`
3. Duplex 应先回复“准备好了”。
4. 程序会自动等待该语音播完，执行 create/update，打印 retrieve，然后上传同一段本地激活 PCM。
5. 听最终回复并等待日志打印完成，再按 `Ctrl-C` 结束。

日志目录需要预先存在：

```bash
mkdir -p aicore/models/stream_model_api/duplex/experiment/test_log/canary
```

## 判定规则

严格通过只能是：

> 标记是 ZEBRA-7319，数值是 17.3。

其他近似值、只答一个字段、编造新值或泛化说明都算失败。

| 结果 | 推断 |
|---|---|
| `control` 也答对 | 实验污染；marker/value 出现在 prompt、PCM 或其他上下文中 |
| create/update 短版都失败 | 文本正文未进入推理，或 PCM 轮无法绑定这些上下文项 |
| create 失败、update 成功 | `conversation.item.update` 才能进入 Duplex 当前推理上下文 |
| create 成功、update 失败 | update 的目标/事件结构有误，或更新项不参与新推理 |
| 短版成功、同方式长版失败 | 长度、截断或注意力稀释是主要因素 |
| 两种短版成功但业务回灌失败 | 正文可见；进一步排查结果噪声、冲突、多 observation 和 prompt 遵循 |

默认写入后等待 1 秒再激活。如果短版偶发失败，可以额外用
`--activation-delay 0` 和 `--activation-delay 3` 各测一次，判断是否存在服务端上下文处理竞态。

注意：`update` 会原位替换首轮用户 question。本实验显式保留原始转写再追加 canary。
生产链路若同一 question 有多个异步任务依次完成，后一次 update 必须携带此前已完成结果，
否则整段替换会覆盖早先结果。
