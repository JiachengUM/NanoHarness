# 智能体演练场 frontend 说明

# 项目结构

```
src
├── assets
├── components
├── hooks
├── request
├── router
├── store
├── styles
├── utils
├── views
├── App.tsx
├── main.tsx
├── vite-env.d.ts
└── vite.config.ts
```

# 目录说明

- `apis`: 存放请求相关的代码，如 API 请求函数。
- `assets`: 存放静态资源，如图片、字体等。
- `components`: 存放可复用的 React 组件。
- `hooks`: 存放自定义 React Hooks。
- `request`: 存放http请求封装相关的代码。
- `routers`: 存放路由相关的代码。
- `stores`: 存放状态管理相关的代码，如 Redux 或 MobX。
- `utils`: 存放工具函数和常用方法。
- `pages`: 存放页面级组件。
- `types`: 存放 TypeScript 类型定义文件。
- `App.tsx`: 应用的根组件。
- `index.css`: 全局样式文件。
- `main.tsx`: 应用的入口文件。
- `vite-env.d.ts`: Vite 环境的类型定义文件。
- `vite.config.ts`: Vite 的配置文件。

# 其他配置

- `tsconfig.json`: TypeScript 的配置文件。
- `eslint.config.js`: ESLint 的配置文件。
- `.prettierrc`: Prettier 的配置文件。
- `package.json`: 项目的依赖和脚本配置文件。

# 项目运行依赖

- Node.js >= 20.x
- npm >= 8.x

```bash
# 安装node环境（版本 20+）
https://nodejs.org/en/download

# node 环境验证
node -v
# v22.16.0
npm -v
# 11.6.3
```

# 项目运行

```bash

# 切换到项目目录
cd projects/mind/test_frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 打包项目
npm run build

# 预览打包结果
npm run preview
```

# 项目构建

```bash
# docker镜像构建
docker build -t ai-mind-test-web:latest -f projects/mind/test_frontend/Dockerfile .

# 运行docker镜像（本地运行docker需要更改dockerfile中的后端地址为http://127.0.0.1:8000/）
docker run --rm -p 9001:9001 --name ai-mind-test-web ai-mind-test-web:latest
```

# Backend 启动
```bash
uvicorn projects.mind.test_backend.main:app --reload
```