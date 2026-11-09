import { useEffect, useState } from 'react'
import Api from '@/apis/task-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { useOptions } from '@/hooks/options'

const defaultForm: Task = {}

type Props = {
  formData?: Task
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<Task>(defaultForm)
  const [datasetId, setDatasetId] = useState<string>()
  const [datasetOptions] = useOptions(Api.complexReasoningDataset.list)

  const [datasetItemOptions] = useOptions(Api.complexReasoningCase.list, { dataset_id: datasetId }, (e) => ({
    label: e.case_id,
    value: e.id,
  }))

  const formList: FormItem[] = [
    {
      label: '任务名称',
      name: 'name',
      type: 'input',
      required: true,
    },
    {
      label: '数据集',
      name: 'dataset_id',
      type: 'select',
      options: datasetOptions,
      required: true,
    },
    {
      label: '测试用例',
      name: 'dataset_item_ids',
      type: 'select',
      options: datasetItemOptions,
      props: {
        mode: 'multiple',
      },
    },
    {
      label: 'Agent配置',
      name: 'config',
      type: 'json',
      required: true,
    },
    {
      label: '任务描述',
      name: 'description',
      type: 'textarea',
    },
    {
      label: '元信息',
      name: 'metadata',
      type: 'json',
    },
  ]

  const onValuesChange = (changedValues: Task, allValues: Task) => {
    if (changedValues.dataset_id) {
      allValues.dataset_item_ids = []
    }

    setDatasetId(allValues.dataset_id)
  }

  useEffect(() => {
    console.log(props.formData)
    setDatasetId(props.formData?.dataset_id)
    setFormData(props.formData || defaultForm)
  }, [props.formData])

  const formpProps: FormProps<Task> = {
    formList,
    formData,
    setFormData,
    labelWidth: 100,
    onValuesChange: onValuesChange,
    createApi: Api.task.create,
    updateApi: Api.task.update,
    onCancel: props.onCancel,
    onSuccess: props.onSuccess,
  }

  return (
    <>
      <ExForm<Task> {...formpProps} />
    </>
  )
}

export default App
