import { useEffect, useState } from 'react'
import Api from '@/apis/task-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { useAdvisorDomainOptions } from '@/hooks/domain-options'
import { LLM_ROLES } from '@/constants'

const defaultForm: AdvisorInput = {}

type Props = {
  formData?: AdvisorInput
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<AdvisorInput>(defaultForm)
  const options = useAdvisorDomainOptions()

  const formList: FormItem[] = [
    { label: '意图查询', name: 'query', type: 'textarea', required: true },
    {
      label: '历史对话',
      name: 'messages',
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
  ]

  useEffect(() => {
    if (!options) return

    const formData = props.formData || defaultForm

    setFormData(formData)
  }, [props.formData, options])

  const formpProps: FormProps<AdvisorInput> = {
    formList,
    formData,
    setFormData,
    createApi: Api.intentInput.create,
    updateApi: Api.intentInput.update,
    onCancel: props.onCancel,
    onSuccess: props.onSuccess,
  }

  return (
    <>
      <ExForm<AdvisorInput> {...formpProps} />
    </>
  )
}

export default App
