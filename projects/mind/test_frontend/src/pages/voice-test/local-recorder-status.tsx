import { useEffect, useMemo, useRef, useState } from 'react'
import { Button } from 'antd'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { CaseFieldLabel } from './case-form-label'
import styles from './index.module.less'
import {
  DEFAULT_LOCAL_RECORDER_CONFIG,
  describeLocalRecorderHealth,
  fetchLocalRecorderHealth,
  LOCAL_RECORDER_DOWNLOAD_URL,
  type LocalRecorderConfig,
  saveLocalRecorderConfig,
} from './local-recorder-client'

type Props = {
  value: LocalRecorderConfig
  disabled?: boolean
  /** 运行配置抽屉打开时为 true：进入时自动检查一次 */
  active?: boolean
  onChange: (value: LocalRecorderConfig) => void
}

/** 开关关闭时不展示「连不上」之类，避免吓人 */
const OFF_STATUS = { connected: false, ready: false, text: '未开启，跑 case 不会本地记录画面与 log' }
const IDLE_STATUS = {
  connected: false,
  ready: false,
  text: '请先启动本地记录服务，再点「检查」',
}

const LocalRecorderStatusForm: React.FC<Props> = ({
  value,
  disabled,
  active = false,
  onChange,
}) => {
  const [formData, setFormData] = useState<LocalRecorderConfig>(() => ({
    ...DEFAULT_LOCAL_RECORDER_CONFIG,
    ...value,
  }))
  const [checking, setChecking] = useState(false)
  const [status, setStatus] = useState(() => (value.enabled ? IDLE_STATUS : OFF_STATUS))
  const isInternalChange = useRef(false)
  const lastAutoCheckKey = useRef('')

  const refresh = async (config: LocalRecorderConfig) => {
    if (!config.enabled) {
      setStatus(OFF_STATUS)
      return
    }
    if (!config.baseUrl.trim()) {
      setStatus({ connected: false, ready: false, text: '请填写服务地址' })
      return
    }
    setChecking(true)
    const health = await fetchLocalRecorderHealth(config.baseUrl)
    setStatus(describeLocalRecorderHealth(health))
    setChecking(false)
  }

  useEffect(() => {
    if (isInternalChange.current) {
      isInternalChange.current = false
      return
    }
    setFormData({ ...DEFAULT_LOCAL_RECORDER_CONFIG, ...value })
  }, [value])

  useEffect(() => {
    if (!value.enabled) {
      setStatus(OFF_STATUS)
      lastAutoCheckKey.current = ''
      return
    }
    setStatus((prev) => (prev.text === OFF_STATUS.text ? IDLE_STATUS : prev))
  }, [value.enabled])

  // 进入运行配置抽屉时自动检查一次；关闭后清空标记以便下次再进仍会刷新
  useEffect(() => {
    if (!active) {
      lastAutoCheckKey.current = ''
      return
    }
    if (!value.enabled || !value.baseUrl.trim()) {
      return
    }
    const key = `${value.baseUrl.trim()}|on`
    if (lastAutoCheckKey.current === key) {
      return
    }
    lastAutoCheckKey.current = key
    void refresh(value)
  }, [active, value.enabled, value.baseUrl])

  const formList: FormItem[] = useMemo(() => {
    const items: FormItem[] = [
      { label: '本地记录', name: 'section_local_record', type: 'title' },
      {
        label: (
          <CaseFieldLabel
            label="开启"
            tooltip="开启后，每个 case 会用本地记录工具记下连接设备的画面与运行 log；关闭则什么都不记。"
          />
        ),
        name: 'enabled',
        type: 'switch',
      },
    ]
    if (!value.enabled) {
      return items
    }
    items.push(
      {
        name: 'local_recorder_download',
        type: 'custom',
        children: (
          <div className={styles.localRecorderDownloadRow}>
            <a href={LOCAL_RECORDER_DOWNLOAD_URL} download="voice_local_recorder.zip">
              下载本地记录工具（zip）
            </a>
            <ol className={styles.localRecorderGuide}>
              <li>下载并解压本地记录工具</li>
              <li>按包内 README 配置，在解压目录执行 python local_recorder.py</li>
              <li>点右下角「检查」；显示设备已连接即可开始测试</li>
            </ol>
          </div>
        ),
      },
      {
        label: (
          <CaseFieldLabel
            label="临时文件存放目录"
            tooltip="记录文件会落到本机 recordings/ 下以该名字新建的文件夹里。不填则用当天日期，如 20260619。"
          />
        ),
        name: 'batchId',
        type: 'input',
        placeholder: '如：奔驰测试 不填则用当天日期，如 20260619',
      },
      {
        label: (
          <CaseFieldLabel
            label="服务地址"
            tooltip="一般不用改。先在跑测试的这台电脑上启动本地记录服务（默认端口 8765），再点下方「检查」。"
          />
        ),
        name: 'baseUrl',
        type: 'input',
        placeholder: DEFAULT_LOCAL_RECORDER_CONFIG.baseUrl,
      },
    )
    return items
  }, [value.enabled])

  const formProps: FormProps<LocalRecorderConfig> = {
    formList,
    formData,
    setFormData,
    labelWidth: 120,
    showAction: false,
    disabled,
    cols: 1,
    onValuesChange: (changed, all) => {
      const next = { ...formData, ...all }
      if (!next.enabled) {
        setStatus(OFF_STATUS)
        lastAutoCheckKey.current = ''
      } else if ('enabled' in changed && changed.enabled) {
        setStatus(IDLE_STATUS)
        lastAutoCheckKey.current = ''
      } else if ('baseUrl' in changed) {
        setStatus(IDLE_STATUS)
        lastAutoCheckKey.current = ''
      }
      isInternalChange.current = true
      onChange(next)
      saveLocalRecorderConfig(next)
      if ('enabled' in changed) {
        setFormData(next)
      }
    },
  }

  return (
    <div className={styles.deviceRecorderForm}>
      <ExForm<LocalRecorderConfig> {...formProps} />
      {value.enabled ? (
        <div className={styles.deviceRecorderHealth}>
          <span
            className={
              status.ready
                ? styles.deviceRecorderHealthOk
                : styles.deviceRecorderHealthWarn
            }
          >
            {status.text}
          </span>
          <Button
            size="small"
            loading={checking}
            disabled={disabled || !value.baseUrl.trim()}
            onClick={() => void refresh(value)}
          >
            检查
          </Button>
        </div>
      ) : null}
    </div>
  )
}

export default LocalRecorderStatusForm
