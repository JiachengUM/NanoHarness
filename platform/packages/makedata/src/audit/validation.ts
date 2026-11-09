/**
 * 程序化校验 - 用于审核前的预检查
 *
 * 包括：
 * - C1: Schema 结构校验
 * - C3: 交互链校验
 * - D1/D2: 标签合规校验
 */

import { DatasetItemSchema } from '@eval-platform/database'
import type { CaseWithScenario } from '@eval-platform/database'
import type { TagTree } from '../core/tag-tree.js'

/**
 * 程序化 Schema 验证 - C1原则
 * 验证 case 是否符合 DatasetItemSchema 定义
 */
export function validateCaseSchema(caseItem: CaseWithScenario): { valid: boolean; info: string; errors: string[] } {
  const result = DatasetItemSchema.safeParse(caseItem)

  if (result.success) {
    return { valid: true, info: 'Case 结构符合 DatasetItemSchema，C1校验通过。', errors: [] }
  }

  // 兼容 Zod 4 的错误格式
  const errorIssues = (result.error as any).issues || []
  const errors = errorIssues.map((err: any) => {
    const path = err.path?.length > 0 ? err.path.join('.') : 'root'
    return `[${path}] ${err.message}`
  })

  return {
    valid: false,
    info: `Case 结构不符合 DatasetItemSchema，发现 ${errors.length} 处错误：\n${errors.join('\n')}`,
    errors,
  }
}

/**
 * 验证交互链连贯性 - C3原则
 * 检查对话流程是否符合规范：
 * 1. 多轮对话中每轮的上下文应连贯
 * 2. 记忆类场景应有生产→消费的闭环
 */
export function validateInteractionChain(caseItem: CaseWithScenario): { valid: boolean; info: string; issues: string[] } {
  const issues: string[] = []
  const { user_query_lists, tags = [], case_description = '' } = caseItem

  // 检查1：user_query_lists 不能为空
  if (!user_query_lists || user_query_lists.length === 0) {
    issues.push('user_query_lists 为空，缺少对话内容')
    return { valid: false, info: issues.join('\n'), issues }
  }

  // 检查2：每轮对话结构正确性（user_query_list 必须是数组）
  for (let i = 0; i < user_query_lists.length; i++) {
    const session = user_query_lists[i]
    if (typeof session !== 'object' || session === null) {
      issues.push(`第${i + 1}轮对话格式错误：不是对象`)
      continue
    }

    const roundConfig = session as { user_query_list?: unknown; mock_info?: unknown; mock_time?: string }

    if (!Array.isArray(roundConfig.user_query_list)) {
      issues.push(`第${i + 1}轮对话格式错误：user_query_list 不是数组`)
    } else if (roundConfig.user_query_list.length === 0) {
      issues.push(`第${i + 1}轮对话格式错误：user_query_list 为空数组`)
    }
  }

  // 检查3：记忆类场景的闭环检查
  const memoryRelatedTags = ['长期记忆调用', '短期记忆调用', '常用地点记忆', '历史行程记忆']
  const isMemoryRelated = tags.some(tag => memoryRelatedTags.some(m => tag.includes(m)))

  if (isMemoryRelated) {
    // 检查是否有足够轮次（记忆类通常需要至少2轮：生产+消费）
    if (user_query_lists.length < 2) {
      issues.push('记忆类场景至少需要2轮对话（生产轮+消费轮），当前轮次不足')
    }

    // 检查 case_description 是否暗示了闭环
    const descLower = case_description.toLowerCase()
    if (!descLower.includes('再次') && !descLower.includes('之后') && !descLower.includes('稍后')) {
      // 软性提示，不作为硬性错误
      issues.push('【建议】记忆类场景建议在描述中明确体现"再次/之后/稍后"等时间词，以表明是独立会话的调用')
    }
  }

  if (issues.length === 0) {
    return { valid: true, info: '交互链结构检查通过，C3校验通过。', issues: [] }
  }

  return { valid: false, info: `交互链检查发现问题：\n${issues.join('\n')}`, issues }
}

/**
 * 验证标签（D1/D2原则）
 */
export function validateTags(tags: string[], tagTree: TagTree): { valid: boolean; info: string } {
  if (!tags || tags.length === 0) {
    return { valid: false, info: '该case无tags，跳过标签校验。' }
  }

  const leafNames = new Set(tagTree.getLeafTagNames())
  const allNodeNames = new Set(tagTree.root.iterNodes().map(n => n.name))

  const notInTree = tags.filter(t => !allNodeNames.has(t))
  const nonLeaf = tags.filter(t => allNodeNames.has(t) && !leafNames.has(t))

  const issues: string[] = []

  if (notInTree.length > 0) {
    issues.push(`以下标签不在标签树中（可能是拼写错误或已废弃）：${notInTree.join(', ')}`)
  }
  if (nonLeaf.length > 0) {
    issues.push(`以下标签是中间节点（非叶子），违反D1只打叶子节点原则：${nonLeaf.join(', ')}`)
  }

  if (issues.length === 0) {
    return { valid: true, info: '所有标签均为合法叶子节点，D1校验通过。' }
  }

  return { valid: false, info: issues.join('\n') }
}
