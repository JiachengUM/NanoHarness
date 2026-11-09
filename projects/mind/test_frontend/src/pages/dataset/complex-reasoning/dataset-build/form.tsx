import { Tabs, type TabsProps } from 'antd'
import React, { useContext, useState } from 'react'
import ExForm, { type FormItem, type FormProps } from '@/components/Form'
import { useOptions } from '@/hooks/options'
import { MessageContext } from '@/context/messageContext'
import Api from '@/apis/task-data'

type Props = {
  formData: DatasetBuildParams
  setFormData: (data: DatasetBuildParams) => void
  onCancel: () => void
  onSuccess: () => void
}

const App: React.FC<Props> = (props) => {
  const { formData, setFormData, onCancel, onSuccess } = props
  const [activeKey, setActiveKey] = useState('build')
  const [loading, setLoading] = useState(false)
  const [datasetOptions] = useOptions(Api.complexReasoningDataset.list)
  const messageApi = useContext(MessageContext)

  const items: TabsProps['items'] = [
    {
      key: 'build',
      label: '构建新数据集',
    },
    {
      key: 'upsert',
      label: '插入现有数据集',
    },
  ]

  const formList: FormItem[] = [
    {
      label: '插入数据集',
      name: 'dataset_id',
      type: 'select',
      options: datasetOptions,
      hidden: activeKey === 'build',
      required: true,
    },
    {
      label: '数据集名称',
      name: ['dataset', 'name'],
      type: 'input',
      required: true,
      hidden: activeKey === 'upsert',
    },
    {
      label: '描述信息',
      name: ['dataset', 'desc'],
      type: 'textarea',
      props: { rows: 4 },
      hidden: activeKey === 'upsert',
    },
  ]

  const onFinish = (data: DatasetBuildParams) => {
    const _data = { ...data }

    if (activeKey === 'upsert') {
      delete _data.dataset
    } else {
      delete _data.dataset_id
    }
    setLoading(true)
    Api.complexReasoningDataset
      .build(_data)
      .then(() => {
        messageApi.success('构建成功！')
        onSuccess()
      })
      .finally(() => {
        setLoading(false)
      })
  }

  const formpProps: FormProps<DatasetBuildParams> = {
    formList,
    formData,
    setFormData,
    loading: loading,
    labelWidth: 100,
    onFinish,
    onCancel: onCancel,
    onSuccess: onSuccess,
  }

  return (
    <>
      <Tabs activeKey={activeKey} onChange={setActiveKey} items={items} />
      <ExForm<DatasetBuildParams> {...formpProps} />
    </>
  )
}

export default App
