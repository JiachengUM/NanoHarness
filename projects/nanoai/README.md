# NanoAI

NanoAI 是 Session 服务的应用层。它通过 FastAPI 提供接口并管理多个具体
Session；`aicore.session` 仍然只承载领域层的 Session 契约。当前实现通过
`SyncSessionBase` 适配 `aicore.v1.experiments.agent.Agent`。

项目包含一个最小 HTTP demo：`GET /health`。

请从仓库根目录启动，使源码目录中的 `aicore` 包可用：

```bash
uv run uvicorn projects.nanoai.main:app --reload
```

启动后可访问 `http://127.0.0.1:8000/health`，或打开
`http://127.0.0.1:8000/docs` 查看接口文档。

## Session 接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/v1/sessions` | 创建 V1 Agent Session。 |
| `POST` | `/v1/sessions/restore` | 从此前导出的 dump 恢复同一 Session。 |
| `GET` | `/v1/sessions/{session_id}/dump` | 导出可跨进程恢复的 Session dump。 |
| `GET` | `/v1/sessions/{session_id}` | 查询 Session 与完整 turn 历史。 |
| `POST` | `/v1/sessions/{session_id}/turns` | 提交一个 turn 并接收 SSE 流。 |
| `POST` | `/v1/sessions/{session_id}/turns/{turn_id}/cancel` | 取消活跃 turn。 |
| `DELETE` | `/v1/sessions/{session_id}` | 关闭并移除 Session。 |

turn 流先发送 `session.submitted`，随后发送文本 `session.output` 事件，最后
以 `session.turn.finished` 结束。最后一个事件包含完整 turn、运行 trace 和终态。

## Dump 与恢复

当 Session 处于空闲状态时，可以导出 dump。dump 会递归保存 V1 Agent 的 context、
模型续接状态和 Session turn 历史；将 JSON 保存到外部存储后，即使服务重启，也可恢复
同一个 `session_id` 并继续对话。运行中或等待中的 turn 不能导出，接口会返回 `409`。

```bash
curl -sS http://127.0.0.1:8000/v1/sessions/SESSION_ID/dump > session-dump.json

curl -sS -X POST http://127.0.0.1:8000/v1/sessions/restore \
  -H 'content-type: application/json' \
  --data-binary @session-dump.json
```

当前 demo 不会自动保存 dump；生产服务应在外部持久化存储中保存它，并在启动后调用
restore。恢复后的运行时 `GET /v1/sessions/{session_id}` 不包含 adapter 私有 snapshot；
需要迁移或持久化时请使用 dump 接口。

先用模型配置创建 Session，再提交 turn：

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/sessions \
  -H 'content-type: application/json' \
  -d '{
    "config": {
      "model": "MODEL_ID",
      "system_prompt": "你是一个车载助手。",
      "max_turns": 1
    },
    "context": {
      "car_info": {
        "vehicle_status": {
          "speed_kph": 0,
          "gear": "P"
        },
        "energy": {
          "battery_percent": 18,
          "remaining_range_km": 42
        },
        "climate": {
          "cabin_temperature_c": 26.5,
          "air_conditioner": "关闭"
        }
      }
    }
  }'

curl -N -X POST http://127.0.0.1:8000/v1/sessions/SESSION_ID/turns \
  -H 'content-type: application/json' \
  -d '{"input":"我刚下班，车里有点热，开空调回家电量够不够？"}'
```

服务当前使用内存保存 Session，进程重启后所有 Session 都会丢失。

## 动态上下文限制

`context` 是创建 Session 时注入 V1 Agent 的静态上下文。当前 demo **不支持**
`state_update`：V1 Agent 的跨 turn 模型状态无法安全地接收该更新。为避免把数据
写入 SessionState 却不影响模型，携带 `state_update` 的 `POST /turns` 会返回
`422`，直接调用 `V1AgentSession.update_state()` 也会抛出
`SessionStateUpdateUnsupportedError`。需要变更车辆状态时，请创建新的 Session，
或在实现模型可见的动态状态注入后再开放该字段。

## 可执行 HTTP Smoke Test

下面的程序会临时启动服务，再通过 HTTP 创建真实 V1 Agent Session、消费 SSE
并调用模型。过程和每项检查结果均通过 Rich 输出；它不依赖 pytest 的 `assert`。

```bash
uv run python projects/nanoai/tests/http_smoke.py
```

默认模型可通过环境变量覆盖：

```bash
NANOAI_HTTP_SMOKE_MODEL=MODEL_ID uv run python projects/nanoai/tests/http_smoke.py
```
