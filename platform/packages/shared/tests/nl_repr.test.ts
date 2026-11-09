import { describe, it, expect } from 'vitest'
import { nlRepr, nlReprSafe, register, setBoolTexts, setListParams } from '../src/utils/nl_repr'

class CustomData {
  constructor(public readonly value: number) {}
}

class WithNLRepr {
  constructor(private readonly name: string) {}

  public __nl_repr__(): string {
    return `名字: ${this.name}`
  }
}

describe('nlRepr', () => {
  it('should format basic list', () => {
    expect(nlRepr([1, 2, 3])).toBe('\n1. 1\n2. 2\n3. 3')
  })

  it('should format dict with null handling and sorted keys', () => {
    expect(nlRepr({ b: null, a: 1 })).toBe('a: 1\nb: 无')
  })

  it('should use __nl_repr__ method', () => {
    expect(nlRepr(new WithNLRepr('小明'))).toBe('名字: 小明')
  })

  it('should use registered type handler', () => {
    register(CustomData, (obj) => `自定义: ${obj.value}`)
    expect(nlRepr(new CustomData(42))).toBe('自定义: 42')
  })

  it('should use configured bool texts', () => {
    setBoolTexts('是', '否')
    expect(nlRepr(true)).toBe('是')
    expect(nlRepr(false)).toBe('否')
  })

  it('should use configured list params', () => {
    setListParams({ separator: '、', numbering: '({i}) ', useNumbering: true })
    expect(nlRepr(['A', 'B'])).toBe('(1) A、(2) B')
  })

  it('should allow local override of list params', () => {
    expect(nlRepr(['A', 'B'], { separator: ' | ', useNumbering: false })).toBe('A | B')
  })
})

describe('nlReprSafe', () => {
  it('should fallback to String() on error', () => {
    expect(nlReprSafe(Symbol('x'))).toBe('Symbol(x)')
  })
})
