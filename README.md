# 项目简介

这不是一个**框架**库，而是一个综合了**组件、demo和业务项目**的库。“nano”意味着精细小巧灵活，容易适配和组装。这是该仓库的初衷，也是它跟各种框架的本质区别。

该库是独立开发的，仅依赖于openai API，目前跟任何开源框架都没有关系。

不写框架是因为认知和能力不足。大部分业务项目也没有必要。简单地基于底层API写业务功能即可。积累了足够多经验和细节后再考虑写框架。

具体地说，这个库的作用如下。

**首先**，它提供**简单通用组件**, 降低开发难度，帮助开发者**以接近于低代码和自然语言的方式**

1. 快速搭建智能体原型, 快速迭代实验，做预研，获得重要认知，例如“语言模型是否能实现某个功能需求”。
2. 构建测试和数据体系，基于此发布产品。
3. last but not least, **以代码和数据的形式**交流和积累认知。

**其次**，它提供**高质量的代码、注释、测试和demo**，好读好懂，帮助开发者提升智能体开发能力。它足够简单灵活，容易扩充容易改。**业务代码完全可以照葫芦画瓢，copy它然后自行扩充。**。

**最后**，它足够成熟时直接用于产品。目前还不到这个程度。

## 项目结构

- [nanoai](./nanoai/README.md): 核心功能模块。和具体业务无关。高质量。有些能直接用于业务，有些还处于预研阶段。
- [examples](./examples/README.md): 各种demo，演示如何使用各种核心功能模块。
- tests: 对nanoai的详尽测试。同时也有"教学"的作用。
- [mvms](./mvms/README.md): 预研的记忆功能模块。还很初期，不成熟。
- [projects](./projects/README.md)：各个业务项目。独立开发和维护。基本都依赖nanoai的核心功能。
- [projects/nanoai](./projects/nanoai/README.md)：基于 FastAPI 的最简 HTTP demo，演示 V1 Agent Session 的创建、SSE turn 输出和取消。

## 快速开始

- 环境要求: python 3.12。近期会升级到python 3.13。
- 安装步骤: 根目录下运行

```bash
pip install -r requirements.txt
```

## NanoAI HTTP Demo

仓库内的可运行 HTTP demo 位于 [projects/nanoai](./projects/nanoai/README.md)。从仓库根目录启动：

```bash
uv run uvicorn projects.nanoai.main:app --reload
```

启动后访问 `http://127.0.0.1:8000/docs` 查看接口文档，或访问 `/health` 验证服务状态。
该 demo 当前只支持创建时的静态 Session context；动态 `state_update` 会明确返回错误。
它支持导出 dump，并可在服务重启后通过 HTTP restore 恢复对话，详见
[projects/nanoai](./projects/nanoai/README.md)。
