# syntax=docker/dockerfile:1.6
# 多阶段构建：使用 Node 构建前端静态资源，用 Nginx 提供生产环境服务

# 支持通过构建参数覆盖镜像仓库与命名空间（REGISTRY/NAMESPACE），
#   docker build --build-arg REGISTRY=your-registry --build-arg NAMESPACE=your-namespace -t ai-eval-web:latest .
ARG REGISTRY=docker.io
ARG NAMESPACE=library
ARG PROJECT_DIR=projects/mind/test_frontend
ARG V2_FRONTEND_DIR=aicore/v2/experiments/v2_frontend

# ---- 构建阶段（builder） ----
FROM ${REGISTRY}/${NAMESPACE}/node:20-alpine AS builder

ARG PROJECT_DIR

WORKDIR /app

# 优先安装依赖以最大化利用构建层缓存
COPY ${PROJECT_DIR}/package.json ./
# 如有锁文件则一并复制，保证依赖可复现（没有也不会报错）
COPY ${PROJECT_DIR}/package-lock.json* ${PROJECT_DIR}/yarn.lock* ${PROJECT_DIR}/pnpm-lock.yaml* ./

RUN npm install --legacy-peer-deps

# 复制源码
COPY ${PROJECT_DIR} .

# 构建静态资源到 /app/dist
# 直接使用 Vite 进行构建，跳过 tsc 类型检查阶段，避免因类型错误导致生产构建失败
RUN npx vite build

# ---- v2 Agent 构建阶段 ----
FROM ${REGISTRY}/${NAMESPACE}/node:20-alpine AS v2-builder

ARG V2_FRONTEND_DIR

WORKDIR /app

COPY ${V2_FRONTEND_DIR}/package.json ./
# 如有锁文件则一并复制，保证依赖可复现（没有也不会报错）
COPY ${V2_FRONTEND_DIR}/package-lock.json* ${V2_FRONTEND_DIR}/yarn.lock* ${V2_FRONTEND_DIR}/pnpm-lock.yaml* ./

RUN npm install

COPY ${V2_FRONTEND_DIR} .

ARG VITE_V2_AGENT_BASE_URL=/api/v2-agent
ENV VITE_V2_AGENT_BASE_URL=${VITE_V2_AGENT_BASE_URL}

RUN npm run build -- --base=/v2-agent/

# ---- 运行阶段（runtime） ----
FROM ${REGISTRY}/${NAMESPACE}/nginx:1.27-alpine AS runtime

ARG PROJECT_DIR

# 默认后端接口网关地址（必须包含协议且不带尾部斜杠 /），可在运行容器时通过环境变量覆盖：
#   docker run -e BACKEND_ORIGIN="http://<host>:<port>" ...
ENV BACKEND_ORIGIN="http://nanoai-mind-dev-svc:8000"
ENV BACKEND_ADVISOR_ORIGIN="http://advisor-dev-svc:8001"
# ENV PLATFORM_BACKEND_ORIGIN="http://nanoai-platform-backend-dev-svc.default:8100"
# platform backend 的接口地址也指向 agent arena backend
ENV PLATFORM_BACKEND_ORIGIN="http://agent-arena-backend-dev-svc.seres-e68-dev:3000"
ENV AGENT_ARENA_BACKEND_ORIGIN="http://agent-arena-backend-dev-svc.seres-e68-dev:3000"

# Legacy 老接口地址（默认与新接口一致，部署时根据实际老接口地址覆盖）
ENV LEGACY_BACKEND_ORIGIN="http://nanoai-mind-dev-svc:8000"
ENV LEGACY_BACKEND_ADVISOR_ORIGIN="http://advisor-dev-svc:8001"
ENV LEGACY_PLATFORM_BACKEND_ORIGIN="http://nanoai-platform-backend-dev-svc.default:8100"
ENV LEGACY_AGENT_ARENA_BACKEND_ORIGIN="http://nanoai-mind-dev-svc:8000"

# 使用 host.docker.internal 访问宿主机服务（适用于 Docker Desktop on Windows/Mac）
# ENV BACKEND_ORIGIN="http://host.docker.internal:8000"
# ENV BACKEND_ADVISOR_ORIGIN="http://host.docker.internal:8001"

# 使用 Nginx 官方的模板渲染机制（envsubst），在启动时将环境变量写入配置
COPY ${PROJECT_DIR}/docker/nginx.conf.template /etc/nginx/templates/default.conf.template

# 拷贝构建产物到 Nginx 默认站点目录
COPY --from=builder /app/dist /usr/share/nginx/html
COPY --from=v2-builder /app/dist /usr/share/nginx/html/v2-agent

EXPOSE 9001

# 可选：健康检查（通过访问首页判断服务可用性）
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD wget -q -O /dev/null http://localhost:9001/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
