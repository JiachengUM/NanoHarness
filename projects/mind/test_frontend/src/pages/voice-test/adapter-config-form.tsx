import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { Button, Collapse, Form, InputNumber, Space, Switch } from 'antd'
import {
  FALLBACK_ADAPTER_CONFIG,
  formatGoodbyeMarkers,
  parseGoodbyeMarkers,
  S2S_SPEAKER_OPTIONS,
  type VoiceAdapterConfig,
} from './adapter-config'
import { CaseFieldLabel } from './case-form-label'
import styles from './index.module.less'

type AdapterConfigFormData = VoiceAdapterConfig & {
  goodbye_markers_text: string
}

type Props = {
  value: VoiceAdapterConfig
  disabled?: boolean
  onChange: (value: VoiceAdapterConfig) => void
}

const ADAPTER_FIELD_TOOLTIPS = {
  wake_up_word:
    '首轮假人 TTS 前自动拼在台词前面，与第一句连读播报，用于唤醒外部车机或音箱；留空则不播唤醒词。',
  s2s_speaker:
    '假人朗读用的音色。',
  vad_timeout_ms:
    '后端火山 S2S 静音判停（毫秒）：判定一句话说完的静音时长，直接决定每轮收尾延迟（体感 ≈ 此值 + ASR 计算）。需大于前端「post 静音判停」+ 上传时间，否则段未到达就判停丢回复；在此前提下越小越快。',
  external_reply_timeout_sec:
    '浏览器确认假人音频播完后，若 N 秒内没有任何 ASR（车机未开口），则超时；一旦识别到 ASR，只等 VAD 判停，不再受 N 秒限制。',
  memory_extraction_wait_sec:
    '同一用例内多次冷启动之间，等待被测 Agent 上一轮记忆提取落库的秒数；仅影响 case 内相邻会话。',
  run_gap_wait_sec:
    '批量自动播放模式下，两条用例开始之间的间隔；手动逐条模式下不生效。',
  split_wake_up_and_first_query:
    '开启后：首轮唤醒词和第一句分开两次发送，中间停顿一会儿；默认关闭，唤醒词和第一句拼在一起一次发出去。',
  split_wake_up_wait_ms:
    '唤醒词发完后，停顿多少毫秒再发第一句；仅在拆分发送开启时生效。',
  goodbye_markers_text:
    '假人台词包含该词时视为告别，结束当前多轮对话；需与假人提示词搭配使用。',
  goodbye_reply:
    '检测到告别语后不再等车机麦克风，写入对话记录中的占位助手回复，供后续评测参考。',
  vad_min_speech_ms:
    '前端 Silero VAD：最短语音段（毫秒）。低于此长度的语音视为噪声丢弃。小=更敏感，能抓住车机快速短回复（如“搞定了”）；过大则会漏掉短句。',
  vad_pre_speech_pad_ms:
    '前端 Silero VAD pre pending：检测到语音开始前，向前补多少毫秒音频。大=开头不易吞字。',
  vad_redemption_ms:
    '前端 Silero VAD post pending/静音判停：语音结束后等多久静音才切句发送。大=切句更稳，防车机回复中途停顿被截断；但注意硬约束：后端「VAD 静音判停」必须大于此值+弱网上传时间（否则段未到达火山就已判停、整段丢失），所以此值越大后端判停只能越大、每轮越慢。',
  vad_positive_threshold:
    '前端 Silero VAD：语音开始判定阈值（0~1）。高=更难触发，滤环境噪声/残余回声；低=更灵敏。',
  vad_negative_threshold:
    '前端 Silero VAD：语音结束判定阈值（0~1）。低=更难判定结束，语音段更完整。',
} as const

function adapterFieldLabel(label: string, tooltip: string) {
  return <CaseFieldLabel label={label} tooltip={tooltip} />
}

function toFormData(config: VoiceAdapterConfig): AdapterConfigFormData {
  return {
    ...config,
    goodbye_markers_text: formatGoodbyeMarkers(config.goodbye_markers),
  }
}

function fromFormData(data: AdapterConfigFormData): VoiceAdapterConfig {
  const { goodbye_markers_text, ...rest } = data
  return {
    ...rest,
    goodbye_markers: parseGoodbyeMarkers(goodbye_markers_text || ''),
  }
}

const AdapterConfigForm: React.FC<Props> = ({ value, disabled, onChange }) => {
  const [formData, setFormData] = useState<AdapterConfigFormData>(toFormData(value))
  // 专门跟踪拆分开关，切换时即时重渲染 formList（避免 setFormData 触发输入框失焦）
  const [showSplitWait, setShowSplitWait] = useState(value.split_wake_up_and_first_query)
  const isInternalChange = useRef(false)

  const formList: FormItem[] = useMemo(
    () => [
      { label: '播报与唤醒', name: 'section_speak', type: 'title' },
      {
        label: adapterFieldLabel('唤醒词', ADAPTER_FIELD_TOOLTIPS.wake_up_word),
        name: 'wake_up_word',
        type: 'input',
        placeholder: '如：你好奔驰。',
      },
      {
        label: adapterFieldLabel('音色', ADAPTER_FIELD_TOOLTIPS.s2s_speaker),
        name: 's2s_speaker',
        type: 'select',
        options: [...S2S_SPEAKER_OPTIONS],
        props: { style: { width: '100%' } },
      },
      { label: '超时', name: 'section_timeout', type: 'title' },
      {
        label: adapterFieldLabel('VAD 静音判停 (ms)', ADAPTER_FIELD_TOOLTIPS.vad_timeout_ms),
        name: 'vad_timeout_ms',
        type: 'number',
        placeholder: '500～50000',
        props: { min: 500, max: 50000, precision: 0, style: { width: '100%' } },
      },
      {
        label: adapterFieldLabel('等外部回复 (s)', ADAPTER_FIELD_TOOLTIPS.external_reply_timeout_sec),
        name: 'external_reply_timeout_sec',
        type: 'number',
        placeholder: '1～120',
        props: { min: 1, precision: 1, style: { width: '100%' } },
      },
      { label: '前端 VAD（浏览器端）', name: 'section_frontend_vad', type: 'title' },
      {
        label: adapterFieldLabel('启用前端 VAD', '开启：Silero VAD 段式发送（整段说完再发）。关闭：流式发送，更接近真实环境连续音频。'),
        name: 'frontend_vad_enabled',
        type: 'switch',
      },
      ...(value.frontend_vad_enabled ? [
        {
          label: adapterFieldLabel('最短语音段 (ms)', ADAPTER_FIELD_TOOLTIPS.vad_min_speech_ms),
          name: 'vad_min_speech_ms',
          type: 'number',
          placeholder: '100～2000',
          props: { min: 100, max: 2000, precision: 0, style: { width: '100%' } },
        },
        {
          label: adapterFieldLabel('pre 前导垫 (ms)', ADAPTER_FIELD_TOOLTIPS.vad_pre_speech_pad_ms),
          name: 'vad_pre_speech_pad_ms',
          type: 'number',
          placeholder: '0～3000',
          props: { min: 0, max: 3000, precision: 0, style: { width: '100%' } },
        },
        {
          label: adapterFieldLabel('post 静音判停 (ms)', ADAPTER_FIELD_TOOLTIPS.vad_redemption_ms),
          name: 'vad_redemption_ms',
          type: 'number',
          placeholder: '300～5000',
          props: { min: 300, max: 5000, precision: 0, style: { width: '100%' } },
        },
        {
          label: adapterFieldLabel('开始判定阈值 (0-1)', ADAPTER_FIELD_TOOLTIPS.vad_positive_threshold),
          name: 'vad_positive_threshold',
          type: 'number',
          placeholder: '默认 0.5',
          props: { min: 0, max: 1, step: 0.05, precision: 2, style: { width: '100%' } },
        },
        {
          label: adapterFieldLabel('结束判定阈值 (0-1)', ADAPTER_FIELD_TOOLTIPS.vad_negative_threshold),
          name: 'vad_negative_threshold',
          type: 'number',
          placeholder: '默认 0.15',
          props: { min: 0, max: 1, step: 0.05, precision: 2, style: { width: '100%' } },
        },
      ] : []),
      { label: '记忆与跑批', name: 'section_memory', type: 'title' },
      {
        label: adapterFieldLabel('记忆提取等待 (s)', ADAPTER_FIELD_TOOLTIPS.memory_extraction_wait_sec),
        name: 'memory_extraction_wait_sec',
        type: 'number',
        placeholder: '0～300',
        props: { min: 0, max: 300, precision: 0, style: { width: '100%' } },
      },
      {
        label: adapterFieldLabel('跑批间隔 (s)', ADAPTER_FIELD_TOOLTIPS.run_gap_wait_sec),
        name: 'run_gap_wait_sec',
        type: 'number',
        placeholder: '0～300',
        props: { min: 0, max: 300, precision: 0, style: { width: '100%' } },
      },
      { label: '告别语', name: 'section_goodbye', type: 'title' },
      {
        label: adapterFieldLabel('告别语', ADAPTER_FIELD_TOOLTIPS.goodbye_markers_text),
        name: 'goodbye_markers_text',
        type: 'input',
        disabled: true,
        placeholder: '退下',
      },
      {
        label: adapterFieldLabel('默认回复', ADAPTER_FIELD_TOOLTIPS.goodbye_reply),
        name: 'goodbye_reply',
        type: 'input',
        placeholder: '跳过麦克风时的占位回复',
      },
      {
        label: '定制化功能',
        name: 'section_advanced',
        type: 'custom',
        children: (
          <Collapse
            size="small"
            ghost
            style={{ marginTop: 8 }}
            items={[
              {
                key: 'split',
                label: '定制化功能',
                children: (
                  <Form.Item
                    label={adapterFieldLabel('拆分首句发送', ADAPTER_FIELD_TOOLTIPS.split_wake_up_and_first_query)}
                    style={{ marginBottom: 0 }}
                  >
                    <Space size="large">
                      <Form.Item
                        name="split_wake_up_and_first_query"
                        valuePropName="checked"
                        noStyle
                      >
                        <Switch disabled={disabled} />
                      </Form.Item>
                      {showSplitWait && (
                        <>
                          <span>拆分等待 (ms)</span>
                          <Form.Item
                            name="split_wake_up_wait_ms"
                            noStyle
                          >
                            <InputNumber
                              min={0}
                              max={5000}
                              precision={0}
                              style={{ width: 120 }}
                              placeholder="0～5000"
                              disabled={disabled}
                            />
                          </Form.Item>
                        </>
                      )}
                    </Space>
                  </Form.Item>
                ),
              },
            ]}
          />
        ),
      },
    ],
    [showSplitWait, value.frontend_vad_enabled, disabled],
  )

  useEffect(() => {
    if (isInternalChange.current) {
      isInternalChange.current = false
      return
    }
    setFormData(toFormData(value))
    setShowSplitWait(value.split_wake_up_and_first_query)
  }, [value])

  const reset = () => {
    const next = toFormData(FALLBACK_ADAPTER_CONFIG)
    setFormData(next)
    setShowSplitWait(FALLBACK_ADAPTER_CONFIG.split_wake_up_and_first_query)
    onChange(fromFormData(next))
  }

  const formProps: FormProps<AdapterConfigFormData> = {
    formList,
    formData,
    setFormData,
    labelWidth: 120,
    showAction: false,
    disabled,
    cols: 1,
    onValuesChange: (_changed, all) => {
      // 勿 setFormData：会触发 ExForm resetFields，导致输入框失焦
      isInternalChange.current = true
      // 拆分开关变化时即时更新 showSplitWait，触发 formList 重算
      if (all.split_wake_up_and_first_query !== showSplitWait) {
        setShowSplitWait(all.split_wake_up_and_first_query)
      }
      // 前端 VAD 开关变化时强制 setFormData，触发 value prop 更新 → formList 重算
      if ('frontend_vad_enabled' in _changed) {
        setFormData({ ...formData, ...all })
      }
      onChange(fromFormData({ ...formData, ...all }))
    },
  }

  return (
    <div className={styles.adapterConfigForm}>
      <Button type="primary" className={styles.adapterConfigReset} disabled={disabled} onClick={reset}>
        重置
      </Button>
      <ExForm<AdapterConfigFormData> {...formProps} />
    </div>
  )
}

export default AdapterConfigForm
