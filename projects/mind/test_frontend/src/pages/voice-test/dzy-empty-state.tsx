import styles from './dzy-index.module.less'

type Props = {
  onStart?: () => void
  canStart?: boolean
}

/**
 * 右侧空态：大字提示 + 整块可点。
 * 文案明确告诉零基础用户"左侧已备好，直接开始"。
 */
const DzyEmptyState: React.FC<Props> = ({ onStart, canStart = false }) => {
  return (
    <div className={styles.dzyChatStage}>
      <div
        className={[
          styles.dzyEmpty,
          canStart ? styles.dzyEmptyClickable : '',
        ]
          .filter(Boolean)
          .join(' ')}
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
        <div className={styles.dzyEmptyTitle}>点「开始测试」体验一次语音测试</div>
        <div className={styles.dzyEmptyHint}>左侧已备好示范用例，直接点右上角即可</div>
      </div>
    </div>
  )
}

export default DzyEmptyState
