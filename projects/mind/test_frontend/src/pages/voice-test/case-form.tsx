import { useCallback, useEffect, useMemo, useState } from 'react'
import styles from './index.module.less'
import { Select } from 'antd'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { LLM_ROLES } from '@/constants'
import { deleteNullKeys } from '@/utils'
import type { VoiceCaseOption } from './case-catalog'
import { buildCaseFieldLabel, WritingGuideModal } from './case-form-label'
import {
  CASE_FIELD_TOOLTIPS,
  NL_ASSERTION_WRITING_GUIDE,
  SCRIPT_WRITING_GUIDE,
} from './case-writing-guides'
const defaultForm: ComplexReasoningCase = {}
type UserQueryListMode = 'messages' | 'roundConfig'

type VoiceCaseFormData = ComplexReasoningCase & {
  user_query_lists_mode?: UserQueryListMode
  user_query_lists_messages?: Message[][]
  user_query_lists_rounds?: DialogueRoundConfig[]
}

const detectMode = (formData?: ComplexReasoningCase): UserQueryListMode => {
  const firstItem = formData?.user_query_lists?.[0]
  return firstItem && !Array.isArray(firstItem) ? 'roundConfig' : 'messages'
}

export const toVoiceCaseFormData = (formData?: ComplexReasoningCase): VoiceCaseFormData => {
  const mode = detectMode(formData)
  const userQueryLists = formData?.user_query_lists || []

  return {
    ...(formData || defaultForm),
    user_query_lists_mode: mode,
    user_query_lists_messages: userQueryLists.filter((item): item is Message[] => Array.isArray(item)),
    user_query_lists_rounds: userQueryLists.filter(
      (item): item is DialogueRoundConfig => !!item && !Array.isArray(item),
    ),
  }
}

export const normalizeVoiceCaseForm = (payload: VoiceCaseFormData): ComplexReasoningCase => {
  const { user_query_lists_mode, user_query_lists_messages, user_query_lists_rounds, ...rest } = payload

  return deleteNullKeys({
    ...rest,
    id: rest.id || rest.case_id || 'voice-test-ephemeral',
    user_query_lists:
      user_query_lists_mode === 'roundConfig' ? user_query_lists_rounds || [] : user_query_lists_messages || [],
  }) as ComplexReasoningCase
}

type Props = {
  value: ComplexReasoningCase
  caseOptions: VoiceCaseOption[]
  selectedCaseKey: string
  disabled?: boolean
  /** 批量预览：只读展示，覆盖 disabled 灰度为正常色 */
  preview?: boolean
  hidePreset?: boolean
  onChange: (next: ComplexReasoningCase) => void
  onCaseTemplateChange: (caseKey: string) => void
}

const VoiceCaseForm: React.FC<Props> = ({
  value,
  caseOptions,
  selectedCaseKey,
  disabled,
  preview,
  hidePreset,
  onChange,
  onCaseTemplateChange,
}) => {
  const [formData, setFormData] = useState<VoiceCaseFormData>(() => toVoiceCaseFormData(value))
  const [userQueryListMode, setUserQueryListMode] = useState<UserQueryListMode>(() => detectMode(value))
  const [writingGuide, setWritingGuide] = useState<{ title: string; items: string[] } | null>(null)

  const openWritingGuide = useCallback((guide: { title: string; items: string[] }) => {
    setWritingGuide(guide)
  }, [])

  const coldStartLabel = useMemo(
    () => buildCaseFieldLabel('假人冷启动台词', CASE_FIELD_TOOLTIPS.coldStart, undefined, openWritingGuide),
    [openWritingGuide],
  )

  const formList: FormItem[] = useMemo(
    () => [
      // 语音测试页暂不展示，数据仍随 DB case 保留（case_id 来自所选用例）
      // { label: 'CASE_ID', name: 'case_id', type: 'input', required: true },
      // {
      //   label: '对话记录类型',
      //   name: 'user_query_lists_mode',
      //   type: 'radio',
      //   options: [
      //     { label: '消息数组 Message[][]', value: 'messages' },
      //     { label: '轮次配置 DialogueRoundConfig[]', value: 'roundConfig' },
      //   ],
      //   required: true,
      // },
      {
        label: coldStartLabel,
        name: 'user_query_lists_messages',
        type: 'arrayArrayItem',
        props: { maxCount: 1 },
        itemList: [
          {
            label: '对话角色',
            name: 'role',
            type: 'autoComplete',
            options: LLM_ROLES.map((it) => ({ label: it, value: it })),
          },
          { label: '消息内容', name: 'content', type: 'input' },
        ],
        hidden: userQueryListMode !== 'messages',
        required: userQueryListMode === 'messages',
      },
      {
        label: coldStartLabel,
        name: 'user_query_lists_rounds',
        type: 'arrayItem',
        itemList: [
          {
            label: '消息列表',
            name: 'user_query_list',
            type: 'arrayItem',
            props: { maxCount: 1 },
            itemList: [
              {
                label: '对话角色',
                name: 'role',
                type: 'autoComplete',
                options: LLM_ROLES.map((it) => ({ label: it, value: it })),
              },
              { label: '消息内容', name: 'content', type: 'input' },
            ],
          },
          { label: 'Mock时间', name: 'mock_time', type: 'datetime', placeholder: 'YYYY-MM-DD HH:mm:ss' },
          { label: 'Mock信息', name: 'mock_info', type: 'json' },
        ],
        hidden: userQueryListMode !== 'roundConfig',
        required: userQueryListMode === 'roundConfig',
      },
      {
        label: buildCaseFieldLabel('最大对话轮数', CASE_FIELD_TOOLTIPS.maxRound, undefined, openWritingGuide),
        name: 'max_round',
        type: 'number',
      },
      {
        label: buildCaseFieldLabel('上下文配置', CASE_FIELD_TOOLTIPS.contextConfig, undefined, openWritingGuide),
        name: 'context_config',
        type: 'json',
      },
      {
        label: buildCaseFieldLabel(
          '剧本',
          CASE_FIELD_TOOLTIPS.expectedScript,
          SCRIPT_WRITING_GUIDE,
          openWritingGuide,
        ),
        name: 'expected_script',
        type: 'textarea',
      },
      {
        label: buildCaseFieldLabel(
          '自然语言断言',
          CASE_FIELD_TOOLTIPS.nlAssertion,
          NL_ASSERTION_WRITING_GUIDE,
          openWritingGuide,
        ),
        name: 'nl_assertion',
        type: 'arrayInput',
      },
      // 语音测试页暂不展示，数据仍随 DB case 保留
      // { label: '代码断言', name: 'code_assertion', type: 'json' },
      // { label: '测试用例描述', name: 'case_description', type: 'textarea' },
      // { label: '测试用例标签', name: 'tags', type: 'arrayInput' },
    ],
    [coldStartLabel, openWritingGuide, userQueryListMode],
  )

  const templateSelectOptions = useMemo(
    () =>
      caseOptions.map((option) => ({
        label: option.label,
        value: option.key,
        title: option.description,
      })),
    [caseOptions],
  )

  useEffect(() => {
    const nextFormData = toVoiceCaseFormData(value)
    setFormData(nextFormData)
    setUserQueryListMode(nextFormData.user_query_lists_mode || 'messages')
  }, [value])

  const formProps: FormProps<VoiceCaseFormData> = {
    formList,
    formData,
    setFormData,
    disabled,
    showAction: false,
    labelWidth: 120,
    onValuesChange: (changedValues, allValues) => {
      if (changedValues.user_query_lists_mode) {
        setUserQueryListMode(changedValues.user_query_lists_mode)
      }
      onChange(
        normalizeVoiceCaseForm({
          ...formData,
          ...allValues,
          case_id: formData.case_id || value.case_id,
        }),
      )
    },
  }

  return (
    <div
      className={[styles.voiceCaseForm, preview ? styles.voiceCaseFormPreview : '']
        .filter(Boolean)
        .join(' ')}
    >
      {!hidePreset && (
        <div className={styles.casePresetField}>
          <span className={styles.label}>标准示例</span>
          <Select
            className={styles.casePresetSelect}
            value={selectedCaseKey || undefined}
            options={templateSelectOptions}
            disabled={disabled || caseOptions.length === 0}
            placeholder={caseOptions.length === 0 ? '数据集暂无用例' : '请选择用例'}
            optionFilterProp="label"
            onChange={onCaseTemplateChange}
          />
          <span className={styles.hint}>
            {caseOptions.length === 0
              ? '代表性用例加载失败，请检查 case-showcase-config 与数据集'
              : '选择用例后可在下方直接修改内容'}
          </span>
        </div>
      )}
      <ExForm<VoiceCaseFormData> {...formProps} />
      <WritingGuideModal guide={writingGuide} onClose={() => setWritingGuide(null)} />
    </div>
  )
}
export default VoiceCaseForm
