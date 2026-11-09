# SGM 意图识别 API 开发文档

## 基本信息

- **接口地址**: `POST http://192.168.46.214/sgm-nanoai-dev/intent`
- **Content-Type**: `application/json`
- **服务说明**: 智能座舱意图识别接口，支持车控、VQA、一方服务、捷停车、闲聊等多种意图分类

---

## 请求参数

### 必填参数

| 参数名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `query` | string | 用户输入的查询内容 | `"打开空调"` |
| `chat_id` | string | 聊天会话ID，用于维护上下文 | `"b11a891b-9d71-4cb5-94a0-f44dd63564cb"` |

### 可选参数

| 参数名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `history` | array | 历史对话记录 | 见下方说明 |
| `car_info` | object | 车辆信息 | 见下方说明 |
| `vehicle_id` | string | 设备唯一ID | `"7b811248-1b44-4f98-9a3f-555685ade4ff"` |
| `vehicle_name` | string | 车辆市售名称 | `"Tesla Model Y"` |
| `longitude` | float | 经度（GCJ02火星坐标系） | `121.5073` |
| `latitude` | float | 纬度（GCJ02火星坐标系） | `31.1953` |

### history 格式

```json
[
  {
    "q": "用户问题",
    "a": "助手回答（可为null）"
  }
]
```

### car_info 字段（部分常用字段）

```json
{
  "vehicle_name": "Tesla Model Y",
  "sound_zone": "主驾",
  "song": "正在播放的歌名",
  "singer": "歌手名",
  "battery": 80,
  "current_location": "上海市浦东新区"
}
```

---

## 响应格式

### 成功响应

```json
{
  "errno": 0,
  "msg": "success",
  "data": {
    "message": "正在为您处理请求，请稍候...",
    "domain": "vehicle_control",
    "intent_type": "vehicle_control",
    "byte_intent_type": "vehicle_control",
    "input": "打开空调",
    "slot_data": "{\"action\":\"打开\",\"target\":\"空调\"}",
    "origin_intent_type": "vehicle_control",
    "next_process": "",
    "question_id": "xxx-xxx-xxx",
    "reject": false,
    "debug_info": {},
    "isComplexIntent": false
  }
}
```

### 拒识响应

```json
{
  "errno": 0,
  "msg": "success",
  "data": {
    "reject": true,
    "isComplexIntent": false,
    "byte_intent_type": null,
    "debug_info": {}
  }
}
```

### 响应字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `reject` | boolean | 是否拒识，true表示无法识别意图 |
| `domain` | string | 意图领域（如：vehicle_control、vqa等） |
| `intent_type` | string | 意图类型 |
| `byte_intent_type` | string | 火山API原始意图类型 |
| `isComplexIntent` | boolean | 是否为复杂意图（复杂模糊车控、多意图） |
| `message` | string | 返回给用户的消息 |
| `input` | string | 处理后的输入内容 |
| `slot_data` | string | 槽位数据（JSON字符串） |
| `question_id` | string | 问题ID |

---

## 请求示例

### 示例1：基础查询

```bash
curl -X POST "http://192.168.46.214/sgm-nanoai-dev/intent" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "打开空调",
    "chat_id": "test-001"
  }'
```

### 示例2：带历史对话

```bash
curl -X POST "http://192.168.46.214/sgm-nanoai-dev/intent" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "帮我打开前排的",
    "chat_id": "test-002",
    "history": [
      {
        "q": "帮我打开座椅加热",
        "a": "好的，已为您打开座椅加热"
      }
    ]
  }'
```

### 示例3：完整参数

```bash
curl -X POST "http://192.168.46.214/sgm-nanoai-dev/intent" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "明天上海天气怎么样？",
    "chat_id": "test-003",
    "vehicle_id": "7b811248-1b44-4f98-9a3f-555685ade4ff",
    "longitude": 121.5073,
    "latitude": 31.1953,
    "car_info": {
      "vehicle_name": "Tesla Model Y"
    }
  }'
```

