import { useEffect, useMemo, useRef, useState } from 'react'
import type { VoiceAcousticFeatures } from '../voice/BrowserVoiceAudio'
import type { VoicePhase } from '../voice/voiceTypes'
import { createDuplexExpressionFrame, type DuplexExpressionFrame } from '../visual/duplexExpressionDirector'
import YituParticle, {
  type LiveVoiceState,
  type ParticleSettings,
} from './YituParticle'

export type DuplexVisualProjection = DuplexExpressionFrame & {
  label: string
  state: LiveVoiceState
  status: 'connecting' | 'online' | 'offline' | 'error'
  transcript: string
}

type DuplexVisualProjectionInput = {
  acoustics?: VoiceAcousticFeatures | null
  connected: boolean | null
  transcript: string
  voicePhase: VoicePhase
}

type DuplexParticleStageProps = Omit<DuplexVisualProjectionInput, 'acoustics'> & {
  disabled?: boolean
  microphoneOpen: boolean
  onToggleVoice: () => void
  readVoiceAcoustics?: () => VoiceAcousticFeatures | null
}

const LABEL_BY_PHASE: Record<VoicePhase, string> = {
  error: '语音连接异常',
  idle: '静默待机',
  interrupted: '已打断 · 继续倾听',
  listening: '正在倾听',
  mic_pending: '正在准备麦克风',
  processing: '正在思考',
  speaking: '正在表达',
}

const INITIAL_PARTICLE_SETTINGS: ParticleSettings = {
  density: 42,
  flowSpeed: 24,
  pupilSize: 76,
  socketSparse: 100,
}

const PARTICLE_CONTROLS = [
  { key: 'density', label: '粒子密度' },
  { key: 'socketSparse', label: '眼窝大小' },
  { key: 'pupilSize', label: '瞳孔尺寸' },
  { key: 'flowSpeed', label: '流动速度' },
] as const satisfies ReadonlyArray<{ key: keyof ParticleSettings; label: string }>

const STATE_LABELS: ReadonlyArray<{ label: string; state: LiveVoiceState }> = [
  { label: '静默', state: 'silent' },
  { label: '倾听', state: 'listen' },
  { label: '思考', state: 'think' },
  { label: '表达', state: 'speak' },
]

const NO_ACOUSTICS = () => null

export function getDuplexVisualProjection({
  acoustics = null,
  connected,
  transcript,
  voicePhase,
}: DuplexVisualProjectionInput): DuplexVisualProjection {
  const normalizedTranscript = transcript.replace(/\s+/g, ' ').trim()
  const frame = createDuplexExpressionFrame({
    acoustics,
    connected,
    transcript: normalizedTranscript,
    voicePhase,
  })
  const status = connected === false
    ? 'offline'
    : voicePhase === 'error'
      ? 'error'
      : connected === null
        ? 'connecting'
        : 'online'

  return {
    ...frame,
    label: connected === false ? 'Duplex 服务离线' : LABEL_BY_PHASE[voicePhase],
    state: frame.mode,
    status,
    transcript: normalizedTranscript,
  }
}

function useLiveProjection(
  input: Omit<DuplexVisualProjectionInput, 'acoustics'>,
  readVoiceAcoustics: () => VoiceAcousticFeatures | null,
): DuplexVisualProjection {
  const inputRef = useRef(input)
  inputRef.current = input
  const acousticsRef = useRef<VoiceAcousticFeatures | null>(null)
  const [projection, setProjection] = useState(() => getDuplexVisualProjection(input))

  useEffect(() => {
    if (input.connected !== true || input.voicePhase !== 'listening') {
      acousticsRef.current = null
    }
    setProjection(getDuplexVisualProjection({
      ...inputRef.current,
      acoustics: acousticsRef.current,
    }))
  }, [input.connected, input.transcript, input.voicePhase])

  useEffect(() => {
    if (input.connected !== true || input.voicePhase !== 'listening') {
      return
    }
    let animationFrame = 0
    let lastUpdate = 0
    const update = (timestamp: number) => {
      if (timestamp - lastUpdate >= 48) {
        acousticsRef.current = readVoiceAcoustics()
        setProjection(getDuplexVisualProjection({
          ...inputRef.current,
          acoustics: acousticsRef.current,
        }))
        lastUpdate = timestamp
      }
      animationFrame = window.requestAnimationFrame(update)
    }
    animationFrame = window.requestAnimationFrame(update)
    return () => window.cancelAnimationFrame(animationFrame)
  }, [input.connected, input.voicePhase, readVoiceAcoustics])

  return projection
}

export function DuplexParticleStage({
  connected,
  disabled = false,
  microphoneOpen,
  onToggleVoice,
  readVoiceAcoustics = NO_ACOUSTICS,
  transcript,
  voicePhase,
}: DuplexParticleStageProps) {
  const projectionInput = useMemo(() => ({
    connected,
    transcript,
    voicePhase,
  }), [connected, transcript, voicePhase])
  const projection = useLiveProjection(projectionInput, readVoiceAcoustics)
  const gestureRef = useRef<{ dragged: boolean; x: number; y: number } | null>(null)
  const [controlsOpen, setControlsOpen] = useState(true)
  const [particleSettings, setParticleSettings] = useState(INITIAL_PARTICLE_SETTINGS)
  const voiceActive = microphoneOpen || voicePhase === 'mic_pending'
  const attentionActive = projection.weights.listen > 0.18
  const wakeLabel = connected === false
    ? '等待 Duplex 服务'
    : voicePhase === 'mic_pending'
      ? '正在唤醒…'
      : voiceActive
        ? '结束语音'
        : '唤醒 Duplex'

  return (
    <section
      aria-label={`Duplex 粒子状态：${projection.label}`}
      className="duplex-particle-stage"
      data-controls={controlsOpen ? 'open' : 'closed'}
      data-status={projection.status}
      data-visual-state={projection.state}
      onClick={(event) => {
        if ((event.target as HTMLElement).closest('[data-particle-control]')) return
        if (!gestureRef.current?.dragged && !disabled) onToggleVoice()
        gestureRef.current = null
      }}
      onPointerCancelCapture={() => { gestureRef.current = null }}
      onPointerDownCapture={(event) => {
        if ((event.target as HTMLElement).closest('[data-particle-control]')) return
        gestureRef.current = { dragged: false, x: event.clientX, y: event.clientY }
      }}
      onPointerMoveCapture={(event) => {
        const gesture = gestureRef.current
        if (!gesture || gesture.dragged) return
        if (Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) > 10) {
          gesture.dragged = true
        }
      }}
    >
      <YituParticle
        attention={{
          driver: attentionActive,
          passenger: attentionActive,
        }}
        liveExpression={projection.expression}
        liveMode={projection.mode}
        liveWeights={projection.weights}
        settings={particleSettings}
        state={projection.botState}
      />

      <button
        aria-label={voiceActive ? '结束语音输入' : '唤醒 Duplex 语音输入'}
        aria-pressed={voiceActive}
        className="duplex-particle-wake"
        data-particle-control
        disabled={disabled}
        title={voiceActive ? '点击结束语音输入' : '点击粒子或此按钮唤醒语音输入'}
        type="button"
        onClick={onToggleVoice}
      >
        <span className="duplex-particle-wake-label">
          <i aria-hidden="true" />
          <b>{wakeLabel}</b>
          <small>{voiceActive ? 'VOICE SESSION ACTIVE' : 'CLICK OR TAP PARTICLE'}</small>
        </span>
      </button>

      <header className="duplex-particle-heading">
        <div>
          <span className="duplex-particle-mark" aria-hidden="true"><i /><i /><i /></span>
          <p>YITU BOT</p>
          <small>THREE.JS EXPRESSION FIELD</small>
        </div>
        <span className="duplex-particle-status"><i aria-hidden="true" />{projection.label}</span>
      </header>

      <div className="duplex-particle-copy">
        <p>{projection.transcript || '声音、语义与状态，共用同一条 Duplex 实时链路。'}</p>
        <small>{projection.transcript ? 'ASR EXPRESSION INPUT' : 'AICORE DUPLEX DIRECTOR'}</small>
      </div>

      <aside
        aria-label="粒子 Live Controls"
        className="duplex-live-controls"
        data-open={controlsOpen}
        data-particle-control
      >
        <button
          aria-expanded={controlsOpen}
          className="duplex-live-controls-toggle"
          type="button"
          onClick={() => setControlsOpen((open) => !open)}
        >
          <span>LIVE CONTROLS</span>
          <small>EYES ONLY</small>
          <i aria-hidden="true" />
        </button>

        {controlsOpen && (
          <div className="duplex-live-controls-content">
            <section className="duplex-live-control-state">
              <p><span>01</span> Duplex 状态</p>
              <ol aria-label="Duplex 视觉状态">
                {STATE_LABELS.map(({ label, state }) => (
                  <li aria-current={projection.state === state ? 'step' : undefined} key={state}>
                    <i aria-hidden="true" /><span>{label}</span>
                  </li>
                ))}
              </ol>
            </section>

            <section className="duplex-live-control-attention">
              <p><span>02</span> 注意力音区</p>
              <div>
                <span data-active={attentionActive}><i aria-hidden="true" />主驾</span>
                <span data-active={attentionActive}><i aria-hidden="true" />副驾</span>
              </div>
            </section>

            <section className="duplex-live-control-tuning">
              <p><span>03</span> 眼睛参数</p>
              <div>
                {PARTICLE_CONTROLS.map(({ key, label }) => (
                  <label key={key}>
                    <span>{label}<b>{particleSettings[key]}</b></span>
                    <input
                      aria-label={label}
                      max="100"
                      min="10"
                      type="range"
                      value={particleSettings[key]}
                      onChange={(event) => {
                        const value = Number(event.target.value)
                        setParticleSettings((current) => ({ ...current, [key]: value }))
                      }}
                    />
                  </label>
                ))}
              </div>
            </section>
          </div>
        )}
      </aside>
    </section>
  )
}
