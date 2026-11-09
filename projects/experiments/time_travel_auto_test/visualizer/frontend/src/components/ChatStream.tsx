/**
 * ChatStream：对话流面板（中栏）。
 * 气泡 = 落盘话语（权威） + 打字机实时气泡（层2 delta）。
 * 工具卡片 = 助手工具调用（参数/返回/耗时），按事件序混排在话语之间。
 * 快进标记 = 时间快进区间（⏩ 紫色分隔条）——快进两侧的对话由此分隔。
 * 标记：插话打断半截话 / 超时截断 / 主动话语。
 */
import { useEffect, useRef } from 'react'
import {
  formatDuration,
  type AccelerationEntry,
  type ChatBubble,
  type DialogueEntry,
  type ScriptEventEntry,
} from '../app/projections'

export interface ChatStreamProps {
  entries: DialogueEntry[]
}

const STATUS_BADGE: Record<ChatBubble['status'], string> = {
  speaking: '正在说…',
  complete: '',
  interrupted: '半截话 · 被插话打断',
  truncated: '半截话 · 超时截断',
}

function formatToolDuration(durationMs: number): string {
  const seconds = durationMs / 1000
  return seconds >= 1 ? `${seconds.toFixed(1)}s` : `${Math.round(durationMs)}ms`
}

function AccelerationView({ entry }: { entry: AccelerationEntry }) {
  const duration = entry.durationMs !== null ? formatDuration(entry.durationMs) : ''
  return (
    <div
      className={`acceleration-entry${entry.ongoing ? ' acceleration-ongoing' : ''}`}
      aria-label="时间快进标记"
    >
      <span className="acceleration-icon" aria-hidden>⏩</span>
      <span className="acceleration-text">
        {entry.ongoing ? '时间快进中' : '时间快进'}
        {duration !== '' && ` ${duration}`}
        {entry.timeRangeText !== null && `（${entry.timeRangeText}）`}
      </span>
    </div>
  )
}

function ToolCardView({ card }: { card: Extract<DialogueEntry, { kind: 'tool' }> }) {
  return (
    <article className="tool-card" aria-label={`工具调用 ${card.toolName}`}>
      <header className="tool-header">
        <span className="tool-icon" aria-hidden>⚙</span>
        <span className="tool-name">{card.toolName}</span>
        {card.durationMs !== null && card.resultText !== null && (
          <span className="tool-duration">{formatToolDuration(card.durationMs)}</span>
        )}
        {card.timeRangeText !== null && (
          <span className="tool-time">{card.timeRangeText}</span>
        )}
      </header>
      {card.argsText !== '' && <p className="tool-args">参数：{card.argsText}</p>}
      {card.resultText !== null ? (
        <p className="tool-result">返回：{card.resultText}</p>
      ) : (
        <p className="tool-result tool-pending">执行中…</p>
      )}
    </article>
  )
}

function ScriptEventView({ entry }: { entry: ScriptEventEntry }) {
  const isCheck = entry.scriptKind === 'state_check'
  const passed = isCheck ? entry.passed === true : false
  const icon = isCheck ? (passed ? '✓' : '✗') : '🎬'
  const variantCls = isCheck
    ? passed
      ? 'script-event-check script-event-pass'
      : 'script-event-check script-event-fail'
    : 'script-event-car'
  return (
    <div className={`script-event ${variantCls}`} aria-label={entry.label}>
      <span className="script-event-icon" aria-hidden>{icon}</span>
      <div className="script-event-body">
        <span className="script-event-label">{entry.label}</span>
        {entry.detail !== '' && (
          <span className="script-event-detail">{entry.detail}</span>
        )}
      </div>
      {entry.timeRangeText !== null && (
        <span className="script-event-time">{entry.timeRangeText}</span>
      )}
    </div>
  )
}

function BubbleView({ bubble }: { bubble: ChatBubble }) {
  return (
    <article
      className={[
        'chat-bubble',
        `bubble-${bubble.speaker}`,
        bubble.isLive ? 'bubble-live' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <header className="bubble-header">
        <span className="bubble-speaker">{bubble.label}</span>
        {bubble.isProactive && (
          <span className="bubble-badge badge-proactive">主动</span>
        )}
        {STATUS_BADGE[bubble.status] !== '' && (
          <span
            className={`bubble-badge badge-${bubble.status}`}
          >
            {STATUS_BADGE[bubble.status]}
          </span>
        )}
        {bubble.timeRangeText !== null && (
          <span className="bubble-time">{bubble.timeRangeText}</span>
        )}
      </header>
      <p className="bubble-content">{bubble.content}</p>
    </article>
  )
}

export function ChatStream({ entries }: ChatStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // 新内容自动滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [entries])

  return (
    <section className="chat-stream" aria-label="对话流">
      <header className="panel-header">
        <h2>对话流</h2>
        <span className="panel-subtitle">话语 + 工具调用 + 实时打字机</span>
      </header>
      <div className="chat-scroll">
        {entries.length === 0 && (
          <p className="empty-hint">选择 case 并运行后，对话将实时出现在这里。</p>
        )}
        {entries.map((entry) => {
          if (entry.kind === 'tool') {
            return <ToolCardView key={entry.id} card={entry} />
          }
          if (entry.kind === 'acceleration') {
            return <AccelerationView key={entry.id} entry={entry} />
          }
          if (entry.kind === 'script') {
            return <ScriptEventView key={entry.id} entry={entry} />
          }
          return <BubbleView key={entry.id} bubble={entry} />
        })}
        <div ref={bottomRef} />
      </div>
    </section>
  )
}
