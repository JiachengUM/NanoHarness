import { useEffect, useState } from 'react'
import JsonView, { type JsonViewProps } from '@uiw/react-json-view'

type Props = {
  value: string | object
} & Omit<JsonViewProps<object>, 'value'>

const JsonViewRender: React.FC<Props> = ({
  value,
  enableClipboard = true,
  displayDataTypes = false,
  shortenTextAfterLength = 60,
  ...otherProps
}) => {
  const [dataJson, setDataJson] = useState<object>()

  useEffect(() => {
    if (typeof value === 'string') {
      try {
        setDataJson(JSON.parse(value))
      } catch {
        setDataJson({ error: 'Invalid JSON string' })
      }
    } else {
      setDataJson(value)
    }
  }, [value])

  return (
    <JsonView
      value={dataJson ?? {}}
      enableClipboard={enableClipboard}
      displayDataTypes={displayDataTypes}
      shortenTextAfterLength={shortenTextAfterLength}
      {...otherProps}
    />
  )
}

export default JsonViewRender
