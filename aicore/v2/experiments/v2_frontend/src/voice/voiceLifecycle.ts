import type { LiveAgentClient } from '../adapters/v2AgentClient'
import type { ConsoleAction } from '../app/consoleReducer'
import type { AgentConsoleEvent } from '../domain/events'
import { asString } from '../utils/unknown'
import type { BrowserVoiceAudio } from './BrowserVoiceAudio'
import { closeVoiceDraftWithoutFinal } from './voiceReducer'
import type { VoiceEvent, VoiceState } from './voiceTypes'

type VoiceAudioRuntime = Pick<
  BrowserVoiceAudio,
  | 'init'
  | 'initPlayback'
  | 'startCapture'
  | 'stop'
  | 'resetPlaybackSchedule'
  | 'setListening'
  | 'playTtsChunk'
  | 'setPlaybackDucked'
>

type BackendVoiceClient = Pick<
  LiveAgentClient,
  'startVoice' | 'openVoiceMicrophone' | 'closeVoiceMicrophone' | 'stopVoice'
>
type VoiceOutputClient = Pick<LiveAgentClient, 'startVoice'>
type VoiceStopClient = Pick<BackendVoiceClient, 'closeVoiceMicrophone' | 'stopVoice'>
type VoiceConsoleAction = Extract<
  ConsoleAction,
  {
    type:
      | 'appendVoiceUserMessage'
      | 'appendVoiceFeedbackMessage'
      | 'markVoiceSubmitFailed'
  }
>

export function createVoiceEventHandlerForSession({
  seq,
  getCurrentSeq,
  applyEvent,
  setLiveInput,
  dispatchConsoleAction,
  stopLocalAudio,
  setPlaybackDucked,
  setPlaybackAssistantMessageId,
  resetPlaybackSchedule,
  showToast,
  now,
}: {
  seq: number
  getCurrentSeq: () => number
  applyEvent: (event: VoiceEvent) => void
  setLiveInput: (input: string) => void
  dispatchConsoleAction: (action: VoiceConsoleAction) => void
  stopLocalAudio: () => void
  setPlaybackDucked?: (ducked: boolean) => void
  setPlaybackAssistantMessageId?: (messageId: string | undefined) => void
  resetPlaybackSchedule: () => void
  showToast: (message: string) => void
  now: () => string
}): (event: VoiceEvent) => void {
  return (event) => {
    if (getCurrentSeq() !== seq) {
      return
    }

    applyEvent(event)

    if (event.type === 'voice.asr.delta') {
      setLiveInput(asString(event.payload.text))
      return
    }

    if (event.type === 'voice.asr.final') {
      dispatchConsoleAction({
        type: 'appendVoiceUserMessage',
        turnId: event.payload.turn_id,
        userMessageId: event.payload.user_message_id,
        text: event.payload.text,
        ...(event.payload.assistant_message_id
          ? { assistantMessageId: event.payload.assistant_message_id }
          : {}),
        timestamp: now(),
      })
      setLiveInput('')
      return
    }

    if (event.type === 'voice.feedback') {
      dispatchConsoleAction({
        type: 'appendVoiceFeedbackMessage',
        turnId: event.payload.turn_id,
        feedbackId: event.payload.feedback_id,
        text: event.payload.text,
        timestamp: now(),
      })
      return
    }

    if (event.type === 'voice.playback.duck') {
      setPlaybackDucked?.(true)
      return
    }

    if (event.type === 'voice.playback.restore') {
      setPlaybackDucked?.(false)
      return
    }

    if (event.type === 'voice.submit.failed') {
      dispatchConsoleAction({
        type: 'markVoiceSubmitFailed',
        turnId: event.payload.turn_id,
        userMessageId: event.payload.user_message_id,
        assistantMessageId: event.payload.assistant_message_id,
        timestamp: now(),
      })
      return
    }

    if (event.type === 'voice.interrupted') {
      setPlaybackDucked?.(false)
      resetPlaybackSchedule()
      setPlaybackAssistantMessageId?.(undefined)
      return
    }

    if (event.type === 'voice.error') {
      stopLocalAudio()
      const message = asString(event.payload.message, asString(event.payload.error))
      if (message) {
        showToast(message)
      }
    }
  }
}

export function applyPlaybackActiveChangeForSession({
  active,
  completed,
  seq,
  getCurrentSeq,
  setPlaybackActive,
  setPlaybackAssistantMessageId,
  notifyVoicePlaybackEnded,
}: {
  active: boolean
  completed: boolean
  seq: number
  getCurrentSeq: () => number
  setPlaybackActive: (active: boolean) => void
  setPlaybackAssistantMessageId: (messageId: string | undefined) => void
  notifyVoicePlaybackEnded: () => Promise<void>
}): void {
  if (getCurrentSeq() !== seq) {
    return
  }
  setPlaybackActive(active)
  if (active) {
    return
  }
  setPlaybackAssistantMessageId(undefined)
  if (completed) {
    void notifyVoicePlaybackEnded().catch(() => undefined)
  }
}

export function ensureVoiceAudioInstance<TAudio extends Pick<VoiceAudioRuntime, 'init' | 'startCapture' | 'stop'>>({
  audioRef,
  initPromiseRef,
  createAudio,
  onCaptureChunk,
}: {
  audioRef: { current: TAudio | null }
  initPromiseRef: { current: Promise<TAudio> | null }
  createAudio: () => TAudio
  onCaptureChunk: (bytes: ArrayBuffer) => void
}): Promise<TAudio> {
  if (initPromiseRef.current) {
    return initPromiseRef.current
  }

  if (!audioRef.current) {
    audioRef.current = createAudio()
  }
  const audio = audioRef.current

  let initPromise!: Promise<TAudio>
  initPromise = (async () => {
    try {
      await audio.init()
      if (audioRef.current !== audio) {
        audio.stop()
        throw new Error('Voice audio initialization was cancelled')
      }
      audio.startCapture(onCaptureChunk)
      return audio
    } catch (error: unknown) {
      audio.stop()
      if (audioRef.current === audio) {
        audioRef.current = null
      }
      throw error
    } finally {
      if (initPromiseRef.current === initPromise) {
        initPromiseRef.current = null
      }
    }
  })()
  initPromiseRef.current = initPromise
  return initPromise
}

export async function ensureVoicePlaybackAudioInstance<
  TAudio extends Pick<VoiceAudioRuntime, 'initPlayback' | 'stop'>
>({
  audioRef,
  createAudio,
}: {
  audioRef: { current: TAudio | null }
  createAudio: () => TAudio
}): Promise<TAudio> {
  const audio = audioRef.current ?? createAudio()
  audioRef.current = audio

  try {
    await audio.initPlayback()
    if (audioRef.current !== audio) {
      audio.stop()
      throw new Error('Voice playback initialization was cancelled')
    }
    return audio
  } catch (error: unknown) {
    audio.stop()
    if (audioRef.current === audio) {
      audioRef.current = null
    }
    throw error
  }
}

async function stopBackendVoice(liveClient: VoiceStopClient): Promise<void> {
  await liveClient.closeVoiceMicrophone().catch(() => undefined)
  await liveClient.stopVoice().catch(() => undefined)
}

export function closeActiveVoiceSession({
  voiceState,
  voiceSessionSeqRef,
  voiceAudioRef,
  voiceAudioInitPromiseRef,
  liveClient,
  setVoiceState,
  setLiveInput,
}: {
  voiceState: VoiceState
  voiceSessionSeqRef: { current: number }
  voiceAudioRef: { current: Pick<VoiceAudioRuntime, 'setListening' | 'stop'> | null }
  voiceAudioInitPromiseRef: { current: Promise<unknown> | null }
  liveClient: VoiceStopClient
  setVoiceState: (state: VoiceState) => void
  setLiveInput: (input: string) => void
}): void {
  voiceSessionSeqRef.current += 1
  voiceAudioRef.current?.setListening(false)
  voiceAudioRef.current?.stop()
  voiceAudioRef.current = null
  voiceAudioInitPromiseRef.current = null

  const restored = closeVoiceDraftWithoutFinal(voiceState)
  setVoiceState(restored)
  setLiveInput(restored.draftText)

  void stopBackendVoice(liveClient)
}

type VoiceAudioResult = Pick<VoiceAudioRuntime, 'resetPlaybackSchedule' | 'setListening' | 'playTtsChunk'>

interface VoiceSequenceOptions {
  seq: number
  isCurrent: (seq: number) => boolean
  ensureVoiceAudio: () => Promise<VoiceAudioResult>
  liveClient: VoiceOutputClient
  onAgentEvent: (event: AgentConsoleEvent) => void
  onVoiceEvent: (event: VoiceEvent) => void
  onVoiceError: (error: unknown) => void
}

async function runVoiceSequence(
  options: VoiceSequenceOptions & {
    openMicrophone: boolean
    onFatalError: (error: unknown, audio: VoiceAudioResult | null) => void
  },
): Promise<void> {
  const { seq, isCurrent, ensureVoiceAudio, liveClient, onAgentEvent, onVoiceEvent, onVoiceError, openMicrophone, onFatalError } = options
  let audio: VoiceAudioResult | null = null
  let voiceStarted = false

  try {
    audio = await ensureVoiceAudio()
    if (!isCurrent(seq)) {
      audio.setListening(false)
      return
    }

    if (!openMicrophone) {
      audio.setListening(false)
    }
    audio.resetPlaybackSchedule()
    await liveClient.startVoice({
      onEvent: (event) => {
        if (isCurrent(seq)) {
          onAgentEvent(event)
        }
      },
      onVoiceEvent: openMicrophone
        ? onVoiceEvent
        : (event) => { if (isCurrent(seq)) onVoiceEvent(event) },
      onVoiceAudio: (chunk) => {
        if (isCurrent(seq)) {
          audio?.playTtsChunk(chunk)
        }
      },
      onError: (error) => {
        if (isCurrent(seq)) {
          onVoiceError(error)
        }
      },
    })
    voiceStarted = true
    if (!isCurrent(seq)) {
      audio.setListening(false)
      if (openMicrophone) {
        await stopBackendVoice(liveClient as BackendVoiceClient)
      }
      return
    }

    if (openMicrophone) {
      const micClient = liveClient as BackendVoiceClient
      await micClient.openVoiceMicrophone()
      if (!isCurrent(seq)) {
        audio.setListening(false)
        await stopBackendVoice(micClient)
        return
      }
      audio.setListening(true)
    }
  } catch (error: unknown) {
    if (voiceStarted && openMicrophone) {
      await stopBackendVoice(liveClient as BackendVoiceClient)
    }
    if (!isCurrent(seq)) {
      return
    }
    onFatalError(error, audio)
  }
}

export async function runVoiceStartupSequence(
  options: VoiceSequenceOptions & {
    liveClient: BackendVoiceClient
    restoreVoiceDraft: (error: unknown) => void
  },
): Promise<void> {
  await runVoiceSequence({
    ...options,
    openMicrophone: true,
    onFatalError: (error, audio) => {
      audio?.setListening(false)
      options.restoreVoiceDraft(error)
    },
  })
}

export async function runVoiceOutputSequence(
  options: VoiceSequenceOptions & {
    liveClient: VoiceOutputClient
  },
): Promise<void> {
  await runVoiceSequence({
    ...options,
    openMicrophone: false,
    onFatalError: (error, audio) => {
      audio?.setListening(false)
      options.onVoiceError(error)
    },
  })
}

export function startTextTurnVoiceFlow({
  startAgentRun,
  startVoiceOutput,
  onVoiceOutputError,
}: {
  startAgentRun: () => void
  startVoiceOutput: () => Promise<void>
  onVoiceOutputError: (error: unknown) => void
}): void {
  startAgentRun()
  void startVoiceOutput().catch(onVoiceOutputError)
}
