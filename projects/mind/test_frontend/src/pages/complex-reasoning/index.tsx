import React, { useState } from 'react'
import styles from './index.module.less'
import { Button, message, Select, Space, Switch, Tabs, type TabsProps } from 'antd'
import { SendOutlined } from '@ant-design/icons'
import taskApi from '@/apis/task-data'
import ConfigForm from './config-form'
import AgentResult from './agent-result'
import sseRequest from '@/request/sse'
import { useOptions } from '@/hooks/options'
import CodeEditor from '@/components/CodeEditor'
import { v4 as uuidv4 } from 'uuid'

const defaultData = { query: '检查车辆电池和油量状态，如果油量足够，导航到北京故宫，路上播放轻松的音乐' }
const showDataset = true

const defaultParams: AgentConfig = localStorage.getItem('agent-default-config')
  ? JSON.parse(localStorage.getItem('agent-default-config') || '')
  : {
      model: 'SEED_1_8_251228',
      params: {
        temperature: 0.3,
        top_p: 0.7,
        thinking: { type: 'disabled' },
        caching: { type: 'disabled' },
      },
      tools: ['car_control', 'media', 'navigation', 'music_search', 'poi_search', 'weather_agent', 'websearch'],
      max_turns: 5,
    }

const items: TabsProps['items'] = [
  {
    key: 'query',
    label: 'query',
  },
  {
    key: 'dataset',
    label: 'dataset',
  },
  {
    key: 'param',
    label: '参数配置',
  },
]

const App: React.FC = () => {
  const [messageApi, contextHolder] = message.useMessage()
  const [type, setType] = useState<string>('dataset')
  const [jsonData, setJsonData] = useState(JSON.stringify(defaultData, null, 2))
  const [isStream, setIsStream] = useState<boolean>(true)
  const [param, setParam] = useState<AgentConfig>(defaultParams)
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState<AgentResponse[]>([])
  const [datasetId, setDatasetId] = useState<string>()
  const [datasetOptions] = useOptions(taskApi.complexReasoningDataset.list, undefined, (e) => ({
    label: e.name,
    value: e.id,
    data: e,
  }))
  const [inputOptions] = useOptions(taskApi.complexReasoningCase.list, { dataset_id: datasetId }, (e) => ({
    label: e.case_id,
    value: e.id,
    data: e,
  }))

  const handleDataChange = (key: string, value: string) => {
    if (key === 'input') {
      const inputData = inputOptions.find((item) => item.value === value)?.data as ComplexReasoningCase
      const query = Array.isArray(inputData?.user_query_lists?.[0])
        ? inputData?.user_query_lists?.[0]?.[0]?.content || ''
        : inputData?.user_query_lists?.[0]?.user_query_list?.[0]?.content || ''
      const _input = {
        query,
      }

      setJsonData(JSON.stringify(_input, null, 2))
    }
  }

  const handleClear = () => {
    setResponse([])
  }

  const mergeDeltaData = (data: AgentResponse[]): AgentResponse[] => {
    const result: AgentResponse[] = []
    for (const item of data) {
      const last = result[result.length - 1]
      if (item.type === 'react.text.delta' && last?.type === 'react.text.delta') {
        result[result.length - 1] = {
          ...last,
          content: {
            ...(last.content || {}),
            delta: (last.content?.delta || '') + (item.content?.delta || ''),
          },
        }
      } else {
        result.push(item)
      }
    }
    return result
  }

  const handleSend = () => {
    try {
      const json = JSON.parse(jsonData)
      const query = json?.query || json

      if (!query) return messageApi.warning('请输入query内容！')

      setLoading(true)
      handleClear()
      try {
        const bodyData = { config: param, query, session_id: uuidv4() }
        localStorage.setItem('agent-default-config', JSON.stringify(param))

        setResponse((prev) => {
          const query_content = { type: 'query', text: json.query as string } as AgentResult
          return [...prev, { type: 'query', content: query_content }]
        })

        if (isStream) {
          sseRequest(
            '/complex_reasoning_run/run_stream',
            'POST',
            bodyData,
            (e: AgentResponse) => {
              setResponse((prev) => {
                const last = prev[prev.length - 1]
                if (e.type === 'react.text.delta' && last?.type === 'react.text.delta') {
                  const next = [...prev]
                  const lastItem = next[next.length - 1]

                  next[next.length - 1] = {
                    ...lastItem,
                    content: {
                      ...(lastItem.content || {}),
                      delta: (lastItem.content?.delta || '') + (e.content?.delta || ''),
                    },
                  }

                  return next
                }

                return [...prev, e as AgentResponse]
              })
            },
            () => {
              setLoading(false)
            }
          )
        } else {
          taskApi.complexReasoning
            .run(bodyData)
            .then((data) => {
              setResponse(mergeDeltaData(data || []))
            })
            .catch((error) => {
              console.error('Fetch Error:', error)
              messageApi.error(`服务错误！`)
            })
            .finally(() => {
              setLoading(false)
            })
        }
      } catch {
        console.error('Invalid JSON data')
        setLoading(false)
      }
    } catch {
      return messageApi.warning('请输入query内容！')
    }
  }

  return (
    <>
      {contextHolder}
      <div className={styles.content}>
        <div className={styles.data}>
          <div className={styles.dataHeader}>
            <Tabs items={items} activeKey={type} onChange={setType}></Tabs>
          </div>
          <div className={styles.dataContent}>
            <div
              style={{
                display: type === 'query' ? 'flex' : 'none',
                flexDirection: 'column',
                height: '100%',
                gap: '16px',
              }}
            >
              <div style={{ flex: 1 }}>
                <CodeEditor height="100%" value={jsonData} onChange={setJsonData}></CodeEditor>
              </div>
            </div>
            <div
              style={{
                display: type === 'dataset' ? 'flex' : 'none',
                flexDirection: 'column',
                height: '100%',
                gap: '16px',
              }}
            >
              {showDataset && (
                <>
                  <Space.Compact>
                    <Button style={{ width: 120 }}>数据集</Button>
                    <Select style={{ width: 260 }} onChange={(e) => setDatasetId(e)} options={datasetOptions}></Select>
                  </Space.Compact>
                  <Space.Compact>
                    <Button style={{ width: 120 }}>测试用例</Button>
                    <Select
                      style={{ width: 260 }}
                      onChange={(e) => handleDataChange('input', e)}
                      options={inputOptions}
                    ></Select>
                  </Space.Compact>
                </>
              )}

              <div style={{ flex: 1 }}>
                <CodeEditor height="100%" value={jsonData} onChange={setJsonData}></CodeEditor>
              </div>
            </div>
            <div style={{ display: type === 'param' ? 'flex' : 'none' }}>
              <ConfigForm value={param} onChange={setParam}></ConfigForm>
            </div>
          </div>
        </div>
        <div className={styles.response}>
          <div className={styles.sendAction}>
            <Switch
              checked={isStream}
              checkedChildren="流式"
              unCheckedChildren="非流式"
              onChange={setIsStream}
            ></Switch>
            {/* <Button disabled={loading} onClick={handleClear}>
              清空
            </Button> */}
            <Button loading={loading} icon={<SendOutlined />} onClick={handleSend}>
              发送
            </Button>
          </div>
          <div className={styles.responseContent}>
            <AgentResult data={response || []}></AgentResult>
          </div>
        </div>
      </div>
    </>
  )
}

export default App
