import { useState } from 'react'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'

const defaultForm: AutoChatConfig = {
  query: '北京最近天气怎么样？',
  chat_turns: 5,
  user_profile:
    '你是一个智能汽车车主，刚刚购买汽车，对汽车智能化还不是很熟悉，你性格比较急躁，容易因为一些无法理解的问题而生气甚至发怒。',
  chat_scene: '你正在和车机助手对话，随意发挥和车机助手聊天，中间可掺杂一些车控、POI搜索等聊天方向。',
}

type Props = {
  onFinish?: (data: AutoChatConfig) => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<AutoChatConfig>(defaultForm)

  const formList: FormItem[] = [
    {
      label: 'query',
      name: 'query',
      type: 'textarea',
    },
    {
      label: '用户人设',
      name: 'user_profile',
      type: 'textarea',
    },
    {
      label: '对话场景',
      name: 'chat_scene',
      type: 'textarea',
    },
    {
      label: '对话轮数',
      name: 'chat_turns',
      type: 'number',
    },
  ]

  const formpProps: FormProps<AutoChatConfig> = {
    formList,
    formData,
    setFormData,
    submitText: '开始',
    onFinish: props.onFinish,
    onCancel: props.onCancel,
  }

  return (
    <>
      <ExForm<AutoChatConfig> {...formpProps} />
    </>
  )
}

export default App
