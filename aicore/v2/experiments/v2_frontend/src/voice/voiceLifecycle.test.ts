import { describe, expect, it, vi } from 'vitest'
import {
  applyPlaybackActiveChangeForSession,
  closeActiveVoiceSession,
  createVoiceEventHandlerForSession,
  ensureVoiceAudioInstance,
  runVoiceStartupSequence,
  startTextTurnVoiceFlow,
} from './voiceLifecycle'
import { initialVoiceState, openVoiceDraft } from './voiceReducer'
import type { VoiceEvent } from './voiceTypes'

function setupHandler() {
  const actions: unknown[] = []
  const applied: VoiceEvent[] = []
  const liveInputs: string[] = []
  const ducked: boolean[] = []
  const playbackIds: Array<string | undefined> = []
  const toasts: string[] = []
  let resets = 0
  let stops = 0
  let currentSeq = 3
  const handler = createVoiceEventHandlerForSession({
    seq: 3,
    getCurrentSeq: () => currentSeq,
    applyEvent: (event) => applied.push(event),
    setLiveInput: (input) => liveInputs.push(input),
    dispatchConsoleAction: (action) => actions.push(action),
    stopLocalAudio: () => { stops += 1 },
    setPlaybackDucked: (value) => ducked.push(value),
    setPlaybackAssistantMessageId: (value) => playbackIds.push(value),
    resetPlaybackSchedule: () => { resets += 1 },
    showToast: (message) => toasts.push(message),
    now: () => '2026-07-16T00:00:00Z',
  })
  return {
    actions,
    applied,
    liveInputs,
    ducked,
    playbackIds,
    toasts,
    handler,
    setCurrentSeq: (value: number) => { currentSeq = value },
    resetCount: () => resets,
    stopCount: () => stops,
  }
}

describe('voice event handler', () => {
  it('projects ASR final directly with the backend Agent ids', () => {
    const runtime = setupHandler()
    runtime.handler({
      v: 1,
      kind: 'voice',
      type: 'voice.asr.final',
      payload: {
        turn_id: 'turn-1',
        user_message_id: 'user-1',
        assistant_message_id: 'assistant-1',
        text: '查一下天气',
      },
    })
    expect(runtime.actions).toEqual([{
      type: 'appendVoiceUserMessage',
      turnId: 'turn-1',
      userMessageId: 'user-1',
      assistantMessageId: 'assistant-1',
      text: '查一下天气',
      timestamp: '2026-07-16T00:00:00Z',
    }])
    expect(runtime.liveInputs).toEqual([''])
  })

  it('ducks, restores, and clears playback on interruption', () => {
    const runtime = setupHandler()
    runtime.handler({ v: 1, kind: 'voice', type: 'voice.playback.duck', payload: {} })
    runtime.handler({ v: 1, kind: 'voice', type: 'voice.playback.restore', payload: {} })
    runtime.handler({
      v: 1,
      kind: 'voice',
      type: 'voice.interrupted',
      payload: { reason: 'barge_in' },
    })
    expect(runtime.ducked).toEqual([true, false, false])
    expect(runtime.resetCount()).toBe(1)
    expect(runtime.playbackIds).toEqual([undefined])
  })

  it('surfaces errors and ignores stale session events', () => {
    const runtime = setupHandler()
    runtime.handler({
      v: 1,
      kind: 'voice',
      type: 'voice.error',
      payload: { message: '语音失败' },
    })
    expect(runtime.stopCount()).toBe(1)
    expect(runtime.toasts).toEqual(['语音失败'])

    runtime.setCurrentSeq(4)
    runtime.handler({
      v: 1,
      kind: 'voice',
      type: 'voice.asr.delta',
      payload: { text: '迟到事件' },
    })
    expect(runtime.applied).toHaveLength(1)
  })
})

describe('voice lifecycle helpers', () => {
  it('notifies the backend only for completed playback', async () => {
    const active: boolean[] = []
    const ids: Array<string | undefined> = []
    const notify = vi.fn(async () => undefined)
    applyPlaybackActiveChangeForSession({
      active: false,
      completed: true,
      seq: 1,
      getCurrentSeq: () => 1,
      setPlaybackActive: (value) => active.push(value),
      setPlaybackAssistantMessageId: (value) => ids.push(value),
      notifyVoicePlaybackEnded: notify,
    })
    await Promise.resolve()
    expect(active).toEqual([false])
    expect(ids).toEqual([undefined])
    expect(notify).toHaveBeenCalledOnce()
  })

  it('shares one audio initialization and starts capture once', async () => {
    const capture = vi.fn()
    const audio = {
      init: vi.fn(async () => undefined),
      startCapture: vi.fn(),
      stop: vi.fn(),
    }
    const audioRef = { current: null as typeof audio | null }
    const initPromiseRef = { current: null as Promise<typeof audio> | null }
    const args = {
      audioRef,
      initPromiseRef,
      createAudio: () => audio,
      onCaptureChunk: capture,
    }
    const [first, second] = await Promise.all([
      ensureVoiceAudioInstance(args),
      ensureVoiceAudioInstance(args),
    ])
    expect(first).toBe(audio)
    expect(second).toBe(audio)
    expect(audio.init).toHaveBeenCalledOnce()
    expect(audio.startCapture).toHaveBeenCalledOnce()
  })

  it('closes local and backend voice while restoring text', async () => {
    const state = openVoiceDraft(initialVoiceState(), '保留输入')
    const audio = { setListening: vi.fn(), stop: vi.fn() }
    const liveClient = {
      closeVoiceMicrophone: vi.fn(async () => undefined),
      stopVoice: vi.fn(async () => undefined),
    }
    const states: unknown[] = []
    const inputs: string[] = []
    const seqRef = { current: 1 }
    closeActiveVoiceSession({
      voiceState: state,
      voiceSessionSeqRef: seqRef,
      voiceAudioRef: { current: audio },
      voiceAudioInitPromiseRef: { current: null },
      liveClient,
      setVoiceState: (value) => states.push(value),
      setLiveInput: (value) => inputs.push(value),
    })
    await Promise.resolve()
    await Promise.resolve()
    expect(seqRef.current).toBe(2)
    expect(audio.stop).toHaveBeenCalledOnce()
    expect(inputs).toEqual(['保留输入'])
    expect(liveClient.closeVoiceMicrophone).toHaveBeenCalledOnce()
    expect(liveClient.stopVoice).toHaveBeenCalledOnce()
  })

  it('starts backend voice before opening the microphone', async () => {
    const order: string[] = []
    const audio = {
      resetPlaybackSchedule: () => order.push('reset'),
      setListening: (value: boolean) => order.push(`listening:${value}`),
      playTtsChunk: vi.fn(),
    }
    const liveClient = {
      startVoice: vi.fn(async () => { order.push('start') }),
      openVoiceMicrophone: vi.fn(async () => { order.push('open') }),
      closeVoiceMicrophone: vi.fn(async () => undefined),
      stopVoice: vi.fn(async () => undefined),
    }
    await runVoiceStartupSequence({
      seq: 1,
      isCurrent: () => true,
      ensureVoiceAudio: async () => audio,
      liveClient,
      onAgentEvent: vi.fn(),
      onVoiceEvent: vi.fn(),
      onVoiceError: vi.fn(),
      restoreVoiceDraft: vi.fn(),
    })
    expect(order).toEqual(['reset', 'start', 'open', 'listening:true'])
  })

  it('starts one Agent run and only initializes voice output for a text turn', async () => {
    const order: string[] = []
    const startAgentRun = vi.fn(() => { order.push('agent') })
    const startVoiceOutput = vi.fn(async () => { order.push('voice-output') })
    const onVoiceOutputError = vi.fn()

    startTextTurnVoiceFlow({
      startAgentRun,
      startVoiceOutput,
      onVoiceOutputError,
    })
    await Promise.resolve()

    expect(order).toEqual(['agent', 'voice-output'])
    expect(startAgentRun).toHaveBeenCalledOnce()
    expect(startVoiceOutput).toHaveBeenCalledOnce()
    expect(onVoiceOutputError).not.toHaveBeenCalled()
  })
})
