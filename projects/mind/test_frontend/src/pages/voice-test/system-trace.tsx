import styles from './index.module.less'
import { Collapse } from 'antd'
import type { VoiceLogItem } from './ws-log'

type Props = {
  items: VoiceLogItem[]
}

const SystemTrace: React.FC<Props> = ({ items }) => {
  if (items.length === 0) {
    return null
  }

  return (
    <Collapse
      ghost
      size="small"
      className={styles.systemTrace}
      items={[
        {
          key: 'trace',
          label: `系统日志（${items.length}）`,
          children: (
            <div className={styles.traceBox}>
              {items.map((item) => (
                <div key={item.id} className={styles[`log_${item.level}`]}>
                  {item.text}
                </div>
              ))}
            </div>
          ),
        },
      ]}
    />
  )
}

export default SystemTrace
