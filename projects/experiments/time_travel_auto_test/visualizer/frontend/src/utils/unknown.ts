/** unknown 兜底解析工具（对齐 v2_frontend 的 utils/unknown.ts 模式）。 */

export function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

export function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

export function asBoolean(value: unknown, fallback = false): boolean {
  return typeof value === 'boolean' ? value : fallback
}

export function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }
  return value as Record<string, unknown>
}

export function asOptionalString(value: unknown): string | undefined {
  const result = asString(value)
  return result === '' ? undefined : result
}

export function asOptionalNumber(value: unknown): number | undefined {
  return asNumber(value)
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}
