import { useEffect, useState } from 'react'
import Api from '@/apis/data-generation'
import ExForm from '@/components/Form'
import type { FormItem, FormProps } from '@/components/Form'

type Props = {
  formData?: GenerationTask
  onSuccess?: () => void
  onCancel?: () => void
}

const TaskForm: React.FC<Props> = (props) => {
  const [formData, setFormData] = useState<GenerationTask>({})

  const formList: FormItem[] = [
    { label: '任务名称', name: 'name', type: 'input', required: true },
    { label: '任务描述', name: 'description', type: 'textarea' },
  ]

  useEffect(() => setFormData(props.formData || {}), [props.formData])

  const formProps: FormProps<GenerationTask> = {
    formList,
    formData,
    setFormData,
    labelWidth: 100,
    createApi: Api.generationTask.create,
    updateApi: Api.generationTask.update,
    onCancel: props.onCancel,
    onSuccess: props.onSuccess,
  }

  return <ExForm<GenerationTask> {...formProps} />
}

export default TaskForm
