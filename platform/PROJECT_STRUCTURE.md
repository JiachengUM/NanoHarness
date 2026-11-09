# Agent Eval Platform - 项目结构完整说明

> 本文档详细说明整个项目的目录结构、文件用途和架构设计。
> **注意**：项目进行任何结构调整时，必须同步更新此文档。

---

## 1. 项目概览

这是一个基于 **pnpm workspace + Turborepo** 构建的 monorepo 项目，用于 AI Agent 评测平台。

- **项目名称**: `eval-platform`
- **包管理器**: pnpm@11.5.1
- **构建工具**: Turborepo
- **开发语言**: TypeScript 6.x
- **运行时**: Node.js >= 22
- **数据库**: MongoDB
- **LLM**: 字节跳动 Doubao（通过 OpenAI SDK 兼容接口调用）

---

## 2. 顶层目录结构

```
platform/
├── apps/                    # 应用层（可部署的独立应用）
│   ├── backend/            # Fastify API 服务端
│   └── frontend/           # 前端应用（暂不活跃）
│
├── packages/               # 共享包（可被 apps 或其他 packages 依赖）
│   ├── database/          # MongoDB 数据访问层 (@eval-platform/database)
│   ├── evaluation/        # 评测核心逻辑 (@eval-platform/evaluation)
│   ├── llm/               # LLM 客户端封装 (@eval-platform/llm)
│   ├── makedata/          # 数据生成工具 (@eval-platform/makedata)
│   └── shared/            # 公共工具与类型 (@eval-platform/shared)
│
├── .turbo/                # Turborepo 缓存目录（自动生成）
├── logs/                  # 应用日志输出目录
├── node_modules/          # 依赖目录（pnpm 虚拟存储）
├── package.json           # 根项目配置
├── pnpm-workspace.yaml    # pnpm workspace 配置
├── turbo.json             # Turborepo 管道配置
├── tsconfig*.json         # TypeScript 配置（多层级）
├── vitest.config.ts       # 测试配置
└── eslint.config.js       # ESLint 配置
```

---

## 3. 配置文件详解

### 3.1 根目录配置文件

| 文件 | 用途 | 关键配置 |
|------|------|----------|
| `pnpm-workspace.yaml` | 定义 workspace 成员 | `packages: - apps/* - packages/*` |
| `turbo.json` | Turborepo 构建管道 | 定义 build/typecheck/test 任务的依赖关系 |
| `tsconfig.base.json` | 共享 TS 配置 | ES2023, ESNext, Bundler resolution |
| `tsconfig.json` | 根 TS 配置 | 继承 base，用于类型检查 |
| `package.json` | 根项目 | 脚本: build/dev/typecheck/test/lint/format |

### 3.2 Turborepo 任务管道

```json
{
  "build": { "dependsOn": ["^build"], "outputs": [".next/**", "dist/**"] },
  "typecheck": { "dependsOn": ["^typecheck"] },
  "lint": { "dependsOn": ["^lint"] },
  "dev": { "cache": false, "persistent": true },
  "test": { "dependsOn": ["^build"], "outputs": ["coverage/**"] }
}
```

- `^` 表示依赖其他包的同名任务
- `dev` 任务不缓存且持久运行

---

## 4. Apps 目录详解

### 4.1 apps/backend（API 服务端）

**技术栈**: Fastify 5.x + Zod Type Provider + MongoDB

```
backend/
├── package.json           # 定义 eval-platform-backend 包
├── tsconfig.json        # 后端专用 TS 配置
├── src/
│   ├── index.ts         # 入口：连接 DB + 启动服务
│   ├── core/
│   │   ├── app.ts       # Fastify 应用构建器（Swagger/Zod/错误处理）
│   │   └── config.ts    # 运行时配置（MONGO_URI, PORT, HOST）
│   ├── api/
│   │   ├── register-routes.ts   # 路由自动注册器
│   │   └── routes/
│   │       ├── dataset.ts                  # Dataset CRUD
│   │       ├── dataset-item.ts             # DatasetItem CRUD
│   │       ├── tag-tree.ts                 # 标签树管理 + 预览/导出
│   │       ├── scenario-management.ts      # 场景 CRUD + 按场景查用例
│   │       ├── scenario-planning.ts        # Plan 生成/确认/查询
│   │       ├── scenario-generation.ts      # 同步场景生成
│   │       ├── scenario-generation-stream.ts # SSE 流式场景生成
│   │       ├── case-generation.ts          # 同步用例生成
│   │       ├── case-generation-stream.ts   # SSE 流式用例生成
│   │       ├── generation-task.ts          # 生成任务定义 CRUD
│   │       └── generation-task-run.ts      # 生成任务运行记录
│   ├── http/
│   │   └── response.ts  # 响应封装（reply.success/reply.fail）
│   ├── schema/
│   │   └── params.ts    # 通用参数 Schema（IdParams）
│   ├── constants/
│   │   ├── index.ts     # API_PREFIX = '/api'
│   │   └── http-status.ts # HTTP 状态码常量
│   └── tests/
│       └── api/
│           ├── dataset.test.ts            # Dataset API 测试（Mock）
│           ├── generate-task.test.ts       # Generation Task API 测试（Mock）
│           ├── scenario-planning.test.ts   # Scenario Planning API 测试（Real LLM + MongoDB）
│           └── end-to-end.test.ts          # 端到端 API 测试（Real LLM + MongoDB）
```

**API URL 前缀**: `/api`

完整路由格式: `/api/{route_prefix}/{path}`

**SSE 流式生成 API**:

| 路由 | 事件类型 | 说明 |
|------|----------|------|
| `POST /api/scenario-generation-stream` | `plan` → `patterns` → `scenario` → `progress` → `complete` | 流式场景生成，实时推送 Plan、Patterns、场景和进度 |
| `POST /api/case-generation-stream` | `case` → `progress` → `complete` | 流式用例生成，每生成一个用例即推送 |
| `POST /api/scenario-generation-stream/cancel` | - | 取消正在进行的场景生成 |

**服务配置** (config.ts):
- MongoDB URI: `mongodb://127.0.0.1:27017/ai-mind-test`
- 端口: `8100`
- 主机: `0.0.0.0`

---

## 5. Packages 目录详解

### 5.1 @eval-platform/database（数据访问层）

**技术栈**: Mongoose + Typegoose + Zod

```
database/
├── package.json           # 定义子路径导出
├── tsconfig.json
├── src/
│   ├── index.ts          # 主出口：导出所有模型和基础类
│   ├── connection.ts     # MongoDB 连接管理（connect/disconnect）
│   ├── base/
│   │   ├── document.ts   # BaseDocument（所有模型的基类）
│   │   ├── repository.ts # BaseRepository（通用 CRUD 封装）
│   │   ├── schema-options.ts # createModelOptions 辅助函数
│   │   └── dto.ts        # CreateSchema/UpdateSchema/PageSchema
│   └── models/
│       ├── dataset/          # 数据集（父）
│       │   ├── dataset.schema.ts
│       │   ├── dataset.dto.ts
│       │   ├── dataset.repository.ts
│       │   └── index.ts
│       │
│       ├── dataset-item/     # 测试用例（子）
│       │   ├── dataset-item.schema.ts
│       │   ├── dataset-item.dto.ts
│       │   ├── dataset-item.repository.ts
│       │   └── index.ts
│       │
│       ├── tag-tree/         # 标签树（测试维度）
│       │   ├── tag-tree.schema.ts
│       │   ├── tag-tree.dto.ts
│       │   ├── tag-tree.repository.ts
│       │   └── index.ts
│       │
│       ├── scenario/         # 场景
│       │   ├── scenario.schema.ts    # Typegoose 模型（含 pattern 字段）
│       │   ├── scenario.dto.ts       # Zod Schema（含 LLMScenarioSchema）
│       │   ├── scenario.repository.ts
│       │   └── index.ts
│       │
│       ├── scenario-plan/     # 场景生成计划（Plan）
│       │   ├── scenario-plan.schema.ts  # Typegoose 模型（不含 scenario_patterns）
│       │   ├── scenario-plan.dto.ts     # Zod Schema + PlannerOutputSchema
│       │   ├── scenario-plan.repository.ts
│       │   └── index.ts
│       │
│       ├── scenario-judge/    # Judge 评估相关 DTO
│       │   ├── scenario-judge.dto.ts    # GenerationGuidanceSchema, LLMJudgementOutputSchema
│       │   └── index.ts
│       │
│       ├── generation-task/   # 生成任务定义
│       │   ├── generation-task.schema.ts
│       │   ├── generation-task.dto.ts
│       │   ├── generation-task.repository.ts
│       │   └── index.ts
│       │
│       ├── generation-task-run/ # 生成任务运行记录
│       │   ├── generation-task-run.schema.ts
│       │   ├── generation-task-run.dto.ts
│       │   ├── generation-task-run.repository.ts
│       │   └── index.ts
│       │
│       └── case-audit/       # 用例审核（仅类型，不入库）
│           ├── case-audit.dto.ts
│           └── index.ts
```

**子路径导出** (package.json):

```json
{
  "exports": {
    ".": "...",
    "./models/tag-tree": "...",
    "./models/scenario": "...",
    "./models/scenario-plan": "...",
    "./models/scenario-judge": "...",
    "./models/case-audit": "...",
    "./models/dataset-item": "...",
    "./models/dataset": "...",
    "./models/generation-task": "...",
    "./models/generation-task-run": "..."
  }
}
```

**核心功能**:

| 功能 | 说明 | 使用场景 |
|------|------|----------|
| **数据集管理** | Dataset CRUD + 级联删除 DatasetItem | 创建/管理评测数据集 |
| **用例管理** | DatasetItem CRUD + 自动计数同步 | 存储/更新测试用例 |
| **标签树管理** | TagTree 增删查（树结构存储） | 定义评测标签体系（测试维度） |
| **场景管理** | Scenario CRUD + pattern 字段 | 管理测试场景模板 |
| **Plan 管理** | ScenarioPlan CRUD + 状态流转 | 管理场景生成计划 |
| **生成任务管理** | GenerationTask/Run CRUD + 事件记录 | 跟踪生成任务执行 |
| **类型验证** | Zod Schema 运行时类型校验 | API 参数/数据验证 |
| **数据库连接** | MongoDB 连接管理（单例模式） | 应用启动时连接 |

---

### 5.2 @eval-platform/llm（LLM 客户端）

**技术栈**: OpenAI SDK（封装 Doubao 模型）

```
llm/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts          # 主出口
│   ├── client.ts         # createClient() - 创建 OpenAI 客户端
│   ├── chat.ts           # Chat API 封装
│   ├── responses.ts      # Responses API 封装（invoke / invokeWithRetry）
│   ├── types.ts          # 类型定义
│   └── zod.ts            # zodTextFormat 辅助函数
└── tests/
    └── responses.test.ts
```

**支持的模型**:
- `doubao-seed-2-0-pro-260215`
- `doubao-seed-2-0-mini-260428`

**主要导出**:
```typescript
import { 
  createClient,       // 创建客户端
  invoke,             // 调用 Responses API
  invokeWithRetry,    // 带重试的调用（处理 JSON 解析偶发错误）
  invokeWithRetryRaw, // 带重试的原始文本调用
  stream,             // 流式调用
  zodTextFormat,      // Zod Schema 转 OpenAI JSON Schema
} from '@eval-platform/llm'
```

**设计特点**:
- 基于 OpenAI SDK 封装，支持字节跳动 Doubao 模型
- 结构化输出：通过 Zod Schema 定义输出格式，LLM 严格遵循
- `invokeWithRetry`：指数退避重试（1s, 2s, 4s），最多 3 次
- 类型安全：TypeScript 类型与 Zod Schema 同步

---

### 5.3 @eval-platform/makedata（数据生成）

**用途**: 基于 LLM 生成测试场景和用例，包含 Plan → Pattern → 生成 → 审核 → 修复完整流程

```
makedata/
├── package.json
├── tsconfig.json
├── README.md             # 用户文档（面向飞书粘贴）
├── src/
│   ├── index.ts              # 主出口，导出所有模块
│   ├── core/
│   │   └── tag-tree.ts       # TagTree 类（树操作、可视化）
│   │
│   ├── generation/           # 数据生成模块
│   │   ├── index.ts          # 导出 generation 模块
│   │   ├── prompt-templates.ts            # 集中管理所有 Prompt 模板和专家角色定义
│   │   ├── scenario-planner.ts            # generateScenarioPlan() - Plan 生成（不含 patterns）
│   │   ├── scenario-pattern-generator.ts  # generateScenarioPatterns() - 独立 Pattern 生成
│   │   ├── scenario-core.ts               # generateScenarios() - 场景生成主入口（并发优化）
│   │   ├── scenario-generator.ts          # generateAndRefineBatch() - 底层场景生成+审核+修复
│   │   ├── scenario-audit.ts              # auditScenarios(), fixScenariosByAudit() - 场景审核修复
│   │   ├── scenario-judge.ts              # judgeScenarioCoverage(), detectDuplicateScenarios() - Judge 评估
│   │   ├── case.ts                        # generateCasesFromScenarios(), generateAndRefineCases() - 用例生成
│   │   └── case-judge.ts                  # judgeCaseGeneration() - 用例生成进度判别
│   │
│   ├── audit/                # 用例审核修复模块
│   │   ├── index.ts          # 导出 audit 模块
│   │   ├── validation.ts     # 程序化校验（Schema/交互链/标签）
│   │   ├── audit.ts          # auditOneCase(), auditCases() - 用例审核（含程序化预检查）
│   │   └── fix.ts            # fixCaseOnce(), fixCaseLoop(), fixCasesByAudit() - 用例修复
│   │
│   ├── principles/           # 原则文档
│   │   ├── index.ts          # 加载原则文件的函数
│   │   ├── writing.md        # 用例编写原则
│   │   ├── key-constraints.md # 关键约束（K0-K6，硬性规则）
│   │   ├── audit.md          # 审核原则
│   │   ├── composite-skill.md # 复合用例技能
│   │   └── audit-supplements.md # 审核补充说明
│   │
│   └── simple_run/           # 调试运行脚本（非核心逻辑）
│       ├── full-pipeline.ts  # 完整流水线调试：Query → Plan → Patterns → 场景 → 用例
│       ├── planner.ts        # Planner 调试：Query → Plan → Patterns
│       └── scenario.ts       # 场景生成调试
│
├── examples/
│   └── data/
│       └── vehicle-tag-tree.json      # 示例标签树数据（181 个叶子标签）
│
└── tests/                    # 测试文件（双模式：Mock + Real LLM）
    ├── test-utils.ts                      # 测试工具（Mock Client、数据构建器、RUN_REAL_LLM 开关）
    ├── index.test.ts                      # 主出口导出测试
    ├── tag-tree.test.ts                   # TagTree 核心功能测试
    ├── principles.test.ts                 # 原则加载测试
    ├── validation.test.ts                 # 程序化校验测试
    ├── pattern-driven.test.ts             # Pattern 驱动逻辑测试
    ├── scenario-planner.test.ts           # Planner 测试（Mock + Real LLM + CLI 调试）
    ├── scenario-pattern-generator.test.ts # Pattern Generator 测试（Mock + Real LLM）
    ├── generation.test.ts                 # 场景/用例生成测试（Mock + Real LLM）
    ├── audit.test.ts                      # 审核/修复测试（Mock + Real LLM）
    ├── integration.test.ts                # 集成测试（Mock + Real LLM）
    ├── e2e-debug.test.ts                  # 端到端调试测试（Real LLM 专用）
    ├── e2e-debug.ts                       # 端到端调试脚本（CLI 直接运行）
    └── scenario-planner-debug.ts          # Planner CLI 调试脚本
```

#### 数据合成流程（Plan → Pattern → 场景 → 用例）

```
Query + 标签树
    │
    ▼
[1] generateScenarioPlan()          → Plan（task_description, target_tags, interpretation_notes）
    │                                 ※ Plan 
    ▼
[2] generateScenarioPatterns(plan)  → { patterns, targetScenarioCount }
    │                                 ※ 独立生成，基于 Plan 派生
    │                                 ※ targetScenarioCount = max(10, patterns.length, tags×2)
    ▼
[3] generateScenarios(query, tagTree, { plan, patterns })
    │
    ├── 阶段1: Pattern 并发巡游（p-limit 25 并发）
    │   └── 每个 pattern 生成 3-5 个场景 → 审核 → 修复
    │       └── 程序化初筛 → LLM 深度审核 → 自动修复
    │
    ├── 阶段2: Judge 全局驱动深化
    │   └── Judge 评估覆盖度 → 指导下一轮生成 → 去重 → 循环
    │
    └── 停止条件: patterns 全覆盖 AND (标签全覆盖 OR Judge满意)
        ※ targetScenarioCount 不再是停止的必要条件，仅用于安全阀和进度展示
    │
    ▼
Scenario[]（每个场景携带 pattern 字段）
    │
    ▼
[4] generateAndRefineCases(scenarios, n, ...)
    └── 生成 → 审核 → 修复 → 循环直到达标
    │
    ▼
Case[]（DatasetItem 格式，合并到数据集）
```

#### 关键设计决策

| 决策 | 说明 |
|------|------|
| **Plan 和 Pattern 分离** | Plan 只描述"测什么"，Pattern 独立生成作为"执行蓝图"，降低用户认知负担 |
| **Pattern 并发生成** | 阶段1使用 p-limit 控制 25 并发，峰值 LLM 调用约 40（豆包限制 50） |
| **程序化初筛** | LLM 审核前先用代码快速剔除标签非叶子、字段缺失等明显问题 |
| **targetScenarioCount 归属** | 由 Pattern Generator 计算，仅用于安全阀和进度展示，不持久化到 Plan |
| **Scenario.pattern 字段** | 每个场景记录所属 pattern，前端可展示和筛选 |
| **LLMScenarioSchema** | LLM 输出专用 Schema（不含 pattern），避免 OpenAI strict mode 报错 |
| **Prompt 模板化** | 专家角色、思维框架、输出标准集中管理在 prompt-templates.ts |

#### 并发参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `patternLimit` | 25 | Pattern 并发处理数 |
| `initialBatchSize` | 25 | 每批次生成场景数 |
| `auditConcurrency` | 35 | 审核 LLM 并发 |
| `fixConcurrency` | 20 | 修复 LLM 并发 |
| 峰值并发 | ~40 | 在豆包 50 并发限制内 |

#### 双模式测试体系

| 模式 | 命令 | 说明 | 耗时 |
|------|------|------|------|
| **Mock 模式** | `pnpm test` | `createMockClient()` 模拟 LLM，快速验证代码逻辑 | ~2 秒 |
| **Real LLM 模式** | `pnpm test:real` | 真实调用 LLM，跑通完整功能流程 | 数分钟~数十分钟 |

**Mock Client** (`test-utils.ts`):
- 根据 `text.format.json_schema.name` 分发预定义响应
- 支持 11 种 format name（planner_output, pattern_output, scenario_list, audit_result 等）
- 可配置 `defaultScenarioCount`、`defaultAuditPass`、自定义响应覆盖

**测试覆盖**:

| 测试文件 | Mock 测试 | Real LLM 测试 | 覆盖内容 |
|----------|-----------|---------------|----------|
| `index.test.ts` | 5 | - | 主出口导出验证 |
| `tag-tree.test.ts` | 29 | - | TagTree 类功能 |
| `principles.test.ts` | 3 | - | 原则文档加载 |
| `validation.test.ts` | 17 | - | 程序化校验 |
| `pattern-driven.test.ts` | 14 | 1 | Pattern 驱动逻辑 + Plan 校验 |
| `scenario-planner.test.ts` | 2 | 5 | Plan 生成（不含 patterns） |
| `scenario-pattern-generator.test.ts` | 2 | 2 | Pattern 生成 |
| `generation.test.ts` | 10 | 7 | 场景生成 + 用例生成 |
| `audit.test.ts` | 22 | 6 | 审核/修复 |
| `integration.test.ts` | 2 | 3 | 完整链路集成 |
| `e2e-debug.test.ts` | - | 1 | 端到端调试（90 分钟超时） |

运行测试:
```bash
cd platform/packages/makedata

# Mock 模式（快速，不调用 LLM）
pnpm test

# Real LLM 模式（需配置 API key）
pnpm test:real

# 运行特定测试文件
pnpm test tests/generation.test.ts

# 监听模式
pnpm test:watch

# CLI 调试脚本
pnpm tsx tests/e2e-debug.ts
pnpm tsx tests/scenario-planner-debug.ts
```

---

### 5.4 @eval-platform/evaluation（评测逻辑）

**用途**: Agent 评测核心逻辑

```
evaluation/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts
│   ├── core/
│   │   ├── evaluator.ts      # 评测器
│   │   ├── judge.ts          # 评判逻辑
│   │   └── hints.ts          # 评测提示
│   ├── adaptors/
│   │   ├── agent-v1.ts       # Agent V1 适配器
│   │   └── base.ts           # 基础适配器
│   ├── experiments/          # 实验模块
│   │   ├── fake_person/
│   │   ├── virtual_car/
│   │   ├── virtual_environment/
│   │   ├── script_events/
│   │   └── tag_tree/
│   ├── request/
│   │   ├── https.ts          # HTTPS 请求
│   │   └── sse.ts            # Server-Sent Events
│   └── tests/
```

**核心功能**:

| 功能 | 说明 | 使用场景 |
|------|------|----------|
| **评测执行** | `Evaluator.evaluate()` 执行单条用例评测 | 运行测试用例并收集结果 |
| **评判逻辑** | `Judge` 评判助手输出是否符合预期 | 基于 nl_assertion 判定通过/失败 |
| **Agent 适配** | `AgentV1Adaptor` 适配不同 Agent 接口 | 支持多种 Agent 实现 |
| **虚拟环境** | `VirtualCar/VirtualEnvironment` 模拟车机和环境 | 无实车情况下的功能测试 |
| **请求处理** | HTTPS/SSE 请求封装 | 与 Agent 服务端通信 |
| **实验模块** | `FakePerson` 等实验性功能 | 模拟人类测试员行为 |

---

### 5.5 @eval-platform/shared（公共库）

**用途**: 所有包共享的工具函数和类型

```
shared/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts              # 主出口
│   ├── logger.ts             # Pino 日志封装
│   ├── interfaces/           # 公共接口
│   ├── constants/            # 常量
│   └── utils/                # 工具函数
│       ├── date.ts           # 日期处理
│       ├── id.ts             # ID 生成
│       ├── validation.ts     # 验证工具
│       └── nl_repr.ts        # 自然语言表示
```

---

## 6. 数据模型关系

> **说明**：以下只列出业务字段（继承自 BaseDocument 的 `_id`, `createdAt`, `updatedAt` 通用字段未列出）

### 6.1 模型层次

```
BaseDocument (abstract)
  ├── _id: ObjectId
  ├── createdAt: Date
  └── updatedAt: Date
      ↑
      │ 继承
┌─────┴──────────────────────────────────────────────────────┐
│                        Dataset                               │
│                    (complex_reasoning_dataset)              │
│  业务字段:                                                    │
│  - name: string              # 数据集名称（必填）              │
│  - description?: string      # 描述（可选）                   │
│  - item_count: number        # 用例数量（自动计算）           │
└───────────────┬─────────────────────────────────────────────┘
                │ 1
                │ 外键关联
                │ N
┌───────────────▼─────────────────────────────────────────────┐
│                     DatasetItem                              │
│                    (complex_reasoning_case)                 │
│  业务字段:                                                    │
│  - dataset_id: ObjectId      # 所属数据集ID（外键）          │
│  - case_id: string           # 用例唯一标识（必填）           │
│  - context_config: object    # 上下文配置                    │
│  - max_round: number         # 最大对话轮数                  │
│  - user_query_lists: Array   # 多次独立会话列表              │
│  - expected_script: string   # 预期对话脚本                  │
│  - nl_assertion: string[]    # 自然语言断言                  │
│  - case_description?: string # 用例描述（可选）              │
│  - code_assertion?: object   # 代码断言（可选）              │
│  - tags: string[]            # 标签列表                      │
│  - source_scenario_id?: string  # 来源场景ID（可选）         │
│  - source_scenario_name?: string # 来源场景名（可选）        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      TagTree                                 │
│                      (tag_tree)                              │
│  业务字段:                                                    │
│  - name: string (unique)     # 标签树名称（唯一）            │
│  - description?: string      # 描述（可选）                  │
│  - tree: object              # 完整标签树 JSON              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      Scenario                                │
│                      (scenario)                              │
│  业务字段:                                                    │
│  - scenario_id: string (unique) # 场景ID（业务唯一）         │
│  - scenario_name: string     # 场景名称                      │
│  - description: string       # 场景描述                      │
│  - tags: string[]            # 关联标签                      │
│  - pattern?: string          # 归属的场景模式（可选）        │
│  - tag_tree_id?: ObjectId    # 关联的标签树ID（可选）        │
│  - source_query?: string     # 来源query（可选）             │
│  - scenario_plan_id?: ObjectId # 关联的Plan ID（可选）       │
│  - generation_task_id?: ObjectId # 关联的生成任务ID（可选）  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    ScenarioPlan                              │
│                    (scenario_plan)                           │
│  业务字段:                                                    │
│  - plan_id: string (unique)  # Plan ID（业务唯一）           │
│  - task_id: ObjectId         # 关联的生成任务ID              │
│  - generation_task_run_id: ObjectId # 关联的运行记录ID       │
│  - original_query: string    # 原始用户查询                  │
│  - task_description: string  # 详细任务描述                  │
│  - target_tags: string[]     # 目标覆盖标签列表              │
│  - interpretation_notes: string # 需求理解注解               │
│  - status: enum              # pending/confirmed/generating/ │
│  │                           #   completed/cancelled         │
│  - tag_tree_name: string     # 关联的标签树名称              │
│  ※ 不含 scenario_patterns                                 │
│    （由 Pattern Generator 在场景生成阶段产出）               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   GenerationTask                             │
│                   (generation_task)                          │
│  业务字段:                                                    │
│  - name: string              # 任务名称                      │
│  - description?: string      # 描述（可选）                  │
│  - creator: string           # 创建者                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                 GenerationTaskRun                            │
│                 (generation_task_run)                        │
│  业务字段:                                                    │
│  - generation_task_id: ObjectId # 关联的生成任务ID           │
│  - query: string             # 查询描述                      │
│  - tag_tree_id: ObjectId     # 使用的标签树ID                │
│  - status: enum              # pending/running/completed/    │
│  │                           #   failed/cancelled            │
│  - progress?: number         # 进度百分比                    │
│  - events: Array             # SSE 事件记录                  │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 关键关系说明

| 关联 | 关系类型 | 说明 |
|------|----------|------|
| Dataset → DatasetItem | 1:N | 一个数据集包含多个用例，级联删除 |
| ScenarioPlan → Scenario | 1:N | 一个 Plan 生成多个场景（通过 generation_task_run_id 关联） |
| Scenario → DatasetItem | 1:N | 一个场景派生多个用例变体（通过 source_scenario_id 关联） |
| TagTree → Scenario | 1:N | 一个标签树下有多个场景（通过 tag_tree_id 关联） |
| GenerationTask → GenerationTaskRun | 1:N | 一个任务可多次运行 |
| GenerationTaskRun → ScenarioPlan | 1:1 | 每次运行对应一个 Plan |

### 6.3 字段说明

| 符号 | 含义 |
|------|------|
| `?:` | 可选字段（Optional） |
| `(FK)` | 外键关联 |
| `(unique)` | 唯一索引 |
| `(auto)` | 自动计算/生成 |

---

## 7. API 路由结构

### 7.1 现有路由

```
GET    /health                            # 健康检查

# 数据集管理
/api/complex_reasoning_dataset
  GET    /list, /page, /:id
  POST   /, PUT /:id, DELETE /:id

# 用例管理
/api/complex_reasoning_case
  GET    /list, /page, /:id
  POST   /, PUT /:id, DELETE /:id

# 标签树管理
/api/tag-tree
  GET    /list, /:id/preview, /:id/export
  POST   /, DELETE /:id

# 场景管理
/api/scenario-management
  GET    /list, /page, /:id
  POST   /, PUT /:id, DELETE /:id
  GET    /:id/cases              # 按场景查用例

# 场景生成计划
/api/scenario-planning
  POST   /generate               # 生成 Plan（不含 patterns）
  GET    /:id, /list
  PUT    /:id                    # 确认/取消 Plan

# 场景生成（同步 + 流式）
/api/scenario-generation
  POST   /                       # 同步生成
/api/scenario-generation-stream
  POST   /                       # SSE 流式生成（含 patterns 事件）
  POST   /cancel                 # 取消生成

# 用例生成（同步 + 流式）
/api/case-generation
  POST   /                       # 同步生成
/api/case-generation-stream
  POST   /                       # SSE 流式生成

# 生成任务管理
/api/generation-task
  GET    /list, /page, /:id
  POST   /, PUT /:id, DELETE /:id

/api/generation-task-run
  GET    /list, /page, /:id
  POST   /, PUT /:id, DELETE /:id
```

### 7.2 SSE 事件类型

**场景生成流**:
| 事件 | 数据 | 说明 |
|------|------|------|
| `plan` | Plan 基本信息 | 开始生成前 |
| `patterns` | `string[]` | Pattern 生成完成 |
| `scenario` | Scenario 对象 | 每生成一个场景 |
| `progress` | 进度信息 | 每轮迭代 |
| `complete` | 最终统计 | 生成完成 |
| `error` | 错误信息 | 异常时 |

**用例生成流**:
| 事件 | 数据 | 说明 |
|------|------|------|
| `case` | Case 对象 | 每生成一个用例 |
| `progress` | 进度信息 | 审核修复进度 |
| `complete` | 最终统计 | 生成完成 |
| `error` | 错误信息 | 异常时 |

---

## 8. 开发工作流

### 8.1 常用命令

```bash
# 安装依赖
pnpm install

# 开发模式
pnpm dev              # 启动所有 watch
pnpm dev:backend      # 仅 backend

# 类型检查
pnpm typecheck        # 全部
pnpm typecheck:packages # 仅 packages

# 构建
pnpm build            # 全部
pnpm build:packages   # 仅 packages

# 测试（makedata 双模式）
cd platform/packages/makedata
pnpm test             # Mock 模式（快速，~2s）
pnpm test:real        # Real LLM 模式（需 API key）
pnpm test:watch       # 监听模式

# 代码质量
pnpm lint
pnpm format
```

### 8.2 添加新 Package

1. 在 `packages/` 创建目录
2. 创建 `package.json`，设置 `"name": "@eval-platform/xxx"`
3. 创建 `tsconfig.json`，继承根配置
4. 在 `pnpm-workspace.yaml` 确认已包含 `packages/*`
5. 运行 `pnpm install`

### 8.3 添加新 API 路由

1. 在 `apps/backend/src/api/routes/` 创建 `.ts` 文件
2. 导出 `prefix` 常量定义子路径
3. 导出 `xxxRoutes` Fastify 插件
4. 遵循现有模式：list/page/get/create/update/delete
5. 使用 Zod Schema 进行参数验证

---

## 9. 技术决策记录

| 决策 | 原因 |
|------|------|
| pnpm workspace | 高效的磁盘利用，严格的依赖管理 |
| Turborepo | 构建管道优化，任务并行化 |
| Typegoose + Mongoose | TypeScript 装饰器简化 MongoDB Schema 定义 |
| Zod | 运行时类型验证 + TypeScript 类型推导 |
| Fastify + Zod Type Provider | 类型安全的 API 路由 |
| Doubao 模型 | 字节跳动中文大模型，适合车载助手场景 |
| ESM 模块 | Node.js 现代标准 |
| Plan/Pattern 分离 | 降低用户认知负担，Plan 只描述需求，Pattern 独立生成 |
| Pattern 并发生成 | p-limit 控制 25 并发，提速 2-3 倍 |
| 程序化初筛 | LLM 审核前用代码快速剔除明显问题，减少 30-50% LLM 调用 |
| target 降级 | 不再作为停止必要条件，不限制 LLM 想象力，仅用于安全阀 |
| LLMScenarioSchema | LLM 输出专用 Schema（不含 pattern），兼容 OpenAI strict mode |
| 双模式测试 | Mock 模式快速验证逻辑，Real LLM 模式跑通功能 |

---

## 10. 注意事项

1. **数据库连接**: 启动 backend 前确保 MongoDB 在 `127.0.0.1:27017` 运行
2. **LLM API Key**: 需配置 `DOUBAO_API_KEY` 或 `OPENAI_API_KEY` 环境变量
3. **LLM 并发限制**: 豆包 API 并发限制 50，系统峰值约 40
4. **开发模式**: packages 通过 `development` 条件直接导出 `src/`，无需频繁构建
5. **类型检查**: 提交前务必运行 `pnpm typecheck` 确保无类型错误
6. **日志位置**: `logs/` 目录按日期自动生成日志文件
7. **测试模式**: 默认 `pnpm test` 运行 Mock 模式（不调用 LLM），`pnpm test:real` 运行 Real LLM 模式

---

**文档维护**: 本文件路径 `platform/PROJECT_STRUCTURE.md`
**最后更新**: 2026-07-06
