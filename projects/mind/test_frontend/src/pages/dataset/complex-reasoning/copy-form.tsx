import { useEffect, useState } from 'react'
import Api from '@/apis/task-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { useOptions } from '@/hooks/options'

interface CopyFormData extends Common {
  dataset_id?: string
  type?: 'all' | 'partial'
}

type Props = {
  dataset_id?: string
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<CopyFormData>({})
  const [datasetOptions] = useOptions(Api.complexReasoningDataset.list)
  const [datasetItemOptions] = useOptions(Api.complexReasoningCase.list, { dataset_id: props.dataset_id }, (e) => ({
    label: e.case_id,
    value: e.id,
  }))

  const formList: FormItem[] = [
    {
      label: '复制源',
      name: 'dataset_id',
      type: 'select',
      options: datasetOptions,
      required: true,
      disabled: true,
    },
    {
      label: '复制内容',
      name: 'type',
      type: 'radio',
      options: [
        { label: '全部', value: 'all' },
        { label: '部分', value: 'partial' },
      ],
      required: true,
    },
    {
      label: '复制用例',
      name: 'dataset_item_ids',
      type: 'select',
      options: datasetItemOptions,
      props: { mode: 'multiple', maxTagCount: 'responsive' },
      hidden: formData.type !== 'partial',
      required: true,
    },
  ]

  const onFinish = (data: CopyFormData) => {
    if (!data.dataset_id) return
    const dataset_item_ids = data.type === 'partial' ? (data.dataset_item_ids as string[]) : undefined
    Api.complexReasoningDataset.copy(data.dataset_id, dataset_item_ids).then(() => {
      props.onSuccess?.()
    })
  }

  useEffect(() => {
    console.log('dataset_id', props.dataset_id)
    setFormData({ dataset_id: props.dataset_id, type: 'all' })
  }, [props.dataset_id])

  const formpProps: FormProps<CopyFormData> = {
    formList,
    formData,
    setFormData,
    onFinish,
    onCancel: props.onCancel,
    onValuesChange(changeValues, allValues) {
      if (changeValues.type) {
        setFormData({ ...allValues })
      }
    },
  }

  return (
    <>
      <ExForm<CopyFormData> {...formpProps} />
    </>
  )
}

export default App
