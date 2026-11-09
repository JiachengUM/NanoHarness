import React, { useMemo } from 'react'
import { Cascader } from 'antd'
import type { CascaderProps } from 'antd'

type ValueType = number | string

type Props = CascaderProps & {
  value?: ValueType
  onChange?: (value?: ValueType) => void
  options?: CascaderProps['options']
  multiple?: boolean
}

const App: React.FC<Props> = ({ value, onChange, options, ...otherProps }) => {
  const valueArr = useMemo(() => {
    if (!value || !options) return []

    const loop = (arr: CascaderProps['options'], parentIds: ValueType[] = []): ValueType[] => {
      if (!arr) return parentIds

      for (const item of arr) {
        if (item.value === value) return [...parentIds, item.value]

        if (item.value && item.children) {
          const res = loop(item.children, [...parentIds, item.value])
          if (res.length) return res
        }
      }

      return []
    }

    return loop(options)
  }, [value, options])

  const handleDateChange: CascaderProps['onChange'] = (arr) => {
    const value = arr?.[arr.length - 1]

    if (value) onChange?.(value)
  }

  return (
    <Cascader
      allowClear
      showSearch
      expandTrigger="hover"
      value={valueArr}
      options={options}
      onChange={handleDateChange}
      onClear={() => onChange?.(undefined)}
      {...otherProps}
      multiple={false}
    />
  )
}

export default App
