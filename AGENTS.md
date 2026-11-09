# Skills 使用指南

> 当前项目已进入**框架级代码研发**阶段。本文档定义 agent 应何时使用哪个 skill。
> 涵盖 4 个 skill 库共 79 个 skill，按研发工作流阶段组织，标注重叠 skill 的选择优先级。

---

## 零、运行环境（强制）

- **默认 Python 解释器**：conda `dzy_env` 环境，完整路径：

  ```
  D:\apps\miniconda\envs\dzy_env\python.exe
  ```

- 运行本项目任何 Python 脚本 / pytest / demo 时，**一律直接用上述完整路径**，不要用裸 `python` 命令（系统 PATH 里没有），也不要每次重新搜索定位解释器。
- 示例：`D:\apps\miniconda\envs\dzy_env\python.exe -m pytest projects/experiments/time_travel_auto_test/test/ -x -q`

---


## 一、总览：来源与分工

| 来源 | 目录 | 数量 | 核心定位 |
|------|------|------|----------|
| **Matt Pocock** (`mattpocock/skills`) | `engineering/` `productivity/` `in-progress/` `misc/` | 35 | 工程方法论 + 生产力工具，强在流程路由、盘问、教学 |
| **Obra** (`obra/superpowers`) | `superpowers/` | 14 | 开发超能力，强在头脑风暴、系统调试、计划执行、子代理调度 |
| **Addy Osmani** (`addyosmani/agent-skills`) | `agent-skills/` | 24 | 全栈工程，强在规格驱动、安全、发布、可观测性、CI/CD |
| **Dietrich Gebert** (`DietrichGebert/ponytail`) | `ponytail/` | 6 | 代码极简主义，强在过度工程审计、YAGNI 强制执行 |

---

## 二、按研发阶段：何时使用哪个 Skill

### 阶段 0：方向定位（不知道用什么时）

| Skill | 来源 | 用途 | 触发条件 |
|-------|------|------|----------|
| **ask-matt** | MP | 整套 skills 的"路由器"，描述从 idea 到 ship 的完整流程地图 | 不确定该用哪个 skill、想了解整体流程时 |
| **using-superpowers** | SP | superpowers 系统入口，设定 skill 优先级和调用铁律 | 每次对话开始时检查；有 1% 可能适用就调用 |
| **using-agent-skills** | AS | 元技能，根据开发阶段自动匹配应使用的 agent-skills | 开始新会话、需要发现适用技能时 |
| **ponytail-help** | PT | ponytail 快速参考卡片 | 询问 ponytail 用法时 |

> **选择建议**：新会话开始时，优先查 `using-superpowers` 和 `using-agent-skills`；不确定整体方向时用 `ask-matt`。

---

### 阶段 1：需求发现与设计

| Skill | 来源 | 用途 | 触发条件 |
|-------|------|------|----------|
| **brainstorming** | SP | 将模糊想法转化为完整设计，**禁止在获得批准前写代码** | 任何创造性工作前（新功能/组件/行为变更）**必须使用** |
| **interview-me** | AS | 面试式一问一答，提取用户真正想要的而非"觉得应该要的" | 需求模糊、用户说"帮我做X"但没说清为什么/为谁时 |
| **idea-refine** | AS | 结构化发散收敛思维，将原始想法精炼为可操作方案 | 想法模糊需要扩展、想在投入前做压力测试时 |
| **grilling** | MP | 有状态盘问，将讨论映射为"设计树"，按轮次推进 | 需要压力测试一个想法或决策时 |
| **grill-me** | MP | 无状态盘问（`grilling` 的轻量版，不保存 CONTEXT.md） | 不在工作目录中、需要快速打磨计划时 |
| **wait-what** | MP | 纠正上一条没理解的消息，用简化技术英语重新解释 | agent 回复没说到点子上需要重新解释时 |

> **重叠说明**：`brainstorming`(SP) 和 `interview-me`(AS) 都用于需求澄清，但 `brainstorming` 更偏设计产出且有硬性"不写代码"门禁，`interview-me` 更偏需求提取。模糊需求先用 `interview-me`，有方向后需要设计时用 `brainstorming`。

---

### 阶段 2：规格与计划

| Skill | 来源 | 用途 | 触发条件 |
|-------|------|------|----------|
| **spec-driven-development** | AS | 在写任何代码前先写好结构化规格文档 | 新项目/新功能/重大变更且没有规格时；预计实现超过 30 分钟时 |
| **to-spec** | MP | 从当前对话上下文合成一份 spec 发布到 issue tracker | 对话已充分讨论需求，需要固化为规范文档时 |
| **writing-plans** | SP | 根据设计规格编写详尽实现计划，假设执行者对代码库零上下文 | 已有规格或需求文档，需要在写代码前制定实现计划时 |
| **planning-and-task-breakdown** | AS | 将工作拆解为有序的、可验证的小任务 | 有规格需要拆成可实现单元、任务太大无法开始时 |
| **to-tickets** | MP | 将 spec 拆分为"曳光弹"ticket（垂直切片），发布到 tracker | 需要将大 spec 拆分为可独立执行的任务时 |
| **wayfinder** | MP | 为超大型模糊项目规划"共享地图"——在 tracker 上创建决策 ticket | 面对巨大、模糊、无法在一次会话中完成的项目时 |
| **codebase-design** | MP | 定义模块、接口、深度、接缝等深层模块设计词汇 | 需要打磨项目的深层设计语言时 |

> **重叠说明**：`spec-driven-development`(AS)、`to-spec`(MP)、`writing-plans`(SP) 都在规格阶段工作。`spec-driven-development`(AS) 最完整（结构化规格+能力图谱），`to-spec`(MP) 最轻量（从对话合成），`writing-plans`(SP) 侧重实现计划。建议：新功能用 `spec-driven-development`(AS)，已有充分讨论用 `to-spec`(MP) 快速固化，实施前用 `writing-plans`(SP) 制定计划。

---

### 阶段 3：实现

| Skill | 来源 | 用途 | 触发条件 |
|-------|------|------|----------|
| **ponytail** | PT | 强制最简方案——YAGNI 优先，最短、最简单、最精简代码 | 任何编码任务（写代码/重构/修复/审查/设计）时持续生效 |
| **test-driven-development** | SP | 严格红-绿-重构循环，先写测试看失败再写实现 | 实现任何功能或修复任何 bug 时**必须**在写实现代码前使用 |
| **implement** | MP | 基于 spec 驱动 TDD 实现，完成后自动运行 code-review | 有明确的 spec 或 ticket 需要编码实现时 |
| **incremental-implementation** | AS | 薄垂直切片增量交付，每实现一小片就测试验证提交 | 实现涉及多个文件的变更、任务太大无法一步完成时 |
| **source-driven-development** | AS | 每个框架相关代码决策都必须有官方文档佐证 | 使用任何框架或库、正确性很重要、构建样板代码时 |
| **doubt-driven-development** | AS | 在每个非平凡决策生效前启动对抗性审查者挑战它 | 正确性比速度更重要、不熟悉代码、高风险操作时 |
| **subagent-driven-development** | SP | 每任务派遣全新实现子代理，附带规范符合性+代码质量双重审查 | 有实现计划、任务大部分独立、在当前会话中执行时 |
| **executing-plans** | SP | 加载已写好的实现计划，在隔离会话中逐步执行 | 已有书面实现计划需在独立会话中执行时 |
| **dispatching-parallel-agents** | SP | 将多个独立任务并行分派给不同专门子代理 | 2 个以上彼此独立、无共享状态、无顺序依赖的任务时 |
| **prototype** | MP | 构建一次性原型代码来验证设计问题（逻辑分支/UI 分支） | 设计问题难以在纸面上定论、需要可运行代码验证时 |
| **context-engineering** | AS | 在正确时机向 Agent 提供正确信息，优化上下文质量 | 开始新会话、Agent 输出质量下降、切换代码区域时 |
| **frontend-ui-engineering** | AS | 构建生产级、可访问、响应式 UI，避免"AI 审美" | 构建或修改界面/页面/组件/布局时 |
| **api-and-interface-design** | AS | 设计稳定、文档良好、不易误用的 API 和接口 | 设计 API 端点、定义模块边界、创建组件 props 接口时 |

> **重叠说明**：
> - **TDD**：三个库都有 TDD，`superpowers/tdd`(SP) 最严格（硬性门禁），`agent-skills/tdd`(AS) 最完整（含修复 bug 前先写复现测试），`mattpocock/tdd`(MP) 侧重测试质量参考。建议：实现时用 `superpowers/tdd`(SP) 作为门禁，修复 bug 时用 `agent-skills/tdd`(AS) 的复现测试流程。
> - **实现方式**：`implement`(MP) 是完整流程（TDD + code-review + commit），`subagent-driven-development`(SP) 适合大量独立任务并行，`incremental-implementation`(AS) 适合单任务增量交付。单个明确任务用 `implement`(MP)，多任务用 `subagent-driven-development`(SP)，大文件变更用 `incremental-implementation`(AS)。

---

### 阶段 4：验证与调试

| Skill | 来源 | 用途 | 触发条件 |
|-------|------|------|----------|
| **systematic-debugging** | SP | 必须找到根因再修复，严禁症状修复，含根因追踪和防御深度 | 任何技术问题（测试失败/生产 bug/异常行为/性能问题/构建失败）时**必须**在提出修复前使用 |
| **debugging-and-error-recovery** | AS | 系统化分类检查清单，指导根本原因调试 | 测试失败、构建中断、行为不符合预期时 |
| **verification-before-completion** | SP | 声称完成前必须运行验证命令并确认输出，证据先于断言 | 即将声称完成/成功、提交代码、创建 PR 之前**必须**使用 |
| **browser-testing-with-devtools** | AS | 通过 Chrome DevTools MCP 在真实浏览器中测试 | 构建或调试浏览器中运行的东西时（需配置 chrome-devtools MCP） |
| **diagnosing-bugs** | MP | 诊断难以一眼看出的 bug（间歇性故障、回归等） | 复杂 bug 排查时 |

> **重叠说明**：`systematic-debugging`(SP) 和 `debugging-and-error-recovery`(AS) 都用于调试，但 `systematic-debugging`(SP) 更严格（硬性门禁、根因追踪、防御深度），`debugging-and-error-recovery`(AS) 更结构化（分类检查清单）。调试时**优先使用 `systematic-debugging`(SP)**。

---

### 阶段 5：审查

| Skill | 来源 | 用途 | 触发条件 |
|-------|------|------|----------|
| **code-review** | MP | 双轴审查：Standards（编码规范）+ Spec（忠实实现 spec/issue），两个子 agent 并行 | 想 review 一个分支、PR、或要求"review since X"时 |
| **code-review-and-quality** | AS | 五维审查：正确性、可读性、架构、安全性、性能 | 合并任何变更之前、审查代码质量时 |
| **requesting-code-review** | SP | 派遣代码审查子代理，审查要早、要频繁 | 完成每个任务后、完成主要功能后、合并到主分支前**必须**使用 |
| **receiving-code-review** | SP | 以技术严谨性接收审查反馈，验证后再实施 | 收到代码审查反馈后、实施建议之前 |
| **ponytail-review** | PT | 专注审查 diff 中的过度工程问题（重复造轮子、不必要的依赖、推测性抽象、死代码） | 审查时想找可删除内容、"is this over-engineered"时 |
| **code-simplification** | AS | 在不改变行为的前提下简化代码提高清晰度 | 代码能工作但阅读/维护/扩展难度过高时 |
| **improve-codebase-architecture** | MP | 发现代码库中可深化的机会 | 审查发现架构层面改进机会时 |

> **重叠说明**：
> - **代码审查**：三个库都有审查 skill。`requesting-code-review`(SP) 最轻量（派遣子代理），`code-review`(MP) 双轴审查（Standards + Spec），`code-review-and-quality`(AS) 最全面（五维）。建议：日常审查用 `requesting-code-review`(SP) 快速派遣，完整审查用 `code-review-and-quality`(AS)，需要对照 spec 时用 `code-review`(MP)。
> - **简洁性审查**：`ponytail-review`(PT) 和 `code-simplification`(AS) 都关注简洁，但 `ponytail-review`(PT) 专注过度工程删除，`code-simplification`(AS) 关注可读性提升。两者互补。

---

### 阶段 6：发布与维护

| Skill | 来源 | 用途 | 触发条件 |
|-------|------|------|----------|
| **finishing-a-development-branch** | SP | 实现完成、测试全绿后，决定如何集成（合并/PR/保留）并清理 | 实现完成、测试全绿、需要决定如何合入代码时 |
| **git-workflow-and-versioning** | AS | 原子提交、分支策略、语义化版本、变更日志 | 任何时候提交、分支、解决冲突、发布版本时 |
| **shipping-and-launch** | AS | 生产发布准备：检查清单、监控设置、分阶段上线、回滚策略 | 准备部署到生产环境时 |
| **ci-cd-and-automation** | AS | 自动化 CI/CD 流水线，确保每次变更都经过质量门禁 | 设置或修改构建部署流水线时 |
| **deprecation-and-migration** | AS | 安全移除旧系统/API/功能，将用户迁移到新实现 | 替换旧系统、下线功能、合并重复实现时 |
| **documentation-and-adrs** | AS | 记录决策和文档，重点在"为什么"而非"是什么" | 做架构决策、修改公共 API、发布功能时 |
| **observability-and-instrumentation** | AS | 结构化日志、指标、追踪、告警 | 发布任何生产功能、生产问题无法从现有数据判断时 |
| **security-and-hardening** | AS | 针对漏洞加固代码，覆盖 OWASP 常见安全风险 | 处理用户输入、认证、数据存储、外部集成时 |
| **performance-optimization** | AS | 先测量再优化，只优化测量证明值得优化的部分 | 规格中有性能要求、用户报告缓慢、怀疑性能回退时 |
| **triage** | MP | 将 issue/PR 按角色状态机分类、验证、编写 agent 可执行简报 | 维护者处理来自他人的 issue 或 PR 时 |
| **resolving-merge-conflicts** | MP | 逐块解决合并/变基冲突 | 遇到合并冲突时 |
| **using-git-worktrees** | SP | 确保开发工作在隔离的 git worktree 中进行 | 开始需要隔离当前工作区的功能开发时 |

> **发布阶段 skills 全部来自 agent-skills(AS)**，构成了完整的发布流水线。`finishing-a-development-branch`(SP) 是开发分支收尾，`git-workflow-and-versioning`(AS) 是日常 Git 操作基础。

---

### 阶段 7：生产力与元技能

| Skill | 来源 | 用途 | 触发条件 |
|-------|------|------|----------|
| **teach** | MP | 多会话教学，构建教学空间含课程/参考资料/学习记录 | 用户想学习新概念或技能且需跨多个会话时 |
| **handoff** | MP | 将当前对话压缩为交接文档供另一个 agent 在新会话中接续 | 需要将进度交给另一个会话（新目录/同事/分叉子任务）时 |
| **loop-me** | MP | 设计可自动化的工作流，识别重复模式输出 spec | 用户想设计一个可自动化的工作流时 |
| **writing-skills** | SP | 用 TDD 方式创建或编辑 skill 文档 | 创建新 skill、编辑已有 skill、验证 skill 是否有效时 |
| **wizard** | MP | 生成交互式 bash 脚本引导人类完成只有人类能执行的步骤 | agent 遇到只能由人类完成的步骤（配置 CI secrets、操作第三方后台）时 |
| **writing-for-agents** | MP | 编写 agent 可消费文档的参考指南 | 需要写 agent 可读的文档时 |
| **to-questionnaire** | MP | 当阻碍来自他人时，编写问卷发给对方 | 需要向他人收集信息时 |
| **migrate-to-shoehorn** | MP | 将 `as` 类型断言迁移为类型安全的 `fromPartial()` 等 | 替换测试中的 `as` 断言、需要部分测试数据时 |
| **scaffold-exercises** | MP | 创建课程练习目录结构 | 搭建练习脚手架、设置新课程章节时 |
| **setup-pre-commit** | MP | 在当前仓库配置 Husky pre-commit hooks + lint-staged | 添加 pre-commit hooks、配置自动格式化/类型检查时 |
| **setup-matt-pocock-skills** | MP | 配置 issue tracker、triage 标签和文档布局 | 首次配置 matt-pocock skills 时 |

---

### 阶段 8：Ponytail 专项（代码极简主义）

| Skill | 来源 | 用途 | 触发条件 |
|-------|------|------|----------|
| **ponytail** | PT | 强制最简方案——三种强度：lite / full / ultra | 任何编码任务持续生效；用户说"be lazy"、"simplest solution"、"yagni"时 |
| **ponytail-audit** | PT | 全仓库过度工程审计，生成可删除/简化清单（只读） | 用户说"audit this codebase"、"find bloat"、"what can I delete"时 |
| **ponytail-debt** | PT | 收集 `ponytail:` 注释标记，整理成技术债务账本（只读） | 用户说"ponytail debt"、"list the shortcuts"时 |
| **ponytail-gain** | PT | 展示 ponytail 量化收益看板（行数减少/成本降低/速度提升） | 用户说"ponytail gain"、"scoreboard"时 |
| **ponytail-review** | PT | Diff 过度工程审查，逐行标注可删除内容 | 审查时想找可删除内容时 |

---

## 三、关键重叠 Skill 选择速查

多个库有同名或类似 skill 时，按以下优先级选择：

| 场景 | 首选 | 次选 | 说明 |
|------|------|------|------|
| **TDD** | `superpowers/tdd` | `agent-skills/tdd` | SP 版最严格（硬性门禁），AS 版含修复 bug 前复现测试 |
| **代码审查** | `requesting-code-review`(SP) | `code-review-and-quality`(AS) | SP 版轻量快速，AS 版五维全面 |
| **调试** | `systematic-debugging`(SP) | `debugging-and-error-recovery`(AS) | SP 版硬性根因追踪，AS 版分类检查清单 |
| **需求澄清** | `brainstorming`(SP) | `interview-me`(AS) | SP 版偏设计产出，AS 版偏需求提取 |
| **规格编写** | `spec-driven-development`(AS) | `to-spec`(MP) | AS 版完整结构化，MP 版从对话合成 |
| **任务拆分** | `planning-and-task-breakdown`(AS) | `to-tickets`(MP) | AS 版可验证任务，MP 版垂直切片 ticket |
| **简洁性** | `ponytail`(PT) | `code-simplification`(AS) | PT 版强制最简，AS 版事后简化 |

---

## 四、参考库

```
.trae/skills/_original-repos/
├── mattpocock-skills/    原始仓库（含 docs/scripts/agents/.changeset 等上下文）
├── superpowers/          原始仓库（含 tests/hooks/scripts 等上下文）
├── agent-skills/         原始仓库（含 evals/references/hooks/agents 等上下文）
└── ponytail/             原始仓库（含 benchmarks/examples/hooks 等上下文）
```

_original-repos/ 仅作参考资料，agent 默认不搜索、不加载。需要查阅原始 README/AGENTS.md/cookbook 等上下文时手动进入。

---

当前阶段：**框架级代码研发**
最后更新：2026-08-20