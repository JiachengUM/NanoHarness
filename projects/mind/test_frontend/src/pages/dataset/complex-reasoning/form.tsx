import { useEffect, useState } from 'react'
import Api from '@/apis/task-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'

const defaultForm: ComplexReasoningDataset = {}

type Props = {
  formData?: ComplexReasoningDataset
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<ComplexReasoningDataset>(defaultForm)

  const formList: FormItem[] = [
    {
      label: '数据集名称',
      name: 'name',
      type: 'input',
      required: true,
    },
    {
      label: '数据集描述',
      name: 'description',
      type: 'textarea',
    },
  ]

  useEffect(() => {
    setFormData(props.formData || defaultForm)
  }, [props.formData])

  const formpProps: FormProps<ComplexReasoningDataset> = {
    formList,
    formData,
    setFormData,
    labelWidth: 100,
    createApi: Api.complexReasoningDataset.create,
    updateApi: Api.complexReasoningDataset.update,
    onCancel: props.onCancel,
    onSuccess: props.onSuccess,
  }

  return (
    <>
      <ExForm<ComplexReasoningDataset> {...formpProps} />
    </>
  )
}

export default App
