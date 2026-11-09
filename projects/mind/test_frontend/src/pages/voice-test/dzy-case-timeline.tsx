import styles from './dzy-index.module.less'
import { Tag, Tooltip } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import CaseDetailView, { type CaseWaitHint } from './case-detail-view'
import type { TtsPlayHandler } from './audio-helper'
import { caseStatusColor, caseStatusLabel } from './case-labels'
import { type CaseBlock, type CaseStatus, countCaseSessions } from './run-state'
import { useLiveConversationScroll } from './use-live-scroll'

const COLLAPSIBLE_STATUS: CaseStatus[] = ['done', 'failed', 'skipped', 'pending']

type Props = {
  cases: CaseBlock[]
  activeCaseIndex: number | null
  showManualStep: boolean
  onManualPlay: () => void
  onManualSkip: () => void
  onTtsPlay?: TtsPlayHandler
  onCaseClick?: (index: number) => void
  scrollToIndex?: number | null
  waitHint?: CaseWaitHint | null
}

/**
 * 从 caseBlock 提取一个人类可读的摘要（取代 case_id 外露）
 * 优先用第一轮用户消息的前 20 字，否则用 case_id
 */
function caseSummary(caseBlock: CaseBlock): string {
  const firstTurn = caseBlock.turns[0]
  if (firstTurn?.fakePerson?.trim()) {
    const text = firstTurn.fakePerson.trim()
    return text.length > 20 ? `${text.slice(0, 20)}…` : text
  }
  return caseBlock.caseId || `用例 ${caseBlock.index}`
}

function caseSummaryText(caseBlock: CaseBlock): string {
  const parts: string[] = []
  if (caseBlock.turns.length > 0) {
    const sessionCount = countCaseSessions(caseBlock)
    if (sessionCount > 1) {
      parts.push(`${sessionCount} 段会话 · 共 ${caseBlock.turns.length} 轮`)
    } else {
      parts.push(`${caseBlock.turns.length} 轮对话`)
    }
  }
  if (caseBlock.verdict?.status === 'passed') {
    parts.push('通过')
  } else if (caseBlock.verdict?.status === 'failed') {
    parts.push('未通过')
  } else if (caseBlock.verdict?.status === 'skipped') {
    parts.push('未评分')
  }
  if (caseBlock.error) {
    parts.push('执行异常')
  }
  if (parts.length === 0) {
    return caseStatusLabel[caseBlock.status]
  }
  return parts.join(' · ')
}

const DzyCaseTimeline: React.FC<Props> = ({
  cases,
  activeCaseIndex,
  showManualStep,
  onManualPlay,
  onManualSkip,
  onTtsPlay,
  onCaseClick,
  scrollToIndex,
  waitHint = null,
}) => {
  const multiCase = useMemo(
    () => cases.length > 1 || (cases[0]?.total ?? 0) > 1,
    [cases],
  )
  const [expandedCases, setExpandedCases] = useState<Record<number, boolean>>({})

  const { timelineRef, turnListRefs, liveTailRefs, cardRefs } = useLiveConversationScroll(
    cases,
    activeCaseIndex,
    scrollToIndex,
    multiCase,
  )

  const isCaseExpanded = useCallback(
    (caseBlock: CaseBlock, isActive: boolean) => {
      if (!multiCase) {
        return true
      }
      if (isActive || caseBlock.status === 'running' || caseBlock.status === 'waiting') {
        return true
      }
      if (expandedCases[caseBlock.index]) {
        return true
      }
      return !COLLAPSIBLE_STATUS.includes(caseBlock.status)
    },
    [multiCase, expandedCases],
  )

  const toggleCaseExpanded = useCallback((caseIndex: number) => {
    setExpandedCases((prev) => ({
      ...prev,
      [caseIndex]: !prev[caseIndex],
    }))
  }, [])

  useEffect(() => {
    if (!multiCase) {
      return
    }
    const running = cases.find((item) => item.status === 'running')
    const waiting = cases.find((item) => item.status === 'waiting')
    const focus = running || waiting
    if (!focus) {
      return
    }
    setExpandedCases((prev) => {
      if (prev[focus.index]) {
        return prev
      }
      return { ...prev, [focus.index]: true }
    })
  }, [cases, multiCase])

  if (cases.length === 0) {
    return null
  }

  return (
    <div className={styles.dzyChatStage}>
      <div
        className={`${styles.dzyTimeline} ${multiCase ? styles.dzyTimelineBatch : styles.dzyTimelineSingle}`}
        ref={timelineRef}
      >
        {cases.map((caseBlock) => {
          const isActive = activeCaseIndex === caseBlock.index
          const isWaiting = caseBlock.status === 'waiting'
          const expanded = isCaseExpanded(caseBlock, isActive)
          const collapsible =
            multiCase && COLLAPSIBLE_STATUS.includes(caseBlock.status) && !isActive && caseBlock.status !== 'running'
          const summary = caseSummary(caseBlock)

          return (
            <div
              key={caseBlock.key}
              ref={(node) => {
                cardRefs.current[caseBlock.index] = node
              }}
              className={[
                styles.dzyCaseCard,
                multiCase ? styles.dzyCaseCardBatch : styles.dzyCaseCardSingle,
                isActive ? styles.dzyCaseCardActive : '',
                isWaiting ? styles.dzyCaseCardWaiting : '',
                !expanded ? styles.dzyCaseCardCollapsed : '',
              ]
                .filter(Boolean)
                .join(' ')}
              onClick={() => onCaseClick?.(caseBlock.index)}
            >
              <div
                className={styles.dzyCaseCardHeader}
                onClick={(event) => {
                  if (!collapsible) {
                    return
                  }
                  event.stopPropagation()
                  toggleCaseExpanded(caseBlock.index)
                }}
              >
                <div className={styles.dzyCaseCardTitle}>
                  <span className={styles.dzyCaseCardIndex}>
                    {caseBlock.total > 1 ? `#${caseBlock.index}/${caseBlock.total}` : '单条测试'}
                  </span>
                  <Tooltip title={caseBlock.caseId}>
                    <span className={styles.dzyCaseCardSummary}>{summary}</span>
                  </Tooltip>
                </div>
                <Tag color={caseStatusColor[caseBlock.status]}>{caseStatusLabel[caseBlock.status]}</Tag>
              </div>

              {!expanded && (
                <div className={styles.dzyCaseCardSummaryRow}>
                  {caseSummaryText(caseBlock)}
                  {collapsible && <span className={styles.dzyCaseCardSummaryHint}> · 点击标题展开</span>}
                </div>
              )}

              {expanded && (
                <div className={multiCase ? styles.dzyCaseDetailHostBatch : styles.dzyCaseDetailHost}>
                  <CaseDetailView
                    caseBlock={caseBlock}
                    hideMeta
                    showManualStep={showManualStep && isWaiting}
                    onManualPlay={onManualPlay}
                    onManualSkip={onManualSkip}
                    onTtsPlay={onTtsPlay}
                    turnListClassName={multiCase ? styles.dzyTurnListBatch : styles.dzyTurnListSingle}
                    turnListRef={(node) => {
                      turnListRefs.current[caseBlock.index] = node
                    }}
                    liveTailRef={(node) => {
                      liveTailRefs.current[caseBlock.index] = node
                    }}
                    waitHint={isActive ? waitHint : null}
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default DzyCaseTimeline
