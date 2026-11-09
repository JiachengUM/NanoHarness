# 评测平台介绍

基于 pnpm workspace + Turborepo 的 monorepo 评测平台。

## 项目结构

```text
platform/
├── apps/
│   ├── frontend/        # 前端应用
│   └── backend/         # 后端服务
├── packages/
│   ├── database/        # 数据访问层
│   ├── evaluation/      # 评测逻辑
│   ├── llm/             # LLM 调用封装（@eval-platform/llm）
│   └── shared/          # 公共类型与工具函数（@eval-platform/shared）
├── turbo.json
├── pnpm-workspace.yaml
└── package.json
```

## 前置要求

- Node.js >= 22
- pnpm >= 10

```bash
# 安装 Node.js
https://nodejs.org/en/download

# 安装 pnpm
npm install -g pnpm
```

## 安装依赖

```bash
pnpm install
```

## 启动开发环境

```bash
pnpm dev
```

## 常用命令

| 命令                      | 说明                    |
| ------------------------- | ----------------------- |
| `pnpm typecheck`          | 所有 workspace 类型检查 |
| `pnpm typecheck:packages` | 所有子包类型检查        |
| `pnpm build`              | 构建所有 workspace      |
| `pnpm build:packages`     | 构建所有子包            |
| `pnpm dev`                | 启动所有可 watch 的子包 |
| `pnpm test`               | 运行测试                |
| `pnpm lint`               | 代码检查                |
| `pnpm format`             | 代码格式化              |

## 调试说明

```bash
# 全局安装tsx （可选）
pnpm add -g tsx

# 进入platform根目录
cd platform

# 安装依赖
pnpm install

# 启动调试服务
pnpm dev

# 运行测试文件（全局安装tsx时）
tsx packages/evaluation/tests/evaluator.test.ts
# 或使用 npx 运行 (未全局安装tsx时)
npx tsx packages/evaluation/tests/evaluator.test.ts
```

### launch.json 配置

- 配置 `launch.json` 以支持调试当前 TS 文件（ESM 模式）。
- 示例配置：

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Node: Debug Current TS File (ESM)",
      "type": "node",
      "request": "launch",
      "program": "${file}",
      "cwd": "${workspaceFolder}/platform",
      "runtimeExecutable": "npx",
      "runtimeArgs": ["tsx"],
      "skipFiles": ["<node_internals>/**"]
    }
  ]
}
```

## 测试说明

```bash
# 全局安装vitest (可选)
pnpm add -g vitest

# 进入platform根目录
cd platform

# 安装依赖
pnpm install

# 运行测试文件（全局安装vitest时）
vitest packages/llm/tests/responses.test.ts
# 或使用 npx 运行 (未全局安装vitest时)
npx vitest packages/llm/tests/responses.test.ts

# 运行所有测试（packages)
pnpm test:packages

# 运行模块下测试
# 1. 进入模块目录
cd packages/llm
# 2. 运行测试
pnpm test
```

## 构建说明 apps/backend

### docker-compose 构建
```bash
# 构建镜像并启动服务（后台运行）
docker-compose up -d --build

# 查看服务状态
docker-compose ps

# 查看后端日志
docker-compose logs backend

# 停止服务
docker-compose down

# 停止并删除容器、网络、卷
docker-compose down -v
```

### docker 构建
```bash
# 进入platform根目录
cd platform

# 构建镜像
docker build -t eval-platform-backend -f apps/backend/Dockerfile .

# 启动后端服务（不连接本地 MongoDB 容器）
docker run -d --name eval-backend -p 8100:8100 eval-platform-backend

# 启动 MongoDB(可选)
# docker run -d --name eval-mongodb -p 27017:27017 mongo:6

# 启动后端服务（连接到本地 MongoDB 容器）
docker run -d --name eval-backend -p 8100:8100 \
  --link eval-mongodb:mongodb \
  -e MONGO_URI=mongodb://mongodb:27017/ai-mind-test \
  eval-platform-backend

# 查看日志
docker logs eval-backend

# 停止容器
docker stop eval-backend eval-mongodb
```

### vscode 建议配置

- 安装 [Vitest](https://marketplace.visualstudio.com/items?itemName=vitest.explorer) 插件

## 代码规范

- 使用 TypeScript 编写
- 遵循 [ESLint](https://eslint.org/) 配置
- 代码格式化采用 [Prettier](https://prettier.io/)

### vscode 建议配置

- 安装 [ESLint](https://marketplace.visualstudio.com/items?itemName=dbaeumer.vscode-eslint) 插件
- 安装 [Prettier](https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode) 插件
- 配置 `settings.json`：

```json
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "editor.codeActionsOnSave": {
    "source.fixAll.eslint": "explicit"
  },
  "[typescript]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[typescriptreact]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[json]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[jsonc]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[markdown]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[yaml]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  }
}
```

## 子包说明

### `@eval-platform/llm`

封装了对 Doubao 模型的调用，支持普通请求和流式请求。

```ts
import { ... } from '@eval-platform/llm'
```

支持模型：

- `doubao-seed-2-0-pro-260215`
- `doubao-seed-2-0-mini-260428`

### `@eval-platform/shared`

公共类型定义、接口和工具函数，供各子包和应用共享。

```ts
import { ... } from '@eval-platform/shared'
```

#### 日志

- 日志等级：`trace`, `debug`, `info`, `warn`, `error`, `fatal`
- 日志输出：
  - `debug` 及以上等级的日志会被打印到控制台
  - `info` 及以上等级的日志会被写入日志文件

使用说明：

```ts
import { logger } from '@eval-platform/shared'

/**
 * debug及以上等级的日志会被打印到控制台
 * info及以上等级的日志会被写入日志文件
 */
logger.silent('logger silent test')
logger.trace('logger trace test')
logger.debug('logger debug test')
logger.info('logger info test')
logger.warn('logger warn test')
logger.error('logger error test')
logger.fatal('logger fatal test')
```
