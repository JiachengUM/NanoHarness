#!/bin/bash

# 设置Python路径
PYTHON_EXEC=python

# 设置服务端口
PORT=8000

# 设置日志级别
LOG_LEVEL=info

# 启动服务
echo "正在启动Qwen FastAPI服务..."
echo "服务地址: http://localhost:$PORT"
echo "日志级别: $LOG_LEVEL"
echo "按 Ctrl+C 停止服务"
echo ""

$PYTHON_EXEC -m uvicorn nanoai.api.qwen_api:app --host 0.0.0.0 --port $PORT --log-level $LOG_LEVEL
