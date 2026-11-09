import { Select, Spin } from 'antd'
import type { DefaultOptionType } from 'antd/es/select'
import styles from './index.module.less'
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

const VoiceCaseSourceBar: React.FC<Props> = ({
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
    ? '请先选择数据集'
    : catalogLoadStatus === 'error'
      ? '加载失败'
      : catalogLoadStatus === 'loading'
        ? '加载中…'
        : caseIdOptions.length === 0
          ? '该数据集暂无用例'
          : '选择 Case'

  return (
    <div className={styles.caseSourceBar}>
      <div className={styles.caseSourceField}>
        <span className={styles.label}>标准示例</span>
        {caseOptions.length === 0 ? (
          <span className={styles.showcaseEmpty}>示例未加载</span>
        ) : (
          <div className={styles.showcaseList}>
            {caseOptions.map((option) => {
              const active = selectedCaseKey === option.key
              return (
                <button
                  key={option.key}
                  type="button"
                  className={`${styles.showcaseChip} ${active ? styles.showcaseChipActive : ''}`}
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

      <div className={styles.caseSourceRow}>
        <div className={styles.caseSourceField}>
          <span className={styles.label}>数据集</span>
          <Select
            className={styles.caseSourceSelect}
            showSearch
            allowClear
            value={datasetId}
            options={datasetOptions}
            disabled={disabled}
            placeholder="可选：选择数据集"
            optionFilterProp="label"
            onChange={(value) => onDatasetChange(value)}
          />
        </div>
        <div className={styles.caseSourceField}>
          <span className={styles.label}>数据集用例</span>
          <Select
            className={styles.caseSourceSelect}
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

export default VoiceCaseSourceBar
