#!/bin/bash

# 创建日志目录
path="/var/logs/$APP_NAME/"
if [ ! -d "$path" ]; then
  mkdir -p "$path"
  echo "目录已创建: $path"
else
  echo "目录已存在: $path"
fi

# 设置 Python 路径
export PYTHONPATH=/var/$APP_NAME

# 启动 uvicorn 服务
exec python3 -m uvicorn projects.sgm_prod.api:app --host 0.0.0.0 --port ${PORT:-8007}
