import React from 'react'
import { DatePicker } from 'antd'
import type { DatePickerProps } from 'antd'
import dayjs from 'dayjs'

type Props = {
  value?: string
  onChange?: (value: string) => void
} & Omit<DatePickerProps, 'value,onChange'>

const App: React.FC<Props> = ({ value, onChange, ...otherProps }) => {
  const handleDateChange: DatePickerProps['onChange'] = (date) => {
    const _date = date ? dayjs(date).format('YYYY-MM-DD') : ''
    onChange?.(_date)
  }

  return <DatePicker value={value ? dayjs(value) : undefined} {...otherProps} onChange={handleDateChange} />
}

export default App
