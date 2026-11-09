import { useEffect, useMemo, useState } from 'react'
import Api from '@/apis/domain-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { Radio } from 'antd'
import { DOMAIN_FORM_TYPE_OPTIONS } from '@/constants'

const defaultForm: User = {}

type Props = {
  formData?: User
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<User>(defaultForm)
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
        label: '名字',
        name: ['entity', 'basic_info', 'name'],
        type: 'input',
      },
      {
        label: '年龄',
        name: ['entity', 'basic_info', 'age'],
        type: 'input',
      },
      {
        label: '性别',
        name: ['entity', 'basic_info', 'gender'],
        type: 'input',
      },
      {
        label: '用户偏好',
        name: ['entity', 'profile'],
        type: 'arrayInput',
      },
      {
        label: '其他属性',
        name: ['entity', 'attributes'],
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

  const formpProps: FormProps<User> = {
    formList,
    formData,
    setFormData,
    labelWidth: 100,
    createApi: Api.user.create,
    updateApi: Api.user.update,
    onCancel: props.onCancel,
    onSuccess: props.onSuccess,
  }

  return (
    <>
      <ExForm<User> {...formpProps} />
    </>
  )
}

export default App
