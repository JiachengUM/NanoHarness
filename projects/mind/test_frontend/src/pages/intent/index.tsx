import React, { useEffect, useState } from 'react'
import styles from './index.module.less'
import { Button, Divider, message, Select, Space, Tabs, type TabsProps } from 'antd'
import { FileTextOutlined, SendOutlined } from '@ant-design/icons'
import CodeEditor from '@/components/CodeEditor'
import { useOptions } from '@/hooks/options'
import Api from '@/apis/task-data'
import taskApi from '@/apis/task-data'
import LLMParamForm from './llm-param-form'
import PromptParamForm from './prompt-param-form'
import ExDrawer from '@/components/Form/drawer'
import EvalForm from '../intent-run/eval-form'

type SendData = {
  input?: IntentInput
  param?: IntentParams
}

const defualtData: SendData = {}

const defaultParams: IntentParams = localStorage.getItem('intent-default-params')
  ? JSON.parse(localStorage.getItem('intent-default-params') || '')
  : {
      prompt: {
        categories: [],
        expert_role: '用户意图分类专家',
        output_hint: '仅返回类别名称, 不包括任何其它内容',
      },
      llm_param: {
        model: 'doubao-seed-1-6-flash-250828',
        temperature: 0.3,
        top_p: 0.7,
      },
    }

const sendTypeOptions = [{ label: '意图识别', value: 'intent' }]

const items: TabsProps['items'] = [
  {
    key: 'dataset',
    label: '数据集',
  },
  {
    key: 'param',
    label: '参数配置',
  },
]

const App: React.FC = () => {
  const [messageApi, contextHolder] = message.useMessage()
  const [jsonData, setJsonData] = useState('')
  const [type, setType] = useState<string>('param')
  const [data, setData] = useState<SendData>(defualtData)
  const [formData, setFormData] = useState<IntentRun | undefined>(undefined)
  const [evalOpen, setEvalOpen] = useState(false)
  const [param, setParam] = useState<IntentParams>(defaultParams)
  const [loading, setLoading] = useState(false)
  const [sendType, setSendType] = useState<string>('intent')
  const [response, setResponse] = useState<object>()
  const [datasetId, setDatasetId] = useState<string>()
  const [datasetOptions] = useOptions(Api.intentDataset.list, undefined, (e) => ({
    label: e.name,
    value: e.id,
    data: e,
  }))
  const [intentInputOptions] = useOptions(Api.intentInput.list, { dataset_id: datasetId }, (e) => ({
    label: e.query,
    value: e.id,
    data: e,
  }))

  const handleDataChange = (key: string, value: string) => {
    if (key === 'input') {
      const inputData = intentInputOptions.find((item) => item.value === value)?.data as IntentInput
      const _input = {
        query: inputData?.query || '',
        messages: inputData?.messages || [],
      }

      setJsonData(JSON.stringify(_input, null, 2))

      if (inputData) {
        setData((prev) => ({ ...prev, input: _input }))
      }
      return
    }
  }

  const handleSend = () => {
    setLoading(true)
    try {
      const bodyData = { param: param, input: JSON.parse(jsonData) }
      localStorage.setItem('intent-default-params', JSON.stringify(param))

      setResponse(undefined)
      setFormData(undefined)

      taskApi.intentRun
        .run(bodyData)
        .then((data) => {
          console.log('Response data:', data)
          setFormData(data)
          const response = { output: data.output, trajectory: data.trajectory, total_time: data.total_time }
          setResponse(response)
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
    setJsonData(JSON.stringify(data?.input, null, 2))
  }, [data])

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
                display: type === 'dataset' ? 'flex' : 'none',
                flexDirection: 'column',
                height: '100%',
                gap: '16px',
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
                  onChange={(e) => handleDataChange('input', e)}
                  options={intentInputOptions}
                ></Select>
              </Space.Compact>
              <div style={{ flex: 1 }}>
                <CodeEditor height="100%" value={jsonData} onChange={setJsonData}></CodeEditor>
              </div>
            </div>

            <div>
              <div style={{ display: type === 'param' ? 'block' : 'none', height: '100%' }}>
                <Divider orientation="left">模型参数</Divider>
                <LLMParamForm
                  value={param.llm_param}
                  onChange={(e) => {
                    setParam((prev) => ({ ...prev, llm_param: e }))
                  }}
                ></LLMParamForm>
                <Divider orientation="left">提示词参数</Divider>
                <PromptParamForm
                  value={param.prompt}
                  onChange={(e) => {
                    setParam((prev) => ({ ...prev, prompt: e }))
                  }}
                ></PromptParamForm>
              </div>
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
