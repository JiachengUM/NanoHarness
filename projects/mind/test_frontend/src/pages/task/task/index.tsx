import { useEffect, useRef, useState } from 'react'
import { Button, message, Popconfirm, Space } from 'antd'
import type { TableColumnsType } from 'antd'
import Api from '@/apis/task-data'
// import ExDeleteButton from '@/components/DeleteButton'
import ExTable from '@/components/Table'
import type { HandleType } from '@/components/Table'
import Form from './form'
import ExDrawer from '@/components/Form/drawer'
import { formatDateTimeByString } from '@/utils/format'
import { TASK_CONFIG } from '@/constants/agent'
import { useOptions } from '@/hooks/options'
import { getLabelById } from '@/utils'
import { useNavigate } from 'react-router'
import useApiModeStore from '@/stores/apiMode'

const App: React.FC = () => {
  const tableRef = useRef<HandleType<Task>>(null)
  const [open, setOpen] = useState(false)
  const [systemPrompt, setSystemPrompt] = useState<SystemPrompt>()
  const [formData, setFormData] = useState<Task>({})
  const [messageApi, contextHolder] = message.useMessage()
  const navigate = useNavigate()
  const resolvePath = useApiModeStore((s) => s.resolvePath)

  const [toolOptions] = useOptions<string>(Api.complexReasoning.tools, undefined, (e) => ({ label: e, value: e }))
  const [datasetOptions] = useOptions(Api.complexReasoningDataset.list)

  const searchList = [
    { key: 'name', label: '任务名称', type: 'input' },
    { key: 'creator', label: '创建人', type: 'input' },
  ]

  const columns: TableColumnsType<Task> = [
    {
      title: 'ID',
      dataIndex: 'id',
    },
    {
      title: '任务名称',
      dataIndex: 'name',
    },
    {
      title: '数据集',
      dataIndex: 'dataset_id',
      render: (id) => getLabelById(id, datasetOptions),
    },
    {
      title: '任务描述',
      dataIndex: 'description',
    },
    {
      title: '创建人',
      dataIndex: 'creator',
      width: 100,
    },
    {
      title: '创建时间',
      dataIndex: 'created_time',
      render: (_, record) => formatDateTimeByString(record.created_time),
      width: 180,
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_, record) => (
        <Space size="middle">
          <Popconfirm title="运行提示" description="请确认是否要运行此任务？" onConfirm={() => onRun(record)}>
            <a>运行</a>
          </Popconfirm>

          <a onClick={() => onCopy(record)}>复制</a>
          <a onClick={() => onEdit(record)}>编辑</a>
          {/* <ExDeleteButton id={record.id} API={Api.task.del} onSuccess={() => tableRef.current?.refresh()} /> */}
        </Space>
      ),
    },
  ]

  const onAdd = () => {
    const config = {
      ...TASK_CONFIG,
      system_prompt: systemPrompt,
      tools_names: toolOptions.map((e) => e.value || ''),
    }
    console.log(config)
    setFormData({
      config: config,
      metadata: {
        concurrency: 10,
        agent_type: 'BaseAgent',
      },
    })
    setOpen(true)
  }

  const onEdit = (record: Task) => {
    setFormData(record)
    setOpen(true)
  }

  const onCopy = (record: Task) => {
    setFormData({
      ...record,
      id: undefined,
    })
    setOpen(true)
  }

  const onRun = (record: Task) => {
    Api.task.run(record.id as string).then(() => {
      messageApi.success('任务开始运行')
      navigate(resolvePath('/task/task-run'))
    })
  }

  const handleSuccess = () => {
    tableRef.current?.refresh()
    setOpen(false)
  }

  const getSystemPrompt = async () => {
    const prompt = await Api.complexReasoning.systemPrompt()
    setSystemPrompt(prompt)
  }

  useEffect(() => {
    getSystemPrompt()
  }, [])

  return (
    <>
      {contextHolder}
      <ExTable<Task>
        ref={tableRef}
        columns={columns}
        api={Api.task.page}
        searchProps={{
          searchList: searchList,
          action: (
            <Button type="primary" onClick={onAdd}>
              新增
            </Button>
          ),
        }}
      />

      <ExDrawer open={open} setOpen={setOpen} title={formData.id ? '编辑任务' : '新增任务'}>
        <Form formData={formData} onCancel={() => setOpen(false)} onSuccess={handleSuccess} />
      </ExDrawer>
    </>
  )
}

export default App
