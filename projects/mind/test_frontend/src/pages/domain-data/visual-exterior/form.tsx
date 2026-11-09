import { useEffect, useMemo, useState } from 'react'
import Api from '@/apis/domain-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { Radio } from 'antd'
import { DOMAIN_FORM_TYPE_OPTIONS } from '@/constants'

const defaultForm: VisualExterior = {}

type Props = {
  formData?: VisualExterior
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<VisualExterior>(defaultForm)
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

    const jsonFormList: FormItem[] = [
      {
        label: '实体信息',
        name: 'entity',
        type: 'json',
      },
    ]

    const entityFormList: FormItem[] = [
      {
        label: '天气状态',
        name: ['entity', 'weather'],
        type: 'textarea',
      },
      {
        label: '道路状态',
        name: ['entity', 'road'],
        type: 'textarea',
      },
      {
        label: '建筑状态',
        name: ['entity', 'building'],
        type: 'textarea',
      },
      {
        label: '交通状态',
        name: ['entity', 'traffic'],
        type: 'textarea',
      },
      {
        label: '其他属性',
        name: ['entity', 'other_state'],
        type: 'json',
      },
    ]

    if (editType === 'json') list.push(...jsonFormList)
    if (editType === 'form') list.push(...entityFormList)

    return list
  }, [editType])

  useEffect(() => {
    setFormData(props.formData || defaultForm)
  }, [props.formData])

  const formpProps: FormProps<VisualExterior> = {
    formList,
    formData,
    setFormData,
    labelWidth: 100,
    createApi: Api.visualExt.create,
    updateApi: Api.visualExt.update,
    onCancel: props.onCancel,
    onSuccess: props.onSuccess,
  }

  return (
    <>
      <ExForm<VisualExterior> {...formpProps} />
    </>
  )
}

export default App
