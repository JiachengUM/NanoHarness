import { BASE_URL } from '@/request/https'
import { MicVAD } from '@ricky0123/vad-web'
import type { RealTimeVADOptions } from '@ricky0123/vad-web'

export type TtsVoice = 'male' | 'female'

export type BrowserVoiceAudioOptions = {
  /**
   * 前端 VAD 整段采集模式（默认 false=老流式）：Silero VAD 切句后把整段语音一次性发出，
   * 替代每 200ms 一帧的流式发送。弱网下帧间隙不再传导到服务端 VAD/ASR，
   * 后端 feed_mic 已兼容大包（按 200ms 帧长切开后连续转发火山）。
   */
  vad?: boolean
  /** VAD 参数覆盖（页面 adapter-config 表单传入）；缺省用 DEFAULT_VAD_CONFIG */
  vadConfig?: Partial<FrontendVadConfig>
}

export type TtsPlayHooks = {
  onAudioStart?: () => void
}

export type TtsPlayHandler = (text: string, voice: TtsVoice, hooks?: TtsPlayHooks) => Promise<void>

const INPUT_SAMPLE_RATE = 16000
const OUTPUT_SAMPLE_RATE = 24000
/** 单帧采样数（16kHz × 200ms），与后端 S2S input chunk 对齐；满一帧立刻经 WS 发出 */
const CHUNK_SAMPLES = 3200
const TTS_PLACEHOLDER = new Set(['思考中…', '识别中…'])

// ---------------------------------------------------------------------------
// 前端 VAD（Silero）参数
// 默认值整体取向：敏感度放开（短句能抓）+ pre/post pending 放大（切句稳）
// - min_speech_ms 300：最短语音段。太小抓不住快速短回复（车机秒回“搞定了”≈400ms）；
//   300 与触发门槛一致（3 帧×96ms），瞬态噪声仍由正阈值+连续帧滤掉；
//   且后端对空 ASR 文本/451 静默忽略，误发噪声段不会污染评测
// - pre_speech_pad_ms 1500（pre pending）：语音开始前多补前导，防吞字头
// - redemption_ms 1500（post pending/静音判停）：尾静音等 1.5s 才切句，防车机回复中途停顿被切断。
//   注意与后端 S2S vad_timeout_ms 的硬约束：段必须在「保活静音判停」前到达火山，
//   即 vad_timeout_ms > redemption_ms + 上传时间；后端默认 3000 > 1500 + 弱网上传余量。
// - positive_threshold 0.5：更难触发语音开始，滤掉环境噪声/残余 TTS 回声
// - negative_threshold 0.15：更难判定语音结束，段更完整
// 页面 adapter-config 表单可覆盖以上全部参数（仅前端生效）。
// ---------------------------------------------------------------------------
export type FrontendVadConfig = {
  /** 最短语音段（ms）：低于此长度的语音视为噪声丢弃（misfire） */
  min_speech_ms: number
  /** pre pending：语音开始前补的前导静音（ms） */
  pre_speech_pad_ms: number
  /** post pending/静音判停：语音结束后等多久静音才切句（ms） */
  redemption_ms: number
  /** 语音开始判定阈值（0~1） */
  positive_threshold: number
  /** 语音结束判定阈值（0~1） */
  negative_threshold: number
}

export const DEFAULT_VAD_CONFIG: FrontendVadConfig = {
  min_speech_ms: 300,
  pre_speech_pad_ms: 1500,
  redemption_ms: 1500,
  positive_threshold: 0.5,
  negative_threshold: 0.15,
}

/** 单段最长说话时长：超过则强制切段提交（pause 触发 onSpeechEnd），避免车机一直说导致段无限长 */
const VAD_MAX_SEGMENT_MS = 30_000


export function isPlayableTtsText(text: string): boolean {
  const content = text.trim()
  return content.length > 0 && !TTS_PLACEHOLDER.has(content)
}

function downsample(buffer: Float32Array, inputRate: number, outputRate: number): Float32Array {
  if (inputRate === outputRate) {
    return buffer
  }
  const ratio = inputRate / outputRate
  const newLength = Math.floor(buffer.length / ratio)
  const result = new Float32Array(newLength)
  for (let i = 0; i < newLength; i++) {
    result[i] = buffer[Math.floor(i * ratio)]
  }
  return result
}

function floatTo16BitPCM(samples: number[]): Int16Array {
  const int16 = new Int16Array(samples.length)
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return int16
}

/** Float32Array 直转 int16（VAD onSpeechEnd 段），避免先转 number[] 的拷贝开销 */
function float32To16BitPCM(samples: Float32Array): Int16Array {
  const int16 = new Int16Array(samples.length)
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return int16
}

export class BrowserVoiceAudio {
  private playbackContext: AudioContext | null = null
  private captureContext: AudioContext | null = null
  private mediaStream: MediaStream | null = null
  private processor: ScriptProcessorNode | null = null
  private sourceNode: MediaStreamAudioSourceNode | null = null
  private nextPlayTime = 0
  private activeSources: AudioBufferSourceNode[] = []
  private pcmBuffer: number[] = []
  private onMicChunk: ((bytes: ArrayBuffer) => void) | null = null
  private listening = false

  // 前端 VAD 整段采集模式（Silero onnxruntime-web）
  private vadEnabled: boolean
  private vad: MicVAD | null = null
  private vadConfig: FrontendVadConfig
  /** 说话超长强制切段的计时器 */
  private segmentTimer: number | null = null

  constructor(options: BrowserVoiceAudioOptions = {}) {
    this.vadEnabled = options.vad ?? false
    this.vadConfig = { ...DEFAULT_VAD_CONFIG, ...options.vadConfig }
  }


  // TTS 预缓冲：攒满 PREBUFFER_MS 毫秒 PCM 后再启动播放，避免前几字卡顿
  private static readonly PREBUFFER_MS = 500
  private static readonly START_DELAY_SEC = 0.15
  /** nextPlayTime 领先 currentTime 超过此值视为"正在播放"，新帧直接无缝衔接 */
  private static readonly PLAYING_MARGIN_SEC = 0.05
  /** 播放中维持的最小缓冲水位：低于此值不调度下一帧，继续攒以避免间隙卡顿 */
  private static readonly MIN_BUFFER_AHEAD_MS = 150
  private ttsQueue: { buffer: AudioBuffer; resolve: () => void }[] = []
  private ttsBufferedMs = 0
  /** 句间衔接标志：softStop 后置 true，让下一帧跳过预缓冲直接启动 */
  private crossSentenceMode = false

  /** 调试日志开关：devtools console 过滤 [VT] 即可查看播放调度细节 */
  private static readonly DEBUG = true
  private log(tag: string, msg: string, data?: unknown): void {
    if (!BrowserVoiceAudio.DEBUG) return
    console.debug(`[VT] ${tag} | ${msg}`, data ?? '')
  }

  private ensurePlaybackRunning(): AudioContext | null {
    const ctx = this.playbackContext
    if (!ctx) {
      return null
    }
    if (ctx.state === 'suspended') {
      void ctx.resume()
    }
    return ctx
  }

  async init(): Promise<void> {
    this.playbackContext = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE })
    await this.playbackContext.resume()
    if (this.vadEnabled) {
      await this.initVad()
    }
    if (!this.vadEnabled) {
      this.captureContext = new AudioContext()
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    }
  }

  /**
   * 加载 Silero VAD（模型/wasm 自托管在 /vad/）。失败时回退老流式采集，不阻塞页面。
   */
  private async initVad(): Promise<void> {
    try {
      this.log('vad', 'loading silero vad model')
      this.vad = await MicVAD.new({
        baseAssetPath: `${import.meta.env.BASE_URL}vad/`,
        onnxWASMBasePath: `${import.meta.env.BASE_URL}vad/`,
        // v5 为较新模型(默认 legacy), 两个 onnx 均已随构建复制
        model: 'v5',
        // 参数来自页面 adapter-config（vadConfig），见文件头 FrontendVadConfig 说明
        positiveSpeechThreshold: this.vadConfig.positive_threshold,
        negativeSpeechThreshold: this.vadConfig.negative_threshold,
        redemptionMs: this.vadConfig.redemption_ms,
        preSpeechPadMs: this.vadConfig.pre_speech_pad_ms,
        minSpeechMs: this.vadConfig.min_speech_ms,
        // pause 时若正在说话也触发 onSpeechEnd，避免切 phase 丢尾
        submitUserSpeechOnPause: true,
        onSpeechStart: () => {
          this.startSegmentTimer()
        },
        onVADMisfire: () => {
          this.clearSegmentTimer()
        },
        onSpeechEnd: (audio) => {
          this.clearSegmentTimer()
          this.sendSegment(audio)
        },
        // ortConfig 在 vad-web JS 实现中支持但类型未暴露, 经 Partial<RealTimeVADOptions> 断言传入。
        // 网关(volcalb)对 .mjs 返回 application/octet-stream, 浏览器动态 import 模块严格 MIME 检查会拦截
        // (线上实测 Failed to fetch dynamically imported module); 故把 ort 的 mjs 绑定指向 .js 扩展名副本
        // (网关按 .js 返回 application/javascript), wasm 二进制显式指定。
        ortConfig: (ort: typeof import('onnxruntime-web')) => {
          ort.env.wasm.wasmPaths = {
            mjs: `${import.meta.env.BASE_URL}vad/ort-wasm-simd-threaded.js`,
            wasm: `${import.meta.env.BASE_URL}vad/ort-wasm-simd-threaded.wasm`,
          } as never
        },
      } as Partial<RealTimeVADOptions>)
      this.vadEnabled = true
      this.log('vad', 'silero vad ready')
    } catch (err) {
      console.warn('[VT] vad init failed, fallback to streaming capture', err)
      this.vad = null
      this.vadEnabled = false
    }
  }

  /** onSpeechEnd 的整段音频（16kHz Float32）→ int16 PCM → 一次性交给调用方（WS 整段发送） */
  private sendSegment(audio: Float32Array): void {
    if (!this.onMicChunk) return
    const int16 = float32To16BitPCM(audio)
    this.log('vad', `segment end samples=${audio.length} (${(audio.length / INPUT_SAMPLE_RATE).toFixed(1)}s)`)
    this.onMicChunk(
      int16.buffer.slice(int16.byteOffset, int16.byteOffset + int16.byteLength) as ArrayBuffer,
    )
  }

  /** 说话超长强制切段：pause 触发 onSpeechEnd（submitUserSpeechOnPause），再恢复监听 */
  private startSegmentTimer(): void {
    this.clearSegmentTimer()
    this.segmentTimer = window.setTimeout(() => {
      this.log('vad', `segment longer than ${VAD_MAX_SEGMENT_MS}ms, force commit`)
      const vad = this.vad
      void vad?.pause().then(() => vad.start())
    }, VAD_MAX_SEGMENT_MS)
  }

  private clearSegmentTimer(): void {
    if (this.segmentTimer !== null) {
      window.clearTimeout(this.segmentTimer)
      this.segmentTimer = null
    }
  }


  async initPlaybackOnly(): Promise<void> {
    this.playbackContext = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE })
    await this.playbackContext.resume()
  }

  async playTtsText(text: string, voice: TtsVoice, hooks?: TtsPlayHooks): Promise<void> {
    const content = text.trim()
    if (!isPlayableTtsText(content)) {
      return
    }
    if (!this.playbackContext) {
      await this.initPlaybackOnly()
    }
    const resp = await fetch(`${BASE_URL}/voice_test/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: content, voice }),
    })
    if (!resp.ok) {
      const detail = await resp.text()
      throw new Error(detail || `TTS 请求失败 (${resp.status})`)
    }
    this.resetPlaybackSchedule()
    hooks?.onAudioStart?.()
    await this.playTtsChunk(await resp.arrayBuffer())
  }

  setListening(value: boolean): void {
    if (this.listening !== value) {
      this.log('audio', `setListening ${this.listening}->${value}`)
    }
    this.listening = value
    if (this.vad) {
      // VAD 模式：phase 控制 VAD 启停（pause 会触发 onSpeechEnd 提交当前段，后端非 LISTENING 会丢弃，无害）
      if (value) {
        void this.vad.start()
      } else {
        void this.vad.pause()
      }
      return
    }
    if (!value) {
      this.pcmBuffer = []
    }
  }

  startCapture(onChunk: (bytes: ArrayBuffer) => void): void {
    this.onMicChunk = onChunk
    if (this.vad) {
      // VAD 模式：mic 采集由 Silero VAD 接管，onSpeechEnd 整段回调走 sendSegment → onMicChunk
      return
    }
    if (!this.captureContext || !this.mediaStream) {
      return
    }
    this.sourceNode = this.captureContext.createMediaStreamSource(this.mediaStream)
    this.processor = this.captureContext.createScriptProcessor(4096, 1, 1)
    this.processor.onaudioprocess = (event) => {
      if (!this.listening || !this.onMicChunk) {
        return
      }
      const input = event.inputBuffer.getChannelData(0)
      const downsampled = downsample(input, this.captureContext!.sampleRate, INPUT_SAMPLE_RATE)
      for (let i = 0; i < downsampled.length; i++) {
        this.pcmBuffer.push(downsampled[i])
      }
      while (this.pcmBuffer.length >= CHUNK_SAMPLES) {
        const slice = this.pcmBuffer.splice(0, CHUNK_SAMPLES)
        const int16 = floatTo16BitPCM(slice)
        this.onMicChunk(
          int16.buffer.slice(int16.byteOffset, int16.byteOffset + int16.byteLength) as ArrayBuffer,
        )
      }
    }
    this.sourceNode.connect(this.processor)
    this.processor.connect(this.captureContext.destination)
  }

  playTtsChunk(bytes: ArrayBuffer): Promise<void> {
    const ctx = this.ensurePlaybackRunning()
    if (!ctx) {
      return Promise.resolve()
    }
    const float32 = new Float32Array(bytes.byteLength / 4)
    float32.set(new Float32Array(bytes))
    const buffer = ctx.createBuffer(1, float32.length, OUTPUT_SAMPLE_RATE)
    buffer.copyToChannel(float32, 0)
    return new Promise((resolve) => {
      this.ttsQueue.push({ buffer, resolve })
      this.ttsBufferedMs += buffer.duration * 1000
      this.log('audio', `playTtsChunk +${(buffer.duration * 1000).toFixed(0)}ms buf=${this.ttsBufferedMs.toFixed(0)}ms queue=${this.ttsQueue.length}`)
      this.trySchedule(ctx)
    })
  }

  /** 正在播放时维持最小水位再衔接；停止时攒满预缓冲再启动；句间衔接跳过预缓冲。 */
  private trySchedule(ctx: AudioContext): void {
    const now = ctx.currentTime
    const isPlaying = this.nextPlayTime > now + BrowserVoiceAudio.PLAYING_MARGIN_SEC
    if (isPlaying) {
      // 正在播放：检查剩余缓冲水位，低于 MIN_BUFFER_AHEAD_MS 继续攒，避免间隙卡顿
      const bufferAheadMs = Math.max(0, (this.nextPlayTime - now) * 1000)
      if (bufferAheadMs >= BrowserVoiceAudio.MIN_BUFFER_AHEAD_MS) {
        this.log('audio', `trySchedule scheduleQueued (playing ahead=${bufferAheadMs.toFixed(0)}ms)`)
        this.scheduleQueued(ctx)
        this.ttsBufferedMs = 0
      } else {
        this.log('audio', `trySchedule hold (playing ahead=${bufferAheadMs.toFixed(0)}ms < ${BrowserVoiceAudio.MIN_BUFFER_AHEAD_MS}ms)`)
      }
      return
    }
    // 已停止：句间衔接模式直接启动（softStop 后第一帧），否则攒满预缓冲才启动
    if (this.crossSentenceMode || this.ttsBufferedMs >= BrowserVoiceAudio.PREBUFFER_MS) {
      const reason = this.crossSentenceMode ? 'cross' : `buf=${this.ttsBufferedMs.toFixed(0)}ms`
      this.log('audio', `trySchedule start (${reason})`)
      this.crossSentenceMode = false
      this.scheduleQueued(ctx)
      this.ttsBufferedMs = 0
    } else {
      this.log('audio', `trySchedule wait (buf=${this.ttsBufferedMs.toFixed(0)}ms < ${BrowserVoiceAudio.PREBUFFER_MS}ms)`)
    }
  }

  /** 把队列里已缓冲的帧按 nextPlayTime 无缝调度播放。 */
  private scheduleQueued(ctx: AudioContext): void {
    while (this.ttsQueue.length > 0) {
      const { buffer, resolve } = this.ttsQueue.shift()!
      const source = ctx.createBufferSource()
      source.buffer = buffer
      source.connect(ctx.destination)
      source.onended = () => {
        this.activeSources = this.activeSources.filter((item) => item !== source)
        resolve()
      }
      this.activeSources.push(source)
      const now = ctx.currentTime
      if (this.nextPlayTime < now) {
        // 首帧留 START_DELAY_SEC 安全余量，后续帧无缝衔接
        this.nextPlayTime = now + BrowserVoiceAudio.START_DELAY_SEC
      }
      source.start(this.nextPlayTime)
      this.nextPlayTime += buffer.duration
    }
  }

  resetPlaybackSchedule(): void {
    this.log('audio', `resetPlaybackSchedule (active=${this.activeSources.length} queue=${this.ttsQueue.length})`)
    this.nextPlayTime = 0
    this.ttsQueue = []
    this.ttsBufferedMs = 0
    this.crossSentenceMode = false
    for (const source of this.activeSources) {
      try {
        source.stop()
      } catch {
        // already stopped
      }
    }
    this.activeSources = []
    void this.playbackContext?.resume()
  }

  /** 轻量停止：停止当前播放，丢弃上一句残留帧，置句间衔接标志让下一句跳过预缓冲。 */
  softStopPlayback(): void {
    this.log('audio', `softStopPlayback (active=${this.activeSources.length} queue=${this.ttsQueue.length})`)
    for (const source of this.activeSources) {
      try {
        source.stop()
      } catch {
        // already stopped
      }
    }
    this.activeSources = []
    this.ttsQueue = []
    this.ttsBufferedMs = 0
    this.nextPlayTime = 0
    // 置句间衔接：下一句第一帧跳过 500ms 预缓冲，直接启动播放
    this.crossSentenceMode = true
    void this.playbackContext?.resume()
  }

  /** 等 WebAudio 已排队的 TTS PCM 全部播完（响应后端 await_playback_drain）。 */
  waitForPlaybackDrain(timeoutMs = 120_000): Promise<void> {
    const ctx = this.playbackContext
    if (!ctx) {
      return Promise.resolve()
    }
    const started = performance.now()
    this.log('audio', `waitForPlaybackDrain start (active=${this.activeSources.length})`)
    return new Promise((resolve) => {
      const poll = () => {
        const drained = this.activeSources.length === 0 && ctx.currentTime >= this.nextPlayTime - 0.02
        if (drained || performance.now() - started >= timeoutMs) {
          this.log('audio', `waitForPlaybackDrain done (drained=${drained})`)
          resolve()
          return
        }
        window.setTimeout(poll, 40)
      }
      poll()
    })
  }

  stop(): void {
    this.clearSegmentTimer()
    if (this.vad) {
      void this.vad.destroy()
      this.vad = null
    }
    this.processor?.disconnect()
    this.sourceNode?.disconnect()
    this.mediaStream?.getTracks().forEach((track) => track.stop())
    if (this.playbackContext) {
      this.playbackContext.close()
    }
    if (this.captureContext) {
      this.captureContext.close()
    }
    this.processor = null
    this.sourceNode = null
    this.mediaStream = null
    this.playbackContext = null
    this.captureContext = null
    this.activeSources = []
    this.pcmBuffer = []
    this.onMicChunk = null
    this.listening = false
    this.ttsQueue = []
    this.ttsBufferedMs = 0
    this.crossSentenceMode = false
  }
}
