# 项目结构说明

这里的设计是临时的。将来可能做大的重构。

可能有很多地方需要改进。需要所有开发者理解全局，实践，思考和建议。

所有标有TODO的模块还没有实现，会逐渐实现。

各个模块大致按照从内层到外层的顺序。外层依赖内层。内层不可以依赖外层。例如，lite依赖intent_data和alg，反之则不行。

intent/
├── intent_data/ # 意图类别的定义。和算法无关。只包括通用定义。具体业务项目细节放在各个项目中。
│ └── category.py # 意图类别定义
│ └── vehicle_control.py # 车控意图类别定义。依赖于category。非常重要通用，结构上尽量灵活，支持不同项目的细节需求。
│ └── navigation.py  # TODO: 导航意图类别定义。依赖于category。非常重要通用，结构上尽量灵活，支持不同项目的细节需求。
│ └── datasets/  # TODO: 常用的各种内部小测试数据集，临时修改临时用。不用于业务交付，不需要进入数据库。例如，用于测运行时间的，快速改prompt看看效果的。
│
│── alg/ # 意图分类算法，很纯粹的底层实现。只依赖于intent_data。
│ └── core.py # 核心算法，通用组件等底层实现。
│ └── volc_intent.py # 火山引擎意图分类算法。
│ └── search.py # TODO: 涉及到知识库，rag等的算法。
│ └── classifier.py # TODO: 基于上述组件的wrapper class。有状态，可以非常方便灵活地配置，是各个项目中意图算法的基类。常用的各种算法选项可以指定。
│ └── experiments/ # TODO: 用于算法的快速实验和迭代。详见后续的说明。
│
│── eval/ # TODO: 算法的评测。这是个大话题。暂时想不清楚。跟前端也是需要打通的。
│ └── core.py # TODO: 核心评测算法，通用组件等底层实现。
│
│ 以下是各个业务项目的意图算法。都依赖于alg。它们各自交付，彼此完全独立，自行迭代。可以有自己定制化的各种实现。能提炼出来的通用的算法部件可以进入底层的alg。必要时可以独立成为单独的repo。
│── lite # TODO: 弋途ai car lite主线的意图算法。ydl的升级版。
│ └── intent_data/  # TODO: 依赖于前面的intent_data，定义了lite项目中特有的意图类别。
│ └── eval/ # TODO: 依赖于前面的eval。用于业务交付的算法精度性能等评测。很严肃的事情。
│ └── tests/ # TODO: 项目内部的功能测试。注意这和eval不同。这是工程功能层面，而eval是算法效果层面。
│ └── experiments/ # TODO: 用于算法的快速实验和迭代。详见后续的说明。
│
│── ydl # 原动力demo中的意图算法。结构无需像lite这么复杂。根据情况自定。
│
│── zhiji # 智己项目中的意图算法。结构无需像lite这么复杂。根据情况自定。
│
| 以下是数据库和后端。由于其细节和前面的内容紧密耦合，是否值得作为独立的repo不确定。
├── task_data/ # 衔接意图算法任务和数据库。将底层的算法数据和api转换成后端数据库和api能使用的统一格式。保持语义完全不变。和前端是解耦的。
│ └── message.py # 纯粹的对话数据。目前只用于intent input。将来尽量能解耦出来成为通用的对话数据结构，供所有的算法和后端数据库使用。
│ └── input.py # 描述算法的输入。依赖于intent_data
│ └── param.py # 描述算法的参数。
│ └── output.py # 描述算法的输出。
│ └── api_alg.py # 将alg中的算法通过input, param, output打包成一个API给前端。
│ └── api_lite.py # 类似的，将lite中的算法打包。
│
├── intent_mdb_models/ # MongoDB Documents 定义，依赖 intent_data
│ └── car_control.py #
│
├── intent_schemas/ # API Schemas，依赖 intent_data
│ └── car_control.py #
│
├── task_mdb_models/ # MongoDB Documents 定义，依赖 task_data
│ └── car_control.py #
│
├── task_schemas/ # API Schemas，依赖 task_data
│ └── car_control.py #
│
├── repositories/ # 数据库操作
│
├── services/ # API 实现，依赖 schemas
│
├── api/ # API 路由（依赖 services + schemas）
│
│ 测试部分。只包含通用功能的功能性测试。项目交付所需要的测试（工程和算法层面的）不在这里，在各个项目中自包含。例如ydl， zhiji等。
├── tests/
│ └── intent_data/
│     └── test_category.py
│
│ └── alg/
│     └── test_core.py
│
│ └── task_data/
│     └── test_message.py

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

## alg

意图任务的核心算法实现，需要支持所有项目的需求，需要高度通用，且持续迭代演化。

算法细节实现位于三个不同的层级：

1: alg: 完全通用。能支持所有项目需求的内容才进入alg模块。变更需要 wei yichen review。
2: lite: 是公司主线，几乎完全通用。支持大量项目。变更需要 wei yichen review。
3: 不同项目的不同细节实现放在不同模块中独立迭代，互不影响。例如, ydl, zhiji等。尽量复用1和2中的内容。

由于1和2的更改需要非常小心，这会严重阻碍算法细节迭代的速度。因此，在其下专门建立了experiments包，用于快速迭代。

- 所有算法同学随意修改算法代码（copy过来再改），随意做对比实验。
- 彼此隔离，互不干扰。随便写，快速迭代。
- 验证有效，经过code review后，合并到1和2中的正式代码。也可以不经过1和2，直接在3中某个项目进行。
- 不想这么麻烦，想直接改核心算法代码，先找wei yichen商量。

## task_data

输入、输出、ground truth、eval metric等。轻度依赖于（只有输入）intent_data。

具体实现和业务高度相关，但结构上有通用成分，将来能成为通用的“通用的业务任务数据库”。

和后端数据库和前端工具衔接。
