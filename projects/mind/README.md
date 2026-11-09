# Mind项目结构和代码说明

main分支受保护。不可写。

基础分支为mind。开发者各自开发时，为了效率，不强制要求建立新分支。

如果做的改动较大，会影响他人，请自行判断，必要时建立新分支开发，再merge回到mind分支。

请遵循下面关于项目结构的说明协同开发。有问题随时找wei yichen讨论。

## 工具包utils（TODO）

非常通用的功能。不依赖库里其它内容。

## AI Car advisor项目

## 目录结构

- mind
  - advisor
    - domain_data
      - vehicle_state
      - ...
    - task_data
      - input
      - output
      - param
      - prompt
    - repostitories
      - mdb_api.py
    - schemas
      - base.py
    - mdb_models
      - doc_base.py

  - intent
    - intent_data
      - category
      - ...
    - task_data
      - input
      - output
      - param
      - prompt
    - repostitories
      - mdb_api.py
    - schemas
      - base.py
    - mdb_models
      - doc_base.py
  
  - test_backend
    - main.py
    - config.py
    - core
      - context.py // 暂时不需要
    - api
    - db ?
    - schemas
      - paginate.py
      - response.py
    - repositories
      - mdb_api.py // get_page
      

  - test_frontend

测试工具前端部分
test_frontend
├── src/
│ ├── apis/ # http接口
│ ├── assets/ # 静态资源
│ ├── components/ # 可复用组件
│ ├── constants/ # 常量定义
│ ├── context/ # React context
│ ├── hooks/ # React hooks
│ ├── layout/ # 布局组件
│ ├── pages/ # 页面组件
│ ├── request/ # http请求封装
│ ├── routes/ # 路由配置
│ ├── stores/ # 状态管理
│ ├── types/ # 类型定义
│ ├── utils/ # 工具函数
│ ├── App.tsx # 根组件
│ ├── index.less # 全局样式
│ └── main.tsx # 入口文件
│
├── .env.development # 开发环境变量
├── package.json # 项目依赖库配置文件
├── tsconfig.json # TypeScript配置文件
└── vite.config.ts # Vite配置文件


docker

```bash
docker build -t nanoai-mind:dev -f projects/mind/test_backend/Dockerfile .
docker run -d -p 8000:8000 --name nanoai-mind nanoai-mind:dev

```