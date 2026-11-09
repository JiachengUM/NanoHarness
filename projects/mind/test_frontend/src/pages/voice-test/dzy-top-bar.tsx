import styles from './dzy-index.module.less'
import { Button, Select, Tooltip } from 'antd'
import {
  FileSearchOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  StopOutlined,
} from '@ant-design/icons'
import type { SessionConnection } from './run-state'
import type { VoiceTestAgentOption } from './agent-catalog'

export type RunMode = 'single' | 'batch'

type Props = {
  // 测试对象
  agentOptions: VoiceTestAgentOption[]
  selectedAgentType: string
  onSelectAgent: (value: string) => void
  // 运行方式
  runMode: RunMode
  onSelectRunMode: (mode: RunMode) => void
  batchDisabled: boolean
  batchDisabledReason?: string
  // 状态
  connection: SessionConnection
  phase: 'idle' | 'speaking' | 'listening' | string
  isVoiceChannel: boolean
  // 高级设置
  onOpenConfig: () => void
  // 结果跳转
  lastTaskRunId?: string
  onOpenResult: () => void
  // 主操作
  running: boolean
  startDisabled: boolean
  onStart: () => void
  onStop: () => void
}

const STATUS_META: Record<SessionConnection, { color: string; label: string }> = {
  disconnected: { color: 'var(--v-text-muted)', label: '未连接' },
  connecting: { color: 'var(--v-warn-text)', label: '连接中' },
  connected: { color: 'var(--v-warn-text)', label: '已连接' },
  ready: { color: 'var(--v-success-text)', label: '已就绪' },
  error: { color: 'var(--v-error-text)', label: '异常' },
}

const PHASE_LABEL: Record<string, string> = {
  speaking: '播音',
  listening: '收音',
  idle: '',
}

const DzyTopBar: React.FC<Props> = ({
  agentOptions,
  selectedAgentType,
  onSelectAgent,
  runMode,
  onSelectRunMode,
  batchDisabled,
  batchDisabledReason,
  connection,
  phase,
  isVoiceChannel,
  onOpenConfig,
  lastTaskRunId,
  onOpenResult,
  running,
  startDisabled,
  onStart,
  onStop,
}) => {
  const status = STATUS_META[connection] || STATUS_META.disconnected
  const phaseLabel = isVoiceChannel ? PHASE_LABEL[phase] || '' : ''

  return (
    <div className={styles.dzyTopBar}>
      <div className={styles.dzyTopBarLeft}>
        <div className={styles.dzyField}>
          <span className={styles.dzyFieldLabel}>测试对象</span>
          <Select
            size="small"
            className={styles.dzyAgentSelect}
            value={selectedAgentType}
            disabled={running}
            options={agentOptions.map((item) => ({
              value: item.value,
              label: item.label,
              title: item.description,
            }))}
            onChange={(value) => onSelectAgent(value ?? 'voice')}
          />
        </div>
        <div className={styles.dzyDivider} aria-hidden />
        <div className={styles.dzyField}>
          <span className={styles.dzyFieldLabel}>运行方式</span>
          <div className={styles.dzySegmented}>
            <button
              type="button"
              className={`${styles.dzySegBtn} ${runMode === 'single' ? styles.dzySegBtnActive : ''}`}
              disabled={running}
              onClick={() => onSelectRunMode('single')}
            >
              单条测试
            </button>
            <Tooltip title={batchDisabled ? batchDisabledReason || '不支持批量' : '批量测试：按测试集执行，结果入库'}>
              <button
                type="button"
                className={`${styles.dzySegBtn} ${runMode === 'batch' ? styles.dzySegBtnActive : ''}`}
                disabled={running || batchDisabled}
                onClick={() => onSelectRunMode('batch')}
              >
                批量测试
              </button>
            </Tooltip>
          </div>
        </div>
      </div>

      <div className={styles.dzyTopBarRight}>
        <div className={styles.dzyStatus}>
          <span className={styles.dzyStatusDot} style={{ background: status.color }} />
          <span className={styles.dzyStatusText}>{status.label}</span>
          {phaseLabel && <span className={styles.dzyStatusPhase}>{phaseLabel}</span>}
        </div>
        <div className={styles.dzyDivider} aria-hidden />
        <Button
          size="small"
          icon={<SettingOutlined />}
          disabled={running}
          onClick={onOpenConfig}
        >
          高级设置
        </Button>
        {lastTaskRunId && (
          <Button
            size="small"
            type="default"
            icon={<FileSearchOutlined />}
            onClick={onOpenResult}
          >
            查看结果
          </Button>
        )}
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          loading={running}
          disabled={startDisabled}
          onClick={onStart}
        >
          开始测试
        </Button>
        {running && (
          <Button icon={<StopOutlined />} onClick={onStop}>
            结束
          </Button>
        )}
      </div>
    </div>
  )
}

export default DzyTopBar
