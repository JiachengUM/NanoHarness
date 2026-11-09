import { CaptureChunker, INPUT_SAMPLE_RATE, OUTPUT_SAMPLE_RATE } from './audioCaptureChunker'
import {
  traceBrowserLatency,
  type LatencyTraceContext,
} from '../utils/latencyTrace'

const CAPTURE_PROCESSING_CONSTRAINTS: MediaTrackConstraints = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
  channelCount: 1,
}

export type VoiceAcousticFeatures = {
  capturedAt: number
  crossingRate: number
  energy: number
  flux: number
  high: number
  low: number
  middle: number
  pulse: number
  rms: number
}

function clamp(value: number, minimum = 0, maximum = 1): number {
  return Math.min(maximum, Math.max(minimum, value))
}

function averageBand(values: Uint8Array, from: number, to: number): number {
  const start = Math.max(0, Math.floor(from))
  const end = Math.min(values.length, Math.max(start + 1, Math.floor(to)))
  let total = 0
  for (let index = start; index < end; index += 1) {
    total += values[index]
  }
  return total / Math.max(1, end - start) / 255
}

export class BrowserVoiceAudio {
  private playbackContext: AudioContext | null = null
  private playbackGain: GainNode | null = null
  private captureContext: AudioContext | null = null
  private mediaStream: MediaStream | null = null
  private analyser: AnalyserNode | null = null
  private analyserTimeData: Uint8Array | null = null
  private analyserFrequencyData: Uint8Array | null = null
  private previousFrequencyData: Uint8Array | null = null
  private processor: ScriptProcessorNode | null = null
  private sourceNode: MediaStreamAudioSourceNode | null = null
  private playbackSources = new Set<AudioBufferSourceNode>()
  private captureChunker = new CaptureChunker()
  private nextPlayTime = 0
  private listening = false
  private playbackActive = false
  private playbackGeneration = 0
  private previousCaptureEnergy = 0
  private latestCaptureFeatures: VoiceAcousticFeatures | null = null

  constructor(
    private readonly onPlaybackActiveChange?: (
      active: boolean,
      completedNaturally?: boolean,
    ) => void,
    private readonly getPlaybackTraceContext: () => LatencyTraceContext = () => ({}),
  ) {}

  async initPlayback(): Promise<void> {
    if (!this.playbackContext) {
      this.playbackContext = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE })
    }
    if (!this.playbackGain) {
      const createGain = (
        this.playbackContext as AudioContext & {
          createGain?: () => GainNode
        }
      ).createGain
      if (typeof createGain === 'function') {
        this.playbackGain = createGain.call(this.playbackContext)
        this.playbackGain.gain.value = 1
        this.playbackGain.connect(this.playbackContext.destination)
      }
    }
    if (this.playbackContext.state === 'suspended') {
      await this.playbackContext.resume()
    }
  }

  async init(): Promise<void> {
    await this.initPlayback()
    if (!this.captureContext) {
      this.captureContext = new AudioContext()
    }
    if (!this.mediaStream) {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: CAPTURE_PROCESSING_CONSTRAINTS,
      })
      await this.reapplyCaptureProcessing(this.mediaStream)
    }
  }

  setListening(value: boolean): void {
    this.listening = value
    if (!value) {
      this.captureChunker.reset()
      this.latestCaptureFeatures = null
      this.previousCaptureEnergy = 0
      this.previousFrequencyData?.fill(0)
    }
  }

  readCaptureFeatures(): VoiceAcousticFeatures | null {
    if (!this.listening) {
      return null
    }
    this.updateCaptureFeatures()
    return this.latestCaptureFeatures
  }

  startCapture(onChunk: (bytes: ArrayBuffer) => void): void {
    if (!this.captureContext || !this.mediaStream || this.sourceNode || this.processor) {
      return
    }

    this.sourceNode = this.captureContext.createMediaStreamSource(this.mediaStream)
    this.processor = this.captureContext.createScriptProcessor(4096, 1, 1)
    const createAnalyser = (
      this.captureContext as AudioContext & {
        createAnalyser?: () => AnalyserNode
      }
    ).createAnalyser
    if (typeof createAnalyser === 'function') {
      this.analyser = createAnalyser.call(this.captureContext)
      this.analyser.fftSize = 1024
      this.analyser.smoothingTimeConstant = 0.46
      this.analyserTimeData = new Uint8Array(this.analyser.fftSize)
      this.analyserFrequencyData = new Uint8Array(this.analyser.frequencyBinCount)
      this.previousFrequencyData = new Uint8Array(this.analyser.frequencyBinCount)
    }
    this.processor.onaudioprocess = (event) => {
      const samples = event.inputBuffer.getChannelData(0)
      if (this.listening) {
        this.captureChunker.processCaptureSamples(
          samples,
          this.captureContext?.sampleRate ?? INPUT_SAMPLE_RATE,
          onChunk,
        )
      }
    }

    if (this.analyser) {
      this.sourceNode.connect(this.analyser)
      this.analyser.connect(this.processor)
    } else {
      this.sourceNode.connect(this.processor)
    }
    this.processor.connect(this.captureContext.destination)
  }

  playTtsChunk(bytes: ArrayBuffer): void {
    if (!this.playbackContext) {
      return
    }

    const context = this.playbackContext
    const samples = new Float32Array(bytes)
    const buffer = context.createBuffer(1, samples.length, OUTPUT_SAMPLE_RATE)
    buffer.copyToChannel(samples, 0)

    const source = context.createBufferSource()
    source.buffer = buffer
    this.registerPlaybackSource(source)

    const now = context.currentTime
    if (this.nextPlayTime < now) {
      this.nextPlayTime = now
    }
    source.start(this.nextPlayTime)
    this.nextPlayTime += buffer.duration
  }

  setPlaybackDucked(ducked: boolean): void {
    const context = this.playbackContext
    const gain = this.playbackGain?.gain
    if (!context || !gain) {
      return
    }
    if (typeof gain.setTargetAtTime === 'function') {
      gain.setTargetAtTime(ducked ? 0.24 : 1, context.currentTime, 0.03)
      return
    }
    gain.value = ducked ? 0.24 : 1
  }

  resetPlaybackSchedule(): void {
    this.playbackGeneration += 1
    this.nextPlayTime = 0
    this.clearPlaybackSources()
  }

  stop(): void {
    this.playbackGeneration += 1
    this.clearPlaybackSources()
    this.processor?.disconnect()
    this.analyser?.disconnect()
    this.sourceNode?.disconnect()
    this.mediaStream?.getTracks().forEach((track) => track.stop())
    this.playbackGain?.disconnect()
    this.playbackContext?.close()
    this.captureContext?.close()

    this.processor = null
    this.analyser = null
    this.analyserTimeData = null
    this.analyserFrequencyData = null
    this.previousFrequencyData = null
    this.sourceNode = null
    this.mediaStream = null
    this.playbackGain = null
    this.playbackContext = null
    this.captureContext = null
    this.nextPlayTime = 0
    this.captureChunker.reset()
    this.latestCaptureFeatures = null
    this.previousCaptureEnergy = 0
    this.listening = false
  }

  private updateCaptureFeatures(): void {
    const timeData = this.analyserTimeData
    const frequencyData = this.analyserFrequencyData
    const previousFrequencyData = this.previousFrequencyData
    if (!this.analyser || !timeData || !frequencyData || !previousFrequencyData) {
      return
    }
    this.analyser.getByteTimeDomainData(timeData)
    this.analyser.getByteFrequencyData(frequencyData)

    let squareTotal = 0
    let crossings = 0
    let previousSample = 0
    const sampleCount = timeData.length
    for (let index = 0; index < sampleCount; index += 1) {
      const sample = (timeData[index] - 128) / 128
      squareTotal += sample * sample
      if (index > 0 && Math.sign(sample) !== Math.sign(previousSample)) {
        crossings += 1
      }
      previousSample = sample
    }

    const rms = Math.sqrt(squareTotal / Math.max(1, sampleCount))
    const energy = clamp((rms - 0.012) * 9.4)
    const count = frequencyData.length
    const low = averageBand(frequencyData, 2, count * 0.1)
    const middle = averageBand(frequencyData, count * 0.1, count * 0.38)
    const high = averageBand(frequencyData, count * 0.38, count * 0.82)
    let flux = 0
    for (let index = 0; index < count; index += 1) {
      flux += Math.max(0, frequencyData[index] - previousFrequencyData[index]) / 255
      previousFrequencyData[index] = frequencyData[index]
    }
    flux /= Math.max(1, count)

    this.latestCaptureFeatures = {
      capturedAt: Date.now(),
      crossingRate: crossings / Math.max(1, sampleCount),
      energy,
      flux,
      high,
      low,
      middle,
      pulse: clamp(flux * 12 + Math.max(0, energy - this.previousCaptureEnergy) * 2.6),
      rms,
    }
    this.previousCaptureEnergy = energy
  }

  private setPlaybackActive(
    active: boolean,
    completedNaturally = false,
  ): void {
    if (this.playbackActive === active) {
      return
    }
    this.playbackActive = active
    traceBrowserLatency(
      active ? 'tts.playback.start' : 'tts.playback.stop',
      this.getPlaybackTraceContext(),
    )
    this.onPlaybackActiveChange?.(active, completedNaturally)
  }

  private clearPlaybackSources(): void {
    this.playbackSources.forEach((source) => {
      source.onended = null
      try {
        source.stop()
      } catch {
        // Source may have already ended or may not have started yet.
      }
      this.disconnectPlaybackSource(source)
    })
    this.playbackSources.clear()
    this.setPlaybackActive(false, false)
  }

  private registerPlaybackSource(source: AudioBufferSourceNode): void {
    const context = this.playbackContext
    if (!context) {
      return
    }
    source.connect(this.playbackGain ?? context.destination)
    source.onended = () => {
      source.onended = null
      this.playbackSources.delete(source)
      this.disconnectPlaybackSource(source)
      if (this.playbackSources.size === 0) {
        this.setPlaybackActive(false, true)
      }
    }
    this.playbackSources.add(source)
    this.setPlaybackActive(true, false)
  }

  private disconnectPlaybackSource(source: AudioBufferSourceNode): void {
    try {
      source.disconnect()
    } catch {
      // Some browser implementations throw when disconnecting an already detached source.
    }
  }

  private async reapplyCaptureProcessing(stream: MediaStream): Promise<void> {
    const track = stream.getAudioTracks?.()[0]
    if (!track) {
      return
    }
    try {
      await track.applyConstraints?.(CAPTURE_PROCESSING_CONSTRAINTS)
    } catch (error: unknown) {
      console.warn('[v2-voice] unable to reapply microphone AEC constraints', error)
    }

    const settings = track.getSettings?.()
    if (settings?.echoCancellation === false) {
      console.warn('[v2-voice] browser microphone AEC is disabled', settings)
    }
  }
}
