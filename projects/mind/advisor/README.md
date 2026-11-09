# 项目结构说明

advisor/
├── domain_data/ # 核心业务数据结构，不依赖其它内容。
│ └── user.py # 用户 profile
│ └── vehicle_state.py # 车辆状态
│ └── visual_ext.py # 外部视觉信息
│ └── visual_int.py # 内部视觉信息
│ └── event.py # (触发 advisor 的)事件
│
├── task_data/ # advisor task相关的数据结构。轻度（只有输入）依赖于domain_data。
│
│── advisors/ # all advisor agents, 依赖task_data
│ └── comfort.py # 舒适 advisor
│ └── emotion.py # 情感 advisor
│
├── mdb_models/ # MongoDB Documents 定义，依赖 domain_data
│ └── user.py # UserDoc(Document, UserBase)
│
├── schemas/ # API Schemas，依赖 domain_data
│ └── user.py # UserCreate, UserUpdate
│
├── repositories/ # 数据库操作，依赖 mdb_models
│
├── services/ # API 实现，依赖 schemas
├── api/ # API 路由（依赖 services + schemas）
│
├── tests/
│ └── advisors/
│ └── test_comfort.py

## domain_data

尽量通用。将来会挪到 mind 目录下，作为所有 advisor 类 agent 的核心数据结构。

## task_data

输入、输出、ground truth、eval metric等。轻度依赖于（只有输入）domain_data。

其概念层级不同，位于“业务task”层面，输入、输出、metric等都可能有不同定义，需要和domain_data解耦。

虽然具体实现和业务高度相关，但结构上有相同通用的成分，设计上需要尽量通用，将来能成为通用的“通用的业务任务数据库”。

## mdb_models

同时对应于domain_data和task_data的mongodb文档定义。

TODO: 应该分拆为 domain_mdb_models 和 task_mdb_models

设计上尽量通用。

domain_mdb_models将来会挪到 mind 目录下，作为所有 advisor 类 agent 的测试数据库。

task_mdb_models将来会成为公司智能体演练场通用数据库的一部分。

## schemas

不通用。为了该项目的 API 服务。

TODO: 类似于domain和task的区别，也应该分为两部分。

## 项目启动说明

安装依赖：

```bash
pip install -r requirements.txt

```

运行开发服务：

```bash
uvicorn projects.mind.advisor.main:app --reload
uvicorn projects.mind.test_backend.main:app --reload

```

docker

```bash
docker build -t nanoai-mind:dev -f projects/mind/Dockerfile .
docker run -d -p 8000:8000 --name nanoai-mind nanoai-mind:dev

```

访问: http://localhost:8000/api/health
