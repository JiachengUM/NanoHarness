import React, { useEffect, useState } from 'react'
import type { InputProps } from 'antd'
import { type OnMount } from '@monaco-editor/react'
import CodeEditor from '@/components/CodeEditor'
import { jsonToString } from '@/utils/json'

type Props = {
  type?: 'string' | 'object'
  value?: string | object
  onChange?: (value: string | object) => void
} & InputProps

const JsonInput: React.FC<Props> = ({ value, onChange, type = 'object' }) => {
  const [json, setJson] = useState<string>('')

  const handleChange = (e: string) => {
    setJson(e)
  }

  const onMount: OnMount = (editor) => {
    editor.onDidBlurEditorText(() => {
      const value = editor.getValue()

      if (type === 'string') {
        onChange?.(value)
      } else if (type === 'object') {
        try {
          onChange?.(JSON.parse(value))
        } catch {
          console.log('不满足json格式')
        }
      }
    })
  }

  useEffect(() => {
    if (value == null) return setJson('')

    if (type === 'object') setJson(jsonToString(value))

    if (type === 'string') setJson(value as string)
  }, [value, type])

  return (
    <>
      <div style={{ border: '1px solid #eee', height: '100%', boxSizing: 'border-box' }}>
        <CodeEditor value={json} height={420} onMount={onMount} onChange={handleChange} />
      </div>
    </>
  )
}

export default JsonInput
