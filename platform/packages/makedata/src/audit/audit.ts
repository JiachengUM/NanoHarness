/**
 * 用例审核 - 质量审计
 *
 * 输入：用例列表 + 标签树 + 审核原则
 * 输出：审核报告（pass/fail、issues、summary）
 */

import { OpenAI, zodTextFormat, invokeWithRetry } from '@eval-platform/llm'
import { CaseAuditResultSchema, type CaseWithScenario, type CaseAuditResult } from '@eval-platform/database'
import type { TagTree } from '../core/tag-tree.js'
import { loadAuditPrinciples, loadKeyConstraints } from '../principles/index.js'
import { validateCaseSchema, validateTags, validateInteractionChain } from './validation.js'

// 使用 zodTextFormat 从 Zod Schema 生成 OpenAI JSON Schema
const auditResultJsonSchema = zodTextFormat(CaseAuditResultSchema, 'case_audit')

const AUDIT_RESULT_SCHEMA: OpenAI.Responses.ResponseTextConfig = {
  format: auditResultJsonSchema,
}

/**
 * 检测条件变量泄题
 */
function detectVariableLeakage(caseItem: CaseWithScenario): { valid: boolean; info: string } {
  const issues: string[] = []

  // 检查每个会话 - 只处理 DialogueRoundConfig 格式（对象格式）
  caseItem.user_query_lists?.forEach((session, idx) => {
    // 类型守卫：检查是否是 DialogueRoundConfig 对象
    if (typeof session === 'object' && !Array.isArray(session) && 'user_query_list' in session) {
      const roundConfig = session as { user_query_list: { role: string; content: string }[]; mock_time?: string | null }
      const userContent = roundConfig.user_query_list?.[0]?.content || ''
      const mockTime = roundConfig.mock_time || ''

      if (userContent && mockTime) {
        // 提取 mock_time 中的时间信息
        const timePatterns = [
          { regex: /(\d{1,2}):(\d{2})/, name: '具体时间（如8:00）', checkFunc: (user: string, mock: string) => user.includes(mock) },
          { regex: /早上|上午|中午|下午|晚上|凌晨/, name: '时段描述', checkFunc: (user: string, mock: string) => {
            const hour = parseInt(mock.match(/(\d{2}):\d{2}/)?.[1] || '0')
            const period = hour >= 5 && hour < 12 ? '早上' : hour >= 12 && hour < 14 ? '中午' : hour >= 14 && hour < 18 ? '下午' : '晚上'
            return user.includes(period)
          }},
          { regex: /(周一|周二|周三|周四|周五|周六|周日|星期[一二三四五六日])/, name: '星期', checkFunc: (user: string, mock: string) => {
            const mockMatch = mock.match(/\d{4}-(\d{2})-(\d{2})/)
            if (!mockMatch) return false
            // 简化：检查用户台词是否包含星期几
            return /周一|周二|周三|周四|周五|周六|周日|星期/.test(user)
          }},
        ]

        for (const pattern of timePatterns) {
          if (pattern.regex.test(mockTime) && pattern.checkFunc(userContent, mockTime)) {
            const mockMatch = mockTime.match(pattern.regex)
            const mockValue = mockMatch ? mockMatch[0] : '时间信息'
            issues.push(`  会话${idx + 1}: 用户台词"${userContent.substring(0, 30)}..."包含 ${pattern.name}"${mockValue}"，但 mock_time 已包含该信息（条件变量泄题）`)
            break // 每个会话只报一次
          }
        }
      }
    }
  })

  return {
    valid: issues.length === 0,
    info: issues.length > 0 ? issues.join('\n') : '✅ 未发现条件变量泄题'
  }
}

/**
 * 检测断言引用不可见字段
 */
function detectInvisibleFieldReferences(caseItem: CaseWithScenario): { valid: boolean; info: string } {
  const issues: string[] = []
  const forbiddenFields = ['mock_time', 'mock_info', 'car_info']

  caseItem.nl_assertion?.forEach((assertion, idx) => {
    for (const field of forbiddenFields) {
      if (assertion.includes(field)) {
        issues.push(`  断言${idx + 1}: 包含不可见字段"${field}"，应改为"背景信息"`)
      }
    }
  })

  return {
    valid: issues.length === 0,
    info: issues.length > 0 ? issues.join('\n') : '✅ 未发现引用不可见字段'
  }
}

/**
 * 检测时间规律发现场景的合理性（K0）
 * 检查：前三轮是否有明确具体行为，而非模糊指令
 */
function detectTimePatternReasonableness(caseItem: CaseWithScenario): { valid: boolean; info: string } {
  const issues: string[] = []
  const tags = caseItem.tags || []

  // 只检查包含"时间规律发现"或"条件规律发现"的用例
  if (!tags.some(tag => tag.includes('规律发现'))) {
    return { valid: true, info: '✅ 非规律发现类场景，跳过K0检查' }
  }

  // 获取用户台词列表
  const userContents: string[] = []
  caseItem.user_query_lists?.forEach((session, idx) => {
    if (typeof session === 'object' && !Array.isArray(session) && 'user_query_list' in session) {
      const roundConfig = session as { user_query_list: { role: string; content: string }[] }
      const content = roundConfig.user_query_list?.[0]?.content || ''
      if (content) userContents.push(content)
    }
  })

  // 检查是否有至少3轮（前三轮）
  if (userContents.length < 3) {
    issues.push(`  规律发现场景至少需要3轮建立行为模式，当前只有${userContents.length}轮`)
  }

  // 检查前三轮是否有模糊指令
  const vaguePatterns = [
    { pattern: /调[一下\s]*空调/, desc: '"调下空调"太模糊，没说调到多少度' },
    { pattern: /弄[一下\s]*空调/, desc: '"弄下空调"太模糊，意图不明确' },
    { pattern: /开[一下\s]*空调/, desc: '"开空调"虽有动作但无具体参数，无法归纳规律' },
    { pattern: /放[一下\s]*歌/, desc: '"放歌"太模糊，没说放什么歌' },
    { pattern: /调[一下\s]*音乐/, desc: '"调下音乐"太模糊' },
    { pattern: /调[一下\s]*温度/, desc: '"调下温度"太模糊，没说调到多少度' },
    { pattern: /调[一下\s]*风量/, desc: '"调下风量"太模糊，没说调到几档' },
  ]

  const firstThreeRounds = userContents.slice(0, 3)
  firstThreeRounds.forEach((content, idx) => {
    for (const { pattern, desc } of vaguePatterns) {
      if (pattern.test(content)) {
        issues.push(`  第${idx + 1}轮用户台词"${content.substring(0, 20)}..." ${desc}，不符合时间规律发现的"具体可归纳行为"要求`)
        break
      }
    }
  })

  // 检查末轮是否是托付短句（符合K2，同时验证K0的"验证"性质）
  const lastRound = userContents[userContents.length - 1]
  if (lastRound && !/照旧|你知道|老样子|和之前|和上次|一样/.test(lastRound)) {
    // 只有第4轮才需要检查托付短句，如果轮数不足4轮则不强制
    if (userContents.length >= 4) {
      issues.push(`  第${userContents.length}轮(末轮)用户台词"${lastRound.substring(0, 20)}..."不是托付短句（如"照旧"），无法验证助手是否主动发现规律`)
    }
  }

  return {
    valid: issues.length === 0,
    info: issues.length > 0 ? issues.join('\n') : '✅ 时间规律发现场景设计合理'
  }
}

/**
 * 检测普通场景误带 mock_time / mock_info 的问题
 *
 * 规则：
 * - 如果 tags 不含"规律发现"，但 user_query_lists 中有 DialogueRoundConfig 设了 mock_time，
 *   则判定为误用（普通场景不需要逐轮时间）
 * - mock_info 如果有 car_info 且与 context_config.car_info 重复，也标记为冗余
 */
function detectUnnecessaryMockTime(caseItem: CaseWithScenario): { valid: boolean; info: string } {
  const tags = caseItem.tags || []
  const isPatternDiscovery = tags.some(tag => tag.includes('规律发现'))

  // 规律发现类场景跳过此检查
  if (isPatternDiscovery) {
    return { valid: true, info: '✅ 规律发现类场景，跳过 mock_time 误用检查' }
  }

  const issues: string[] = []
  let hasUnnecessaryMockTime = false
  let hasUnnecessaryMockInfo = false

  caseItem.user_query_lists?.forEach((session, idx) => {
    if (typeof session === 'object' && !Array.isArray(session) && 'user_query_list' in session) {
      const roundConfig = session as { mock_time?: string | null; mock_info?: Record<string, unknown> }

      // 检查 mock_time
      if (roundConfig.mock_time != null && roundConfig.mock_time !== '') {
        hasUnnecessaryMockTime = true
        issues.push(`  第${idx + 1}轮：普通场景不应设置 mock_time="${roundConfig.mock_time}"，应为 null`)
      }

      // 检查 mock_info 是否有非空 car_info（可能与 context_config 重复）
      if (roundConfig.mock_info && Object.keys(roundConfig.mock_info).length > 0) {
        hasUnnecessaryMockInfo = true
        issues.push(`  第${idx + 1}轮：普通场景不应在 mock_info 中设置车况，应统一放在 context_config.car_info`)
      }
    }
  })

  if (hasUnnecessaryMockTime || hasUnnecessaryMockInfo) {
    return {
      valid: false,
      info: `⚠️ 普通场景误用了 mock_time/mock_info（应为规律发现类场景才需要）：\n${issues.join('\n')}`,
    }
  }

  return { valid: true, info: '✅ 普通场景未误用 mock_time/mock_info' }
}

/**
 * 检测用户台词和脚本中的占位符（如 XX、某、某某、待定等）
 * 地址/地名/路名/店名/小区名/歌曲名等具体信息必须用可真实读出的具体值，
 * 否则 TTS 会读成"叉叉路"，使 case 无评测意义。
 */
function detectPlaceholderContent(caseItem: CaseWithScenario): { valid: boolean; info: string } {
  const issues: string[] = []
  const placeholderPatterns = [
    { regex: /XX|xx|Xx|xX/, name: 'XX型占位符' },
    { regex: /某某|某/, name: '某/某某型占位符' },
    { regex: /待定|未知/, name: '待定/未知型占位符' },
  ]

  const textsToCheck: { text: string; source: string }[] = []

  // 收集 user_query_lists 中的用户台词
  caseItem.user_query_lists?.forEach((session, idx) => {
    if (Array.isArray(session)) {
      session.forEach((msg, msgIdx) => {
        if (msg?.role === 'user' && msg.content) {
          textsToCheck.push({ text: msg.content, source: `user_query_lists[${idx}][${msgIdx}]` })
        }
      })
    } else if (typeof session === 'object' && session && 'user_query_list' in session) {
      const roundConfig = session as { user_query_list?: { role?: string; content?: string }[] }
      roundConfig.user_query_list?.forEach((msg, msgIdx) => {
        if (msg?.role === 'user' && msg.content) {
          textsToCheck.push({ text: msg.content, source: `user_query_lists[${idx}][${msgIdx}]` })
        }
      })
    }
  })

  // 收集 expected_script 中的用户台词
  if (caseItem.expected_script && typeof caseItem.expected_script === 'string') {
    const userLines = caseItem.expected_script.split('\n').filter(line => /^\s*用户[：:]/.test(line))
    userLines.forEach((line, idx) => {
      textsToCheck.push({ text: line, source: `expected_script 用户行${idx + 1}` })
    })
  }

  for (const { source, text } of textsToCheck) {
    for (const { regex, name } of placeholderPatterns) {
      if (regex.test(text)) {
        issues.push(`  ${source}: 包含${name}"${text.substring(0, 30)}..."，必须改为真实可读的具体的值（如"南京西路1266号"）`)
        break
      }
    }
  }

  return {
    valid: issues.length === 0,
    info: issues.length > 0 ? `❌ 发现占位符问题：\n${issues.join('\n')}` : '✅ 未发现用户台词中有占位符',
  }
}

/**
 * 检测用例核心字段类型是否正确
 * 类型错误应作为审核 issue 暴露，而不是在生成阶段被默默清洗成默认值。
 */
function detectTypeIssues(caseItem: CaseWithScenario): { valid: boolean; info: string } {
  const issues: string[] = []

  const fieldChecks: { field: string; expected: string; actual: string; valid: boolean }[] = [
    { field: 'case_id', expected: 'string', actual: typeof caseItem.case_id, valid: typeof caseItem.case_id === 'string' && caseItem.case_id.trim().length > 0 },
    { field: 'expected_script', expected: 'string', actual: typeof caseItem.expected_script, valid: typeof caseItem.expected_script === 'string' },
    { field: 'case_description', expected: 'string', actual: typeof caseItem.case_description, valid: typeof caseItem.case_description === 'string' },
    { field: 'max_round', expected: 'number', actual: typeof caseItem.max_round, valid: typeof caseItem.max_round === 'number' && caseItem.max_round > 0 },
    { field: 'context_config', expected: 'object', actual: typeof caseItem.context_config, valid: typeof caseItem.context_config === 'object' && caseItem.context_config !== null && !Array.isArray(caseItem.context_config) },
    { field: 'user_query_lists', expected: 'array', actual: Array.isArray(caseItem.user_query_lists) ? 'array' : typeof caseItem.user_query_lists, valid: Array.isArray(caseItem.user_query_lists) },
    { field: 'nl_assertion', expected: 'array<string>', actual: Array.isArray(caseItem.nl_assertion) ? 'array' : typeof caseItem.nl_assertion, valid: Array.isArray(caseItem.nl_assertion) && caseItem.nl_assertion.every(item => typeof item === 'string') },
    { field: 'tags', expected: 'array<string>', actual: Array.isArray(caseItem.tags) ? 'array' : typeof caseItem.tags, valid: Array.isArray(caseItem.tags) && caseItem.tags.every(item => typeof item === 'string') },
  ]

  for (const check of fieldChecks) {
    if (!check.valid) {
      issues.push(`  ${check.field} 类型错误：期望 ${check.expected}，实际为 ${check.actual}`)
    }
  }

  return {
    valid: issues.length === 0,
    info: issues.length > 0 ? `❌ 发现字段类型错误：\n${issues.join('\n')}` : '✅ 核心字段类型正确',
  }
}

/**
 * 检测 context_config 中是否包含记忆相关配置（memory_types、collection_name 等）
 * 记忆库配置属于被测 agent 的部署/测试环境配置，不应由数据合成生成。
 */
function detectMemoryConfigInContext(caseItem: CaseWithScenario): { valid: boolean; info: string } {
  const issues: string[] = []
  const contextConfig = caseItem.context_config as Record<string, unknown> | undefined

  if (contextConfig) {
    const forbiddenKeys = ['memory_types', 'collection_name', 'memory_type', 'collection_id', 'memory_config']
    for (const key of forbiddenKeys) {
      if (key in contextConfig) {
        issues.push(`  context_config 包含禁止字段"${key}"：${JSON.stringify(contextConfig[key])}，记忆库配置应由测试环境统一注入，用例中不生成`)
      }
    }
  }

  return {
    valid: issues.length === 0,
    info: issues.length > 0 ? `❌ 发现 context_config 中记忆配置问题：\n${issues.join('\n')}` : '✅ context_config 未包含记忆相关配置',
  }
}

/**
 * 检测 car_info 中是否包含用户查询目标、需求或目标对象属性
 * car_info 只应包含当前车辆及所处环境的客观状态。
 */
function detectCarInfoMisuse(caseItem: CaseWithScenario): { valid: boolean; info: string } {
  const issues: string[] = []
  const contextConfig = caseItem.context_config as Record<string, unknown> | undefined
  const carInfo = contextConfig?.car_info

  if (carInfo === undefined || carInfo === null) {
    return { valid: true, info: '✅ car_info 为空，跳过检查' }
  }

  const carInfoText = typeof carInfo === 'string' ? carInfo : JSON.stringify(carInfo)

  const misusePatterns = [
    { regex: /用户需求|用户要求|查询目标|筛选目标|目标车型|目标车辆|购车需求|购车目标|筛选条件|查询条件/i, name: '用户需求/查询目标/筛选条件' },
    { regex: /车辆用途|用车场景|目标用途|用途定位|购车用途/i, name: '目标车辆用途' },
    { regex: /目标价格|购车预算|售价区间|预算范围|价格区间/i, name: '目标价格/预算' },
    { regex: /用户身份|用户角色|用户画像|车主身份|用户类型/i, name: '用户身份/角色' },
    { regex: /用户所在地作为|用户所在城市|以用户所在地|按用户所在地/i, name: '用户所在地作为筛选条件' },
  ]

  for (const { regex, name } of misusePatterns) {
    if (regex.test(carInfoText)) {
      issues.push(`  car_info 包含${name}："${carInfoText.substring(0, 60)}..."，car_info 只应写当前车辆及环境客观状态，查询目标/需求应放在 user_query_lists`)
      break
    }
  }

  return {
    valid: issues.length === 0,
    info: issues.length > 0 ? `❌ 发现 car_info 误用问题：\n${issues.join('\n')}` : '✅ car_info 未包含用户查询目标或需求',
  }
}

/**
 * 构建审核 Prompt
 */
export async function buildAuditPrompt(caseItem: CaseWithScenario, tagTree: TagTree): Promise<string> {
  const principles = await loadAuditPrinciples()
  const keyConstraints = await loadKeyConstraints()

  // 程序化校验
  const schemaValidation = validateCaseSchema(caseItem)
  const typeValidation = detectTypeIssues(caseItem)
  const tagValidation = validateTags(caseItem.tags || [], tagTree)
  const chainValidation = validateInteractionChain(caseItem)
  const leakageValidation = detectVariableLeakage(caseItem)
  const fieldRefValidation = detectInvisibleFieldReferences(caseItem)
  const timePatternValidation = detectTimePatternReasonableness(caseItem)
  const unnecessaryMockTimeValidation = detectUnnecessaryMockTime(caseItem)
  const placeholderValidation = detectPlaceholderContent(caseItem)
  const memoryConfigValidation = detectMemoryConfigInContext(caseItem)
  const carInfoMisuseValidation = detectCarInfoMisuse(caseItem)

  // 汇总程序化校验结果
  const programmaticResults = [
    `【Schema结构校验 (C1)】${schemaValidation.valid ? '✅ 通过' : '❌ 失败'}`
    + (schemaValidation.valid ? '' : `\n${schemaValidation.info}`),

    `【字段类型校验 (C1)】${typeValidation.valid ? '✅ 通过' : '❌ 失败'}`
    + (typeValidation.valid ? '' : `\n${typeValidation.info}`),

    `【标签合规校验 (D1/D2)】${tagValidation.valid ? '✅ 通过' : '⚠️ 警告'}`
    + `\n${tagValidation.info}`,

    `【交互链校验 (C3)】${chainValidation.valid ? '✅ 通过' : '⚠️ 警告'}`
    + (chainValidation.valid ? '' : `\n${chainValidation.info}`),

    `【时间规律发现场景合理性 (K0)】${timePatternValidation.valid ? '✅ 通过' : '❌ 失败'}`
    + (timePatternValidation.valid ? '' : `\n${timePatternValidation.info}`),

    `【mock_time/mock_info 误用检查】${unnecessaryMockTimeValidation.valid ? '✅ 通过' : '⚠️ 警告'}`
    + (unnecessaryMockTimeValidation.valid ? '' : `\n${unnecessaryMockTimeValidation.info}`),

    `【条件变量泄题检查 (K1)】${leakageValidation.valid ? '✅ 通过' : '❌ 失败'}`
    + (leakageValidation.valid ? '' : `\n${leakageValidation.info}`),

    `【断言字段引用检查 (K3)】${fieldRefValidation.valid ? '✅ 通过' : '❌ 失败'}`
    + (fieldRefValidation.valid ? '' : `\n${fieldRefValidation.info}`),

    `【占位符检查 (K7)】${placeholderValidation.valid ? '✅ 通过' : '❌ 失败'}`
    + (placeholderValidation.valid ? '' : `\n${placeholderValidation.info}`),

    `【context_config 记忆配置检查 (K8)】${memoryConfigValidation.valid ? '✅ 通过' : '❌ 失败'}`
    + (memoryConfigValidation.valid ? '' : `\n${memoryConfigValidation.info}`),

    `【car_info 误用检查 (K10)】${carInfoMisuseValidation.valid ? '✅ 通过' : '❌ 失败'}`
    + (carInfoMisuseValidation.valid ? '' : `\n${carInfoMisuseValidation.info}`),
  ].join('\n\n')

  return `
你是一个专业的车载助手测试用例审核专家。请严格审核以下用例是否符合审核原则。

## 🚨 关键约束（硬性要求，违反则必须标记为 CRITICAL）

${keyConstraints || '【关键约束加载失败，请参考完整审核原则】'}

## 审核原则（完整版）

${principles}

---

【程序化预校验结果】

以下校验结果由系统自动完成，**请务必在审核结果中体现**（特别是标记为❌失败的项）：

${programmaticResults}

---

【待审核用例】
${JSON.stringify({
    id: caseItem.case_id,
    case_id: caseItem.case_id,
    tags: caseItem.tags,
    case_description: caseItem.case_description,
    user_query_lists: caseItem.user_query_lists,
    expected_script: caseItem.expected_script,
    nl_assertion: caseItem.nl_assertion,
    context_config: caseItem.context_config,
    max_round: caseItem.max_round,
  }, null, 2)}

---

【审核任务 - 必须逐项检查】

### 🔴 K类 - 硬性约束（发现即 CRITICAL，必须 fail）

**K0. 时间规律发现场景设计合理性【关键】**
- 检查：规律发现类场景（含"时间规律发现"或"条件规律发现"标签）是否符合乘用车场景常识
- 核心问题：前三轮用户是否有**明确的具体行为**（如"空调调到24度"），而非模糊指令（如"调下空调"）
- 检查点：
  * 前三轮是否都有明确可归纳的行为？（有具体参数/数值，助手知道该做什么）
  * 如果没有明确行为，之前是否建立过明确偏好？（助手有依据推断）
  * 是否符合真实车主行为？（问自己：车主真的会反复这样说吗？）
- 反例（❌ 无厘头）：前三轮用户都说"调下空调"（模糊），第四轮说"照旧"——没有"旧"可循
- 正例（✅ 合理）：前三轮分别说"空调调到24度"/"还是24度"/"和昨天一样"，第四轮"照旧"——助手应主动执行24度
- 本质：**时间规律发现的前提是用户有可归纳的具体行为模式**

**K1. 条件变量禁止泄题**
- 检查：用户台词是否复述了 mock_time/car_info 中的时间/天气/星期/车速等条件变量
- 反例：mock_time="08:00"，用户说"早上8点去公司"
- 正例：用户只说"今天去公司"，时间从 mock_time 推断

**K2. 验证轮禁止复述具体动作（规律类题型）**
- 检查：时间/条件规律发现的第4轮，用户是否复述了前几轮的具体车控口令（关窗/开内循环/调风量）
- 正例：第4轮用户说"照旧""你知道咋办吧"

**K3. 断言禁止引用不可见字段**
- 检查：nl_assertion 中是否出现 car_info、mock_time、mock_info 字样
- 正例：使用"背景信息"指代

**K4. car_info 格式规范**
- 检查：是否使用中文全角冒号「键：值」
- 反例："车速: 60" 或 "车速=60"

**K5. user_query_lists 结构**
- 检查：每项是否只有1条user消息
- 反例：user_query_lists[0].user_query_list 里有3条user

**K6. 禁止能力泄题**
- 检查：测「助手主动给替代方案」时，用户是否直接说"给我替代方案"
- 本质：用户说了就变成测"命令遵循"而非"主动能力"

|**K7. 用户台词禁止出现占位符（XX、某、某某、待定等）**
|- 检查：user_query_lists 和 expected_script 中"用户："行是否包含 XX、某、某某、待定、未知等占位符
|- 反例（❌ 错误）："把我家地址改成XX路123号""导航到某某商场""播放待定歌曲"
|- 正例（✅ 正确）："把我家地址改成南京西路1266号""导航到陆家嘴中心商场"
|- 本质：用户台词是演员照读给 TTS 的，占位符会被读成"叉叉路"，case 失去评测意义

|**K8. context_config 禁止包含记忆相关配置**
|- 检查：context_config 中是否包含 memory_types、collection_name 等记忆相关字段
|- 反例（❌ 错误）：context_config: { car_info: "...", memory_types: "导航记忆、临时地址记忆" }
|- 正例（✅ 正确）：context_config: { car_info: "..." }
|- 本质：记忆库配置属于被测 agent 的部署/测试环境配置，数据合成不生成

|**K9. 核心字段类型正确**
|- 检查：case_id、expected_script、case_description、max_round、context_config、user_query_lists、nl_assertion、tags 等字段类型是否符合 DatasetItemSchema
|- 反例（❌ 错误）：expected_script 是数字或对象、case_id 为空、max_round 不是正整数
|- 本质：字段类型错误会导致下游执行/评测异常，必须由修复阶段修复

|**K10. car_info 只应包含当前车辆及环境客观状态**
|- 检查：car_info 中是否包含用户需求、查询目标、目标对象属性、车辆用途、用户身份等
|- 反例（❌ 错误）：car_info: "用户需求：2025年通勤纯电SUV；车辆用途：日常通勤；用户所在地：广州"
|- 正例（✅ 正确）：car_info: "车速：0km/h，档位：P档，道路类型：室内停车场，动力电池电量：70%"
|- 本质：car_info 是当前车辆状态快照，查询目标/需求必须放在 user_query_lists 的用户台词中

|**K11. 用户台词自然性（冷启动 + expected_script 后续轮次）**
|- 检查：user_query_lists 每个 session 的首条 user 消息（冷启动台词）**以及** expected_script 中每个"用户："行的台词，是否像真人会对车载助手说的话
|- 重点抓两类不自然：
  - **念清单式冷启动**：单句内多次反复改变同一目标且无犹豫语气词，像念任务清单——说明多轮交互被错误压缩进第一句。反例（❌）："导航到公司，先去虹桥机场，马上回公司，还有多久到？"
  - **技术化/书面化/指令式表述**（expected_script 后续轮次）：把测试需求直接翻译成台词，用工程师/产品视角的术语。反例（❌）："再问下当前座椅设置""查询当前任务状态""请反馈当前导航进度""确认座椅模式""反馈剩余时间"——真人不会这么对车机说话
|- 正例（✅ 正确）：冷启动"导航到公司，顺便放点轻音乐"（并行多任务长句，自然）；冷启动"导航到公司，噢不，导航到虹桥机场先"（带犹豫语气的自然改口）；后续轮次"现在啥状态""调好了吗""还有多久到""加油站找到了吗"（口语化、结果导向、短句）
|- 本质：念清单式冷启动说明多轮交互应拆为冷启动第一句 + expected_script 后续轮次；技术化表述说明 LLM 把测试意图直接写进了用户嘴里
|- ⚠️ 注意不要矫枉过正：并行多任务长句、带犹豫语气的自然改口是允许的，只抓"多次反复改变同一目标且无犹豫语气"；口语化不等于必须极短，自然的长句询问也可

|**K12. 任务持续性与可取消性**
|- 检查：测"取消任务/询问任务进度/中途插话改任务/任务优先级调度"的场景，是否含至少一个**持续任务**（导航/搜索/播放/提醒）作为前置状态
|- 重点抓：用连续瞬间车控任务（开按摩/调空调/开车窗/开后备箱等）冒充"多任务并行/任务状态查询/任务取消"测试
|- 反例（❌ 错误）：用户连续下达"开按摩→调空调→开车窗"后问"当前正在执行哪些任务"——这些瞬间任务下达即完成，无"正在执行"状态可查
|- 反例（❌ 错误）：用户说"打开座椅按摩"后说"取消座椅按摩"——按摩已开完，无状态可取消
|- 正例（✅ 正确）：用户发起导航后中途问"还有多久到"或"取消导航"——导航是持续任务，有进度可问、有状态可取消
|- 本质：瞬间任务（秒级完成、无持续状态）不能作为"取消/询问进度/中途改任务/优先级调度"的测试对象，详见《用例编写通用原则》§13b
|- ⚠️ 例外：纯车控并行执行测试（如"同时开空调和开车窗"测多指令并行）不在此约束内，但不应伪装成"任务状态管理"测试
|- **架空前置检查**：冷启动台词或剧本里"取消之前的XX""查询刚才那个任务"等带定语引用前置任务的台词，被引用的任务必须在本 case 内（user_query_lists 或 expected_script 前序轮次）真实建立过。若被引用任务从未在本 case 建立过（LLM 脑补的背景故事），属架空前置，评测不可复现——详见《用例编写通用原则》§14b.2

### 🟡 A-E 类 - 常规质量检查

1. **用户台词（A类）**
   - 是否有括号尾巴（如"(概括)""(仅两字提示)"）
   - 是否有悬空指代（如"这款""竞争对手""那人"）
   - 记忆消费轮是否泄题（复述生产轮内容）

2. **断言质量（B类）**
   - 是否规范用户行为（如"用户台词须干净"）
   - 是否包含导演看不见的后台操作（如"写入长期记忆"）
   - 禁止类断言是否用"不得"开头

3. **结构正确性（C类）**
   - 记忆类是否有生产→消费闭环（至少2次冷启动）
   - 状态依赖型指令（暂停/下一首/上一首/切歌/导航取消/导航改线/导航状态询问等）是否先用一轮建立前置状态（播放某首歌、发起导航），再下达状态依赖指令——禁止用例里从未播放过任何歌曲却让用户直接说"暂停当前音乐"（评测不可复现）。**特别注意"取消之前的XX""查询刚才那个任务"等带定语引用前置任务的台词——被引用的任务必须在本 case 内真实建立过，禁止架空前置（§14b.2）**
   - **expected_script 多轮交替格式**：多轮场景（涉及中途插话/取消/查询/改口/多任务并行等需要中途交互的标签）的 expected_script 是否展开为"用户：xxx 管家：（期望…）"的交替剧本（而非一行概括）？假人照着剧本逐轮演绎，只写概括就无法演绎
   - **单次多轮不标"第N轮"**：单会话多轮剧本是否误标"第一轮""第二轮"（会让假人误以为是多次多轮）？
   - **多次多轮用"（重启新的对话……）"分隔**：多次多轮剧本是否用"第一会话""第二会话"等标注（应改为独立一行"（重启新的对话……）"分隔）？
   - **剧本首句=冷启动台词（强制一致性）**：expected_script 第一句"用户：xxx"是否与 user_query_lists[0] 的冷启动台词**逐字一致**？多次多轮场景每个"（重启新的对话……）"段的首句是否与对应 session 冷启动台词逐字一致？不一致则假人会念错第一句或无所适从，整个用例评测失效
   - **人设前导段检查（若使用）**：expected_script 开头若有非"用户：/管家："的前导段（人设/规则/环境约束等），检查：①前导段和正文是否用空行分隔；②前导段是否只写演绎规则（用户性格/应对策略/重试规则/环境约束），不写助手行为/判分点；③前导段是否架空前置状态（禁止"假设你之前已经XX"）；④不要把前导段误判为格式错误——它是 expected_script 的合法组成部分（§7.3）

4. **标签合规性（D类）**
   - 是否只打叶子标签
   - 标签与case内容是否支撑匹配

5. **感知边界（E类）**
   - 是否默认助手具备车载视觉

---

【输出格式】

严格返回JSON：
{
  "audit_pass": true/false,
  "issues": [
    {
      "principle": "违反的原则编号，如K1/K3/A5/B3",
      "dimension": "问题维度",
      "severity": "CRITICAL/MAJOR/MINOR",
      "description": "具体怎么违反了这条原则",
      "suggestion": "直接改写后的具体内容"
    }
  ],
  "summary": "一句话结论"
}

注意：
- 发现 K类（硬性约束）问题，audit_pass 必须为 false，severity 必须为 CRITICAL
- 程序化校验已发现的❌失败项，必须在 issues 中体现（principle 填对应编号如K1）
- suggestion 必须是可直接采用的改写建议，不要空泛描述
`.trim()
}

/**
 * 审核单个用例
 */
export async function auditOneCase(
  caseItem: CaseWithScenario,
  tagTree: TagTree,
  client: OpenAI,
  signal?: AbortSignal
): Promise<CaseAuditResult> {
  const prompt = await buildAuditPrompt(caseItem, tagTree)

  const params: OpenAI.Responses.ResponseCreateParamsNonStreaming = {
    instructions: prompt,
    input: `审核用例: ${caseItem.case_id}`,
    text: AUDIT_RESULT_SCHEMA,
    temperature: 0.0,
  }

  try {
    const result = await invokeWithRetry<Omit<CaseAuditResult, 'id' | 'case_id'>>(client, params, 3, signal)

    return {
      id: caseItem.case_id,
      case_id: caseItem.case_id,
      ...result,
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : '未知错误'
    console.warn(`[auditOneCase] ${caseItem.case_id} 审核失败（重试3次后仍失败）: ${errorMsg}`)

    // 兜底：返回审核失败结果，而不是抛异常中断整个流程
    return {
      id: caseItem.case_id,
      case_id: caseItem.case_id,
      audit_pass: false,
      issues: [
        {
          principle: 'SYSTEM',
          dimension: '系统错误',
          severity: 'CRITICAL',
          description: `LLM 审核调用失败: ${errorMsg}`,
          suggestion: '请重试审核，或人工检查该用例',
        },
      ],
      summary: `审核异常：${errorMsg}`,
    }
  }
}

/**
 * 批量审核用例
 *
 * @param cases - 用例列表
 * @param tagTree - 标签树（用于标签校验）
 * @param client - OpenAI 客户端
 * @param options - 配置选项
 * @returns 审核结果列表
 */
export async function auditCases(
  cases: CaseWithScenario[],
  tagTree: TagTree,
  client: OpenAI,
  options?: {
    concurrency?: number
    onProgress?: (completed: number, total: number) => void
    signal?: AbortSignal
  }
): Promise<CaseAuditResult[]> {
  const { concurrency = 10, signal } = options || {}

  console.log(`[auditCases] 开始审核 ${cases.length} 个用例，并发: ${concurrency}`)

  const results: CaseAuditResult[] = []
  let completed = 0

  // 简单的并发控制
  const runInBatches = async (batch: CaseWithScenario[]) => {
    const batchResults = await Promise.all(
      batch.map(async caseItem => {
        try {
          const result = await auditOneCase(caseItem, tagTree, client, signal)
          completed++
          options?.onProgress?.(completed, cases.length)
          return result
        } catch (error) {
          completed++
          options?.onProgress?.(completed, cases.length)
          return {
            id: caseItem.case_id,
            case_id: caseItem.case_id,
            audit_pass: false,
            issues: [
              {
                principle: 'SYSTEM',
                dimension: '系统错误' as const,
                severity: 'CRITICAL' as const,
                description: `审核异常: ${error}`,
                suggestion: '请重试审核',
              },
            ],
            summary: `审核异常: ${error}`,
          }
        }
      })
    )
    return batchResults
  }

  // 分批处理
  for (let i = 0; i < cases.length; i += concurrency) {
    if (signal?.aborted) {
      console.log(`[auditCases] 已取消，停止后续审核`)
      break
    }
    const batch = cases.slice(i, i + concurrency)
    const batchResults = await runInBatches(batch)
    results.push(...batchResults)

    const progress = Math.round((completed / cases.length) * 100)
    console.log(`  进度: ${completed}/${cases.length} (${progress}%)`)
  }

  // 汇总统计
  const passed = results.filter(r => r.audit_pass).length
  const failed = results.filter(r => !r.audit_pass && r.issues.length > 0).length
  const errors = results.filter(r => r.issues.some(i => i.principle === 'SYSTEM')).length

  console.log(`[auditCases] 审核完成`)
  console.log(`  通过: ${passed}`)
  console.log(`  未通过: ${failed}`)
  console.log(`  异常: ${errors}`)

  return results
}

export { validateCaseSchema, validateTags, validateInteractionChain }
