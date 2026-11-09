import { describe, expect, it } from 'vitest'
import {
  createDuplexExpressionFrame,
  semanticReadingFromTranscript,
} from './duplexExpressionDirector'

describe('duplexExpressionDirector', () => {
  it('turns an ASR question into a focused, open semantic reading', () => {
    const neutral = semanticReadingFromTranscript('')
    const question = semanticReadingFromTranscript('我们现在应该怎么修复这个问题？')

    expect(question.confidence).toBeGreaterThan(neutral.confidence)
    expect(question.vector.openness).toBeGreaterThan(neutral.vector.openness)
    expect(question.vector.focus).toBeGreaterThan(neutral.vector.focus)
  })

  it('keeps backend voicePhase authoritative for the visual mode', () => {
    expect(createDuplexExpressionFrame({
      acoustics: null,
      connected: true,
      transcript: '请继续',
      voicePhase: 'processing',
    })).toMatchObject({ mode: 'think', botState: 'think' })

    expect(createDuplexExpressionFrame({
      acoustics: null,
      connected: true,
      transcript: '请继续',
      voicePhase: 'speaking',
    })).toMatchObject({ mode: 'speak', botState: 'focus' })
  })

  it('forces a silent frame when Duplex is offline', () => {
    const frame = createDuplexExpressionFrame({
      acoustics: null,
      connected: false,
      transcript: '这段文字不能让离线粒子继续表达',
      voicePhase: 'speaking',
    })

    expect(frame.mode).toBe('silent')
    expect(frame.expression.energy).toBe(0.08)
    expect(frame.expression.pulse).toBe(0)
  })
})
