import React, { useEffect, useState } from 'react'
import styles from './index.module.less'
import { Button, Divider, Input, message, Select, Space, Tabs, type TabsProps } from 'antd'
import { SendOutlined, FileTextOutlined } from '@ant-design/icons'
import CodeEditor from '@/components/CodeEditor'
import world_info_json from '@/assets/template/domain/world_info.json'
import user_json from '@/assets/template/domain/user.json'
import memory_json from '@/assets/template/domain/memory.json'
import vehicle_state_json from '@/assets/template/domain/vehicle_state.json'
import visual_ext_json from '@/assets/template/domain/visual_ext.json'
import visual_int_json from '@/assets/template/domain/visual_int.json'
import context_json from '@/assets/template/domain/context.json'
import { useAdvisorDomainOptions } from '@/hooks/domain-options'
import { useOptions } from '@/hooks/options'
import Api from '@/apis/task-data'
import taskApi, { type AdvisorRunType } from '@/apis/task-data'
import ExDrawer from '@/components/Form/drawer'
import EvalForm from '../advisor-run/eval-form'

type SendData = {
  event?: string
  context?: {
    user?: Record<string, unknown>
    world_info?: Record<string, unknown>
    memory?: Record<string, unknown>
    vehicle_state?: Record<string, unknown>
    visual_ext?: Record<string, unknown>
    visual_int?: Record<string, unknown>
  }
}

const defualtData: SendData = {
  event: '主驾上车了',
  context: {
    user: user_json,
    world_info: world_info_json,
    memory: memory_json,
    vehicle_state: vehicle_state_json,
    visual_ext: visual_ext_json,
    visual_int: visual_int_json,
  },
}

const items: TabsProps['items'] = [
  {
    key: 'dataset',
    label: '数据集',
  },
  {
    key: 'domain',
    label: <span style={{ color: 'red' }}>domain-data</span>,
  },
  {
    key: 'json',
    label: 'JSON 编辑',
  },
  {
    key: 'text',
    label: '文本编辑',
  },
]

const sendTypeOptions = [
  { label: '舒适', value: 'comfort' },
  { label: '情感', value: 'emotion' },
]

const App: React.FC = () => {
  const [messageApi, contextHolder] = message.useMessage()
  const [showType, setShowType] = useState<string>('dataset')
  const [jsonData, setJsonData] = useState('')
  const [textContext, setTextContext] = useState(context_json.context)
  const [data, setData] = useState<SendData>(defualtData)
  const [formData, setFormData] = useState<AdvisorRun | undefined>(undefined)
  const [evalOpen, setEvalOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [sendType, setSendType] = useState<string>('comfort')
  const [response, setResponse] = useState<object>()
  const [datasetId, setDatasetId] = useState<string>()
  const [datasetOptions] = useOptions(Api.advisorDataset.list)
  const [advisorInputOptions] = useOptions(Api.advisorInput.list, { dataset_id: datasetId }, (e) => ({
    label: e.event,
    value: e.id,
    data: e,
  }))

  const options = useAdvisorDomainOptions()

  const domainDataItems = [
    { label: '事件信息', value: 'event', type: 'input' },
    { label: '用户画像', value: 'user', type: 'select', options: options.user },
    { label: '记忆信息', value: 'memory', type: 'select', options: options.memory },
    { label: '世界信息', value: 'world_info', type: 'select', options: options.world_info },
    { label: '车辆状态', value: 'vehicle_state', type: 'select', options: options.vehicle_state },
    { label: '外部视觉信息', value: 'visual_ext', type: 'select', options: options.visual_ext },
    { label: '内部视觉信息', value: 'visual_int', type: 'select', options: options.visual_int },
  ]

  const handleDataChange = (key: string, value: string) => {
    if (key === 'advisor_input') {
      const inputData = advisorInputOptions.find((item) => item.value === value)?.data as SendData

      console.log('Selected advisor input data:', inputData)
      if (inputData) {
        setData(inputData)
      }
      return
    }

    if (key === 'event') {
      setData((prev) => ({
        ...prev,
        event: value,
      }))
      return
    }

    const data = options[key as keyof typeof options]?.find((item) => item.value === value)?.data || value
    setData((prev) => ({
      ...prev,
      context: {
        ...prev.context,
        [key]: data,
      },
    }))
  }

  const handleSend = () => {
    setLoading(true)
    try {
      const bodyData = { event: data.event, context: JSON.parse(jsonData) }

      if (showType === 'text') {
        bodyData.context = textContext
      }

      console.log('Sending data:', bodyData)
      setResponse(undefined)
      setFormData(undefined)

      const runType = `${sendType}${showType === 'text' ? '_quick' : ''}` as AdvisorRunType

      taskApi.advisorRun
        .run(runType, bodyData)
        .then((data) => {
          setResponse(data?.output)
          setFormData(data)
        })
        .catch((error) => {
          console.error('Fetch Error:', error)
          messageApi.error(`服务错误！`)
        })
        .finally(() => {
          setLoading(false)
        })
    } catch {
      console.error('Invalid JSON data')
      setLoading(false)
    }
  }

  const handleEvalSuccess = (data?: AdvisorRun) => {
    setFormData(data)
    setEvalOpen(false)
  }

  useEffect(() => {
    setJsonData(JSON.stringify(data?.context, null, 2))
  }, [data])

  return (
    <>
      {contextHolder}
      <div className={styles.advisor}>
        <div className={styles.domain}>
          <div className={styles.domainHeader}>
            <Tabs items={items} activeKey={showType} onChange={setShowType}></Tabs>
          </div>

          <div className={styles.domainContent}>
            <div
              style={{
                display: showType === 'dataset' ? 'flex' : 'none',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <Space.Compact>
                <Button style={{ width: 120 }}>数据集</Button>
                <Select style={{ width: 260 }} onChange={(e) => setDatasetId(e)} options={datasetOptions}></Select>
              </Space.Compact>
              <Space.Compact>
                <Button style={{ width: 120 }}>测试用例</Button>
                <Select
                  style={{ width: 260 }}
                  onChange={(e) => handleDataChange('advisor_input', e)}
                  options={advisorInputOptions}
                ></Select>
              </Space.Compact>
            </div>

            <div
              style={{
                display: showType === 'domain' ? 'flex' : 'none',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              {domainDataItems.map((item) => {
                if (item.type === 'divider') {
                  return <Divider key="divider" />
                }

                return (
                  <Space.Compact key={item.value}>
                    <Button style={{ width: 120 }}>{item.label}</Button>
                    {item.type === 'input' && item.value === 'event' && (
                      <Input
                        style={{ width: 260 }}
                        value={data.event}
                        onChange={(e) => handleDataChange(item.value, e.target.value)}
                      />
                    )}
                    {item.type === 'input' && item.value !== 'event' && (
                      <Input style={{ width: 260 }} onChange={(e) => handleDataChange(item.value, e.target.value)} />
                    )}
                    {item.type === 'select' && (
                      <Select
                        style={{ width: 260 }}
                        onChange={(e) => handleDataChange(item.value, e)}
                        options={item.options}
                      ></Select>
                    )}
                  </Space.Compact>
                )
              })}
            </div>

            <div
              style={{
                display: showType === 'json' ? 'flex' : 'none',
                height: '100%',
                flexDirection: 'column',
                gap: 16,
              }}
            >
              <Space.Compact>
                <Button style={{ width: 120 }}>事件信息</Button>
                <Input
                  value={data.event}
                  placeholder="输入事件信息"
                  onChange={(e) => handleDataChange('event', e.target.value)}
                ></Input>
              </Space.Compact>
              <div style={{ flex: 1 }}>
                <CodeEditor height="100%" value={jsonData} onChange={setJsonData}></CodeEditor>
              </div>
            </div>

            <div
              style={{
                display: showType === 'text' ? 'flex' : 'none',
                height: '100%',
                flexDirection: 'column',
                gap: 16,
              }}
            >
              <Space.Compact>
                <Button style={{ width: 120 }}>事件信息</Button>
                <Input
                  value={data.event}
                  placeholder="输入事件信息"
                  onChange={(e) => handleDataChange('event', e.target.value)}
                ></Input>
              </Space.Compact>
              <Input.TextArea value={textContext} rows={20} onChange={(e) => setTextContext(e.target.value)} />
            </div>
          </div>
        </div>
        <div className={styles.response}>
          <div className={styles.sendAction}>
            <Select value={sendType} options={sendTypeOptions} onChange={setSendType}></Select>
            <Button loading={loading} icon={<SendOutlined />} onClick={handleSend}>
              发送
            </Button>
            <Button disabled={!formData?.id || loading} icon={<FileTextOutlined />} onClick={() => setEvalOpen(true)}>
              评价
            </Button>
          </div>
          <div style={{ flex: 1 }}>
            <CodeEditor height="100%" readOnly value={response ? JSON.stringify(response, null, 2) : ''} />
          </div>
        </div>
      </div>

      <ExDrawer open={evalOpen} setOpen={setEvalOpen} title="advisor执行评价">
        <EvalForm record={formData} onCancel={() => setEvalOpen(false)} onSuccess={handleEvalSuccess} />
      </ExDrawer>
    </>
  )
}

export default App
