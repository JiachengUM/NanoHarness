import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Collapse, Select } from 'antd'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { LLM_ROLES } from '@/constants'
import { deleteNullKeys } from '@/utils'
import type { VoiceCaseOption } from './case-catalog'
import { CaseFieldLabel, WritingGuideModal } from './case-form-label'
import {
  CASE_FIELD_TOOLTIPS,
  NL_ASSERTION_WRITING_GUIDE,
  SCRIPT_WRITING_GUIDE,
} from './case-writing-guides'
import styles from './dzy-index.module.less'

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
  /** 批量预览：只读展示 */
  preview?: boolean
  hidePreset?: boolean
  onChange: (next: ComplexReasoningCase) => void
  onCaseTemplateChange: (caseKey: string) => void
}

/**
 * 折叠版表单：
 * - 必填平铺：示例 + 用户开场白 + 剧本 + 检查点
 * - 折叠：最大对话轮数 + 上下文配置
 * - 文案改写：假人冷启动台词 → 用户开场白，自然语言断言 → 检查点
 * - 剧本加 placeholder 示例
 */
const DzyCaseForm: React.FC<Props> = ({
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
  const [advancedOpen, setAdvancedOpen] = useState<string[]>([])

  const openWritingGuide = useCallback((guide: { title: string; items: string[] }) => {
    setWritingGuide(guide)
  }, [])

  // 文案改写后的字段标签
  const coldStartLabel = useMemo(
    () => buildDzyFieldLabel('用户开场白', '用户第一句话，会直接念出来。点击右侧 ? 看写作建议。', SCRIPT_WRITING_GUIDE, openWritingGuide),
    [openWritingGuide],
  )
  const scriptLabel = useMemo(
    () => buildDzyFieldLabel('剧本', '按"用户：xxx 管家：（期望回复）"的格式写完整对话。括号内是期望，不是真实回复。', SCRIPT_WRITING_GUIDE, openWritingGuide),
    [openWritingGuide],
  )
  const checkpointLabel = useMemo(
    () => buildDzyFieldLabel('检查点', '一条一句，描述管家该做什么、做对没。用于自动评分。', NL_ASSERTION_WRITING_GUIDE, openWritingGuide),
    [openWritingGuide],
  )
  const maxRoundLabel = useMemo(
    () => buildDzyFieldLabel('最大对话轮数', '一次多轮对话最多进行几轮。不知道填几就保持空，用默认值。', undefined, openWritingGuide),
    [openWritingGuide],
  )
  const contextLabel = useMemo(
    () => buildDzyFieldLabel('上下文配置', '车辆状态、记忆等额外信息。普通用户无需填写。', undefined, openWritingGuide),
    [openWritingGuide],
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

  // 把必填字段和折叠字段分开渲染
  // formList 顺序：[开场白, 剧本, 检查点, 最大轮数, 上下文]
  // ExForm 不支持分段，这里用两个 ExForm 渲染同一份 formData 会有状态同步问题。
  // 改为：单 ExForm + 用 Collapse 把折叠字段包起来 —— 但 ExForm 是按 formList 平铺渲染的。
  // 折中方案：折叠区用单独的 Collapse 包住，但字段仍由同一 ExForm 管理。
  // 这里 ExForm 不支持插槽分段，所以退而求其次：折叠区字段在 formList 里 hidden=false，
  // 但我们在 ExForm 下方放一个 Collapse，里面再渲染一个只含折叠字段的 mini ExForm。
  // 为避免双 ExForm 状态冲突，mini ExForm 用受控 formData + onValuesChange 合并回主 form。
  const advancedFormList: FormItem[] = useMemo(
    () => [
      {
        label: maxRoundLabel,
        name: 'max_round',
        type: 'number',
        props: { min: 1, precision: 0, placeholder: '默认即可，无需填' },
      },
      {
        label: contextLabel,
        name: 'context_config',
        type: 'json',
      },
    ],
    [maxRoundLabel, contextLabel],
  )

  const mainFormList: FormItem[] = useMemo(
    () => [
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
          { label: '消息内容', name: 'content', type: 'input', placeholder: '如：导航到虹桥机场T2' },
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
              { label: '消息内容', name: 'content', type: 'input', placeholder: '如：导航到虹桥机场T2' },
            ],
          },
          { label: 'Mock时间', name: 'mock_time', type: 'datetime', placeholder: 'YYYY-MM-DD HH:mm:ss' },
          { label: 'Mock信息', name: 'mock_info', type: 'json' },
        ],
        hidden: userQueryListMode !== 'roundConfig',
        required: userQueryListMode === 'roundConfig',
      },
      {
        label: scriptLabel,
        name: 'expected_script',
        type: 'textarea',
        props: {
          placeholder: '用户：导航到虹桥机场T2\n管家：（开始导航）\n用户：路上放点轻音乐\n管家：（已为您播放轻音乐）',
          autoSize: { minRows: 4, maxRows: 12 },
        },
      },
      {
        label: checkpointLabel,
        name: 'nl_assertion',
        type: 'arrayInput',
        props: {
          placeholder: '如：管家须在回复中明确反馈已开始导航',
        },
      },
    ],
    [coldStartLabel, scriptLabel, checkpointLabel, userQueryListMode],
  )

  const advancedFormProps: FormProps<VoiceCaseFormData> = {
    formList: advancedFormList,
    formData,
    setFormData,
    disabled,
    showAction: false,
    labelWidth: 120,
    onValuesChange: (_changed, allValues) => {
      onChange(
        normalizeVoiceCaseForm({
          ...formData,
          ...allValues,
          case_id: formData.case_id || value.case_id,
        }),
      )
    },
  }

  const mainFormProps: FormProps<VoiceCaseFormData> = {
    formList: mainFormList,
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
      className={[styles.dzyCaseForm, preview ? styles.dzyCaseFormPreview : '']
        .filter(Boolean)
        .join(' ')}
    >
      {!hidePreset && (
        <div className={styles.dzyPresetField}>
          <span className={styles.dzyLabel}>示例</span>
          <Select
            className={styles.dzyPresetSelect}
            value={selectedCaseKey || undefined}
            options={templateSelectOptions}
            disabled={disabled || caseOptions.length === 0}
            placeholder={caseOptions.length === 0 ? '测试集暂无用例' : '请选择用例'}
            optionFilterProp="label"
            onChange={onCaseTemplateChange}
          />
          <span className={styles.dzyHint}>
            {caseOptions.length === 0
              ? '代表性用例加载失败，请检查 case-showcase-config 与测试集'
              : '选择用例后可在下方直接修改内容'}
          </span>
        </div>
      )}
      <ExForm<VoiceCaseFormData> {...mainFormProps} />
      {!preview && (
        <Collapse
          className={styles.dzyAdvancedCollapse}
          activeKey={advancedOpen}
          onChange={(keys) => setAdvancedOpen(typeof keys === 'string' ? [keys] : keys)}
          items={[
            {
              key: 'advanced',
              label: <span className={styles.dzyAdvancedLabel}>更多设置（最大对话轮数 · 上下文配置）</span>,
              children: <ExForm<VoiceCaseFormData> {...advancedFormProps} />,
            },
          ]}
        />
      )}
      {preview && <ExForm<VoiceCaseFormData> {...advancedFormProps} />}
      <WritingGuideModal guide={writingGuide} onClose={() => setWritingGuide(null)} />
    </div>
  )
}

function buildDzyFieldLabel(
  label: string,
  tooltip: string,
  guide: { title: string; items: string[] } | undefined,
  onOpenGuide: (guide: { title: string; items: string[] }) => void,
): React.ReactNode {
  return <CaseFieldLabel label={label} tooltip={tooltip} guide={guide} onOpenGuide={onOpenGuide} />
}

export default DzyCaseForm
