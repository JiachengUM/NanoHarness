import { useMemo } from 'react'
import Editor, { type BeforeMount, type OnMount } from '@monaco-editor/react'
import type * as Monaco from 'monaco-editor'
import { loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker'
import cssWorker from 'monaco-editor/esm/vs/language/css/css.worker?worker'
import htmlWorker from 'monaco-editor/esm/vs/language/html/html.worker?worker'
import tsWorker from 'monaco-editor/esm/vs/language/typescript/ts.worker?worker'

self.MonacoEnvironment = {
  getWorker(_, label) {
    if (label === 'json') {
      return new jsonWorker()
    }
    if (label === 'css' || label === 'scss' || label === 'less') {
      return new cssWorker()
    }
    if (label === 'html' || label === 'handlebars' || label === 'razor') {
      return new htmlWorker()
    }
    if (label === 'typescript' || label === 'javascript') {
      return new tsWorker()
    }
    return new editorWorker()
  },
}

loader.config({ monaco })

loader.init().then(/* ... */)

export type CodeEditorProps = {
  value?: unknown
  defaultValue?: string
  language?: string
  height?: number | string
  width?: number | string
  readOnly?: boolean
  options?: Monaco.editor.IStandaloneEditorConstructionOptions
  theme?: 'light' | 'dark' | 'vs' | 'vs-dark' | 'hc-black'
  className?: string
  style?: React.CSSProperties
  onChange?: (value: string) => void
  onMount?: OnMount
  beforeMount?: BeforeMount
}

const CodeEditor = (props: CodeEditorProps) => {
  const {
    value,
    defaultValue,
    language = 'json',
    height = 320,
    width = '100%',
    readOnly,
    options,
    theme = 'light',
    className,
    style,
    onChange,
    onMount,
    beforeMount,
  } = props

  const handleChange = (val?: string) => {
    const text = val ?? ''

    onChange?.(text)
  }

  const mergedOptions: Monaco.editor.IStandaloneEditorConstructionOptions = useMemo(
    () => ({
      readOnly,
      wordWrap: 'on',
      minimap: { enabled: false },
      automaticLayout: true,
      scrollBeyondLastLine: false,
      tabSize: 2,
      renderWhitespace: 'selection',
      ...options,
    }),
    [options, readOnly]
  )

  return (
    <div style={{ width, height, ...(style || {}) }} className={className}>
      <Editor
        height={height}
        defaultLanguage={language}
        language={language}
        value={
          language === 'json'
            ? typeof value === 'string'
              ? value
              : value
                ? JSON.stringify(value, null, 2)
                : undefined
            : (value as string | undefined)
        }
        defaultValue={defaultValue}
        onChange={handleChange}
        options={mergedOptions}
        theme={theme}
        onMount={onMount}
        beforeMount={beforeMount}
      />
    </div>
  )
}

export default CodeEditor
