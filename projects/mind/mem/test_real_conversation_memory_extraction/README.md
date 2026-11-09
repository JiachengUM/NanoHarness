# 真实对话记忆提取测试

## 文件说明

| 文件 | 功能 |
|------|------|
| `aggregate_conversations.py` | 聚合原始对话数据 |
| `simulate_memory.py` | 模拟写入记忆库 |

## 使用步骤

### 1. 聚合原始对话数据

```bash
python aggregate_conversations.py
```

**输入**：`sample-data-v2.csv`（原始对话数据）

**输出**：`sample-data-v3.csv`，新增两列：
- `conversation_1min`：60s 内连续对话聚合
- `conversation_1day`：同一天对话聚合

### 2. 模拟写入记忆库

```bash
python simulate_memory.py
```

**测试维度**：
- `test_1min()`：1 分钟粒度，user_id = `Benz_test_1min`
- `test_1day()`：1 天粒度，user_id = `Benz_test_1day`

**配置**：取消注释对应函数即可运行

```python
if __name__ == "__main__":
    # 分钟维度
    asyncio.run(test_1min())
    
    # 按天为维度 
    asyncio.run(test_1day())
```

## 数据格式

**输入 CSV 必需列**：
- `timestamp`：时间戳，格式 `YYYYMMDD HH:MM:SS`
- `user_command`：用户输入
- `system_response`：系统回复

**输出格式示例**：
```json
[{"user": "打开空调", "assistant": "OK"}, {"user": "调高温度", "assistant": "已调到26度"}]
```
