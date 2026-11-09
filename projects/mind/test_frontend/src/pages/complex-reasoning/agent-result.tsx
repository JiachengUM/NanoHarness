import React, { useEffect, useRef } from 'react'
import { Card, Tag, Typography } from 'antd'
import { MessageOutlined, ThunderboltOutlined, CheckCircleOutlined, SendOutlined } from '@ant-design/icons'
import JsonViewRender from '@/components/JsonView'

const { Text, Paragraph } = Typography

type Props = {
  data: AgentResponse[]
}

const typeConfig: Record<string, { color: string; label: string; icon: React.ReactNode }> = {
  model_response: { color: 'blue', label: 'Model Response', icon: <MessageOutlined /> },
  tool_calls: { color: 'orange', label: 'Tool Calls', icon: <ThunderboltOutlined /> },
  tool_results: { color: 'green', label: 'Tool Results', icon: <CheckCircleOutlined /> },
}

const getTypeConfig = (type: string) => typeConfig[type] ?? { color: 'default', label: type, icon: <SendOutlined /> }

const AgentResponseItem: React.FC<{ item: AgentResult; index: number }> = ({ item, index }) => {
  const cfg = getTypeConfig(item.type)

  const renderContent = () => {
    if (!item) return <Text type="secondary">（无内容）</Text>

    if (item.type === 'react.start') return

    if (item.type === 'react.tool_results.done')
      return <Paragraph>{item.tool_results?.map((e) => <pre>{e.toString()}</pre>)}</Paragraph>

    if (item.type === 'react.tool_calls.start')
      return (
        <Paragraph>
          <JsonViewRender value={item.arguments} collapsed={true} />
        </Paragraph>
      )

    if (item.delta || item.text) return <Text type="secondary">{item.delta || item.text}</Text>

    const value = item.response || item.arguments || item.tool_results

    return <JsonViewRender value={value} collapsed={true} />
  }

  return (
    <Card
      size="small"
      style={{ borderLeft: `3px solid` }}
      styles={{ header: { padding: '6px 12px' }, body: { padding: '10px 12px' } }}
      extra={item.type === 'react.tool_calls.start' && <JsonViewRender value={item.arguments} collapsed={true} />}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            #{index + 1}
          </Text>
          <Tag color={cfg.color} icon={cfg.icon} style={{ margin: 0 }}>
            {cfg.label}
          </Tag>
        </div>
      }
    >
      {renderContent()}
    </Card>
  )
}

const App: React.FC<Props> = ({ data }) => {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, 100)
  }, [data])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '4px 0' }}>
      {data.map((item, index) => (
        <AgentResponseItem key={index} item={item.content} index={index} />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

export default App
