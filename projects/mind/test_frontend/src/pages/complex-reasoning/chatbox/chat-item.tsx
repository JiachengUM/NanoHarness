import React, { useMemo, useState } from 'react'
import Markdown from '@/components/Markdown'
import { LoadingOutlined, SendOutlined } from '@ant-design/icons'
import styles from './index.module.less'
import { CHAT_ROLE } from '@/constants/chatbox'
import { Button, Collapse, Space, Tag, Typography } from 'antd'
import JsonViewRender from '@/components/JsonView'

const { Text, Paragraph } = Typography

type Props = {
  loading?: boolean
  data?: Partial<ChatMessage>
  onEvaluate?: () => void
  onMemory?: () => void
}

const renderContent = (item: AgentResult) => {
  if (!item) return <Text type="secondary">（无内容）</Text>

  if (item.type === 'react.start') return

  if (item.type === 'error') return <Text type="danger">{item.reason || '未知错误'}</Text>

  if (item.type === 'react.failed') return <Text type="danger">{item.reason || '未知原因'}</Text>

  if (item.type === 'task_tool.done') return <JsonViewRender value={item.output} collapsed={true} />

  if (item.type === 'react.tool_results.done')
    return <Paragraph>{item.tool_results?.map((e, index) => <pre key={index}>{String(e)}</pre>)}</Paragraph>

  if (item.type === 'react.tool_call.start') return <JsonViewRender value={item.arguments} collapsed={true} />

  if (item.delta || item.text) return <Text type="secondary">{item.delta || item.text}</Text>

  const value = item.response || item.tool_results

  return <JsonViewRender value={value} collapsed={true} />
}

const toolCallRender = (item: AgentResult) => {
  return (
    <Space key={item.event_id}>
      {item.type === 'react.tool_call.start' && <Tag color="green">{item.name}</Tag>}
      <Tag>{item.timestamp}</Tag>
    </Space>
  )
}

const App: React.FC<Props> = ({ loading, data, onEvaluate, onMemory }) => {
  const [activeKey, setActiveKey] = useState<string[]>([])

  const { type = '', content = '' } = data || {}

  const items = useMemo(() => {
    const _items = data?.events?.map((e, index) => {
      return {
        key: String(index),
        label: (
          <>
            <Text type="secondary" style={{ fontSize: 12, marginRight: 8 }}>
              #{index + 1}
            </Text>
            {e.round && <Tag>round: {e.round}</Tag>}
            <Tag icon={<SendOutlined />}>{e.type}</Tag>
          </>
        ),
        children: renderContent(e),
        extra: toolCallRender(e),
      }
    })

    setActiveKey(_items?.map((item) => item.key) || [])

    return _items
  }, [data?.events])

  return (
    <div className={styles.chatItem}>
      <div className={`${styles.chatMessage} ${styles[type || '']}`}>
        {loading && <LoadingOutlined />}
        <div>
          {[CHAT_ROLE.ASSISTANT, CHAT_ROLE.AI].includes(type) && (
            <div>
              <Collapse activeKey={activeKey} items={items} onChange={(e) => setActiveKey(e)} />

              <Markdown content={content || ''}></Markdown>
            </div>
          )}
          {[CHAT_ROLE.USER, CHAT_ROLE.HUMAIN].includes(type) && <span>{content}</span>}
          {[CHAT_ROLE.ASSISTANT, CHAT_ROLE.AI].includes(type) && (
            <div className={styles.tags}>
              <Space>
                <Button style={{ display: 'none' }} variant="outlined" size="small" onClick={() => onMemory?.()}>
                  记忆
                </Button>
                <Button
                  color={data?.human_evaluation ? 'cyan' : 'primary'}
                  variant="outlined"
                  size="small"
                  onClick={() => onEvaluate?.()}
                >
                  评价 {data?.human_evaluation?.overall_score}
                </Button>
              </Space>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
