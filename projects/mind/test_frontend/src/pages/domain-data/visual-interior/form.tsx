import { useEffect, useMemo, useState } from 'react'
import Api from '@/apis/domain-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { DOMAIN_FORM_TYPE_OPTIONS } from '@/constants'
import { Radio } from 'antd'

const defaultForm: VisualInterior = {}

type Props = {
  formData?: VisualInterior
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<VisualInterior>(defaultForm)
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
        label: '场景信息',
        name: ['entity', 'scenes'],
        type: 'objectItem',
        itemList: [
          {
            label: '人员信息',
            name: 'persons',
            type: 'arrayItem',
            itemList: [
              { label: '位置', name: 'position', type: 'input' },
              { label: '性别', name: 'sex', type: 'input' },
              { label: '年龄', name: 'age', type: 'input' },
              { label: '表情', name: 'expression', type: 'input' },
              { label: '安全带状态', name: 'seat_belt_status', type: 'input' },
              { label: '外观', name: 'appearance', type: 'json' },
              { label: '衣服', name: 'clothes', type: 'json' },
              { label: '配饰', name: 'accessories', type: 'arrayInput' },
              { label: '动作', name: 'action', type: 'arrayInput' },
            ],
          },
          { label: '儿童座椅', name: 'child_seat', type: 'json' },
          { label: '宠物信息', name: 'pet', type: 'json' },
        ],
        props: {
          baseKey: 'vlm_inside',
        },
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

  const formpProps: FormProps<VisualInterior> = {
    formList,
    formData,
    setFormData,
    labelWidth: 100,
    createApi: Api.visualInt.create,
    updateApi: Api.visualInt.update,
    onCancel: props.onCancel,
    onSuccess: props.onSuccess,
  }

  return (
    <>
      <ExForm<VisualInterior> {...formpProps} />
    </>
  )
}

export default App
