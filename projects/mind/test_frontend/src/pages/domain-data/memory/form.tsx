import { useEffect, useMemo, useState } from 'react'
import Api from '@/apis/domain-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { Radio } from 'antd'
import { DOMAIN_FORM_TYPE_OPTIONS } from '@/constants'

const defaultForm: EpisodicMemory = {}

type Props = {
  formData?: EpisodicMemory
  onSuccess?: () => void
  onCancel?: () => void
}

const memoryItems = [
  { label: '时间', name: 'date_time', type: 'input', placeholder: '请输入时间' },
  { label: '地点', name: 'location', type: 'input', placeholder: '请输入地点' },
  { label: '事件描述', name: 'content', type: 'input', placeholder: '请输入事件描述' },
  { label: '感受', name: 'feel', type: 'input', placeholder: '请输入感受' },
  { label: '其他细节', name: 'details', type: 'json', placeholder: '请输入其他细节' },
]

const App = (props: Props) => {
  const [formData, setFormData] = useState<EpisodicMemory>(defaultForm)
  const [editType, setEditType] = useState<string>('json')

  const formList: FormItem[] = useMemo(() => {
    const list: FormItem[] = [
      {
        label: '摘要信息',
        name: 'brief',
        type: 'input',
        required: true,
      },
      {
        label: '',
        name: 'entity-title',
        type: 'title',
        children: (
          <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
            <b>实体信息</b>
            <Radio.Group
              value={editType}
              options={DOMAIN_FORM_TYPE_OPTIONS}
              size="small"
              optionType="button"
              buttonStyle="solid"
              onChange={(e) => setEditType(e.target.value)}
            />
          </div>
        ),
      },
    ]

    const entityFormList: FormItem[] = [
      {
        label: '瞬时记忆',
        name: ['entity', 'instant'],
        type: 'arrayItem',
        itemList: memoryItems,
      },
      {
        label: '短期记忆',
        name: ['entity', 'short'],
        type: 'arrayItem',
        itemList: memoryItems,
      },
      {
        label: '长期记忆',
        name: ['entity', 'long'],
        type: 'arrayItem',
        itemList: memoryItems,
      },
    ]

    const jsonFormList: FormItem[] = [
      {
        label: '实体信息',
        name: 'entity',
        type: 'json',
      },
    ]

    if (editType === 'json') return [...list, ...jsonFormList]
    if (editType === 'form') return [...list, ...entityFormList]
    return list
  }, [editType])

  useEffect(() => {
    setFormData(props.formData || defaultForm)
  }, [props.formData])

  const formpProps: FormProps<EpisodicMemory> = {
    formList,
    formData,
    setFormData,
    labelWidth: 100,
    createApi: Api.memory.create,
    updateApi: Api.memory.update,
    onCancel: props.onCancel,
    onSuccess: props.onSuccess,
  }

  return (
    <>
      <ExForm<EpisodicMemory> {...formpProps} />
    </>
  )
}

export default App
