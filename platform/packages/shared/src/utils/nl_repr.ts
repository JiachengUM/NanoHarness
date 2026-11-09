export class NLReprError extends Error {
  public readonly obj: unknown
  public reason: string

  constructor(obj: unknown, reason: string) {
    super()
    this.name = 'NLReprError'
    this.obj = obj
    this.reason = reason
  }

  public override toString(): string {
    return `nl_repr转换失败, 输入: ${String(this.obj)}，原因: ${this.reason}`
  }
}

export type NLReprHandler<T = unknown> = (obj: T, options?: NLReprOptions) => string
export type Constructor<T = unknown> = abstract new (...args: never[]) => T

const typeRegistry = new Map<Constructor, NLReprHandler>()

let boolTrueText = 'True'
let boolFalseText = 'False'

export function setBoolTexts(trueText: string, falseText: string): void {
  boolTrueText = trueText
  boolFalseText = falseText
}

export function registerBoolTexts(trueText: string, falseText: string): void {
  setBoolTexts(trueText, falseText)
}

export interface ListFormatParams {
  separator: string
  numbering: string
  useNumbering: boolean
  start: number
  prefix: string
  suffix: string
}

const defaultListParams: ListFormatParams = {
  separator: '\n',
  numbering: '{i}. ',
  useNumbering: true,
  start: 1,
  prefix: '',
  suffix: '',
}

export function setListParams(params: Partial<ListFormatParams>): void {
  Object.assign(defaultListParams, params)
}

export function registerListParams(params: Partial<ListFormatParams>): void {
  setListParams(params)
}

export interface DictFormatOptions {
  itemSeparator?: string
  keyValueSeparator?: string
  keyPrefix?: string
  keySuffix?: string
  valuePrefix?: string
  valueSuffix?: string
  showEmpty?: boolean
  sortKeys?: boolean
  noneText?: string
}

export type NLReprOptions = Partial<ListFormatParams> & DictFormatOptions

export function register<T>(clsType: Constructor<T>, handler: NLReprHandler<T>): NLReprHandler<T>
export function register<T>(clsType: Constructor<T>): (handler: NLReprHandler<T>) => NLReprHandler<T>
export function register<T>(
  clsType: Constructor<T>,
  handler?: NLReprHandler<T>,
): NLReprHandler<T> | ((inner: NLReprHandler<T>) => NLReprHandler<T>) {
  if (handler) {
    typeRegistry.set(clsType, handler as NLReprHandler)
    return handler
  }

  return (inner: NLReprHandler<T>) => {
    typeRegistry.set(clsType, inner as NLReprHandler)
    return inner
  }
}

function isPlainObject(x: unknown): x is Record<string, unknown> {
  if (x === null || typeof x !== 'object') {
    return false
  }
  const proto = Object.getPrototypeOf(x)
  return proto === Object.prototype || proto === null
}

function nlReprList(
  list: unknown[],
  nlReprFunc: (x: unknown, options?: NLReprOptions) => string,
  options?: NLReprOptions,
): string {
  const separator = options?.separator ?? defaultListParams.separator
  const numbering = options?.numbering ?? defaultListParams.numbering
  const useNumbering = options?.useNumbering ?? defaultListParams.useNumbering
  const start = options?.start ?? defaultListParams.start
  const prefix = options?.prefix ?? defaultListParams.prefix
  const suffix = options?.suffix ?? defaultListParams.suffix

  if (list.length === 0) {
    return '无'
  }

  const itemStrings = list.map((item, idx) => {
    let itemText: string
    try {
      itemText = nlReprFunc(item, options)
    } catch (error) {
      if (error instanceof NLReprError) {
        error.reason = `\n列表项${idx}发生错误: \n${error.reason}`
      }
      throw error
    }

    const wrapped = `${prefix}${itemText}${suffix}`
    if (!useNumbering) {
      return wrapped
    }
    return `${numbering.replace('{i}', String(idx + start))}${wrapped}`
  })

  const result = itemStrings.join(separator)
  if (separator === '\n' && result && list.length > 1) {
    return `\n${result}`
  }
  return result
}

function nlReprDict(
  obj: Record<string, unknown>,
  nlReprFunc: (x: unknown, options?: NLReprOptions) => string,
  options?: NLReprOptions,
): string {
  const itemSeparator = options?.itemSeparator ?? '\n'
  const keyValueSeparator = options?.keyValueSeparator ?? ': '
  const keyPrefix = options?.keyPrefix ?? ''
  const keySuffix = options?.keySuffix ?? ''
  const valuePrefix = options?.valuePrefix ?? ''
  const valueSuffix = options?.valueSuffix ?? ''
  const showEmpty = options?.showEmpty ?? true
  const sortKeys = options?.sortKeys ?? true
  const noneText = options?.noneText ?? '无'

  const entries = Object.entries(obj)
  if (entries.length === 0) {
    return showEmpty ? '无' : ''
  }

  if (sortKeys) {
    entries.sort(([a], [b]) => a.localeCompare(b))
  }

  const lines = entries.map(([key, value]) => {
    let keyText: string
    try {
      keyText = nlReprFunc(key, options)
    } catch (error) {
      if (error instanceof NLReprError) {
        error.reason = `\n字典key ${JSON.stringify(key)} 发生错误: \n${error.reason}`
      }
      throw error
    }

    let valueText: string
    if (value === null || value === undefined) {
      valueText = noneText
    } else {
      try {
        valueText = nlReprFunc(value, options)
      } catch (error) {
        if (error instanceof NLReprError) {
          error.reason = `\n字典key ${JSON.stringify(key)} 的value发生错误: \n${error.reason}`
        }
        throw error
      }
    }

    return `${keyPrefix}${keyText}${keySuffix}${keyValueSeparator}${valuePrefix}${valueText}${valueSuffix}`
  })

  return lines.join(itemSeparator)
}

type NLReprMethodOwner = {
  __nl_repr__?: (options?: NLReprOptions) => string
}

export function nlRepr(x: unknown, options?: NLReprOptions): string {
  if (x && typeof x === 'object') {
    const method = (x as NLReprMethodOwner).__nl_repr__
    if (method !== undefined) {
      if (typeof method !== 'function') {
        throw new NLReprError(x, `__nl_repr__ must be callable, got ${typeof method}`)
      }
      const result = method.call(x, options)
      if (typeof result !== 'string') {
        throw new NLReprError(x, `__nl_repr__()必须返回string, 不能是${typeof result}`)
      }
      return result
    }
  }

  if (x !== null && x !== undefined) {
    const ctor = (x as { constructor?: Constructor }).constructor
    const handler = ctor ? typeRegistry.get(ctor) : undefined
    if (handler) {
      const result = handler(x, options)
      if (typeof result !== 'string') {
        throw new NLReprError(x, `registered handler must return string, got ${typeof result}`)
      }
      return result
    }
  }

  if (typeof x === 'string') {
    return x
  }
  if (typeof x === 'boolean') {
    return x ? boolTrueText : boolFalseText
  }
  if (typeof x === 'number') {
    return String(x)
  }
  if (Array.isArray(x)) {
    return nlReprList(x, nlRepr, options)
  }
  if (isPlainObject(x)) {
    return nlReprDict(x, nlRepr, options)
  }
  if (x instanceof Error) {
    return `错误: ${x.name}: ${x.message}`
  }

  throw new NLReprError(x, `对于类型${Object.prototype.toString.call(x)}未实现nl_repr, 值为${String(x)}`)
}

export function nlReprSafe(x: unknown, options?: NLReprOptions): string {
  try {
    return nlRepr(x, options)
  } catch (error) {
    if (error instanceof NLReprError) {
      return String(x)
    }
    throw error
  }
}
