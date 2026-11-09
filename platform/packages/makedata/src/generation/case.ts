/**
 * 用例生成 - 基于场景列表生成具体测试用例
 *
 * 输入：Scenario[] + n（每个场景生成几个 case）
 * 输出：Case[]（遵循 DatasetItemSchema）
 */

import { OpenAI, zodTextFormat, invokeWithRetry } from '@eval-platform/llm'
import { CaseWithScenarioSchema, type CaseWithScenario, type DialogueRoundConfig } from '@eval-platform/database'
import type { Scenario } from '@eval-platform/database/models/scenario'
import pLimit from 'p-limit'
import type { CaseAuditResult, FixedCaseResult } from '@eval-platform/database/models/case-audit'
import type { TagTree } from '../core/tag-tree.js'
import { loadWritingPrinciples, loadKeyConstraints } from '../principles/index.js'
import { z } from 'zod'
import { getGenerationTemplate } from './prompt-templates.js'

// ═══════════════════════════════════════════════════════════════════════════
// LLM 输出专用 Schema
// 使用统一的 DialogueRoundConfig（mock_time/mock_info 可选），避免 z.union 导致
// OpenAI strict mode 兼容问题。后处理时将不需要时间/条件的轮次简化为纯消息数组。
// ═══════════════════════════════════════════════════════════════════════════

const LLMMessageSchema = z.object({
  role: z.enum(['user', 'assistant', 'system']),
  content: z.string(),
})

const LLMDialogueRoundSchema = z.object({
  user_query_list: z.array(LLMMessageSchema).min(1),
  mock_info: z.record(z.string(), z.unknown()).default({}),
  mock_time: z.string().nullable().optional(),
})

const LLMCaseSchema = z.object({
  dataset_id: z.string().min(1),
  case_id: z.string().min(1),
  context_config: z.record(z.string(), z.unknown()).default({}),
  max_round: z.coerce.number().int().positive().default(1),
  user_query_lists: z.array(LLMDialogueRoundSchema).min(1),
  expected_script: z.string().default(''),
  nl_assertion: z.array(z.string()).default([]),
  case_description: z.string().default(''),
  tags: z.array(z.string()).default([]),
  source_scenario_id: z.string().min(1),
  source_scenario_name: z.string().min(1),
})

const LLMCaseListSchema = z.object({
  cases: z.array(LLMCaseSchema).min(1, '至少需要一个用例'),
})

const caseListJsonSchema = zodTextFormat(LLMCaseListSchema, 'case_list')

const CASE_LIST_SCHEMA: OpenAI.Responses.ResponseTextConfig = {
  format: caseListJsonSchema,
}

/**
 * 后处理：将 LLM 输出的统一 DialogueRoundConfig 格式简化
 *
 * 规则：
 * - 如果 mock_time 为 null/undefined 且 mock_info 为空对象 {}，
 *   则简化为纯消息数组形式（减少存储冗余）
 * - 否则保留 DialogueRoundConfig 形式
 *
 * 导出供外部（如 e2e-debug、后端 API）使用
 */
export function simplifyUserQueryLists(cases: CaseWithScenario[]): CaseWithScenario[] {
  return cases.map(c => {
    const simplifiedLists = c.user_query_lists.map(session => {
      if (Array.isArray(session)) {
        // 已经是简单数组形式，保持不变
        return session
      }
      // DialogueRoundConfig 形式
      const round = session as DialogueRoundConfig
      const hasMockTime = round.mock_time != null && round.mock_time !== ''
      const hasMockInfo = round.mock_info && Object.keys(round.mock_info).length > 0

      if (!hasMockTime && !hasMockInfo) {
        // 不需要时间/条件，简化为纯消息数组
        return round.user_query_list
      }
      // 保留 DialogueRoundConfig
      return round
    })

    return { ...c, user_query_lists: simplifiedLists }
  })
}

/**
 * 构建同场景多用例一次性生成的 Prompt
 *
 * 设计：一次让 LLM 生成同一场景下的全部 N 个用例，
 * 使其能在命名、台词、描述上做协同差异化。
 */
async function buildCasesForScenarioPrompt(
  scenario: Scenario,
  count: number,
  tagTree?: TagTree,
  priorCasesSummary?: { case_id: string; oneLiner: string }[]
): Promise<string> {
  const principles = await loadWritingPrinciples()
  const keyConstraints = await loadKeyConstraints()
  const expertBase = getGenerationTemplate()

  // 提取场景标签的 description（含示例）作为生成参考
  let tagDescriptionsSection = ''
  if (tagTree) {
    const tagDescs: string[] = []
    for (const tagName of scenario.tags) {
      try {
        const node = tagTree.getNodeByName(tagName)
        if (node.description) {
          tagDescs.push(`### ${tagName}\n${node.description}`)
        }
      } catch {
        // 节点不存在则跳过
      }
    }
    if (tagDescs.length > 0) {
      tagDescriptionsSection = `
## 📋 场景标签详解（含示例，生成时必须参考）

以下是本场景涉及标签的详细说明和示例。生成用例时，**必须参考这些描述中的"属于""不属于""示例对话"来确保用例内容与标签定义一致**：

${tagDescs.join('\n\n')}
`
    }
  }

  // 已生成用例的弱协同提示（分批/补充生成时使用）
  let priorCasesSection = ''
  if (priorCasesSummary && priorCasesSummary.length > 0) {
    priorCasesSection = `
## ⚠️ 已生成的同场景用例（必须避开，做差异化协同）

以下是该场景下已生成的用例（可能来自之前的批次或补充生成轮次）。**新用例必须与它们在测试点、首轮台词、case_id 命名上明显不同**——不仅是字面不同，而是测的"那一件事"必须不同：

${priorCasesSummary.map((p, i) => `${i + 1}. 「${p.case_id}」— ${p.oneLiner}`).join('\n')}

**硬性要求**：不要重复上述用例已覆盖的测试点（如已测"整体行程规划"就不要再生成"X日行程规划"，已测"沿途住宿筛选"就不要再生成"沿途特色住宿"）。请从全新的角度切入（不同的子任务、不同的约束维度、不同的用户画像、不同的异常分支等）。
`
  }

  return `${expertBase}

现在，你需要基于你的专家经验，**一次性为同一个场景生成 ${count} 个高质量的测试用例**。

## 🚨 关键约束（必须严格遵守，违反则 case 无效）

${keyConstraints || '【关键约束文件加载失败，请参考完整原则】'}

### 额外强调：用户台词中的具体信息必须真实可读出

- \`user_query_lists\` 和 \`expected_script\` 中的 \`用户：\` 行是演员要照读给 TTS 的台词，**绝对禁止**出现 \`XX\`、\`某\`、\`某某\`、\`待定\`、\`未知\` 等占位符
- 地址、地名、路名、小区名、店名、歌曲名等必须写成真实可读的具体的值（如「导航到南京西路1266号」「我家改成陆家嘴花园石桥路」「播放周杰伦的晴天」）
- TTS 会把「XX路」读成「叉叉路」，导致 case 失去评测意义，这是硬性错误
${tagDescriptionsSection}${priorCasesSection}
## 场景信息

**场景 ID**: ${scenario.scenario_id}
**场景名称**: ${scenario.scenario_name}
**场景描述**: ${scenario.description}
**场景标签**: ${scenario.tags.join(', ')}

## 同场景多用例协同规范（核心！本批 ${count} 个用例必须协同设计）

你正在一次性生成 ${count} 个用例，它们都基于同一个场景，但必须是**互不雷同、各有侧重**的高质量用例。请严格遵守以下协同规范：

### 1. case_id 命名规范（重要！）
- **10字左右的精炼描述性命名**，能让人一眼看出这个用例具体测什么
- ✅ 好的命名示例：「周董别名点播周杰伦」「行驶中请求开门被拒」「跨会话记忆空调偏好」
- ❌ 禁止使用「变体1」「变体2」「用例1」「用例2」「${scenario.scenario_name}-1」等**无信息量的编号命名**
- ❌ 禁止用场景名直接当 case_id（因为同场景多个用例会重名）
- ${count} 个用例的 case_id 必须**互不相同**

### 2. user_query_lists 首轮台词多样性（重要！）
${count} 个用例的冷启动首轮 user_query **表达方式必须互不相同**，在保持语义与场景一致的前提下，从以下维度做差异化：
- 口语风格 vs 正式 vs 简洁 vs 带语气词 vs 带上下文铺垫
- 不同的具体对象（歌手名、温度值、地点等）
- 不同的句式（祈使句、疑问句、省略句）
- **禁止 ${count} 个用例的首轮台词只换个别名词而句式雷同**

### 3. case_description 差异点说明（重要！）
每个 case_description 在描述测试目的后，**必须明确点出本用例与同场景其他用例的具体差异点**，格式：
"…。**本用例区别于同场景其他用例：**侧重于 XX，而其他用例分别侧重 YY/ZZ。"

### 4. 测试点差异化
${count} 个用例应在以下维度分配不同的测试侧重点（不要每个用例都测同一件事）：
- 正常流程 vs 边界条件 vs 异常处理
- 单轮直达 vs 多轮澄清 vs 跨会话
- 显式意图 vs 隐式意图 vs 模糊意图
- 不同的驾驶情境（车速/道路/环境）
- 不同的用户画像（年轻/年长、急躁/从容）

## 用例编写原则（完整版参考）

${principles}

## 你的设计任务

基于你的专家思维框架，设计用例时请激活以下第一性原则：

### 1. 驾驶情境真实性（激活第一性原则）
- **物理情境**：车速、道路类型、环境条件是否真实合理？
- **生理状态**：驾驶员是否处于需要该功能的合理状态？
- **认知负荷**：该用例的交互设计是否符合驾驶中的认知限制？

### 2. 助手行为预期（应用安全判断原则）
- 该场景下助手的预期行为是否符合量产产品的行业惯例？
- 警惕"过度安全泛化"：不要将合理操作误判为需拒绝的危险操作
- 警惕"安全盲区"：真正需要拒绝/提醒的操作是否被正确识别？

### 3. 断言设计原则（可验证 vs 万能话）
- 每个断言是否能在对话中找到具体的核对点？
- 避免"助手应该正确理解"等无法验证的断言
- 产品功能类断言必须有明确的可核对结果（如"助手应将空调设为24°C"）
- **专家级要求**：断言应体现15年产品专家的判断标准

## 标签语义自审（输出前必须执行）

在最终确定每个用例的 tags 前，请逐条回顾所选标签的 description，问自己："这个标签的业务含义是否天然暗示了另一种标签或结构？"

**示例（不穷举）**：
- 选了"追问连续回答" → 它描述的是同一次对话内的追问，因此必须同时选"多轮对话"（如多轮对话_2到3轮），且 user_query_lists 只有 1 个 session。
- 选了记忆类标签（如常用地点记忆、长期记忆调用）→ 它描述的是跨会话记忆能力，通常需要"多次多轮"来形成"生产→消费"闭环。
- 选了"多轮对话" → 结构上必须是单 session，后续追问写在 expected_script 的"用户："行。
- 选了"多次多轮" → 结构上必须是多 session，user_query_lists 中有多个 session。

**动作**：检查当前标签组合是否存在"标签含义要求了某种结构，但组合里没体现"的情况。如果存在，请先调整 tags，再输出最终用例。不要依赖外部规则表，要靠对标签 description 的理解做常识推导。

## 输出要求

请生成 **${count} 个**测试用例，输出为 \`cases\` 数组，每个元素严格符合 DatasetItemSchema 结构：

### 1. **case_id**: 用例名称
10字左右的精炼描述性命名（详见"同场景多用例协同规范"第 1 条）

### 2. **context_config**: 上下文配置
- **只包含 car_info**：当前车辆及所处环境的客观状态，使用中文全角冒号分隔（键：值）
- **car_info 可包含**：车速、档位、道路类型、当前位置、电量/油量、续航、温度、胎压、天窗/空调状态、车况告警、车机屏幕状态、**当前日期时间**等
- **car_info 禁止包含**：用户需求、用户查询目标、目标对象属性（如目标车型用途/售价/参数）、用户所在地作为筛选条件、用户身份/角色等。这些都属于用户台词（\`user_query_lists\`），不应预先注入
- **专家级要求**：car_info 应体现真实驾驶情境（车速、档位、道路类型等）
- **⚠️ 当前日期时间一致性**：若场景涉及时效性信息（年度活动/季节性事件/赛事/政策时效/实时动态/某届展会/春运假期/天气预警等），**必须在 car_info 中加入 \`"当前日期时间": "YYYY-MM-DD HH:mm"\`** 作为整个 case 的时间基准；台词用相对时间表述（"今年""下周"），nl_assertion 中换算为具体年份/日期。**禁止**在 nl_assertion 中出现 car_info 或台词无法推出的具体年份/日期。详见《用例编写通用原则》§12b。

### 3. **max_round**: 最大对话轮数
根据复杂度设置（简单5-8，多会话8-14，规律类14-18）

### 4. **user_query_lists**: 多次独立会话列表 [重要！]
**类型**: 数组，每个元素是一个 **DialogueRoundConfig 对象**

#### ⚠️ mock_time / mock_info 判断规则（必须严格遵守）

**第一步：查看场景的 tags，判断是否属于以下特殊场景：**
- tags 包含「时间规律发现」→ 需要设置 mock_time（每轮不同时间）
- tags 包含「条件规律发现」或需要逐轮变化车况 → 需要设置 mock_info
- **以上都不满足 → mock_time 必须为 null，mock_info 必须为 {} （这是 90% 的情况！）**

---

#### 默认情况（90% 的场景）：mock_time = null，mock_info = {}
适用于：空调控制、导航、媒体播放、车窗控制、座椅调节等**绝大多数场景**。
- 车况信息统一放在 \`context_config.car_info\` 中，不放在 mock_info 里
- **绝对不要**为普通场景设置 mock_time
\`\`\`json
{
  "user_query_list": [{ "role": "user", "content": "空调调到24度" }],
  "mock_info": {},
  "mock_time": null
}
\`\`\`

#### 仅以下特殊场景才设置 mock_time 和/或 mock_info：

**特殊场景A：时间规律发现**（tags 含「时间规律发现」）
- 用户在**不同日期的同一时间**重复同一行为，助手识别规律后主动服务
- **每轮必须设置不同的 mock_time**（体现日期跨度，时间相同体现规律性）
- mock_info 仍为 {}
\`\`\`json
[
  { "user_query_list": [{ "role": "user", content: "空调调到24度" }],
    "mock_info": {}, "mock_time": "2024-01-15 08:30:00" },
  { "user_query_list": [{ "role": "user", content: "空调还是24度" }],
    "mock_info": {}, "mock_time": "2024-01-16 08:30:00" },
  { "user_query_list": [{ "role": "user", content: "照旧" }],
    "mock_info": {}, "mock_time": "2024-01-17 08:30:00" }
]
\`\`\`

**特殊场景B：条件规律发现**（需要逐轮变化车况）
- 不同轮次的车况条件不同（如"行驶中"vs"停车时"助手行为不同）
- **需要变化车况的轮次设置 mock_info.car_info**，不需要变化的轮次 mock_info 为 {}
- mock_time 通常为 null（除非同时涉及时间规律）
\`\`\`json
[
  { "user_query_list": [{ "role": "user", content: "打开后备箱" }],
    "mock_info": { "car_info": { "车速": "0km/h", "档位": "P档" } }, "mock_time": null },
  { "user_query_list": [{ "role": "user", content: "打开后备箱" }],
    "mock_info": { "car_info": { "车速": "60km/h", "档位": "D档" } }, "mock_time": null }
]
\`\`\`

**关键约束**：
- \`user_query_lists\` 是一个**数组**，每个元素是一个 DialogueRoundConfig **对象**
- 每个对象的 \`user_query_list\` 字段是一个**数组**，包含消息对象
- 每个消息对象必须有 \`role\` ("user" 或 "assistant") 和 \`content\`
- 冷启动语义：每项是一次独立对话，只取首条 user 消息
- 同会话后续轮次写在 expected_script
- **⚠️ 冷启动台词自然性**（详见《用例编写通用原则》§8.1）：冷启动台词必须是真人一口气会说出的话。允许并行多任务长句（"导航到公司，顺便放点轻音乐"）和带犹豫语气的自然改口（"导航到公司，噢不，导航到虹桥机场先"）；**禁止**单句内多次反复改变同一目标且无犹豫语气，像念任务清单（"导航到公司，先去虹桥机场，马上回公司，还有多久到？"）——这种多轮交互应拆为冷启动第一句 + expected_script 后续轮次
- **⚠️ 如果场景不属于时间规律发现或条件规律发现，mock_time 必须为 null，mock_info 必须为 {}。不要编造不必要的时间戳**

### 5. **expected_script**: 预期对话脚本
- 「用户：」后只能是口述台词
- 「管家：（...）」包含期望行为和评测重点
- **多轮场景必须展开为交替剧本**（详见《用例编写通用原则》§7）：涉及中途插话/取消/查询/改口/多任务并行等需要中途交互的标签时，必须逐轮写"用户：xxx 管家：（期望…）"的交替结构，不能只写一行概括
- **单次多轮不标"第N轮"**；**多次多轮用"（重启新的对话……）"分隔**（不要用"第一会话""第二会话"等标注）
- **⚠️ 剧本首句=冷启动台词（强制一致性）**：expected_script 的第一句"用户：xxx"必须与 user_query_lists 第一项的冷启动台词**逐字一致**（单次多轮场景）；多次多轮场景下，每个"（重启新的对话……）"分隔段的第一句"用户：xxx"必须与对应 user_query_lists 项的冷启动台词**逐字一致**。原因：执行器在冷启动阶段只会念 user_query_lists 的首条 user 消息给被测助手，剧本是给假人演绎后续轮次的依据——如果剧本首句与冷启动台词不一致，假人要么无所适从，要么会念错第一句导致与被测助手的实际接收输入对不上
- **可选：人设/规则前导段**（详见《用例编写通用原则》§7.3）：测"用户性格/行为模式""助手容错""应对策略""重试逻辑""唤醒词"等非固定台词场景时，可在 expected_script 开头加前导段（用户性格/应对策略/重试规则/环境约束等演绎规则），用空行与正文分隔。前导段只写"假人怎么演"，不写助手行为/判分点/架空前置。例：「你扮演一个急躁没耐心的用户，助手回复慢或没回应你会催。如果助手没说话，你可以重试最多2次，重试时换个说法。」空一行后接正文「用户：导航到公司 / 管家：（期望助手发起去公司的导航）/ 用户：怎么还没开始 / 管家：（期望助手反馈导航已启动）」
- **专家级要求**：脚本应体现对行业惯例的理解，应用安全判断原则，避免过度保守或过度开放

### 6. **nl_assertion**: 自然语言断言列表（2-5条）
- 每条只评助手一件事
- 面向导演，可从对话核对
- 产品功能类必须有可核对的具体结果
- 禁止万能废话（如"不得答非所问"）
- **专家级要求**：断言应体现15年产品专家的判断标准，应用第一性原则

### 7. **case_description**: 用例综合描述
描述该用例的测试目的，应体现专家级的产品洞察（使用中文），并按协同规范第 3 条点出与同场景其他用例的差异点

### 8. **tags**: 标签列表
必须全部来自场景的 tags（引用中文标签名称）

### 9. **source_scenario_id** / **source_scenario_name**
固定填 "${scenario.scenario_id}" / "${scenario.scenario_name}"

**【语言要求】所有内容必须使用中文输出**：
- **case_id**: 10字左右的中文精炼描述（如「周董别名点播周杰伦」）
- **case_description**: 用例综合描述，必须使用中文
- **expected_script**: 预期对话脚本，用户台词和管家评测说明必须使用中文
- **nl_assertion**: 自然语言断言列表，必须使用中文描述验证标准
- **user_query_lists**: 用户查询列表，用户台词必须使用中文

## 关键约束检查（每个用例都要自检）

- [ ] tags 全部来自场景标签列表
- [ ] user_query_lists 每项只有1条user消息
- [ ] 多会话场景的第2轮起写在 expected_script
- [ ] **expected_script 首句用户台词 = user_query_lists 第一项的冷启动台词（逐字一致）**；多次多轮场景每个"（重启新的对话……）"段的首句也必须等于对应 session 的冷启动台词
- [ ] **expected_script 后续轮次台词自然性**：expected_script 中每个"用户："行的台词必须像真人对车机说的话，禁止技术化/书面化/指令式表述（如"再问下当前座椅设置""查询当前任务状态""确认座椅模式""反馈剩余时间"）和机械组合"功能名+动作"（如"查询加油站信息"），应改为口语化表述（如"现在啥状态""调好了吗""还有多久到""加油站找到了吗"）（§8.1）
- [ ] **可选：人设前导段**（§7.3）：测"用户性格/行为模式""助手容错""应对策略""重试逻辑""唤醒词"等非固定台词场景时，可在 expected_script 开头加前导段。前导段只写演绎规则（用户性格/应对策略/重试规则/环境约束），不写助手行为/判分点/架空前置；前导段和正文用空行分隔
- [ ] 记忆类题型有生产→消费闭环
- [ ] **状态依赖型指令**（暂停/下一首/上一首/切歌/导航取消/导航改线等）必须先用一轮建立前置状态（播放某首歌、发起导航），再下达状态依赖指令，形成可复现闭环——禁止从未播放过任何歌曲却让用户直接说"暂停当前音乐"。**特别注意"取消之前的XX""查询刚才那个任务"等带定语引用前置任务的台词——被引用的任务必须在本 case 内真实建立过，禁止架空前置（§14b.2）**
- [ ] **任务持续性与可取消性**（详见《用例编写通用原则》§13b）：测"取消任务/询问任务进度/中途插话改任务/任务优先级调度"时，被操作的对象必须是**持续任务**（导航/搜索/播放/提醒），禁止用瞬间车控任务（开按摩/调空调/开车窗等）冒充可取消/可查询状态——这些瞬间任务下达即完成，无"正在执行"状态可查、无状态可取消
- [ ] nl_assertion 只评助手行为，不评用户台词
- [ ] car_info 使用「键：值」格式（中文冒号）
- [ ] **时间一致性**：若场景涉及时效性信息（年度活动/季节性事件/赛事/政策时效/实时动态等），car_info 必须含"当前日期时间"字段；nl_assertion 中的具体年份/日期必须能从 car_info 的"当前日期时间"或台词中推出，不得凭空出现
- [ ] **专家级合理性**：用例设计符合行业惯例和第一性原则
- [ ] **${count} 个用例的 case_id 互不相同，均为描述性命名**
- [ ] **${count} 个用例的首轮 user_query 表达方式互不相同**
- [ ] **每个 case_description 都点出了与同场景其他用例的差异点**
- [ ] **用户台词中无占位符**：地址/地名/路名/店名/歌曲名等具体信息均为真实可读的具体的值，无 \`XX\`/\`某\`/\`某某\`/\`待定\`/\`未知\`

请输出 \`cases\` 数组，长度为 ${count}。
`.trim()
}

/**
 * 基于单个场景生成多个用例（一次性生成，协同差异化）
 *
 * 设计：单次 LLM 调用生成同场景全部 N 个用例，
 * 使 LLM 能在命名、台词、描述上做协同差异化。
 * N 较大时分批，批间注入已生成用例摘要做弱协同。
 *
 * 补充生成（跨迭代轮次）时可通过 externalPriorCases 传入该场景已通过的 case 摘要，
 * 避免 LLM 重复生成与已有 case 雷同的用例。
 */
export async function generateCasesForScenario(
  scenario: Scenario,
  count: number,
  client: OpenAI,
  datasetId: string = 'generated',
  tagTree?: TagTree,
  onFirstCaseGenerated?: (caseItem: CaseWithScenario) => void | Promise<void>,
  /** 跨迭代轮次已生成的同场景 case（用于注入去重上下文，避免补充生成时与已有 case 雷同） */
  externalPriorCases?: CaseWithScenario[],
  signal?: AbortSignal
): Promise<CaseWithScenario[]> {
  console.log(`  为 ${scenario.scenario_id} 生成 ${count} 个用例（一次性协同生成）...`)
  if (externalPriorCases && externalPriorCases.length > 0) {
    console.log(`  [补充生成] 已有 ${externalPriorCases.length} 个同场景用例，将注入去重上下文`)
  }

  // 大批次分批：每批最多 4 个，避免单次输出 token 过大被截断
  const BATCH_SIZE = 4
  const batches: number[] = []
  for (let i = 0; i < count; i += BATCH_SIZE) {
    batches.push(Math.min(BATCH_SIZE, count - i))
  }

  const allCases: CaseWithScenario[] = []
  let firstCaseEmitted = false

  for (let bIdx = 0; bIdx < batches.length; bIdx++) {
    if (signal?.aborted) {
      console.log(`  [${scenario.scenario_id}] 已取消，停止后续批次生成`)
      break
    }
    const batchCount = batches[bIdx]

    // 合并去重上下文：跨迭代轮次的 externalPriorCases + 本轮已累积的 allCases
    const priorCandidates = [...(externalPriorCases || []), ...allCases]
    const priorCasesSummary = priorCandidates.length > 0
      ? priorCandidates.map(c => ({
          case_id: c.case_id,
          oneLiner: (c.case_description || '').slice(0, 60),
        }))
      : undefined

    console.log(`  [批次 ${bIdx + 1}/${batches.length}] 生成 ${batchCount} 个用例（累计已有 ${allCases.length} 个）...`)

    const prompt = await buildCasesForScenarioPrompt(scenario, batchCount, tagTree, priorCasesSummary)

    const params: OpenAI.Responses.ResponseCreateParamsNonStreaming = {
      instructions: prompt,
      input: `请为场景 "${scenario.scenario_name}" 一次性生成 ${batchCount} 个互不雷同的测试用例，输出为 cases 数组`,
      text: CASE_LIST_SCHEMA,
      temperature: 0.8,
    }

    try {
      const result = await invokeWithRetry<{ cases: Partial<CaseWithScenario>[] }>(client, params, 3, signal)

      if (!result.cases || result.cases.length === 0) {
        console.warn(`  警告: ${scenario.scenario_id} 批次 ${bIdx + 1} 解析失败`)
        continue
      }

      // 补全元数据 + fallback 命名（不使用"变体N"）
      let fallbackIdx = allCases.length + 1
      for (const rawCase of result.cases) {
        const caseWithMeta: CaseWithScenario = {
          dataset_id: datasetId,
          case_id: rawCase.case_id || `${scenario.scenario_name}-${fallbackIdx}`,
          context_config: rawCase.context_config || {},
          max_round: rawCase.max_round || 8,
          user_query_lists: rawCase.user_query_lists || [],
          expected_script: rawCase.expected_script || '',
          nl_assertion: rawCase.nl_assertion || [],
          code_assertion: rawCase.code_assertion,
          case_description: rawCase.case_description || scenario.description,
          tags: rawCase.tags || scenario.tags,
          source_scenario_id: scenario.scenario_id,
          source_scenario_name: scenario.scenario_name,
        }
        allCases.push(caseWithMeta)
        if (!firstCaseEmitted && onFirstCaseGenerated) {
          firstCaseEmitted = true
          await onFirstCaseGenerated(caseWithMeta)
        }
        fallbackIdx++
      }

      console.log(`  ✓ 批次 ${bIdx + 1} 完成，本批 ${result.cases.length} 个，累计 ${allCases.length} 个`)
    } catch (error) {
      console.warn(`  警告: ${scenario.scenario_id} 批次 ${bIdx + 1} 生成失败（重试3次后仍失败）: ${(error as Error).message}`)
    }
  }

  // 截断到目标数量（LLM 可能多输出）
  const trimmed = allCases.slice(0, count)

  // 后处理：将不需要时间/条件的轮次简化为纯消息数组
  return simplifyUserQueryLists(trimmed)
}

/**
 * 基于场景列表批量生成测试用例
 *
 * @param scenarios - 场景信息列表
 * @param casesPerScenario - 每个场景生成的用例数量
 * @param client - OpenAI 客户端
 * @param datasetId - 数据集 ID
 * @returns 用例列表（含来源场景信息）
 */
export async function generateCasesFromScenarios(
  scenarios: Scenario[],
  casesPerScenario: number,
  client: OpenAI,
  datasetId: string = 'generated',
  tagTree?: TagTree
): Promise<CaseWithScenario[]> {
  console.log(`[generateCasesFromScenarios] 开始生成用例（并发）`)
  console.log(`  场景数量: ${scenarios.length}`)
  console.log(`  每场景用例数: ${casesPerScenario}`)
  console.log(`  预计总用例数: ${scenarios.length * casesPerScenario}`)
  console.log(`  场景并发数: 10`)
  console.log()

  // 场景级并发：同时处理 10 个场景
  const scenarioLimit = pLimit(10)
  let completedCount = 0

  const results = await Promise.all(
    scenarios.map((scenario, i) => scenarioLimit(async () => {
      console.log(`[${i + 1}/${scenarios.length}] 处理场景: ${scenario.scenario_id} (${scenario.scenario_name})`)

      try {
        const cases = await generateCasesForScenario(
          scenario,
          casesPerScenario,
          client,
          datasetId,
          tagTree
        )
        completedCount++
        console.log(`  ✅ [${completedCount}/${scenarios.length}] ${scenario.scenario_name}: ${cases.length} 个用例`)
        return cases
      } catch (error) {
        completedCount++
        console.error(`  ❌ [${completedCount}/${scenarios.length}] ${scenario.scenario_name}:`, error)
        return []
      }
    }))
  )

  const allCases = results.flat()

  console.log(`\n[generateCasesFromScenarios] 完成`)
  console.log(`  成功生成: ${allCases.length} / ${scenarios.length * casesPerScenario} 个用例`)

  return allCases
}

/**
 * 按场景ID分组用例
 */
export function groupCasesByScenario(cases: CaseWithScenario[]): Map<string, CaseWithScenario[]> {
  const groups = new Map<string, CaseWithScenario[]>()

  for (const caseItem of cases) {
    const scenarioId = caseItem.source_scenario_id
    if (!groups.has(scenarioId)) {
      groups.set(scenarioId, [])
    }
    groups.get(scenarioId)!.push(caseItem)
  }

  return groups
}

/**
 * 生成-审核-修复-判别-迭代完整流程
 *
 * 确保每个场景的合格用例数达到用户要求的数量。
 *
 * 流程：
 * 1. 第一轮：为所有场景生成用例
 * 2. 审核-修复循环（产出合格用例）
 * 3. Judge 判别：统计每个场景的合格用例数
 * 4. 如有场景不达标，只为这些场景补充生成
 * 5. 重复 2-4 直到达标或达到上限
 *
 * @param scenarios - 场景列表
 * @param casesPerScenario - 每个场景生成的用例数
 * @param tagTree - 标签树（用于审核）
 * @param client - LLM 客户端
 * @param auditCases - 审核函数
 * @param fixCasesByAudit - 修复函数
 * @param datasetId - 数据集 ID
 * @param options - 配置选项
 * @returns 审核通过的用例列表
 */
export async function generateAndRefineCases(
  scenarios: Scenario[],
  casesPerScenario: number,
  tagTree: TagTree,
  client: OpenAI,
  auditCases: (
    cases: CaseWithScenario[],
    tagTree: TagTree,
    client: OpenAI,
    options?: { concurrency?: number; onProgress?: (completed: number, total: number) => void; signal?: AbortSignal }
  ) => Promise<CaseAuditResult[]>,
  fixCasesByAudit: (
    cases: CaseWithScenario[],
    auditResults: CaseAuditResult[],
    tagTree: TagTree,
    client: OpenAI,
    auditOneCase: (caseItem: CaseWithScenario, tagTree: TagTree, client: OpenAI, signal?: AbortSignal) => Promise<CaseAuditResult>,
    options?: { maxRounds?: number; concurrency?: number; onProgress?: (completed: number, total: number) => void; signal?: AbortSignal }
  ) => Promise<FixedCaseResult[]>,
  datasetId: string = 'generated',
  options?: {
    maxIterations?: number
    maxRefineRoundsPerBatch?: number
    auditConcurrency?: number
    fixConcurrency?: number
    onProgress?: (info: {
      stage: 'generating' | 'auditing' | 'fixing' | 'completed'
      current: number
      total: number
      /** 当前阶段进度百分比 0-100 */
      progressPercentage: number
      /** 当前正在做什么的人话描述，可直接展示给用户 */
      currentStep: string
      /** 当前场景名（用例按场景逐个进行） */
      currentScenarioName?: string
    }) => void
    /** 流式回调：每当生成一个合格用例时调用 */
    onCaseGenerated?: (caseItem: CaseWithScenario, info: {
      scenarioId: string
      scenarioName: string
      iteration: number
      totalPassedCases: number
    }) => void | Promise<void>
    /** 取消信号，用于中断 LLM HTTP 请求 */
    signal?: AbortSignal
  }
): Promise<CaseWithScenario[]> {
  const {
    maxIterations = 5,
    maxRefineRoundsPerBatch = 2,
    auditConcurrency = 35,  // 豆包 API 峰值 40，用例阶段分配 35 给审核
    fixConcurrency = 20,    // 修复分配 20
    onProgress,
    onCaseGenerated,
    signal,
  } = options || {}

  console.log(`\n========================================`)
  console.log(`     用例生成启动（迭代流程）`)
  console.log(`========================================`)
  console.log(`  场景数: ${scenarios.length}`)
  console.log(`  每场景目标: ${casesPerScenario} 个用例`)
  console.log(`  目标总数: ${scenarios.length * casesPerScenario} 个用例`)
  console.log(`  最大迭代: ${maxIterations}`)
  console.log(`========================================\n`)

  const targetTotalCases = scenarios.length * casesPerScenario

  // 导入判别器和审核相关函数
  const { judgeCaseGeneration, printCaseCountReport } = await import('./case-judge.js')
  const { auditOneCase } = await import('../audit/index.js')

  // 进度计算（阶段制，保证单调递增）
  // 每次迭代占一部分进度，迭代内按完成场景数推进
  // 迭代1: 0% → 50%, 迭代2: 50% → 80%, 迭代3: 80% → 95%, 完成: 100%
  let maxProgress = 0
  function calcProgress(iteration: number, completedInIteration: number, totalInIteration: number): number {
    const iterRatio = iteration / maxIterations
    const iterStart = iterRatio <= 0.5 ? 0 : Math.round(iterRatio * 50) + (iteration - 1) * 15
    // 简化：每次迭代分配一个进度区间
    const phaseRanges: Array<[number, number]> = [
      [0, 50],   // 迭代1: 0-50%
      [50, 80],  // 迭代2: 50-80%
      [80, 95],  // 迭代3: 80-95%
      [95, 99],  // 迭代4+: 95-99%
    ]
    const [start, end] = phaseRanges[Math.min(iteration - 1, phaseRanges.length - 1)]
    const withinIter = totalInIteration > 0 ? completedInIteration / totalInIteration : 0
    const progress = Math.round(start + (end - start) * withinIter)
    maxProgress = Math.max(maxProgress, progress)
    return maxProgress
  }

  // 累计所有合格用例
  const allPassedCases: CaseWithScenario[] = []

  // 记录每个场景的已生成用例数（用于后续计算缺口）
  const scenarioCaseCount = new Map<string, number>()
  for (const scenario of scenarios) {
    scenarioCaseCount.set(scenario.scenario_id, 0)
  }

  // ========== 迭代生成循环 ==========
  for (let iteration = 1; iteration <= maxIterations; iteration++) {
    if (signal?.aborted) {
      console.log(`\n[generateAndRefineCases] 已取消，停止迭代`)
      break
    }
    console.log(`\n--- 迭代 ${iteration}/${maxIterations} ---`)

    // Judge 判别：统计当前每个场景的用例数
    const judgement = judgeCaseGeneration(allPassedCases, scenarios, casesPerScenario)
    printCaseCountReport(judgement)

    // 如果全部达标，结束循环
    if (judgement.satisfied) {
      console.log('✅ 所有场景的用例数已达标，迭代结束')
      break
    }

    // 准备为缺口场景补充生成
    const guidance = judgement.guidance!
    const scenariosToReplenish = guidance.scenariosToReplenish

    console.log(`\n  [补充生成] 为 ${scenariosToReplenish.length} 个场景并发生成 ${guidance.totalNeeded} 个用例`)

    // 构建需要处理的场景列表（每个场景及其缺口数量）
    const replenishmentTasks: Array<{
      scenario: Scenario
      needCount: number
    }> = []

    for (const item of scenariosToReplenish) {
      const scenario = scenarios.find(s => s.scenario_id === item.scenarioId)
      if (scenario) {
        replenishmentTasks.push({ scenario, needCount: item.needCount })
      }
    }

    // 场景级并发：同时处理 10 个场景的补充生成
    const replenishLimit = pLimit(10)
    let replenishCompleted = 0

    const replenishResults = await Promise.all(
      replenishmentTasks.map(({ scenario, needCount }, taskIdx) =>
        replenishLimit(async () => {
          if (signal?.aborted) {
            console.log(`\n    [场景 ${taskIdx + 1}/${replenishmentTasks.length}] 已取消，跳过`)
            return [] as CaseWithScenario[]
          }
          console.log(`\n    [场景 ${taskIdx + 1}/${replenishmentTasks.length}] ${scenario.scenario_name}: 需补充 ${needCount} 个`)

          // 推送生成阶段进度
          onProgress?.({
            stage: 'generating',
            current: allPassedCases.length,
            total: targetTotalCases,
            progressPercentage: calcProgress(iteration, replenishCompleted, replenishmentTasks.length),
            currentStep: `正在为"${scenario.scenario_name}"生成用例 (${taskIdx + 1}/${replenishmentTasks.length})`,
            currentScenarioName: scenario.scenario_name,
          })

          // 生成用例
          // 传入该场景已通过的 case 作为去重上下文，避免补充生成时与已有 case 雷同
          const existingScenarioCases = allPassedCases.filter(c => c.source_scenario_id === scenario.scenario_id)
          const newCases = await generateCasesForScenario(
            scenario, needCount, client, datasetId, tagTree,
            undefined, // 补充生成不需要 onFirstCaseGenerated 回调（流式输出在外层统一处理）
            existingScenarioCases,
            signal
          )
          console.log(`      [${scenario.scenario_name}] 生成: ${newCases.length} 个用例`)

          if (newCases.length === 0) {
            console.warn(`      ⚠️ [${scenario.scenario_name}] 未能生成用例`)
            return [] as CaseWithScenario[]
          }

          // 审核-修复循环
          let remainingCases = [...newCases]
          const passedCases: CaseWithScenario[] = []
          let round = 0

          while (round <= maxRefineRoundsPerBatch && remainingCases.length > 0) {
            round++
            console.log(`      [${scenario.scenario_name}] 审核-修复 轮次 ${round}/${maxRefineRoundsPerBatch + 1}`)

            // 审核
            const auditResults = await auditCases(remainingCases, tagTree, client, {
              concurrency: auditConcurrency,
              signal,
              onProgress: (completed, total) => {
                if (completed % 3 === 0 || completed === total) {
                  console.log(`        [${scenario.scenario_name}] 审核: ${completed}/${total}`)
                }
                onProgress?.({
                  stage: 'auditing',
                  current: completed,
                  total,
                  progressPercentage: calcProgress(iteration, replenishCompleted, replenishmentTasks.length),
                  currentStep: `正在审核"${scenario.scenario_name}"的用例 (${completed}/${total})`,
                  currentScenarioName: scenario.scenario_name,
                })
              },
            })

            // 分类
            const passedIds = new Set(auditResults.filter(r => r.audit_pass).map(r => r.case_id))
            const justPassed = remainingCases.filter(c => passedIds.has(c.case_id))
            const failedCases = remainingCases.filter(c => !passedIds.has(c.case_id))

            passedCases.push(...justPassed)
            console.log(`        [${scenario.scenario_name}] 通过: ${justPassed.length}, 失败: ${failedCases.length}`)

            if (failedCases.length === 0 || round > maxRefineRoundsPerBatch) {
              break
            }

            // 修复
            const failedAudits = auditResults.filter(r => !r.audit_pass)
            const fixResults = await fixCasesByAudit(
              failedCases,
              failedAudits,
              tagTree,
              client,
              auditOneCase,
              {
                maxRounds: 2,
                concurrency: fixConcurrency,
                signal,
              }
            )

            remainingCases = fixResults.map(r => r.fixed_case)
            const afterFixPassed = fixResults.filter(r => r.final_pass).length
            console.log(`        [${scenario.scenario_name}] 修复后通过: ${afterFixPassed}/${fixResults.length}`)
          }

          replenishCompleted++
          return passedCases
        })
      )
    )

    // 合并所有并发场景的结果到总集合
    for (const passedCases of replenishResults) {
      for (const caseItem of passedCases) {
        // 去重检查（基于 case_id）
        const exists = allPassedCases.some(c => c.case_id === caseItem.case_id)
        if (!exists) {
          allPassedCases.push(caseItem)

          // 流式输出（简化后再推送，确保前端/后端收到的格式一致）
          const simplified = simplifyUserQueryLists([caseItem])[0]
          await onCaseGenerated?.(simplified, {
            scenarioId: caseItem.source_scenario_id,
            scenarioName: caseItem.source_scenario_name,
            iteration,
            totalPassedCases: allPassedCases.length,
          })
        }
      }
    }

    // 更新场景用例计数
    for (const scenario of scenarios) {
      const count = allPassedCases.filter(c => c.source_scenario_id === scenario.scenario_id).length
      scenarioCaseCount.set(scenario.scenario_id, count)
    }

    // 推送迭代结束进度
    onProgress?.({
      stage: 'auditing',
      current: allPassedCases.length,
      total: targetTotalCases,
      progressPercentage: calcProgress(iteration, replenishmentTasks.length, replenishmentTasks.length),
      currentStep: `迭代 ${iteration} 完成，累计 ${allPassedCases.length}/${targetTotalCases} 个用例`,
    })

    console.log(`\n  [迭代完成] 累计合格用例: ${allPassedCases.length}`)
  }

  // ========== 完成 ==========
  const finalJudgement = judgeCaseGeneration(allPassedCases, scenarios, casesPerScenario)
  printCaseCountReport(finalJudgement)

  console.log(`\n========================================`)
  console.log(`     用例生成完成`)
  console.log(`========================================`)
  console.log(`  最终合格用例: ${allPassedCases.length}`)
  console.log(`  目标总数: ${scenarios.length * casesPerScenario}`)
  console.log(`  达标率: ${finalJudgement.satisfied ? '100%' : `${Math.round(((scenarios.length * casesPerScenario - finalJudgement.totalDeficit) / (scenarios.length * casesPerScenario)) * 100)}%`}`)
  console.log(`========================================\n`)

  // 推送完成状态
  onProgress?.({
    stage: 'completed',
    current: allPassedCases.length,
    total: targetTotalCases,
    progressPercentage: 100,
    currentStep: `用例生成完成，共 ${allPassedCases.length} 个用例`,
  })

  // 最终统一简化：将不需要 mock_time/mock_info 的轮次转为纯消息数组
  return simplifyUserQueryLists(allPassedCases)
}
