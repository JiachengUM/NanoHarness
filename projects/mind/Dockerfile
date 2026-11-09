# 基于轻量的Python 3.12-slim镜像
FROM python:3.12-slim

# 项目名称
ARG APP_NAME=nanoai-mind
ENV APP_NAME=${APP_NAME}

# 核心环境变量配置（优化Python运行、设置时区、编码）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    TZ=Asia/Shanghai \
    DEBIAN_FRONTEND=noninteractive

# 设置暴露端口
EXPOSE 8000

# 创建并切换到项目工作目录
WORKDIR /var/nanoai

# 先拷贝依赖文件（利用Docker缓存，避免代码变动重复安装依赖）
COPY requirements.txt .

# 安装Python依赖，使用清华源加速，不缓存安装包减少镜像体积
RUN pip install --no-cache-dir \
    --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt

# 拷贝mind代码到工作目录
COPY . .

# 启动命令（直接用uvicorn启动）
CMD ["uvicorn", "projects.mind.test_backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--log-level", "info"]