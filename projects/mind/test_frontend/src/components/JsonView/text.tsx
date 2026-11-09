import { useEffect, useState } from 'react'
import { Collapse, Tag, Typography, Divider } from 'antd'
import JsonViewRender from './index'

const { Text } = Typography

interface Props {
  value: string | object
}

const LONG_TEXT_THRESHOLD = 120

function isLongOrMultiline(str: string) {
  return str.includes('\n') || str.length > LONG_TEXT_THRESHOLD
}

const MAX_DEPTH = 3

function renderValue(val: unknown, key?: string, depth = 0): React.ReactNode {
  if (val === null) return <Text type="secondary">null</Text>
  if (typeof val === 'boolean') return <Tag color={val ? 'green' : 'red'}>{String(val)}</Tag>
  if (typeof val === 'number') return <Text code>{val}</Text>

  if (typeof val === 'string') {
    if (isLongOrMultiline(val)) {
      return (
        <Collapse
          size="small"
          ghost
          items={[
            {
              key: '1',
              label: <Text type="secondary">{val.slice(0, 60).replace(/\n/g, '↵')}…</Text>,
              children: (
                <pre
                  style={{
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    margin: 0,
                    fontSize: 12,
                    background: '#fafafa',
                    padding: '8px',
                    borderRadius: 4,
                    maxHeight: 400,
                    overflowY: 'auto',
                  }}
                >
                  {val}
                </pre>
              ),
            },
          ]}
        />
      )
    }
    return <Text>{val}</Text>
  }

  if (Array.isArray(val)) {
    if (val.length === 0) return <Text type="secondary">[]</Text>
    if (depth >= MAX_DEPTH) return <JsonViewRender value={val} />
    return (
      <Collapse
        size="small"
        ghost
        items={[
          {
            key: '1',
            label: (
              <Text type="secondary">
                {key ?? 'array'} ({val.length} items)
              </Text>
            ),
            children: (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {val.map((item, idx) => (
                  <div
                    key={idx}
                    style={{
                      borderLeft: '3px solid #d9d9d9',
                      paddingLeft: 10,
                    }}
                  >
                    {/* <Text type="secondary" style={{ fontSize: 11 }}>
                      [{idx}]
                    </Text> */}
                    <div style={{ marginTop: 2 }}>{renderValue(item, undefined, depth + 1)}</div>
                  </div>
                ))}
              </div>
            ),
          },
        ]}
      />
    )
  }

  if (typeof val === 'object') {
    if (depth >= MAX_DEPTH) return <JsonViewRender value={val as object} />
    return <JsonObjectView data={val as Record<string, unknown>} depth={depth + 1} />
  }

  return <Text>{String(val)}</Text>
}

interface JsonObjectViewProps {
  data: Record<string, unknown>
  depth?: number
}

const JsonObjectView: React.FC<JsonObjectViewProps> = ({ data, depth = 0 }) => {
  const entries = Object.entries(data).filter(([, val]) => val !== null && val !== undefined)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {entries.map(([key, val], idx) => (
        <div key={key}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <Text strong style={{ minWidth: 120, flexShrink: 0, wordBreak: 'break-all' }}>
              {key}
            </Text>
            <div style={{ flex: 1, minWidth: 0 }}>{renderValue(val, key, depth)}</div>
          </div>
          {idx < entries.length - 1 && <Divider style={{ margin: '6px 0' }} />}
        </div>
      ))}
    </div>
  )
}

const JsonViewText: React.FC<Props> = ({ value }) => {
  const [dataJson, setDataJson] = useState<Record<string, unknown>>()

  useEffect(() => {
    if (typeof value === 'string') {
      try {
        const parsed = JSON.parse(value)
        setDataJson(typeof parsed === 'object' && parsed !== null ? parsed : { value: parsed })
      } catch {
        setDataJson({ error: 'Invalid JSON string', raw: value })
      }
    } else {
      setDataJson(value as Record<string, unknown>)
    }
  }, [value])

  if (!dataJson) return null

  return (
    <div
      style={{
        padding: '12px',
        background: '#fff',
        borderRadius: 6,
        border: '1px solid #f0f0f0',
      }}
    >
      <JsonObjectView data={dataJson} />
    </div>
  )
}

export default JsonViewText
