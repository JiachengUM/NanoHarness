import React, { useEffect, useState } from 'react'
import { Button, Drawer, Input, Select, Space } from 'antd'
import type { InputProps } from 'antd'
import { CodeSandboxOutlined } from '@ant-design/icons'
import CodeEditor from '@/components/CodeEditor'
import { filterOption } from '@/utils'

type Props = {
  type?: 'string' | 'object'
  value?: string | object
  onChange?: (value: string | object) => void
  enableString?: boolean
  options?: (OptionItem & { data: Record<string, unknown> })[]
} & InputProps

const jsonToString = (data: object) => {
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return ''
  }
}

const JsonInput: React.FC<Props> = ({ value, onChange, type = 'object', options, enableString = true, ...other }) => {
  const [json, setJson] = useState<string>('')
  const [open, setOpen] = useState<boolean>(false)
  const [language, setLanguage] = useState<'json' | 'text'>('json')

  const stringToJson = (data: string, enableString: boolean) => {
    try {
      setLanguage('json')
      return JSON.parse(data)
    } catch {
      if (enableString) {
        setLanguage('text')
        return data
      }
      return null
    }
  }

  const handleChange: InputProps['onChange'] = (e) => {
    setJson(e.target.value)
  }

  const handleBlur: InputProps['onBlur'] = () => {
    onChange?.(type === 'string' ? json : stringToJson(json, enableString))
  }

  const handleSelectChange = (newValue: string) => {
    const selectedOption = options?.find((option) => option.value === newValue)

    if (selectedOption) {
      const jsonString = jsonToString(selectedOption.data)
      const formattedJson = type === 'string' ? jsonString : selectedOption.data
      setJson(jsonString)
      onChange?.(formattedJson)
    }
  }

  const onClose = () => {
    setOpen(false)
    onChange?.(type === 'string' ? json : stringToJson(json, enableString))
  }

  useEffect(() => {
    if (value == null) return setJson('')

    if (type === 'object') setJson(jsonToString(value as object))

    if (type === 'string') setJson(value as string)
  }, [value, type])

  return (
    <>
      <Space.Compact style={{ width: '100%' }}>
        {!!options?.length && (
          <Select
            onChange={handleSelectChange}
            options={options}
            style={{ maxWidth: 160 }}
            showSearch
            filterOption={filterOption}
          />
        )}
        <Input value={json} onChange={handleChange} onBlur={handleBlur} {...other} />
        <Button type="primary" icon={<CodeSandboxOutlined />} onClick={() => setOpen(true)}></Button>
      </Space.Compact>
      <Drawer
        title="JSON 编辑器"
        width={720}
        placement="right"
        open={open}
        onClose={onClose}
        styles={{
          header: { padding: '14px' },
          body: { padding: 16 },
        }}
      >
        <div style={{ border: '1px solid #eee', height: '100%', boxSizing: 'border-box' }}>
          <CodeEditor value={json} height="100%" language={language} onChange={setJson} />
        </div>
      </Drawer>
    </>
  )
}

export default JsonInput
