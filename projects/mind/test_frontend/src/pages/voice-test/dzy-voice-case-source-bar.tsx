import { Select, Spin } from 'antd'
import type { DefaultOptionType } from 'antd/es/select'
import styles from './dzy-index.module.less'
import type { VoiceCaseOption } from './case-catalog'

type CatalogLoadStatus = 'idle' | 'loading' | 'ready' | 'error'

type Props = {
  caseOptions: VoiceCaseOption[]
  selectedCaseKey: string
  datasetId?: string
  datasetOptions: DefaultOptionType[]
  selectedCaseId: string
  caseIdOptions: { label: string; value: string; title?: string }[]
  catalogLoadStatus: CatalogLoadStatus
  disabled?: boolean
  onPresetChange: (caseKey: string) => void
  onDatasetChange: (datasetId?: string) => void
  onCaseIdChange: (caseId: string) => void
}

/**
 * 源选择栏：文案改写版
 * - "标准示例" → "示例"，加一行说明
 * - "数据集" → "测试集"
 * - "数据集用例" → "测试用例"
 */
const DzyVoiceCaseSourceBar: React.FC<Props> = ({
  caseOptions,
  selectedCaseKey,
  datasetId,
  datasetOptions,
  selectedCaseId,
  caseIdOptions,
  catalogLoadStatus,
  disabled,
  onPresetChange,
  onDatasetChange,
  onCaseIdChange,
}) => {
  const caseIdLoading = !!datasetId && catalogLoadStatus === 'loading'
  const caseIdDisabled =
    disabled || !datasetId || catalogLoadStatus === 'loading' || catalogLoadStatus === 'error'

  const caseIdPlaceholder = !datasetId
    ? '可选：从测试集中选一条'
    : catalogLoadStatus === 'error'
      ? '加载失败'
      : catalogLoadStatus === 'loading'
        ? '加载中…'
        : caseIdOptions.length === 0
          ? '该测试集暂无用例'
          : '选择测试用例'

  return (
    <div className={styles.dzySourceBar}>
      <div className={styles.dzySourceField}>
        <span className={styles.dzyLabel}>示例</span>
        <span className={styles.dzySourceHint}>点击套用一份示范，可直接开始</span>
        {caseOptions.length === 0 ? (
          <span className={styles.dzyShowcaseEmpty}>示例未加载</span>
        ) : (
          <div className={styles.dzyShowcaseList}>
            {caseOptions.map((option) => {
              const active = selectedCaseKey === option.key
              return (
                <button
                  key={option.key}
                  type="button"
                  className={`${styles.dzyShowcaseChip} ${active ? styles.dzyShowcaseChipActive : ''}`}
                  disabled={disabled}
                  title={option.description}
                  onClick={() => onPresetChange(option.key)}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
        )}
      </div>

      <div className={styles.dzySourceRow}>
        <div className={styles.dzySourceField}>
          <span className={styles.dzyLabel}>测试集</span>
          <Select
            className={styles.dzySourceSelect}
            showSearch
            allowClear
            value={datasetId}
            options={datasetOptions}
            disabled={disabled}
            placeholder="可选：选择测试集"
            optionFilterProp="label"
            onChange={(value) => onDatasetChange(value)}
          />
        </div>
        <div className={styles.dzySourceField}>
          <span className={styles.dzyLabel}>测试用例</span>
          <Select
            className={styles.dzySourceSelect}
            showSearch
            allowClear
            value={selectedCaseId || undefined}
            options={caseIdOptions}
            disabled={caseIdDisabled}
            loading={caseIdLoading}
            placeholder={caseIdPlaceholder}
            optionFilterProp="label"
            notFoundContent={caseIdLoading ? <Spin size="small" /> : undefined}
            onChange={(value) => {
              if (value) {
                onCaseIdChange(value)
              }
            }}
            onClear={() => onCaseIdChange('')}
          />
        </div>
      </div>
    </div>
  )
}

export default DzyVoiceCaseSourceBar
