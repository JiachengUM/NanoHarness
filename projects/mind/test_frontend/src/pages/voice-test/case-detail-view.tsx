import styles from './index.module.less'
import { Button, Collapse, Tag, Tooltip } from 'antd'
import {
  LoadingOutlined,
  PlayCircleOutlined,
  RobotOutlined,
  SoundOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Fragment, useState } from 'react'
import {
  agentBubbleText,
  isNewSessionTurn,
  sessionOrdinalAtTurn,
  shouldShowAgentBubble,
  turnIndexInSession,
  type CaseBlock,
} from './run-state'
import { caseStatusColor, caseStatusLabel } from './case-labels'
import { isPlayableTtsText, type TtsPlayHandler, type TtsVoice } from './audio-helper'

type TtsPlayPhase = 'idle' | 'loading' | 'playing'

export type CaseWaitHint = {
  label: string
  remainingSec: number
}

type Props = {
  caseBlock: CaseBlock | null
  emptyHint?: string
  hideMeta?: boolean
  showManualStep?: boolean
  onManualPlay?: () => void
  onManualSkip?: () => void
  onTtsPlay?: TtsPlayHandler
  turnListClassName?: string
  turnListRef?: (node: HTMLDivElement | null) => void
  /** 对话区底部锚点：用于滚动跟随最新消息 */
  liveTailRef?: (node: HTMLDivElement | null) => void
  /** 冷启动间隔等待：红线前倒计时气泡 */
  waitHint?: CaseWaitHint | null
}

function TtsPlayBtn({
  text,
  voice,
  onPlay,
}: {
  text: string
  voice: TtsVoice
  onPlay: TtsPlayHandler
}) {
  const [phase, setPhase] = useState<TtsPlayPhase>('idle')

  if (!isPlayableTtsText(text)) {
    return null
  }

  const tooltip =
    phase === 'loading' ? '合成中…' : phase === 'playing' ? '播放中…' : '文本转语音'
  const icon =
    phase === 'loading' ? (
      <LoadingOutlined spin />
    ) : phase === 'playing' ? (
      <SoundOutlined />
    ) : (
      <PlayCircleOutlined />
    )
  const btnClass =
    phase === 'playing'
      ? `${styles.ttsPlayBtn} ${styles.ttsPlayBtnActive}`
      : phase === 'loading'
        ? `${styles.ttsPlayBtn} ${styles.ttsPlayBtnLoading}`
        : styles.ttsPlayBtn

  return (
    <Tooltip title={tooltip}>
      <Button
        type="text"
        size="small"
        className={btnClass}
        icon={icon}
        disabled={phase !== 'idle'}
        onClick={(event) => {
          event.stopPropagation()
          if (phase !== 'idle') {
            return
          }
          setPhase('loading')
          void onPlay(text, voice, {
            onAudioStart: () => setPhase('playing'),
          }).finally(() => {
            setPhase('idle')
          })
        }}
      />
    </Tooltip>
  )
}

const CaseDetailView: React.FC<Props> = ({
  caseBlock,
  emptyHint = '点击上方用例查看对话细节',
  hideMeta = false,
  showManualStep = false,
  onManualPlay,
  onManualSkip,
  onTtsPlay,
  turnListClassName,
  turnListRef,
  liveTailRef,
  waitHint = null,
}) => {
  if (!caseBlock) {
    return <div className={styles.caseDetailEmpty}>{emptyHint}</div>
  }

  return (
    <div className={styles.caseDetailContent}>
      {!hideMeta && (
        <div className={styles.caseDetailMeta}>
          <span className={styles.caseDetailIndex}>
            {caseBlock.total > 1 ? `#${caseBlock.index}/${caseBlock.total}` : '单用例'}
          </span>
          <span className={styles.caseDetailId}>{caseBlock.caseId}</span>
          <Tag color={caseStatusColor[caseBlock.status]}>{caseStatusLabel[caseBlock.status]}</Tag>
        </div>
      )}

      {showManualStep && caseBlock.status === 'waiting' && (
        <div className={styles.caseManualBar}>
          <span className={styles.caseManualHint}>等待手动播放本条</span>
          <div className={styles.caseManualActions}>
            <Button type="primary" size="small" icon={<PlayCircleOutlined />} onClick={onManualPlay}>
              播放本条
            </Button>
            <Button size="small" onClick={onManualSkip}>
              跳过
            </Button>
          </div>
        </div>
      )}

      <div ref={turnListRef} className={styles.caseDetailMain}>
        <div className={`${styles.turnList} ${turnListClassName || styles.turnListDetail}`}>
          {caseBlock.turns.length > 0 ? (
            caseBlock.turns.map((turn, turnIndex) => {
              const agentText = agentBubbleText(turn)
              return (
                <Fragment key={turn.id}>
                  {isNewSessionTurn(caseBlock.turns, turnIndex) && (
                    <div className={styles.sessionSplit} role="separator">
                      <span className={styles.sessionSplitLabel}>
                        第 {sessionOrdinalAtTurn(caseBlock.turns, turnIndex)} 次多轮对话
                      </span>
                    </div>
                  )}
                  <div className={styles.turnBlock}>
                    {caseBlock.turns.length > 1 && (
                      <div className={styles.turnDivider}>
                        Round {turnIndexInSession(caseBlock.turns, turnIndex)}
                      </div>
                    )}
                    <div className={styles.msgRow}>
                      <Tooltip title="假人">
                        <div className={`${styles.msgAvatar} ${styles.msgAvatarFake}`}>
                          <UserOutlined />
                        </div>
                      </Tooltip>
                      <div className={`${styles.msgBubble} ${styles.msgBubbleFake}`}>{turn.fakePerson}</div>
                      {onTtsPlay && <TtsPlayBtn text={turn.fakePerson} voice="male" onPlay={onTtsPlay} />}
                    </div>
                    {shouldShowAgentBubble(turn) && (
                      <div className={`${styles.msgRow} ${styles.msgRowRight}`}>
                        {onTtsPlay && <TtsPlayBtn text={agentText} voice="female" onPlay={onTtsPlay} />}
                        <div
                          className={`${styles.msgBubble} ${styles.msgBubbleAgent} ${turn.listening ? styles.msgBubbleListening : ''}`}
                        >
                          {agentText}
                        </div>
                        <Tooltip title="被测助手">
                          <div className={`${styles.msgAvatar} ${styles.msgAvatarAgent}`}>
                            <RobotOutlined />
                          </div>
                        </Tooltip>
                      </div>
                    )}
                  </div>
                </Fragment>
              )
            })
          ) : (
            <div className={styles.caseCardPlaceholder}>等待对话开始…</div>
          )}
          {waitHint && waitHint.remainingSec > 0 && (
            <div className={styles.waitCountdownBlock}>
              <div className={styles.sessionSplitLine} role="separator" aria-hidden />
              <div className={styles.waitCountdownBubble}>
                <span className={styles.waitCountdownLabel}>{waitHint.label}</span>
                <span className={styles.waitCountdownSec}>剩余 {waitHint.remainingSec} 秒</span>
              </div>
            </div>
          )}
          <div ref={liveTailRef} className={styles.liveTailAnchor} aria-hidden />
        </div>

        {caseBlock.error && <div className={styles.caseError}>{caseBlock.error}</div>}
      </div>

      {(caseBlock.verdict || caseBlock.fullHistory) && (
        <div className={styles.caseDetailFooter}>
          {caseBlock.verdict && (
            <div
              className={`${styles.verdictCard} ${
                caseBlock.verdict.status === 'passed'
                  ? styles.verdictPassed
                  : caseBlock.verdict.status === 'failed'
                    ? styles.verdictFailed
                    : caseBlock.verdict.status === 'judging'
                      ? styles.verdictJudging
                      : styles.verdictSkipped
              }`}
            >
              <div className={styles.verdictTitle}>
                {caseBlock.verdict.status === 'passed' && '评测通过'}
                {caseBlock.verdict.status === 'failed' && '评测未通过'}
                {caseBlock.verdict.status === 'judging' && '正在评测…'}
                {caseBlock.verdict.status === 'skipped' && '未启用评测'}
              </div>
              {caseBlock.verdict.reason && (
                <div className={styles.verdictReason}>{caseBlock.verdict.reason}</div>
              )}
            </div>
          )}

          {caseBlock.fullHistory && (
            <Collapse
              ghost
              size="small"
              className={styles.historyCollapse}
              items={[
                {
                  key: 'history',
                  label: '查看完整对话历史',
                  children: <pre className={styles.historyPre}>{caseBlock.fullHistory}</pre>,
                },
              ]}
            />
          )}
        </div>
      )}
    </div>
  )
}

export default CaseDetailView
