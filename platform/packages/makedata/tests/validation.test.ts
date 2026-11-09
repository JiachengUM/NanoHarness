import { describe, it, expect, beforeEach } from 'vitest'
import {
  validateCaseSchema,
  validateTags,
  validateInteractionChain,
} from '../src/audit/validation'
import { loadTestTagTree, getTestLeafTags, getInvalidLeafTag, getIntermediateNodeTag } from './test-utils'
import type { TagTree } from '../src/core/tag-tree'
import type { CaseWithScenario } from '@eval-platform/database'

describe('Validation', () => {
  let testTree: TagTree
  let leafTags: string[]

  beforeEach(() => {
    testTree = loadTestTagTree()
    leafTags = getTestLeafTags()
  })

  // 构建测试用的有效 case
  const buildValidCase = (): CaseWithScenario => ({
    dataset_id: 'test-dataset',
    case_id: 'test-case-001',
    context_config: { car_info: '车速：30km/h，档位：D' },
    max_round: 8,
    user_query_lists: [
      {
        user_query_list: [{ role: 'user', content: '把空调调低两度' }],
        mock_info: { car_info: { 空调当前状态: '25℃制冷' } },
        mock_time: '2024-01-15 09:00:00',
      },
    ],
    expected_script: '用户：把空调调低两度\n管家：（验证温度调节指令执行结果）\n助手：已将空调温度调低至23℃',
    nl_assertion: ['助手正确识别温度调节指令并执行', '助手反馈执行结果'],
    case_description: '测试空调温度调节功能',
    tags: leafTags.slice(0, 3),
    source_scenario_id: 'scenario-001',
    source_scenario_name: '空调测试场景',
  })

  describe('validateCaseSchema', () => {
    it('should pass for valid case with real vehicle tree tags', () => {
      const testCase = buildValidCase()
      const result = validateCaseSchema(testCase)

      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
      expect(result.info).toContain('C1校验通过')
    })

    it('should fail for missing required fields', () => {
      const testCases = [
        { field: 'dataset_id', value: '', expected: 'dataset_id' },
        { field: 'case_id', value: '', expected: 'case_id' },
      ]

      testCases.forEach(({ field, value, expected }) => {
        const testCase = { ...buildValidCase(), [field]: value } as CaseWithScenario
        const result = validateCaseSchema(testCase)

        expect(result.valid).toBe(false)
        expect(result.errors.length).toBeGreaterThan(0)
        expect(result.errors.some(e => e.includes(expected))).toBe(true)
      })
    })

    it('should fail for invalid max_round', () => {
      const testCases = [
        { max_round: 0, description: 'zero' },
        { max_round: -1, description: 'negative' },
      ]

      testCases.forEach(({ max_round, description }) => {
        const testCase = { ...buildValidCase(), max_round } as CaseWithScenario
        const result = validateCaseSchema(testCase)

        expect(result.valid).toBe(false)
        expect(result.errors.some(e => e.includes('max_round'))).toBe(true)
      })
    })

    it('should fail for empty user_query_lists', () => {
      const testCase = { ...buildValidCase(), user_query_lists: [] } as CaseWithScenario
      const result = validateCaseSchema(testCase)

      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('user_query_lists'))).toBe(true)
    })

    it('should fail for invalid user_query_list structure', () => {
      const testCase = {
        ...buildValidCase(),
        user_query_lists: [
          { user_query_list: [], mock_info: {} }, // 空数组
        ],
      } as CaseWithScenario

      const result = validateCaseSchema(testCase)
      expect(result.valid).toBe(false)
    })

    it('should fail for missing role or content in message', () => {
      const testCase = {
        ...buildValidCase(),
        user_query_lists: [
          {
            user_query_list: [{ role: 'user' }], // 缺少 content
            mock_info: {},
          },
        ],
      } as CaseWithScenario

      const result = validateCaseSchema(testCase)
      expect(result.valid).toBe(false)
    })

    it('should fail for invalid mock_time format', () => {
      const testCase = {
        ...buildValidCase(),
        user_query_lists: [
          {
            user_query_list: [{ role: 'user', content: '测试' }],
            mock_time: '2024-01-15', // 错误格式，应该是 HH:MM:SS
          },
        ],
      } as CaseWithScenario

      const result = validateCaseSchema(testCase)
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('mock_time'))).toBe(true)
    })

    it('should pass for valid mock_time formats', () => {
      const validTimes = [
        '2024-01-15 09:00:00',
        '2024-12-31 23:59:59',
        '2024-06-15 00:00:00',
      ]

      validTimes.forEach(mock_time => {
        const testCase = {
          ...buildValidCase(),
          user_query_lists: [
            {
              user_query_list: [{ role: 'user', content: '测试' }],
              mock_time,
            },
          ],
        } as CaseWithScenario

        const result = validateCaseSchema(testCase)
        expect(result.valid).toBe(true)
      })
    })

    it('should detect schema errors with paths', () => {
      const testCase = {
        ...buildValidCase(),
        max_round: -5,
        case_id: '',
      } as CaseWithScenario

      const result = validateCaseSchema(testCase)
      expect(result.valid).toBe(false)
      expect(result.errors.length).toBeGreaterThanOrEqual(1)
      // 每个错误都应该有路径信息
      result.errors.forEach(error => {
        expect(error).toMatch(/^\[/) // 以 [ 开头
      })
    })
  })

  describe('validateTags', () => {
    it('should pass for valid leaf tags from vehicle tree', () => {
      const result = validateTags(leafTags, testTree)

      expect(result.valid).toBe(true)
      expect(result.info).toContain('D1校验通过')
    })

    it('should fail for non-existent tags', () => {
      const invalidTag = getInvalidLeafTag()
      const result = validateTags([leafTags[0], invalidTag], testTree)

      expect(result.valid).toBe(false)
      expect(result.info).toContain('不在标签树中')
    })

    it('should fail for intermediate node tags', () => {
      const intermediateTag = getIntermediateNodeTag()
      const result = validateTags([intermediateTag], testTree)

      expect(result.valid).toBe(false)
      expect(result.info).toContain('中间节点')
      expect(result.info).toContain('D1')
    })

    it('should fail for empty tags array', () => {
      const result = validateTags([], testTree)

      expect(result.valid).toBe(false)
      expect(result.info).toContain('无tags')
    })

    it('should detect multiple invalid tags at once', () => {
      const mixedTags = [
        leafTags[0],           // 有效
        getInvalidLeafTag(), // 无效：不存在
        getIntermediateNodeTag(), // 无效：中间节点
      ]
      const result = validateTags(mixedTags, testTree)

      expect(result.valid).toBe(false)
      expect(result.info).toContain('不在标签树中')
      expect(result.info).toContain('中间节点')
    })

    it('should validate all leaf tags in vehicle tree', () => {
      const allLeaves = testTree.getLeafTagNames().slice(0, 20)
      const result = validateTags(allLeaves, testTree)

      expect(result.valid).toBe(true)
    })
  })

  describe('validateInteractionChain', () => {
    it('should pass for valid single session', () => {
      const testCase = buildValidCase()
      const result = validateInteractionChain(testCase)

      expect(result.valid).toBe(true)
      expect(result.issues).toHaveLength(0)
    })

    it('should fail for empty user_query_lists', () => {
      const testCase = { ...buildValidCase(), user_query_lists: [] } as CaseWithScenario

      const result = validateInteractionChain(testCase)
      expect(result.valid).toBe(false)
      expect(result.info).toContain('为空')
    })

    it('should detect invalid session structure', () => {
      const testCase = {
        ...buildValidCase(),
        user_query_lists: [
          { user_query_list: 'not-an-array' }, // 错误类型
        ],
      } as CaseWithScenario

      const result = validateInteractionChain(testCase)
      expect(result.valid).toBe(false)
      expect(result.issues.some(i => i.includes('不是数组'))).toBe(true)
    })

    it('should warn for memory-related case with single session', () => {
      const testCase = {
        ...buildValidCase(),
        tags: ['常用地点记忆'], // 记忆相关标签
        user_query_lists: [
          {
            user_query_list: [{ role: 'user', content: '导航去公司' }],
            mock_info: {},
          },
        ],
      } as CaseWithScenario

      const result = validateInteractionChain(testCase)
      // 记忆类场景至少应该给出建议
      expect(result.issues.length).toBeGreaterThan(0)
      expect(result.issues.some(i => i.includes('轮次'))).toBe(true)
    })

    it('should warn for memory case without time indicators in description', () => {
      const testCase = {
        ...buildValidCase(),
        tags: ['常用地点记忆'],
        case_description: '使用常用地点记忆', // 缺少时间词
        user_query_lists: [
          { user_query_list: [{ role: 'user', content: '记住公司' }], mock_info: {} },
          { user_query_list: [{ role: 'user', content: '去公司' }], mock_info: {} },
        ],
      } as CaseWithScenario

      const result = validateInteractionChain(testCase)
      expect(result.issues.some(i => i.includes('时间词') || i.includes('再次') || i.includes('建议'))).toBe(true)
    })

    it('should pass for memory case with multiple sessions and time indicators', () => {
      const testCase = {
        ...buildValidCase(),
        tags: ['常用地点记忆'],
        case_description: '第一会话记录地点，稍后再次使用',
        user_query_lists: [
          {
            user_query_list: [{ role: 'user', content: '记住公司地址是科技园' }],
            mock_info: {},
            mock_time: '2024-01-15 09:00:00',
          },
          {
            user_query_list: [{ role: 'user', content: '导航去我公司' }],
            mock_info: {},
            mock_time: '2024-01-15 18:00:00',
          },
        ],
      } as CaseWithScenario

      const result = validateInteractionChain(testCase)
      expect(result.valid).toBe(true)
    })

    it('should pass for non-memory cases with single session', () => {
      const testCase = {
        ...buildValidCase(),
        tags: ['温度增减调节'], // 非记忆标签
        user_query_lists: [
          { user_query_list: [{ role: 'user', content: '调低温度' }], mock_info: {} },
        ],
      } as CaseWithScenario

      const result = validateInteractionChain(testCase)
      expect(result.valid).toBe(true)
    })
  })

  describe('Combined validation', () => {
    it('should pass all validations for a complete valid case', () => {
      const testCase = buildValidCase()

      const schemaResult = validateCaseSchema(testCase)
      const tagsResult = validateTags(testCase.tags || [], testTree)
      const chainResult = validateInteractionChain(testCase)

      expect(schemaResult.valid).toBe(true)
      expect(tagsResult.valid).toBe(true)
      expect(chainResult.valid).toBe(true)
    })

    it('should detect multiple issues in invalid case', () => {
      const testCase = {
        dataset_id: '', // 无效
        case_id: '',    // 无效
        context_config: {},
        max_round: -1,  // 无效
        user_query_lists: [], // 无效
        expected_script: '',
        nl_assertion: [],
        case_description: '',
        tags: [],       // 无效
        source_scenario_id: 'scenario-001',
        source_scenario_name: '测试',
      } as CaseWithScenario

      const schemaResult = validateCaseSchema(testCase)
      const tagsResult = validateTags(testCase.tags || [], testTree)
      const chainResult = validateInteractionChain(testCase)

      expect(schemaResult.valid).toBe(false)
      expect(tagsResult.valid).toBe(false)
      expect(chainResult.valid).toBe(false)
    })
  })
})
