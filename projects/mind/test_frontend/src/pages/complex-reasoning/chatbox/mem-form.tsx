import { useEffect, useState } from 'react'
import MarkdownRenderer from '@/components/Markdown'

type MemoryType = {
  user_profiles?: MemoryContentType[]
  events?: MemoryContentType[]
}

const defaultForm: MemoryType = {}

type Props = {
  data?: AgentMemoryResponse
  disabled?: boolean
  onSuccess?: () => void
  onCancel?: () => void
}

const formatMemoryContent = (value: MemoryContentType): string => {
  if (value === null || value === undefined) return ''

  try {
    if (JSON.parse(String(value))) {
      return '```json\n' + JSON.stringify(JSON.parse(String(value)), null, 2) + '\n```'
    }
  } catch {
    console.log('formatMemoryContent', value)
  }

  console.log('formatMemoryContent', value)
  if (Array.isArray(value)) return value.join('\n')
  return String(value)
}

const App = (props: Props) => {
  const [renderData, setRenderData] = useState<MemoryType>(defaultForm)

  useEffect(() => {
    const user_profiles = props.data?.profiles?.data?.result_list?.map((item) => item.memory_info?.user_profile) || []
    const events = props.data?.events?.data?.result_list?.map((item) => item.memory_info?.summary) || []
    setRenderData({ user_profiles, events })
  }, [props.data])

  const profilesCount = props.data?.profiles?.data?.count ?? 0
  const eventsCount = props.data?.events?.data?.count ?? 0

  return (
    <div style={{ padding: '8px 0' }}>
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>用户画像（{profilesCount} 条）</div>
        {renderData.user_profiles && renderData.user_profiles.length > 0 ? (
          renderData.user_profiles.map((item, index) => (
            <div key={index} style={{ marginBottom: 8, padding: '8px 12px', background: '#f5f5f5', borderRadius: 6 }}>
              <MarkdownRenderer content={formatMemoryContent(item)} />
            </div>
          ))
        ) : (
          <div style={{ color: '#999', fontSize: 13 }}>暂无画像数据</div>
        )}
      </div>

      <div>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>事件记忆（{eventsCount} 条）</div>
        {renderData.events && renderData.events.length > 0 ? (
          renderData.events.map((item, index) => (
            <div key={index} style={{ marginBottom: 8, padding: '8px 12px', background: '#f5f5f5', borderRadius: 6 }}>
              <MarkdownRenderer content={formatMemoryContent(item)} />
            </div>
          ))
        ) : (
          <div style={{ color: '#999', fontSize: 13 }}>暂无事件数据</div>
        )}
      </div>
    </div>
  )
}

export default App
