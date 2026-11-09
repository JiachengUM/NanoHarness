import type {
  VoiceEvent,
  VoicePhase,
  VoiceState,
} from './voiceTypes'

const knownVoicePhases: ReadonlySet<VoicePhase> = new Set([
  'idle',
  'mic_pending',
  'listening',
  'processing',
  'speaking',
  'interrupted',
  'error',
])

function normalizeVoicePhase(value: unknown, fallback: VoicePhase): VoicePhase {
  return typeof value === 'string' && knownVoicePhases.has(value as VoicePhase)
    ? (value as VoicePhase)
    : fallback
}

export function initialVoiceState(): VoiceState {
  return {
    phase: 'idle',
    microphoneOpen: false,
    inputLocked: false,
    draftText: '',
    stashedTextInput: '',
  }
}

export function openVoiceDraft(state: VoiceState, currentInput: string): VoiceState {
  return {
    ...state,
    phase: 'mic_pending',
    microphoneOpen: false,
    inputLocked: true,
    draftText: '',
    stashedTextInput: currentInput,
  }
}

export function closeVoiceDraftWithoutFinal(state: VoiceState): VoiceState {
  return {
    ...state,
    phase: 'idle',
    microphoneOpen: false,
    inputLocked: false,
    draftText: state.stashedTextInput,
    stashedTextInput: '',
  }
}

export function applyVoiceEvent(state: VoiceState, event: VoiceEvent): VoiceState {
  switch (event.type) {
    case 'voice.ready':
    case 'voice.feedback':
    case 'voice.playback.duck':
    case 'voice.playback.restore':
    case 'voice.submit.failed':
      return state

    case 'voice.phase': {
      const phase = normalizeVoicePhase(event.payload.phase, state.phase)
      const microphoneOpen = phase === 'listening' ? true : state.microphoneOpen
      return {
        ...state,
        phase,
        microphoneOpen,
        inputLocked: phase === 'mic_pending' || microphoneOpen,
      }
    }

    case 'voice.asr.delta':
      return {
        ...state,
        phase: 'listening',
        microphoneOpen: true,
        inputLocked: true,
        draftText: event.payload.text,
      }

    case 'voice.asr.final':
      return {
        ...state,
        phase: 'processing',
        inputLocked: state.microphoneOpen,
        draftText: '',
        stashedTextInput: '',
      }

    case 'voice.interrupted':
      return {
        ...state,
        phase: 'interrupted',
        inputLocked: state.microphoneOpen,
      }

    case 'voice.error':
      return {
        ...state,
        phase: 'error',
        microphoneOpen: false,
        inputLocked: false,
        draftText: state.stashedTextInput,
        stashedTextInput: '',
      }
  }
}
