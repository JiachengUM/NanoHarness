import { AutoComplete, Button, InputNumber, Space } from 'antd'
import React from 'react'

type Props = {
  value?: LLMParam
  onChange?: (value: LLMParam) => void
}

const LLMParamForm: React.FC<Props> = ({ value, onChange }) => {
  const handleChange = (key: keyof LLMParam, val: string | number | null) => {
    const newValue = {
      ...value,
      [key]: val,
    }
    onChange?.(newValue)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Space.Compact>
        <Button style={{ width: 110 }}>模型</Button>
        <AutoComplete
          style={{ flex: 1 }}
          value={value?.model}
          placeholder="请选择或输入模型"
          onChange={(e) => handleChange('model', e)}
        ></AutoComplete>
      </Space.Compact>
      <Space.Compact>
        <Button style={{ width: 110 }}>temperature</Button>
        <InputNumber
          style={{ flex: 1 }}
          value={value?.temperature}
          placeholder="请输入模型temperature"
          onChange={(e) => handleChange('temperature', e)}
        ></InputNumber>
      </Space.Compact>
      <Space.Compact>
        <Button style={{ width: 110 }}>top_p</Button>
        <InputNumber
          style={{ flex: 1 }}
          value={value?.top_p}
          placeholder="请输入模型top_p"
          onChange={(e) => handleChange('top_p', e)}
        ></InputNumber>
      </Space.Compact>
    </div>
  )
}

export default LLMParamForm
