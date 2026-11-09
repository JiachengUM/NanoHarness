import { useCallback, useEffect, useRef, useState } from 'react'
import type { LiveAgentClient } from '../adapters/v2AgentClient'
import type { ConsoleAction, Toast } from '../app/consoleReducer'
import type { AgentConsoleEvent } from '../domain/events'
import { errorMessage } from '../utils/unknown'
import { BrowserVoiceAudio, type VoiceAcousticFeatures } from './BrowserVoiceAudio'
import {
  applyVoiceEvent,
  closeVoiceDraftWithoutFinal,
  initialVoiceState,
  openVoiceDraft,
} from './voiceReducer'
import {
  applyPlaybackActiveChangeForSession,
  closeActiveVoiceSession,
  createVoiceEventHandlerForSession,
  ensureVoiceAudioInstance,
  ensureVoicePlaybackAudioInstance,
  runVoiceOutputSequence,
  runVoiceStartupSequence,
  startTextTurnVoiceFlow,
} from './voiceLifecycle'
import type { VoiceEvent } from './voiceTypes'

type DispatchConsoleAction = (action: ConsoleAction) => void
type ShowToast = (message: string, level?: Toast['level']) => void

export function nextVoiceTranscript(current: string, event: VoiceEvent): string {
  if (event.type === 'voice.phase' && event.payload.phase === 'listening') {
    return ''
  }
  if (event.type === 'voice.asr.delta') {
    return `${current}${event.payload.text}`
  }
  if (event.type === 'voice.asr.final') {
    return event.payload.text
  }
  if (event.type === 'voice.error') {
    return ''
  }
  return current
}

export function dispatchMicrophoneAgentEvent({
  event,
  dispatch,
}: {
  event: AgentConsoleEvent
  dispatch: DispatchConsoleAction
}): void {
  dispatch({ type: 'event', event })
}

export function applyAcceptedPlaybackProjection(
  projection: { messageId?: string; revision: number },
  setPlaybackAssistantMessageId: (messageId?: string) => void,
): void {
  if (projection.revision > 0) {
    setPlaybackAssistantMessageId(projection.messageId)
  }
}

export function useVoiceSession({
  acceptedPlaybackMessageId,
  acceptedPlaybackRevision,
  dispatch,
  liveClient,
  liveInput,
  setLiveInput,
  showToast,
}: {
  acceptedPlaybackMessageId?: string
  acceptedPlaybackRevision: number
  dispatch: DispatchConsoleAction
  liveClient: LiveAgentClient
  liveInput: string
  setLiveInput: (input: string) => void
  showToast: ShowToast
}) {
  const [voiceState, setVoiceState] = useState(initialVoiceState)
  const [latestVoiceTranscript, setLatestVoiceTranscript] = useState('')
  const [ttsPlaybackActive, setTtsPlaybackActive] = useState(false)
  const [ttsPlaybackAssistantMessageId, setTtsPlaybackAssistantMessageId] =
    useState<string | undefined>()
  const ttsPlaybackAssistantMessageIdRef = useRef<string | undefined>(undefined)
  const voiceAudioRef = useRef<BrowserVoiceAudio | null>(null)
  const voiceAudioInitPromiseRef = useRef<Promise<BrowserVoiceAudio> | null>(null)
  const voiceSessionSeqRef = useRef(0)
  const playbackSessionSeqRef = useRef(0)

  const setPlaybackAssistantMessageId = useCallback((messageId?: string) => {
    ttsPlaybackAssistantMessageIdRef.current = messageId
    setTtsPlaybackAssistantMessageId(messageId)
  }, [])

  const handleTtsPlaybackActiveChange = useCallback((
    active: boolean,
    completedNaturally = false,
  ) => {
    applyPlaybackActiveChangeForSession({
      active,
      completed: completedNaturally,
      seq: playbackSessionSeqRef.current,
      getCurrentSeq: () => voiceSessionSeqRef.current,
      setPlaybackActive: setTtsPlaybackActive,
      setPlaybackAssistantMessageId,
      notifyVoicePlaybackEnded: () => liveClient.notifyVoicePlaybackEnded(),
    })
  }, [liveClient, setPlaybackAssistantMessageId])

  useEffect(() => {
    applyAcceptedPlaybackProjection({
      messageId: acceptedPlaybackMessageId,
      revision: acceptedPlaybackRevision,
    }, setPlaybackAssistantMessageId)
  }, [
    acceptedPlaybackMessageId,
    acceptedPlaybackRevision,
    setPlaybackAssistantMessageId,
  ])

  useEffect(
    () => () => {
      voiceSessionSeqRef.current += 1
      voiceAudioRef.current?.stop()
      voiceAudioRef.current = null
      voiceAudioInitPromiseRef.current = null
    },
    [],
  )

  const makeVoiceEventHandler = useCallback((seq: number) => {
    const handleEvent = createVoiceEventHandlerForSession({
      seq,
      getCurrentSeq: () => voiceSessionSeqRef.current,
      applyEvent: (event) => setVoiceState((current) => applyVoiceEvent(current, event)),
      setLiveInput,
      dispatchConsoleAction: (action) => dispatch(action),
      stopLocalAudio: () => {
        voiceAudioRef.current?.setListening(false)
        voiceAudioRef.current?.stop()
        voiceAudioRef.current = null
        voiceAudioInitPromiseRef.current = null
        setLatestVoiceTranscript('')
      },
      setPlaybackDucked: (ducked) => voiceAudioRef.current?.setPlaybackDucked(ducked),
      setPlaybackAssistantMessageId,
      resetPlaybackSchedule: () => voiceAudioRef.current?.resetPlaybackSchedule(),
      showToast: (message) => showToast(message, 'error'),
      now: () => new Date().toISOString(),
    })
    return (event: Parameters<typeof handleEvent>[0]) => {
      if (voiceSessionSeqRef.current !== seq) {
        return
      }
      setLatestVoiceTranscript((current) => nextVoiceTranscript(current, event))
      handleEvent(event)
    }
  }, [dispatch, setLiveInput, setPlaybackAssistantMessageId, showToast])

  const readVoiceAcoustics = useCallback((): VoiceAcousticFeatures | null => {
    return voiceAudioRef.current?.readCaptureFeatures() ?? null
  }, [])

  const createVoiceAudio = useCallback(() => new BrowserVoiceAudio(
    handleTtsPlaybackActiveChange,
    () => ({
      message_id: ttsPlaybackAssistantMessageIdRef.current,
      generation: voiceSessionSeqRef.current,
    }),
  ), [handleTtsPlaybackActiveChange])

  const ensureVoiceAudio = useCallback(async () => {
    return ensureVoiceAudioInstance({
      audioRef: voiceAudioRef,
      initPromiseRef: voiceAudioInitPromiseRef,
      createAudio: createVoiceAudio,
      onCaptureChunk: (chunk) => {
        void liveClient.sendVoiceAudio(chunk).catch((error: unknown) => {
          const message = errorMessage(error)
          showToast(`发送语音失败: ${message}`, 'error')
        })
      },
    })
  }, [createVoiceAudio, liveClient, showToast])

  const ensureVoicePlaybackAudio = useCallback(async () => {
    return ensureVoicePlaybackAudioInstance({
      audioRef: voiceAudioRef,
      createAudio: createVoiceAudio,
    })
  }, [createVoiceAudio])

  const toggleVoice = useCallback(() => {
    const voiceActive = voiceState.microphoneOpen || voiceState.phase === 'mic_pending'

    if (voiceActive) {
      setPlaybackAssistantMessageId(undefined)
      setTtsPlaybackActive(false)
      closeActiveVoiceSession({
        voiceState,
        voiceSessionSeqRef,
        voiceAudioRef,
        voiceAudioInitPromiseRef,
        liveClient,
        setVoiceState,
        setLiveInput,
      })
      setLatestVoiceTranscript('')
      return
    }

    const seq = voiceSessionSeqRef.current + 1
    voiceSessionSeqRef.current = seq
    playbackSessionSeqRef.current = seq
    setPlaybackAssistantMessageId(undefined)
    const opened = openVoiceDraft(voiceState, liveInput)
    setLatestVoiceTranscript('')
    setVoiceState(opened)
    setLiveInput('')

    void runVoiceStartupSequence({
      seq,
      isCurrent: (currentSeq) => voiceSessionSeqRef.current === currentSeq,
      ensureVoiceAudio,
      liveClient,
      onAgentEvent: (event) => dispatchMicrophoneAgentEvent({
        event,
        dispatch,
      }),
      onVoiceEvent: makeVoiceEventHandler(seq),
      onVoiceError: (error: unknown) => {
        const message = errorMessage(error)
        showToast(`语音连接异常: ${message}`, 'error')
      },
      restoreVoiceDraft: (error: unknown) => {
        const restored = closeVoiceDraftWithoutFinal(opened)
        setVoiceState(restored)
        setLiveInput(restored.draftText)
        const message = errorMessage(error)
        showToast(`无法访问麦克风: ${message}`, 'error')
      },
    })
  }, [dispatch, ensureVoiceAudio, liveClient, liveInput, makeVoiceEventHandler, setLiveInput, setPlaybackAssistantMessageId, showToast, voiceState])

  const startTextTurnVoiceOutput = useCallback(({
    startAgentRun,
  }: {
    startAgentRun: () => void
  }) => {
    const voiceOutputSeq = voiceSessionSeqRef.current + 1
    voiceSessionSeqRef.current = voiceOutputSeq
    playbackSessionSeqRef.current = voiceOutputSeq
    voiceAudioRef.current?.resetPlaybackSchedule()
    setTtsPlaybackActive(false)

    startTextTurnVoiceFlow({
      startAgentRun,
      startVoiceOutput: () => runVoiceOutputSequence({
        seq: voiceOutputSeq,
        isCurrent: (currentSeq) => voiceSessionSeqRef.current === currentSeq,
        ensureVoiceAudio: ensureVoicePlaybackAudio,
        liveClient,
        onAgentEvent: (event) => dispatch({ type: 'event', event }),
        onVoiceEvent: (event) => setVoiceState((current) => applyVoiceEvent(current, event)),
        onVoiceError: (error: unknown) => {
          setPlaybackAssistantMessageId(undefined)
          const message = errorMessage(error)
          showToast(`语音播报连接异常: ${message}`, 'error')
        },
      }),
      onVoiceOutputError: (error: unknown) => {
        setPlaybackAssistantMessageId(undefined)
        const message = errorMessage(error)
        showToast(`语音播报连接异常: ${message}`, 'error')
      },
    })
  }, [dispatch, ensureVoicePlaybackAudio, liveClient, setPlaybackAssistantMessageId, showToast])

  const resetVoiceSession = useCallback(() => {
    voiceSessionSeqRef.current += 1
    voiceAudioRef.current?.stop()
    voiceAudioRef.current = null
    voiceAudioInitPromiseRef.current = null
    setLatestVoiceTranscript('')
    setTtsPlaybackActive(false)
    setPlaybackAssistantMessageId(undefined)
    setVoiceState(initialVoiceState())
    void liveClient.stopVoice().catch(() => undefined)
  }, [liveClient, setPlaybackAssistantMessageId])

  return {
    inputLocked: voiceState.inputLocked,
    latestVoiceTranscript,
    liveInputValue: voiceState.inputLocked ? voiceState.draftText || liveInput : liveInput,
    readVoiceAcoustics,
    resetVoiceSession,
    startTextTurnVoiceOutput,
    speakingAssistantMessageId: ttsPlaybackActive ? ttsPlaybackAssistantMessageId : undefined,
    toggleVoice,
    voiceMicrophoneOpen: voiceState.microphoneOpen,
    voicePhase: voiceState.phase,
  }
}
