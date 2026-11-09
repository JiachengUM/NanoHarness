import { describe, expect, it } from 'vitest'
import {
  applyVoiceEvent,
  closeVoiceDraftWithoutFinal,
  initialVoiceState,
  openVoiceDraft,
} from './voiceReducer'
import type { VoiceEvent, VoiceState } from './voiceTypes'

function event<T extends VoiceEvent>(value: T): T {
  return value
}

describe('voiceReducer', () => {
  it('opens a locked microphone draft', () => {
    const initial = initialVoiceState()
    expect(initial).toEqual({
      phase: 'idle',
      microphoneOpen: false,
      inputLocked: false,
      draftText: '',
      stashedTextInput: '',
    })

    expect(openVoiceDraft(initial, '保留输入')).toEqual({
      ...initial,
      phase: 'mic_pending',
      inputLocked: true,
      stashedTextInput: '保留输入',
    })
  })

  it('restores the stashed input when voice closes without a final', () => {
    const opened = openVoiceDraft(initialVoiceState(), '保留输入')
    expect(closeVoiceDraftWithoutFinal(opened)).toEqual({
      ...initialVoiceState(),
      draftText: '保留输入',
    })
  })

  it('projects ASR draft and final phases', () => {
    const listening = applyVoiceEvent(initialVoiceState(), event({
      v: 1,
      kind: 'voice',
      type: 'voice.asr.delta',
      payload: { text: '查一下天气' },
    }))
    expect(listening).toMatchObject({
      phase: 'listening',
      microphoneOpen: true,
      inputLocked: true,
      draftText: '查一下天气',
    })

    const processing = applyVoiceEvent(listening, event({
      v: 1,
      kind: 'voice',
      type: 'voice.asr.final',
      payload: {
        turn_id: 'turn-1',
        user_message_id: 'user-1',
        assistant_message_id: 'assistant-1',
        text: '查一下天气',
      },
    }))
    expect(processing).toMatchObject({
      phase: 'processing',
      microphoneOpen: true,
      inputLocked: true,
      draftText: '',
    })
  })

  it('projects interruption and resets safely on errors', () => {
    const listening: VoiceState = {
      ...initialVoiceState(),
      phase: 'listening',
      microphoneOpen: true,
      inputLocked: true,
      stashedTextInput: '保留输入',
    }
    const interrupted = applyVoiceEvent(listening, event({
      v: 1,
      kind: 'voice',
      type: 'voice.interrupted',
      payload: { reason: 'barge_in' },
    }))
    expect(interrupted.phase).toBe('interrupted')

    const failed = applyVoiceEvent(interrupted, event({
      v: 1,
      kind: 'voice',
      type: 'voice.error',
      payload: { message: '失败' },
    }))
    expect(failed).toMatchObject({
      phase: 'error',
      microphoneOpen: false,
      inputLocked: false,
      draftText: '保留输入',
    })
  })
})
