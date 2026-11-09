import React, { useEffect, useState } from 'react'
import { Input, Tabs } from 'antd'
import type { TabsProps } from 'antd'
import CodeEditor from '@/components/CodeEditor'
import { jsonToString, stringToJson } from '@/utils/json'

type Props = {
  value?: string | object
  onChange?: (value: string | object) => void
  disabled?: boolean
  placeholder?: string
}

const items: TabsProps['items'] = [
  {
    key: 'visual',
    label: '可视化',
  },
  {
    key: 'json',
    label: 'JSON',
  },
  {
    key: 'text',
    label: '文本',
  },
]

const JsonInput: React.FC<Props> = ({ value, onChange, disabled, placeholder }) => {
  const [type, setType] = useState<string>('json')
  const [jsonValue, setJsonValue] = useState<object>()
  const [textValue, setTextValue] = useState<string>('')
  const [jsonEditorValue, setJsonEditorValue] = useState<string>('')

  // JSON 编辑器内容变化
  const handleJsonEditorChange = (v: string) => {
    setJsonEditorValue(v)
    const parsedValue = stringToJson(v, null)
    if (parsedValue !== null) {
      setJsonValue(parsedValue)
      onChange?.(parsedValue)
    }
  }

  // 文本编辑器内容变化
  const handleTextChange = (v: string) => {
    setTextValue(v)
    onChange?.(v)
  }

  const handleTabChange = (key: string) => {
    setType(key)

    if (key === 'json') {
      onChange?.(jsonValue || {})
    } else if (key === 'text') {
      onChange?.(textValue)
    }
    // visual 模式暂不处理
  }

  useEffect(() => {
    if (typeof value === 'object') {
      setJsonValue(value)
      setJsonEditorValue(jsonToString(value))
      setType('json')
    } else {
      setTextValue(value || '')
      setType('text')
    }
  }, [value])

  return (
    <>
      <Tabs activeKey={type} size="small" items={items} onChange={handleTabChange} />
      <div style={{ height: 360 }}>
        {type === 'visual' && <div style={{ padding: 16, color: '#999' }}>可视化编辑功能暂未实现</div>}

        {type === 'json' && (
          <div style={{ border: '1px solid #eee', height: '100%', boxSizing: 'border-box' }}>
            <CodeEditor
              value={jsonEditorValue}
              readOnly={disabled}
              height="100%"
              language="json"
              onChange={handleJsonEditorChange}
            />
          </div>
        )}

        {type === 'text' && (
          <Input.TextArea
            value={textValue}
            disabled={disabled}
            placeholder={placeholder || '请输入文本内容'}
            style={{ height: '100%' }}
            onChange={(e) => handleTextChange(e.target.value)}
          />
        )}
      </div>
    </>
  )
}

export default JsonInput
