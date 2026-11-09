# UIAgent项目结构和代码说明

main分支受保护。不可写。

基础分支为ui。各自开发功能时，为了效率，不强制要求建立新分支。如果做的改动较大，会影响他人，请自行建立新分支开发，再merge回到ui分支。

请遵循下面关于项目结构的说明协同开发。有问题随时找wei yichen讨论。

## 工具包utils

通用函数、类。不依赖库里其它内容。

## 模型包model

## 数据包datasets

通用数据功能。和具体任务（停车、咖啡等）无关。

## [智能体算法通用包core](./core/__init__.py)

通用智能体算法功能。和具体任务（停车、咖啡等）无关。

按照依赖关系顺序，包括以下模块

- action.py: 关于ui action的定义。
- visualize.py：关于ui action的渲染。
- __init__: workflow通用实现。
- eval.py: 通用eval功能。

## 各个具体任务包（demo_task, seatbooking, coffee_purchase, jie_parking）

注意，demo_task是一个假任务。它仅仅起到code demo and experiment的作用。

所有智能体架构层面的改动，首先在这个任务上验证"代码怎么写"。其它任务的代码可以照葫芦画瓢。

所有的任务包共同遵循下面的架构。

- datasets包: 存放所有的重要测试数据以及生成数据的代码。注意，数据文件不可以提交进入git。所有开发者手动维护，保持一致。
- workflow.py: 智能体/工作流实现。
- eval.py：智能体评测。
- exps包：所有的实验。每个人可以维护自己的实验模块。不同的实验代码隔离开。
     其中的代码基于workflow.py随便改，尽量复用, 只修改必要的部分。参见[示例](./seatbooking/exps/exp_demo.py)

## 工作原则和思路

同时有三个过程在“永远不停”地进行。

（每个任务下）数据生成和积累：以boyang, fangwei为主执行。

（每个任务下）智能体代码实现和测试的不停迭代：以ziyu，fangwei，liudong为主执行。

智能体整体架构（含前端，测试）的不断迭代：以yichen为主执行。

这三个工作线程高度同步。互相促进，互相迭代。数据一直增长，智能体的效果不断提升，架构不断改进。
