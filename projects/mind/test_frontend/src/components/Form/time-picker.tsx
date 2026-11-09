import React from 'react'
import { TimePicker } from 'antd'
import type { TimePickerProps } from 'antd'
import dayjs from 'dayjs'

type Props = {
  value?: string
  onChange?: (value: string) => void
} & Omit<TimePickerProps, 'value,onChange'>

const App: React.FC<Props> = ({ value, onChange, ...otherProps }) => {
  const handleDateChange: TimePickerProps['onChange'] = (date) => {
    const _date = date ? dayjs(date).format('HH:mm:ss') : ''
    onChange?.(_date)
  }

  return <TimePicker value={value ? dayjs(value, 'HH:mm:ss') : undefined} {...otherProps} onChange={handleDateChange} />
}

export default App
