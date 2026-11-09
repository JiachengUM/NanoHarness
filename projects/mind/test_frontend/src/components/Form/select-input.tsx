import React, { useEffect, useState } from 'react'
import { Input, Select, Space } from 'antd'
import type { InputProps, SelectProps } from 'antd'
import { SwapOutlined } from '@ant-design/icons'
import { filterOption } from '@/utils'
import { isObjectId } from '@/utils/validate'

type Mode = 'input' | 'select'

type Props = {
  value?: string
  onChange?: (value: string) => void
  options?: SelectProps['options'] & { data?: Record<string, unknown> }
  placeholder?: string
  disabled?: boolean
  selectProps?: Omit<SelectProps, 'value' | 'onChange'>
  inputProps?: Omit<InputProps, 'value' | 'onChange'>
  defaultMode?: Mode
}

const SelectInput: React.FC<Props> = ({
  value,
  onChange,
  options = [],
  selectProps,
  inputProps,
  defaultMode = 'input',
  placeholder,
  disabled,
}) => {
  const [mode, setMode] = useState<Mode>(defaultMode)
  const [inputValue, setInputValue] = useState<string>('')
  const [selectValue, setSelectValue] = useState<string>('')

  // 根据 value 自动判断模式
  useEffect(() => {
    if (value == null || value === '') {
      setInputValue('')
      setSelectValue('')
      return
    }

    // 如果是 ObjectId，设置为选择模式
    if (isObjectId(value)) {
      setSelectValue(value)
      setMode('select')
    } else {
      setInputValue(value)
      setMode('input')
    }
  }, [value])

  const handleInputChange: InputProps['onChange'] = (e) => {
    const newValue = e.target.value
    setInputValue(newValue)
    onChange?.(newValue)
  }

  const handleSelectChange: SelectProps['onChange'] = (newValue) => {
    setSelectValue(newValue as string)
    onChange?.(newValue as string)
  }

  const handleModeChange = (newMode: Mode) => {
    setMode(newMode)
    // 切换模式时，触发对应模式的值
    if (newMode === 'input') {
      onChange?.(inputValue)
    } else {
      onChange?.(selectValue)
    }
  }

  const modeOptions = [
    { label: '输入', value: 'input' },
    { label: '选择', value: 'select' },
  ]

  return (
    <Space.Compact style={{ width: '100%' }}>
      {mode === 'input' ? (
        <Input
          value={inputValue}
          onChange={handleInputChange}
          placeholder={placeholder}
          disabled={disabled}
          {...inputProps}
        />
      ) : (
        <Select
          value={selectValue}
          onChange={handleSelectChange}
          options={options}
          showSearch
          allowClear
          placeholder={placeholder}
          disabled={disabled}
          filterOption={filterOption as SelectProps['filterOption']}
          {...selectProps}
        />
      )}
      <Select
        value={mode}
        onChange={handleModeChange}
        options={modeOptions}
        style={{ width: 80 }}
        suffixIcon={<SwapOutlined />}
      />
    </Space.Compact>
  )
}

export default SelectInput
