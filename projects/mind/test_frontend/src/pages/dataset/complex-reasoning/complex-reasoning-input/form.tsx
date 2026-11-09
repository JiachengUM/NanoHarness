import { useEffect, useMemo, useState } from 'react'
import Api from '@/apis/task-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { LLM_ROLES } from '@/constants'
import { deleteNullKeys } from '@/utils'

const defaultForm: ComplexReasoningCase = {}
type UserQueryListMode = 'messages' | 'roundConfig'

type ComplexReasoningForm = ComplexReasoningCase & {
  user_query_lists_mode?: UserQueryListMode
  user_query_lists_messages?: Message[][]
  user_query_lists_rounds?: DialogueRoundConfig[]
}

const detectMode = (formData?: ComplexReasoningCase): UserQueryListMode => {
  const firstItem = formData?.user_query_lists?.[0]
  return firstItem && !Array.isArray(firstItem) ? 'roundConfig' : 'messages'
}

const toFormData = (formData?: ComplexReasoningCase): ComplexReasoningForm => {
  const mode = detectMode(formData)
  const userQueryLists = formData?.user_query_lists || []

  return {
    ...(formData || defaultForm),
    user_query_lists_mode: mode,
    user_query_lists_messages: userQueryLists.filter((item): item is Message[] => Array.isArray(item)),
    user_query_lists_rounds: userQueryLists.filter(
      (item): item is DialogueRoundConfig => !!item && !Array.isArray(item)
    ),
  }
}

const normalizeSubmitData = (payload: ComplexReasoningForm): ComplexReasoningCase => {
  const { user_query_lists_mode, user_query_lists_messages, user_query_lists_rounds, ...rest } = payload

  return deleteNullKeys({
    ...rest,
    user_query_lists:
      user_query_lists_mode === 'roundConfig' ? user_query_lists_rounds || [] : user_query_lists_messages || [],
  }) as ComplexReasoningCase
}

type Props = {
  formData?: ComplexReasoningCase
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<ComplexReasoningForm>(toFormData(defaultForm))
  const [userQueryListMode, setUserQueryListMode] = useState<UserQueryListMode>('messages')

  const formList: FormItem[] = useMemo(
    () => [
      { label: 'CASE_ID', name: 'case_id', type: 'input', required: true },
      {
        label: '对话记录类型',
        name: 'user_query_lists_mode',
        type: 'radio',
        options: [
          { label: '消息数组 Message[][]', value: 'messages' },
          { label: '轮次配置 DialogueRoundConfig[]', value: 'roundConfig' },
        ],
        required: true,
      },
      {
        label: '前置对话记录',
        name: 'user_query_lists_messages',
        type: 'arrayArrayItem',
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
        label: '前置对话记录',
        name: 'user_query_lists_rounds',
        type: 'arrayItem',
        itemList: [
          {
            label: '消息列表',
            name: 'user_query_list',
            type: 'arrayItem',
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
      { label: '最大对话轮数', name: 'max_round', type: 'number' },
      { label: '上下文配置', name: 'context_config', type: 'json' },
      { label: '剧本', name: 'expected_script', type: 'textarea' },
      { label: '自然语言断言', name: 'nl_assertion', type: 'arrayInput' },
      { label: '代码断言', name: 'code_assertion', type: 'json' },
      { label: '测试用例描述', name: 'case_description', type: 'textarea' },
      { label: '测试用例标签', name: 'tags', type: 'arrayInput' },
    ],
    [userQueryListMode]
  )

  useEffect(() => {
    const nextFormData = toFormData(props.formData || defaultForm)
    setFormData(nextFormData)
    setUserQueryListMode(nextFormData.user_query_lists_mode || 'messages')
  }, [props.formData])

  const formpProps: FormProps<ComplexReasoningForm> = {
    formList,
    formData,
    setFormData,
    createApi: (payload) => Api.complexReasoningCase.create(normalizeSubmitData(payload)),
    updateApi: (payload) => Api.complexReasoningCase.update(normalizeSubmitData(payload)),
    onCancel: props.onCancel,
    onSuccess: props.onSuccess,
    onValuesChange: (changedValues) => {
      if (changedValues.user_query_lists_mode) {
        setUserQueryListMode(changedValues.user_query_lists_mode)
      }
    },
  }

  return (
    <>
      <ExForm<ComplexReasoningForm> {...formpProps} />
    </>
  )
}

export default App
