# SGM Intent Recognition API

基于 FastAPI 的意图识别服务。

## 功能特性

- **并行处理**：同时执行 Prompt 分类和火山接口调用
- **复杂意图识别**：支持模糊车控、复杂联网等场景
- **定制业务**：支持旅游规划、AI 内容、生活服务等场景
- **健康检查**：内置健康检查机制

## 快速开始

### 方式一：Docker 运行

```bash
# 构建镜像（在 Nano 项目根目录执行）
docker build -f Dockerfile -t sgm-intent-api:latest .

# 运行容器
docker run -d \
  --name sgm-intent-api \
  -p 8000:8000 \
  -e DOUBAO_API_KEY="REDACTED" \
  -e DOUBAO_BASE_URL="your_base_url" \
  sgm-intent-api:latest

# 查看日志
docker logs -f sgm-intent-api

# 停止容器
docker stop sgm-intent-api

# 删除容器
docker rm sgm-intent-api
```

### 方式二：Docker Compose 运行

```bash
# 在 Nano 项目根目录启动服务
cd ../../  # 回到 Nano 项目根目录
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 方式三：本地开发运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行服务
cd ../../  # 回到 Nano 项目根目录
uvicorn projects.SGM.main:app --host 0.0.0.0 --port 8000 --reload
```

## API 文档

服务启动后，访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API 接口

### POST /intent

意图识别接口

**请求体**：
```json
{
  "query": "我想去北京旅游",
  "chat_id": "uuid-string",
  "history": [
    {
      "q": "你好",
      "a": "你好，有什么可以帮助你的吗？"
    }
  ],
  "car_info": {
    "vehicle_name": "某某车型"
  }
}
```

**响应**：
```json
{
  "data": {
    "message": "正在为您处理请求，请稍候...",
    "domain": "custom",
    "intent_type": "旅游规划",
    "input": "我想去北京旅游",
    "slot_data": "",
    "origin_intent_type": "旅游规划",
    "next_process": "plugin",
    "question_id": "uuid-string",
    "reject": false,
    "debug_info": {},
    "isComplexIntent": false
  },
  "errno": 0,
  "msg": "success"
}
```

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| PORT | 服务端口 | 8000 |
| DOUBAO_API_KEY | 豆包 API Key | - |
| DOUBAO_BASE_URL | 豆包 API Base URL | - |

## 项目结构

```
SGM/
├── main.py              # FastAPI 应用入口
├── core.py              # 意图分类核心逻辑
├── requirements.txt     # Python 依赖
├── ../../Dockerfile          # Docker 镜像配置（位于项目根目录）
├── ../../docker-compose.yml  # Docker Compose 配置（位于项目根目录）
├── .dockerignore       # Docker 忽略文件
├── common/             # 公共模块
│   ├── client.py       # 客户端配置
│   └── engine_api.py   # 火山引擎 API
├── domain/             # 领域定义
│   ├── simple.py       # 简单意图（闲聊）
│   ├── complex.py      # 复杂意图（车控、联网）
│   └── custom.py       # 定制意图（旅游、AI、生活）
└── test/               # 测试文件
    ├── test_core.py
    ├── test_engine.py
    └── test_new_intent_api.py
```

## 意图类别

### 复杂意图
- **模糊车控**：需要多轮交互的车辆控制
- **复杂联网**：复杂的网络相关请求

### 定制意图
- **旅游规划**：旅游相关咨询和规划
- **AI 内容**：AI 生成内容相关
- **生活服务**：日常生活服务

### 简单意图
- **闲聊**：日常对话和问候

## 开发说明

### 添加新的意图类别

1. 在 `domain/` 目录下定义新的意图类别
2. 在 `core.py` 的 `IntentClassifier.__init__` 中注册
3. 更新相应的分类逻辑

### 运行测试

```bash
cd ../../  # 回到 Nano 项目根目录
python -m pytest projects/SGM/test/ -v
```

## 监控和维护

### 查看容器状态
```bash
docker ps --filter name=sgm-intent-api
```

### 查看实时日志
```bash
docker logs -f sgm-intent-api
```

### 健康检查
```bash
curl http://localhost:8000/docs
```

### 重启服务
```bash
docker restart sgm-intent-api
```

## 故障排查

### 容器无法启动
1. 检查端口 8000 是否被占用
2. 检查环境变量是否正确配置
3. 查看日志：`docker logs sgm-intent-api`

### API 返回错误
1. 检查 API Key 是否有效
2. 检查网络连接
3. 查看容器日志排查具体错误

## License

内部项目

