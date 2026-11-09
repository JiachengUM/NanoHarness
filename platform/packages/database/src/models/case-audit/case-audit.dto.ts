import { z } from 'zod'
import { CaseWithScenarioSchema } from '../dataset-item/dataset-item.dto'

// ═══════════════════════════════════════════════════════════════════════════
// 审核 Schema (Case Audit)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 审核严重程度 Enum
 */
export const AuditSeveritySchema = z.enum(['CRITICAL', 'MAJOR', 'MINOR'])

/**
 * 审核维度 Enum
 */
export const AuditDimensionSchema = z.enum([
  '记忆泄题',
  '断言质量',
  '用户台词脏',
  '标签乱打',
  '主场穿帮',
  '结构错',
  '感知边界',
  '格式问题',
  '剧本套话',
  '条件泄题',
  '系统错误',
])

/**
 * 审核单个 Issue Schema
 */
export const AuditIssueSchema = z.object({
  principle: z.string().min(1, '违反的原则编号不能为空'),
  dimension: AuditDimensionSchema,
  severity: AuditSeveritySchema,
  description: z.string().min(1, '问题描述不能为空'),
  suggestion: z.string().min(1, '改写建议不能为空'),
})

/**
 * 审核结果 Schema
 */
export const CaseAuditResultSchema = z.object({
  id: z.string().min(1),
  case_id: z.string().min(1),
  audit_pass: z.boolean(),
  issues: z.array(AuditIssueSchema).default([]),
  summary: z.string().min(1, '审核结论不能为空'),
})

/**
 * 修复后结果 Schema
 */
export const FixedCaseResultSchema = z.object({
  original_id: z.string().min(1),
  original_case_id: z.string().min(1),
  fixed_case: CaseWithScenarioSchema,
  audit_rounds: z.number().int().nonnegative(),
  final_pass: z.boolean(),
  remaining_issues: z.array(AuditIssueSchema).nullable().optional(),
  error: z.string().nullable().optional(),
})

// ═══════════════════════════════════════════════════════════════════════════
// 类型导出
// ═══════════════════════════════════════════════════════════════════════════

export type AuditSeverity = z.infer<typeof AuditSeveritySchema>
export type AuditDimension = z.infer<typeof AuditDimensionSchema>
export type AuditIssue = z.infer<typeof AuditIssueSchema>
export type CaseAuditResult = z.infer<typeof CaseAuditResultSchema>
export type FixedCaseResult = z.infer<typeof FixedCaseResultSchema>
