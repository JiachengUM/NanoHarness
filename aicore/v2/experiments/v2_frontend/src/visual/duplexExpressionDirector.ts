import type {
  BotState,
  LiveExpression,
  LiveVoiceState,
  LiveVoiceWeights,
} from '../components/YituParticle'
import type { VoiceAcousticFeatures } from '../voice/BrowserVoiceAudio'
import type { VoicePhase } from '../voice/voiceTypes'
import {
  fuseExpression,
  manualVoiceWeights,
  neutralExpression,
  type SemanticReading,
} from './expressionDirector'

export type DuplexExpressionFrame = {
  botState: BotState
  expression: LiveExpression
  mode: LiveVoiceState
  weights: LiveVoiceWeights
}

type DuplexExpressionInput = {
  acoustics: VoiceAcousticFeatures | null
  connected: boolean | null
  transcript: string
  voicePhase: VoicePhase
}

const PHASE_STATE: Record<VoicePhase, LiveVoiceState> = {
  error: 'silent',
  idle: 'silent',
  interrupted: 'listen',
  listening: 'listen',
  mic_pending: 'listen',
  processing: 'think',
  speaking: 'speak',
}

const BOT_STATE: Record<LiveVoiceState, BotState> = {
  silent: 'silent',
  listen: 'awake',
  think: 'think',
  speak: 'focus',
}

const clamp = (value: number, minimum = 0, maximum = 1) => (
  Math.min(maximum, Math.max(minimum, value))
)

function phaseExpression(state: LiveVoiceState): LiveExpression {
  const expression = { ...neutralExpression }
  if (state === 'silent') {
    return {
      ...expression,
      energy: 0.08,
      openness: 0.2,
      focus: 0.3,
      turbulence: 0.06,
      pulse: 0,
      eyeAperture: 0.28,
      pupilDilation: 0.38,
    }
  }
  if (state === 'think') {
    return {
      ...expression,
      energy: 0.34,
      openness: 0.38,
      tension: 0.42,
      focus: 0.94,
      turbulence: 0.46,
      certainty: 0.52,
      pulse: 0.2,
      eyeAperture: 0.56,
      gazeX: 0.12,
      gazeY: 0.08,
    }
  }
  if (state === 'speak') {
    return {
      ...expression,
      energy: 0.82,
      openness: 0.74,
      tension: 0.26,
      focus: 0.76,
      turbulence: 0.3,
      warmth: 0.76,
      valence: 0.68,
      certainty: 0.88,
      pulse: 0.88,
      eyeAperture: 0.7,
      pupilDilation: 0.58,
    }
  }
  return {
    ...expression,
    energy: 0.34,
    openness: 0.68,
    tension: 0.18,
    focus: 0.88,
    turbulence: 0.12,
    warmth: 0.58,
    certainty: 0.72,
    pulse: 0.2,
    eyeAperture: 0.74,
    pupilDilation: 0.54,
  }
}

export function expressionFromAcoustics(
  acoustics: VoiceAcousticFeatures | null,
  state: LiveVoiceState,
): LiveExpression {
  const base = phaseExpression(state)
  if (!acoustics || state !== 'listen') {
    return base
  }

  const spectralTotal = Math.max(0.001, acoustics.low + acoustics.middle + acoustics.high)
  return {
    ...base,
    energy: acoustics.energy,
    openness: clamp(0.22 + acoustics.high / spectralTotal * 1.42 + acoustics.energy * 0.16),
    tension: clamp(
      acoustics.high / Math.max(0.001, acoustics.low + acoustics.high) * 0.86
      + acoustics.flux * 4.2,
    ),
    focus: clamp(0.38 + acoustics.middle / spectralTotal * 1.1 - acoustics.flux * 1.4),
    turbulence: clamp(acoustics.flux * 8.5 + acoustics.crossingRate * 2.2),
    warmth: clamp(acoustics.low / spectralTotal * 1.74 + 0.06),
    certainty: clamp(0.72 + acoustics.energy * 0.18 - acoustics.flux * 3.1),
    pulse: acoustics.pulse,
    pupilDilation: clamp(0.46 + acoustics.energy * 0.28),
  }
}

export function semanticReadingFromTranscript(text: string): SemanticReading {
  const normalized = text.replace(/\s+/g, ' ').trim()
  if (!normalized) {
    return { confidence: 0, vector: { ...neutralExpression } }
  }

  const lengthActivity = clamp(Array.from(normalized).length / 36)
  const question = /[?？]|吗(?:[，。！？!?]|$)|怎么|如何|为什么|哪里|什么/u.test(normalized)
  const positive = /喜欢|开心|太好|很好|谢谢|期待|可以|成功|漂亮|舒服|放松/u.test(normalized)
  const concern = /担心|问题|错误|失败|不能|不行|危险|难受|糟糕|修复/u.test(normalized)
  const urgency = /马上|立刻|赶紧|紧急|快点|现在/u.test(normalized)
  const vector = { ...neutralExpression }

  vector.energy = clamp(0.34 + lengthActivity * 0.18 + (urgency ? 0.28 : 0))
  vector.openness = clamp(0.48 + (question ? 0.34 : 0.04))
  vector.focus = clamp(0.62 + (question ? 0.24 : 0.08) + (urgency ? 0.08 : 0))
  vector.tension = clamp(0.26 + (concern ? 0.48 : 0) + (urgency ? 0.18 : 0))
  vector.turbulence = clamp(0.18 + (concern ? 0.3 : 0) + (urgency ? 0.28 : 0))
  vector.warmth = clamp(0.48 + (positive ? 0.4 : 0) - (concern ? 0.18 : 0))
  vector.valence = clamp(0.54 + (positive ? 0.36 : 0) - (concern ? 0.34 : 0))
  vector.certainty = clamp(0.56 + (question ? -0.24 : 0.16) + (urgency ? 0.08 : 0))
  vector.pulse = clamp(lengthActivity * 0.24 + (urgency ? 0.52 : 0))
  vector.eyeCurve = clamp((positive ? 0.44 : 0) - (concern ? 0.42 : 0), -1, 1)
  vector.eyeAperture = clamp(0.62 + (question ? 0.2 : 0) + (urgency ? 0.12 : 0))
  vector.eyeSlant = clamp((concern ? -0.28 : 0) + (positive ? 0.12 : 0), -1, 1)
  vector.pupilDilation = clamp(0.5 + (question ? 0.16 : 0) + (urgency ? 0.14 : 0))
  vector.gazeX = question ? 0.08 : 0
  vector.gazeY = question ? 0.05 : 0

  return {
    confidence: clamp(0.2 + lengthActivity * 0.34 + (question || positive || concern || urgency ? 0.18 : 0)),
    vector,
  }
}

export function createDuplexExpressionFrame({
  acoustics,
  connected,
  transcript,
  voicePhase,
}: DuplexExpressionInput): DuplexExpressionFrame {
  const mode = connected === false ? 'silent' : PHASE_STATE[voicePhase]
  const prosody = expressionFromAcoustics(acoustics, mode)
  const semantic = semanticReadingFromTranscript(transcript)
  const expression = connected === false
    ? phaseExpression('silent')
    : fuseExpression(prosody, semantic)
  const weights = manualVoiceWeights(mode)

  return {
    botState: BOT_STATE[mode],
    expression,
    mode,
    weights,
  }
}
