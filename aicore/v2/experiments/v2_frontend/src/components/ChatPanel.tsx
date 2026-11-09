import { useEffect, useRef, useState, type FormEvent } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage } from '../app/consoleReducer'
import type { VoicePhase } from '../voice/voiceTypes'
import {
  CAPABILITY_EXPERIENCES,
  CapabilityGuide,
  type CapabilityExperience,
  type CapabilityExperienceId,
} from './CapabilityGuide'

type ChatPanelProps = {
  messages: ChatMessage[]
  liveInput: string
  isPlaying: boolean
  connected: boolean | null
  voicePhase: VoicePhase
  voiceInputLocked: boolean
  voiceMicrophoneOpen: boolean
  modeResetting: boolean
  textInputEnabled?: boolean
  speakingAssistantMessageId?: string
  onLiveInputChange: (input: string) => void
  onStartLive: () => void
  onToggleVoice: () => void
}

type ChatScrollMetrics = {
  clientHeight: number
  scrollHeight: number
  currentScrollTop: number
}

type ChatGrowthScrollMetrics = ChatScrollMetrics & {
  previousScrollHeight: number
  isInitial: boolean
  wasFollowingLatest?: boolean
}

const CHAT_FOLLOW_THRESHOLD = 32
const CAPABILITY_GUIDE_STORAGE_KEY = 'v2-capability-guide-seen-v1'

const ASSISTANT_MARKDOWN_COMPONENTS: Components = {
  a: ({ node: _node, ...props }) => (
    <a {...props} target="_blank" rel="noreferrer noopener" />
  ),
}

type ActiveCapabilityExperience = {
  id: CapabilityExperienceId
  stepIndex: number
  awaitingResponse: boolean
  assistantResponseCountAtSubmit: number
}

export function getAssistantResponseCount(messages: ChatMessage[]): number {
  return messages.filter(
    (message) =>
      message.role === 'assistant'
      && (message.content.trim().length > 0 || message.status !== 'streaming'),
  ).length
}

function readCapabilityGuideSeen(): boolean {
  if (typeof window === 'undefined') {
    return false
  }
  try {
    return window.localStorage.getItem(CAPABILITY_GUIDE_STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

function writeCapabilityGuideSeen() {
  if (typeof window === 'undefined') {
    return
  }
  try {
    window.localStorage.setItem(CAPABILITY_GUIDE_STORAGE_KEY, 'true')
  } catch {
    // The guide remains usable when storage is unavailable.
  }
}

export function isChatAtLatest(metrics: ChatScrollMetrics): boolean {
  return metrics.currentScrollTop + metrics.clientHeight >=
    metrics.scrollHeight - CHAT_FOLLOW_THRESHOLD
}

export function getChatScrollTarget(metrics: ChatGrowthScrollMetrics) {
  const maximumTop = Math.max(0, metrics.scrollHeight - metrics.clientHeight)
  const clampedTop = Math.min(maximumTop, Math.max(0, metrics.currentScrollTop))
  const contentGrew = metrics.scrollHeight > metrics.previousScrollHeight
  const followedPreviousBottom = metrics.wasFollowingLatest ?? (
    metrics.currentScrollTop + metrics.clientHeight >=
      metrics.previousScrollHeight - CHAT_FOLLOW_THRESHOLD
  )
  const top = metrics.isInitial || (contentGrew && followedPreviousBottom)
    ? maximumTop
    : clampedTop
  return top === metrics.currentScrollTop
    ? { shouldScroll: false, top }
    : { shouldScroll: true, top }
}

function formatMessageTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) {
    return '--:--:--'
  }
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

export function ChatPanel({
  messages,
  liveInput,
  isPlaying,
  connected,
  voicePhase,
  voiceInputLocked,
  voiceMicrophoneOpen,
  modeResetting,
  textInputEnabled = true,
  speakingAssistantMessageId,
  onLiveInputChange,
  onStartLive,
  onToggleVoice,
}: ChatPanelProps) {
  const messageListRef = useRef<HTMLDivElement | null>(null)
  const liveInputRef = useRef<HTMLInputElement | null>(null)
  const capabilityTriggerRef = useRef<HTMLButtonElement | null>(null)
  const previousMessageHeightRef = useRef<number | undefined>(undefined)
  const isFollowingLatestRef = useRef(true)
  const [isViewingHistory, setIsViewingHistory] = useState(false)
  const [hasSeenCapabilityGuide, setHasSeenCapabilityGuide] = useState(
    readCapabilityGuideSeen,
  )
  const [isCapabilityGuideOpen, setIsCapabilityGuideOpen] = useState(
    () => messages.length === 0 && !readCapabilityGuideSeen(),
  )
  const [activeExperience, setActiveExperience] =
    useState<ActiveCapabilityExperience>()
  const inputDisabled =
    !textInputEnabled || modeResetting || voiceInputLocked || connected === false
  const canSubmitLive =
    liveInput.trim().length > 0
    && connected !== false
    && textInputEnabled
    && !voiceInputLocked
    && !modeResetting
  const voiceActive = voiceMicrophoneOpen || voicePhase === 'mic_pending'
  const voiceLabel = voicePhase === 'mic_pending'
    ? '正在开启语音输入'
    : voiceMicrophoneOpen
      ? '关闭语音输入'
      : '开启语音输入'
  const voiceHint = voicePhase === 'error' ? '语音连接异常' : ''

  const markCapabilityGuideSeen = () => {
    setHasSeenCapabilityGuide(true)
    writeCapabilityGuideSeen()
  }

  const closeCapabilityGuide = () => {
    markCapabilityGuideSeen()
    setIsCapabilityGuideOpen(false)
    capabilityTriggerRef.current?.focus()
  }

  const fillLiveInput = (prompt: string) => {
    onLiveInputChange(prompt)
    window.requestAnimationFrame(() => {
      const input = liveInputRef.current
      if (!input) {
        return
      }
      input.focus()
      input.setSelectionRange(prompt.length, prompt.length)
    })
  }

  const startCapabilityExperience = (experience: CapabilityExperience) => {
    markCapabilityGuideSeen()
    setIsCapabilityGuideOpen(false)
    setActiveExperience({
      id: experience.id,
      stepIndex: 0,
      awaitingResponse: false,
      assistantResponseCountAtSubmit: getAssistantResponseCount(messages),
    })
    fillLiveInput(experience.prompts[0])
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!canSubmitLive) {
      return
    }
    if (isCapabilityGuideOpen) {
      markCapabilityGuideSeen()
      setIsCapabilityGuideOpen(false)
    }
    if (activeExperience && activeExperience.stepIndex <
      (CAPABILITY_EXPERIENCES.find(
        (experience) => experience.id === activeExperience.id,
      )?.prompts.length ?? 0)
    ) {
      setActiveExperience({
        ...activeExperience,
        awaitingResponse: true,
        assistantResponseCountAtSubmit: getAssistantResponseCount(messages),
      })
    }
    onStartLive()
  }

  useEffect(() => {
    const scroller = messageListRef.current
    if (!scroller) {
      return
    }

    const isInitial = previousMessageHeightRef.current === undefined
    const previousScrollHeight = previousMessageHeightRef.current ?? scroller.scrollHeight
    const target = getChatScrollTarget({
      clientHeight: scroller.clientHeight,
      scrollHeight: scroller.scrollHeight,
      currentScrollTop: scroller.scrollTop,
      previousScrollHeight,
      isInitial,
      wasFollowingLatest: isFollowingLatestRef.current,
    })

    if (target.shouldScroll) {
      scroller.scrollTop = target.top
    }

    previousMessageHeightRef.current = scroller.scrollHeight
    const isFollowingLatest = isChatAtLatest({
      clientHeight: scroller.clientHeight,
      scrollHeight: scroller.scrollHeight,
      currentScrollTop: scroller.scrollTop,
    })
    isFollowingLatestRef.current = isFollowingLatest
    setIsViewingHistory(!isFollowingLatest)
  }, [messages])

  useEffect(() => {
    const scroller = messageListRef.current
    if (!scroller || typeof ResizeObserver === 'undefined') {
      return
    }

    const reconcile = () => {
      const maximumTop = Math.max(0, scroller.scrollHeight - scroller.clientHeight)
      const clampedTop = Math.min(maximumTop, Math.max(0, scroller.scrollTop))
      const targetTop = isFollowingLatestRef.current ? maximumTop : clampedTop
      if (targetTop !== scroller.scrollTop) {
        scroller.scrollTop = targetTop
      }

      previousMessageHeightRef.current = scroller.scrollHeight
      const isFollowingLatest = isChatAtLatest({
        clientHeight: scroller.clientHeight,
        scrollHeight: scroller.scrollHeight,
        currentScrollTop: scroller.scrollTop,
      })
      isFollowingLatestRef.current = isFollowingLatest
      setIsViewingHistory(!isFollowingLatest)
    }

    const observer = new ResizeObserver(reconcile)
    observer.observe(scroller)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!activeExperience?.awaitingResponse) {
      return
    }
    if (
      getAssistantResponseCount(messages)
      <= activeExperience.assistantResponseCountAtSubmit
    ) {
      return
    }
    setActiveExperience({
      ...activeExperience,
      stepIndex: activeExperience.stepIndex + 1,
      awaitingResponse: false,
    })
  }, [activeExperience, messages])

  useEffect(() => {
    if (!isCapabilityGuideOpen || messages.length === 0) {
      return
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') {
        return
      }
      closeCapabilityGuide()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [isCapabilityGuideOpen, messages.length])

  const selectedExperience = activeExperience
    ? CAPABILITY_EXPERIENCES.find(
      (experience) => experience.id === activeExperience.id,
    )
    : undefined
  const currentExperiencePrompt = selectedExperience?.prompts[
    activeExperience?.stepIndex ?? 0
  ]
  const experienceComplete = Boolean(
    selectedExperience
    && activeExperience
    && activeExperience.stepIndex >= selectedExperience.prompts.length,
  )

  return (
    <section className="panel chat-panel">
      <header className="panel-header chat-panel-header">
        <div>
          <p className="eyebrow">conversation</p>
          <h2>对话</h2>
          <p className="panel-subtitle">输入任务，或使用语音连续交流</p>
        </div>
        <div className="capability-entry">
          <button
            aria-controls="capability-guide-surface"
            aria-expanded={isCapabilityGuideOpen}
            className="capability-trigger"
            ref={capabilityTriggerRef}
            type="button"
            onClick={() => {
              const nextOpen = !isCapabilityGuideOpen
              if (nextOpen) {
                markCapabilityGuideSeen()
              }
              setIsCapabilityGuideOpen(nextOpen)
            }}
          >
            <span className="capability-trigger-spark" aria-hidden="true">✦</span>
            新能力 · 3
            {!hasSeenCapabilityGuide && !isCapabilityGuideOpen && (
              <span className="capability-trigger-new">NEW</span>
            )}
          </button>
          {messages.length > 0 && isCapabilityGuideOpen && (
            <div className="capability-popover">
              <CapabilityGuide
                disabled={inputDisabled}
                variant="popover"
                onClose={closeCapabilityGuide}
                onTry={startCapabilityExperience}
              />
            </div>
          )}
        </div>
      </header>
      <div
        className="message-list"
        ref={messageListRef}
        onScroll={(event) => {
          const scroller = event.currentTarget
          previousMessageHeightRef.current = scroller.scrollHeight
          const isFollowingLatest = isChatAtLatest({
            clientHeight: scroller.clientHeight,
            scrollHeight: scroller.scrollHeight,
            currentScrollTop: scroller.scrollTop,
          })
          isFollowingLatestRef.current = isFollowingLatest
          setIsViewingHistory(!isFollowingLatest)
        }}
      >
        {messages.length === 0 ? (
          isCapabilityGuideOpen ? (
            <div className="capability-welcome-shell">
              <CapabilityGuide
                disabled={inputDisabled}
                variant="empty"
                onClose={closeCapabilityGuide}
                onTry={startCapabilityExperience}
              />
            </div>
          ) : (
            <div className="empty-copy chat-empty">
              <strong>开始一次对话</strong>
              <span>输入任务，或开启语音连续交流。</span>
            </div>
          )
        ) : (
          <>
            {messages.map((message) => {
              const avatarLabel = message.role === 'user' ? '用户头像' : 'Agent头像'
              const isSpeakingAssistant =
                message.role === 'assistant' && message.id === speakingAssistantMessageId
              const isWaitingForAgent =
                message.role === 'assistant' &&
                message.status === 'streaming' &&
                message.content.length === 0
              const isInterrupted = message.role === 'assistant' && message.status === 'interrupted'
              const isTaskResult = message.role === 'assistant' && Boolean(message.sourceTaskId)
              const isQuickResponse =
                message.role === 'assistant'
                && message.voiceMessageKind === 'quick-response'

              return (
                <article
                  key={message.id}
                  className={`message-row ${message.role}${isSpeakingAssistant ? ' speaking' : ''}`}
                >
                  <div
                    className={`message-avatar ${message.role}${isSpeakingAssistant ? ' speaking' : ''}`}
                    role="img"
                    aria-label={avatarLabel}
                  >
                    {message.role === 'user' ? (
                      <svg viewBox="0 0 32 32" aria-hidden="true">
                        <circle cx="16" cy="16" r="16" fill="#dcebff" />
                        <circle cx="16" cy="13" r="5" fill="#2f6fed" />
                        <path
                          d="M6.5 27a9.5 9.5 0 0 1 19 0Z"
                          fill="#2f6fed"
                        />
                      </svg>
                    ) : (
                      <svg viewBox="0 0 32 32" aria-hidden="true">
                        <circle cx="16" cy="16" r="16" fill="#e3f7ef" />
                        <rect x="8" y="11" width="16" height="12" rx="4" fill="#1f9d70" />
                        <circle cx="13" cy="17" r="1.8" fill="#fff" />
                        <circle cx="19" cy="17" r="1.8" fill="#fff" />
                        <path d="M16 6v3" stroke="#1f9d70" strokeWidth="1.6" strokeLinecap="round" />
                        <circle cx="16" cy="5.5" r="1.8" fill="#1f9d70" />
                      </svg>
                    )}
                  </div>
                  <div className={`message-stack ${message.role}`}>
                    <div className={`message-bubble ${message.role}${isSpeakingAssistant ? ' speaking' : ''}`}>
                      {isTaskResult && (
                        <div className="task-result-source">
                          <span className="task-result-title">
                            后台任务结果{message.sourceTaskTitle ? ` · ${message.sourceTaskTitle}` : ''}
                          </span>
                        </div>
                      )}
                      {isQuickResponse && (
                        <div className="quick-feedback-source">
                          <span>快速回应</span>
                        </div>
                      )}
                      {isWaitingForAgent ? (
                        <div className="message-waiting" role="status" aria-label="Agent 正在回复">
                          <span className="message-waiting-spinner" aria-hidden="true" />
                          <span>思考中</span>
                        </div>
                      ) : (
                        <>
                          {isSpeakingAssistant && (
                            <span className="speaking-indicator" aria-label="正在播报">
                              <span className="speaking-wave" aria-hidden="true">
                                <i /><i /><i /><i />
                              </span>
                              正在播报
                            </span>
                          )}
                          {message.role === 'assistant' ? (
                            <div
                              className={`message-markdown${message.status === 'streaming' ? ' is-streaming' : ''}`}
                            >
                              <ReactMarkdown
                                components={ASSISTANT_MARKDOWN_COMPONENTS}
                                remarkPlugins={[remarkGfm]}
                              >
                                {message.content}
                              </ReactMarkdown>
                            </div>
                          ) : <p>{message.content}</p>}
                          {message.status === 'streaming' && <span className="cursor">▌</span>}
                          {isInterrupted && <span className="message-interrupted">已被打断</span>}
                        </>
                      )}
                    </div>
                    <time className="message-timestamp" dateTime={message.createdAt}>
                      {formatMessageTimestamp(message.createdAt)}
                    </time>
                  </div>
                </article>
              )
            })}
          </>
        )}
      </div>
      {isViewingHistory && (
        <button
          className="return-to-latest"
          type="button"
          onClick={() => {
            const scroller = messageListRef.current
            if (!scroller) {
              return
            }
            scroller.scrollTop = Math.max(0, scroller.scrollHeight - scroller.clientHeight)
            previousMessageHeightRef.current = scroller.scrollHeight
            isFollowingLatestRef.current = true
            setIsViewingHistory(false)
          }}
        >
          回到最新
        </button>
      )}
      {activeExperience && selectedExperience && (
        <section
          aria-live="polite"
          className={`experience-coach${activeExperience.awaitingResponse ? ' is-waiting' : ''}${experienceComplete ? ' is-complete' : ''}`}
        >
          <div className="experience-coach-copy">
            <div className="experience-coach-heading">
              <span className="experience-coach-step">
                {experienceComplete
                  ? '体验完成'
                  : `体验 ${Math.min(
                    activeExperience.stepIndex + 1,
                    selectedExperience.prompts.length,
                  )}/${selectedExperience.prompts.length}`}
              </span>
              <strong>{selectedExperience.title}</strong>
            </div>
            {activeExperience.awaitingResponse ? (
              <span>已发送，等 Agent 回应后继续下一步。</span>
            ) : experienceComplete ? (
              <span>之后可以直接自然地追问、取消或修改任务。</span>
            ) : (
              <span>
                {activeExperience.stepIndex === 0
                  ? '第一句话已填入，可按需修改后发送。'
                  : 'Agent 已回应，现在继续下一步。'}
              </span>
            )}
          </div>
          {!activeExperience.awaitingResponse && !experienceComplete && currentExperiencePrompt && (
            <button
              className="experience-prompt"
              disabled={inputDisabled}
              title="填入输入框"
              type="button"
              onClick={() => fillLiveInput(currentExperiencePrompt)}
            >
              <span>试着说</span>
              <strong>“{currentExperiencePrompt}”</strong>
              <em>{activeExperience.stepIndex === 0 ? '重新填入' : '填入'}</em>
            </button>
          )}
          {experienceComplete && (
            <button
              className="experience-more"
              type="button"
              onClick={() => {
                setActiveExperience(undefined)
                setIsCapabilityGuideOpen(true)
              }}
            >
              体验其它能力
            </button>
          )}
          <button
            aria-label="结束能力体验"
            className="experience-close"
            title="结束体验"
            type="button"
            onClick={() => setActiveExperience(undefined)}
          >
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="m6 6 8 8m0-8-8 8" />
            </svg>
          </button>
        </section>
      )}
      <form className="chat-composer" onSubmit={handleSubmit}>
        <input
          aria-label="live agent input"
          placeholder={
            connected === false
              ? '后端未连接，请启动服务...'
              : textInputEnabled
                ? '继续追问，或发起一个日常任务...'
                : '原生 Duplex 模式，请使用语音输入'
          }
          value={liveInput}
          disabled={inputDisabled}
          readOnly={inputDisabled}
          ref={liveInputRef}
          onChange={(event) => onLiveInputChange(event.target.value)}
        />
        <div className="composer-actions">
          <button
            aria-label={voiceLabel}
            aria-pressed={voiceMicrophoneOpen ? undefined : voiceActive}
            className={`icon-button voice-button${voiceActive ? ' active' : ''}${voicePhase === 'mic_pending' ? ' pending' : ''}`}
            disabled={connected === false || modeResetting}
            title={voiceLabel}
            type="button"
            onClick={onToggleVoice}
          >
            {voicePhase === 'mic_pending' ? (
              <span className="voice-spinner" aria-hidden="true" />
            ) : voiceActive ? (
              <span className="voice-wave" aria-hidden="true">
                <i /><i /><i /><i /><i />
              </span>
            ) : (
              <svg className="voice-icon" viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M12 14.5a3.25 3.25 0 0 0 3.25-3.25v-5a3.25 3.25 0 0 0-6.5 0v5A3.25 3.25 0 0 0 12 14.5Z"
                  fill="currentColor"
                />
                <path
                  d="M6 11a6 6 0 0 0 12 0M12 17.5V21M9 21h6"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </button>
          {voiceMicrophoneOpen && (
            <button
              aria-label="关闭语音输入"
              className="icon-button voice-close-button"
              disabled={connected === false || modeResetting}
              title="关闭语音输入"
              type="button"
              onClick={onToggleVoice}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M7 7l10 10M17 7 7 17"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeWidth="1.8"
                />
              </svg>
            </button>
          )}
          <button
            aria-label="发送"
            className="icon-button send-button"
            title="发送 (Enter)"
            type="submit"
            disabled={!canSubmitLive}
          >
            <svg className="send-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M20 6v4a4 4 0 0 1-4 4H5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d="M9 10l-4 4 4 4"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </div>
      </form>
      {voiceHint && (
        <p className="voice-hint">
          <span className={`voice-hint-pill voice-hint-${voicePhase}`}>
            <span className="voice-hint-dot" aria-hidden="true" />
            {voiceHint}
          </span>
        </p>
      )}
      {isPlaying && <p className="stream-hint">Agent 正在处理，仍可继续追问。</p>}
    </section>
  )
}
