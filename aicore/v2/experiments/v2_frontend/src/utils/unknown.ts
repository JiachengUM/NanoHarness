export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

export function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

/**
 * 达成判据（success_check）→ 展示用文本。
 *
 * 判据在计划里是强类型联合（kind + expression / assertions），事件与旧 payload 里则可能是
 * 裸字符串；两种都认，UI 只需拿一个能显示的句子。
 */
export function formatCriterion(value: unknown): string {
  if (typeof value === 'string') return value
  const record = asRecord(value)
  const expression = asString(record.expression)
  if (expression) return expression
  const assertions = record.assertions
  if (Array.isArray(assertions)) {
    return assertions.filter((item) => typeof item === 'string').join('；')
  }
  return ''
}

export function asNumber(value: unknown, fallback?: number): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export function formatDetailValue(value: unknown): string {
  if (value === undefined || value === null || value === '') return '无'
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}
