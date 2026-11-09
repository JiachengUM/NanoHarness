
path="/var/logs/$APP_NAME/"
# 检查路径是否存在
if [ ! -d "$path" ]; then
  # 路径不存在，创建它
  mkdir -p "$path"
  echo "目录已创建: $path"
else
  # 路径已存在
  echo "目录已存在: $path"
fi
export PYTHONPATH=/var/$APP_NAME/projects/uiagent/server
exec python3 -m main