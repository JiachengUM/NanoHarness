# aicore简要介绍

aicore是通用的智能体架构和组件库，**同时用于业务项目交付和智能体演练场**。因此，它是联通业务交付和资产积累（平台数据库、数据链路、架构思路、产品认知等）的关键。

它提供很多功能的实现，但原则上不包括需要根据业务定制化的细节。业务细节的功能位于projects/目录下，每个项目可以不一样。业务项目尽量复用aicore中的功能（继承或者组合）。例如，项目中的master agent可以继承aicore\agents\的react or base agent.

以下按照从通用功能到具体业务的顺序简要介绍整体架构。注意，下层依赖上层，而不是反过来。

aicore/
├── utils/                                   # 完全通用的工具包，和aicore无关。
│ ├── nl_repr/                               # 自然语言表示模块
│ ├── volc_client/                           # 火山引擎模型能力底层API的封装
│ ├── misc.py                                # 杂项工具函数
│ └── _concepts/                             # 关于“概念”的实现和常用定义
│
├── core/                                    # aicore的基础设施层，与业务无关
│ ├── types.py                               # 通用数据类型定义
│ ├── event.py                               # 事件的基础定义
│ ├── task_runner.py                         # 任务执行器         TODO: 进入runtime
│ └── stream_task_runner.py                  # 流式任务执行器      TODO: 进入runtime
│
├── events/                                  # 事件系统定义，agent对外输出的唯一数据接口定义
│ ├── react.py                               # react算法的事件
│ └── task.py                                # （通用）任务事件
│
├── models/                                  # 语言模型层
│ ├── chat/                                  # 基于Chat API的封装
│ ├── responses/                             # 基于Responses API的封装
│ ├── messages.py                            # 模型层统一对外输出的消息格式
│ ├── doubao_models.py                       # 豆包模型定义和描述
│ └── credentials.py                         # 保密信息管理
│
├── tools/                                   # 供Agent调用的工具集
│ ├── builtin/                               # 内置工具实现
│ ├── base.py                                # 工具基类定义，基于langchain BaseTool的简化
│ ├── factory.py                             # 统一的创建工具API
│ ├── task.py                                # 结合BaseTool和runtime\task的工具，agent的重要组件
│ └── responses_helper.py                    # 基于Responses API的辅助功能
│
├── runtime/                                 # 运行时模块。相当于“手”，被agent控制和管理。 TODO: 将来会大幅扩展。
│ ├── task/                                  # 任务管理
│   └── models.py                            # 任务的数据模型定义
│   ├── manager.py                           # 任务管理器
│   └── worker.py                            # 任务的实现API
│
├── agents/                                  # Agent的通用功能。依赖events, models, tools, runtime等
│ ├── react.py                               # React算法的基础实现
│ └── _react_core.py                         # React算法的核心逻辑
│
├── simulation/                              # 模拟器，模拟端到端的测试。功能上不属于aicore
│ └── user_env/                              # 用户环境模拟
│
├── v1/                                      # agent V1架构，可能包括自己的tools, runtime, simulation等
│ ├── master.py                              # 主Agent实现
│ └── simulation/                            # V1特有的模拟器
│
├── v2/                                      # agent V2架构，可能包括自己的tools, runtime, simulation等
│ ├── async_tasks_demo.py                    # 简单demo
│ └── master.py                              # 主Agent实现
│

注意，

- 所有package下面均可能有实验性代码，位于experiments目录下。这些代码随时会改，不能进入生产。
- 其它代码都是能交付业务生产的质量，有充分的测试，位于tests目录下。

下面按照自底向上，从底层具象细节到高层抽象概念的顺序介绍各个模块。

## [工具包](./utils)

通用工具。

**由于其影响很大，需要具有全局观的核心开发者负责。普通开发者不允许修改。**。

### [自然语言表达](./utils/nl_repr/__init__.py)

跟语言模型交流主要用自然语言(natural language)，也就是写prompt，而大量的业务和数据概念用python表达。

基于这些概念写prompt时，如果缺乏统一的规范和管理，非常容易写出各种奇怪的、有噪声的prompt。

这个模块提供标准化、可配置的“将任意python对象”转换了自然语言的功能。

它大幅降低了智能体编程的工作量，大幅减少了prompt转写中的各种噪声和错误，同时也提供了足够的灵活性。

## 语言模型

对于火山引擎模型能力底层API的封装，屏蔽底层细节，提供统一接口供上层的智能体开发使用。

**由于其影响很大，需要具有全局观的核心开发者负责。普通开发者不允许修改。**。

### [responses API](./models/responses/__init__.py)

基于responses api的wrapper

TODO:

### [chat API](./models/chat/__init__.py)

基于chat api的wrapper

TODO:

### 其它

- [messages](./models/messages.py): 模型层对外输出的供agent使用的消息。
- [model_profile](./models/model_profile.py): 模型画像类
- [doubao_models](./models/doubao_models.py): 豆包模型配置类
- [credentials](./models/credentials.py): 保密信息

## 智能体架构 (agents, V1, V2, ...)

TODO: 不确定性非常大，要同时兼顾业务交付和架构探索，如何管理并不清楚。
