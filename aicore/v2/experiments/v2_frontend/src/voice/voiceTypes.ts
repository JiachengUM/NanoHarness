export type VoicePhase =
  | 'idle'
  | 'mic_pending'
  | 'listening'
  | 'processing'
  | 'speaking'
  | 'interrupted'
  | 'error'

export function isVoiceInputActive(phase: VoicePhase): boolean {
  return phase === 'mic_pending' || phase === 'listening'
}

export type VoiceFeedbackMode = 'duplex'

export type VoiceEventType =
  | 'voice.ready'
  | 'voice.phase'
  | 'voice.asr.delta'
  | 'voice.asr.final'
  | 'voice.feedback'
  | 'voice.playback.duck'
  | 'voice.playback.restore'
  | 'voice.submit.failed'
  | 'voice.interrupted'
  | 'voice.error'

type ExtensibleVoicePayload = Record<string, unknown>

interface BaseVoiceEvent<
  TType extends VoiceEventType,
  TPayload extends ExtensibleVoicePayload,
> {
  v: 1
  kind: 'voice'
  type: TType
  payload: TPayload
}

export type VoiceReadyPayload = ExtensibleVoicePayload & {
  input_sample_rate?: number
  output_sample_rate?: number
  output_format?: 'f32le'
}

export type VoicePhasePayload = ExtensibleVoicePayload & {
  phase: VoicePhase
}

export type VoiceAsrDeltaPayload = ExtensibleVoicePayload & {
  text: string
}

export type VoiceAsrFinalPayload = ExtensibleVoicePayload & {
  turn_id: string
  user_message_id: string
  text: string
  assistant_message_id?: string
}

export type VoiceFeedbackPayload = ExtensibleVoicePayload & {
  turn_id: string | null
  feedback_id: string
  text: string
  mode: VoiceFeedbackMode
}

export type VoiceSubmitFailedPayload = ExtensibleVoicePayload & {
  turn_id: string
  user_message_id: string
  assistant_message_id: string
  code: 'AGENT_SUBMIT_FAILED'
}

export type VoiceInterruptedPayload = ExtensibleVoicePayload & {
  reason?: string
  message_id?: string
}

export type VoiceErrorPayload = ExtensibleVoicePayload & {
  message?: string
  error?: string
}

export type VoiceEvent =
  | BaseVoiceEvent<'voice.ready', VoiceReadyPayload>
  | BaseVoiceEvent<'voice.phase', VoicePhasePayload>
  | BaseVoiceEvent<'voice.asr.delta', VoiceAsrDeltaPayload>
  | BaseVoiceEvent<'voice.asr.final', VoiceAsrFinalPayload>
  | BaseVoiceEvent<'voice.feedback', VoiceFeedbackPayload>
  | BaseVoiceEvent<'voice.playback.duck', ExtensibleVoicePayload>
  | BaseVoiceEvent<'voice.playback.restore', ExtensibleVoicePayload>
  | BaseVoiceEvent<'voice.submit.failed', VoiceSubmitFailedPayload>
  | BaseVoiceEvent<'voice.interrupted', VoiceInterruptedPayload>
  | BaseVoiceEvent<'voice.error', VoiceErrorPayload>

export interface VoiceState {
  phase: VoicePhase
  microphoneOpen: boolean
  inputLocked: boolean
  draftText: string
  stashedTextInput: string
}
