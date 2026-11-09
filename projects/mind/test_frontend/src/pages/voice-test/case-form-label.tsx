import { QuestionCircleOutlined } from '@ant-design/icons'
import { Modal, Tooltip, Typography } from 'antd'
import styles from './index.module.less'

type GuideContent = {
  title: string
  items: string[]
}

type FieldLabelProps = {
  label: string
  tooltip?: string
  guide?: GuideContent
  onOpenGuide?: (guide: GuideContent) => void
}

export const CaseFieldLabel: React.FC<FieldLabelProps> = ({ label, tooltip, guide, onOpenGuide }) => {
  return (
    <span className={styles.caseFieldLabelStack}>
      <span className={styles.caseFieldLabel}>
        <span>{label}</span>
        {tooltip && (
          <Tooltip title={tooltip}>
            <QuestionCircleOutlined className={styles.caseFieldHintIcon} />
          </Tooltip>
        )}
      </span>
      {guide && onOpenGuide && (
        <Typography.Link className={styles.caseFieldGuideLink} onClick={() => onOpenGuide(guide)}>
          {guide.title}
        </Typography.Link>
      )}
    </span>
  )
}

type WritingGuideModalProps = {
  guide: GuideContent | null
  onClose: () => void
}

export const WritingGuideModal: React.FC<WritingGuideModalProps> = ({ guide, onClose }) => {
  return (
    <Modal title={guide?.title} open={guide != null} footer={null} width={640} onCancel={onClose}>
      {guide && (
        <ul className={styles.writingGuideList}>
          {guide.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </Modal>
  )
}

export function buildCaseFieldLabel(
  label: string,
  tooltip: string | undefined,
  guide: GuideContent | undefined,
  onOpenGuide: (guide: GuideContent) => void,
): React.ReactNode {
  return <CaseFieldLabel label={label} tooltip={tooltip} guide={guide} onOpenGuide={onOpenGuide} />
}
