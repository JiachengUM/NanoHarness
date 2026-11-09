import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import {
  DuplexParticleStage,
  getDuplexVisualProjection,
} from './DuplexParticleStage'
import type { VoicePhase } from '../voice/voiceTypes'

describe('getDuplexVisualProjection', () => {
  it.each([
    ['idle', 'silent'],
    ['mic_pending', 'listen'],
    ['listening', 'listen'],
    ['processing', 'think'],
    ['speaking', 'speak'],
    ['interrupted', 'listen'],
    ['error', 'silent'],
  ] satisfies ReadonlyArray<[VoicePhase, string]>)('maps %s to %s', (voicePhase, state) => {
    expect(getDuplexVisualProjection({
      connected: true,
      transcript: '',
      voicePhase,
    }).state).toBe(state)
  })

  it('uses the ASR transcript as semantic expression input', () => {
    const quiet = getDuplexVisualProjection({
      connected: true,
      transcript: '',
      voicePhase: 'listening',
    })
    const active = getDuplexVisualProjection({
      connected: true,
      transcript: '帮我找一家安静并且适合聊天的咖啡店',
      voicePhase: 'listening',
    })

    expect(active.transcript).toBe('帮我找一家安静并且适合聊天的咖啡店')
    expect(active.expression.energy).toBeGreaterThan(quiet.expression.energy)
    expect(active.expression.pulse).toBeGreaterThan(quiet.expression.pulse)
  })

  it('projects acoustic features from the shared Duplex microphone stream', () => {
    const projection = getDuplexVisualProjection({
      acoustics: {
        capturedAt: 1,
        crossingRate: 0.08,
        energy: 0.76,
        flux: 0.04,
        high: 0.28,
        low: 0.38,
        middle: 0.46,
        pulse: 0.7,
        rms: 0.09,
      },
      connected: true,
      transcript: '',
      voicePhase: 'listening',
    })

    expect(projection.expression.energy).toBe(0.76)
    expect(projection.expression.pulse).toBe(0.7)
    expect(projection.expression.turbulence).toBeGreaterThan(0.2)
  })

  it('falls back to a low-energy honest state when the backend is offline', () => {
    const projection = getDuplexVisualProjection({
      connected: false,
      transcript: '不应继续显示正在说话',
      voicePhase: 'speaking',
    })

    expect(projection).toMatchObject({
      label: 'Duplex 服务离线',
      state: 'silent',
      status: 'offline',
    })
    expect(projection.expression.energy).toBe(0.08)
    expect(projection.expression.pulse).toBe(0)
  })

  it('keeps every expression value inside the normalized range', () => {
    const projection = getDuplexVisualProjection({
      connected: true,
      transcript: '很长的实时语音草稿'.repeat(20),
      voicePhase: 'interrupted',
    })

    expect(Object.values(projection.expression).every(
      (value) => value >= 0 && value <= 1,
    )).toBe(true)
  })
})

describe('DuplexParticleStage', () => {
  it('exposes the particle surface as the voice wake control', () => {
    const markup = renderToStaticMarkup(createElement(DuplexParticleStage, {
      connected: true,
      microphoneOpen: false,
      onToggleVoice: vi.fn(),
      transcript: '',
      voicePhase: 'idle',
    }))

    expect(markup).toContain('aria-label="唤醒 Duplex 语音输入"')
    expect(markup).toContain('aria-pressed="false"')
    expect(markup).toContain('唤醒 Duplex')
    expect(markup).toContain('CLICK OR TAP PARTICLE')
    expect(markup).toContain('可交互的 YITU BOT 3D 粒子生命体')
    expect(markup).toContain('THREE.JS EXPRESSION FIELD')
    expect(markup).toContain('aria-label="粒子 Live Controls"')
    expect(markup).toContain('EYES ONLY')
    expect(markup.match(/type="range"/g)).toHaveLength(4)
    expect(markup).toContain('粒子密度')
    expect(markup).toContain('流动速度')
  })

  it('turns the same surface into the stop control while voice is active', () => {
    const markup = renderToStaticMarkup(createElement(DuplexParticleStage, {
      connected: true,
      microphoneOpen: true,
      onToggleVoice: vi.fn(),
      transcript: '正在识别',
      voicePhase: 'listening',
    }))

    expect(markup).toContain('aria-label="结束语音输入"')
    expect(markup).toContain('aria-pressed="true"')
    expect(markup).toContain('VOICE SESSION ACTIVE')
  })
})
