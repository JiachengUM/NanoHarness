import React, { useEffect, useState } from 'react'
import { Switch } from 'antd'
import type { SwitchProps } from 'antd'

type Props = SwitchProps & {
  value?: string
  onChange?: (value: boolean | number) => void
  type?: 'boolean' | 'number'
}

const App: React.FC<Props> = ({ type = 'boolean', value, onChange, ...switchProps }) => {
  const [switchValue, setSwitchValue] = useState<boolean>(false)

  const handleChange = (e: boolean) => {
    setSwitchValue(e)
    const _value = type === 'boolean' ? e : +e

    onChange?.(_value)
  }

  useEffect(() => {
    setSwitchValue(!!value)
  }, [value])

  return (
    <>
      <Switch value={switchValue} onChange={(e) => handleChange(e)} {...switchProps}></Switch>
    </>
  )
}

export default App
