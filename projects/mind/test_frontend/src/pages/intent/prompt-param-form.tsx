import { useOptions } from '@/hooks/options'
import { Button, Input, Select, Space } from 'antd'
import React, { useEffect } from 'react'
import Api from '@/apis/intent'
import { removeMetaFields } from '@/utils/json'

type Props = {
  value?: IntentClsPrompt
  onChange?: (value: IntentClsPrompt) => void
}

const PromptParamForm: React.FC<Props> = ({ value, onChange }) => {
  const [categoryNames, setCategoryNames] = React.useState<string[]>([])

  const [categoryOptions] = useOptions(Api.category.list, {}, (e) => {
    return { label: e.name, value: e.name, data: e }
  })

  const categoryChange = (value: string[]) => {
    setCategoryNames(value)
    const categories = categoryOptions
      .filter((item) => value.includes(item.label || ''))
      .map((item) => removeMetaFields(item.data as Category))

    handleChange('categories', categories)
  }

  const handleChange = (key: keyof IntentClsPrompt, val: string | Category[] | null) => {
    const newValue = {
      ...value,
      [key]: val,
    }

    onChange?.(newValue)
  }

  useEffect(() => {
    const categories = (value?.categories as Category[]) || ([] as Category[])
    setCategoryNames(categories.map((item) => item.name || ''))
  }, [value])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Space.Compact>
        <Button>意图列表</Button>
        <Select
          style={{ flex: 1 }}
          value={categoryNames}
          placeholder="请选择意图分类列表"
          mode="multiple"
          options={categoryOptions}
          onChange={categoryChange}
        ></Select>
      </Space.Compact>
      <Space.Compact>
        <Button>专家角色</Button>
        <Input.TextArea
          value={value?.expert_role}
          placeholder="请输入模型专家角色"
          onChange={(e) => handleChange('expert_role', e.target.value)}
        ></Input.TextArea>
      </Space.Compact>
      <Space.Compact>
        <Button>输出提示</Button>
        <Input.TextArea
          value={value?.output_hint}
          placeholder="请输入模型输出提示"
          onChange={(e) => handleChange('output_hint', e.target.value)}
        ></Input.TextArea>
      </Space.Compact>
    </div>
  )
}

export default PromptParamForm
