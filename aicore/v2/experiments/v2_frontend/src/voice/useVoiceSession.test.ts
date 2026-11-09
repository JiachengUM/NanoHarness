import { describe, expect, it } from 'vitest'
import { nextVoiceTranscript } from './useVoiceSession'
import type { VoiceEvent } from './voiceTypes'

function event(value: VoiceEvent): VoiceEvent {
  return value
}

describe('nextVoiceTranscript', () => {
  it('accumulates ASR deltas and lets the final transcript replace them', () => {
    const first = nextVoiceTranscript('', event({
      kind: 'voice',
      payload: { text: '上海' },
      type: 'voice.asr.delta',
      v: 1,
    }))
    const second = nextVoiceTranscript(first, event({
      kind: 'voice',
      payload: { text: '天气' },
      type: 'voice.asr.delta',
      v: 1,
    }))
    const final = nextVoiceTranscript(second, event({
      kind: 'voice',
      payload: {
        text: '上海天气怎么样？',
        turn_id: 'turn-1',
        user_message_id: 'user-1',
      },
      type: 'voice.asr.final',
      v: 1,
    }))

    expect(second).toBe('上海天气')
    expect(final).toBe('上海天气怎么样？')
  })

  it('clears the previous turn when Duplex starts listening again', () => {
    expect(nextVoiceTranscript('上一轮问题', event({
      kind: 'voice',
      payload: { phase: 'listening' },
      type: 'voice.phase',
      v: 1,
    }))).toBe('')
  })
})
