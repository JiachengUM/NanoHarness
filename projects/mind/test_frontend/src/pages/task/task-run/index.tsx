import { useRef, useState } from 'react'
import { Space, Modal, message } from 'antd'
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons'
import type { TableColumnsType } from 'antd'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Api from '@/apis/task-data'
// import ExDeleteButton from '@/components/DeleteButton'
import ExTable from '@/components/Table'
import type { HandleType } from '@/components/Table'
import { formatDateTimeByString } from '@/utils/format'
import { useOptions } from '@/hooks/options'
import { getLabelById } from '@/utils'
import { TASK_RUN_STATUS_OPTIONS } from '@/constants/task'
import useApiModeStore from '@/stores/apiMode'
import ExDrawer from '@/components/Form/drawer'
import Detail from './detail'
import { exportExcelGet } from '@/utils/export'

const App: React.FC = () => {
  const resolvePath = useApiModeStore((s) => s.resolvePath)
  const tableRef = useRef<HandleType<TaskRun>>(null)
  const [open, setOpen] = useState(false)
  const [record, setRecord] = useState<TaskRun>()
  const [aiReportOpen, setAiReportOpen] = useState(false)
  const [aiReportContent, setAiReportContent] = useState<string>('')
  const [aiReportRecord, setAiReportRecord] = useState<TaskRun>()

  const [taskOptions] = useOptions(Api.task.list)
  const [datasetOptions] = useOptions(Api.complexReasoningDataset.list)

  const searchList = [
    { key: 'task_id', label: '测试任务', type: 'select', options: taskOptions },
    { key: 'status', label: '运行状态', type: 'select', options: TASK_RUN_STATUS_OPTIONS },
  ]

  const columns: TableColumnsType<TaskRun> = [
    {
      title: '测试任务',
      dataIndex: 'task_id',
      render: (id) => getLabelById(id, taskOptions),
    },
    {
      title: '数据集',
      dataIndex: 'dataset_id',
      render: (_, record) => {
        const task = taskOptions.find((item) => item.value === record.task_id)?.data as Task
        return getLabelById(task?.dataset_id, datasetOptions)
      },
    },
    {
      title: '进度',
      dataIndex: 'progress',
      render: (progress) => {
        if (!progress?.percent) return ''
        return `${progress.completed} / ${progress.total} [${progress.percent.toFixed(0)}%]`
      },
      width: 150,
    },
    {
      title: '状态',
      dataIndex: 'status',
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
      width: 240,
      render: (_, record) => (
        <Space size="middle">
          <a onClick={() => onReport(record)}>报告</a>
          <a onClick={() => onAiReport(record)}>AI报告</a>
          <a onClick={() => onExport(record)}>导出</a>
          <a href={resolvePath(`/task/task-run/${record.id}`)}>明细</a>
          {/* <ExDeleteButton id={record.id} API={Api.taskRun.del} onSuccess={() => tableRef.current?.refresh()} /> */}
        </Space>
      ),
    },
  ]

  const onReport = (record: TaskRun) => {
    setRecord(record)
    setOpen(true)
  }

  const onExport = (record: TaskRun) => {
    if (!record.id) return
    exportExcelGet(`/task_run/${record.id}/export`, {}, `task_run_${record.id}.xlsx`)
  }

  const onAiReport = async (record: TaskRun) => {
    if (!record.id) return
    setAiReportRecord(record)

    try {
      const detail = await Api.taskRun.get(record.id)
      const aiReport = detail?.metadata?.ai_report

      if (aiReport) {
        setAiReportContent(aiReport)
        setAiReportOpen(true)
        return
      }

      await Api.taskRun.generateReport(record.id)
      message.success('报告正在生成中，预计 3-5 分钟，请稍后刷新页面查看')
      tableRef.current?.refresh()
    } catch (e) {
      message.error('操作失败')
      console.error(e)
    }
  }

  const downloadReport = () => {
    if (!aiReportContent || !aiReportRecord) return
    const blob = new Blob([aiReportContent], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `AI报告_${aiReportRecord.id ?? 'task_run'}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const onRegenerateReport = async () => {
    if (!aiReportRecord?.id) return
    try {
      await Api.taskRun.generateReport(aiReportRecord.id)
      message.success('报告正在重新生成中，预计 3-5 分钟，请稍后刷新页面查看')
      setAiReportOpen(false)
      tableRef.current?.refresh()
    } catch (e) {
      message.error('触发生成报告失败')
      console.error(e)
    }
  }

  return (
    <>
      <ExTable<TaskRun>
        ref={tableRef}
        columns={columns}
        api={Api.taskRun.page}
        searchProps={{
          searchList: searchList,
        }}
      />
      <ExDrawer open={open} setOpen={setOpen} title="测试统计报告">
        {record && <Detail record={record} />}
      </ExDrawer>
      <Modal
        title="AI 测试报告"
        open={aiReportOpen}
        onCancel={() => setAiReportOpen(false)}
        footer={null}
        width={900}
        destroyOnClose
      >
        {aiReportContent && (
          <>
            <div style={{ textAlign: 'right', marginBottom: 8 }}>
              <Space>
                <a onClick={onRegenerateReport}>
                  <ReloadOutlined /> 重新生成
                </a>
                <a onClick={downloadReport}>
                  <DownloadOutlined /> 下载
                </a>
              </Space>
            </div>
            <div
              style={{
                maxHeight: '70vh',
                overflowY: 'auto',
                padding: '16px',
                background: '#fff',
                border: '1px solid #f0f0f0',
                borderRadius: 4,
              }}
              className="markdown-body"
            >
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{aiReportContent}</ReactMarkdown>
            </div>
          </>
        )}
      </Modal>
    </>
  )
}

export default App
