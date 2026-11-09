import { afterEach, describe, expect, test, vi } from 'vitest'
import { BrowserVoiceAudio } from './BrowserVoiceAudio'

describe('BrowserVoiceAudio', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('initializes playback without requesting microphone capture', async () => {
    class FakeAudioContext {
      currentTime = 0
      destination = {}
      sampleRate = 24000
      close = vi.fn()
    }
    const getUserMedia = vi.fn()

    vi.stubGlobal('AudioContext', FakeAudioContext)
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })

    const audio = new BrowserVoiceAudio()
    await audio.initPlayback()

    expect(getUserMedia).not.toHaveBeenCalled()
  })

  test('initializes playback by resuming a suspended playback context', async () => {
    const contexts: FakeAudioContext[] = []
    class FakeAudioContext {
      currentTime = 0
      destination = {}
      sampleRate = 24000
      state = 'suspended'
      resume = vi.fn().mockImplementation(async () => {
        this.state = 'running'
      })
      close = vi.fn()
      constructor() {
        contexts.push(this)
      }
    }

    vi.stubGlobal('AudioContext', FakeAudioContext)

    const audio = new BrowserVoiceAudio()
    await audio.initPlayback()

    expect(contexts[0].resume).toHaveBeenCalledOnce()
    expect(contexts[0].state).toBe('running')
  })

  test('upgrades a playback session to microphone capture only when init is called', async () => {
    class FakeAudioContext {
      currentTime = 0
      destination = {}
      sampleRate = 24000
      close = vi.fn()
    }
    const audioTrack = {
      applyConstraints: vi.fn().mockResolvedValue(undefined),
      getSettings: vi.fn().mockReturnValue({ echoCancellation: true }),
    }
    const mediaStream = {
      getTracks: () => [audioTrack],
      getAudioTracks: () => [audioTrack],
    }
    const getUserMedia = vi.fn().mockResolvedValue(mediaStream)

    vi.stubGlobal('AudioContext', FakeAudioContext)
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })

    const audio = new BrowserVoiceAudio()
    await audio.initPlayback()
    await audio.init()

    expect(getUserMedia).toHaveBeenCalledOnce()
    expect(getUserMedia).toHaveBeenCalledWith({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    })
    expect(audioTrack.applyConstraints).toHaveBeenCalledWith({
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
    })
  })

  test('resetPlaybackSchedule preserves the existing playback context', async () => {
    const contexts: FakeAudioContext[] = []
    class FakeAudioContext {
      currentTime = 0
      destination = {}
      sampleRate = 24000
      close = vi.fn()
      constructor() {
        contexts.push(this)
      }
    }

    vi.stubGlobal('AudioContext', FakeAudioContext)

    const audio = new BrowserVoiceAudio()
    await audio.initPlayback()

    audio.resetPlaybackSchedule()

    expect(contexts).toHaveLength(1)
    expect(contexts[0].close).not.toHaveBeenCalled()
  })

  test('resetPlaybackSchedule stops queued playback sources', async () => {
    const firstSource = {
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      disconnect: vi.fn(),
      onended: null as (() => void) | null,
    }
    const secondSource = {
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      disconnect: vi.fn(),
      onended: null as (() => void) | null,
    }
    const thirdSource = {
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      disconnect: vi.fn(),
      onended: null as (() => void) | null,
    }
    const sources = [firstSource, secondSource, thirdSource]

    class FakeAudioContext {
      currentTime = 3
      destination = {}
      sampleRate = 24000
      close = vi.fn()
      createBuffer() {
        return {
          duration: 0.25,
          copyToChannel: vi.fn(),
        }
      }
      createBufferSource() {
        return sources.shift()
      }
    }

    vi.stubGlobal('AudioContext', FakeAudioContext)

    const audio = new BrowserVoiceAudio()
    await audio.initPlayback()
    audio.playTtsChunk(new Float32Array([0.1, 0.2]).buffer)
    audio.playTtsChunk(new Float32Array([0.3, 0.4]).buffer)

    audio.resetPlaybackSchedule()

    expect(firstSource.stop).toHaveBeenCalledOnce()
    expect(firstSource.disconnect).toHaveBeenCalledOnce()
    expect(secondSource.stop).toHaveBeenCalledOnce()
    expect(secondSource.disconnect).toHaveBeenCalledOnce()

    audio.playTtsChunk(new Float32Array([0.5]).buffer)

    expect(thirdSource.start).toHaveBeenCalledWith(3)
  })

  test('reports playback active until all queued tts sources end', async () => {
    const firstSource = {
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      disconnect: vi.fn(),
      onended: null as (() => void) | null,
    }
    const secondSource = {
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      disconnect: vi.fn(),
      onended: null as (() => void) | null,
    }
    const sources = [firstSource, secondSource]

    class FakeAudioContext {
      currentTime = 0
      destination = {}
      sampleRate = 24000
      close = vi.fn()
      createBuffer() {
        return {
          duration: 0.25,
          copyToChannel: vi.fn(),
        }
      }
      createBufferSource() {
        return sources.shift()
      }
    }

    vi.stubGlobal('AudioContext', FakeAudioContext)

    const activeChanges: boolean[] = []
    const audio = new BrowserVoiceAudio((active) => activeChanges.push(active))
    await audio.initPlayback()

    audio.playTtsChunk(new Float32Array([0.1, 0.2]).buffer)
    audio.playTtsChunk(new Float32Array([0.3, 0.4]).buffer)

    expect(activeChanges).toEqual([true])

    firstSource.onended?.()
    expect(activeChanges).toEqual([true])

    secondSource.onended?.()
    expect(activeChanges).toEqual([true, false])
  })

  test('resetPlaybackSchedule reports playback inactive', async () => {
    const source = {
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      disconnect: vi.fn(),
      onended: null as (() => void) | null,
    }

    class FakeAudioContext {
      currentTime = 0
      destination = {}
      sampleRate = 24000
      close = vi.fn()
      createBuffer() {
        return {
          duration: 0.25,
          copyToChannel: vi.fn(),
        }
      }
      createBufferSource() {
        return source
      }
    }

    vi.stubGlobal('AudioContext', FakeAudioContext)

    const activeChanges: boolean[] = []
    const audio = new BrowserVoiceAudio((active) => activeChanges.push(active))
    await audio.initPlayback()

    audio.playTtsChunk(new Float32Array([0.1, 0.2]).buffer)
    audio.resetPlaybackSchedule()

    expect(activeChanges).toEqual([true, false])
  })

  test('traces playback start and interruption stop with the target message id', async () => {
    const source = {
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      disconnect: vi.fn(),
      onended: null as (() => void) | null,
    }

    class FakeAudioContext {
      currentTime = 0
      destination = {}
      sampleRate = 24000
      close = vi.fn()
      createBuffer() {
        return { duration: 0.25, copyToChannel: vi.fn() }
      }
      createBufferSource() {
        return source
      }
    }

    vi.stubGlobal('AudioContext', FakeAudioContext)
    const info = vi.spyOn(console, 'info').mockImplementation(() => undefined)
    const audio = new BrowserVoiceAudio(undefined, () => ({
      message_id: 'agent-1',
      generation: 5,
    }))
    await audio.initPlayback()

    audio.playTtsChunk(new Float32Array([0.1, 0.2]).buffer)
    audio.resetPlaybackSchedule()

    const records = info.mock.calls.map((call) => call[1] as Record<string, unknown>)
    expect(records).toEqual([
      expect.objectContaining({
        event: 'tts.playback.start',
        message_id: 'agent-1',
        generation: 5,
      }),
      expect.objectContaining({
        event: 'tts.playback.stop',
        message_id: 'agent-1',
        generation: 5,
      }),
    ])
    info.mockRestore()
  })

  test('startCapture is idempotent once capture nodes exist', () => {
    const audio = new BrowserVoiceAudio()
    let sourceCount = 0
    let processorCount = 0
    const source = { connect: () => undefined }
    const processor = { connect: () => undefined, onaudioprocess: null }
    const captureContext = {
      destination: {},
      sampleRate: 16000,
      createMediaStreamSource: () => {
        sourceCount += 1
        return source
      },
      createScriptProcessor: () => {
        processorCount += 1
        return processor
      },
    }
    const mediaStream = { getTracks: () => [] }

    Object.assign(audio as unknown as Record<string, unknown>, {
      captureContext,
      mediaStream,
    })

    audio.startCapture(() => undefined)
    audio.startCapture(() => undefined)

    expect(sourceCount).toBe(1)
    expect(processorCount).toBe(1)
  })

  test('samples acoustic features on visual reads independently from PCM callbacks', () => {
    const source = { connect: vi.fn(), disconnect: vi.fn() }
    const processor = {
      connect: vi.fn(),
      disconnect: vi.fn(),
      onaudioprocess: null as ((event: AudioProcessingEvent) => void) | null,
    }
    const analyser = {
      connect: vi.fn(),
      disconnect: vi.fn(),
      fftSize: 0,
      frequencyBinCount: 8,
      smoothingTimeConstant: 0,
      getByteTimeDomainData: vi.fn((data: Uint8Array) => {
        data.fill(128)
        data[0] = 255
        data[1] = 0
      }),
      getByteFrequencyData: vi.fn((data: Uint8Array) => {
        data.set([10, 80, 120, 160, 100, 60, 20, 0])
      }),
    }
    const captureContext = {
      createAnalyser: () => analyser,
      createMediaStreamSource: () => source,
      createScriptProcessor: () => processor,
      destination: {},
      sampleRate: 16000,
    }
    const audio = new BrowserVoiceAudio()
    Object.assign(audio as unknown as Record<string, unknown>, {
      captureContext,
      mediaStream: { getTracks: () => [] },
    })

    const onChunk = vi.fn()
    audio.startCapture(onChunk)
    audio.setListening(true)
    processor.onaudioprocess?.({
      inputBuffer: {
        getChannelData: () => new Float32Array(3200),
      },
    } as unknown as AudioProcessingEvent)

    expect(source.connect).toHaveBeenCalledWith(analyser)
    expect(analyser.connect).toHaveBeenCalledWith(processor)
    expect(onChunk).toHaveBeenCalledOnce()
    expect(analyser.getByteTimeDomainData).not.toHaveBeenCalled()
    expect(analyser.getByteFrequencyData).not.toHaveBeenCalled()

    const features = audio.readCaptureFeatures()
    expect(analyser.getByteTimeDomainData).toHaveBeenCalledOnce()
    expect(analyser.getByteFrequencyData).toHaveBeenCalledOnce()
    expect(features).toMatchObject({
      capturedAt: expect.any(Number),
      high: expect.any(Number),
      low: expect.any(Number),
      middle: expect.any(Number),
    })
    expect(features?.energy).toBeGreaterThan(0)
    expect(features?.pulse).toBeGreaterThan(0)

    audio.setListening(false)
    expect(audio.readCaptureFeatures()).toBeNull()
    expect(analyser.getByteTimeDomainData).toHaveBeenCalledOnce()
  })

  test('creates one playback gain connected to the destination', async () => {
    const gain = {
      gain: { value: 0, setTargetAtTime: vi.fn() },
      connect: vi.fn(),
      disconnect: vi.fn(),
    }
    const contexts: FakeAudioContext[] = []
    class FakeAudioContext {
      currentTime = 0
      destination = { kind: 'destination' }
      sampleRate = 24000
      close = vi.fn()
      createGain = vi.fn(() => gain)
      constructor() {
        contexts.push(this)
      }
    }

    vi.stubGlobal('AudioContext', FakeAudioContext)

    const audio = new BrowserVoiceAudio()
    await audio.initPlayback()
    await audio.initPlayback()

    expect(contexts[0].createGain).toHaveBeenCalledOnce()
    expect(gain.gain.value).toBe(1)
    expect(gain.connect).toHaveBeenCalledOnce()
    expect(gain.connect).toHaveBeenCalledWith(contexts[0].destination)
  })

  test('routes streamed tts through the shared playback gain', async () => {
    const gain = {
      gain: { value: 1, setTargetAtTime: vi.fn() },
      connect: vi.fn(),
      disconnect: vi.fn(),
    }
    const source = {
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      disconnect: vi.fn(),
      onended: null as (() => void) | null,
    }
    class FakeAudioContext {
      currentTime = 0
      destination = {}
      sampleRate = 24000
      close = vi.fn()
      createGain = vi.fn(() => gain)
      createBuffer() {
        return { duration: 0.25, copyToChannel: vi.fn() }
      }
      createBufferSource() {
        return source
      }
    }

    vi.stubGlobal('AudioContext', FakeAudioContext)

    const audio = new BrowserVoiceAudio()
    await audio.initPlayback()
    audio.playTtsChunk(new Float32Array([0.1]).buffer)

    expect(source.connect).toHaveBeenCalledWith(gain)
  })

  test('ducks and restores the shared playback gain without timers', async () => {
    const setTargetAtTime = vi.fn()
    const gain = {
      gain: { value: 1, setTargetAtTime },
      connect: vi.fn(),
      disconnect: vi.fn(),
    }
    class FakeAudioContext {
      currentTime = 12.5
      destination = {}
      sampleRate = 24000
      close = vi.fn()
      createGain = vi.fn(() => gain)
    }

    vi.stubGlobal('AudioContext', FakeAudioContext)

    const audio = new BrowserVoiceAudio()
    await audio.initPlayback()
    audio.setPlaybackDucked(true)
    audio.setPlaybackDucked(false)

    expect(setTargetAtTime.mock.calls).toEqual([
      [0.24, 12.5, 0.03],
      [1, 12.5, 0.03],
    ])
  })

  test('stop disconnects and clears the playback gain without reporting completion', async () => {
    const gain = {
      gain: { value: 1, setTargetAtTime: vi.fn() },
      connect: vi.fn(),
      disconnect: vi.fn(),
    }
    const source = {
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      disconnect: vi.fn(),
      onended: null as (() => void) | null,
    }
    class FakeAudioContext {
      currentTime = 0
      destination = {}
      sampleRate = 24000
      close = vi.fn()
      createGain = vi.fn(() => gain)
      createBuffer() {
        return { duration: 0.25, copyToChannel: vi.fn() }
      }
      createBufferSource() {
        return source
      }
    }

    vi.stubGlobal('AudioContext', FakeAudioContext)

    const activeChanges: Array<[boolean, boolean | undefined]> = []
    const audio = new BrowserVoiceAudio((active, completed) => {
      activeChanges.push([active, completed])
    })
    await audio.initPlayback()
    audio.playTtsChunk(new Float32Array([0.1]).buffer)
    audio.stop()

    expect(gain.disconnect).toHaveBeenCalledOnce()
    expect(activeChanges).toEqual([[true, false], [false, false]])
  })
})
