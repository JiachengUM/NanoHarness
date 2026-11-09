import styles from './index.module.less'
import { Tag } from 'antd'
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
  onStart?: () => void
  startDisabled?: boolean
  /** 当前活跃 case 的等待提示（记忆提取等） */
  waitHint?: CaseWaitHint | null
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
    parts.push('评测通过')
  } else if (caseBlock.verdict?.status === 'failed') {
    parts.push('评测未通过')
  } else if (caseBlock.verdict?.status === 'skipped') {
    parts.push('未评测')
  }
  if (caseBlock.error) {
    parts.push('执行异常')
  }
  if (parts.length === 0) {
    return caseStatusLabel[caseBlock.status]
  }
  return parts.join(' · ')
}

const CaseTimeline: React.FC<Props> = ({
  cases,
  activeCaseIndex,
  showManualStep,
  onManualPlay,
  onManualSkip,
  onTtsPlay,
  onCaseClick,
  scrollToIndex,
  onStart,
  startDisabled = false,
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
    const canStart = Boolean(onStart) && !startDisabled
    return (
      <div className={styles.chatStage}>
        <div
          className={[styles.timelineEmpty, canStart ? styles.timelineEmptyClickable : ''].filter(Boolean).join(' ')}
          role={canStart ? 'button' : undefined}
          tabIndex={canStart ? 0 : undefined}
          onClick={canStart ? onStart : undefined}
          onKeyDown={
            canStart
              ? (event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onStart?.()
                  }
                }
              : undefined
          }
        >
          点击
          <span className={styles.timelineEmptyHighlight}>此处</span>
          或右上角
          <span className={styles.timelineEmptyHighlight}>「开始」</span>
          开始测试
        </div>
      </div>
    )
  }

  return (
    <div className={styles.chatStage}>
      <div
        className={`${styles.timeline} ${multiCase ? styles.timelineBatch : styles.timelineSingle}`}
        ref={timelineRef}
      >
        {cases.map((caseBlock) => {
          const isActive = activeCaseIndex === caseBlock.index
          const isWaiting = caseBlock.status === 'waiting'
          const expanded = isCaseExpanded(caseBlock, isActive)
          const collapsible =
            multiCase && COLLAPSIBLE_STATUS.includes(caseBlock.status) && !isActive && caseBlock.status !== 'running'

          return (
            <div
              key={caseBlock.key}
              ref={(node) => {
                cardRefs.current[caseBlock.index] = node
              }}
              className={[
                styles.caseCard,
                multiCase ? styles.caseCardBatch : styles.caseCardSingle,
                isActive ? styles.caseCardActive : '',
                isWaiting ? styles.caseCardWaiting : '',
                !expanded ? styles.caseCardCollapsed : '',
              ]
                .filter(Boolean)
                .join(' ')}
              onClick={() => onCaseClick?.(caseBlock.index)}
            >
              <div
                className={styles.caseCardHeader}
                onClick={(event) => {
                  if (!collapsible) {
                    return
                  }
                  event.stopPropagation()
                  toggleCaseExpanded(caseBlock.index)
                }}
              >
                <div className={styles.caseCardTitle}>
                  <span className={styles.caseCardIndex}>
                    {caseBlock.total > 1 ? `${caseBlock.index}/${caseBlock.total}` : '单用例'}
                  </span>
                  <span className={styles.caseCardId}>{caseBlock.caseId}</span>
                </div>
                <Tag color={caseStatusColor[caseBlock.status]}>{caseStatusLabel[caseBlock.status]}</Tag>
              </div>

              {!expanded && (
                <div className={styles.caseCardSummary}>
                  {caseSummaryText(caseBlock)}
                  {collapsible && <span className={styles.caseCardSummaryHint}> · 点击标题展开</span>}
                </div>
              )}

              {expanded && (
                <div className={multiCase ? styles.caseDetailHostBatch : styles.caseDetailHost}>
                  <CaseDetailView
                    caseBlock={caseBlock}
                    hideMeta
                    showManualStep={showManualStep && isWaiting}
                    onManualPlay={onManualPlay}
                    onManualSkip={onManualSkip}
                    onTtsPlay={onTtsPlay}
                    turnListClassName={multiCase ? styles.turnListBatch : styles.turnListSingle}
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

export default CaseTimeline
