/**
 * 测试工具函数
 *
 * 所有测试统一使用 vehicle-tag-tree.json 作为标签树数据源。
 *
 * 双模式测试支持：
 * - Mock 模式：createMockClient() 返回不调用真实 LLM 的 mock 客户端，用于快速测试代码逻辑
 * - Real LLM 模式：createClient() 调用真实 LLM，用于跑通功能逻辑和考察效果
 *
 * 通过环境变量 RUN_REAL_LLM 控制是否运行 real LLM 测试：
 * - 默认（pnpm test）：仅运行 mock 测试
 * - RUN_REAL_LLM=true pnpm test:real：运行 real LLM 测试
 */

import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'
import { describe } from 'vitest'
import { TagTree } from '../src/core/tag-tree'
import type { Scenario } from '@eval-platform/database/models/scenario'
import type { CaseWithScenario } from '@eval-platform/database'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// ═══════════════════════════════════════════════════════════════════════════
// 测试模式开关
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 是否运行真实 LLM 测试。
 * - 默认 false：仅运行 mock 测试（快速）
 * - 设为 true：运行真实 LLM 测试（慢，需配置 API key）
 *
 * 通过环境变量 RUN_REAL_LLM=true 启用，或 pnpm test:real
 */
export const RUN_REAL_LLM = process.env.RUN_REAL_LLM === 'true' || process.env.RUN_REAL_LLM === '1'

/**
 * Real LLM 测试描述块：仅在 RUN_REAL_LLM=true 时运行
 */
export const describeRealLLM = RUN_REAL_LLM ? describe : describe.skip

/**
 * Mock 测试描述块：始终运行（除非显式 RUN_REAL_LLM=true 且只要 mock）
 */
export const describeMock = describe

// ═══════════════════════════════════════════════════════════════════════════
// 标签树工具
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 加载真实的 vehicle-tag-tree.json 作为测试标签树
 * 所有需要标签树的测试都应该使用此函数
 */
export function loadTestTagTree(): TagTree {
  const treePath = join(__dirname, '../examples/data/vehicle-tag-tree.json')
  const treeJson = JSON.parse(readFileSync(treePath, 'utf-8'))
  return TagTree.fromJSON(treeJson)
}

/**
 * 获取测试标签树中的几个代表性叶子标签
 * 用于测试用例构建
 */
export function getTestLeafTags(): string[] {
  const tree = loadTestTagTree()
  const allLeaves = tree.getLeafTagNames()

  return [
    '温度增减调节',
    '精确地点直达',
    '按歌手点播',
    '多轮对话_2到3轮',
    '常用地点记忆',
  ].filter(tag => allLeaves.includes(tag))
}

/**
 * 获取一个无效的叶子标签（肯定不存在于标签树中）
 */
export function getInvalidLeafTag(): string {
  return '不存在的测试标签_12345'
}

/**
 * 获取一个中间节点标签（非叶子，应该被拒绝）
 */
export function getIntermediateNodeTag(): string {
  return '空调操作'
}

// ═══════════════════════════════════════════════════════════════════════════
// Mock 数据构建器
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 构建 mock Plan 数据（不含 scenario_patterns，符合新流程）
 */
export function buildMockPlanData(query: string) {
  return {
    original_query: query,
    task_description: `【Mock】${query} - 详细任务描述`,
    target_tags: ['温度增减调节', '精确地点直达', '常用地点记忆'],
    interpretation_notes: 'Mock Plan 理解注解，用于测试代码逻辑',
    status: 'pending' as const,
    tag_tree_name: 'mock-tree',
  }
}

/**
 * 构建 mock patterns 列表
 */
export function buildMockPatterns(): string[] {
  return [
    '单轮直达空调温度调节场景',
    '单轮直达导航到常用地点场景',
    '多轮对话空调温度调节场景',
  ]
}

/**
 * 构建 mock 场景列表
 */
export function buildMockScenarios(count: number = 3, pattern?: string): Scenario[] {
  const names = ['空调温度调节', '导航到公司', '音乐播放控制', '座椅加热调节', '车窗控制']
  const tagsOptions = [
    ['温度增减调节', '单轮任务'],
    ['精确地点直达', '常用地点记忆'],
    ['按歌手点播', '单轮任务'],
    ['温度直接设定', '多轮对话_2到3轮'],
    ['车窗开关控制', '单轮任务'],
  ]

  const scenarios: Scenario[] = []
  for (let i = 0; i < count; i++) {
    const idx = i % names.length
    scenarios.push({
      scenario_id: `scenario-mock-${String(i + 1).padStart(3, '0')}`,
      scenario_name: names[idx] + (i >= names.length ? ` 变体${Math.floor(i / names.length) + 1}` : ''),
      description: `Mock 场景描述：测试${names[idx]}功能，验证助手能正确理解和执行用户指令`,
      tags: tagsOptions[idx],
      pattern: pattern,
    })
  }
  return scenarios
}

/**
 * 构建 mock 用例
 */
export function buildMockCases(scenarios: Scenario[], casesPerScenario: number = 1): CaseWithScenario[] {
  const cases: CaseWithScenario[] = []
  for (const scenario of scenarios) {
    for (let i = 0; i < casesPerScenario; i++) {
      cases.push({
        dataset_id: 'mock-dataset',
        case_id: `${scenario.scenario_name}-变体${i + 1}`,
        context_config: { car_info: { 车速: '30km/h' } },
        max_round: 8,
        user_query_lists: [
          {
            user_query_list: [{ role: 'user', content: '把空调调低两度' }],
            mock_info: {},
            mock_time: '2024-01-15 09:00:00',
          },
        ],
        expected_script: '用户：把空调调低两度\n助手：已将空调温度调低2度',
        nl_assertion: ['助手正确识别温度调节指令并执行', '助手反馈执行结果'],
        case_description: `测试 ${scenario.scenario_name}`,
        tags: scenario.tags,
        source_scenario_id: scenario.scenario_id,
        source_scenario_name: scenario.scenario_name,
      })
    }
  }
  return cases
}

// ═══════════════════════════════════════════════════════════════════════════
// Mock LLM Client
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Mock LLM 响应类型映射
 *
 * 根据 params.text.format.json_schema.name 分发不同的 mock 响应。
 * 这样可以模拟完整的生成流程，不调用真实 LLM。
 */
type MockResponder = (params: any) => any

interface MockClientOptions {
  /** 自定义响应覆盖：key = format name，value = 响应数据或响应生成函数 */
  responses?: Record<string, any | ((params: any) => any)>
  /** 默认场景数量（用于 scenario_list 响应） */
  defaultScenarioCount?: number
  /** 默认审核是否通过 */
  defaultAuditPass?: boolean
}

/**
 * 创建 Mock LLM Client
 *
 * 模拟 OpenAI 客户端的 responses.create 方法，
 * 根据 text.format.json_schema.name 分发预定义的 mock 响应。
 *
 * 支持的 format name：
 * - planner_output: Plan 生成
 * - pattern_output: Pattern 生成
 * - scenario_list: 场景生成
 * - audit_result: 场景审核
 * - fixed_scenario: 场景修复
 * - duplicate_detection: 重复检测
 * - judgement: Judge 评估
 * - output: 相关标签识别
 * - case_list: 用例生成
 * - case_audit: 用例审核
 * - fixed_case: 用例修复
 */
export function createMockClient(options: MockClientOptions = {}): any {
  const {
    responses = {},
    defaultScenarioCount = 3,
    defaultAuditPass = true,
  } = options

  /**
   * 根据 format name 获取 mock 响应
   */
  const getMockResponse = (formatName: string, params: any): any => {
    // 优先使用自定义响应
    if (responses[formatName] !== undefined) {
      const custom = responses[formatName]
      return typeof custom === 'function' ? custom(params) : custom
    }

    // 默认 mock 响应
    switch (formatName) {
      // ── Plan 生成 ──
      case 'planner_output':
        return {
          plan: buildMockPlanData(params.input?.substring(0, 50) || 'mock query'),
        }

      // ── Pattern 生成 ──
      case 'pattern_output':
        return { scenario_patterns: buildMockPatterns() }

      // ── 场景生成 ──
      case 'scenario_list':
        return { scenarios: buildMockScenarios(defaultScenarioCount) }

      // ── 场景审核 ──
      case 'audit_result': {
        // 从 params 中提取场景信息
        const scenarioMatch = params.input?.match(/ID:\s*(scenario-\S+)/)
        const scenarioId = scenarioMatch?.[1] || 'scenario-mock-001'
        return {
          id: `audit-${Date.now()}`,
          scenario_id: scenarioId,
          audit_pass: defaultAuditPass,
          issues: defaultAuditPass ? [] : [{
            principle: 'T2',
            dimension: '标签合法性',
            severity: 'MAJOR',
            description: 'Mock 审核问题：标签可能不匹配',
            suggestion: '建议调整标签',
          }],
          summary: defaultAuditPass ? 'Mock 审核通过' : 'Mock 审核未通过',
        }
      }

      // ── 场景修复 ──
      case 'fixed_scenario': {
        const scenarioMatch = params.input?.match(/ID:\s*(scenario-\S+)/)
        const scenarioId = scenarioMatch?.[1] || 'scenario-mock-001'
        return {
          fixed_scenario: {
            scenario_id: scenarioId,
            scenario_name: 'Mock 修复后场景',
            description: 'Mock 修复后的场景描述',
            tags: ['温度增减调节', '单轮任务'],
          },
        }
      }

      // ── 重复检测 ──
      case 'duplicate_detection':
        return { duplicate_groups: [] }

      // ── Judge 评估 ──
      case 'judgement':
        return {
          judgement: {
            satisfied: true,
            gap_analysis: {
              uncovered_relevant_tags: [],
              query_intent_fulfillment: 100,
              coverage_depth_score: 100,
              suggestion: 'Mock Judge: 已满足要求',
            },
            refinement_direction: {
              next_batch_size: 0,
              focus_tags: [],
              avoid_tags: [],
              scenario_types: [],
              guidance: 'Mock Judge: 已满足要求',
              suggested_count: 0,
              target_pattern: null,
              duplicate_scenarios: [],
            },
          },
        }

      // ── 相关标签识别 ──
      case 'output':
        return {
          relevant_tags: ['温度增减调节', '精确地点直达', '常用地点记忆'],
        }

      // ── 用例生成（一次性生成同场景 N 个用例）──
      case 'case_list': {
        const scenarioMatch = params.input?.match(/场景\s*"([^"]+)"/)
        const scenarioName = scenarioMatch?.[1] || 'Mock 场景'
        const scenarioId = 'scenario-mock-001'

        // 从 input 中解析请求数量
        const countMatch = params.input?.match(/生成\s*(\d+)\s*个/)
        const requestedCount = countMatch ? parseInt(countMatch[1], 10) : 1

        // 生成 requestedCount 个互不雷同的 mock 用例
        const mockFirstLines = [
          '把空调调低两度',
          '空调太热了降一点',
          '帮我调下温度',
          '空调温度设成24度',
        ]
        const mockCaseNames = [
          '空调降温两度直达',
          '口语化请求降温',
          '简洁指令调温',
          '精确温度设定24度',
        ]
        const cases = Array.from({ length: requestedCount }, (_, i) => ({
          dataset_id: 'mock-dataset',
          case_id: mockCaseNames[i % mockCaseNames.length] + (i >= mockCaseNames.length ? `-${i + 1}` : ''),
          context_config: { car_info: { 车速: '30km/h' } },
          max_round: 8,
          user_query_lists: [
            {
              user_query_list: [{ role: 'user', content: mockFirstLines[i % mockFirstLines.length] }],
              mock_info: {},
              mock_time: null,
            },
          ],
          expected_script: `用户：${mockFirstLines[i % mockFirstLines.length]}\n助手：已处理温度调节请求`,
          nl_assertion: ['助手正确执行温度调节'],
          case_description: `Mock 用例 ${i + 1}。本用例区别于同场景其他用例：侧重 ${mockCaseNames[i % mockCaseNames.length]}`,
          tags: ['温度增减调节'],
          source_scenario_id: scenarioId,
          source_scenario_name: scenarioName,
        }))
        return { cases }
      }

      // ── 用例审核 ──
      case 'case_audit': {
        const caseMatch = params.input?.match(/case_id.*?(\S+)/)
        const caseId = caseMatch?.[1] || 'mock-case-001'
        return {
          id: `audit-${Date.now()}`,
          case_id: caseId,
          audit_pass: defaultAuditPass,
          issues: defaultAuditPass ? [] : [{
            principle: 'K1',
            dimension: '条件泄题',
            severity: 'CRITICAL',
            description: 'Mock 审核问题',
            suggestion: '修复建议',
          }],
          summary: defaultAuditPass ? 'Mock 用例审核通过' : 'Mock 用例审核未通过',
        }
      }

      // ── 用例修复 ──
      case 'fixed_case': {
        const caseMatch = params.input?.match(/case_id.*?(\S+)/)
        const caseId = caseMatch?.[1] || 'mock-case-001'
        return {
          original_id: `orig-${caseId}`,
          original_case_id: caseId,
          fixed_case: {
            dataset_id: 'mock-dataset',
            case_id: caseId,
            context_config: { car_info: { 车速: '30km/h' } },
            max_round: 8,
            user_query_lists: [
              {
                user_query_list: [{ role: 'user', content: '把空调调低两度' }],
                mock_info: {},
                mock_time: '2024-01-15 09:00:00',
              },
            ],
            expected_script: '用户：把空调调低两度\n助手：已将空调温度调低2度',
            nl_assertion: ['助手正确执行温度调节'],
            case_description: 'Mock 修复后用例',
            tags: ['温度增减调节'],
            source_scenario_id: 'scenario-mock-001',
            source_scenario_name: 'Mock 场景',
          },
          audit_rounds: 1,
          final_pass: true,
          remaining_issues: null,
          error: null,
        }
      }

      default:
        console.warn(`[MockClient] 未知 format name: ${formatName}，返回空对象`)
        return {}
    }
  }

  return {
    responses: {
      create: async (params: any) => {
        // 提取 format name
        const formatName = params.text?.format?.json_schema?.name
          || params.text?.format?.name
          || 'unknown'

        const mockData = getMockResponse(formatName, params)
        const outputText = JSON.stringify(mockData)

        // 模拟 OpenAI 响应结构
        return {
          output_text: outputText,
          id: `mock-resp-${Date.now()}`,
          model: params.model || 'mock-model',
          created: Date.now(),
        }
      },
    },
  }
}
