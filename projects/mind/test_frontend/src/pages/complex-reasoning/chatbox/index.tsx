import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ChatInput from './chat-input'
import ChatItemApp from './chat-item'
import styles from './index.module.less'
import { CHAT_ROLE, CHAT_STATUS } from '@/constants/chatbox'
import sseRequest from '@/request/sse'
import { Button, Space } from 'antd'
import ExDrawer from '@/components/Form/drawer'
import ConfigForm from '../config-form'
import { cloneDeep } from 'lodash-es'
import ChatHistory, { type HandleType } from './chat-history'
import { throttle } from 'lodash-es'
import Api from '@/apis/task-data'
import { v4 } from 'uuid'
import EvalForm from './eval-form'
import MemForm from './mem-form'
import AutoChatForm from './auto-chat-form'
import { DEFAULT_AGENT_CONFIG } from '@/constants/agent'

const AGENT_CHAT_URL = '/complex_reasoning_run/base_agent_stream'
const AGENT_AUTO_CHAT_URL = '/complex_reasoning_run/base_agent_stream/auto_chat'
const LOCAL_STORAGE_KEY = 'agent-default-config'

const historyShow = true

const getAgentConfig = () => {
  const storageParams = JSON.parse(localStorage.getItem(LOCAL_STORAGE_KEY) || '{}') as AgentConfig
  if (!storageParams || !storageParams.model) return cloneDeep(DEFAULT_AGENT_CONFIG) as AgentConfig
  return storageParams
}

const App: React.FC = () => {
  const historyRef = useRef<HandleType>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(false)
  const [memOpen, setMemOpen] = useState(false)
  const [autoChatOpen, setAutoChatOpen] = useState(false)
  const [open, setOpen] = useState(false)
  const [evalOpen, setEvalOpen] = useState(false)
  const [evalForm, setEvalForm] = useState<EvaluationForm>()
  const [memoryType, setMemoryType] = useState<'user_profile' | 'memory_config'>('user_profile')
  const [memForm, setMemForm] = useState<AgentMemoryResponse>()
  const [currentSession, setCurrentSession] = useState<ChatSession>({ session_id: v4() })
  const [sessionList, setSessionList] = useState<ChatSession[]>([])
  const [param, setParam] = useState<AgentConfig>(getAgentConfig())
  const [chatList, setChatList] = useState<ChatMessage[]>([])
  const [agentDump, setAgentDump] = useState<AgentV1Dump>()
  const [modelList, setModelList] = useState<{ name: string; value: string }[]>([])

  const query = (formData: ChatRequest, url = AGENT_CHAT_URL, autoChatConfig?: AutoChatConfig) => {
    setChatList((prev) => {
      return [
        ...prev,
        { type: CHAT_ROLE.HUMAIN, content: formData?.message, status: CHAT_STATUS.COMPLETE },
        { type: CHAT_ROLE.AI, status: CHAT_STATUS.LOADING, content: '' },
      ]
    })
    setLoading(true)
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(param))

    const bodyData = cloneDeep({
      config: param,
      query: formData?.message,
      session_id: currentSession?.session_id,
      auto_chat_config: autoChatConfig,
      save_to_db: true,
    })

    if (memoryType === 'user_profile') {
      delete bodyData.config.memory_config
    } else {
      delete bodyData.config.user_profile
    }

    sseRequest(
      url,
      'POST',
      bodyData,
      (e: AgentResult) => {
        if (url === AGENT_CHAT_URL && (e.type === 'react.finish' || e.type === 'react.failed')) setLoading(false)

        setChatList((prev) => {
          if (!prev.length) return prev

          const next = [...prev]
          const lastItem = next[next.length - 1]

          if (e.type === 'human_message') {
            next.push({ type: CHAT_ROLE.HUMAIN, content: e.content, status: CHAT_STATUS.COMPLETE })
            next.push({ type: CHAT_ROLE.AI, status: CHAT_STATUS.LOADING, content: '' })
          } else if (e.type === 'react.text.delta') {
            next[next.length - 1] = {
              ...lastItem,
              content: lastItem.content + (e?.delta || ''),
            }
          } else {
            if (e.type === 'error') setLoading(false)

            next[next.length - 1] = {
              ...lastItem,
              status: e.type,
              events: [...(lastItem.events || []), e],
            }
          }

          localStorage.setItem('agent-chat-list', JSON.stringify(next))

          return next
        })

        throttledScroll()
      },
      () => {
        getSessionList()
        setLoading(false)
      }
    )
  }

  const stop = () => {
    setChatList((prev) => {
      if (!prev.length) return prev

      const current = [...prev]
      const lastItem = current.pop() as ChatMessage
      lastItem.status = 'stop'
      return [...current, lastItem]
    })

    setLoading(false)
  }

  const getModelList = async () => {
    const list = await Api.complexReasoning.models()
    setModelList(list || [])
  }

  const getSessionList = async () => {
    const list = await Api.chatHistory.list()
    setSessionList(list || [])
  }

  const getChatList = async (id?: string) => {
    if (!id) return setChatList([])
    const chatHistory = await Api.chatHistory.get(id)
    setChatList(chatHistory?.messages || [])
    setAgentDump(chatHistory?.agent_instance_dump)
    setLoading(false)
  }

  const onClear = () => {
    setChatList(() => [])
    setLoading(false)
    // setMemoryType('user_profile')
    localStorage.removeItem('agent-chat-list')
    setCurrentSession({ session_id: v4() })
    setParam(getAgentConfig())
  }

  const changSession = (session?: ChatSession) => {
    setCurrentSession(session || { session_id: v4() })
  }

  const onEvaluate = (index: number) => {
    console.log('评价', currentSession?.session_id, index)
    setEvalOpen(true)
    setEvalForm({ id: currentSession?.id, message_index: index, human_evaluation: chatList[index].human_evaluation })
  }

  const onMemory = () => {
    setMemOpen(true)
    Api.complexReasoning.retrieve_memory(currentSession?.session_id || '').then((res) => {
      setMemForm(res)
      console.log('记忆信息', res)
    })
  }

  const handleEvalSuccess = () => {
    setEvalOpen(false)
    getChatList(currentSession?.id)
  }

  const handleMemSuccess = () => {
    setMemOpen(false)
  }

  const onAutoChat = (data: AutoChatConfig) => {
    console.log('自动对话', data)
    onClear()
    setAutoChatOpen(false)
    Promise.resolve().then(() => {
      query({ message: data.query || '' }, AGENT_AUTO_CHAT_URL, data)
    })
  }

  const scrollToBottom = useCallback(() => {
    if (!scrollRef.current) return

    scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [])

  const throttledScroll = useMemo(() => throttle(scrollToBottom, 100), [scrollToBottom])

  useEffect(() => {
    if (agentDump) {
      const ctx = agentDump.context
      setParam((prev) => ({
        ...prev,
        model: modelList.find((item) => item.value === ctx?.model_params?.model)?.name || '',
        max_turns: ctx?.react_max_turns,
        params: ctx?.model_params?.params,
        tools: ctx?.tools_names,
        system_prompt: ctx?.system_prompt,
        memory_config: {
          consumer_config: ctx?.memory_consumer_config,
          producer_config: ctx?.memory_producer_config,
          user_info: ctx?.memory_user_info,
          session_size: ctx?.memory_producer_session_size,
        },
        user_profile: ctx?.user_profile,
      }))

      if (ctx?.memory_consumer_config?.collection_id || ctx?.memory_producer_config?.collection_id) {
        setMemoryType('memory_config')
      } else if (ctx?.user_profile) {
        setMemoryType('user_profile')
      }
    }
  }, [agentDump, modelList])

  useEffect(() => {
    if (!chatList.length) return

    throttledScroll()
  }, [chatList.length, throttledScroll])

  useEffect(() => {
    const exist = sessionList.find((item) => item.session_id === currentSession.session_id)
    if (exist) setCurrentSession(exist)
  }, [sessionList, currentSession?.session_id])

  useEffect(() => {
    getModelList()
    getSessionList()
  }, [])

  useEffect(() => {
    getChatList(currentSession?.id)
  }, [currentSession])

  return (
    <>
      <div className={styles.container}>
        {historyShow && (
          <ChatHistory
            ref={historyRef}
            list={sessionList}
            value={currentSession?.id}
            onCreate={onClear}
            onChange={changSession}
            onDeleteSuccess={getSessionList}
          />
        )}
        <div className={styles.chat}>
          <Space className={styles.config}>
            {/* <Button onClick={() => setAutoChatOpen(true)}>自动对话</Button> */}
            <Button onClick={() => onMemory()}>记忆</Button>
            <Button onClick={() => setOpen(true)}>配置</Button>
          </Space>

          <div ref={scrollRef} className={styles.chatList}>
            {chatList.map((item, index) => (
              <ChatItemApp
                key={index}
                loading={item.status === CHAT_STATUS.LOADING}
                data={item}
                onEvaluate={() => onEvaluate(index)}
                onMemory={() => onMemory()}
              ></ChatItemApp>
            ))}
          </div>
          <ChatInput loading={loading} onSend={query} onStop={stop} />
        </div>
      </div>
      <ExDrawer title="Agent配置" open={open} setOpen={setOpen}>
        <ConfigForm
          value={param}
          disabled={!!chatList.length}
          modelList={modelList}
          onChange={setParam}
          memoryType={memoryType}
          setMemoryType={setMemoryType}
        ></ConfigForm>
      </ExDrawer>

      <ExDrawer title="记忆信息" open={memOpen} setOpen={setMemOpen}>
        <MemForm data={memForm} disabled onCancel={() => setMemOpen(false)} onSuccess={handleMemSuccess} />
      </ExDrawer>

      <ExDrawer title="回复评价" open={evalOpen} setOpen={setEvalOpen}>
        <EvalForm data={evalForm} onCancel={() => setEvalOpen(false)} onSuccess={handleEvalSuccess} />
      </ExDrawer>

      <ExDrawer title="自动对话" open={autoChatOpen} setOpen={setAutoChatOpen}>
        <AutoChatForm onCancel={() => setAutoChatOpen(false)} onFinish={onAutoChat} />
      </ExDrawer>
    </>
  )
}

export default App
