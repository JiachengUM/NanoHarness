import { Spin, Tag } from 'antd'
import styles from './index.module.less'
import { caseStatusColor, caseStatusLabel } from './case-labels'
import type { CaseStatus } from './run-state'

export type CaseNavItem = {
  index: number
  caseId: string
  status?: CaseStatus
  repeatIndex?: number
  repeatN?: number
}

type CatalogLoadStatus = 'idle' | 'loading' | 'ready' | 'error'

type Props = {
  items: CaseNavItem[]
  selectedIndex: number | null
  activeCaseIndex?: number | null
  loadStatus: CatalogLoadStatus
  disabled?: boolean
  emptyHint?: string
  onSelect: (index: number) => void
}

const CaseListPanel: React.FC<Props> = ({
  items,
  selectedIndex,
  activeCaseIndex = null,
  loadStatus,
  disabled,
  emptyHint = '暂无可用用例',
  onSelect,
}) => {
  if (loadStatus === 'loading') {
    return (
      <div className={styles.caseCatalogLoading}>
        <Spin size="small" />
        <span>加载数据集用例…</span>
      </div>
    )
  }

  if (loadStatus === 'error') {
    return <div className={styles.caseCatalogError}>数据集用例加载失败</div>
  }

  if (items.length === 0) {
    return <div className={styles.caseDetailEmpty}>{emptyHint}</div>
  }

  return (
    <div className={styles.caseList}>
      {items.map((item) => {
        const isSelected = selectedIndex === item.index
        const isRunning = activeCaseIndex === item.index
        return (
          <div
            key={`${item.caseId}-${item.index}`}
            role="button"
            tabIndex={disabled ? -1 : 0}
            className={[
              styles.caseListItem,
              isSelected ? styles.caseListItemSelected : '',
              isRunning ? styles.caseListItemRunning : '',
              item.status === 'waiting' ? styles.caseListItemWaiting : '',
            ]
              .filter(Boolean)
              .join(' ')}
            onClick={() => {
              if (!disabled) {
                onSelect(item.index)
              }
            }}
            onKeyDown={(event) => {
              if (disabled) {
                return
              }
              if (event.key === 'Enter' || event.key === ' ') {
                onSelect(item.index)
              }
            }}
          >
            <span className={styles.caseListIndex}>{item.index}</span>
            <span
              className={styles.caseListId}
              title={
                item.repeatIndex && item.repeatN
                  ? `${item.caseId}（第 ${item.repeatIndex}/${item.repeatN} 遍）`
                  : item.caseId
              }
            >
              {item.repeatIndex && item.repeatN
                ? `${item.caseId} #${item.repeatIndex}`
                : item.caseId}
            </span>
            {isRunning && item.status !== 'waiting' && (
              <span className={styles.caseListRunningDot} title="正在执行" />
            )}
            {item.status && (
              <Tag color={caseStatusColor[item.status]}>{caseStatusLabel[item.status]}</Tag>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default CaseListPanel
